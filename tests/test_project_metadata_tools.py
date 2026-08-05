"""Tests for project metadata lookup impls (trackers and issue categories)."""

import os
import sys
from unittest.mock import AsyncMock, Mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.redmine_handler import (  # noqa: E402
    _handle_redmine_error,
)
from redmine_mcp_server.handler_impl.tools.projects import (  # noqa: E402
    list_project_issue_categories_impl,
    list_project_trackers_impl,
)


def _deps(client, **overrides):
    """Build injected dependencies for the impls."""
    deps = {
        "ensure_cleanup_started": AsyncMock(),
        "get_client": lambda: client,
        "wrap_content": lambda value: value,
        "handle_error": _handle_redmine_error,
    }
    deps.update(overrides)
    return deps


class TestListProjectTrackers:
    """Unit tests for list_project_trackers_impl."""

    @pytest.fixture
    def mock_client(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_list_project_trackers_success(self, mock_client):
        tracker_bug = Mock()
        tracker_bug.id = 1
        tracker_bug.name = "Bug"

        tracker_task = Mock()
        tracker_task.id = 2
        tracker_task.name = "Task"

        project = Mock()
        project.trackers = [tracker_bug, tracker_task]
        mock_client.project.get.return_value = project

        result = await list_project_trackers_impl(10, **_deps(mock_client))

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert "Bug" in result[0]["name"]
        mock_client.project.get.assert_called_once_with(10, include="trackers")

    @pytest.mark.asyncio
    async def test_list_project_trackers_empty(self, mock_client):
        project = Mock()
        project.trackers = []
        mock_client.project.get.return_value = project

        result = await list_project_trackers_impl("core", **_deps(mock_client))

        assert result == []

    @pytest.mark.asyncio
    async def test_list_project_trackers_error(self, mock_client):
        mock_client.project.get.side_effect = Exception("Boom")

        result = await list_project_trackers_impl(10, **_deps(mock_client))

        assert len(result) == 1
        assert "error" in result[0]


class TestListProjectIssueCategories:
    """Unit tests for list_project_issue_categories_impl."""

    @pytest.fixture
    def mock_client(self):
        return Mock()

    @pytest.mark.asyncio
    async def test_list_project_issue_categories_success(self, mock_client):
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

        mock_client.issue_category.filter.return_value = [backend, frontend]

        result = await list_project_issue_categories_impl(10, **_deps(mock_client))

        assert len(result) == 2
        assert result[0]["id"] == 20
        assert "Backend" in result[0]["name"]
        assert result[0]["assigned_to"]["id"] == 3
        assert "Alice" in result[0]["assigned_to"]["name"]
        assert result[1]["assigned_to"] is None
        mock_client.issue_category.filter.assert_called_once_with(project_id=10)

    @pytest.mark.asyncio
    async def test_list_project_issue_categories_empty(self, mock_client):
        mock_client.issue_category.filter.return_value = []

        result = await list_project_issue_categories_impl(10, **_deps(mock_client))

        assert result == []

    @pytest.mark.asyncio
    async def test_list_project_issue_categories_error(self, mock_client):
        mock_client.issue_category.filter.side_effect = Exception("Boom")

        result = await list_project_issue_categories_impl(10, **_deps(mock_client))

        assert len(result) == 1
        assert "error" in result[0]
