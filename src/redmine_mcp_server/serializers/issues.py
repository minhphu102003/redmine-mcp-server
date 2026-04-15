"""Serializer helpers split from serialization module."""

from typing import Any, Dict, List, Optional

from .content import _coerce_json_safe, wrap_insecure_content


def _custom_fields_to_list(issue: Any) -> List[Dict[str, Any]]:
    """Convert issue custom_fields to a serializable list."""
    raw_custom_fields = getattr(issue, "custom_fields", None)
    if raw_custom_fields is None:
        return []

    custom_fields: List[Dict[str, Any]] = []
    try:
        iterator = iter(raw_custom_fields)
    except TypeError:
        return []

    for custom_field in iterator:
        if isinstance(custom_field, dict):
            field_id = custom_field.get("id")
            field_name = custom_field.get("name")
            field_value = custom_field.get("value")
        else:
            field_id = getattr(custom_field, "id", None)
            field_name = getattr(custom_field, "name", None)
            field_value = getattr(custom_field, "value", None)

        custom_fields.append(
            {
                "id": field_id,
                "name": field_name,
                "value": _coerce_json_safe(field_value),
            }
        )

    return custom_fields


def _issue_to_dict(issue: Any, include_custom_fields: bool = False) -> Dict[str, Any]:
    """Convert a python-redmine Issue object to a serializable dict."""
    # Use getattr for all potentially missing attributes (search API may not return all)
    assigned = getattr(issue, "assigned_to", None)
    project = getattr(issue, "project", None)
    status = getattr(issue, "status", None)
    priority = getattr(issue, "priority", None)
    author = getattr(issue, "author", None)

    issue_dict = {
        "id": getattr(issue, "id", None),
        "subject": getattr(issue, "subject", ""),
        "description": wrap_insecure_content(getattr(issue, "description", "")),
        "project": (
            {"id": project.id, "name": project.name} if project is not None else None
        ),
        "status": (
            {"id": status.id, "name": status.name} if status is not None else None
        ),
        "priority": (
            {"id": priority.id, "name": priority.name} if priority is not None else None
        ),
        "author": (
            {"id": author.id, "name": author.name} if author is not None else None
        ),
        "assigned_to": (
            {
                "id": assigned.id,
                "name": assigned.name,
            }
            if assigned is not None
            else None
        ),
        "created_on": (
            issue.created_on.isoformat()
            if getattr(issue, "created_on", None) is not None
            else None
        ),
        "updated_on": (
            issue.updated_on.isoformat()
            if getattr(issue, "updated_on", None) is not None
            else None
        ),
    }

    if include_custom_fields:
        issue_dict["custom_fields"] = _custom_fields_to_list(issue)

    return issue_dict


