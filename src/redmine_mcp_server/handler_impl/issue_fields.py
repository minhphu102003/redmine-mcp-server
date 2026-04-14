"""Issue-field helper utilities extracted from redmine_handler."""

import json
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Set, Union

logger = logging.getLogger(__name__)

_DEFAULT_REQUIRED_CUSTOM_FIELD_VALUES: Dict[str, Any] = {}

_STANDARD_ISSUE_UPDATE_FIELDS: Set[str] = {
    "subject",
    "description",
    "notes",
    "private_notes",
    "tracker_id",
    "status_id",
    "priority_id",
    "category_id",
    "fixed_version_id",
    "assigned_to_id",
    "parent_issue_id",
    "start_date",
    "due_date",
    "done_ratio",
    "estimated_hours",
    "is_private",
    "watcher_user_ids",
    "uploads",
    "deleted_attachment_ids",
    "custom_fields",
    "status_name",
}


def _is_true_env(var_name: str, default: str = "false") -> bool:
    """Parse common truthy env-var values."""
    return os.getenv(var_name, default).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_field_label(label: str) -> str:
    """Normalize a field label for case/spacing-insensitive comparisons."""
    return re.sub(r"[^a-z0-9]+", "", label.lower())


def _parse_create_issue_fields(
    fields: Optional[Union[Dict[str, Any], str]],
) -> Dict[str, Any]:
    """Parse create issue fields from dict or serialized string payload."""
    return _parse_optional_object_payload(fields, "fields")


def _parse_optional_object_payload(
    payload: Optional[Union[Dict[str, Any], str]], payload_name: str
) -> Dict[str, Any]:
    """Parse an optional payload from dict or serialized JSON object string."""
    if payload is None:
        return {}

    if isinstance(payload, dict):
        parsed: Any = dict(payload)
    elif isinstance(payload, str):
        raw = payload.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception as e:
            raise ValueError(
                f"Invalid {payload_name} payload. Expected a dict or "
                "JSON object string."
            ) from e
    else:
        raise ValueError(
            f"Invalid {payload_name} payload. Expected a dict or JSON object string."
        )

    if parsed is None:
        raise ValueError(
            f"Invalid {payload_name} payload. Parsed value must be an object/dict."
        )

    if isinstance(parsed, dict) and set(parsed.keys()) == {payload_name}:
        wrapped = parsed.get(payload_name)
        if isinstance(wrapped, dict):
            parsed = wrapped

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Invalid {payload_name} payload. Parsed value must be an object/dict."
        )

    return dict(parsed)


def _extract_possible_values(custom_field: Any) -> List[str]:
    """Extract possible values from a Redmine custom field in a robust way."""
    possible_values = getattr(custom_field, "possible_values", None) or []
    result: List[str] = []
    for value in possible_values:
        if isinstance(value, dict):
            extracted = value.get("value")
        else:
            extracted = getattr(value, "value", value)
        if extracted is not None:
            result.append(str(extracted))
    return result


