"""Tests for the get_project_issue_context consolidated tool."""

import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import redmine_handler  # noqa: E402
from redmine_mcp_server.handler_impl.tools import project_context  # noqa: E402


def _fake_deps() -> dict:
    """Return fake injected dependencies for impl-level tests."""
    return {
        "ensure_cleanup_started": AsyncMock(),
        "get_client": Mock(),
        "custom_field_applies_to_tracker": lambda field, tracker_id: True,
        "custom_field_to_dict": lambda field: {
            "id": field["id"],
            "name": field["name"],
            "is_required": field["is_required"],
        },
        "membership_to_dict": lambda m: {"id": m["id"], "name": m["name"]},
        "version_to_dict": lambda v: {"id": v["id"], "name": v["name"]},
        "wrap_content": lambda value: value,
        "handle_error": lambda exc, ctx, meta: {
            "error": str(exc),
            "context": ctx,
        },
    }


def _mock_project(**kwargs):
    project = Mock()
    project.id = kwargs.get("id", 1)
    project.name = kwargs.get("name", "My Project")
    project.identifier = kwargs.get("identifier", "my-project")
    project.description = kwargs.get("description", "A test project")
    project.created_on = kwargs.get("created_on", None)
    return project


class TestGetProjectIssueContextImpl:
    """Unit tests for the impl-level aggregation logic."""

    @pytest.mark.asyncio
    async def test_aggregates_all_sections(self):
        deps = _fake_deps()
        client = Mock(project=Mock(get=Mock(return_value=_mock_project())))
        deps["get_client"] = Mock(return_value=client)

        with (
            patch.object(
                project_context,
                "list_project_trackers_impl",
                AsyncMock(return_value=[{"id": 1, "name": "Bug"}]),
            ),
            patch.object(
                project_context,
                "list_project_issue_categories_impl",
                AsyncMock(return_value=[{"id": 1, "name": "Frontend"}]),
            ),
            patch.object(
                project_context,
                "list_project_members_impl",
                AsyncMock(return_value=[{"id": 1, "name": "Alice"}]),
            ),
            patch.object(
                project_context,
                "list_redmine_versions_impl",
                AsyncMock(return_value=[{"id": 1, "name": "v1.0"}]),
            ),
            patch.object(
                project_context,
                "list_project_issue_custom_fields_impl",
                AsyncMock(
                    return_value=[
                        {"id": 1, "name": "Size", "is_required": True},
                        {"id": 2, "name": "Priority", "is_required": False},
                    ]
                ),
            ),
            patch.object(
                project_context,
                "list_redmine_issue_statuses_impl",
                AsyncMock(
                    return_value=[
                        {"id": 1, "name": "New", "is_closed": False},
                        {"id": 5, "name": "Closed", "is_closed": True},
                    ]
                ),
            ),
            patch.object(
                project_context,
                "_list_issue_priorities",
                AsyncMock(
                    return_value=[
                        {"id": 2, "name": "Normal"},
                        {"id": 4, "name": "High"},
                    ]
                ),
            ),
        ):
            result = await project_context.get_project_issue_context_impl(
                project_id=1, **deps
            )

        assert result["project"]["id"] == 1
        assert result["project"]["name"] == "My Project"
        assert result["project"]["identifier"] == "my-project"
        assert result["tracker_id"] is None
        assert result["trackers"] == [{"id": 1, "name": "Bug"}]
        assert result["categories"] == [{"id": 1, "name": "Frontend"}]
        assert result["members"] == [{"id": 1, "name": "Alice"}]
        assert result["versions"] == [{"id": 1, "name": "v1.0"}]
        assert result["statuses"] == [
            {"id": 1, "name": "New", "is_closed": False},
            {"id": 5, "name": "Closed", "is_closed": True},
        ]
        assert result["priorities"] == [
            {"id": 2, "name": "Normal"},
            {"id": 4, "name": "High"},
        ]
        assert len(result["custom_fields"]) == 2
        assert result["required_custom_fields"] == [
            {"id": 1, "name": "Size", "is_required": True}
        ]

    @pytest.mark.asyncio
    async def test_tracker_id_passed_to_custom_fields_filter(self):
        deps = _fake_deps()
        client = Mock(project=Mock(get=Mock(return_value=_mock_project())))
        deps["get_client"] = Mock(return_value=client)

        custom_fields_impl = AsyncMock(return_value=[])
        with (
            patch.object(
                project_context,
                "list_project_trackers_impl",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                project_context,
                "list_project_issue_categories_impl",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                project_context, "list_project_members_impl", AsyncMock(return_value=[])
            ),
            patch.object(
                project_context,
                "list_redmine_versions_impl",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                project_context,
                "list_project_issue_custom_fields_impl",
                custom_fields_impl,
            ),
            patch.object(
                project_context,
                "list_redmine_issue_statuses_impl",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                project_context,
                "_list_issue_priorities",
                AsyncMock(return_value=[]),
            ),
        ):
            result = await project_context.get_project_issue_context_impl(
                project_id="core", tracker_id=5, **deps
            )

        assert result["tracker_id"] == 5
        assert result["statuses"] == []
        assert result["priorities"] == []
        assert custom_fields_impl.await_args.args[0] == "core"
        assert custom_fields_impl.await_args.args[1] == 5

    @pytest.mark.asyncio
    async def test_partial_section_failure_keeps_other_sections(self):
        deps = _fake_deps()
        client = Mock(project=Mock(get=Mock(return_value=_mock_project())))
        deps["get_client"] = Mock(return_value=client)

        with (
            patch.object(
                project_context,
                "list_project_trackers_impl",
                AsyncMock(return_value=[{"error": "trackers boom"}]),
            ),
            patch.object(
                project_context,
                "list_project_issue_categories_impl",
                AsyncMock(return_value=[{"id": 1, "name": "Frontend"}]),
            ),
            patch.object(
                project_context,
                "list_project_members_impl",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                project_context,
                "list_redmine_versions_impl",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                project_context,
                "list_project_issue_custom_fields_impl",
                AsyncMock(
                    return_value=[
                        {"id": 1, "name": "Size", "is_required": True},
                        {"error": "fields boom"},
                    ]
                ),
            ),
            patch.object(
                project_context,
                "list_redmine_issue_statuses_impl",
                AsyncMock(return_value=[{"id": 1, "name": "New", "is_closed": False}]),
            ),
            patch.object(
                project_context,
                "_list_issue_priorities",
                AsyncMock(return_value=[{"id": 2, "name": "Normal"}]),
            ),
        ):
            result = await project_context.get_project_issue_context_impl(
                project_id=1, **deps
            )

        assert result["trackers"] == [{"error": "trackers boom"}]
        assert result["categories"] == [{"id": 1, "name": "Frontend"}]
        assert result["statuses"] == [{"id": 1, "name": "New", "is_closed": False}]
        assert result["priorities"] == [{"id": 2, "name": "Normal"}]
        assert result["required_custom_fields"] == [
            {"id": 1, "name": "Size", "is_required": True}
        ]

    @pytest.mark.asyncio
    async def test_client_none_returns_error(self):
        deps = _fake_deps()
        deps["get_client"] = Mock(return_value=None)

        result = await project_context.get_project_issue_context_impl(
            project_id=1, **deps
        )

        assert "error" in result
        assert "Redmine client not initialized" in result["error"]

    @pytest.mark.asyncio
    async def test_project_get_failure_returns_error(self):
        deps = _fake_deps()
        client = Mock(
            project=Mock(get=Mock(side_effect=Exception("Project not found")))
        )
        deps["get_client"] = Mock(return_value=client)

        result = await project_context.get_project_issue_context_impl(
            project_id=404, **deps
        )

        assert "error" in result
        assert "Project not found" in result["error"]


