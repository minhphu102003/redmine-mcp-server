"""Tests for consolidated MCP tools."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import redmine_handler  # noqa: E402


class TestManageTimeEntries:
    @pytest.mark.asyncio
    async def test_list_action(self):
        payload = [{"id": 1, "hours": 2.0}]
        with patch.object(
            redmine_handler,
            "list_time_entries",
            AsyncMock(return_value=payload),
        ):
            result = await redmine_handler.manage_time_entries(
                action="list",
                project_id=7,
            )

        assert result["action"] == "list"
        assert result["data"] == payload

    @pytest.mark.asyncio
    async def test_create_requires_hours(self):
        result = await redmine_handler.manage_time_entries(action="create")
        assert "error" in result
        assert "hours is required" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_action(self):
        payload = {"success": True, "time_entry_id": 55}
        mock_delete = AsyncMock(return_value=payload)
        with patch.object(
            redmine_handler,
            "delete_time_entry",
            mock_delete,
        ):
            result = await redmine_handler.manage_time_entries(
                action="delete",
                time_entry_id=55,
            )

        assert result["action"] == "delete"
        assert result["data"] == payload
        mock_delete.assert_awaited_once_with(time_entry_id=55)

    @pytest.mark.asyncio
    async def test_delete_requires_time_entry_id(self):
        result = await redmine_handler.manage_time_entries(action="delete")
        assert "error" in result
        assert "time_entry_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_invalid_action_message_includes_delete(self):
        result = await redmine_handler.manage_time_entries(action="nope")
        assert "error" in result
        assert "delete" in result["error"]
