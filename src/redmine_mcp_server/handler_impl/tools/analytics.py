"""Undecorated analytics tool implementations extracted from redmine_handler."""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

_DEFAULT_SCRUM_REPORT_MAX_DAYS = 31
_MAX_SCRUM_REPORT_MAX_DAYS = 365
_DEFAULT_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY = 5
_MAX_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY = 20


def _resolve_scrum_report_max_days() -> int:
    """Resolve max custom report range from env with safe bounds."""
    raw = os.getenv(
        "REDMINE_SCRUM_REPORT_MAX_DAYS",
        str(_DEFAULT_SCRUM_REPORT_MAX_DAYS),
    ).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_SCRUM_REPORT_MAX_DAYS
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_SCRUM_REPORT_MAX_DAYS)


def _resolve_scrum_issue_fetch_concurrency() -> int:
    """Resolve max concurrent issue detail fetches for scrum report enrichment."""
    raw = os.getenv(
        "REDMINE_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY",
        str(_DEFAULT_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY),
    ).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY)


def _resolve_scrum_report_range(
    *,
    report_type: str,
    from_date: Optional[str],
    to_date: Optional[str],
    reference_date: Optional[date] = None,
    max_days: Optional[int] = None,
) -> Union[Dict[str, str], Dict[str, Any]]:
    """Resolve daily/weekly/custom date windows for scrum report generation."""
    today = reference_date or date.today()
    normalized_type = (report_type or "").strip().lower()
    max_window_days = max_days or _resolve_scrum_report_max_days()

    if normalized_type == "daily":
        yesterday = today - timedelta(days=1)
        return {
            "report_type": "daily",
            "from_date": yesterday.isoformat(),
            "to_date": yesterday.isoformat(),
            "label": "yesterday",
        }

    if normalized_type == "weekly":
        start_of_current_week = today - timedelta(days=today.weekday())
        start_of_last_week = start_of_current_week - timedelta(days=7)
        end_of_last_week = start_of_current_week - timedelta(days=1)
        return {
            "report_type": "weekly",
            "from_date": start_of_last_week.isoformat(),
            "to_date": end_of_last_week.isoformat(),
            "label": "last_week",
        }

    if normalized_type == "custom":
        if not from_date or not to_date:
            return {
                "error": (
                    "from_date and to_date are required when report_type='custom'."
                )
            }
        try:
            parsed_from = date.fromisoformat(from_date)
            parsed_to = date.fromisoformat(to_date)
        except ValueError:
            return {"error": "from_date and to_date must use YYYY-MM-DD format."}
        if parsed_from > parsed_to:
            return {"error": "from_date must be less than or equal to to_date."}
        window_days = (parsed_to - parsed_from).days + 1
        if window_days > max_window_days:
            return {
                "error": (
                    f"Custom report range too large ({window_days} days). "
                    f"Maximum supported is {max_window_days} days."
                )
            }
        return {
            "report_type": "custom",
            "from_date": parsed_from.isoformat(),
            "to_date": parsed_to.isoformat(),
            "label": "custom",
        }

    return {"error": "Invalid report_type. Supported values: daily, weekly, custom."}


