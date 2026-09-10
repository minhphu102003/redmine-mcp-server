"""Undecorated personnel/performance tool implementations for manager oversight.

Two read-only tools used by the boss workflow:

- ``list_personnel_impl``: unique project members across projects
  (step 1 — boss picks a person).
- ``get_person_work_summary_impl``: per-person performance for a day or a
  Monday-to-Sunday week, grouped by project (step 3 — backend aggregates,
  the AI agent renders the UI).

Both are pure reads and work under any auth mode; person resolution via the
admin ``/users.json`` API requires an admin API key (boss key).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from ...serializers.content import wrap_insecure_content

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

_PAGE_SIZE = 100

# Max characters of an issue description kept in task_context (weekly
# note material). Long enough to name the module, short enough to keep
# the compact payload small.
_TASK_CONTEXT_DESC_LIMIT = 1500

# Vietnamese weekday labels, Monday-first, for widget_data keys.
_VI_DAY_NAMES = [
    "Thứ 2",
    "Thứ 3",
    "Thứ 4",
    "Thứ 5",
    "Thứ 6",
    "Thứ 7",
    "Chủ nhật",
]


# --- Small date helpers ---


def _parse_day(value: Optional[str]) -> Union[date, Dict[str, Any]]:
    """Parse an optional YYYY-MM-DD string, defaulting to the server date."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return date.today()
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return {
            "error": (
                f"Invalid date '{value}'. Expected YYYY-MM-DD " "(e.g. 2026-09-03)."
            )
        }


def _week_range(day: date) -> tuple[date, date]:
    """Return the Monday-to-Sunday range containing ``day``."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def _as_date(value: Any) -> Optional[date]:
    """Coerce a date/datetime/ISO-string value to a date, else None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _user_display_name(user: Any) -> str:
    """Best-effort display name for a /users.json user object."""
    name = getattr(user, "name", None)
    if name:
        return str(name)
    full = " ".join(
        part
        for part in (
            str(getattr(user, "firstname", "") or "").strip(),
            str(getattr(user, "lastname", "") or "").strip(),
        )
        if part
    )
    if full:
        return full
    login = getattr(user, "login", None)
    return str(login) if login else f"user #{getattr(user, 'id', '?')}"


def _round2(value: Any) -> float:
    """Coerce to float rounded to 2 decimals (0.0 on garbage)."""
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _done_ratio_100(issue: Any) -> bool:
    """Whether the issue counts as completed (done_ratio == 100)."""
    try:
        return int(float(getattr(issue, "done_ratio", 0) or 0)) == 100
    except (TypeError, ValueError):
        return False


def _is_completed(issue: Any, closed_ids: set) -> bool:
    """Whether the issue counts as completed (boss rule).

    Completed = done_ratio == 100 with a Done status, or any status
    flagged ``is_closed`` in Redmine. Matching Done by status name
    (case-insensitive) instead of a hardcoded id keeps this portable
    across Redmine instances with custom status ids.
    """
    status = getattr(issue, "status", None)
    if status is not None and getattr(status, "id", None) in closed_ids:
        return True
    return _done_ratio_100(issue) and (
        str(getattr(status, "name", "") or "").lower() == "done"
    )


def _quality_flag(issue: Any, closed_ids: set) -> Optional[str]:
    """Flag contradictory status/done_ratio combos needing Redmine cleanup.

    Returns a human-readable reason, or None when the record is sane.
    """
    status = getattr(issue, "status", None)
    name = str(getattr(status, "name", "") or "")
    ratio100 = _done_ratio_100(issue)
    is_closed_status = status is not None and getattr(status, "id", None) in closed_ids
    if ratio100 and not is_closed_status and name.lower() != "done":
        return (
            f"done_ratio is 100 but status is '{name}' (looks finished "
            "yet still counts as open)"
        )
    if not ratio100 and name.lower() == "done":
        return "status is Done but done_ratio is below 100 " "(progress not recorded)"
    return None


