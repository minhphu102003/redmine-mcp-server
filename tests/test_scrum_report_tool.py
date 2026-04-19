"""Tests for scrum report generation tool and analytics helper."""

from datetime import date
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import redmine_handler  # noqa: E402
from redmine_mcp_server.handler_impl.tools import analytics  # noqa: E402
from redmine_mcp_server.handler_impl.tools.analytics import (  # noqa: E402
    _resolve_scrum_issue_fetch_concurrency,
    _resolve_scrum_report_range,
    export_weekly_report_docx_impl,
    export_weekly_report_markdown_impl,
    generate_scrum_report_impl,
)


def test_resolve_scrum_report_range_daily_uses_yesterday():
    resolved = _resolve_scrum_report_range(
        report_type="daily",
        from_date=None,
        to_date=None,
        reference_date=date(2026, 4, 19),
    )
    assert resolved["from_date"] == "2026-04-18"
    assert resolved["to_date"] == "2026-04-18"


def test_resolve_scrum_report_range_weekly_uses_previous_week():
    resolved = _resolve_scrum_report_range(
        report_type="weekly",
        from_date=None,
        to_date=None,
        reference_date=date(2026, 4, 19),  # Sunday
    )
    assert resolved["from_date"] == "2026-04-06"
    assert resolved["to_date"] == "2026-04-12"


@pytest.mark.asyncio
async def test_generate_scrum_report_impl_returns_error_for_invalid_custom_range():
    result = await generate_scrum_report_impl(
        report_type="custom",
        from_date="2026-04-10",
        to_date=None,
        get_client=lambda: None,
        time_entry_to_dict=lambda entry: {},
        wrap_content=lambda value: value,
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )
    assert "error" in result
    assert "from_date and to_date are required" in result["error"]


def test_resolve_scrum_report_range_custom_rejects_large_window():
    resolved = _resolve_scrum_report_range(
        report_type="custom",
        from_date="2026-01-01",
        to_date="2026-02-15",
        max_days=31,
    )
    assert "error" in resolved
    assert "Custom report range too large" in resolved["error"]


def test_resolve_scrum_issue_fetch_concurrency_from_env(monkeypatch):
    monkeypatch.setenv("REDMINE_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY", "8")
    assert _resolve_scrum_issue_fetch_concurrency() == 8


@pytest.mark.asyncio
async def test_generate_scrum_report_impl_builds_summary_payload():
    entries = [
        SimpleNamespace(
            id=1,
            hours=2.5,
            spent_on=date(2026, 4, 18),
            issue=SimpleNamespace(id=101, name="Fix login flow"),
            activity=SimpleNamespace(id=10, name="Development"),
            user=SimpleNamespace(id=1, name="Alice"),
        ),
        SimpleNamespace(
            id=2,
            hours=1.5,
            spent_on=date(2026, 4, 18),
            issue=SimpleNamespace(id=102, name="Write tests"),
            activity=SimpleNamespace(id=11, name="Testing"),
            user=SimpleNamespace(id=1, name="Alice"),
        ),
    ]
    client = SimpleNamespace(
        time_entry=SimpleNamespace(filter=lambda **kwargs: entries),
    )
    result = await generate_scrum_report_impl(
        report_type="daily",
        user_id=1,
        get_client=lambda: client,
        time_entry_to_dict=lambda entry: {"id": entry.id, "hours": entry.hours},
        wrap_content=lambda value: f"<wrapped>{value}</wrapped>",
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )

    assert result["summary"]["total_hours"] == 4.0
    assert result["summary"]["total_entries"] == 2
    assert result["top_issues"][0]["issue_subject"].startswith("<wrapped>")
    assert result["top_users"][0]["user_name"].startswith("<wrapped>")
    assert result["top_issues"][0]["summary_line"].startswith("- #")
    assert result["top_issues"][0]["description_line"].startswith("  desc:")
    assert "Daily Scrum Report Draft" in result["report_draft"]
    assert "standup_three_questions" in result["report_templates"]
    assert "standup_workflow_focused" in result["report_templates"]
    assert "weekly_status_summary" in result["report_templates"]
    weekly_template = result["report_templates"]["weekly_status_summary"]
    assert "- Continue/close:" in weekly_template
    assert "- Continue/close:   desc:" not in weekly_template


