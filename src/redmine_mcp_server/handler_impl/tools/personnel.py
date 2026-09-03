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

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

_PAGE_SIZE = 100


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


def _issue_brief(issue: Any, base_url: str) -> Dict[str, Any]:
    """Compact, UI-ready issue summary for grouped performance views."""
    project = getattr(issue, "project", None)
    status = getattr(issue, "status", None)
    updated = getattr(issue, "updated_on", None)
    issue_id = getattr(issue, "id", None)
    url = f"{base_url}/issues/{issue_id}" if base_url and issue_id else None
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
    *,
    get_client: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Summarize one person's performance for a day or Mon-Sun week."""
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

        statuses = await asyncio.to_thread(client.issue_status.all)
        closed_ids = {s.id for s in statuses if bool(getattr(s, "is_closed", False))}

        scope = set(project_ids) if project_ids else None

        def in_scope(issue: Any) -> bool:
            if scope is None:
                return True
            project = getattr(issue, "project", None)
            return project is not None and project.id in scope

        # Activity: time logged in the window.
        time_entries = await _fetch_all_pages(
            client.time_entry.filter,
            user_id=uid,
            from_date=start.isoformat(),
            to_date=end.isoformat(),
        )
        hours_total = 0.0
        hours_by_project: Dict[Any, float] = {}
        for entry in time_entries:
            try:
                hours_total += float(getattr(entry, "hours", 0) or 0)
            except (TypeError, ValueError):
                continue
            project = getattr(entry, "project", None)
            if project is not None and (scope is None or project.id in scope):
                hours_by_project[project.id] = hours_by_project.get(
                    project.id, 0.0
                ) + float(getattr(entry, "hours", 0) or 0)

        # Activity: assigned issues touched in the window (any status).
        touched_raw = await _fetch_all_pages(
            client.issue.filter,
            assigned_to_id=uid,
            status_id="*",
            updated_on=f">={start.isoformat()}",
            sort="updated_on:desc",
        )
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

        # Backlog snapshot: currently open issues assigned to the person.
        backlog_raw = await _fetch_all_pages(
            client.issue.filter,
            assigned_to_id=uid,
            sort="due_date:asc",
        )
        backlog = [issue for issue in backlog_raw if in_scope(issue)]
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

        # Group everything by project for the agent-rendered UI.
        project_names: Dict[Any, str] = {}
        for issue in touched + backlog:
            project = getattr(issue, "project", None)
            if project is not None and project.id not in project_names:
                project_names[project.id] = getattr(
                    project, "name", f"project #{project.id}"
                )

        def briefs(issues: List[Any]) -> List[Dict[str, Any]]:
            return [_issue_brief_json_safe(_issue_brief(i, base_url)) for i in issues]

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

        for pid in sorted(
            set(touched_by_project) | set(backlog_by_project),
            key=lambda k: str(project_names.get(k, k)),
        ):
            proj_touched = touched_by_project.get(pid, [])
            proj_closed = [
                i
                for i in proj_touched
                if getattr(getattr(i, "status", None), "id", None) in closed_ids
            ]
            proj_backlog = backlog_by_project.get(pid, [])
            proj_overdue = [i for i in proj_backlog if i in overdue]
            proj_no_due = [i for i in proj_backlog if i in no_due_date]
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
            "open_count": len(backlog),
            "overdue_count": len(overdue),
            "no_due_date_count": len(no_due_date),
        }
        return {
            "person": resolved,
            "window": {
                "type": window,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
            "per_project": per_project,
            "totals": totals,
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
                "totals": totals,
            },
        }
    except Exception as e:
        return handle_error(e, "summarizing person workload", None)
