"""Undecorated project tool implementations extracted from redmine_handler."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Union

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


async def list_redmine_projects_impl(
    *,
    get_client: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> List[Dict[str, Any]]:
    """List all accessible projects in Redmine."""
    try:
        projects = get_client().project.all()
        return [
            {
                "id": project.id,
                "name": project.name,
                "identifier": project.identifier,
                "description": getattr(project, "description", ""),
                "created_on": (
                    project.created_on.isoformat()
                    if getattr(project, "created_on", None) is not None
                    else None
                ),
            }
            for project in projects
        ]
    except Exception as e:
        return [handle_error(e, "listing projects", None)]


async def list_project_issue_custom_fields_impl(
    project_id: Union[str, int],
    tracker_id: Optional[Union[str, int]] = None,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    custom_field_applies_to_tracker: Callable[[Any, Optional[int]], bool],
    custom_field_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> List[Dict[str, Any]]:
    """List issue custom fields configured for a project."""
    parsed_tracker_id: Optional[int] = None
    if tracker_id is not None:
        try:
            parsed_tracker_id = int(tracker_id)
        except (TypeError, ValueError):
            return [
                {
                    "error": (
                        f"Invalid tracker_id '{tracker_id}'. "
                        "Expected an integer tracker ID."
                    )
                }
            ]

    await ensure_cleanup_started()
    try:
        project = get_client().project.get(project_id, include="issue_custom_fields")
        custom_fields = getattr(project, "issue_custom_fields", None) or []

        result: List[Dict[str, Any]] = []
        for custom_field in custom_fields:
            if not custom_field_applies_to_tracker(custom_field, parsed_tracker_id):
                continue
            result.append(custom_field_to_dict(custom_field))

        return result
    except Exception as e:
        return [
            handle_error(
                e,
                f"listing issue custom fields for project {project_id}",
                {"resource_type": "project", "resource_id": project_id},
            )
        ]


async def list_redmine_versions_impl(
    project_id: Union[str, int],
    status_filter: Optional[str] = None,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    version_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> List[Dict[str, Any]]:
    """List versions (roadmap milestones) for a Redmine project."""
    valid_statuses = {"open", "locked", "closed"}
    if status_filter is not None:
        status_filter = str(status_filter).lower()
        if status_filter not in valid_statuses:
            return [
                {
                    "error": (
                        f"Invalid status_filter '{status_filter}'. "
                        "Allowed values: open, locked, closed"
                    )
                }
            ]

    await ensure_cleanup_started()
    try:
        versions = get_client().version.filter(project_id=project_id)
        result = []
        for version in versions:
            if (
                status_filter is not None
                and getattr(version, "status", "") != status_filter
            ):
                continue
            result.append(version_to_dict(version))
        return result
    except Exception as e:
        return [
            handle_error(
                e,
                f"listing versions for project {project_id}",
                {"resource_type": "project", "resource_id": project_id},
            )
        ]


async def list_project_members_impl(
    project_id: Union[str, int],
    *,
    get_client: Callable[[], Any],
    membership_to_dict: Callable[[Any], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> List[Dict[str, Any]]:
    """List members of a Redmine project."""
    try:
        memberships = get_client().project_membership.filter(project_id=project_id)
        return [membership_to_dict(membership) for membership in memberships]
    except Exception as e:
        return [
            handle_error(
                e,
                f"listing members for project {project_id}",
                {"resource_type": "project", "resource_id": project_id},
            )
        ]
