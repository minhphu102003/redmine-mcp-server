"""Undecorated issue-relation tool implementations.

Redmine issue relations model dependencies between issues:
- ``precedes`` / ``follows`` — issue A precedes issue B (A must be done first),
  with an optional ``delay`` in days.
- ``blocks`` / ``blocked`` — issue A blocks issue B.
- ``relates`` — generic relation.
- ``duplicates`` / ``duplicated``, ``copied_to`` / ``copied_from``.

Redmine stores a single row per relation; complementary types (follows, blocked,
duplicated) are computed automatically on the other side.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, Mapping, Optional

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

ALLOWED_RELATION_TYPES = frozenset(
    {
        "relates",
        "duplicates",
        "duplicated",
        "blocks",
        "blocked",
        "precedes",
        "follows",
        "copied_to",
        "copied_from",
    }
)


async def create_redmine_issue_relation_impl(
    issue_id: int,
    issue_to_id: int,
    relation_type: str,
    delay: Optional[int] = None,
    *,
    is_read_only_mode: Callable[[], bool],
    read_only_error: Mapping[str, Any],
    get_client: Callable[[], Any],
    wrap_content: Callable[[Any], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Create an issue relation (dependency) between two Redmine issues."""
    if is_read_only_mode():
        return dict(read_only_error)

    normalized_type = (relation_type or "").strip().lower()
    if normalized_type not in ALLOWED_RELATION_TYPES:
        return {
            "error": (
                f"Invalid relation_type '{relation_type}'. Allowed values: "
                + ", ".join(sorted(ALLOWED_RELATION_TYPES))
                + "."
            )
        }

    if issue_id == issue_to_id:
        return {"error": "issue_id and issue_to_id must be different issues."}

    try:
        client = get_client()
        try:
            from_issue = await asyncio.to_thread(client.issue.get, issue_id)
            to_issue = await asyncio.to_thread(client.issue.get, issue_to_id)
        except Exception as e:
            return handle_error(
                e,
                "resolving relation endpoints",
                {
                    "resource_type": "issue relation",
                    "resource_id": issue_id,
                    "issue_to_id": issue_to_id,
                },
            )

        params: Dict[str, Any] = {
            "issue_id": issue_id,
            "issue_to_id": issue_to_id,
            "relation_type": normalized_type,
        }
        if delay is not None:
            params["delay"] = delay

        relation = await asyncio.to_thread(client.issue_relation.create, **params)

        from_subject = getattr(from_issue, "subject", "")
        to_subject = getattr(to_issue, "subject", "")
        return {
            "success": True,
            "relation": {
                "id": getattr(relation, "id", None),
                "issue_id": issue_id,
                "issue_to_id": issue_to_id,
                "relation_type": getattr(relation, "relation_type", None),
                "delay": getattr(relation, "delay", None),
            },
            "issues": {
                "from": {"id": issue_id, "subject": wrap_content(from_subject)},
                "to": {"id": issue_to_id, "subject": wrap_content(to_subject)},
            },
        }
    except Exception as e:
        return handle_error(
            e,
            f"creating relation {issue_id} -> {issue_to_id}",
            {
                "resource_type": "issue relation",
                "resource_id": issue_id,
                "issue_to_id": issue_to_id,
            },
        )


async def delete_redmine_issue_relation_impl(
    relation_id: int,
    *,
    is_read_only_mode: Callable[[], bool],
    read_only_error: Mapping[str, Any],
    get_client: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Delete an issue relation from Redmine."""
    if is_read_only_mode():
        return dict(read_only_error)

    try:
        client = get_client()
        await asyncio.to_thread(client.issue_relation.delete, relation_id)
        return {
            "success": True,
            "relation_id": relation_id,
            "message": f"Issue relation {relation_id} deleted successfully.",
        }
    except Exception as e:
        return handle_error(
            e,
            f"deleting issue relation {relation_id}",
            {"resource_type": "issue relation", "resource_id": relation_id},
        )
