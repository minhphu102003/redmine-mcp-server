"""
Test cases for parent_issue_id validation in create_redmine_issue_impl.

Covers creating a new issue as a subtask of an existing issue:
parent existence, same-project enforcement, unlimited nesting depth
(deep subtask parents are allowed), string parent IDs, and standalone
creation without parent.
"""

import os
import sys
from unittest.mock import Mock

import pytest
from redminelib.exceptions import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.handler_impl.issue_fields import (  # noqa: E402
    _extract_missing_required_field_names,
    _is_required_custom_field_autofill_enabled,
    _parse_create_issue_fields,
    _parse_optional_object_payload,
)
from redmine_mcp_server.handler_impl.tools.issues import (  # noqa: E402
    create_redmine_issue_impl,
)
from redmine_mcp_server.redmine_handler import (  # noqa: E402
    _READ_ONLY_ERROR,
    _augment_fields_with_required_custom_fields,
    _handle_redmine_error,
    _is_read_only_mode,
    _issue_to_dict,
    _prepare_create_issue_fields,
    _resolve_project_tracker_name,
    validate_issue_description_template,
)


def _deps(client):
    """Build dependency-injected kwargs for create_redmine_issue_impl."""
    return {
        "is_read_only_mode": _is_read_only_mode,
        "read_only_error": _READ_ONLY_ERROR,
        "parse_create_issue_fields": _parse_create_issue_fields,
        "parse_optional_object_payload": _parse_optional_object_payload,
        "prepare_issue_fields": _prepare_create_issue_fields,
        "validate_issue_template": validate_issue_description_template,
        "resolve_tracker_name": _resolve_project_tracker_name,
        "get_client": lambda: client,
        "issue_to_dict": _issue_to_dict,
        "is_required_custom_field_autofill_enabled": (
            _is_required_custom_field_autofill_enabled
        ),
        "extract_missing_required_field_names": _extract_missing_required_field_names,
        "augment_fields_with_required_custom_fields": (
            _augment_fields_with_required_custom_fields
        ),
        "handle_error": _handle_redmine_error,
        "validation_error": ValidationError,
    }


def _make_mock_client():
    """Create a mock Redmine client with get/create stubs."""
    client = Mock()

    created_issue = Mock()
    created_issue.id = 999
    created_issue.subject = "Subtask of 42"
    created_issue.description = ""
    created_issue.project = Mock(id=1, name="Test Project")
    created_issue.parent = Mock(id=42, subject="Parent Task")
    created_issue.status = Mock(id=1, name="New")
    created_issue.priority = Mock(id=2, name="Normal")
    created_issue.author = Mock(id=1, name="Author")
    created_issue.assigned_to = None
    created_issue.created_on = None
    created_issue.updated_on = None
    client.issue.create.return_value = created_issue
    return client


def _make_parent_issue(project_id=1):
    """Create a mock parent issue belonging to the given project."""
    parent = Mock()
    parent.id = 42
    parent.subject = "Parent Task"
    parent.project = Mock(id=project_id, name="Test Project")
    parent.parent = None
    return parent


class TestCreateIssueWithParent:
    """Test cases for create_redmine_issue with parent_issue_id."""

    @pytest.mark.asyncio
    async def test_create_subtask_success(self):
        """Test creating a subtask under a valid existing parent."""
        client = _make_mock_client()
        client.issue.get.return_value = _make_parent_issue(project_id=1)

        result = await create_redmine_issue_impl(
            project_id=1,
            subject="Subtask of 42",
            description="",
            parent_issue_id=42,
            **_deps(client),
        )

        assert "error" not in result
        assert result["id"] == 999
        client.issue.get.assert_called_once_with(42)
        call_kwargs = client.issue.create.call_args[1]
        assert call_kwargs.get("parent_issue_id") == 42
        assert call_kwargs.get("project_id") == 1

    @pytest.mark.asyncio
    async def test_create_subtask_string_parent_id(self):
        """Test that a string parent ID is cast to int for the API."""
        client = _make_mock_client()
        client.issue.get.return_value = _make_parent_issue(project_id=1)

        result = await create_redmine_issue_impl(
            project_id=1,
            subject="Subtask of 42",
            description="",
            parent_issue_id="42",
            **_deps(client),
        )

        assert "error" not in result
        call_kwargs = client.issue.create.call_args[1]
        assert call_kwargs.get("parent_issue_id") == 42
        assert isinstance(call_kwargs.get("parent_issue_id"), int)

    @pytest.mark.asyncio
    async def test_create_subtask_parent_not_found(self):
        """Test error when the parent issue does not exist."""
        client = _make_mock_client()
        client.issue.get.side_effect = Exception("Issue 42 not found")

        result = await create_redmine_issue_impl(
            project_id=1,
            subject="Subtask of 42",
            description="",
            parent_issue_id=42,
            **_deps(client),
        )

        assert "error" in result
        assert "42" in result["error"]
        client.issue.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_subtask_parent_in_different_project(self):
        """Test error when parent belongs to a different project."""
        client = _make_mock_client()
        client.issue.get.return_value = _make_parent_issue(project_id=7)

        result = await create_redmine_issue_impl(
            project_id=1,
            subject="Subtask of 42",
            description="",
            parent_issue_id=42,
            **_deps(client),
        )

        assert "error" in result
        assert "same project" in result["error"]
        assert result["parent_project_id"] == 7
        client.issue.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_subtask_deep_nesting_success(self):
        """Test that a subtask can be created under a parent that is itself a
        subtask (Redmine supports unlimited nesting depth)."""
        client = _make_mock_client()
        parent = _make_parent_issue(project_id=1)
        parent.parent = Mock(id=10, subject="Grandparent")
        client.issue.get.return_value = parent

        result = await create_redmine_issue_impl(
            project_id=1,
            subject="Subtask of 42",
            description="",
            parent_issue_id=42,
            **_deps(client),
        )

        assert "error" not in result
        assert result["id"] == 999
        call_kwargs = client.issue.create.call_args[1]
        assert call_kwargs.get("parent_issue_id") == 42

    @pytest.mark.asyncio
    async def test_create_standalone_does_not_fetch_parent(self):
        """Test that standalone creation never fetches a parent issue."""
        client = _make_mock_client()

        result = await create_redmine_issue_impl(
            project_id=1,
            subject="Standalone task",
            description="",
            **_deps(client),
        )

        assert "error" not in result
        client.issue.get.assert_not_called()
        call_kwargs = client.issue.create.call_args[1]
        assert "parent_issue_id" not in call_kwargs
