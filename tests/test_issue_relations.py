"""
Test cases for issue-relation tools (create/delete).

Covers dependency creation between issues (precedes/follows/blocks/relates),
validation (relation type, self-relation, missing issues), read-only mode,
and deletion.
"""

import os
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.handler_impl.tools.relations import (  # noqa: E402
    ALLOWED_RELATION_TYPES,
    create_redmine_issue_relation_impl,
    delete_redmine_issue_relation_impl,
)
from redmine_mcp_server.redmine_handler import (  # noqa: E402
    _READ_ONLY_ERROR,
    _handle_redmine_error,
    _is_read_only_mode,
)
from redmine_mcp_server.serializers.content import (  # noqa: E402
    wrap_insecure_content,
)


def _deps(client):
    """Build dependency-injected kwargs for create_redmine_issue_relation_impl."""
    return {
        "is_read_only_mode": _is_read_only_mode,
        "read_only_error": _READ_ONLY_ERROR,
        "get_client": lambda: client,
        "wrap_content": wrap_insecure_content,
        "handle_error": _handle_redmine_error,
    }


def _delete_deps(client):
    """Build dependency-injected kwargs for delete_redmine_issue_relation_impl."""
    return {
        "is_read_only_mode": _is_read_only_mode,
        "read_only_error": _READ_ONLY_ERROR,
        "get_client": lambda: client,
        "handle_error": _handle_redmine_error,
    }


def _make_issue(issue_id, subject="Task"):
    issue = Mock()
    issue.id = issue_id
    issue.subject = subject
    return issue


def _make_relation(relation_id=7):
    relation = Mock()
    relation.id = relation_id
    relation.issue_id = 100
    relation.issue_to_id = 200
    relation.relation_type = "precedes"
    relation.delay = None
    return relation


def _make_client():
    client = Mock()
    client.issue.get.side_effect = [
        _make_issue(100, "Setup API"),
        _make_issue(200, "Build UI"),
    ]
    client.issue_relation.create.return_value = _make_relation()
    return client


class TestCreateIssueRelation:
    """Test cases for create_redmine_issue_relation."""

    @pytest.mark.asyncio
    async def test_create_precedes_success(self):
        """Test creating a 'precedes' dependency between two issues."""
        client = _make_client()

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=200,
            relation_type="precedes",
            **_deps(client),
        )

        assert "error" not in result
        assert result["success"] is True
        assert result["relation"]["relation_type"] == "precedes"
        assert result["relation"]["issue_id"] == 100
        assert result["relation"]["issue_to_id"] == 200
        client.issue_relation.create.assert_called_once_with(
            issue_id=100,
            issue_to_id=200,
            relation_type="precedes",
        )
        assert "Setup API" in result["issues"]["from"]["subject"]
        assert "insecure-content" in result["issues"]["from"]["subject"]

    @pytest.mark.asyncio
    async def test_create_with_delay(self):
        """Test passing a delay in days for precedes/follows."""
        client = _make_client()

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=200,
            relation_type="follows",
            delay=1,
            **_deps(client),
        )

        assert "error" not in result
        call_kwargs = client.issue_relation.create.call_args[1]
        assert call_kwargs.get("delay") == 1

    @pytest.mark.asyncio
    async def test_create_case_insensitive_type(self):
        """Test that relation type is normalized to lowercase."""
        client = _make_client()

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=200,
            relation_type="Blocks",
            **_deps(client),
        )

        assert "error" not in result
        call_kwargs = client.issue_relation.create.call_args[1]
        assert call_kwargs.get("relation_type") == "blocks"

    @pytest.mark.asyncio
    async def test_create_invalid_relation_type(self):
        """Test error for an unknown relation type."""
        client = _make_client()

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=200,
            relation_type="depends_on",
            **_deps(client),
        )

        assert "error" in result
        assert "Invalid relation_type" in result["error"]
        client.issue_relation.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_self_relation_rejected(self):
        """Test error when an issue is related to itself."""
        client = _make_client()

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=100,
            relation_type="relates",
            **_deps(client),
        )

        assert "error" in result
        assert "different issues" in result["error"]
        client.issue_relation.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_missing_endpoint_issue(self):
        """Test error when one of the issues does not exist."""
        client = _make_client()
        client.issue.get.side_effect = Exception("Issue 200 not found")

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=200,
            relation_type="precedes",
            **_deps(client),
        )

        assert "error" in result
        client.issue_relation.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_read_only_mode(self, monkeypatch):
        """Test that read-only mode blocks relation creation."""
        monkeypatch.setenv("REDMINE_MCP_READ_ONLY", "true")
        client = _make_client()

        result = await create_redmine_issue_relation_impl(
            issue_id=100,
            issue_to_id=200,
            relation_type="precedes",
            **_deps(client),
        )

        assert result == _READ_ONLY_ERROR
        client.issue_relation.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_supports_expected_types(self):
        """Test that all Redmine dependency types are allowed."""
        expected = {
            "relates",
            "duplicates",
            "duplicated",
            "blocks",
            "blocked",
            "precedes",
            "follows",
            "copied_to",
            "copied_from",
        }
        assert ALLOWED_RELATION_TYPES == expected


class TestDeleteIssueRelation:
    """Test cases for delete_redmine_issue_relation."""

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test deleting a relation by ID."""
        client = Mock()

        result = await delete_redmine_issue_relation_impl(
            relation_id=7,
            **_delete_deps(client),
        )

        assert "error" not in result
        assert result["success"] is True
        assert result["relation_id"] == 7
        client.issue_relation.delete.assert_called_once_with(7)

    @pytest.mark.asyncio
    async def test_delete_read_only_mode(self, monkeypatch):
        """Test that read-only mode blocks relation deletion."""
        monkeypatch.setenv("REDMINE_MCP_READ_ONLY", "true")
        client = Mock()

        result = await delete_redmine_issue_relation_impl(
            relation_id=7,
            **_delete_deps(client),
        )

        assert result == _READ_ONLY_ERROR
        client.issue_relation.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """Test error when the relation does not exist."""
        client = Mock()
        client.issue_relation.delete.side_effect = Exception("Relation 7 not found")

        result = await delete_redmine_issue_relation_impl(
            relation_id=7,
            **_delete_deps(client),
        )

        assert "error" in result
