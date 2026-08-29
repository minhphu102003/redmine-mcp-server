"""
Server-side memory store for user-scoped JSON data.

Stores per-user memory as JSON files keyed by a hash of their
authentication credentials. Supports dynamic auth mode only;
legacy/oauth modes return None (devs use local files).
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MEMORY_BASE_DIR: Optional[Path] = None


def _get_memory_dir() -> Path:
    """Return (and lazily create) the memory storage directory."""
    global _MEMORY_BASE_DIR
    if _MEMORY_BASE_DIR is None:
        data_dir = os.getenv("REDMINE_MCP_DATA_DIR", "")
        if data_dir:
            _MEMORY_BASE_DIR = Path(data_dir) / "memory"
        else:
            _MEMORY_BASE_DIR = Path.cwd() / "data" / "memory"
        _MEMORY_BASE_DIR.mkdir(parents=True, exist_ok=True)
    return _MEMORY_BASE_DIR


def compute_user_hash(*parts: str) -> str:
    """Compute a stable 16-char hex hash from identity parts."""
    combined = "|".join(p.strip() for p in parts if p)
    digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    return digest[:16]


def _resolve_user_hash() -> Optional[str]:
    """Resolve the current user's identity hash from ContextVars.

    Only works in dynamic auth mode (X-Redmine-URL + X-Redmine-API-Key).
    Returns None for legacy/oauth modes.
    """
    try:
        from .dynamic_auth_middleware import get_dynamic_config

        dyn_url, dyn_key = get_dynamic_config()
        logger.warning(
            "DEBUG memory_store._resolve_user_hash: url=%r key_present=%s",
            dyn_url,
            bool(dyn_key),
        )
        if dyn_url and dyn_key:
            return compute_user_hash(dyn_url, dyn_key)
    except ImportError:
        logger.exception("DEBUG memory_store: import error")
    except Exception:
        logger.exception("DEBUG memory_store: unexpected error in _resolve_user_hash")

    return None


def _user_file_path(user_hash: str) -> Path:
    """Return the JSON file path for a given user hash."""
    return _get_memory_dir() / f"{user_hash}.json"


def _load_user_file(user_hash: str) -> Dict[str, Any]:
    """Load the full memory file for a user. Returns empty structure if missing."""
    path = _user_file_path(user_hash)
    if not path.exists():
        now = datetime.now(timezone.utc).isoformat()
        return {
            "version": 1,
            "identity_hash": user_hash,
            "created_at": now,
            "updated_at": now,
            "entries": {},
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load memory file %s: %s", path, e)
        now = datetime.now(timezone.utc).isoformat()
        return {
            "version": 1,
            "identity_hash": user_hash,
            "created_at": now,
            "updated_at": now,
            "entries": {},
        }


def _save_user_file(user_hash: str, data: Dict[str, Any]) -> None:
    """Atomically save the memory file for a user."""
    path = _user_file_path(user_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(path)
    except OSError as e:
        logger.error("Failed to save memory file %s: %s", path, e)
        tmp_path.unlink(missing_ok=True)
        raise


# --- Public API ---


def get_entry(key: str) -> Optional[Dict[str, Any]]:
    """Get a specific memory entry for the current user."""
    user_hash = _resolve_user_hash()
    if user_hash is None:
        return None
    data = _load_user_file(user_hash)
    return data.get("entries", {}).get(key)


def set_entry(key: str, value: Dict[str, Any]) -> Dict[str, Any]:
    """Set a memory entry for the current user."""
    user_hash = _resolve_user_hash()
    if user_hash is None:
        raise RuntimeError("Cannot determine user identity for memory storage.")
    data = _load_user_file(user_hash)
    data.setdefault("entries", {})[key] = value
    _save_user_file(user_hash, data)
    return {
        "status": "ok",
        "key": key,
        "updated_at": data["updated_at"],
    }


def delete_entry(key: str) -> Dict[str, Any]:
    """Delete a memory entry for the current user."""
    user_hash = _resolve_user_hash()
    if user_hash is None:
        raise RuntimeError("Cannot determine user identity for memory storage.")
    data = _load_user_file(user_hash)
    entries = data.get("entries", {})
    if key not in entries:
        return {"status": "not_found", "key": key}
    del entries[key]
    _save_user_file(user_hash, data)
    return {"status": "deleted", "key": key}


def list_keys() -> List[str]:
    """List all memory keys for the current user."""
    user_hash = _resolve_user_hash()
    if user_hash is None:
        return []
    data = _load_user_file(user_hash)
    return sorted(data.get("entries", {}).keys())


def get_user_hash() -> Optional[str]:
    """Return the current user's hash (for diagnostics)."""
    return _resolve_user_hash()
