"""Serialization and content-safety helpers for Redmine resources."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def wrap_insecure_content(content: Any) -> Any:
    """Wrap user-controlled content in boundary tags to prevent prompt injection.

    Wraps non-empty string content in unique boundary tags so that LLM
    consumers can distinguish trusted tool output from untrusted user data.

    Args:
        content: The content to wrap. Non-string or empty values are
                 returned unchanged.

    Returns:
        Wrapped string with boundary tags, or original value if not a
        non-empty string.
    """
    if not isinstance(content, str) or not content:
        return content
    boundary = uuid.uuid4().hex[:16]
    return (
        f"<insecure-content-{boundary}>\n{content}\n" f"</insecure-content-{boundary}>"
    )


def _coerce_json_safe(value: Any) -> Any:
    """Convert arbitrary values into JSON-safe data."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return [_coerce_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_json_safe(item) for key, item in value.items()}
    return str(value)


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


def _resource_to_dict(resource: Any, resource_type: str) -> Dict[str, Any]:
    """
    Convert any Redmine resource to a serializable dict for search results.

    Args:
        resource: Python-redmine resource object (Issue, WikiPage, etc.)
        resource_type: Type identifier ('issues', 'wiki_pages', etc.)

    Returns:
        Dictionary with standardized fields for search results
    """
    base_dict: Dict[str, Any] = {
        "id": getattr(resource, "id", None),
        "type": resource_type,
    }

    # Extract title from various possible attributes
    if hasattr(resource, "subject"):
        base_dict["title"] = resource.subject
    elif hasattr(resource, "title"):
        base_dict["title"] = resource.title
    elif hasattr(resource, "name"):
        base_dict["title"] = resource.name
    else:
        base_dict["title"] = None

    # Extract project info
    if hasattr(resource, "project") and resource.project is not None:
        base_dict["project"] = (
            resource.project.name
            if hasattr(resource.project, "name")
            else str(resource.project)
        )
        base_dict["project_id"] = getattr(resource.project, "id", None)
    elif hasattr(resource, "project_id") and resource.project_id:
        # Fallback for search results that have project_id but not project object
        base_dict["project"] = None
        base_dict["project_id"] = resource.project_id
    else:
        base_dict["project"] = None
        base_dict["project_id"] = None

    # Extract status (issues have status, wiki pages don't)
    if hasattr(resource, "status"):
        base_dict["status"] = (
            resource.status.name
            if hasattr(resource.status, "name")
            else str(resource.status)
        )
    else:
        base_dict["status"] = None

    # Extract updated timestamp
    if hasattr(resource, "updated_on"):
        base_dict["updated_on"] = (
            str(resource.updated_on) if resource.updated_on else None
        )
    else:
        base_dict["updated_on"] = None

    # Extract description/excerpt (first 200 chars)
    if hasattr(resource, "description") and resource.description:
        raw_excerpt = (
            resource.description[:200] + "..."
            if len(resource.description) > 200
            else resource.description
        )
        base_dict["excerpt"] = wrap_insecure_content(raw_excerpt)
    elif hasattr(resource, "text") and resource.text:
        raw_excerpt = (
            resource.text[:200] + "..." if len(resource.text) > 200 else resource.text
        )
        base_dict["excerpt"] = wrap_insecure_content(raw_excerpt)
    else:
        base_dict["excerpt"] = None

    return base_dict


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


