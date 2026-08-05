"""Tests for create_redmine_issue_with_subtasks tool."""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import redmine_handler  # noqa: E402


def _make_subtask(subject, **overrides):
    """Build a subtask dict carrying every required field."""
    subtask = {
        "subject": subject,
        "description": f"Description of {subject}",
        "tracker_id": 1,
        "priority_id": 3,
        "status_id": 1,
        "assigned_to_id": 80,
        "start_date": "2026-08-05",
        "due_date": "2026-08-12",
        "estimated_hours": 2.0,
        "done_ratio": 0,
    }
    subtask.update(overrides)
    return subtask


class TestCreateRedmineIssueWithSubtasks:
    """Unit tests for parent + subtasks batch creation tool."""

    @pytest.mark.asyncio
    async def test_creates_parent_and_subtasks_successfully(self):
        create_issue_mock = AsyncMock(
            side_effect=[
                {"id": 100, "subject": "Parent"},
                {"id": 101, "subject": "Child 1"},
                {"id": 102, "subject": "Child 2"},
            ]
        )
        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            result = await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                subtasks=[
                    _make_subtask("Child 1"),
                    _make_subtask("Child 2", tracker_id=2, fields={"tracker_id": 2}),
                ],
            )

        assert result["parent_issue"]["id"] == 100
        assert len(result["created_subtasks"]) == 2
        assert result["summary"]["created_subtasks"] == 2
        assert result["summary"]["failed_subtasks"] == 0

        parent_fields = create_issue_mock.await_args_list[0].kwargs["fields"]
        child_1_fields = create_issue_mock.await_args_list[1].kwargs["fields"]
        child_2_fields = create_issue_mock.await_args_list[2].kwargs["fields"]
        assert parent_fields["tracker_id"] == 1
        assert parent_fields["status_id"] == 1
        assert parent_fields["assigned_to_id"] == 80
        assert child_1_fields["parent_issue_id"] == 100
        assert child_2_fields["parent_issue_id"] == 100
        assert child_2_fields["tracker_id"] == 2

    @pytest.mark.asyncio
    async def test_returns_error_when_parent_creation_fails(self):
        create_issue_mock = AsyncMock(return_value={"error": "Permission denied"})
        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            result = await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                subtasks=[_make_subtask("Child 1")],
            )

        assert "error" in result
        assert "parent issue" in result["error"].lower()
        assert result["created_subtasks"] == []
        assert create_issue_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_stops_on_first_subtask_error_when_requested(self):
        create_issue_mock = AsyncMock(
            side_effect=[
                {"id": 100, "subject": "Parent"},
                {"id": 101, "subject": "Child 1"},
                {"error": "Tracker invalid"},
                {"id": 103, "subject": "Child 3"},
            ]
        )
        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            result = await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                stop_on_subtask_error=True,
                subtasks=[
                    _make_subtask("Child 1"),
                    _make_subtask("Child 2"),
                    _make_subtask("Child 3"),
                ],
            )

        assert len(result["created_subtasks"]) == 1
        assert len(result["failed_subtasks"]) == 1
        assert result["summary"]["created_subtasks"] == 1
        assert result["summary"]["failed_subtasks"] == 1
        assert create_issue_mock.await_count == 3

    @pytest.mark.asyncio
    async def test_rejects_invalid_subtasks_payload(self):
        result = await redmine_handler.create_redmine_issue_with_subtasks(
            project_id=10,
            parent_subject="Parent",
            parent_description="Parent description",
            tracker_id=1,
            priority_id=3,
            status_id=1,
            assigned_to_id=80,
            start_date="2026-08-05",
            due_date="2026-08-12",
            estimated_hours=2.0,
            done_ratio=0,
            subtasks="not-a-list",  # type: ignore[arg-type]
        )

        assert "error" in result
        assert "subtasks must be a list" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_rejects_subtask_missing_required_fields(self):
        create_issue_mock = AsyncMock(
            side_effect=[
                {"id": 100, "subject": "Parent"},
                {"id": 101, "subject": "Child 1"},
            ]
        )
        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            result = await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                subtasks=[
                    _make_subtask("Child 1"),
                    {"subject": "Incomplete", "tracker_id": 1},
                ],
            )

        assert len(result["created_subtasks"]) == 1
        assert result["summary"]["created_subtasks"] == 1
        assert result["summary"]["failed_subtasks"] == 1
        failed = result["failed_subtasks"][0]
        assert "Missing required subtask fields" in failed["error"]
        for name in (
            "description",
            "priority_id",
            "status_id",
            "assigned_to_id",
            "start_date",
            "due_date",
            "estimated_hours",
            "done_ratio",
        ):
            assert name in failed["error"]
        assert create_issue_mock.await_count == 2

    @pytest.mark.asyncio
    async def test_batches_subtasks_in_chunks_of_50(self):
        subtasks = [_make_subtask(f"Task {i}") for i in range(1, 101)]
        side_effect = [{"id": 100, "subject": "Parent"}] + [
            {"id": 100 + i, "subject": f"Task {i}"} for i in range(1, 101)
        ]
        create_issue_mock = AsyncMock(side_effect=side_effect)

        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            result = await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                subtasks=subtasks,
            )

        assert len(result["created_subtasks"]) == 100
        assert result["summary"]["subtask_batch_size"] == 50
        assert result["summary"]["subtask_batch_count"] == 2
        assert create_issue_mock.await_count == 101

    @pytest.mark.asyncio
    async def test_supports_wrapped_parent_fields_payload(self):
        create_issue_mock = AsyncMock(
            side_effect=[
                {"id": 100, "subject": "Parent"},
                {"id": 101, "subject": "Child 1"},
            ]
        )
        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=2,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                parent_fields={"parent_fields": {"tracker_id": 2}},
                subtasks=[_make_subtask("Child 1")],
            )

        parent_fields = create_issue_mock.await_args_list[0].kwargs["fields"]
        assert parent_fields["tracker_id"] == 2

    @pytest.mark.asyncio
    async def test_forces_subtasks_to_created_parent_issue_id(self):
        create_issue_mock = AsyncMock(
            side_effect=[
                {"id": 100, "subject": "Parent"},
                {"id": 101, "subject": "Child 1"},
            ]
        )
        with patch.object(redmine_handler, "create_redmine_issue", create_issue_mock):
            await redmine_handler.create_redmine_issue_with_subtasks(
                project_id=10,
                parent_subject="Parent",
                parent_description="Parent description",
                tracker_id=1,
                priority_id=3,
                status_id=1,
                assigned_to_id=80,
                start_date="2026-08-05",
                due_date="2026-08-12",
                estimated_hours=2.0,
                done_ratio=0,
                subtasks=[
                    _make_subtask(
                        "Child 1",
                        tracker_id=2,
                        fields={"parent_issue_id": 999, "tracker_id": 2},
                    )
                ],
            )

        child_fields = create_issue_mock.await_args_list[1].kwargs["fields"]
        assert child_fields["parent_issue_id"] == 100
        assert child_fields["tracker_id"] == 2