def _iso_date(value: Any) -> Optional[str]:
    """Convert date-like values to YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text


def _extract_description_excerpt(value: Any, max_len: int = 180) -> str:
    """Build a compact single-line description excerpt."""
    text = str(value or "").strip()
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return f"{collapsed[: max_len - 1].rstrip()}…"


def _safe_name(value: Any, default: str) -> str:
    """Normalize optional nested names to safe display text."""
    text = str(value or "").strip()
    return text or default


async def _fetch_issue_details_map(
    *,
    client: Any,
    issue_ids: List[int],
    max_concurrency: int = 5,
) -> Dict[int, Any]:
    """Fetch issue details concurrently without blocking the event loop."""
    if not issue_ids:
        return {}

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _fetch_one(issue_id: int) -> tuple[int, Any]:
        async with semaphore:
            try:
                issue = await asyncio.to_thread(client.issue.get, issue_id)
            except Exception:
                issue = None
            return issue_id, issue

    results = await asyncio.gather(*[_fetch_one(issue_id) for issue_id in issue_ids])
    return {issue_id: issue for issue_id, issue in results}


async def generate_scrum_report_impl(
    report_type: str = "daily",
    user_id: Optional[Union[str, int]] = None,
    project_id: Optional[Union[str, int]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    top_n_items: int = 7,
    include_entries: bool = False,
    *,
    get_client: Callable[[], Any],
    time_entry_to_dict: Callable[[Any], Dict[str, Any]],
    wrap_content: Callable[[Any], str],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Generate an auto-draft scrum report from Redmine time entries."""
    try:
        resolved_range = _resolve_scrum_report_range(
            report_type=report_type,
            from_date=from_date,
            to_date=to_date,
        )
        if "error" in resolved_range:
            return resolved_range

        filters: Dict[str, Any] = {
            "from_date": resolved_range["from_date"],
            "to_date": resolved_range["to_date"],
        }
        if user_id is not None:
            filters["user_id"] = user_id
        if project_id is not None:
            filters["project_id"] = project_id

        client = get_client()
        time_entries = await asyncio.to_thread(
            lambda: list(client.time_entry.filter(**filters))
        )
        total_hours = 0.0
        by_issue: Dict[str, Dict[str, Any]] = {}
        by_activity: Dict[str, Dict[str, Any]] = {}
        by_day: Dict[str, Dict[str, Any]] = {}
        by_user: Dict[str, Dict[str, Any]] = {}
        unique_users = set()

        for entry in time_entries:
            hours = float(getattr(entry, "hours", 0) or 0)
            total_hours += hours

            spent_on_key = _iso_date(getattr(entry, "spent_on", None)) or "unknown"
            day_bucket = by_day.setdefault(
                spent_on_key, {"date": spent_on_key, "hours": 0.0, "entries": 0}
            )
            day_bucket["hours"] += hours
            day_bucket["entries"] += 1

            entry_user = getattr(entry, "user", None)
            user_id_value = getattr(entry_user, "id", None) if entry_user else None
            user_name = getattr(entry_user, "name", "") if entry_user else ""
            if user_name:
                unique_users.add(str(user_name))
            user_key = (
                str(user_id_value)
                if user_id_value is not None
                else str(user_name or "unknown")
            )
            user_bucket = by_user.setdefault(
                user_key,
                {
                    "user_id": user_id_value,
                    "user_name": wrap_content(user_name or "Unknown"),
                    "hours": 0.0,
                    "entries": 0,
                },
            )
            user_bucket["hours"] += hours
            user_bucket["entries"] += 1

            issue = getattr(entry, "issue", None)
            issue_id = getattr(issue, "id", None) if issue else None
            issue_name_raw = (
                getattr(issue, "name", None) or getattr(issue, "subject", None)
                if issue
                else None
            )
            project_obj = getattr(entry, "project", None)
            issue_key = str(issue_id) if issue_id is not None else "no_issue"
            issue_bucket = by_issue.setdefault(
                issue_key,
                {
                    "issue_id": issue_id,
                    "issue_subject_raw": issue_name_raw or "No linked issue",
                    "project_name_raw": getattr(project_obj, "name", None)
                    or "Unknown project",
                    "status_raw": "Unknown",
                    "priority_raw": "Unknown",
                    "assignee_raw": "Unassigned",
                    "updated_on": None,
                    "description_excerpt_raw": "",
                    "hours": 0.0,
                    "entries": 0,
                },
            )
            issue_bucket["hours"] += hours
            issue_bucket["entries"] += 1

            activity = getattr(entry, "activity", None)
            activity_id = getattr(activity, "id", None) if activity else None
            activity_name = wrap_content(
                _safe_name(
                    getattr(activity, "name", None) if activity else None,
                    "Unspecified",
                )
            )
            activity_key = str(activity_id) if activity_id is not None else "unknown"
            activity_bucket = by_activity.setdefault(
                activity_key,
                {
                    "activity_id": activity_id,
                    "activity_name": activity_name,
                    "hours": 0.0,
                    "entries": 0,
                },
            )
            activity_bucket["hours"] += hours
            activity_bucket["entries"] += 1

        sorted_issues = sorted(
            by_issue.values(),
            key=lambda item: (item["hours"], item["entries"]),
            reverse=True,
        )
        sorted_activities = sorted(
            by_activity.values(),
            key=lambda item: (item["hours"], item["entries"]),
            reverse=True,
        )
        sorted_users = sorted(
            by_user.values(),
            key=lambda item: (item["hours"], item["entries"]),
            reverse=True,
        )

        top_limit = max(1, min(top_n_items, 20))
        top_issues = sorted_issues[:top_limit]
        top_issue_ids = [
            int(issue_item["issue_id"])
            for issue_item in top_issues
            if issue_item.get("issue_id") is not None
        ]
        issue_details_by_id = await _fetch_issue_details_map(
            client=client,
            issue_ids=top_issue_ids,
            max_concurrency=_resolve_scrum_issue_fetch_concurrency(),
        )

        for issue_item in top_issues:
            issue_id = issue_item.get("issue_id")
            if issue_id is None:
                continue
            issue_data = issue_details_by_id.get(int(issue_id))
            if issue_data is None:
                continue
            issue_item["issue_subject_raw"] = (
                getattr(issue_data, "subject", None)
                or getattr(issue_data, "name", None)
                or issue_item.get("issue_subject_raw")
            )
            issue_item["project_name_raw"] = _safe_name(
                getattr(getattr(issue_data, "project", None), "name", None),
                issue_item.get("project_name_raw", "Unknown project"),
            )
            issue_item["status_raw"] = _safe_name(
                getattr(getattr(issue_data, "status", None), "name", None),
                "Unknown",
            )
            issue_item["priority_raw"] = _safe_name(
                getattr(getattr(issue_data, "priority", None), "name", None),
                "Unknown",
            )
            issue_item["assignee_raw"] = _safe_name(
                getattr(getattr(issue_data, "assigned_to", None), "name", None),
                "Unassigned",
            )
            issue_item["updated_on"] = _iso_date(
                getattr(issue_data, "updated_on", None)
            )
            issue_item["description_excerpt_raw"] = _extract_description_excerpt(
                getattr(issue_data, "description", None)
            )

        for issue_item in top_issues:
            issue_id_text = (
                f"#{issue_item['issue_id']}"
                if issue_item.get("issue_id") is not None
                else "#N/A"
            )
            issue_item["issue_subject"] = wrap_content(
                issue_item.get("issue_subject_raw", "No linked issue")
            )
            issue_item["project_name"] = wrap_content(
                issue_item.get("project_name_raw", "Unknown project")
            )
            issue_item["status"] = wrap_content(issue_item.get("status_raw", "Unknown"))
            issue_item["priority"] = wrap_content(
                issue_item.get("priority_raw", "Unknown")
            )
            issue_item["assignee"] = wrap_content(
                issue_item.get("assignee_raw", "Unassigned")
            )
            issue_item["updated_on"] = issue_item.get("updated_on") or "unknown"
            issue_item["description_excerpt"] = wrap_content(
                issue_item.get("description_excerpt_raw", "")
            )
            issue_item["summary_line"] = (
                f"- {issue_id_text} "
                f"[{issue_item['status']}][{issue_item['priority']}] "
                f"{issue_item['issue_subject']} | assignee: {issue_item['assignee']} | "
                f"{round(issue_item['hours'], 2)}h | "
                f"project: {issue_item['project_name']} | "
                f"updated: {issue_item['updated_on']}"
            )
            issue_item["description_line"] = (
                f"  desc: {issue_item['description_excerpt']}"
                if issue_item["description_excerpt"].strip()
                else "  desc: (no description)"
            )
        sorted_days = [
            {
                **bucket,
                "hours": round(bucket["hours"], 2),
            }
            for _, bucket in sorted(by_day.items(), key=lambda item: item[0])
        ]

        summary_lines = [
            item["summary_line"] for item in top_issues if item.get("summary_line")
        ]
        highlights = [
            f"{item['summary_line']}\n{item['description_line']}" for item in top_issues
        ]

        report_title = (
            "Daily Scrum Report Draft"
            if resolved_range["report_type"] == "daily"
            else (
                "Weekly Scrum Report Draft"
                if resolved_range["report_type"] == "weekly"
                else "Custom Scrum Report Draft"
            )
        )
        report_draft = "\n".join(
            [
                f"### {report_title}",
                (
                    f"- Range: {resolved_range['from_date']} to "
                    f"{resolved_range['to_date']}"
                ),
                f"- Total time logged: {round(total_hours, 2)}h",
                f"- Total entries: {len(time_entries)}",
                "",
                "#### Completed work highlights",
                *(highlights or ["- No tracked work in selected range."]),
                "",
                "#### Suggested talking points",
                "- Yesterday/Last week: summarize completed items above.",
                "- Today/Next week: list planned follow-ups from top items.",
                "- Blockers: mention blocked tasks or dependency issues.",
            ]
        )
        range_line = f"{resolved_range['from_date']} to {resolved_range['to_date']}"
        top_issue_lines = highlights or ["- No major completed item recorded."]
        next_focus_line = (
            summary_lines[0].replace("- ", "- Continue/close: ", 1)
            if summary_lines
            else "- Continue/close: No priority item selected yet."
        )

        template_standup_three_questions = "\n".join(
            [
                "### Daily Standup Template (3 Questions)",
                f"- Range reviewed: {range_line}",
                "",
                "1) What I completed in the last period",
                *top_issue_lines,
                "",
                "2) What I will work on next",
                next_focus_line,
                "",
                "3) Blockers / dependencies",
                "- [ ] None",
                "- [ ] Need support from: <team/person>",
            ]
        )

        template_workflow_focused = "\n".join(
            [
                "### Daily Standup Template (Workflow Focused)",
                f"- Range reviewed: {range_line}",
                "",
                "Done since last update:",
                *top_issue_lines,
                "",
                "In progress now:",
                "- <issue/task> (owner: <name>)",
                "",
                "Blocked:",
                "- <issue/task> (blocker: <reason>)",
                "",
                "Next 24h commit:",
                next_focus_line,
            ]
        )

        template_weekly_status = "\n".join(
            [
                "### Weekly Status Template (Accomplishments / Risks / Next)",
                f"- Reporting window: {range_line}",
                f"- Total hours logged: {round(total_hours, 2)}h",
                f"- Total entries: {len(time_entries)}",
                "",
                "Top accomplishments:",
                *top_issue_lines,
                "",
                "Risks / blockers:",
                "- <risk or blocker> | owner: <name> | mitigation: <action>",
                "",
                "Next-week priorities:",
                next_focus_line,
                "- <priority 2>",
                "- <priority 3>",
            ]
        )

        payload: Dict[str, Any] = {
            "report_type": resolved_range["report_type"],
            "analysis_range": {
                "label": resolved_range["label"],
                "from_date": resolved_range["from_date"],
                "to_date": resolved_range["to_date"],
            },
            "filters": {
                "user_id": user_id,
                "project_id": project_id,
            },
            "summary": {
                "total_hours": round(total_hours, 2),
                "total_entries": len(time_entries),
                "unique_user_count": len(unique_users),
            },
            "top_issues": [
                {
                    **item,
                    "hours": round(item["hours"], 2),
                }
                for item in top_issues
            ],
            "top_activities": [
                {
                    **item,
                    "hours": round(item["hours"], 2),
                }
                for item in sorted_activities[:top_limit]
            ],
            "top_users": [
                {
                    **item,
                    "hours": round(item["hours"], 2),
                }
                for item in sorted_users[:top_limit]
            ],
            "by_day": sorted_days,
            "report_draft": report_draft,
            "report_templates": {
                "standup_three_questions": template_standup_three_questions,
                "standup_workflow_focused": template_workflow_focused,
                "weekly_status_summary": template_weekly_status,
            },
        }

        if include_entries:
            payload["entries"] = [time_entry_to_dict(entry) for entry in time_entries]

        return payload
    except Exception as e:
        return handle_error(e, "generating scrum report", None)


