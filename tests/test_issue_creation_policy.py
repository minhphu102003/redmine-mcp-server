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
    async def test_defaults_done_ratio_status_and_priority_when_missing(self):
        mock_redmine = Mock()
        mock_redmine.issue_status.all.return_value = [
            _make_status(1, "New"),
            _make_status(2, "In Progress"),
        ]
        mock_redmine.issue_priority.all.return_value = [
            _make_priority(2, "Normal"),
            _make_priority(3, "High"),
        ]
        mock_redmine.issue.create.return_value = _make_issue()

        with patch("redmine_mcp_server.redmine_handler.redmine", mock_redmine):
            with patch.dict(
                os.environ,
                {"REDMINE_STRICT_ISSUE_CREATION_INPUTS": "false"},
                clear=False,
            ):
                await redmine_handler.create_redmine_issue(
                    project_id=1,
                    subject="[api] create endpoint",
                    description="desc",
                    fields={"tracker_id": 1},
                )

        called_kwargs = mock_redmine.issue.create.call_args.kwargs
        assert called_kwargs["done_ratio"] == 0
        assert called_kwargs["status_id"] == 1
        assert called_kwargs["priority_id"] == 2

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
                fields={},
            )

        assert "error" in result
        assert "[module name] task name" in result["error"]

    @pytest.mark.asyncio
    async def test_strict_mode_requires_manual_fields(self):
        with patch.dict(
            os.environ,
            {"REDMINE_STRICT_ISSUE_CREATION_INPUTS": "true"},
            clear=False,
        ):
            result = await redmine_handler.create_redmine_issue(
                project_id=1,
                subject="[api] create endpoint",
                description="desc",
                fields={"tracker_id": 1},
            )

        assert "error" in result
        assert "missing_fields" in result
        assert "assigned_to_id" in result["missing_fields"]
