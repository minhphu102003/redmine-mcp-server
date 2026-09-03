"""Tests for list_personnel and get_person_work_summary (boss workflow)."""

import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.redmine_handler import (  # noqa: E402
    get_person_work_summary,
    list_personnel,
)


def _named_mock(**attrs):
    """Mock with attributes set explicitly (Mock(name=...) is reserved)."""
    m = Mock()
    for key, value in attrs.items():
        setattr(m, key, value)
    return m


def _mock_membership(user_id, user_name, roles=("Developer",), group=False):
    m = Mock()
    if group:
        m.user = None
        m.group = _named_mock(id=900, name="Group")
    else:
        m.user = _named_mock(id=user_id, name=user_name)
        m.group = None
    m.project = _named_mock(id=1, name="Proj")
    m.roles = [_named_mock(id=1, name=r) for r in roles]
    return m


def _mock_issue(
    issue_id,
    subject="Task",
    project_id=1,
    project_name="Proj",
    status_id=2,
    status_name="In Progress",
    due=None,
    done_ratio=30,
    updated_on=None,
):
    issue = Mock()
    issue.id = issue_id
    issue.subject = subject
    issue.project = _named_mock(id=project_id, name=project_name)
    issue.status = _named_mock(id=status_id, name=status_name)
    issue.due_date = due
    issue.done_ratio = done_ratio
    issue.updated_on = updated_on or datetime(2026, 9, 2, 10, 0, 0)
    return issue


def _mock_user(uid, firstname="An", lastname="Nguyen", status=1):
    u = Mock()
    u.id = uid
    u.firstname = firstname
    u.lastname = lastname
    u.name = None
    u.login = f"user{uid}"
    u.mail = f"user{uid}@example.com"
    u.status = status
    return u


def _mock_status(sid, name, is_closed=False):
    return _named_mock(id=sid, name=name, is_closed=is_closed)


def _mock_entry(hours, project_id=1, project_name="Proj"):
    e = Mock()
    e.hours = hours
    e.project = _named_mock(id=project_id, name=project_name)
    return e


class TestListPersonnel:
    @pytest.fixture
    def mock_redmine(self):
        with patch("redmine_mcp_server.redmine_handler.redmine") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_dedupes_user_across_projects(self, mock_redmine):
        mock_redmine.project.all.return_value = [
            _named_mock(id=1, name="Web"),
            _named_mock(id=2, name="App"),
        ]

        def memberships(project_id):
            if project_id == 1:
                return [
                    _mock_membership(7, "An Nguyen"),
                    _mock_membership(8, "Binh Tran"),
                ]
            return [_mock_membership(7, "An Nguyen", roles=("Manager",))]

        mock_redmine.project_membership.filter.side_effect = memberships

        result = await list_personnel()

        assert result["count"] == 2
        assert result["project_count"] == 2
        an = next(p for p in result["personnel"] if p["id"] == 7)
        assert len(an["projects"]) == 2
        assert {p["id"] for p in an["projects"]} == {1, 2}

    @pytest.mark.asyncio
    async def test_skips_groups_and_counts_them(self, mock_redmine):
        mock_redmine.project.all.return_value = [_named_mock(id=1, name="Web")]
        mock_redmine.project_membership.filter.return_value = [
            _mock_membership(7, "An Nguyen"),
            _mock_membership(None, "", group=True),
        ]

        result = await list_personnel()

        assert result["count"] == 1
        assert result["groups_skipped"] == 1

    @pytest.mark.asyncio
    async def test_project_scope_limits_projects(self, mock_redmine):
        mock_redmine.project_membership.filter.return_value = [
            _mock_membership(7, "An Nguyen")
        ]

        result = await list_personnel(project_ids=[5])

        assert result["project_count"] == 1
        call_kwargs = mock_redmine.project_membership.filter.call_args[1]
        assert call_kwargs.get("project_id") == 5
        mock_redmine.project.all.assert_not_called()

    @pytest.mark.asyncio
    async def test_project_error_is_partial_not_fatal(self, mock_redmine):
        mock_redmine.project.all.return_value = [
            _named_mock(id=1, name="Web"),
            _named_mock(id=2, name="App"),
        ]

        def memberships(project_id):
            if project_id == 1:
                raise RuntimeError("forbidden")
            return [_mock_membership(7, "An Nguyen")]

        mock_redmine.project_membership.filter.side_effect = memberships

        result = await list_personnel()

        assert result["count"] == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["project_id"] == 1