async def summarize_project_status_impl(
    project_id: int,
    days: int = 30,
    *,
    get_client: Callable[[], Any],
    analyze_issues: Callable[[List[Any]], Dict[str, Any]],
    handle_error: HandleErrorFn,
    resource_not_found_error: Type[Exception],
) -> Dict[str, Any]:
    """Provide summary statistics for project activity over a date window."""
    try:
        try:
            project = get_client().project.get(project_id)
        except resource_not_found_error:
            return {"error": f"Project {project_id} not found."}

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        date_filter = f">={start_date.strftime('%Y-%m-%d')}"

        client = get_client()
        created_issues = await asyncio.to_thread(
            lambda: list(
                client.issue.filter(project_id=project_id, created_on=date_filter)
            )
        )
        updated_issues = await asyncio.to_thread(
            lambda: list(
                client.issue.filter(project_id=project_id, updated_on=date_filter)
            )
        )

        created_stats = analyze_issues(created_issues)
        updated_stats = analyze_issues(updated_issues)

        total_created = len(created_issues)
        total_updated = len(updated_issues)

        all_issues = await asyncio.to_thread(
            lambda: list(client.issue.filter(project_id=project_id))
        )
        all_stats = analyze_issues(all_issues)

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "identifier": getattr(project, "identifier", ""),
            },
            "analysis_period": {
                "days": days,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
            },
            "recent_activity": {
                "issues_created": total_created,
                "issues_updated": total_updated,
                "created_breakdown": created_stats,
                "updated_breakdown": updated_stats,
            },
            "project_totals": {
                "total_issues": len(all_issues),
                "overall_breakdown": all_stats,
            },
            "insights": {
                "daily_creation_rate": round(total_created / days, 2),
                "daily_update_rate": round(total_updated / days, 2),
                "recent_activity_percentage": round(
                    (total_updated / len(all_issues) * 100) if all_issues else 0,
                    2,
                ),
            },
        }
    except Exception as e:
        return handle_error(
            e,
            f"summarizing project {project_id}",
            {"resource_type": "project", "resource_id": project_id},
        )


