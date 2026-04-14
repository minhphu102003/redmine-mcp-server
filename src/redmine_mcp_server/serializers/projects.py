"""Serializer helpers split from serialization module."""

from typing import Any, Dict


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
