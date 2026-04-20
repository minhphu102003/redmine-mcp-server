"""Tests for project metadata lookup tools (trackers and issue categories)."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.redmine_handler import (  # noqa: E402
    list_project_issue_categories,
    list_project_trackers,
)


class TestListProjectTrackers:
    """Unit tests for list_project_trackers tool."""

    @pytest.fixture
    def mock_redmine(self):
        with patch("redmine_mcp_server.redmine_handler.redmine") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_list_project_trackers_success(self, mock_redmine):
        tracker_bug = Mock()
        tracker_bug.id = 1
        tracker_bug.name = "Bug"

        tracker_task = Mock()
        tracker_task.id = 2
        tracker_task.name = "Task"

        project = Mock()
        project.trackers = [tracker_bug, tracker_task]
        mock_redmine.project.get.return_value = project

        result = await list_project_trackers(project_id=10)

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert "Bug" in result[0]["name"]
        mock_redmine.project.get.assert_called_once_with(10, include="trackers")

    @pytest.mark.asyncio
    async def test_list_project_trackers_empty(self, mock_redmine):
        project = Mock()
        project.trackers = []
        mock_redmine.project.get.return_value = project

        result = await list_project_trackers(project_id="core")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_project_trackers_error(self, mock_redmine):
        mock_redmine.project.get.side_effect = Exception("Boom")

        result = await list_project_trackers(project_id=10)

        assert len(result) == 1
        assert "error" in result[0]


class TestListProjectIssueCategories:
    """Unit tests for list_project_issue_categories tool."""

    @pytest.fixture
    def mock_redmine(self):
        with patch("redmine_mcp_server.redmine_handler.redmine") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_list_project_issue_categories_success(self, mock_redmine):
        assigned_to = Mock()
        assigned_to.id = 3
        assigned_to.name = "Alice"

        backend = Mock()
        backend.id = 20
        backend.name = "Backend"
        backend.assigned_to = assigned_to

        frontend = Mock()
        frontend.id = 21
        frontend.name = "Frontend"
        frontend.assigned_to = None

        mock_redmine.issue_category.filter.return_value = [backend, frontend]

        result = await list_project_issue_categories(project_id=10)

        assert len(result) == 2
        assert result[0]["id"] == 20
        assert "Backend" in result[0]["name"]
        assert result[0]["assigned_to"]["id"] == 3
        assert "Alice" in result[0]["assigned_to"]["name"]
        assert result[1]["assigned_to"] is None
        mock_redmine.issue_category.filter.assert_called_once_with(project_id=10)

    @pytest.mark.asyncio
    async def test_list_project_issue_categories_empty(self, mock_redmine):
        mock_redmine.issue_category.filter.return_value = []

        result = await list_project_issue_categories(project_id=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_list_project_issue_categories_error(self, mock_redmine):
        mock_redmine.issue_category.filter.side_effect = Exception("Boom")

        result = await list_project_issue_categories(project_id=10)

        assert len(result) == 1
        assert "error" in result[0]