def _load_required_custom_field_defaults(
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load normalized custom field defaults from env + built-in fallbacks."""
    resolved_defaults = dict(defaults or _DEFAULT_REQUIRED_CUSTOM_FIELD_VALUES)
    raw = os.getenv("REDMINE_REQUIRED_CUSTOM_FIELD_DEFAULTS", "").strip()
    if not raw:
        return resolved_defaults

    try:
        loaded = json.loads(raw)
        if isinstance(loaded, dict):
            for key, value in loaded.items():
                if key and value is not None:
                    resolved_defaults[_normalize_field_label(str(key))] = value
        else:
            logger.warning(
                "REDMINE_REQUIRED_CUSTOM_FIELD_DEFAULTS must be a JSON object."
            )
    except Exception as e:
        logger.warning(
            "Failed parsing REDMINE_REQUIRED_CUSTOM_FIELD_DEFAULTS as JSON: %s",
            e,
        )

    return resolved_defaults


def _is_required_custom_field_autofill_enabled() -> bool:
    """Check whether retry-based required custom field autofill is enabled."""
    return _is_true_env("REDMINE_AUTOFILL_REQUIRED_CUSTOM_FIELDS", "false")


def _extract_missing_required_field_names(error_message: str) -> List[str]:
    """Extract field names from relevant validation errors."""
    message = error_message or ""
    if "Validation failed:" in message:
        message = message.split("Validation failed:", 1)[1]

    # Handle common Redmine validation fragments that imply we should retry
    # required custom field autofill.
    markers = [
        "cannot be blank",
        "is not included in the list",
        "is invalid",
    ]

    missing_names: List[str] = []
    for item in [part.strip() for part in message.split(",") if part.strip()]:
        lower_item = item.lower()
        for marker in markers:
            marker_pos = lower_item.find(marker)
            if marker_pos == -1:
                continue
            field_name = item[:marker_pos].strip(" .:")
            if field_name:
                missing_names.append(field_name)
            break

    return missing_names


def _is_missing_custom_field_value(value: Any) -> bool:
    """Return True when a custom field value should be treated as missing."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _is_allowed_custom_field_value(value: Any, possible_values: List[str]) -> bool:
    """Check whether a value is compatible with field possible_values."""
    if not possible_values:
        return True
    if isinstance(value, (list, tuple, set)):
        return bool(value) and all(str(item) in possible_values for item in value)
    return str(value) in possible_values


def _resolve_required_custom_field_value(
    custom_field: Any, defaults: Dict[str, Any]
) -> Optional[Any]:
    """Resolve value from explicit defaults only (Redmine default/env override)."""
    name = str(getattr(custom_field, "name", "") or "")
    normalized_name = _normalize_field_label(name)
    possible_values = _extract_possible_values(custom_field)

    default_value = getattr(custom_field, "default_value", None)
    if not _is_missing_custom_field_value(
        default_value
    ) and _is_allowed_custom_field_value(default_value, possible_values):
        return default_value

    preferred = defaults.get(normalized_name)
    if not _is_missing_custom_field_value(preferred) and _is_allowed_custom_field_value(
        preferred, possible_values
    ):
        return preferred

    return None


def _augment_fields_with_required_custom_fields(
    project_id: int,
    issue_fields: Dict[str, Any],
    missing_field_names: List[str],
    get_client: Optional[Callable[[], Any]] = None,
    defaults: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Populate missing required custom fields based on project metadata."""
    if not missing_field_names:
        return issue_fields

    missing_normalized = {_normalize_field_label(name) for name in missing_field_names}
    if not missing_normalized:
        return issue_fields

    if get_client is None:
        raise ValueError("get_client callable is required.")

    project = get_client().project.get(
        project_id, include="issue_custom_fields"
    )
    project_custom_fields = getattr(project, "issue_custom_fields", None) or []

    updated_fields = dict(issue_fields)
    existing_custom_fields = updated_fields.get("custom_fields", [])
    if existing_custom_fields is None:
        existing_custom_fields = []
    if not isinstance(existing_custom_fields, list):
        raise ValueError(
            "Invalid custom_fields payload. Expected a list of "
            "{'id': <int>, 'value': <value>} dictionaries."
        )

    merged_custom_fields: List[Dict[str, Any]] = []
    existing_entries_by_id: Dict[Any, Dict[str, Any]] = {}
    for entry in existing_custom_fields:
        if not isinstance(entry, dict):
            continue
        entry_copy = dict(entry)
        field_id = entry_copy.get("id")
        if field_id is not None and field_id not in existing_entries_by_id:
            existing_entries_by_id[field_id] = entry_copy
        merged_custom_fields.append(entry_copy)

    resolved_defaults = _load_required_custom_field_defaults(defaults=defaults)

    for custom_field in project_custom_fields:
        field_id = getattr(custom_field, "id", None)
        field_name = str(getattr(custom_field, "name", "") or "")
        if field_id is None or not field_name:
            continue

        normalized_name = _normalize_field_label(field_name)
        if normalized_name not in missing_normalized:
            continue

        possible_values = _extract_possible_values(custom_field)
        field_value = _resolve_required_custom_field_value(
            custom_field,
            resolved_defaults,
        )
        if field_value is None:
            continue
        existing_entry = existing_entries_by_id.get(field_id)
        if existing_entry is not None:
            existing_value = existing_entry.get("value")
            if _is_missing_custom_field_value(existing_value) or (
                not _is_allowed_custom_field_value(existing_value, possible_values)
            ):
                existing_entry["value"] = field_value
            continue

        new_entry = {"id": field_id, "value": field_value}
        merged_custom_fields.append(new_entry)
        existing_entries_by_id[field_id] = new_entry

    if merged_custom_fields:
        updated_fields["custom_fields"] = merged_custom_fields

    return updated_fields


def _coerce_update_custom_fields(
    custom_fields: Optional[Any],
) -> List[Dict[str, Any]]:
    """Normalize an update payload custom_fields value into Redmine format."""
    if custom_fields is None:
        return []
    if not isinstance(custom_fields, list):
        raise ValueError(
            "Invalid custom_fields payload. Expected a list of "
            "{'id': <int>, 'value': <value>} dictionaries."
        )

    normalized: List[Dict[str, Any]] = []
    for entry in custom_fields:
        if not isinstance(entry, dict):
            raise ValueError(
                "Invalid custom_fields payload. Expected a list of "
                "{'id': <int>, 'value': <value>} dictionaries."
            )
        if "id" not in entry:
            raise ValueError("Invalid custom_fields entry. Missing required 'id'.")
        normalized.append({"id": entry["id"], "value": entry.get("value")})
    return normalized


def _upsert_custom_field_entry(
    entries: List[Dict[str, Any]], field_id: Any, value: Any
) -> None:
    """Insert or replace a custom field entry by id."""
    for entry in entries:
        if entry.get("id") == field_id:
            entry["value"] = value
            return
    entries.append({"id": field_id, "value": value})


def _resolve_project_issue_custom_fields(
    issue_id: int, get_client: Callable[[], Any]
) -> List[Any]:
    """Load project custom-field definitions for a given issue."""
    issue = get_client().issue.get(issue_id)
    project = getattr(issue, "project", None)
    project_id = getattr(project, "id", None)
    if project_id is None:
        return []
    project_obj = get_client().project.get(project_id, include="issue_custom_fields")
    return list(getattr(project_obj, "issue_custom_fields", None) or [])


def _is_standard_issue_update_key(field_name: str) -> bool:
    """Return True when a field name should be passed through unchanged."""
    return field_name in _STANDARD_ISSUE_UPDATE_FIELDS


def _map_named_custom_fields_for_update(
    issue_id: int, update_fields: Dict[str, Any], get_client: Callable[[], Any]
) -> Dict[str, Any]:
    """Map named custom fields in an update payload to custom_fields entries."""
    if not update_fields:
        return update_fields

    # Keep caller-provided custom_fields and merge name-based mappings into it.
    missing = object()
    custom_fields_raw = update_fields.pop("custom_fields", missing)
    custom_fields_provided = (
        custom_fields_raw is not missing and custom_fields_raw is not None
    )
    if custom_fields_raw is missing:
        custom_fields_raw = None
    merged_custom_fields = _coerce_update_custom_fields(custom_fields_raw)

    named_candidates = [
        field_name
        for field_name in update_fields.keys()
        if not _is_standard_issue_update_key(field_name)
    ]
    if not named_candidates:
        if custom_fields_provided:
            update_fields["custom_fields"] = merged_custom_fields
        return update_fields

    project_custom_fields = _resolve_project_issue_custom_fields(issue_id, get_client)
    by_normalized_name: Dict[str, Dict[str, Any]] = {}
    ambiguous_names: Set[str] = set()

    for custom_field in project_custom_fields:
        field_id = getattr(custom_field, "id", None)
        field_name = str(getattr(custom_field, "name", "") or "")
        if field_id is None or not field_name:
            continue
        normalized = _normalize_field_label(field_name)
        if not normalized:
            continue
        existing = by_normalized_name.get(normalized)
        if existing and existing.get("id") != field_id:
            ambiguous_names.add(normalized)
            continue
        by_normalized_name[normalized] = {
            "id": field_id,
            "name": field_name,
            "possible_values": _extract_possible_values(custom_field),
        }

    for normalized in ambiguous_names:
        by_normalized_name.pop(normalized, None)

    for candidate in named_candidates:
        normalized_candidate = _normalize_field_label(candidate)
        if normalized_candidate in ambiguous_names:
            raise ValueError(
                f"Ambiguous custom field name '{candidate}'. "
                "Use fields.custom_fields with explicit field IDs."
            )

        match = by_normalized_name.get(normalized_candidate)
        if match is None:
            continue

        value = update_fields.pop(candidate)
        possible_values = match["possible_values"]
        if not _is_missing_custom_field_value(
            value
        ) and not _is_allowed_custom_field_value(value, possible_values):
            raise ValueError(
                f"Invalid value '{value}' for custom field '{match['name']}'. "
                f"Allowed values: {possible_values}."
            )
        _upsert_custom_field_entry(merged_custom_fields, match["id"], value)

    if merged_custom_fields or custom_fields_provided:
        update_fields["custom_fields"] = merged_custom_fields

    return update_fields


def _custom_field_trackers_to_list(custom_field: Any) -> List[Dict[str, Any]]:
    """Serialize custom field tracker bindings into a predictable list."""
    raw_trackers = getattr(custom_field, "trackers", None)
    if raw_trackers is None:
        return []

    try:
        iterator = iter(raw_trackers)
    except TypeError:
        return []

    trackers: List[Dict[str, Any]] = []
    for tracker in iterator:
        tracker_id = None
        tracker_name = None

        if isinstance(tracker, dict):
            tracker_id = tracker.get("id")
            tracker_name = tracker.get("name")
        else:
            tracker_id = getattr(tracker, "id", None)
            tracker_name = getattr(tracker, "name", None)

        if tracker_id is None and tracker_name is None:
            continue

        if tracker_id is not None:
            try:
                tracker_id = int(tracker_id)
            except (TypeError, ValueError):
                tracker_id = str(tracker_id)

        trackers.append({"id": tracker_id, "name": tracker_name})

    return trackers


def _custom_field_applies_to_tracker(
    custom_field: Any, tracker_id: Optional[int]
) -> bool:
    """Return whether a custom field is available for the given tracker."""
    if tracker_id is None:
        return True

    trackers = _custom_field_trackers_to_list(custom_field)
    if not trackers:
        # No tracker restrictions exposed by Redmine -> treat as globally available.
        return True

    for tracker in trackers:
        if tracker.get("id") == tracker_id:
            return True

    return False


def _custom_field_to_dict(custom_field: Any) -> Dict[str, Any]:
    """Convert project issue custom field metadata to a serializable dict."""
    return {
        "id": getattr(custom_field, "id", None),
        "name": getattr(custom_field, "name", ""),
        "field_format": getattr(custom_field, "field_format", ""),
        "is_required": bool(getattr(custom_field, "is_required", False)),
        "multiple": bool(getattr(custom_field, "multiple", False)),
        "default_value": getattr(custom_field, "default_value", None),
        "possible_values": _extract_possible_values(custom_field),
        "trackers": _custom_field_trackers_to_list(custom_field),
    }
