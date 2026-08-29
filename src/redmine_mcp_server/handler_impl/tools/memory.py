"""Undecorated memory tool implementations."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional


async def get_user_memory_impl(
    key: str,
    *,
    get_entry: Callable[[str], Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Retrieve a specific memory entry by key."""
    entry = get_entry(key)
    if entry is None:
        return {"error": f"No memory entry found for key '{key}'."}
    return {"key": key, "value": entry}


async def set_user_memory_impl(
    key: str,
    value: Dict[str, Any],
    *,
    set_entry: Callable[[str, Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any]:
    """Store a memory entry."""
    return set_entry(key, value)


async def delete_user_memory_impl(
    key: str,
    *,
    delete_entry: Callable[[str], Dict[str, Any]],
) -> Dict[str, Any]:
    """Delete a memory entry."""
    return delete_entry(key)


async def list_user_memory_impl(
    *,
    list_keys: Callable[[], List[str]],
    get_user_hash: Callable[[], Optional[str]],
) -> Dict[str, Any]:
    """List all memory keys for the current user."""
    keys = list_keys()
    user_hash = get_user_hash()
    return {
        "user_hash": user_hash,
        "keys": keys,
        "count": len(keys),
    }