@pytest.mark.asyncio
async def test_generate_scrum_report_impl_fetches_issue_details_for_top_items_only():
    entries = [
        SimpleNamespace(
            id=1,
            hours=5.0,
            spent_on=date(2026, 4, 18),
            issue=SimpleNamespace(id=101, name="A"),
            activity=SimpleNamespace(id=10, name="Development"),
            user=SimpleNamespace(id=1, name="Alice"),
            project=SimpleNamespace(id=1, name="Core"),
        ),
        SimpleNamespace(
            id=2,
            hours=4.0,
            spent_on=date(2026, 4, 18),
            issue=SimpleNamespace(id=102, name="B"),
            activity=SimpleNamespace(id=10, name="Development"),
            user=SimpleNamespace(id=1, name="Alice"),
            project=SimpleNamespace(id=1, name="Core"),
        ),
        SimpleNamespace(
            id=3,
            hours=3.0,
            spent_on=date(2026, 4, 18),
            issue=SimpleNamespace(id=103, name="C"),
            activity=SimpleNamespace(id=10, name="Development"),
            user=SimpleNamespace(id=1, name="Alice"),
            project=SimpleNamespace(id=1, name="Core"),
        ),
    ]
    issue_get_calls = []

    def _get_issue(issue_id):
        issue_get_calls.append(issue_id)
        return SimpleNamespace(
            id=issue_id,
            subject=f"Issue {issue_id}",
            project=SimpleNamespace(name="Core"),
            status=SimpleNamespace(name="In Progress"),
            priority=SimpleNamespace(name="High"),
            assigned_to=SimpleNamespace(name="Alice"),
            updated_on=date(2026, 4, 18),
            description="Desc",
        )

    client = SimpleNamespace(
        time_entry=SimpleNamespace(filter=lambda **kwargs: entries),
        issue=SimpleNamespace(get=_get_issue),
    )
    result = await generate_scrum_report_impl(
        report_type="daily",
        user_id=1,
        top_n_items=2,
        get_client=lambda: client,
        time_entry_to_dict=lambda entry: {"id": entry.id, "hours": entry.hours},
        wrap_content=lambda value: str(value),
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )

    assert len(result["top_issues"]) == 2
    assert sorted(issue_get_calls) == [101, 102]


@pytest.mark.asyncio
async def test_generate_scrum_report_impl_fetches_issue_details_via_to_thread():
    entries = [
        SimpleNamespace(
            id=1,
            hours=5.0,
            spent_on=date(2026, 4, 18),
            issue=SimpleNamespace(id=101, name="A"),
            activity=SimpleNamespace(id=10, name="Development"),
            user=SimpleNamespace(id=1, name="Alice"),
            project=SimpleNamespace(id=1, name="Core"),
        )
    ]

    def _get_issue(issue_id):
        return SimpleNamespace(
            id=issue_id,
            subject=f"Issue {issue_id}",
            project=SimpleNamespace(name="Core"),
            status=SimpleNamespace(name="In Progress"),
            priority=SimpleNamespace(name="High"),
            assigned_to=SimpleNamespace(name="Alice"),
            updated_on=date(2026, 4, 18),
            description="Desc",
        )

    client = SimpleNamespace(
        time_entry=SimpleNamespace(filter=lambda **kwargs: entries),
        issue=SimpleNamespace(get=_get_issue),
    )

    async def _fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch.object(
        analytics.asyncio, "to_thread", AsyncMock(side_effect=_fake_to_thread)
    ) as mock_to_thread:
        result = await generate_scrum_report_impl(
            report_type="daily",
            user_id=1,
            top_n_items=1,
            get_client=lambda: client,
            time_entry_to_dict=lambda entry: {"id": entry.id, "hours": entry.hours},
            wrap_content=lambda value: str(value),
            handle_error=lambda exc, op, ctx: {"error": str(exc)},
        )

    assert result["top_issues"][0]["issue_id"] == 101
    assert mock_to_thread.await_count >= 2