class TestGetProjectIssueContextTool:
    """End-to-end tests for the @mcp.tool() wrapper."""

    @pytest.fixture
    def mock_redmine(self):
        with patch("redmine_mcp_server.redmine_handler.redmine") as mock:
            yield mock

    def _build_project(self):
        tracker = Mock()
        tracker.id = 1
        tracker.name = "Bug"

        project = Mock()
        project.id = 10
        project.name = "Core"
        project.identifier = "core"
        project.description = ""
        project.created_on = None
        project.trackers = [tracker]

        custom_field = Mock()
        custom_field.id = 6
        custom_field.name = "Size"
        custom_field.field_format = "list"
        custom_field.is_required = True
        custom_field.multiple = False
        custom_field.default_value = None
        custom_field.possible_values = ["S", "M", "L"]
        custom_field.trackers = []
        project.issue_custom_fields = [custom_field]
        return project

    @pytest.mark.asyncio
    async def test_wrapper_end_to_end(self, mock_redmine):
        project = self._build_project()
        mock_redmine.project.get.return_value = project

        category = Mock()
        category.id = 1
        category.name = "Frontend"
        category.assigned_to = None
        mock_redmine.issue_category.filter.return_value = [category]

        membership = Mock()
        membership.id = 1
        membership.user = Mock()
        membership.user.id = 3
        membership.user.name = "Alice"
        membership.group = None
        membership.project = None
        membership.roles = []
        mock_redmine.project_membership.filter.return_value = [membership]

        version = Mock()
        version.id = 1
        version.name = "v1.0"
        version.description = ""
        version.status = "open"
        version.due_date = None
        version.sharing = "none"
        version.wiki_page_title = ""
        version.project = None
        version.created_on = None
        version.updated_on = None
        mock_redmine.version.filter.return_value = [version]

        status_new = Mock()
        status_new.id = 1
        status_new.name = "New"
        status_new.is_closed = False
        status_closed = Mock()
        status_closed.id = 5
        status_closed.name = "Closed"
        status_closed.is_closed = True
        mock_redmine.issue_status.all.return_value = [status_new, status_closed]

        priority_normal = Mock()
        priority_normal.id = 2
        priority_normal.name = "Normal"
        priority_high = Mock()
        priority_high.id = 4
        priority_high.name = "High"
        mock_redmine.enumeration.filter.return_value = [
            priority_normal,
            priority_high,
        ]

        result = await redmine_handler.get_project_issue_context(project_id=10)

        assert result["project"]["id"] == 10
        assert "core" in result["project"]["identifier"]
        assert result["tracker_id"] is None
        assert result["trackers"][0]["id"] == 1
        assert "Bug" in result["trackers"][0]["name"]
        assert result["categories"][0]["id"] == 1
        assert "Frontend" in result["categories"][0]["name"]
        assert result["members"][0]["id"] == 1
        assert result["versions"][0]["id"] == 1
        assert [s["id"] for s in result["statuses"]] == [1, 5]
        assert "New" in result["statuses"][0]["name"]
        assert result["statuses"][0]["is_closed"] is False
        assert "Closed" in result["statuses"][1]["name"]
        assert result["statuses"][1]["is_closed"] is True
        assert [p["id"] for p in result["priorities"]] == [2, 4]
        assert "Normal" in result["priorities"][0]["name"]
        assert "High" in result["priorities"][1]["name"]
        assert result["custom_fields"][0]["id"] == 6
        assert result["custom_fields"][0]["possible_values"] == ["S", "M", "L"]
        assert result["required_custom_fields"][0]["id"] == 6
        mock_redmine.project.get.assert_any_call(10)
