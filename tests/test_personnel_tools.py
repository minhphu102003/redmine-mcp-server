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
    estimated_hours=None,
    description="",
):
    issue = Mock()
    issue.id = issue_id
    issue.subject = subject
    issue.project = _named_mock(id=project_id, name=project_name)
    issue.status = _named_mock(id=status_id, name=status_name)
    issue.due_date = due
    issue.done_ratio = done_ratio
    issue.estimated_hours = estimated_hours
    issue.updated_on = updated_on or datetime(2026, 9, 2, 10, 0, 0)
    issue.description = description
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


def _mock_entry(
    hours,
    project_id=1,
    project_name="Proj",
    issue_id=None,
    spent_on=None,
    comments="",
    activity_name=None,
):
    e = Mock()
    e.hours = hours
    e.project = _named_mock(id=project_id, name=project_name)
    e.issue = _named_mock(id=issue_id) if issue_id is not None else None
    e.spent_on = spent_on
    e.comments = comments
    e.activity = (
        _named_mock(id=9, name=activity_name) if activity_name is not None else None
    )
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
                _mock_status(3, "Done"),
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
        """Due today is NOT overdue; closed/Done + past-due is NOT; None separate."""
        today = date.today()
        issues = [
            _mock_issue(1, due=today),  # due today -> in progress, not overdue
            _mock_issue(  # closed + past due -> not overdue
                2, status_id=5, status_name="Closed", due=today - timedelta(3)
            ),
            _mock_issue(3, due=today - timedelta(1)),  # overdue
            _mock_issue(4, due=None),  # no due date -> separate bucket
            _mock_issue(  # Done + 100% + past due -> completed, not overdue
                5,
                status_id=3,
                status_name="Done",
                done_ratio=100,
                due=today - timedelta(10),
            ),
        ]
        self._setup_backlog(mock_redmine, issues)

        result = await get_person_work_summary(7, window="day")

        assert "error" not in result
        proj = result["per_project"][0]["backlog"]
        assert proj["overdue_count"] == 1
        assert proj["overdue"][0]["id"] == 3
        assert proj["no_due_date_count"] == 1
        assert proj["no_due_date"][0]["id"] == 4
        assert proj["completed_count"] == 2  # Closed id=2 + Done id=5
        assert result["totals"]["overdue_count"] == 1
        assert result["totals"]["completed_total"] == 2
        assert result["totals"]["open_count"] == 3

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
        window_calls = [
            c[1]
            for c in mock_redmine.time_entry.filter.call_args_list
            if "from_date" in c[1]
        ]
        assert window_calls[0]["from_date"] == "2026-08-31"
        assert window_calls[0]["to_date"] == "2026-09-06"
        lifetime_calls = [
            c[1]
            for c in mock_redmine.time_entry.filter.call_args_list
            if "from_date" not in c[1]
        ]
        assert len(lifetime_calls) == 1 and lifetime_calls[0]["user_id"] == 7

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

    @pytest.mark.asyncio
    async def test_completed_rule_done100_and_done_status(self, mock_redmine):
        """100% needs Done status (or closed) to count as completed."""
        done = _mock_issue(
            1,
            status_id=3,
            status_name="Done",
            done_ratio=100,
            estimated_hours=3.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        ratio_only = _mock_issue(
            2, done_ratio=100, updated_on=datetime(2026, 9, 2, 9, 0, 0)
        )  # In Progress -> open, flagged
        almost = _mock_issue(3, done_ratio=90, updated_on=datetime(2026, 9, 2, 9, 0, 0))

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return [done, ratio_only, almost]
            return []

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = []

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["completed_count"] == 1
        assert result["totals"]["closed_count"] == 0
        wed = result["widget_data"]["Thứ 4"]
        assert [t["id"] for t in wed] == [1]
        assert wed[0]["est"] == 3.0
        assert wed[0]["hours"] == 0.0
        assert wed[0]["completed"] is True
        flags = {f["issue"]["id"]: f["reason"] for f in result["data_quality_flags"]}
        assert 2 in flags
        assert 1 not in flags and 3 not in flags

    @pytest.mark.asyncio
    async def test_hours_split_per_day_with_completion_flag(self, mock_redmine):
        done = _mock_issue(
            1,
            status_id=3,
            status_name="Done",
            done_ratio=100,
            estimated_hours=4.0,
            updated_on=datetime(2026, 9, 1, 9, 0, 0),
        )

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return [done]
            return []

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(1.5, issue_id=1, spent_on=date(2026, 9, 1)),
            _mock_entry(1.0, issue_id=1, spent_on=date(2026, 9, 2)),
            _mock_entry(2.0, issue_id=None),  # project-level: hours only
        ]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        assert result["totals"]["hours"] == 4.5
        tue = result["widget_data"]["Thứ 3"]
        assert [(t["id"], t["completed"]) for t in tue] == [(1, True)]
        assert tue[0]["hours"] == 1.5
        assert tue[0]["est"] == 4.0
        wed = result["widget_data"]["Thứ 4"]
        assert [(t["id"], t["completed"]) for t in wed] == [(1, False)]
        assert wed[0]["hours"] == 1.0
        assert wed[0]["est"] == 4.0

    @pytest.mark.asyncio
    async def test_widget_data_week_keys_in_order(self, mock_redmine):
        self._setup_backlog(mock_redmine, [])

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        assert list(result["widget_data"].keys()) == [
            "Thứ 2",
            "Thứ 3",
            "Thứ 4",
            "Thứ 5",
            "Thứ 6",
            "Thứ 7",
            "Chủ nhật",
        ]
        assert all(days == [] for days in result["widget_data"].values())

    @pytest.mark.asyncio
    async def test_day_window_returns_seven_keys(self, mock_redmine):
        self._setup_backlog(mock_redmine, [])

        result = await get_person_work_summary(7, date_str="2026-09-06")

        assert list(result["widget_data"].keys()) == [
            "Thứ 2",
            "Thứ 3",
            "Thứ 4",
            "Thứ 5",
            "Thứ 6",
            "Thứ 7",
            "Chủ nhật",
        ]
        assert all(days == [] for days in result["widget_data"].values())

    @pytest.mark.asyncio
    async def test_compact_omits_per_project(self, mock_redmine):
        issues = [_mock_issue(1, due=date.today() - timedelta(1))]
        self._setup_backlog(mock_redmine, issues)

        full = await get_person_work_summary(7, date_str="2026-09-02")
        assert "per_project" in full
        assert "widget_data" in full

        slim = await get_person_work_summary(7, date_str="2026-09-02", compact=True)
        assert "per_project" not in slim
        assert "widget_data" in slim
        assert slim["totals"] == full["totals"]

    @pytest.mark.asyncio
    async def test_hours_rounded_to_2dp(self, mock_redmine):
        done = _mock_issue(
            1,
            status_id=3,
            status_name="Done",
            done_ratio=100,
            estimated_hours=2.126,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return [done]
            return []

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(1.126, issue_id=1, spent_on=date(2026, 9, 2))
        ]

        result = await get_person_work_summary(7, date_str="2026-09-02")

        task = result["widget_data"]["Thứ 4"][0]
        assert task["est"] == 2.13
        assert task["hours"] == 1.13
        assert task["completed"] is True
        assert task["url"] == "https://redmine.example.com/issues/1"

    @pytest.mark.asyncio
    async def test_in_progress_logged_days_appear_not_completed(self, mock_redmine):
        """Open task with logs shows completed=false rows on logged days only."""
        working = _mock_issue(
            1,
            done_ratio=30,
            estimated_hours=5.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [working])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(2.0, issue_id=1, spent_on=date(2026, 9, 1)),
            _mock_entry(1.5, issue_id=1, spent_on=date(2026, 9, 2)),
        ]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        tue = result["widget_data"]["Thứ 3"]
        wed = result["widget_data"]["Thứ 4"]
        assert [(t["id"], t["completed"]) for t in tue] == [(1, False)]
        assert tue[0]["hours"] == 2.0
        assert [(t["id"], t["completed"]) for t in wed] == [(1, False)]
        assert wed[0]["hours"] == 1.5
        assert tue[0]["est"] == wed[0]["est"] == 5.0
        assert result["widget_data"]["Thứ 5"] == []
        assert result["totals"]["completed_count"] == 0

    @pytest.mark.asyncio
    async def test_in_progress_without_logs_absent(self, mock_redmine):
        """Open task with no time logs gets no widget row at all."""
        working = _mock_issue(
            1,
            done_ratio=30,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [working])
        mock_redmine.time_entry.filter.return_value = []

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        assert all(days == [] for days in result["widget_data"].values())
        assert result["totals"]["open_count"] == 1

    @pytest.mark.asyncio
    async def test_unresolvable_issue_logs_stay_in_totals_only(self, mock_redmine):
        """Logs for an unknown issue count in totals but get no DATA row."""
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(3.0, issue_id=99, spent_on=date(2026, 9, 2)),
        ]

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["hours"] == 3.0
        assert result["totals"]["time_entries"] == 1
        all_ids = [t["id"] for days in result["widget_data"].values() for t in days]
        assert 99 not in all_ids

    @pytest.mark.asyncio
    async def test_completed_true_exactly_once_across_week(self, mock_redmine):
        """Multi-day task: completed=true on the updated day only."""
        done = _mock_issue(
            1,
            status_id=3,
            status_name="Done",
            done_ratio=100,
            estimated_hours=5.0,
            updated_on=datetime(2026, 9, 2, 17, 0, 0),
        )

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return [done]
            return []

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(2.0, issue_id=1, spent_on=date(2026, 9, 1)),
            _mock_entry(1.0, issue_id=1, spent_on=date(2026, 9, 2)),
            _mock_entry(0.5, issue_id=1, spent_on=date(2026, 9, 3)),
        ]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        rows = [
            (day, t)
            for day, days in result["widget_data"].items()
            for t in days
            if t["id"] == 1
        ]
        assert len(rows) == 3
        assert [t["est"] for _, t in rows] == [5.0, 5.0, 5.0]
        completed_days = [day for day, t in rows if t["completed"] is True]
        assert completed_days == ["Thứ 4"]
        hours_by_day = {day: t["hours"] for day, t in rows}
        assert hours_by_day == {"Thứ 3": 2.0, "Thứ 4": 1.0, "Thứ 5": 0.5}
        assert result["totals"]["hours"] == 3.5

    @pytest.mark.asyncio
    async def test_backlog_splits_completed_from_open(self, mock_redmine):
        """Done+100% leaves the open backlog; counts stay consistent."""
        today = date.today()
        issues = [
            _mock_issue(
                1,
                status_id=3,
                status_name="Done",
                done_ratio=100,
                due=today - timedelta(10),
            ),
            _mock_issue(
                2,
                status_id=1,
                status_name="New",
                done_ratio=100,
                due=today - timedelta(5),
            ),
            _mock_issue(3, done_ratio=40, due=today - timedelta(2)),
            _mock_issue(4, done_ratio=30, due=today + timedelta(5)),
        ]
        self._setup_backlog(mock_redmine, issues)

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["completed_total"] == 1
        assert result["totals"]["open_count"] == 3
        assert result["totals"]["overdue_count"] == 2  # ids 2 and 3
        assert result["totals"]["completed_count"] == 0  # nothing touched
        overdue_ids = [
            t["id"] for p in result["per_project"] for t in p["backlog"]["overdue"]
        ]
        assert sorted(overdue_ids) == [2, 3]
        flags = {f["issue"]["id"] for f in result["data_quality_flags"]}
        assert flags == {2}

    @pytest.mark.asyncio
    async def test_closed_status_counts_completed(self, mock_redmine):
        """A closed status is completed even when done_ratio is below 100."""
        issues = [
            _mock_issue(
                1,
                status_id=5,
                status_name="Closed",
                done_ratio=80,
                due=date.today() - timedelta(4),
            ),
        ]
        self._setup_backlog(mock_redmine, issues)

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["completed_total"] == 1
        assert result["totals"]["open_count"] == 0
        assert result["totals"]["overdue_count"] == 0
        assert result["data_quality_flags"] == []

    @pytest.mark.asyncio
    async def test_done_below_100_is_flagged_and_open(self, mock_redmine):
        """Done status with ratio below 100 stays open and gets flagged."""
        issues = [
            _mock_issue(7, status_id=3, status_name="Done", done_ratio=0, due=None),
        ]
        self._setup_backlog(mock_redmine, issues)

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["completed_total"] == 0
        assert result["totals"]["open_count"] == 1
        assert result["totals"]["no_due_date_count"] == 1
        assert len(result["data_quality_flags"]) == 1
        assert result["data_quality_flags"][0]["issue"]["id"] == 7
        assert "below 100" in result["data_quality_flags"][0]["reason"]

    @pytest.mark.asyncio
    async def test_hours_scope_block_is_window_only(self, mock_redmine):
        """Evidence states hours cover only this user's logs in the window."""
        self._setup_backlog(mock_redmine, [])

        day = await get_person_work_summary(7, date_str="2026-09-02")
        scope = day["evidence"]["hours_scope"]
        assert scope["scope"] == "window_only"
        assert scope["user_id"] == 7
        assert scope["from"] == "2026-09-02"
        assert scope["to"] == "2026-09-02"
        assert "0.0" in scope["note"]

        week = await get_person_work_summary(7, window="week", date_str="2026-09-03")
        assert week["evidence"]["hours_scope"]["from"] == "2026-08-31"
        assert week["evidence"]["hours_scope"]["to"] == "2026-09-06"

    def _setup_week_context(self, mock_redmine):
        """Week 2026-08-31..2026-09-06: 1 done, 1 working w/ logs, 1 untouched."""
        done = _mock_issue(
            1,
            subject="Tích hợp thanh toán",
            status_id=3,
            status_name="Done",
            done_ratio=100,
            updated_on=datetime(2026, 9, 4, 15, 0, 0),
            description="Triển khai module thanh toán VNPay cho giỏ hàng.",
        )
        working = _mock_issue(
            2,
            subject="Màn hình báo cáo",
            done_ratio=30,
            updated_on=datetime(2026, 9, 3, 10, 0, 0),
            description="x" * 1600,
        )
        untouched = _mock_issue(
            3,
            subject="Việc tồn đọng",
            done_ratio=10,
            updated_on=datetime(2026, 8, 1, 10, 0, 0),
        )
        issues = [done, working, untouched]

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return [done, working]
            return issues

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(8.0, issue_id=1, spent_on=date(2026, 9, 4)),
            _mock_entry(2.0, issue_id=2, spent_on=date(2026, 9, 2)),
            _mock_entry(1.5, issue_id=2, spent_on=date(2026, 9, 3)),
        ]
        return done, working, untouched

    @pytest.mark.asyncio
    async def test_task_context_present_in_compact_mode(self, mock_redmine):
        """Compact keeps task_context: done + logged working, not untouched."""
        self._setup_week_context(mock_redmine)

        result = await get_person_work_summary(
            7, window="week", date_str="2026-09-03", compact=True
        )

        assert "per_project" not in result
        by_id = {t["id"]: t for t in result["task_context"]}
        assert set(by_id) == {1, 2}
        assert by_id[1]["completed"] is True
        assert by_id[1]["week_hours"] == 8.0
        assert "VNPay" in by_id[1]["description"]
        assert by_id[1]["url"] == "https://redmine.example.com/issues/1"
        assert by_id[2]["completed"] is False
        assert by_id[2]["week_hours"] == 3.5
        assert by_id[2]["status"] == "In Progress"

    @pytest.mark.asyncio
    async def test_task_context_truncates_long_description(self, mock_redmine):
        """1600-char description is cut to 1500 + ellipsis (inside wrap tags)."""
        self._setup_week_context(mock_redmine)

        result = await get_person_work_summary(
            7, window="week", date_str="2026-09-03", compact=True
        )

        desc = next(t for t in result["task_context"] if t["id"] == 2)["description"]
        assert "…" in desc
        assert desc.count("x") == 1500

    @pytest.mark.asyncio
    async def test_task_context_missing_description_is_empty(self, mock_redmine):
        """Issue without a description yields '' instead of crashing."""
        done, working, _untouched = self._setup_week_context(mock_redmine)
        del working.description

        result = await get_person_work_summary(
            7, window="week", date_str="2026-09-03", compact=True
        )

        desc = next(t for t in result["task_context"] if t["id"] == 2)["description"]
        assert desc == ""

    @pytest.mark.asyncio
    async def test_lifetime_hours_span_weeks(self, mock_redmine):
        """Out-of-window logs surface as total/prior; window numbers stay pure.

        Issue 2 has 3.5h in the viewed week plus 8.0h logged the prior
        week: week_hours stays 3.5 while lifetime/prior expose 11.5/8.0
        so overrun is judged on lifetime, not the window slice.
        """
        self._setup_week_context(mock_redmine)
        window_entries = mock_redmine.time_entry.filter.return_value

        def entry_filter(**kwargs):
            if "from_date" in kwargs:
                return window_entries
            return window_entries + [
                _mock_entry(8.0, issue_id=2, spent_on=date(2026, 8, 20)),
            ]

        mock_redmine.time_entry.filter.side_effect = entry_filter

        result = await get_person_work_summary(
            7, window="week", date_str="2026-09-03", compact=True
        )

        by_id = {t["id"]: t for t in result["task_context"]}
        assert by_id[2]["week_hours"] == 3.5
        assert by_id[2]["lifetime_hours"] == 11.5
        assert by_id[2]["prior_hours"] == 8.0
        assert by_id[1]["week_hours"] == 8.0
        assert by_id[1]["lifetime_hours"] == 8.0
        assert by_id[1]["prior_hours"] == 0.0

        friday_row = next(t for t in result["widget_data"]["Thứ 6"] if t["id"] == 1)
        assert friday_row["hours"] == 8.0
        assert friday_row["total"] == 8.0
        assert friday_row["completed"] is True
        thu_row = next(t for t in result["widget_data"]["Thứ 5"] if t["id"] == 2)
        assert thu_row["hours"] == 1.5
        assert thu_row["total"] == 11.5
        assert thu_row["completed"] is False
        # Window totals unchanged by the prior-week log.
        assert result["totals"]["hours"] == 11.5

    @pytest.mark.asyncio
    async def test_supporting_row_for_open_task_of_other_person(self, mock_redmine):
        """Hours on someone else's open task -> supporting row, not completed."""
        foreign = _mock_issue(
            99,
            subject="Task người khác",
            done_ratio=30,
            estimated_hours=8.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(2.0, issue_id=99, spent_on=date(2026, 9, 2)),
        ]
        mock_redmine.issue.get.side_effect = lambda iid: foreign

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        wed = result["widget_data"]["Thứ 4"]
        assert [(t["id"], t["completed"], t["role"]) for t in wed] == [
            (99, False, "supporting")
        ]
        assert wed[0]["hours"] == 2.0
        assert wed[0]["est"] == 8.0
        assert wed[0]["total"] == 2.0
        assert result["totals"]["completed_count"] == 0
        assert result["totals"]["open_count"] == 0  # not their backlog
        assert result["totals"]["hours"] == 2.0
        by_id = {t["id"]: t for t in result["task_context"]}
        assert by_id[99]["completed"] is False
        assert by_id[99]["role"] == "supporting"
        assert by_id[99]["week_hours"] == 2.0

    @pytest.mark.asyncio
    async def test_supported_row_for_closed_task_of_other_person(self, mock_redmine):
        """Hours on someone else's closed task -> supported, off the counts."""
        foreign = _mock_issue(
            99,
            subject="Task đã đóng",
            status_id=5,
            status_name="Closed",
            done_ratio=80,
            estimated_hours=8.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(1.5, issue_id=99, spent_on=date(2026, 9, 2)),
        ]
        mock_redmine.issue.get.side_effect = lambda iid: foreign

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        wed = result["widget_data"]["Thứ 4"]
        assert [(t["id"], t["completed"], t["role"]) for t in wed] == [
            (99, False, "supported")
        ]
        assert result["totals"]["completed_count"] == 0
        assert result["totals"]["completed_total"] == 0
        by_id = {t["id"]: t for t in result["task_context"]}
        assert by_id[99]["completed"] is False
        assert by_id[99]["role"] == "supported"

    @pytest.mark.asyncio
    async def test_owner_rows_keep_owner_role(self, mock_redmine):
        """Assigned task rows carry role=owner (regression guard)."""
        working = _mock_issue(
            1,
            done_ratio=30,
            estimated_hours=5.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [working])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(2.0, issue_id=1, spent_on=date(2026, 9, 2)),
        ]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        wed = result["widget_data"]["Thứ 4"]
        assert [(t["id"], t["completed"], t["role"]) for t in wed] == [
            (1, False, "owner")
        ]
        by_id = {t["id"]: t for t in result["task_context"]}
        assert by_id[1]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_contributor_fetch_failure_stays_in_totals(self, mock_redmine):
        """issue.get raising -> hours in totals, no row (graceful)."""
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(3.0, issue_id=99, spent_on=date(2026, 9, 2)),
        ]
        mock_redmine.issue.get.side_effect = RuntimeError("forbidden")

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["hours"] == 3.0
        all_ids = [t["id"] for days in result["widget_data"].values() for t in days]
        assert 99 not in all_ids
        assert 99 not in {t["id"] for t in result["task_context"]}

    @pytest.mark.asyncio
    async def test_multiple_contributor_issues_all_resolved(self, mock_redmine):
        """Batch path: several foreign logged issues each get their row."""
        helping = _mock_issue(
            98,
            subject="Task ké mở",
            done_ratio=20,
            estimated_hours=4.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        helped = _mock_issue(
            99,
            subject="Task ké đóng",
            status_id=5,
            status_name="Closed",
            done_ratio=80,
            estimated_hours=6.0,
            updated_on=datetime(2026, 9, 3, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(1.0, issue_id=98, spent_on=date(2026, 9, 2)),
            _mock_entry(2.0, issue_id=99, spent_on=date(2026, 9, 3)),
        ]
        mock_redmine.issue.get.side_effect = lambda iid: {98: helping, 99: helped}[iid]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        by_day_id = {
            (day, t["id"]): t["role"]
            for day, days in result["widget_data"].items()
            for t in days
        }
        assert by_day_id[("Thứ 4", 98)] == "supporting"
        assert by_day_id[("Thứ 5", 99)] == "supported"
        assert result["totals"]["hours"] == 3.0
        assert result["totals"]["completed_count"] == 0

    @pytest.mark.asyncio
    async def test_day_log_concatenates_same_day_comments(self, mock_redmine):
        """Two logs same day+issue -> one widget row, one joined log line."""
        working = _mock_issue(
            1,
            done_ratio=30,
            estimated_hours=5.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [working])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(
                2.0,
                issue_id=1,
                spent_on=date(2026, 9, 2),
                comments="test case đăng nhập",
                activity_name="Development",
            ),
            _mock_entry(
                1.5,
                issue_id=1,
                spent_on=date(2026, 9, 2),
                comments="fix lỗi hiển thị",
                activity_name="Development",
            ),
        ]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        wed = result["widget_data"]["Thứ 4"]
        assert len(wed) == 1
        assert wed[0]["hours"] == 3.5
        assert "test case đăng nhập (2.0h, Development)" in wed[0]["log"]
        assert "fix lỗi hiển thị (1.5h, Development)" in wed[0]["log"]
        by_id = {t["id"]: t for t in result["task_context"]}
        assert set(by_id[1]["daily_logs"]) == {"2026-09-02"}
        assert "fix lỗi hiển thị" in by_id[1]["daily_logs"]["2026-09-02"]

    @pytest.mark.asyncio
    async def test_day_log_empty_when_no_comment(self, mock_redmine):
        """Logs without comments still render hours; completed 0h row has ''."""
        done = _mock_issue(
            1,
            status_id=3,
            status_name="Done",
            done_ratio=100,
            estimated_hours=4.0,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )

        def issue_filter(**kwargs):
            if kwargs.get("status_id") == "*":
                return [done]
            return []

        mock_redmine.issue.filter.side_effect = issue_filter
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(2.0, issue_id=1, spent_on=date(2026, 9, 1)),
        ]

        result = await get_person_work_summary(7, window="week", date_str="2026-09-03")

        tue = result["widget_data"]["Thứ 3"]
        assert "(2.0h)" in tue[0]["log"]
        wed = result["widget_data"]["Thứ 4"]
        assert wed[0]["completed"] is True
        assert wed[0]["hours"] == 0.0
        assert wed[0]["log"] == ""

    @pytest.mark.asyncio
    async def test_day_log_truncated_to_1000_chars(self, mock_redmine):
        """A very long comment is cut to 1000 chars + ellipsis (in tags)."""
        working = _mock_issue(
            1,
            done_ratio=30,
            updated_on=datetime(2026, 9, 2, 9, 0, 0),
        )
        self._setup_backlog(mock_redmine, [working])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(
                1.0, issue_id=1, spent_on=date(2026, 9, 2), comments="y" * 1200
            ),
        ]

        result = await get_person_work_summary(7, date_str="2026-09-02")

        log = result["widget_data"]["Thứ 4"][0]["log"]
        assert "…" in log
        assert log.count("y") == 1000

    @pytest.mark.asyncio
    async def test_unlinked_logs_for_project_level_entries(self, mock_redmine):
        """Project-level logs (no issue) surface in unlinked_logs, not DATA."""
        self._setup_backlog(mock_redmine, [])
        mock_redmine.time_entry.filter.return_value = [
            _mock_entry(
                2.0,
                project_id=1,
                project_name="Web",
                issue_id=None,
                spent_on=date(2026, 9, 2),
                comments="họp dự án",
                activity_name="Meeting",
            ),
        ]

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["totals"]["hours"] == 2.0
        assert all(days == [] for days in result["widget_data"].values())
        assert len(result["unlinked_logs"]) == 1
        row = result["unlinked_logs"][0]
        assert row["date"] == "2026-09-02"
        assert row["hours"] == 2.0
        assert "họp dự án" in row["comment"]
        assert row["project"] == "Web"
        assert row["activity"] == "Meeting"

    @pytest.mark.asyncio
    async def test_unlinked_logs_empty_by_default(self, mock_redmine):
        """Responses without project-level logs carry an empty list."""
        self._setup_backlog(mock_redmine, [])

        result = await get_person_work_summary(7, date_str="2026-09-02")

        assert result["unlinked_logs"] == []
