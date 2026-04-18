"""Workflow contract resource helpers."""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

from ._utils import parse_tracker_id

_DEFAULT_WORKFLOW_CONTRACT_SAMPLE_LIMIT = 25
_MAX_WORKFLOW_CONTRACT_SAMPLE_LIMIT = 100


def resolve_workflow_contract_sample_limit() -> int:
    """Resolve workflow contract sample size from env, clamped to safe bounds."""
    raw = os.getenv(
        "REDMINE_WORKFLOW_CONTRACT_SAMPLE_LIMIT",
        str(_DEFAULT_WORKFLOW_CONTRACT_SAMPLE_LIMIT),
    ).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_WORKFLOW_CONTRACT_SAMPLE_LIMIT
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_WORKFLOW_CONTRACT_SAMPLE_LIMIT)


def build_transition_matrix(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize workflow snapshot data into compact transition maps."""
    transition_rows = workflow_data.get("workflow_by_current_status", [])
    by_from_status_id: Dict[str, Any] = {}
    by_from_status_name: Dict[str, Any] = {}

    for row in transition_rows:
        current = row.get("current_status") or {}
        current_id = current.get("id")
        current_name = current.get("name")
        allowed_statuses: List[Dict[str, Any]] = row.get("allowed_statuses", [])

        allowed_ids = [status.get("id") for status in allowed_statuses]
        allowed_names = [status.get("name") for status in allowed_statuses]

        key_id = str(current_id) if current_id is not None else "unknown"
        by_from_status_id[key_id] = {
            "current_status": current,
            "allowed_status_ids": allowed_ids,
            "allowed_status_names": allowed_names,
            "allowed_statuses": allowed_statuses,
        }

        if current_name:
            by_from_status_name[str(current_name)] = allowed_names

    return {
        "by_from_status_id": by_from_status_id,
        "by_from_status_name": by_from_status_name,
    }


async def build_workflow_contract_payload(
    *,
    project_id: Union[str, int],
    tracker_id: Optional[Union[str, int]],
    get_workflow_snapshot: Callable[..., Awaitable[Any]],
    list_statuses: Callable[..., Awaitable[Any]],
    get_client: Callable[..., Any],
    wrap_content: Callable[[Any], str],
    handle_error: Callable[[Exception, str, Optional[Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Build workflow contract payload for project-level or tracker-level resources."""
    try:
        parsed_tracker_id = parse_tracker_id(tracker_id)
    except (TypeError, ValueError):
        return {
            "error": (
                f"Invalid tracker_id '{tracker_id}'. Expected an integer tracker ID."
            )
        }

    sample_limit = resolve_workflow_contract_sample_limit()
    workflow_snapshot = await get_workflow_snapshot(
        project_id,
        tracker_id=parsed_tracker_id,
        status_id=None,
        sample_limit=sample_limit,
        get_client=get_client,
        wrap_content=wrap_content,
        handle_error=handle_error,
    )
    if isinstance(workflow_snapshot, dict) and "error" in workflow_snapshot:
        return workflow_snapshot

    statuses = await list_statuses(
        get_client=get_client,
        wrap_content=wrap_content,
        handle_error=handle_error,
    )
    if isinstance(statuses, dict) and "error" in statuses:
        return statuses

    return {
        "resource": "workflow_contract",
        "project_id": project_id,
        "tracker_id": parsed_tracker_id,
        "statuses": statuses,
        "sample_limit": sample_limit,
        "transition_matrix": build_transition_matrix(workflow_snapshot),
        "workflow_snapshot": workflow_snapshot,
    }
