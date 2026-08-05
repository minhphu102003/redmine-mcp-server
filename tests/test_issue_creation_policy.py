"""Tests for create issue policy defaults and strict validation mode."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import redmine_handler  # noqa: E402


def _make_status(status_id: int, name: str) -> Mock:
    status = Mock()
    status.id = status_id
    status.name = name
    return status


def _make_priority(priority_id: int, name: str) -> Mock:
    priority = Mock()
    priority.id = priority_id
    priority.name = name
    return priority


def _make_issue(issue_id: int = 100) -> Mock:
    issue = Mock()
    issue.id = issue_id
    issue.subject = "[api] create endpoint"
    issue.description = "desc"
    issue.project = Mock(id=1, name="Project")
    issue.status = Mock(id=1, name="New")
    issue.priority = Mock(id=2, name="Normal")
    issue.author = Mock(id=10, name="Author")
    issue.assigned_to = None
    issue.created_on = None
    issue.updated_on = None
    return issue


class TestIssueCreationPolicy:
    @pytest.mark.asyncio
    async def test_passes_required_fields_through_to_create_call(self):
        mock_redmine = Mock()
        mock_redmine.issue.create.return_value = _make_issue()

        with patch("redmine_mcp_server.redmine_handler.redmine", mock_redmine):
            await redmine_handler.create_redmine_issue(
                project_id=1,
                subject="[api] create endpoint",
                description="desc",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                fields={},
            )

        called_kwargs = mock_redmine.issue.create.call_args.kwargs
        assert called_kwargs["tracker_id"] == 1
        assert called_kwargs["priority_id"] == 3
        assert called_kwargs["status_id"] == 1
        assert called_kwargs["assigned_to_id"] == 80
        assert called_kwargs["start_date"] == "2026-08-05"
        assert called_kwargs["due_date"] == "2026-08-12"
        assert called_kwargs["estimated_hours"] == 2.0
        assert called_kwargs["done_ratio"] == 0

    @pytest.mark.asyncio
    async def test_strict_mode_rejects_subject_without_module_prefix(self):
        with patch.dict(
            os.environ,
            {"REDMINE_STRICT_ISSUE_CREATION_INPUTS": "true"},
            clear=False,
        ):
            result = await redmine_handler.create_redmine_issue(
                project_id=1,
                subject="Create endpoint",
                description="desc",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                fields={},
            )

        assert "error" in result
        assert "[module name] task name" in result["error"]
