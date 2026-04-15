"""Undecorated analytics tool implementations extracted from redmine_handler."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


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

        created_issues = list(
            get_client().issue.filter(project_id=project_id, created_on=date_filter)
        )
        updated_issues = list(
            get_client().issue.filter(project_id=project_id, updated_on=date_filter)
        )

        created_stats = analyze_issues(created_issues)
        updated_stats = analyze_issues(updated_issues)

        total_created = len(created_issues)
        total_updated = len(updated_issues)

        all_issues = list(get_client().issue.filter(project_id=project_id))
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
        categorized_results = get_client().search(query, **search_options)

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
