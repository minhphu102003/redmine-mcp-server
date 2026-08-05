"""
Tests for logging time entries via update_redmine_issue.

Covers the optional spent_hours/activity_id/time_comments/spent_on parameters
that create a time entry on the issue after a successful update.
"""

import os
import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from redmine_mcp_server.redmine_handler import update_redmine_issue


@pytest.fixture
def mock_redmine_issue():
    """Create a mock Redmine issue object."""
    mock_issue = Mock()
    mock_issue.id = 123
    mock_issue.subject = "Test Issue Subject"
    mock_issue.description = "Test issue description"

    mock_project = Mock()
    mock_project.id = 1
    mock_project.name = "Test Project"
    mock_issue.project = mock_project

    mock_status = Mock()
    mock_status.id = 1
    mock_status.name = "New"
    mock_issue.status = mock_status

    mock_priority = Mock()
    mock_priority.id = 2
    mock_priority.name = "Normal"
    mock_issue.priority = mock_priority

    mock_author = Mock()
    mock_author.id = 1
    mock_author.name = "Test Author"
    mock_issue.author = mock_author

    mock_assigned = Mock()
    mock_assigned.id = 2
    mock_assigned.name = "Test Assignee"
    mock_issue.assigned_to = mock_assigned

    mock_tracker = Mock()
    mock_tracker.id = 1
    mock_tracker.name = "Task"
    mock_issue.tracker = mock_tracker

    mock_issue.category = None
    mock_issue.fixed_version = None
    mock_issue.parent = None
    mock_issue.start_date = "2024-01-01"
    mock_issue.due_date = None
    mock_issue.done_ratio = 0
    mock_issue.estimated_hours = None
    mock_issue.created_on = datetime(2024, 1, 1, 10, 0, 0)
    mock_issue.updated_on = datetime(2024, 1, 2, 10, 0, 0)
    mock_issue.custom_fields = []
    return mock_issue


@pytest.fixture
def mock_time_entry():
    """Create a mock Redmine time entry object."""
    entry = Mock()
    entry.id = 55
    entry.hours = 1.5
    entry.comments = "Worked on the fix"
    entry.spent_on = "2024-01-02"

    user = Mock()
    user.id = 1
    user.name = "Test Author"
    entry.user = user

    project = Mock()
    project.id = 1
    project.name = "Test Project"
    entry.project = project

    issue = Mock()
    issue.id = 123
    entry.issue = issue

    activity = Mock()
    activity.id = 9
    activity.name = "Development"
    entry.activity = activity

    entry.created_on = datetime(2024, 1, 2, 10, 0, 0)
    entry.updated_on = datetime(2024, 1, 2, 10, 0, 0)
    return entry


class TestUpdateIssueLogTime:
    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_update_with_log_time_success(
        self, mock_redmine, mock_redmine_issue, mock_time_entry
    ):
        """Issue update succeeds and a time entry is logged on the issue."""
        mock_redmine.issue.update.return_value = True
        mock_redmine.issue.get.return_value = mock_redmine_issue
        mock_redmine.time_entry.create.return_value = mock_time_entry

        result = await update_redmine_issue(
            123,
            {"subject": "New"},
            spent_hours=1.5,
            activity_id=9,
            time_comments="Worked on the fix",
            spent_on="2024-01-02",
        )

        assert result["id"] == 123
        assert result["subject"] == "Test Issue Subject"
        assert result["time_entry"]["id"] == 55
        assert result["time_entry"]["hours"] == 1.5
        assert "time_entry_error" not in result
        mock_redmine.issue.update.assert_called_once_with(123, subject="New")
        mock_redmine.time_entry.create.assert_called_once_with(
            hours=1.5,
            issue_id=123,
            activity_id=9,
            comments="Worked on the fix",
            spent_on="2024-01-02",
        )

    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_log_time_negative_hours_rejected(
        self, mock_redmine, mock_redmine_issue
    ):
        """Non-positive spent_hours is rejected before any update happens."""
        result = await update_redmine_issue(123, {"subject": "New"}, spent_hours=0)

        assert "spent_hours must be a positive number" in result["error"]
        mock_redmine.issue.update.assert_not_called()
        mock_redmine.time_entry.create.assert_not_called()

    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_issue_update_failure_skips_time_logging(
        self, mock_redmine, mock_redmine_issue
    ):
        """When the issue update fails, no time entry is created."""
        mock_redmine.issue.update.side_effect = Exception("Boom")

        result = await update_redmine_issue(123, {"subject": "New"}, spent_hours=1.5)

        assert "error" in result
        mock_redmine.issue.update.assert_called_once()
        mock_redmine.time_entry.create.assert_not_called()

    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_time_log_failure_keeps_issue_update(
        self, mock_redmine, mock_redmine_issue
    ):
        """Time logging failure keeps the issue update and reports the error."""
        mock_redmine.issue.update.return_value = True
        mock_redmine.issue.get.return_value = mock_redmine_issue
        mock_redmine.time_entry.create.side_effect = Exception("Boom")

        result = await update_redmine_issue(123, {"subject": "New"}, spent_hours=1.5)

        assert result["id"] == 123
        assert "time_entry_error" in result
        assert result["time_entry_error"] is True
        assert "error" in result["time_entry"]
        mock_redmine.issue.update.assert_called_once()
        mock_redmine.time_entry.create.assert_called_once()

    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_read_only_blocks_update_and_logging(
        self, mock_redmine, mock_redmine_issue
    ):
        """Read-only mode blocks both the update and the time logging."""
        with patch.dict(os.environ, {"REDMINE_MCP_READ_ONLY": "true"}, clear=False):
            result = await update_redmine_issue(
                123, {"subject": "New"}, spent_hours=1.5
            )

        assert "read-only" in result["error"].lower()
        mock_redmine.issue.update.assert_not_called()
        mock_redmine.time_entry.create.assert_not_called()

    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_no_spent_hours_unchanged_behavior(
        self, mock_redmine, mock_redmine_issue
    ):
        """Without spent_hours the result is unchanged and has no time_entry key."""
        mock_redmine.issue.update.return_value = True
        mock_redmine.issue.get.return_value = mock_redmine_issue

        result = await update_redmine_issue(123, {"subject": "New"})

        assert result["id"] == 123
        assert "time_entry" not in result
        mock_redmine.issue.update.assert_called_once_with(123, subject="New")
        mock_redmine.time_entry.create.assert_not_called()

    @pytest.mark.asyncio
    @patch("redmine_mcp_server.redmine_handler.redmine")
    async def test_log_time_only_with_empty_fields(
        self, mock_redmine, mock_redmine_issue, mock_time_entry
    ):
        """Empty fields with spent_hours skips the update and only logs time."""
        mock_redmine.issue.update.return_value = True
        mock_redmine.issue.get.return_value = mock_redmine_issue
        mock_redmine.time_entry.create.return_value = mock_time_entry

        result = await update_redmine_issue(123, {}, spent_hours=2.0)

        assert result["id"] == 123
        assert result["time_entry"]["id"] == 55
        mock_redmine.issue.update.assert_not_called()
        mock_redmine.time_entry.create.assert_called_once_with(hours=2.0, issue_id=123)
