"""Undecorated workflow/status tool implementations extracted from redmine_handler."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Union

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

_DEFAULT_WORKFLOW_SAMPLE_LIMIT = 25
_MAX_WORKFLOW_SAMPLE_LIMIT = 100
_WORKFLOW_FETCH_CONCURRENCY = 10


def _status_to_dict(status: Any, wrap_content: Callable[[Any], Any]) -> Dict[str, Any]:
    """Serialize an issue status object into a JSON-safe dictionary."""
    return {
        "id": getattr(status, "id", None),
        "name": wrap_content(getattr(status, "name", "")),
        "is_closed": bool(getattr(status, "is_closed", False)),
    }


async def list_redmine_issue_statuses_impl(
    *,
    get_client: Callable[[], Any],
    wrap_content: Callable[[Any], Any],
    handle_error: HandleErrorFn,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List all issue statuses defined in Redmine."""
    try:
        statuses = get_client().issue_status.all()
        return [_status_to_dict(status, wrap_content) for status in statuses]
    except Exception as e:
        return handle_error(e, "listing issue statuses", None)


async def get_redmine_issue_allowed_statuses_impl(
    issue_id: int,
    *,
    get_client: Callable[[], Any],
    wrap_content: Callable[[Any], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Get workflow-allowed next statuses for a specific issue."""
    try:
        issue = get_client().issue.get(issue_id, include="allowed_statuses")
        current_status = getattr(issue, "status", None)
        raw_allowed = getattr(issue, "allowed_statuses", None) or []

        allowed_statuses = [
            _status_to_dict(status, wrap_content) for status in raw_allowed
        ]
        return {
            "issue_id": issue_id,
            "current_status": (
                {
                    "id": getattr(current_status, "id", None),
                    "name": wrap_content(getattr(current_status, "name", "")),
                }
                if current_status is not None
                else None
            ),
            "allowed_statuses": allowed_statuses,
            "count": len(allowed_statuses),
            "source": "issue.allowed_statuses",
            "note": (
                "Allowed statuses depend on Redmine workflow, current user role, "
                "and issue constraints."
            ),
        }
    except Exception as e:
        return handle_error(
            e,
            f"fetching allowed statuses for issue {issue_id}",
            {"resource_type": "issue", "resource_id": issue_id},
        )


def _normalize_sample_limit(sample_limit: int) -> int:
    """Normalize project workflow sample size."""
    try:
        parsed = int(sample_limit)
    except (TypeError, ValueError):
        return _DEFAULT_WORKFLOW_SAMPLE_LIMIT
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_WORKFLOW_SAMPLE_LIMIT)


async def get_redmine_project_workflow_impl(
    project_id: Union[str, int],
    tracker_id: Optional[int] = None,
    status_id: Optional[Union[int, str]] = None,
    sample_limit: int = _DEFAULT_WORKFLOW_SAMPLE_LIMIT,
    *,
    get_client: Callable[[], Any],
    wrap_content: Callable[[Any], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Approximate project workflow from issue-level allowed statuses."""
    try:
        limit = _normalize_sample_limit(sample_limit)

        filters: Dict[str, Any] = {
            "project_id": project_id,
            "limit": limit,
            "offset": 0,
            "status_id": status_id if status_id is not None else "*",
        }
        if tracker_id is not None:
            filters["tracker_id"] = tracker_id

        client = get_client()
        issues = await asyncio.to_thread(lambda: list(client.issue.filter(**filters)))

        semaphore = asyncio.Semaphore(_WORKFLOW_FETCH_CONCURRENCY)

        async def _fetch_detailed_issue(issue_id: int) -> Any:
            async with semaphore:
                return await asyncio.to_thread(
                    client.issue.get,
                    issue_id,
                    include="allowed_statuses",
                )

        issue_ids = [
            issue_id
            for issue in issues
            for issue_id in [getattr(issue, "id", None)]
            if issue_id is not None
        ]
        detailed_issues = await asyncio.gather(
            *(_fetch_detailed_issue(issue_id) for issue_id in issue_ids)
        )

        matrix: Dict[Any, Dict[str, Any]] = {}
        for detailed in detailed_issues:
            current_status = getattr(detailed, "status", None)
            if current_status is None:
                continue

            current_status_id = getattr(current_status, "id", None)
            key = current_status_id if current_status_id is not None else "unknown"
            entry = matrix.setdefault(
                key,
                {
                    "current_status": {
                        "id": current_status_id,
                        "name": wrap_content(getattr(current_status, "name", "")),
                    },
                    "allowed_statuses": {},
                    "issue_count": 0,
                },
            )

            entry["issue_count"] += 1
            for allowed in getattr(detailed, "allowed_statuses", None) or []:
                allowed_id = getattr(allowed, "id", None)
                entry["allowed_statuses"][allowed_id] = {
                    "id": allowed_id,
                    "name": wrap_content(getattr(allowed, "name", "")),
                    "is_closed": bool(getattr(allowed, "is_closed", False)),
                }

        workflow_by_status: List[Dict[str, Any]] = []
        for entry in matrix.values():
            allowed = list(entry["allowed_statuses"].values())
            allowed.sort(
                key=lambda item: (
                    item["id"] is None,
                    item["id"] if item["id"] is not None else 0,
                )
            )
            workflow_by_status.append(
                {
                    "current_status": entry["current_status"],
                    "allowed_statuses": allowed,
                    "issue_count": entry["issue_count"],
                }
            )

        workflow_by_status.sort(
            key=lambda item: (
                item["current_status"]["id"] is None,
                (
                    item["current_status"]["id"]
                    if item["current_status"]["id"] is not None
                    else 0
                ),
            )
        )

        return {
            "project_id": project_id,
            "tracker_id": tracker_id,
            "status_id_filter": status_id if status_id is not None else "*",
            "sample_limit": limit,
            "sampled_issues": len(issues),
            "workflow_by_current_status": workflow_by_status,
            "note": (
                "Workflow is inferred from sampled issues via issue.allowed_statuses "
                "for the current authenticated user; it may vary across roles and "
                "issue constraints. This endpoint performs one follow-up request per "
                "sampled issue."
            ),
            "request_pattern": {
                "list_request_count": 1,
                "detail_request_count": len(issue_ids),
                "total_request_count": len(issue_ids) + 1,
                "detail_fetch_concurrency": _WORKFLOW_FETCH_CONCURRENCY,
            },
        }
    except Exception as e:
        return handle_error(
            e,
            f"fetching workflow snapshot for project {project_id}",
            {"resource_type": "project", "resource_id": project_id},
        )