def _truncate_description(value: Any, limit: int = _TASK_CONTEXT_DESC_LIMIT) -> str:
    """Trim an issue description to a short, note-ready excerpt.

    Non-string or missing values become "". Raw Redmine Textile is kept
    as-is (no markup parsing) so the agent always sees grounded text.
    """
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _task_context_entry(
    issue: Any,
    base_url: str,
    week_hours: float,
    completed_flag: bool,
    lifetime_hours: float = 0.0,
    prior_hours: float = 0.0,
    role: str = "owner",
) -> Dict[str, Any]:
    """One task's weekly-note material: what it is + what it says.

    Covers issues completed in the window and in-progress issues with
    hours logged in the window. The description is truncated and wrapped
    as insecure content (same convention as the issue serializers), so
    agents must strip the wrapper tags before quoting it.

    ``week_hours`` counts this user's logs inside the viewed window
    only; ``lifetime_hours`` counts all their logs on the issue across
    every week, and ``prior_hours`` is the out-of-window part
    (lifetime minus window). Overrun judgments must use lifetime, not
    the window slice.

    ``role`` is "owner" (assigned to this user), "supporting" (someone
    else's open task this user logged hours on) or "supported"
    (someone else's closed task this user contributed hours to).
    """
    project = getattr(issue, "project", None)
    status = getattr(issue, "status", None)
    issue_id = getattr(issue, "id", None)
    return {
        "id": issue_id,
        "subject": getattr(issue, "subject", ""),
        "project": (
            {"id": project.id, "name": getattr(project, "name", "")}
            if project is not None
            else None
        ),
        "status": getattr(status, "name", "") or "",
        "completed": completed_flag,
        "role": role,
        "week_hours": _round2(week_hours),
        "lifetime_hours": _round2(lifetime_hours),
        "prior_hours": _round2(prior_hours),
        "description": wrap_insecure_content(
            _truncate_description(getattr(issue, "description", ""))
        ),
        "url": (f"{base_url}/issues/{issue_id}" if base_url and issue_id else None),
    }


def _lifetime_split(
    issue_id: Any,
    window_by_issue: Dict[Any, float],
    lifetime_by_issue: Dict[Any, float],
) -> tuple:
    """(lifetime, prior) hours for one issue, both rounded.

    Lifetime is clamped to at least the window total so a partial
    lifetime fetch can never report less than the viewed week. Prior
    (out-of-window) is lifetime minus window, never negative.
    """
    window = window_by_issue.get(issue_id, 0.0)
    lifetime = max(lifetime_by_issue.get(issue_id, 0.0), window)
    return _round2(lifetime), _round2(lifetime - window)


def _issue_brief(
    issue: Any, base_url: str, actual_hours: float = 0.0
) -> Dict[str, Any]:
    """Compact, UI-ready issue summary for grouped performance views."""
    project = getattr(issue, "project", None)
    status = getattr(issue, "status", None)
    updated = getattr(issue, "updated_on", None)
    issue_id = getattr(issue, "id", None)
    url = f"{base_url}/issues/{issue_id}" if base_url and issue_id else None
    estimated = getattr(issue, "estimated_hours", None)
    return {
        "id": issue_id,
        "subject": getattr(issue, "subject", ""),
        "project": (
            {"id": project.id, "name": project.name} if project is not None else None
        ),
        "status": (
            {"id": status.id, "name": status.name} if status is not None else None
        ),
        "due_date": (_as_date(getattr(issue, "due_date", None)) or None),
        "done_ratio": getattr(issue, "done_ratio", None),
        "estimated_hours": (_round2(estimated) if estimated is not None else None),
        "actual_hours": _round2(actual_hours),
        "updated_on": (
            updated.isoformat()
            if isinstance(updated, datetime)
            else (str(updated) if updated is not None else None)
        ),
        "url": url,
    }


def _issue_brief_json_safe(brief: Dict[str, Any]) -> Dict[str, Any]:
    """Convert date objects in a brief to ISO strings for JSON transport."""
    due = brief.get("due_date")
    if isinstance(due, date):
        brief["due_date"] = due.isoformat()
    return brief


