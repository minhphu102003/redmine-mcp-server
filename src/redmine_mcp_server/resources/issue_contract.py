"""Issue contract resource payload builder."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Union

from ..handler_impl import issue_fields as _issue_fields


def _serialize_project_trackers(project: Any) -> List[Dict[str, Any]]:
    """Serialize project trackers into a stable list."""
    trackers: List[Dict[str, Any]] = []
    for tracker in getattr(project, "trackers", None) or []:
        trackers.append(
            {
                "id": getattr(tracker, "id", None),
                "name": getattr(tracker, "name", ""),
            }
        )
    return trackers


def _parse_tracker_id(tracker_id: Optional[Union[str, int]]) -> Optional[int]:
    """Parse optional tracker id safely."""
    if tracker_id is None:
        return None
    return int(tracker_id)


async def build_issue_contract_payload(
    *,
    project_id: Union[str, int],
    tracker_id: Optional[Union[str, int]],
    get_client: Callable[[], Any],
    handle_error: Callable[[Exception, str, Optional[Dict[str, Any]]], Dict[str, Any]],
    standard_issue_update_fields: Set[str],
    template_resource_uri: str,
    template_required_sections: List[str],
    template_enforced: bool,
) -> Dict[str, Any]:
    """Build issue-create/update contract payload for a project/tracker."""
    try:
        parsed_tracker_id = _parse_tracker_id(tracker_id)
    except (TypeError, ValueError):
        return {
            "error": (
                f"Invalid tracker_id '{tracker_id}'. Expected an integer tracker ID."
            )
        }

    try:
        project = get_client().project.get(project_id, include="issue_custom_fields")
        project_custom_fields = getattr(project, "issue_custom_fields", None) or []
        custom_fields: List[Dict[str, Any]] = []

        for custom_field in project_custom_fields:
            if not _issue_fields._custom_field_applies_to_tracker(
                custom_field, parsed_tracker_id
            ):
                continue
            custom_fields.append(_issue_fields._custom_field_to_dict(custom_field))

        required_custom_fields = [
            {
                "id": field.get("id"),
                "name": field.get("name"),
                "multiple": field.get("multiple", False),
                "possible_values": field.get("possible_values", []),
                "default_value": field.get("default_value"),
            }
            for field in custom_fields
            if field.get("is_required")
        ]

        return {
            "resource": "issue_contract",
            "project": {
                "id": getattr(project, "id", project_id),
                "name": getattr(project, "name", ""),
                "identifier": getattr(project, "identifier", ""),
            },
            "tracker_id": parsed_tracker_id,
            "trackers": _serialize_project_trackers(project),
            "create_required_fields": ["project_id", "subject"],
            "description_template": {
                "resource_uri": template_resource_uri,
                "enforced": template_enforced,
                "required_sections": template_required_sections,
            },
            "update_supported_fields": sorted(standard_issue_update_fields),
            "custom_fields": custom_fields,
            "required_custom_fields": required_custom_fields,
            "custom_field_name_matching": (
                "Case/spacing-insensitive. If ambiguous names exist, "
                "use custom_fields with explicit IDs."
            ),
        }
    except Exception as exc:
        return handle_error(
            exc,
            f"building issue contract for project {project_id}",
            {"resource_type": "project", "resource_id": project_id},
        )