async def search_entire_redmine_impl(
    query: str,
    resources: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    resource_to_dict: Callable[[Any, str], Dict[str, Any]],
    handle_error: HandleErrorFn,
    version_mismatch_error: Type[Exception],
) -> Dict[str, Any]:
    """Search issues and wiki pages across the Redmine instance."""
    try:
        await ensure_cleanup_started()

        allowed_types = ["issues", "wiki_pages"]
        if resources:
            resources = [
                resource for resource in resources if resource in allowed_types
            ]
            if not resources:
                resources = allowed_types
        else:
            resources = allowed_types

        limit = min(limit, 100)
        if limit <= 0:
            limit = 100

        search_options = {
            "resources": resources,
            "limit": limit,
            "offset": offset,
        }
        categorized_results = await asyncio.to_thread(
            get_client().search, query, **search_options
        )

        if not categorized_results:
            return {
                "results": [],
                "results_by_type": {},
                "total_count": 0,
                "query": query,
            }

        all_results = []
        results_by_type: Dict[str, int] = {}
        for resource_type, resource_set in categorized_results.items():
            if resource_type == "unknown":
                continue
            if resource_type not in allowed_types:
                continue

            if hasattr(resource_set, "__iter__"):
                count = 0
                for resource in resource_set:
                    all_results.append(resource_to_dict(resource, resource_type))
                    count += 1
                if count > 0:
                    results_by_type[resource_type] = count

        return {
            "results": all_results,
            "results_by_type": results_by_type,
            "total_count": len(all_results),
            "query": query,
        }
    except version_mismatch_error:
        return {"error": "Search requires Redmine 3.3.0 or higher."}
    except Exception as e:
        return handle_error(e, f"searching Redmine for '{query}'", None)
