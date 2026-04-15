"""Tests for issue status/workflow MCP tools."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.redmine_handler import (  # noqa: E402
    get_redmine_issue_allowed_statuses,
    get_redmine_project_workflow,
    list_redmine_issue_statuses,
)


class TestIssueWorkflowTools:
    @pytest.fixture
    def mock_redmine(self):
        with patch("redmine_mcp_server.redmine_handler.redmine") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_list_redmine_issue_statuses(self, mock_redmine):
        s1 = Mock(id=1, name="New", is_closed=False)
        s2 = Mock(id=5, name="Closed", is_closed=True)
        mock_redmine.issue_status.all.return_value = [s1, s2]

        result = await list_redmine_issue_statuses()

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["is_closed"] is False
        assert result[1]["id"] == 5
        assert result[1]["is_closed"] is True

    @pytest.mark.asyncio
    async def test_list_redmine_issue_statuses_error_shape(self, mock_redmine):
        mock_redmine.issue_status.all.side_effect = Exception("boom")

        result = await list_redmine_issue_statuses()

        assert isinstance(result, dict)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_redmine_issue_allowed_statuses(self, mock_redmine):
        issue = Mock()
        issue.status = Mock(id=2, name="In Progress")
        issue.allowed_statuses = [
            Mock(id=3, name="Resolved", is_closed=False),
            Mock(id=5, name="Closed", is_closed=True),
        ]
        mock_redmine.issue.get.return_value = issue

        result = await get_redmine_issue_allowed_statuses(123)

        assert result["issue_id"] == 123
        assert result["current_status"]["id"] == 2
        assert result["count"] == 2
        assert [s["id"] for s in result["allowed_statuses"]] == [3, 5]
        mock_redmine.issue.get.assert_called_once_with(123, include="allowed_statuses")

    @pytest.mark.asyncio
    async def test_get_redmine_project_workflow(self, mock_redmine):
        issue_1 = Mock(id=101)
        issue_2 = Mock(id=102)
        mock_redmine.issue.filter.return_value = [issue_1, issue_2]

        detailed_1 = Mock()
        detailed_1.status = Mock(id=1, name="New")
        detailed_1.allowed_statuses = [Mock(id=2, name="In Progress", is_closed=False)]

        detailed_2 = Mock()
        detailed_2.status = Mock(id=2, name="In Progress")
        detailed_2.allowed_statuses = [
            Mock(id=3, name="Resolved", is_closed=False),
            Mock(id=5, name="Closed", is_closed=True),
        ]

        mock_redmine.issue.get.side_effect = [detailed_1, detailed_2]

        result = await get_redmine_project_workflow(project_id=7, sample_limit=500)

        assert result["project_id"] == 7
        assert result["sample_limit"] == 100
        assert result["sampled_issues"] == 2
        assert len(result["workflow_by_current_status"]) == 2
        assert result["request_pattern"]["total_request_count"] == 3
        assert result["request_pattern"]["detail_fetch_concurrency"] == 10

        call_kwargs = mock_redmine.issue.filter.call_args[1]
        assert call_kwargs["project_id"] == 7
        assert call_kwargs["limit"] == 100
        assert call_kwargs["status_id"] == "*"

    @pytest.mark.asyncio
    async def test_get_redmine_project_workflow_default_sample_limit(
        self, mock_redmine
    ):
        mock_redmine.issue.filter.return_value = []

        result = await get_redmine_project_workflow(project_id=7)

        assert result["sample_limit"] == 25
        call_kwargs = mock_redmine.issue.filter.call_args[1]
        assert call_kwargs["limit"] == 25

    @pytest.mark.asyncio
    async def test_get_redmine_project_workflow_handles_none_ids(self, mock_redmine):
        mock_redmine.issue.filter.return_value = [Mock(id=101), Mock(id=102)]

        detailed_1 = Mock()
        detailed_1.status = Mock(id=None, name="Unknown")
        detailed_1.allowed_statuses = [Mock(id=None, name="No ID", is_closed=False)]

        detailed_2 = Mock()
        detailed_2.status = Mock(id=None, name="Unknown")
        detailed_2.allowed_statuses = [Mock(id=None, name="No ID", is_closed=False)]

        mock_redmine.issue.get.side_effect = [detailed_1, detailed_2]

        result = await get_redmine_project_workflow(project_id=7)

        assert len(result["workflow_by_current_status"]) == 1
        assert result["workflow_by_current_status"][0]["current_status"]["id"] is None
        assert len(result["workflow_by_current_status"][0]["allowed_statuses"]) == 1

    @pytest.mark.asyncio
    async def test_get_redmine_project_workflow_skips_issue_without_id(
        self, mock_redmine
    ):
        mock_redmine.issue.filter.return_value = [object(), Mock(id=102)]

        detailed = Mock()
        detailed.status = Mock(id=2, name="In Progress")
        detailed.allowed_statuses = [Mock(id=3, name="Resolved", is_closed=False)]
        mock_redmine.issue.get.return_value = detailed

        result = await get_redmine_project_workflow(project_id=7)

        assert result["sampled_issues"] == 2
        assert result["request_pattern"]["detail_request_count"] == 1
        assert result["request_pattern"]["total_request_count"] == 2
        mock_redmine.issue.get.assert_called_once_with(102, include="allowed_statuses")
