"""Serializer helpers split from serialization module."""

import uuid
from datetime import datetime
from typing import Any, Dict


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