class TestPersonWorkSummary:
    @pytest.fixture
    def mock_redmine(self):
        with patch("redmine_mcp_server.redmine_handler.redmine") as mock:
            mock.url = "https://redmine.example.com"
            mock.issue_status.all.return_value = [
                _mock_status(1, "New"),
                _mock_status(2, "In Progress"),
                _mock_status(5, "Closed", is_closed=True),
            ]
            mock.user.get.side_effect = lambda uid: _mock_user(uid)
            yield mock

    def _setup_backlog(self, mock_redmine, issues):
        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return []
            return issues

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = []

    @pytest.mark.asyncio
    async def test_overdue_boundaries(self, mock_redmine):
        """Due today is NOT overdue; closed+past-due is NOT; None is separate."""
        today = date.today()
        issues = [
            _mock_issue(1, due=today),  # due today -> in progress, not overdue
            _mock_issue(  # closed + past due -> not overdue
                2, status_id=5, status_name="Closed", due=today - timedelta(3)
            ),
            _mock_issue(3, due=today - timedelta(1)),  # overdue
            _mock_issue(4, due=None),  # no due date -> separate bucket
        ]
        self._setup_backlog(mock_redmine, issues)

        result = await get_person_work_summary(7, window="day")

        assert "error" not in result
        proj = result["per_project"][0]["backlog"]
        assert proj["overdue_count"] == 1
        assert proj["overdue"][0]["id"] == 3
        assert proj["no_due_date_count"] == 1
        assert proj["no_due_date"][0]["id"] == 4
        assert result["totals"]["overdue_count"] == 1
        assert result["totals"]["open_count"] == 4

    @pytest.mark.asyncio
    async def test_day_window_bounds(self, mock_redmine):
        """updated_on lower bound is forwarded; upper cut drops next-day."""
        touched = [
            _mock_issue(1, updated_on=datetime(2026, 9, 2, 9, 0, 0)),
            _mock_issue(2, updated_on=datetime(2026, 9, 3, 0, 30, 0)),
        ]

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                assert kwargs["updated_on"] == ">=2026-09-02"
                return touched
            return []

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = []

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["window"] == {
            "type": "day",
            "from": "2026-09-02",
            "to": "2026-09-02",
        }
        assert result["totals"]["touched_count"] == 1

    @pytest.mark.asyncio
    async def test_week_window_is_mon_to_sun(self, mock_redmine):
        """A Thursday anchors Mon-Sun; a Sunday still anchors the same week."""
        self._setup_backlog(mock_redmine, [])

        thursday = await get_person_work_summary(
            7, window="week", date_str="2026-09-03"
        )
        assert thursday["window"] == {
            "type": "week",
            "from": "2026-08-31",
            "to": "2026-09-06",
        }
        call_kwargs = mock_redmine.time_entry.filter.call_args[1]
        assert call_kwargs["from_date"] == "2026-08-31"
        assert call_kwargs["to_date"] == "2026-09-06"

        mock_redmine.time_entry.filter.reset_mock()
        sunday = await get_person_work_summary(7, window="week", date_str="2026-09-06")
        assert sunday["window"]["from"] == "2026-08-31"
        assert sunday["window"]["to"] == "2026-09-06"

    @pytest.mark.asyncio
    async def test_hours_summed_per_project(self, mock_redmine):
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(2.5, project_id=1, project_name="Web"),
            _mock_entry(1.5, project_id=1, project_name="Web"),
            _mock_entry(4.0, project_id=2, project_name="App"),
        ]

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["hours"] == 8.0
        assert result["totals"]["time_entries"] == 3

    @pytest.mark.asyncio
    async def test_group_by_project(self, mock_redmine):
        issues = [
            _mock_issue(
                1, project_id=1, project_name="Web", due=date.today() - timedelta(1)
            ),
            _mock_issue(
                2, project_id=2, project_name="App", due=date.today() + timedelta(5)
            ),
        ]
        self._setup_backlog(mock_redmine, issues)

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert [p["project"]["name"] for p in result["per_project"]] == [
            "App",
            "Web",
        ]
        web = next(p for p in result["per_project"] if p["project"]["id"] == 1)
        assert web["backlog"]["overdue_count"] == 1

    @pytest.mark.asyncio
    async def test_ambiguous_name_returns_candidates(self, mock_redmine):
        mock_redmine.user.filter.return_value = [
            _mock_user(7, firstname="An", lastname="Nguyen"),
            _mock_user(9, firstname="An", lastname="Pham"),
        ]

        result = await get_person_work_summary("An")

        assert "error" in result
        assert "Multiple users match" in result["error"]
        mock_redmine.issue.filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_person_by_id(self, mock_redmine):
        mock_redmine.user.get.side_effect = Exception("404 Not Found")

        result = await get_person_work_summary(999)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_invalid_window_and_date(self, mock_redmine):
        bad_window = await get_person_work_summary(7, window="month")
        assert "error" in bad_window

        bad_date = await get_person_work_summary(7, date_str="02-09-2026")
        assert "error" in bad_date
        mock_redmine.issue.filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_name_resolution_forwards_name_filter(self, mock_redmine):
        mock_redmine.user.filter.return_value = [_mock_user(7)]
        self._setup_backlog(mock_redmine, [])

        result = await get_person_work_summary("An Nguyen")

        assert result["person"]["id"] == 7
        call_kwargs = mock_redmine.user.filter.call_args[1]
        assert call_kwargs.get("name") == "An Nguyen"

    @pytest.mark.asyncio
    async def test_evidence_block_present(self, mock_redmine):
        self._setup_backlog(mock_redmine, [])

        result = await get_person_work_summary(7, date_str="2026-09-02")

        evidence = result["evidence"]
        assert evidence["queried_at"]
        assert evidence["person_query"] == 7
        assert evidence["filters_used"]["assigned_to_id"] == 7
        assert evidence["totals"]["open_count"] == 0
