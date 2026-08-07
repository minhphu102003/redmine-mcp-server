"""Undecorated time-entry tool implementations extracted from redmine_handler."""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


async def list_time_entries_impl(
    project_id: Optional[Union[str, int]] = None,
    issue_id: Optional[int] = None,
    user_id: Optional[Union[str, int]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    *,
    get_client: Callable[[], Any],
    time_entry_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List time entries from Redmine with filtering and pagination."""
    try:
        filters: Dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if project_id is not None:
            filters["project_id"] = project_id
        if issue_id is not None:
            filters["issue_id"] = issue_id
        if user_id is not None:
            filters["user_id"] = user_id
        if from_date is not None:
            filters["from_date"] = from_date
        if to_date is not None:
            filters["to_date"] = to_date

        client = get_client()
        time_entries = await asyncio.to_thread(
            lambda: list(client.time_entry.filter(**filters))
        )
        return [time_entry_to_dict(time_entry) for time_entry in time_entries]
    except Exception as e:
        return [handle_error(e, "listing time entries", None)]


async def create_time_entry_impl(
    hours: float,
    project_id: Optional[Union[str, int]] = None,
    issue_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    comments: str = "",
    spent_on: Optional[str] = None,
    *,
    get_client: Callable[[], Any],
    time_entry_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Create a new time entry in Redmine."""
    if project_id is None and issue_id is None:
        return {"error": "Either project_id or issue_id must be provided."}

    if hours <= 0:
        return {"error": "Hours must be a positive number."}

    try:
        params: Dict[str, Any] = {"hours": hours}
        if project_id is not None:
            params["project_id"] = project_id
        if issue_id is not None:
            params["issue_id"] = issue_id
        if activity_id is not None:
            params["activity_id"] = activity_id
        if comments:
            params["comments"] = comments
        if spent_on is not None:
            params["spent_on"] = spent_on

        client = get_client()
        time_entry = await asyncio.to_thread(client.time_entry.create, **params)
        return time_entry_to_dict(time_entry)
    except Exception as e:
        context: dict[str, Any] = {}
        if issue_id:
            context = {"resource_type": "issue", "resource_id": issue_id}
        elif project_id:
            context = {"resource_type": "project", "resource_id": project_id}
        return handle_error(e, "creating time entry", context)


async def update_time_entry_impl(
    time_entry_id: int,
    hours: Optional[float] = None,
    activity_id: Optional[int] = None,
    comments: Optional[str] = None,
    spent_on: Optional[str] = None,
    *,
    get_client: Callable[[], Any],
    time_entry_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Update an existing time entry in Redmine."""
    if hours is not None and hours <= 0:
        return {"error": "Hours must be a positive number."}

    try:
        params: Dict[str, Any] = {}
        if hours is not None:
            params["hours"] = hours
        if activity_id is not None:
            params["activity_id"] = activity_id
        if comments is not None:
            params["comments"] = comments
        if spent_on is not None:
            params["spent_on"] = spent_on

        if not params:
            return {"error": "No fields provided for update."}

        client = get_client()
        await asyncio.to_thread(client.time_entry.update, time_entry_id, **params)
        updated_entry = await asyncio.to_thread(client.time_entry.get, time_entry_id)
        return time_entry_to_dict(updated_entry)
    except Exception as e:
        return handle_error(
            e,
            f"updating time entry {time_entry_id}",
            {"resource_type": "time entry", "resource_id": time_entry_id},
        )


async def delete_time_entry_impl(
    time_entry_id: int,
    *,
    get_client: Callable[[], Any],
    is_read_only_mode: Callable[[], bool],
    read_only_error: Mapping[str, Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Delete a time entry from Redmine."""
    if is_read_only_mode():
        return dict(read_only_error)

    try:
        client = get_client()
        await asyncio.to_thread(client.time_entry.delete, time_entry_id)
        return {
            "success": True,
            "time_entry_id": time_entry_id,
            "message": f"Time entry {time_entry_id} deleted successfully.",
        }
    except Exception as e:
        return handle_error(
            e,
            f"deleting time entry {time_entry_id}",
            {"resource_type": "time entry", "resource_id": time_entry_id},
        )


async def list_time_entry_activities_impl(
    *,
    get_client: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> List[Dict[str, Any]]:
    """List available time entry activities from Redmine."""
    try:
        client = get_client()
        activities = await asyncio.to_thread(
            lambda: list(client.enumeration.filter(resource="time_entry_activities"))
        )
        return [
            {
                "id": getattr(activity, "id", None),
                "name": getattr(activity, "name", None),
                "active": getattr(activity, "active", None),
                "is_default": getattr(activity, "is_default", None),
            }
            for activity in activities
        ]
    except Exception as e:
        return [handle_error(e, "listing time entry activities", None)]
