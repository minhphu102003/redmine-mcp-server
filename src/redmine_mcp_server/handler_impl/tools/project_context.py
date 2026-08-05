"""Consolidated project issue context tool implementation."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from .projects import (
    list_project_issue_categories_impl,
    list_project_issue_custom_fields_impl,
    list_project_members_impl,
    list_project_trackers_impl,
    list_redmine_versions_impl,
)

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


def _serialize_project(
    project: Any, wrap_content: Callable[[Any], Any]
) -> Dict[str, Any]:
    """Serialize basic project metadata into a JSON-safe dictionary."""
    return {
        "id": getattr(project, "id", None),
        "name": wrap_content(getattr(project, "name", "")),
        "identifier": wrap_content(getattr(project, "identifier", "")),
        "description": wrap_content(getattr(project, "description", "")),
        "created_on": (
            project.created_on.isoformat()
            if getattr(project, "created_on", None) is not None
            else None
        ),
    }


async def get_project_issue_context_impl(
    project_id: Union[str, int],
    tracker_id: Optional[Union[str, int]] = None,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    custom_field_applies_to_tracker: Callable[[Any, Optional[int]], bool],
    custom_field_to_dict: Callable[[Any], Dict[str, Any]],
    membership_to_dict: Callable[[Any], Dict[str, Any]],
    version_to_dict: Callable[[Any], Dict[str, Any]],
    wrap_content: Callable[[Any], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Fetch complete issue-creation context for a project in one call."""
    await ensure_cleanup_started()
    try:
        client = get_client()
        if client is None:
            return handle_error(
                RuntimeError("Redmine client not initialized"),
                f"fetching project issue context for {project_id}",
                {"resource_id": project_id},
            )

        project = await asyncio.to_thread(client.project.get, project_id)

        trackers, categories, members, versions, custom_fields = await asyncio.gather(
            list_project_trackers_impl(
                project_id,
                ensure_cleanup_started=ensure_cleanup_started,
                get_client=get_client,
                wrap_content=wrap_content,
                handle_error=handle_error,
            ),
            list_project_issue_categories_impl(
                project_id,
                ensure_cleanup_started=ensure_cleanup_started,
                get_client=get_client,
                wrap_content=wrap_content,
                handle_error=handle_error,
            ),
            list_project_members_impl(
                project_id,
                get_client=get_client,
                membership_to_dict=membership_to_dict,
                handle_error=handle_error,
            ),
            list_redmine_versions_impl(
                project_id,
                status_filter=None,
                ensure_cleanup_started=ensure_cleanup_started,
                get_client=get_client,
                version_to_dict=version_to_dict,
                handle_error=handle_error,
            ),
            list_project_issue_custom_fields_impl(
                project_id,
                tracker_id,
                ensure_cleanup_started=ensure_cleanup_started,
                get_client=get_client,
                custom_field_applies_to_tracker=custom_field_applies_to_tracker,
                custom_field_to_dict=custom_field_to_dict,
                handle_error=handle_error,
            ),
        )

        required_custom_fields = [
            field
            for field in custom_fields
            if isinstance(field, dict) and field.get("is_required")
        ]

        return {
            "project": _serialize_project(project, wrap_content),
            "tracker_id": tracker_id,
            "trackers": trackers,
            "categories": categories,
            "members": members,
            "versions": versions,
            "custom_fields": custom_fields,
            "required_custom_fields": required_custom_fields,
        }
    except Exception as e:
        return handle_error(
            e,
            f"fetching project issue context for {project_id}",
            {"resource_type": "project", "resource_id": project_id},
        )
