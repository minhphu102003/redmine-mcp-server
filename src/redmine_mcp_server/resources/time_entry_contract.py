"""Time-entry contract resource payload builder."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

TIME_ENTRY_CONTRACT_RESOURCE_URI = "redmine://time-entry/contract"


async def build_time_entry_contract_payload(
    *,
    get_client: Callable[[], Any],
    handle_error: Callable[[Exception, str, Optional[Dict[str, Any]]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Build time-entry validation contract payload."""
    try:
        activities = get_client().enumeration.filter(resource="time_entry_activities")
        serialized_activities = [
            {
                "id": getattr(activity, "id", None),
                "name": getattr(activity, "name", None),
                "active": getattr(activity, "active", None),
                "is_default": getattr(activity, "is_default", None),
            }
            for activity in activities
        ]
        return {
            "resource": "time_entry_contract",
            "rules": {
                "required_on_create": [
                    "hours",
                    "project_id|issue_id",
                ],
                "hours": {
                    "type": "number",
                    "gt": 0,
                    "description": "Hours must be a positive number.",
                },
                "spent_on": {
                    "format": "YYYY-MM-DD",
                    "optional": True,
                },
                "list_limit_max": 100,
                "list_offset_min": 0,
            },
            "activities": serialized_activities,
            "examples": {
                "create": {
                    "hours": 2.5,
                    "issue_id": 123,
                    "activity_id": (
                        serialized_activities[0]["id"]
                        if serialized_activities
                        else None
                    ),
                    "spent_on": "2026-04-19",
                    "comments": "Implemented issue contract resource",
                },
                "update": {
                    "time_entry_id": 456,
                    "hours": 3.0,
                    "comments": "Adjusted estimate after review",
                },
            },
        }
    except Exception as exc:
        return handle_error(exc, "building time-entry contract", None)
