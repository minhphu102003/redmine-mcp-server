"""Serializer helpers split from serialization module."""

from typing import Any, Dict


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
