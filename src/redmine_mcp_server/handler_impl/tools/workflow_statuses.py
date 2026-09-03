"""Undecorated workflow-status tool implementations (leaf).

Kept after the broader workflow-tool removal so the two leaf tools
(list_redmine_issue_statuses, get_redmine_issue_allowed_statuses) can
still be registered without dragging in the heavy project-workflow
inference code that lived in the old workflow.py module.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Union

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


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
        statuses = await asyncio.to_thread(get_client().issue_status.all)
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
        issue = await asyncio.to_thread(
            get_client().issue.get, issue_id, include="allowed_statuses"
        )
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