async def _fetch_all_pages(filter_fn: Callable[..., Any], **kwargs: Any) -> List[Any]:
    """Fetch every page (100/page) of a python-redmine filter call."""
    items: List[Any] = []
    offset = 0
    while True:
        page = await asyncio.to_thread(
            lambda: list(filter_fn(limit=_PAGE_SIZE, offset=offset, **kwargs))
        )
        items.extend(page)
        if len(page) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return items


# --- Tool 1: personnel list ---


async def list_personnel_impl(
    project_ids: Optional[List[int]] = None,
    *,
    get_client: Callable[[], Any],
    membership_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """List unique project members across projects (boss step 1)."""
    try:
        client = get_client()
        if client is None:
            return handle_error(
                RuntimeError("Redmine client not initialized"),
                "listing personnel",
                None,
            )

        if project_ids:
            projects = [{"id": pid, "name": None} for pid in project_ids]
        else:
            all_projects = await asyncio.to_thread(client.project.all)
            projects = [
                {"id": p.id, "name": getattr(p, "name", "")} for p in all_projects
            ]

        people: Dict[Any, Dict[str, Any]] = {}
        project_names: Dict[Any, str] = {}
        errors: List[Dict[str, Any]] = []
        group_count = 0

        for project in projects:
            pid = project["id"]
            try:
                memberships = await asyncio.to_thread(
                    client.project_membership.filter, project_id=pid
                )
            except Exception as exc:  # noqa: BLE001 - partial results kept
                errors.append({"project_id": pid, "error": str(exc)})
                continue
            for membership in memberships:
                entry = membership_to_dict(membership)
                user = entry.get("user")
                if user is None:
                    group_count += 1
                    continue
                uid = user.get("id")
                pname = project.get("name")
                if pname is None:
                    pname = project_names.get(pid, "")
                else:
                    project_names[pid] = pname
                roles = [
                    r.get("name", "")
                    for r in (entry.get("roles") or [])
                    if isinstance(r, dict)
                ]
                person = people.setdefault(
                    uid,
                    {
                        "id": uid,
                        "name": user.get("name", ""),
                        "projects": [],
                    },
                )
                if not person["name"] and user.get("name"):
                    person["name"] = user.get("name", "")
                person["projects"].append({"id": pid, "name": pname, "roles": roles})

        personnel = sorted(
            people.values(), key=lambda p: (str(p.get("name") or ""), p["id"])
        )
        return {
            "personnel": personnel,
            "count": len(personnel),
            "project_count": len(projects),
            "groups_skipped": group_count,
            "errors": errors,
        }
    except Exception as e:
        return handle_error(e, "listing personnel", None)


# --- Tool 2: per-person windowed performance summary ---


async def _resolve_person(
    client: Any, person: Union[int, str]
) -> Union[Dict[str, Any], Dict[str, str]]:
    """Resolve a person (id or name/login) via the admin users API."""
    if isinstance(person, int) or (
        isinstance(person, str) and person.strip().isdigit()
    ):
        uid = int(str(person).strip())
        try:
            user = await asyncio.to_thread(client.user.get, uid)
        except Exception:
            return {"error": f"No Redmine user with id {uid}."}
        return {
            "id": getattr(user, "id", uid),
            "name": _user_display_name(user),
            "login": getattr(user, "login", None),
            "mail": getattr(user, "mail", None),
        }

    query = str(person).strip()
    matches = await asyncio.to_thread(lambda: list(client.user.filter(name=query)))
    active = [u for u in matches if getattr(u, "status", 1) == 1]
    if not matches or not active:
        return {
            "error": (
                f"No active Redmine user matching '{query}'. "
                "Ask boss to pick from the personnel list."
            )
        }
    if len(active) > 1:
        return {
            "error": (
                f"Multiple users match '{query}'. Ask boss to pick one: "
                + ", ".join(
                    f"{_user_display_name(u)}"
                    f" (id {getattr(u, 'id', '?')}"
                    f"{', ' + str(getattr(u, 'login', '')) if getattr(u, 'login', None) else ''})"  # noqa: E501
                    for u in active
                )
            )
        }
    user = active[0]
    return {
        "id": getattr(user, "id", None),
        "name": _user_display_name(user),
        "login": getattr(user, "login", None),
        "mail": getattr(user, "mail", None),
    }


async def get_person_work_summary_impl(
    person: Union[int, str],
    window: str = "day",
    date_str: Optional[str] = None,
    project_ids: Optional[List[int]] = None,
    compact: bool = False,
    *,
    get_client: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Summarize one person's performance for a day or Mon-Sun week.

    Besides the grouped detail (skipped when ``compact`` is True), always
    returns     ``completed`` (done_ratio == 100 with a Done status, or a
    closed status, updated in the window), ``completed_total`` (all-time
    count of completed issues assigned to the person, count only),
    ``data_quality_flags`` (contradictory status/done_ratio records
    needing Redmine cleanup), ``task_context`` (completed issues plus
    in-progress issues with hours logged in the window, each with a
    truncated description for the agent-written weekly note — also
    returned when ``compact`` is True) and ``widget_data`` — per-day time-log
    entries bucketed per weekday with estimate vs same-day hours, a
    lifetime ``total`` per issue, plus a completion flag, ready to embed
    verbatim into the oversight widget. Keys always cover Mon-Sun.

    Every widget row and task-context entry carries a ``role``:
    "owner" (assigned to this person — the only rows that count toward
    completion), "supporting" (someone else's open task this person
    logged hours on in the window) or "supported" (someone else's
    closed task this person contributed hours to). Contributor rows
    never count toward completed/backlog/overdue totals.

    Hours scope: ``actual_hours`` per issue and ``totals.hours`` count
    ONLY time logged by this user inside the viewed window (see
    ``evidence.hours_scope``). 0.0 means "no hours logged in this
    window", never "this task never had hours".
    """
    if window not in ("day", "week"):
        return {"error": f"Invalid window '{window}'. Use 'day' or 'week'."}
    day = _parse_day(date_str)
    if isinstance(day, dict):
        return day

    if window == "day":
        start, end = day, day
    else:
        start, end = _week_range(day)
    today = date.today()

    try:
        client = get_client()
        if client is None:
            return handle_error(
                RuntimeError("Redmine client not initialized"),
                "summarizing person workload",
                None,
            )

        resolved = await _resolve_person(client, person)
        if "error" in resolved:
            return resolved
        uid = resolved["id"]
        base_url = str(getattr(client, "url", "") or "").rstrip("/")

        scope = set(project_ids) if project_ids else None

        def in_scope(issue: Any) -> bool:
            if scope is None:
                return True
            project = getattr(issue, "project", None)
            return project is not None and project.id in scope

        # Independent reads fetched concurrently: statuses, window +
        # lifetime time entries, touched issues, full assigned backlog.
        # Total latency is the slowest call, not the sum. Any failure
        # still aborts into the outer error handler, as before.
        (
            statuses,
            time_entries,
            lifetime_entries,
            touched_raw,
            backlog_raw,
        ) = await asyncio.gather(
            asyncio.to_thread(client.issue_status.all),
            _fetch_all_pages(
                client.time_entry.filter,
                user_id=uid,
                from_date=start.isoformat(),
                to_date=end.isoformat(),
            ),
            _fetch_all_pages(
                client.time_entry.filter,
                user_id=uid,
            ),
            _fetch_all_pages(
                client.issue.filter,
                assigned_to_id=uid,
                status_id="*",
                updated_on=f">={start.isoformat()}",
                sort="updated_on:desc",
            ),
            _fetch_all_pages(
                client.issue.filter,
                assigned_to_id=uid,
                sort="due_date:asc",
            ),
        )
        closed_ids = {s.id for s in statuses if bool(getattr(s, "is_closed", False))}

        # Activity: time logged in the window.
        hours_total = 0.0
        hours_by_project: Dict[Any, float] = {}
        actual_by_issue: Dict[Any, float] = {}
        # Per-day hours per issue: (issue_id, spent_on ISO date) -> hours.
        # Drives the widget "hours" field (hours logged on that day only).
        hours_by_issue_day: Dict[tuple, float] = {}
        for entry in time_entries:
            entry_hours = _round2(getattr(entry, "hours", 0))
            hours_total += entry_hours
            project = getattr(entry, "project", None)
            if project is not None and (scope is None or project.id in scope):
                hours_by_project[project.id] = (
                    hours_by_project.get(project.id, 0.0) + entry_hours
                )
            entry_issue = getattr(entry, "issue", None)
            entry_issue_id = (
                getattr(entry_issue, "id", None) if entry_issue is not None else None
            )
            if entry_issue_id is not None:
                actual_by_issue[entry_issue_id] = (
                    actual_by_issue.get(entry_issue_id, 0.0) + entry_hours
                )
                spent_day = _as_date(getattr(entry, "spent_on", None))
                if spent_day is not None and start <= spent_day <= end:
                    day_key = (entry_issue_id, spent_day.isoformat())
                    hours_by_issue_day[day_key] = (
                        hours_by_issue_day.get(day_key, 0.0) + entry_hours
                    )

        # Lifetime hours per issue for this user (all weeks, no date
        # bounds). Drives the widget v4 "total" field and the
        # task_context lifetime/prior hours so week-spanning issues
        # report the true overrun (est vs lifetime) instead of the
        # window slice only. One extra paginated call per summary.
        lifetime_by_issue: Dict[Any, float] = {}
        for entry in lifetime_entries:
            entry_issue = getattr(entry, "issue", None)
            entry_issue_id = (
                getattr(entry_issue, "id", None) if entry_issue is not None else None
            )
            if entry_issue_id is not None:
                lifetime_by_issue[entry_issue_id] = lifetime_by_issue.get(
                    entry_issue_id, 0.0
                ) + _round2(getattr(entry, "hours", 0))

        # Activity: assigned issues touched in the window (any status).
        touched = [
            issue
            for issue in touched_raw
            if in_scope(issue)
            and (_as_date(getattr(issue, "updated_on", None)) or date.min) <= end
        ]
        closed_in_window = [
            issue
            for issue in touched
            if getattr(getattr(issue, "status", None), "id", None) in closed_ids
        ]

        # Backlog snapshot: issues assigned to the person that are still
        # open. Completed issues (done_ratio 100 + Done status, or a
        # closed status) are split out so open/overdue counts only cover
        # work that is genuinely outstanding.
        backlog: List[Any] = []
        backlog_completed: List[Any] = []
        for issue in backlog_raw:
            if not in_scope(issue):
                continue
            if _is_completed(issue, closed_ids):
                backlog_completed.append(issue)
            else:
                backlog.append(issue)
        overdue = [
            issue
            for issue in backlog
            if (_due := _as_date(getattr(issue, "due_date", None))) is not None
            and _due < today
            and getattr(getattr(issue, "status", None), "id", None) not in closed_ids
        ]
        no_due_date = [
            issue
            for issue in backlog
            if _as_date(getattr(issue, "due_date", None)) is None
        ]

        # Completed in the window: done_ratio == 100 with a Done status,
        # or a closed status (boss rule).
        completed = [issue for issue in touched if _is_completed(issue, closed_ids)]

        # Contributor issues: tasks with hours logged by this user in the
        # window that are NOT assigned to them (someone else's task they
        # helped with). Resolved individually so the widget and the weekly
        # note can credit the work with a contributor role instead of
        # dropping it from named rows. Fetch failures (no permission,
        # deleted issue) are skipped silently — the hours stay in the
        # totals either way.
        assigned_ids = {
            getattr(i, "id", None) for i in touched + backlog + backlog_completed
        }
        contrib_issues: Dict[Any, Any] = {}
        contrib_sem = asyncio.Semaphore(5)

        async def _fetch_contrib(
            logged_id: Any,
        ) -> Optional[tuple[Any, Any]]:
            async with contrib_sem:
                try:
                    contrib = await asyncio.to_thread(client.issue.get, logged_id)
                except Exception:
                    return None
            if getattr(contrib, "id", None) != logged_id:
                return None
            if not in_scope(contrib):
                return None
            return logged_id, contrib

        contrib_ids = sorted(
            {
                iid
                for (iid, _spent_iso) in hours_by_issue_day
                if iid is not None and iid not in assigned_ids
            },
            key=lambda v: str(v),
        )
        # gather preserves input order, so insertion order matches the
        # old sequential loop exactly.
        for fetched in await asyncio.gather(
            *(_fetch_contrib(logged_id) for logged_id in contrib_ids)
        ):
            if fetched is not None:
                contrib_issues[fetched[0]] = fetched[1]

        def _contrib_role(issue: Any) -> str:
            if _is_completed(issue, closed_ids):
                return "supported"
            return "supporting"

        # Contradictory status/done_ratio records (e.g. New at 100%,
        # Done below 100%) that need cleanup in the Redmine UI.
        seen_flagged: set = set()
        data_quality_flags: List[Dict[str, Any]] = []
        for issue in (
            touched + backlog + backlog_completed + list(contrib_issues.values())
        ):
            issue_id = getattr(issue, "id", None)
            if issue_id in seen_flagged:
                continue
            seen_flagged.add(issue_id)
            reason = _quality_flag(issue, closed_ids)
            if reason is not None:
                data_quality_flags.append(
                    {
                        "issue": _issue_brief_json_safe(
                            _issue_brief(issue, base_url, 0.0)
                        ),
                        "reason": reason,
                    }
                )

        # Widget data v4: per-day time-log entries, ready to embed verbatim
        # into the oversight widget. Keys ALWAYS cover Mon-Sun (7 Vietnamese
        # labels) for both day and week windows — days outside a day window
        # stay empty. Completed tasks appear with completed=true on exactly
        # one day (their updated_on day, hours = logged that day only, 0.0
        # when nothing was logged that day). Every other logged day of any
        # task appears as completed=false (in-progress row). Tasks this user
        # helped with but is not assigned to appear the same way with
        # role="supporting" (open) or "supported" (closed) and
        # completed=false, so charts and completion counts (which only
        # count completed=true) are unaffected. Each entry
        # also carries "total" (this user's lifetime hours on the issue,
        # all weeks) so the widget computes overrun as total - est instead
        # of the window slice. Entries whose issue is unknown (e.g.
        # project-level logs, reassigned issues) stay in totals but cannot
        # be placed on a named task row.
        widget_data: Dict[str, List[Dict[str, Any]]] = {
            name: [] for name in _VI_DAY_NAMES
        }

        def _widget_entry(
            issue: Any, day_hours: float, is_completed: bool, role: str = "owner"
        ) -> Dict[str, Any]:
            project = getattr(issue, "project", None)
            issue_id = getattr(issue, "id", None)
            lifetime, _prior = _lifetime_split(
                issue_id, actual_by_issue, lifetime_by_issue
            )
            return {
                "id": issue_id,
                "name": getattr(issue, "subject", ""),
                "project": (
                    getattr(project, "name", "") if project is not None else ""
                ),
                "est": _round2(getattr(issue, "estimated_hours", None)),
                "hours": _round2(day_hours),
                "total": lifetime,
                "url": (
                    f"{base_url}/issues/{issue_id}" if base_url and issue_id else None
                ),
                "completed": is_completed,
                "role": role,
            }

        emitted_days: set = set()
        for issue in completed:
            updated_day = _as_date(getattr(issue, "updated_on", None))
            if updated_day is None or updated_day < start or updated_day > end:
                continue
            if not in_scope(issue):
                continue
            issue_id = getattr(issue, "id", None)
            day_hours = hours_by_issue_day.get((issue_id, updated_day.isoformat()), 0.0)
            widget_data[_VI_DAY_NAMES[updated_day.weekday()]].append(
                _widget_entry(issue, day_hours, True)
            )
            emitted_days.add((issue_id, updated_day.isoformat()))

        known_issues: Dict[Any, Any] = {}
        for issue in touched + backlog:
            issue_id = getattr(issue, "id", None)
            if issue_id is not None and issue_id not in known_issues:
                known_issues[issue_id] = issue

        for (issue_id, spent_iso), day_hours in sorted(
            hours_by_issue_day.items(), key=lambda kv: (str(kv[0][0]), kv[0][1])
        ):
            if (issue_id, spent_iso) in emitted_days:
                continue
            issue = known_issues.get(issue_id)
            role = "owner"
            if issue is None:
                issue = contrib_issues.get(issue_id)
                if issue is None or not in_scope(issue):
                    continue
                role = _contrib_role(issue)
            elif not in_scope(issue):
                continue
            spent_day = date.fromisoformat(spent_iso)
            widget_data[_VI_DAY_NAMES[spent_day.weekday()]].append(
                _widget_entry(issue, day_hours, False, role)
            )

        # Task context for the agent-written weekly note: issues completed
        # in the window plus in-progress issues with hours logged in the
        # window. Untouched backlog is excluded. Always returned, even
        # when compact is True, so the skill can summarize what the
        # person actually worked on with grounded descriptions.
        # week_hours is window-only; lifetime_hours/prior_hours cover all
        # weeks so overrun is judged on lifetime, not the window slice.
        task_context: List[Dict[str, Any]] = []
        context_seen_ids: set = set()
        for issue in completed:
            issue_id = getattr(issue, "id", None)
            if issue_id is None or issue_id in context_seen_ids:
                continue
            context_seen_ids.add(issue_id)
            lifetime, prior = _lifetime_split(
                issue_id, actual_by_issue, lifetime_by_issue
            )
            task_context.append(
                _task_context_entry(
                    issue,
                    base_url,
                    actual_by_issue.get(issue_id, 0.0),
                    True,
                    lifetime,
                    prior,
                )
            )
        for issue_id, _spent_iso in sorted(
            hours_by_issue_day, key=lambda k: (str(k[0]), k[1])
        ):
            if issue_id in context_seen_ids:
                continue
            context_seen_ids.add(issue_id)
            issue = known_issues.get(issue_id)
            role = "owner"
            if issue is None:
                issue = contrib_issues.get(issue_id)
                if issue is None or not in_scope(issue):
                    continue
                role = _contrib_role(issue)
            elif not in_scope(issue):
                continue
            if role == "owner" and _is_completed(issue, closed_ids):
                continue
            lifetime, prior = _lifetime_split(
                issue_id, actual_by_issue, lifetime_by_issue
            )
            task_context.append(
                _task_context_entry(
                    issue,
                    base_url,
                    actual_by_issue.get(issue_id, 0.0),
                    False,
                    lifetime,
                    prior,
                    role,
                )
            )

        # Group everything by project for the agent-rendered UI.
        project_names: Dict[Any, str] = {}
        for issue in touched + backlog + backlog_completed:
            project = getattr(issue, "project", None)
            if project is not None and project.id not in project_names:
                project_names[project.id] = getattr(
                    project, "name", f"project #{project.id}"
                )

        def briefs(issues: List[Any]) -> List[Dict[str, Any]]:
            return [
                _issue_brief_json_safe(
                    _issue_brief(
                        i, base_url, actual_by_issue.get(getattr(i, "id", None), 0.0)
                    )
                )
                for i in issues
            ]

        per_project: List[Dict[str, Any]] = []
        touched_by_project: Dict[Any, List[Any]] = {}
        for issue in touched:
            project = getattr(issue, "project", None)
            if project is not None:
                touched_by_project.setdefault(project.id, []).append(issue)
        backlog_by_project: Dict[Any, List[Any]] = {}
        for issue in backlog:
            project = getattr(issue, "project", None)
            if project is not None:
                backlog_by_project.setdefault(project.id, []).append(issue)
        completed_by_project: Dict[Any, List[Any]] = {}
        for issue in backlog_completed:
            project = getattr(issue, "project", None)
            if project is not None:
                completed_by_project.setdefault(project.id, []).append(issue)

        # Id sets for O(1) membership below (the old `i in overdue`
        # list checks were O(n) each, i.e. O(B^2) over the backlog).
        overdue_ids = {getattr(i, "id", None) for i in overdue}
        no_due_ids = {getattr(i, "id", None) for i in no_due_date}

        for pid in sorted(
            set(touched_by_project)
            | set(backlog_by_project)
            | set(completed_by_project),
            key=lambda k: str(project_names.get(k, k)),
        ):
            proj_touched = touched_by_project.get(pid, [])
            proj_closed = [
                i
                for i in proj_touched
                if getattr(getattr(i, "status", None), "id", None) in closed_ids
            ]
            proj_backlog = backlog_by_project.get(pid, [])
            proj_overdue = [
                i for i in proj_backlog if getattr(i, "id", None) in overdue_ids
            ]
            proj_no_due = [
                i for i in proj_backlog if getattr(i, "id", None) in no_due_ids
            ]
            per_project.append(
                {
                    "project": {
                        "id": pid,
                        "name": project_names.get(pid, f"project #{pid}"),
                    },
                    "activity": {
                        "hours": round(hours_by_project.get(pid, 0.0), 2),
                        "touched": briefs(proj_touched),
                        "touched_count": len(proj_touched),
                        "closed": briefs(proj_closed),
                        "closed_count": len(proj_closed),
                    },
                    "backlog": {
                        "open_count": len(proj_backlog),
                        "completed_count": len(completed_by_project.get(pid, [])),
                        "overdue": briefs(
                            sorted(
                                proj_overdue,
                                key=lambda i: _as_date(getattr(i, "due_date", None))
                                or date.max,
                            )
                        ),
                        "overdue_count": len(proj_overdue),
                        "no_due_date": briefs(proj_no_due),
                        "no_due_date_count": len(proj_no_due),
                        "in_progress": briefs(
                            [
                                i
                                for i in proj_backlog
                                if i not in proj_overdue and i not in proj_no_due
                            ]
                        ),
                    },
                }
            )

        totals = {
            "hours": round(hours_total, 2),
            "time_entries": len(time_entries),
            "touched_count": len(touched),
            "closed_count": len(closed_in_window),
            "completed_count": len(completed),
            "completed_total": len(backlog_completed),
            "open_count": len(backlog),
            "overdue_count": len(overdue),
            "no_due_date_count": len(no_due_date),
        }
        result: Dict[str, Any] = {
            "person": resolved,
            "window": {
                "type": window,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
            "widget_data": widget_data,
            "totals": totals,
            "data_quality_flags": data_quality_flags,
            "task_context": task_context,
            "evidence": {
                "queried_at": datetime.now(timezone.utc).isoformat(),
                "person_query": person,
                "filters_used": {
                    "assigned_to_id": uid,
                    "updated_on": f">={start.isoformat()} (cut at {end})",
                    "time_entries": (
                        f"user_id={uid}, " f"{start.isoformat()}..{end.isoformat()}"
                    ),
                    "project_scope": (
                        "all accessible" if scope is None else sorted(scope)
                    ),
                },
                "hours_scope": {
                    "scope": "window_only",
                    "user_id": uid,
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "note": (
                        "actual_hours (per issue) and totals.hours count ONLY"
                        " time logged by this user inside the window above."
                        " 0.0 means 'no hours logged in this window', NEVER"
                        " 'this task never had hours'. / actual_hours và"
                        " totals.hours CHỈ tính giờ của đúng user này log"
                        " TRONG tuần trên. 0.0 = 'tuần này chưa log', KHÔNG"
                        " phải 'task chưa từng được log giờ'."
                    ),
                },
                "totals": totals,
            },
        }
        if not compact:
            result["per_project"] = per_project
        return result
    except Exception as e:
        return handle_error(e, "summarizing person workload", None)