@pytest.mark.asyncio
async def test_generate_scrum_report_tool_delegates_to_impl():
    payload = {"report_type": "daily", "summary": {"total_hours": 3}}
    with patch.object(
        redmine_handler,
        "generate_scrum_report_impl",
        AsyncMock(return_value=payload),
    ) as mock_impl:
        result = await redmine_handler.generate_scrum_report(report_type="daily")

    assert result == payload
    assert mock_impl.await_count == 1


@pytest.mark.asyncio
async def test_export_weekly_report_markdown_impl_writes_file(tmp_path, monkeypatch):
    template_path = tmp_path / "weekly_template.md"
    template_path.write_text(
        (
            "BÁO CÁO CÔNG TÁC TUẦN {{tuan_bao_cao}}\n"
            "{{#bao_cao_items}}- {{cong_viec}} | {{phan_tram_hoan_thanh}} | {{mo_ta}}\n"
            "{{/bao_cao_items}}"
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_TEMPLATE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_OUTPUT_BASE_DIR", str(tmp_path))

    async def _fake_generate_scrum_report_fn(**kwargs):
        return {
            "analysis_range": {
                "from_date": "2026-04-06",
                "to_date": "2026-04-12",
            },
            "summary": {"total_hours": 10.0},
            "top_issues": [
                {
                    "issue_subject": "Fix login flow",
                    "description_excerpt": "Complete OAuth flow",
                    "status_raw": "In Progress",
                }
            ],
        }

    result = await export_weekly_report_markdown_impl(
        generate_scrum_report_fn=_fake_generate_scrum_report_fn,
        template_path=str(template_path),
        output_dir=str(output_dir),
        file_name="weekly.md",
        reporter_name="Nguyen Minh Phu",
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )

    assert result["exported"] is True
    output_path = output_dir / "weekly.md"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "BÁO CÁO CÔNG TÁC TUẦN" in content
    assert "Fix login flow" in content


@pytest.mark.asyncio
async def test_export_weekly_report_markdown_tool_delegates_to_impl():
    payload = {"exported": True, "output_path": "reports/weekly/sample.md"}
    with patch.object(
        redmine_handler,
        "export_weekly_report_markdown_impl",
        AsyncMock(return_value=payload),
    ) as mock_impl:
        result = await redmine_handler.export_weekly_report_markdown(project_id=12)

    assert result == payload
    assert mock_impl.await_count == 1


@pytest.mark.asyncio
async def test_export_weekly_report_docx_impl_writes_docx_file(tmp_path, monkeypatch):
    template_path = tmp_path / "weekly_template.md"
    template_path.write_text("BÁO CÁO CÔNG TÁC TUẦN {{tuan_bao_cao}}", encoding="utf-8")
    output_dir = tmp_path / "out"
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_TEMPLATE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_OUTPUT_BASE_DIR", str(tmp_path))

    async def _fake_generate_scrum_report_fn(**kwargs):
        return {
            "analysis_range": {
                "from_date": "2026-04-06",
                "to_date": "2026-04-12",
            },
            "summary": {"total_hours": 10.0},
            "top_issues": [],
        }

    result = await export_weekly_report_docx_impl(
        generate_scrum_report_fn=_fake_generate_scrum_report_fn,
        template_path=str(template_path),
        output_dir=str(output_dir),
        file_name="weekly-client.docx",
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )

    assert result["exported"] is True
    docx_path = output_dir / "weekly-client.docx"
    assert docx_path.exists()
    assert docx_path.stat().st_size > 0


@pytest.mark.asyncio
async def test_export_weekly_report_docx_tool_delegates_to_impl():
    payload = {"exported": True, "output_path": "reports/weekly/sample.docx"}
    with patch.object(
        redmine_handler,
        "export_weekly_report_docx_impl",
        AsyncMock(return_value=payload),
    ) as mock_impl:
        result = await redmine_handler.export_weekly_report_docx(project_id=12)

    assert result == payload
    assert mock_impl.await_count == 1


@pytest.mark.asyncio
async def test_export_weekly_report_markdown_rejects_path_traversal_file_name(
    tmp_path, monkeypatch
):
    template_base = tmp_path / "templates"
    output_base = tmp_path / "reports"
    template_base.mkdir(parents=True, exist_ok=True)
    output_base.mkdir(parents=True, exist_ok=True)
    template_path = template_base / "weekly.md"
    template_path.write_text("{{tuan_bao_cao}}", encoding="utf-8")

    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_TEMPLATE_BASE_DIR", str(template_base))
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_OUTPUT_BASE_DIR", str(output_base))

    async def _fake_generate_scrum_report_fn(**kwargs):
        return {
            "analysis_range": {"from_date": "2026-04-06", "to_date": "2026-04-12"},
            "summary": {"total_hours": 10.0},
            "top_issues": [],
        }

    result = await export_weekly_report_markdown_impl(
        generate_scrum_report_fn=_fake_generate_scrum_report_fn,
        template_path=str(template_path),
        output_dir=str(output_base),
        file_name="../../evil.md",
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )
    assert "error" in result
    assert "Path separators are not allowed" in result["error"]


@pytest.mark.asyncio
async def test_export_weekly_report_markdown_rejects_template_path_outside_base(
    tmp_path, monkeypatch
):
    template_base = tmp_path / "templates"
    output_base = tmp_path / "reports"
    template_base.mkdir(parents=True, exist_ok=True)
    output_base.mkdir(parents=True, exist_ok=True)
    outside_template = tmp_path / "outside.md"
    outside_template.write_text("{{tuan_bao_cao}}", encoding="utf-8")

    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_TEMPLATE_BASE_DIR", str(template_base))
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_OUTPUT_BASE_DIR", str(output_base))

    async def _fake_generate_scrum_report_fn(**kwargs):
        return {
            "analysis_range": {"from_date": "2026-04-06", "to_date": "2026-04-12"},
            "summary": {"total_hours": 10.0},
            "top_issues": [],
        }

    result = await export_weekly_report_markdown_impl(
        generate_scrum_report_fn=_fake_generate_scrum_report_fn,
        template_path=str(outside_template),
        output_dir=str(output_base),
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )
    assert "error" in result
    assert "template_path must stay within" in result["error"]


@pytest.mark.asyncio
async def test_export_weekly_report_markdown_returns_clear_error_when_template_missing(
    tmp_path, monkeypatch
):
    template_base = tmp_path / "templates"
    output_base = tmp_path / "reports"
    template_base.mkdir(parents=True, exist_ok=True)
    output_base.mkdir(parents=True, exist_ok=True)
    missing_template = template_base / "missing.md"

    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_TEMPLATE_BASE_DIR", str(template_base))
    monkeypatch.setenv("REDMINE_WEEKLY_REPORT_OUTPUT_BASE_DIR", str(output_base))

    async def _fake_generate_scrum_report_fn(**kwargs):
        return {
            "analysis_range": {"from_date": "2026-04-06", "to_date": "2026-04-12"},
            "summary": {"total_hours": 10.0},
            "top_issues": [],
        }

    result = await export_weekly_report_markdown_impl(
        generate_scrum_report_fn=_fake_generate_scrum_report_fn,
        template_path=str(missing_template),
        output_dir=str(output_base),
        handle_error=lambda exc, op, ctx: {"error": str(exc)},
    )
    assert "error" in result
    assert "Weekly report template not found" in result["error"]
