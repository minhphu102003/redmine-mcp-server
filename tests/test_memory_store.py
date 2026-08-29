"""Tests for server-side memory store."""

import json
import importlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


# Mock the dynamic_auth_middleware before importing memory_store
@pytest.fixture(autouse=True)
def mock_dynamic_auth():
    """Mock dynamic auth to return test credentials."""
    with patch(
        "redmine_mcp_server.memory_store._resolve_user_hash",
        return_value="test_user_hash_123",
    ):
        yield


@pytest.fixture
def memory_dir(tmp_path):
    """Provide a temporary memory directory."""
    with patch("redmine_mcp_server.memory_store._MEMORY_BASE_DIR", tmp_path):
        yield tmp_path


def _import_memory_impl():
    """Import memory implementation directly without going through __init__."""
    import importlib.util
    import sys

    # Get the path to memory.py
    module_path = (
        Path(__file__).parent.parent
        / "src"
        / "redmine_mcp_server"
        / "handler_impl"
        / "tools"
        / "memory.py"
    )

    spec = importlib.util.spec_from_file_location(
        "redmine_mcp_server.handler_impl.tools.memory",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestComputeUserHash:
    def test_deterministic(self):
        """Same input produces same hash."""
        from redmine_mcp_server.memory_store import compute_user_hash

        hash1 = compute_user_hash("https://redmine.example.com", "api_key_123")
        hash2 = compute_user_hash("https://redmine.example.com", "api_key_123")
        assert hash1 == hash2

    def test_different_inputs(self):
        """Different inputs produce different hashes."""
        from redmine_mcp_server.memory_store import compute_user_hash

        hash1 = compute_user_hash("https://redmine1.example.com", "key1")
        hash2 = compute_user_hash("https://redmine2.example.com", "key2")
        assert hash1 != hash2

    def test_length(self):
        """Hash is 16 characters."""
        from redmine_mcp_server.memory_store import compute_user_hash

        h = compute_user_hash("test", "value")
        assert len(h) == 16

    def test_hex_characters(self):
        """Hash contains only hex characters."""
        from redmine_mcp_server.memory_store import compute_user_hash

        h = compute_user_hash("test", "value")
        assert all(c in "0123456789abcdef" for c in h)


class TestMemoryStore:
    def test_get_entry_returns_none_when_no_user(self, memory_dir):
        """get_entry returns None when user hash cannot be resolved."""
        from redmine_mcp_server.memory_store import get_entry

        with patch(
            "redmine_mcp_server.memory_store._resolve_user_hash",
            return_value=None,
        ):
            result = get_entry(".redmine")
            assert result is None

    def test_set_and_get_roundtrip(self, memory_dir):
        """Set then get returns same data."""
        from redmine_mcp_server.memory_store import set_entry, get_entry

        test_data = {
            "version": 1,
            "project": {"id": 12, "name": "Test Project"},
            "fetched_at": "2026-08-29T00:00:00Z",
        }

        set_entry(".redmine", test_data)
        result = get_entry(".redmine")

        assert result is not None
        assert result["version"] == 1
        assert result["project"]["id"] == 12
        assert result["project"]["name"] == "Test Project"

    def test_delete_entry(self, memory_dir):
        """Delete removes the key."""
        from redmine_mcp_server.memory_store import set_entry, delete_entry, get_entry

        set_entry(".redmine", {"test": True})
        result = delete_entry(".redmine")

        assert result["status"] == "deleted"
        assert get_entry(".redmine") is None

    def test_delete_entry_not_found(self, memory_dir):
        """Deleting nonexistent key returns not_found."""
        from redmine_mcp_server.memory_store import delete_entry

        result = delete_entry("nonexistent")
        assert result["status"] == "not_found"

    def test_list_keys(self, memory_dir):
        """Lists all stored keys."""
        from redmine_mcp_server.memory_store import set_entry, list_keys

        set_entry(".redmine", {"test": True})
        set_entry(".google-sheets", {"test": True})

        keys = list_keys()
        assert ".google-sheets" in keys
        assert ".redmine" in keys
        assert len(keys) == 2

    def test_list_keys_empty(self, memory_dir):
        """List keys returns empty list when no entries."""
        from redmine_mcp_server.memory_store import list_keys

        keys = list_keys()
        assert keys == []

    def test_user_file_created(self, memory_dir):
        """User file is created on first write."""
        from redmine_mcp_server.memory_store import set_entry

        set_entry(".redmine", {"test": True})

        user_file = memory_dir / "test_user_hash_123.json"
        assert user_file.exists()

    def test_user_file_valid_json(self, memory_dir):
        """User file contains valid JSON."""
        from redmine_mcp_server.memory_store import set_entry

        set_entry(".redmine", {"test": True})

        user_file = memory_dir / "test_user_hash_123.json"
        with open(user_file, "r") as f:
            data = json.load(f)

        assert data["version"] == 1
        assert data["identity_hash"] == "test_user_hash_123"
        assert "created_at" in data
        assert "updated_at" in data
        assert ".redmine" in data["entries"]

    def test_overwrite_existing_entry(self, memory_dir):
        """Overwrite existing entry with new value."""
        from redmine_mcp_server.memory_store import set_entry, get_entry

        set_entry(".redmine", {"version": 1, "old": True})
        set_entry(".redmine", {"version": 1, "new": True})

        result = get_entry(".redmine")
        assert result["new"] is True
        assert "old" not in result

    def test_multiple_keys_independent(self, memory_dir):
        """Different keys are independent."""
        from redmine_mcp_server.memory_store import set_entry, get_entry

        set_entry(".redmine", {"type": "redmine"})
        set_entry(".google-sheets", {"type": "sheets"})

        assert get_entry(".redmine")["type"] == "redmine"
        assert get_entry(".google-sheets")["type"] == "sheets"

    def test_set_entry_returns_status(self, memory_dir):
        """set_entry returns status dict with timestamp."""
        from redmine_mcp_server.memory_store import set_entry

        result = set_entry(".redmine", {"test": True})

        assert result["status"] == "ok"
        assert result["key"] == ".redmine"
        assert "updated_at" in result

    def test_get_user_hash(self, memory_dir):
        """get_user_hash returns current user hash."""
        from redmine_mcp_server.memory_store import get_user_hash

        result = get_user_hash()
        assert result == "test_user_hash_123"


class TestMemoryTools:
    @pytest.mark.asyncio
    async def test_get_user_memory_impl_found(self):
        """get_user_memory_impl returns value when entry exists."""
        memory_mod = _import_memory_impl()

        mock_get = MagicMock(return_value={"test": True})
        result = await memory_mod.get_user_memory_impl(".redmine", get_entry=mock_get)

        assert result["key"] == ".redmine"
        assert result["value"]["test"] is True

    @pytest.mark.asyncio
    async def test_get_user_memory_impl_not_found(self):
        """get_user_memory_impl returns error when entry not found."""
        memory_mod = _import_memory_impl()

        mock_get = MagicMock(return_value=None)
        result = await memory_mod.get_user_memory_impl(
            "nonexistent", get_entry=mock_get
        )

        assert "error" in result
        assert "nonexistent" in result["error"]

    @pytest.mark.asyncio
    async def test_set_user_memory_impl(self):
        """set_user_memory_impl stores value."""
        memory_mod = _import_memory_impl()

        mock_set = MagicMock(return_value={"status": "ok", "key": ".redmine"})
        result = await memory_mod.set_user_memory_impl(
            ".redmine", {"test": True}, set_entry=mock_set
        )

        mock_set.assert_called_once_with(".redmine", {"test": True})
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_user_memory_impl(self):
        """delete_user_memory_impl deletes entry."""
        memory_mod = _import_memory_impl()

        mock_delete = MagicMock(return_value={"status": "deleted"})
        result = await memory_mod.delete_user_memory_impl(
            ".redmine", delete_entry=mock_delete
        )

        mock_delete.assert_called_once_with(".redmine")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_list_user_memory_impl(self):
        """list_user_memory_impl returns keys and hash."""
        memory_mod = _import_memory_impl()

        mock_list = MagicMock(return_value=[".redmine", ".google-sheets"])
        mock_hash = MagicMock(return_value="abc123")

        result = await memory_mod.list_user_memory_impl(
            list_keys=mock_list, get_user_hash=mock_hash
        )

        assert result["user_hash"] == "abc123"
        assert ".redmine" in result["keys"]
        assert ".google-sheets" in result["keys"]
        assert result["count"] == 2


# Tests for the MCP tool wrappers' error-handling live in
# tests/test_memory_tool_wrappers.py — that file is a standalone
# test because redmine_handler.py imports `redminelib` which is not
# available in this test environment.