def _issue_to_dict_selective(
    issue: Any, fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Convert a python-redmine Issue object to a dict with selected fields.

    Args:
        issue: The python-redmine Issue object to convert.
        fields: List of field names to include. If None, ["*"], or ["all"],
                returns all fields (same as _issue_to_dict). Invalid or
                missing fields are silently skipped.

    Available fields:
        - id: Issue ID
        - subject: Issue subject/title
        - description: Issue description
        - project: Project info (dict with id and name)
        - status: Status info (dict with id and name)
        - priority: Priority info (dict with id and name)
        - author: Author info (dict with id and name)
        - assigned_to: Assigned user info (dict with id and name, or None)
        - created_on: Creation timestamp (ISO format)
        - updated_on: Last update timestamp (ISO format)

    Returns:
        Dictionary containing only the requested fields.

    Examples:
        >>> _issue_to_dict_selective(issue, ["id", "subject"])
        {"id": 123, "subject": "Bug fix"}

        >>> _issue_to_dict_selective(issue, ["*"])
        # Returns all fields (same as _issue_to_dict)

        >>> _issue_to_dict_selective(issue, None)
        # Returns all fields (same as _issue_to_dict)
    """
    # Handle "all fields" cases
    if fields is None or fields == ["*"] or fields == ["all"]:
        return _issue_to_dict(issue)

    # Build field mapping with all available fields
    # Use getattr for all potentially missing attributes (search API may not return all)
    assigned = getattr(issue, "assigned_to", None)
    project = getattr(issue, "project", None)
    status = getattr(issue, "status", None)
    priority = getattr(issue, "priority", None)
    author = getattr(issue, "author", None)

    all_fields = {
        "id": getattr(issue, "id", None),
        "subject": getattr(issue, "subject", ""),
        "description": wrap_insecure_content(getattr(issue, "description", "")),
        "project": (
            {"id": project.id, "name": project.name} if project is not None else None
        ),
        "status": (
            {"id": status.id, "name": status.name} if status is not None else None
        ),
        "priority": (
            {"id": priority.id, "name": priority.name} if priority is not None else None
        ),
        "author": (
            {"id": author.id, "name": author.name} if author is not None else None
        ),
        "assigned_to": (
            {
                "id": assigned.id,
                "name": assigned.name,
            }
            if assigned is not None
            else None
        ),
        "created_on": (
            issue.created_on.isoformat()
            if getattr(issue, "created_on", None) is not None
            else None
        ),
        "updated_on": (
            issue.updated_on.isoformat()
            if getattr(issue, "updated_on", None) is not None
            else None
        ),
    }

    # Return only requested fields (silently skip invalid field names)
    return {key: all_fields[key] for key in fields if key in all_fields}


def _journals_to_list(issue: Any) -> List[Dict[str, Any]]:
    """Convert journals on an issue object to a list of dicts."""
    raw_journals = getattr(issue, "journals", None)
    if raw_journals is None:
        return []

    journals: List[Dict[str, Any]] = []
    try:
        iterator = iter(raw_journals)
    except TypeError:
        return []

    for journal in iterator:
        notes = getattr(journal, "notes", "")
        if not notes:
            continue
        user = getattr(journal, "user", None)
        journals.append(
            {
                "id": journal.id,
                "user": (
                    {
                        "id": user.id,
                        "name": user.name,
                    }
                    if user is not None
                    else None
                ),
                "notes": wrap_insecure_content(notes),
                "created_on": (
                    journal.created_on.isoformat()
                    if getattr(journal, "created_on", None) is not None
                    else None
                ),
            }
        )
    return journals


def _attachments_to_list(issue: Any) -> List[Dict[str, Any]]:
    """Convert attachments on an issue object to a list of dicts."""
    raw_attachments = getattr(issue, "attachments", None)
    if raw_attachments is None:
        return []

    attachments: List[Dict[str, Any]] = []
    try:
        iterator = iter(raw_attachments)
    except TypeError:
        return []

    for attachment in iterator:
        attachments.append(
            {
                "id": attachment.id,
                "filename": getattr(attachment, "filename", ""),
                "filesize": getattr(attachment, "filesize", 0),
                "content_type": getattr(attachment, "content_type", ""),
                "description": getattr(attachment, "description", ""),
                "content_url": getattr(attachment, "content_url", ""),
                "author": (
                    {
                        "id": attachment.author.id,
                        "name": attachment.author.name,
                    }
                    if getattr(attachment, "author", None) is not None
                    else None
                ),
                "created_on": (
                    attachment.created_on.isoformat()
                    if getattr(attachment, "created_on", None) is not None
                    else None
                ),
            }
        )
    return attachments


def _version_to_dict(version: Any) -> Dict[str, Any]:
    """Convert a python-redmine Version object to a serializable dict."""
    project = getattr(version, "project", None)
    return {
        "id": getattr(version, "id", None),
        "name": getattr(version, "name", ""),
        "description": wrap_insecure_content(getattr(version, "description", "")),
        "status": getattr(version, "status", ""),
        "due_date": (
            str(version.due_date)
            if getattr(version, "due_date", None) is not None
            else None
        ),
        "sharing": getattr(version, "sharing", ""),
        "wiki_page_title": getattr(version, "wiki_page_title", ""),
        "project": (
            {"id": project.id, "name": project.name} if project is not None else None
        ),
        "created_on": (
            version.created_on.isoformat()
            if getattr(version, "created_on", None) is not None
            else None
        ),
        "updated_on": (
            version.updated_on.isoformat()
            if getattr(version, "updated_on", None) is not None
            else None
        ),
    }


def _analyze_issues(issues: List[Any]) -> Dict[str, Any]:
    """Helper function to analyze a list of issues and return statistics."""
    if not issues:
        return {
            "by_status": {},
            "by_priority": {},
            "by_assignee": {},
            "total": 0,
        }

    status_counts = {}
    priority_counts = {}
    assignee_counts = {}

    for issue in issues:
        # Count by status
        status_name = getattr(issue.status, "name", "Unknown")
        status_counts[status_name] = status_counts.get(status_name, 0) + 1

        # Count by priority
        priority_name = getattr(issue.priority, "name", "Unknown")
        priority_counts[priority_name] = priority_counts.get(priority_name, 0) + 1

        # Count by assignee
        assigned_to = getattr(issue, "assigned_to", None)
        if assigned_to:
            assignee_name = getattr(assigned_to, "name", "Unknown")
            assignee_counts[assignee_name] = assignee_counts.get(assignee_name, 0) + 1
        else:
            assignee_counts["Unassigned"] = assignee_counts.get("Unassigned", 0) + 1

    return {
        "by_status": status_counts,
        "by_priority": priority_counts,
        "by_assignee": assignee_counts,
        "total": len(issues),
    }
