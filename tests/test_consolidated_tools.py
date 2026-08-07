"""Tests for consolidated MCP tools."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import redmine_handler  # noqa: E402


class TestGetIssueWorkflowContext:
    @pytest.mark.asyncio
    async def test_statuses_mode(self):
        payload = [{"id": 1, "name": "New", "is_closed": False}]
        with patch.object(
            redmine_handler,
            "list_redmine_issue_statuses",
            AsyncMock(return_value=payload),
        ):
            result = await redmine_handler.get_issue_workflow_context(mode="statuses")

        assert result["mode"] == "statuses"
        assert result["data"] == payload

    @pytest.mark.asyncio
    async def test_statuses_mode_error_payload(self):
        payload = {"error": "Authentication failed"}
        with patch.object(
            redmine_handler,
            "list_redmine_issue_statuses",
            AsyncMock(return_value=payload),
        ):
            result = await redmine_handler.get_issue_workflow_context(mode="statuses")

        assert result["mode"] == "statuses"
        assert result["data"]["error"] == "Authentication failed"

    @pytest.mark.asyncio
    async def test_transition_check_allowed(self):
        issue_payload = {
            "current_status": {"id": 1, "name": "New"},
            "allowed_statuses": [
                {"id": 2, "name": "In Progress", "is_closed": False},
                {"id": 3, "name": "Resolved", "is_closed": False},
            ],
        }
        with patch.object(
            redmine_handler,
            "get_redmine_issue_allowed_statuses",
            AsyncMock(return_value=issue_payload),
        ):
            result = await redmine_handler.get_issue_workflow_context(
                mode="transition_check",
                issue_id=123,
                target_status_name="resolved",
            )

        assert result["mode"] == "transition_check"
        assert result["allowed"] is True
        assert result["matched_status"]["id"] == 3

    @pytest.mark.asyncio
    async def test_transition_check_allowed_with_wrapped_status_name(self):
        issue_payload = {
            "current_status": {"id": 1, "name": "New"},
            "allowed_statuses": [
                {
                    "id": 3,
                    "name": (
                        "<insecure-content-abc123>\nResolved\n"
                        "</insecure-content-abc123>"
                    ),
                    "is_closed": False,
                }
            ],
        }
        with patch.object(
            redmine_handler,
            "get_redmine_issue_allowed_statuses",
            AsyncMock(return_value=issue_payload),
        ):
            result = await redmine_handler.get_issue_workflow_context(
                mode="transition_check",
                issue_id=123,
                target_status_name="resolved",
            )

        assert result["mode"] == "transition_check"
        assert result["allowed"] is True
        assert result["matched_status"]["id"] == 3

    @pytest.mark.asyncio
    async def test_transition_check_propagates_issue_lookup_error(self):
        with patch.object(
            redmine_handler,
            "get_redmine_issue_allowed_statuses",
            AsyncMock(return_value={"error": "Resource not found"}),
        ):
            result = await redmine_handler.get_issue_workflow_context(
                mode="transition_check",
                issue_id=404,
                target_status_name="resolved",
            )

        assert result["mode"] == "transition_check"
        assert result["error"] == "Resource not found"


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
