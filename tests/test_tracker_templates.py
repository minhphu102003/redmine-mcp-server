"""Tests for tracker-specific issue description templates."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.resources.template_guidance import (  # noqa: E402
    required_issue_template_sections,
    validate_issue_description_template,
)
from redmine_mcp_server import redmine_handler  # noqa: E402


def test_required_sections_use_tracker_specific_template(tmp_path):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "issue_description.md").write_text(
        "## Default\n## AC", encoding="utf-8"
    )
    (templates_dir / "issue_description_bug.md").write_text(
        "## Steps to Reproduce\n## Expected Result", encoding="utf-8"
    )

    with patch.dict(
        os.environ,
        {
            "REDMINE_RESOURCE_TEMPLATE_DIR": str(templates_dir),
            "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS": "",
            "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS_BY_TRACKER": "",
            "REDMINE_ISSUE_DESCRIPTION_TEMPLATE": "",
            "REDMINE_ISSUE_DESCRIPTION_TEMPLATE_BY_TRACKER": "",
        },
        clear=False,
    ):
        bug_sections = required_issue_template_sections("Bug")
        default_sections = required_issue_template_sections(None)

    assert bug_sections == ["Steps to Reproduce", "Expected Result"]
    assert default_sections == ["Default", "AC"]


def test_validate_template_with_tracker_specific_sections():
    with patch.dict(
        os.environ,
        {
            "REDMINE_ENFORCE_ISSUE_TEMPLATE": "true",
            "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS": "",
            "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS_BY_TRACKER": (
                '{"bug": ["Steps to Reproduce", "Expected Result"]}'
            ),
        },
        clear=False,
    ):
        error = validate_issue_description_template(
            "## Steps to Reproduce\n- A", tracker_name="Bug"
        )

    assert error is not None
    assert error["tracker"] == "Bug"
    assert error["missing_sections"] == ["Expected Result"]


@pytest.mark.asyncio
async def test_create_issue_uses_tracker_specific_template_validation():
    mock_redmine = Mock()
    tracker_bug = Mock()
    tracker_bug.id = 1
    tracker_bug.name = "Bug"
    project = Mock()
    project.trackers = [tracker_bug]
    mock_redmine.project.get.return_value = project

    with patch("redmine_mcp_server.redmine_handler.redmine", mock_redmine):
        with patch.dict(
            os.environ,
            {
                "REDMINE_ENFORCE_ISSUE_TEMPLATE": "true",
                "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS": "",
                "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS_BY_TRACKER": (
                    '{"bug": ["Steps to Reproduce", "Expected Result"]}'
                ),
            },
            clear=False,
        ):
            result = await redmine_handler.create_redmine_issue(
                project_id=10,
                subject="Bug ticket",
                description="## Steps to Reproduce\n- open app",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                fields={"tracker_id": 1},
            )

    assert "error" in result
    assert result["missing_sections"] == ["Expected Result"]