def _membership_to_dict(membership: Any) -> Dict[str, Any]:
    """Convert a project membership to a serializable dict."""
    user = getattr(membership, "user", None)
    group = getattr(membership, "group", None)
    project = getattr(membership, "project", None)
    roles = getattr(membership, "roles", None) or []

    result: Dict[str, Any] = {
        "id": getattr(membership, "id", None),
    }

    # User or group (memberships can be for either)
    if user is not None:
        result["user"] = {
            "id": getattr(user, "id", None),
            "name": getattr(user, "name", ""),
        }
        result["group"] = None
    elif group is not None:
        result["user"] = None
        result["group"] = {
            "id": getattr(group, "id", None),
            "name": getattr(group, "name", ""),
        }
    else:
        result["user"] = None
        result["group"] = None

    # Project info
    if project is not None:
        result["project"] = {
            "id": getattr(project, "id", None),
            "name": getattr(project, "name", ""),
        }
    else:
        result["project"] = None

    # Roles
    result["roles"] = []
    try:
        for role in roles:
            if isinstance(role, dict):
                result["roles"].append(
                    {
                        "id": role.get("id"),
                        "name": role.get("name", ""),
                    }
                )
            else:
                result["roles"].append(
                    {
                        "id": getattr(role, "id", None),
                        "name": getattr(role, "name", ""),
                    }
                )
    except TypeError:
        pass  # roles not iterable

    return result


def _time_entry_to_dict(time_entry: Any) -> Dict[str, Any]:
    """Convert a time entry to a serializable dict."""
    user = getattr(time_entry, "user", None)
    project = getattr(time_entry, "project", None)
    issue = getattr(time_entry, "issue", None)
    activity = getattr(time_entry, "activity", None)

    return {
        "id": getattr(time_entry, "id", None),
        "hours": getattr(time_entry, "hours", 0),
        "comments": getattr(time_entry, "comments", ""),
        "spent_on": (
            str(time_entry.spent_on)
            if getattr(time_entry, "spent_on", None) is not None
            else None
        ),
        "user": (
            {"id": getattr(user, "id", None), "name": getattr(user, "name", "")}
            if user is not None
            else None
        ),
        "project": (
            {
                "id": getattr(project, "id", None),
                "name": getattr(project, "name", ""),
            }
            if project is not None
            else None
        ),
        "issue": ({"id": getattr(issue, "id", None)} if issue is not None else None),
        "activity": (
            {
                "id": getattr(activity, "id", None),
                "name": getattr(activity, "name", ""),
            }
            if activity is not None
            else None
        ),
        "created_on": (
            time_entry.created_on.isoformat()
            if getattr(time_entry, "created_on", None) is not None
            else None
        ),
        "updated_on": (
            time_entry.updated_on.isoformat()
            if getattr(time_entry, "updated_on", None) is not None
            else None
        ),
    }


def _wiki_page_to_dict(
    wiki_page: Any, include_attachments: bool = True
) -> Dict[str, Any]:
    """Convert a wiki page object to a dictionary.

    Args:
        wiki_page: Redmine wiki page object
        include_attachments: Whether to include attachment metadata

    Returns:
        Dictionary with wiki page data
    """
    result: Dict[str, Any] = {
        "title": wiki_page.title,
        "text": wrap_insecure_content(wiki_page.text),
        "version": wiki_page.version,
    }

    # Add optional timestamp fields
    if hasattr(wiki_page, "created_on"):
        result["created_on"] = (
            str(wiki_page.created_on) if wiki_page.created_on else None
        )
    else:
        result["created_on"] = None

    if hasattr(wiki_page, "updated_on"):
        result["updated_on"] = (
            str(wiki_page.updated_on) if wiki_page.updated_on else None
        )
    else:
        result["updated_on"] = None

    # Add author info
    if hasattr(wiki_page, "author"):
        result["author"] = {
            "id": wiki_page.author.id,
            "name": wiki_page.author.name,
        }

    # Add project info
    if hasattr(wiki_page, "project"):
        result["project"] = {
            "id": wiki_page.project.id,
            "name": wiki_page.project.name,
        }

    # Process attachments if requested
    if include_attachments and hasattr(wiki_page, "attachments"):
        result["attachments"] = []
        for attachment in wiki_page.attachments:
            att_dict = {
                "id": attachment.id,
                "filename": attachment.filename,
                "filesize": attachment.filesize,
                "content_type": attachment.content_type,
                "description": getattr(attachment, "description", ""),
                "created_on": (
                    str(attachment.created_on)
                    if hasattr(attachment, "created_on") and attachment.created_on
                    else None
                ),
            }
            result["attachments"].append(att_dict)

    return result
