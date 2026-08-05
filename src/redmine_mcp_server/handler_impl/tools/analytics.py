"""Undecorated analytics tool implementations extracted from redmine_handler."""

from __future__ import annotations

import asyncio
import io
import os
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type, Union
from xml.sax.saxutils import escape

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

_DEFAULT_SCRUM_REPORT_MAX_DAYS = 31
_MAX_SCRUM_REPORT_MAX_DAYS = 365
_DEFAULT_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY = 5
_MAX_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY = 20
_DEFAULT_WEEKLY_REPORT_TEMPLATE_PATH = (
    "docs/templates/weekly_work_report_plan_template.md"
)
_DEFAULT_WEEKLY_REPORT_OUTPUT_DIR = "reports/weekly"
_DEFAULT_WEEKLY_REPORT_TEMPLATE_BASE_DIR = "docs/templates"
_DEFAULT_WEEKLY_REPORT_OUTPUT_BASE_DIR = "reports"
_PROJECT_ROOT_DIR = Path(__file__).resolve().parents[4]


def _resolve_scrum_report_max_days() -> int:
    """Resolve max custom report range from env with safe bounds."""
    raw = os.getenv(
        "REDMINE_SCRUM_REPORT_MAX_DAYS",
        str(_DEFAULT_SCRUM_REPORT_MAX_DAYS),
    ).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_SCRUM_REPORT_MAX_DAYS
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_SCRUM_REPORT_MAX_DAYS)


def _resolve_scrum_issue_fetch_concurrency() -> int:
    """Resolve max concurrent issue detail fetches for scrum report enrichment."""
    raw = os.getenv(
        "REDMINE_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY",
        str(_DEFAULT_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY),
    ).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_SCRUM_REPORT_ISSUE_FETCH_CONCURRENCY)


def _resolve_weekly_report_template_path(custom_path: Optional[str] = None) -> Path:
    """Resolve weekly report markdown template path."""
    configured_path = (custom_path or "").strip() or os.getenv(
        "REDMINE_WEEKLY_REPORT_TEMPLATE_PATH",
        _DEFAULT_WEEKLY_REPORT_TEMPLATE_PATH,
    )
    template_candidate = Path(configured_path).expanduser()
    template_path = (
        template_candidate.resolve()
        if template_candidate.is_absolute()
        else (_PROJECT_ROOT_DIR / template_candidate).resolve()
    )
    template_base_candidate = Path(
        os.getenv(
            "REDMINE_WEEKLY_REPORT_TEMPLATE_BASE_DIR",
            _DEFAULT_WEEKLY_REPORT_TEMPLATE_BASE_DIR,
        )
    ).expanduser()
    template_base_dir = (
        template_base_candidate.resolve()
        if template_base_candidate.is_absolute()
        else (_PROJECT_ROOT_DIR / template_base_candidate).resolve()
    )
    if template_path.suffix.lower() != ".md":
        raise ValueError(
            f"Invalid template_path extension '{template_path.suffix}'. Expected .md."
        )
    if not _is_within_directory(template_path, template_base_dir):
        raise ValueError(
            f"template_path must stay within {template_base_dir}: {template_path}"
        )
    return template_path


def _resolve_weekly_report_output_dir(custom_dir: Optional[str] = None) -> Path:
    """Resolve output directory for generated weekly markdown reports."""
    configured_dir = (custom_dir or "").strip() or os.getenv(
        "REDMINE_WEEKLY_REPORT_OUTPUT_DIR",
        _DEFAULT_WEEKLY_REPORT_OUTPUT_DIR,
    )
    output_candidate = Path(configured_dir).expanduser()
    output_dir = (
        output_candidate.resolve()
        if output_candidate.is_absolute()
        else (_PROJECT_ROOT_DIR / output_candidate).resolve()
    )
    output_base_candidate = Path(
        os.getenv(
            "REDMINE_WEEKLY_REPORT_OUTPUT_BASE_DIR",
            _DEFAULT_WEEKLY_REPORT_OUTPUT_BASE_DIR,
        )
    ).expanduser()
    output_base_dir = (
        output_base_candidate.resolve()
        if output_base_candidate.is_absolute()
        else (_PROJECT_ROOT_DIR / output_base_candidate).resolve()
    )
    if not _is_within_directory(output_dir, output_base_dir):
        raise ValueError(f"output_dir must stay within {output_base_dir}: {output_dir}")
    return output_dir


def _is_within_directory(path: Path, base_dir: Path) -> bool:
    """Return True when path is equal to or nested inside base_dir."""
    try:
        path.relative_to(base_dir)
        return True
    except ValueError:
        return False


def _validate_export_file_name(file_name: str, expected_suffix: str) -> str:
    """Validate user-provided export file name to avoid traversal."""
    candidate = (file_name or "").strip()
    if not candidate:
        raise ValueError("file_name cannot be empty.")
    path_like = Path(candidate)
    if path_like.name != candidate or path_like.parent != Path("."):
        raise ValueError(
            f"Invalid file_name '{candidate}'. Path separators are not allowed."
        )
    if not candidate.lower().endswith(expected_suffix.lower()):
        candidate = f"{candidate}{expected_suffix}"
    return candidate


def _replace_loop_block(
    template: str,
    section_name: str,
    rows: List[Dict[str, str]],
) -> str:
    """Replace simple loop blocks like {{#section}}...{{/section}}."""
    start_tag = f"{{{{#{section_name}}}}}"
    end_tag = f"{{{{/{section_name}}}}}"
    start_idx = template.find(start_tag)
    end_idx = template.find(end_tag)
    if start_idx == -1 or end_idx == -1 or end_idx < start_idx:
        return template

    block_start = start_idx + len(start_tag)
    block_template = template[block_start:end_idx]
    rendered_blocks: List[str] = []
    for row in rows:
        row_block = block_template
        for key, value in row.items():
            row_block = row_block.replace(f"{{{{{key}}}}}", str(value))
        rendered_blocks.append(row_block)

    return (
        template[:start_idx]
        + "".join(rendered_blocks)
        + template[end_idx + len(end_tag) :]
    )


def _render_weekly_report_template(
    *,
    template_text: str,
    context: Dict[str, str],
    bao_cao_items: List[Dict[str, str]],
    ke_hoach_items: List[Dict[str, str]],
) -> str:
    """Render weekly work report template with scalar and loop placeholders."""
    rendered = _replace_loop_block(template_text, "bao_cao_items", bao_cao_items)
    rendered = _replace_loop_block(rendered, "ke_hoach_items", ke_hoach_items)
    for key, value in context.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))
    return rendered


def _build_minimal_docx_from_text(text: str) -> bytes:
    """Build a minimal plain-text .docx payload from input lines."""
    paragraphs: List[str] = []
    for raw_line in (text or "").splitlines():
        line = raw_line if raw_line else ""
        safe = escape(line)
        if line.strip() == "":
            paragraphs.append("<w:p/>")
            continue
        paragraphs.append(
            '<w:p><w:r><w:t xml:space="preserve">' f"{safe}" "</w:t></w:r></w:p>"
        )

    document_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            (
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships">'
            ),
            f"<w:body>{''.join(paragraphs)}<w:sectPr/></w:body>",
            "</w:document>",
        ]
    )
    content_types_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',  # noqa: E501
            (
                '  <Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.'
                'relationships+xml"/>'
            ),
            '  <Default Extension="xml" ContentType="application/xml"/>',
            (
                '  <Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'wordprocessingml.document.main+xml"/>'
            ),
            (
                '  <Override PartName="/docProps/core.xml" '
                'ContentType="application/vnd.openxmlformats-package.'
                'core-properties+xml"/>'
            ),
            (
                '  <Override PartName="/docProps/app.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.'
                'extended-properties+xml"/>'
            ),
            "</Types>",
            "",
        ]
    )
    root_rels_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            (
                "<Relationships "
                'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            ),
            (
                '  <Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/officeDocument" '
                'Target="word/document.xml"/>'
            ),
            (
                '  <Relationship Id="rId2" '
                'Type="http://schemas.openxmlformats.org/package/2006/'
                'relationships/metadata/core-properties" '
                'Target="docProps/core.xml"/>'
            ),
            (
                '  <Relationship Id="rId3" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                'relationships/extended-properties" '
                'Target="docProps/app.xml"/>'
            ),
            "</Relationships>",
            "",
        ]
    )
    now_utc = datetime.now(timezone.utc).isoformat()
    core_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            (
                "<cp:coreProperties "
                'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
                'core-properties"'
            ),
            ' xmlns:dc="http://purl.org/dc/elements/1.1/"',
            ' xmlns:dcterms="http://purl.org/dc/terms/"',
            ' xmlns:dcmitype="http://purl.org/dc/dcmitype/"',
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
            "  <dc:title>Weekly Work Report</dc:title>",
            "  <dc:creator>Redmine MCP Server</dc:creator>",
            "  <cp:lastModifiedBy>Redmine MCP Server</cp:lastModifiedBy>",
            (
                '  <dcterms:created xsi:type="dcterms:W3CDTF">'
                f"{now_utc}</dcterms:created>"
            ),
            (
                '  <dcterms:modified xsi:type="dcterms:W3CDTF">'
                f"{now_utc}</dcterms:modified>"
            ),
            "</cp:coreProperties>",
            "",
        ]
    )
    app_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            (
                '<Properties xmlns="http://schemas.openxmlformats.org/'
                'officeDocument/2006/extended-properties"'
            ),
            (
                ' xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
                'docPropsVTypes">'
            ),
            "  <Application>Redmine MCP Server</Application>",
            "</Properties>",
            "",
        ]
    )
    doc_rels_xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            (
                "<Relationships "
                'xmlns="http://schemas.openxmlformats.org/package/2006/'
                'relationships"></Relationships>'
            ),
            "",
        ]
    )

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels_xml)
        zf.writestr("docProps/core.xml", core_xml)
        zf.writestr("docProps/app.xml", app_xml)
    return stream.getvalue()


def _resolve_scrum_report_range(
    *,
    report_type: str,
    from_date: Optional[str],
    to_date: Optional[str],
    reference_date: Optional[date] = None,
    max_days: Optional[int] = None,
) -> Union[Dict[str, str], Dict[str, Any]]:
    """Resolve daily/weekly/custom date windows for scrum report generation."""
    today = reference_date or date.today()
    normalized_type = (report_type or "").strip().lower()
    max_window_days = max_days or _resolve_scrum_report_max_days()

    if normalized_type == "daily":
        yesterday = today - timedelta(days=1)
        return {
            "report_type": "daily",
            "from_date": yesterday.isoformat(),
            "to_date": yesterday.isoformat(),
            "label": "yesterday",
        }

    if normalized_type == "weekly":
        start_of_current_week = today - timedelta(days=today.weekday())
        start_of_last_week = start_of_current_week - timedelta(days=7)
        end_of_last_week = start_of_current_week - timedelta(days=1)
        return {
            "report_type": "weekly",
            "from_date": start_of_last_week.isoformat(),
            "to_date": end_of_last_week.isoformat(),
            "label": "last_week",
        }

    if normalized_type == "custom":
        if not from_date or not to_date:
            return {
                "error": (
                    "from_date and to_date are required when report_type='custom'."
                )
            }
        try:
            parsed_from = date.fromisoformat(from_date)
            parsed_to = date.fromisoformat(to_date)
        except ValueError:
            return {"error": "from_date and to_date must use YYYY-MM-DD format."}
        if parsed_from > parsed_to:
            return {"error": "from_date must be less than or equal to to_date."}
        window_days = (parsed_to - parsed_from).days + 1
        if window_days > max_window_days:
            return {
                "error": (
                    f"Custom report range too large ({window_days} days). "
                    f"Maximum supported is {max_window_days} days."
                )
            }
        return {
            "report_type": "custom",
            "from_date": parsed_from.isoformat(),
            "to_date": parsed_to.isoformat(),
            "label": "custom",
        }

    return {"error": "Invalid report_type. Supported values: daily, weekly, custom."}


def _iso_date(value: Any) -> Optional[str]:
    """Convert date-like values to YYYY-MM-DD."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    return text


def _extract_description_excerpt(value: Any, max_len: int = 180) -> str:
    """Build a compact single-line description excerpt."""
    text = str(value or "").strip()
    if not text:
        return ""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return f"{collapsed[: max_len - 1].rstrip()}..."


def _safe_name(value: Any, default: str) -> str:
    """Normalize optional nested names to safe display text."""
    text = str(value or "").strip()
    return text or default


async def _fetch_issue_details_map(
    *,
    client: Any,
    issue_ids: List[int],
    max_concurrency: int = 5,
) -> Dict[int, Any]:
    """Fetch issue details concurrently without blocking the event loop."""
    if not issue_ids:
        return {}

    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def _fetch_one(issue_id: int) -> tuple[int, Any]:
        async with semaphore:
            try:
                issue = await asyncio.to_thread(client.issue.get, issue_id)
            except Exception:
                issue = None
            return issue_id, issue

    results = await asyncio.gather(*[_fetch_one(issue_id) for issue_id in issue_ids])
    return {issue_id: issue for issue_id, issue in results}


async def generate_scrum_report_impl(
    report_type: str = "daily",
    user_id: Optional[Union[str, int]] = None,
    project_id: Optional[Union[str, int]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    top_n_items: int = 7,
    include_entries: bool = False,
    *,
    get_client: Callable[[], Any],
    time_entry_to_dict: Callable[[Any], Dict[str, Any]],
    wrap_content: Callable[[Any], str],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Generate an auto-draft scrum report from Redmine time entries."""
    try:
        resolved_range = _resolve_scrum_report_range(
            report_type=report_type,
            from_date=from_date,
            to_date=to_date,
        )
        if "error" in resolved_range:
            return resolved_range

        filters: Dict[str, Any] = {
            "from_date": resolved_range["from_date"],
            "to_date": resolved_range["to_date"],
        }
        if user_id is not None:
            filters["user_id"] = user_id
        if project_id is not None:
            filters["project_id"] = project_id

        client = get_client()
        time_entries = await asyncio.to_thread(
            lambda: list(client.time_entry.filter(**filters))
        )
        total_hours = 0.0
        by_issue: Dict[str, Dict[str, Any]] = {}
        by_activity: Dict[str, Dict[str, Any]] = {}
        by_day: Dict[str, Dict[str, Any]] = {}
        by_user: Dict[str, Dict[str, Any]] = {}
        unique_users = set()

        for entry in time_entries:
            hours = float(getattr(entry, "hours", 0) or 0)
            total_hours += hours

            spent_on_key = _iso_date(getattr(entry, "spent_on", None)) or "unknown"
            day_bucket = by_day.setdefault(
                spent_on_key, {"date": spent_on_key, "hours": 0.0, "entries": 0}
            )
            day_bucket["hours"] += hours
            day_bucket["entries"] += 1

            entry_user = getattr(entry, "user", None)
            user_id_value = getattr(entry_user, "id", None) if entry_user else None
            user_name = getattr(entry_user, "name", "") if entry_user else ""
            if user_name:
                unique_users.add(str(user_name))
            user_key = (
                str(user_id_value)
                if user_id_value is not None
                else str(user_name or "unknown")
            )
            user_bucket = by_user.setdefault(
                user_key,
                {
                    "user_id": user_id_value,
                    "user_name": wrap_content(user_name or "Unknown"),
                    "hours": 0.0,
                    "entries": 0,
                },
            )
            user_bucket["hours"] += hours
            user_bucket["entries"] += 1

            issue = getattr(entry, "issue", None)
            issue_id = getattr(issue, "id", None) if issue else None
            issue_name_raw = (
                getattr(issue, "name", None) or getattr(issue, "subject", None)
                if issue
                else None
            )
            project_obj = getattr(entry, "project", None)
            issue_key = str(issue_id) if issue_id is not None else "no_issue"
            issue_bucket = by_issue.setdefault(
                issue_key,
                {
                    "issue_id": issue_id,
                    "issue_subject_raw": issue_name_raw or "No linked issue",
                    "project_name_raw": getattr(project_obj, "name", None)
                    or "Unknown project",
                    "status_raw": "Unknown",
                    "priority_raw": "Unknown",
                    "assignee_raw": "Unassigned",
                    "updated_on": None,
                    "description_excerpt_raw": "",
                    "hours": 0.0,
                    "entries": 0,
                },
            )
            issue_bucket["hours"] += hours
            issue_bucket["entries"] += 1

            activity = getattr(entry, "activity", None)
            activity_id = getattr(activity, "id", None) if activity else None
            activity_name = wrap_content(
                _safe_name(
                    getattr(activity, "name", None) if activity else None,
                    "Unspecified",
                )
            )
            activity_key = str(activity_id) if activity_id is not None else "unknown"
            activity_bucket = by_activity.setdefault(
                activity_key,
                {
                    "activity_id": activity_id,
                    "activity_name": activity_name,
                    "hours": 0.0,
                    "entries": 0,
                },
            )
            activity_bucket["hours"] += hours
            activity_bucket["entries"] += 1

        sorted_issues = sorted(
            by_issue.values(),
            key=lambda item: (item["hours"], item["entries"]),
            reverse=True,
        )
        sorted_activities = sorted(
            by_activity.values(),
            key=lambda item: (item["hours"], item["entries"]),
            reverse=True,
        )
        sorted_users = sorted(
            by_user.values(),
            key=lambda item: (item["hours"], item["entries"]),
            reverse=True,
        )

        top_limit = max(1, min(top_n_items, 20))
        top_issues = sorted_issues[:top_limit]
        top_issue_ids = [
            int(issue_item["issue_id"])
            for issue_item in top_issues
            if issue_item.get("issue_id") is not None
        ]
        issue_details_by_id = await _fetch_issue_details_map(
            client=client,
            issue_ids=top_issue_ids,
            max_concurrency=_resolve_scrum_issue_fetch_concurrency(),
        )

        for issue_item in top_issues:
            issue_id = issue_item.get("issue_id")
            if issue_id is None:
                continue
            issue_data = issue_details_by_id.get(int(issue_id))
            if issue_data is None:
                continue
            issue_item["issue_subject_raw"] = (
                getattr(issue_data, "subject", None)
                or getattr(issue_data, "name", None)
                or issue_item.get("issue_subject_raw")
            )
            issue_item["project_name_raw"] = _safe_name(
                getattr(getattr(issue_data, "project", None), "name", None),
                issue_item.get("project_name_raw", "Unknown project"),
            )
            issue_item["status_raw"] = _safe_name(
                getattr(getattr(issue_data, "status", None), "name", None),
                "Unknown",
            )
            issue_item["priority_raw"] = _safe_name(
                getattr(getattr(issue_data, "priority", None), "name", None),
                "Unknown",
            )
            issue_item["assignee_raw"] = _safe_name(
                getattr(getattr(issue_data, "assigned_to", None), "name", None),
                "Unassigned",
            )
            issue_item["updated_on"] = _iso_date(
                getattr(issue_data, "updated_on", None)
            )
            issue_item["done_ratio_raw"] = getattr(issue_data, "done_ratio", None)
            issue_item["description_excerpt_raw"] = _extract_description_excerpt(
                getattr(issue_data, "description", None)
            )

        for issue_item in top_issues:
            issue_id_text = (
                f"#{issue_item['issue_id']}"
                if issue_item.get("issue_id") is not None
                else "#N/A"
            )
            issue_item["issue_subject"] = wrap_content(
                issue_item.get("issue_subject_raw", "No linked issue")
            )
            issue_item["project_name"] = wrap_content(
                issue_item.get("project_name_raw", "Unknown project")
            )
            issue_item["status"] = wrap_content(issue_item.get("status_raw", "Unknown"))
            issue_item["priority"] = wrap_content(
                issue_item.get("priority_raw", "Unknown")
            )
            issue_item["assignee"] = wrap_content(
                issue_item.get("assignee_raw", "Unassigned")
            )
            issue_item["updated_on"] = issue_item.get("updated_on") or "unknown"
            issue_item["description_excerpt"] = wrap_content(
                issue_item.get("description_excerpt_raw", "")
            )
            issue_item["summary_line"] = (
                f"- {issue_id_text} "
                f"[{issue_item['status']}][{issue_item['priority']}] "
                f"{issue_item['issue_subject']} | assignee: {issue_item['assignee']} | "
                f"{round(issue_item['hours'], 2)}h | "
                f"project: {issue_item['project_name']} | "
                f"updated: {issue_item['updated_on']}"
            )
            issue_item["description_line"] = (
                f"  desc: {issue_item['description_excerpt']}"
                if issue_item["description_excerpt"].strip()
                else "  desc: (no description)"
            )
        sorted_days = [
            {
                **bucket,
                "hours": round(bucket["hours"], 2),
            }
            for _, bucket in sorted(by_day.items(), key=lambda item: item[0])
        ]

        summary_lines = [
            item["summary_line"] for item in top_issues if item.get("summary_line")
        ]
        highlights = [
            f"{item['summary_line']}\n{item['description_line']}" for item in top_issues
        ]

        report_title = (
            "Daily Scrum Report Draft"
            if resolved_range["report_type"] == "daily"
            else (
                "Weekly Scrum Report Draft"
                if resolved_range["report_type"] == "weekly"
                else "Custom Scrum Report Draft"
            )
        )
        report_draft = "\n".join(
            [
                f"### {report_title}",
                (
                    f"- Range: {resolved_range['from_date']} to "
                    f"{resolved_range['to_date']}"
                ),
                f"- Total time logged: {round(total_hours, 2)}h",
                f"- Total entries: {len(time_entries)}",
                "",
                "#### Completed work highlights",
                *(highlights or ["- No tracked work in selected range."]),
                "",
                "#### Suggested talking points",
                "- Yesterday/Last week: summarize completed items above.",
                "- Today/Next week: list planned follow-ups from top items.",
                "- Blockers: mention blocked tasks or dependency issues.",
            ]
        )
        range_line = f"{resolved_range['from_date']} to {resolved_range['to_date']}"
        top_issue_lines = highlights or ["- No major completed item recorded."]
        next_focus_line = (
            summary_lines[0].replace("- ", "- Continue/close: ", 1)
            if summary_lines
            else "- Continue/close: No priority item selected yet."
        )

        template_standup_three_questions = "\n".join(
            [
                "### Daily Standup Template (3 Questions)",
                f"- Range reviewed: {range_line}",
                "",
                "1) What I completed in the last period",
                *top_issue_lines,
                "",
                "2) What I will work on next",
                next_focus_line,
                "",
                "3) Blockers / dependencies",
                "- [ ] None",
                "- [ ] Need support from: <team/person>",
            ]
        )

        template_workflow_focused = "\n".join(
            [
                "### Daily Standup Template (Workflow Focused)",
                f"- Range reviewed: {range_line}",
                "",
                "Done since last update:",
                *top_issue_lines,
                "",
                "In progress now:",
                "- <issue/task> (owner: <name>)",
                "",
                "Blocked:",
                "- <issue/task> (blocker: <reason>)",
                "",
                "Next 24h commit:",
                next_focus_line,
            ]
        )

        template_weekly_status = "\n".join(
            [
                "### Weekly Status Template (Accomplishments / Risks / Next)",
                f"- Reporting window: {range_line}",
                f"- Total hours logged: {round(total_hours, 2)}h",
                f"- Total entries: {len(time_entries)}",
                "",
                "Top accomplishments:",
                *top_issue_lines,
                "",
                "Risks / blockers:",
                "- <risk or blocker> | owner: <name> | mitigation: <action>",
                "",
                "Next-week priorities:",
                next_focus_line,
                "- <priority 2>",
                "- <priority 3>",
            ]
        )

        payload: Dict[str, Any] = {
            "report_type": resolved_range["report_type"],
            "analysis_range": {
                "label": resolved_range["label"],
                "from_date": resolved_range["from_date"],
                "to_date": resolved_range["to_date"],
            },
            "filters": {
                "user_id": user_id,
                "project_id": project_id,
            },
            "summary": {
                "total_hours": round(total_hours, 2),
                "total_entries": len(time_entries),
                "unique_user_count": len(unique_users),
            },
            "top_issues": [
                {
                    **item,
                    "hours": round(item["hours"], 2),
                }
                for item in top_issues
            ],
            "top_activities": [
                {
                    **item,
                    "hours": round(item["hours"], 2),
                }
                for item in sorted_activities[:top_limit]
            ],
            "top_users": [
                {
                    **item,
                    "hours": round(item["hours"], 2),
                }
                for item in sorted_users[:top_limit]
            ],
            "by_day": sorted_days,
            "report_draft": report_draft,
            "report_templates": {
                "standup_three_questions": template_standup_three_questions,
                "standup_workflow_focused": template_workflow_focused,
                "weekly_status_summary": template_weekly_status,
            },
        }

        if include_entries:
            payload["entries"] = [time_entry_to_dict(entry) for entry in time_entries]

        return payload
    except Exception as e:
        return handle_error(e, "generating scrum report", None)


async def _build_weekly_report_render_payload(
    *,
    generate_scrum_report_fn: Callable[..., Awaitable[Dict[str, Any]]],
    user_id: Optional[Union[str, int]],
    project_id: Optional[Union[str, int]],
    top_n_items: int,
    template_path: Optional[str],
    unit_name: str,
    reporter_name: str,
    location: str,
    today: Optional[date],
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Build rendered weekly report markdown and metadata from scrum report data."""
    report_type = "custom" if (from_date and to_date) else "weekly"
    report_data = await generate_scrum_report_fn(
        report_type=report_type,
        user_id=user_id,
        project_id=project_id,
        top_n_items=top_n_items,
        include_entries=False,
        from_date=from_date,
        to_date=to_date,
    )
    if isinstance(report_data, dict) and "error" in report_data:
        return report_data

    analysis_range = report_data.get("analysis_range", {})
    from_date = str(analysis_range.get("from_date", "")).strip()
    to_date = str(analysis_range.get("to_date", "")).strip()
    if not from_date or not to_date:
        return {"error": "Weekly report data is missing analysis_range dates."}

    parsed_from = date.fromisoformat(from_date)
    parsed_to = date.fromisoformat(to_date)
    next_week_start = parsed_to + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)
    week_report = parsed_from.isocalendar().week
    week_plan = next_week_start.isocalendar().week

    top_issues = report_data.get("top_issues", []) or []

    def _resolve_completion_percent(item: Dict[str, Any]) -> str:
        raw_done_ratio = item.get("done_ratio_raw")
        if isinstance(raw_done_ratio, (int, float)):
            clamped = int(max(0, min(100, round(float(raw_done_ratio)))))
            return str(clamped)
        status_raw = str(item.get("status_raw", "")).lower()
        return (
            "100"
            if "closed" in status_raw
            or "done" in status_raw
            or "resolved" in status_raw
            else "80"
        )

    bao_cao_items = [
        {
            "cong_viec": str(item.get("issue_subject", "N/A")),
            "phan_tram_hoan_thanh": _resolve_completion_percent(item),
            "mo_ta": str(item.get("description_excerpt", "(no description)")),
        }
        for item in top_issues
    ] or [
        {
            "cong_viec": "(Không có dữ liệu)",
            "phan_tram_hoan_thanh": "0",
            "mo_ta": "Không có time entry trong tuần báo cáo.",
        }
    ]

    ke_hoach_items = [
        {
            "cong_viec": str(item.get("issue_subject", "N/A")),
            "phan_tram_chi_tieu": "100",
            "mo_ta": f"Tiếp tục hoàn thiện: {item.get('description_excerpt', '')}",
        }
        for item in top_issues[: max(1, min(top_n_items, 10))]
    ] or [
        {
            "cong_viec": "(Chưa xác định)",
            "phan_tram_chi_tieu": "100",
            "mo_ta": "Bổ sung kế hoạch cho tuần kế tiếp.",
        }
    ]

    template_file = _resolve_weekly_report_template_path(template_path)
    if not template_file.exists() or not template_file.is_file():
        return {"error": f"Weekly report template not found: {template_file}"}
    template_text = template_file.read_text(encoding="utf-8")

    now = today or date.today()
    context = {
        "don_vi": unit_name,
        "nguoi_bao_cao": reporter_name,
        "dia_diem": location,
        "ngay": str(now.day),
        "thang": str(now.month),
        "nam": str(now.year),
        "tuan_bao_cao": str(week_report),
        "tuan_ke_hoach": str(week_plan),
        "range_bao_cao": f"{from_date} - {to_date}",
        "range_ke_hoach": (
            f"{next_week_start.isoformat()} - {next_week_end.isoformat()}"
        ),
    }
    markdown = _render_weekly_report_template(
        template_text=template_text,
        context=context,
        bao_cao_items=bao_cao_items,
        ke_hoach_items=ke_hoach_items,
    )

    return {
        "markdown": markdown,
        "template_file": template_file,
        "report_summary": report_data.get("summary", {}),
        "analysis_range": {
            "from_date": from_date,
            "to_date": to_date,
            "week_report": week_report,
            "week_plan": week_plan,
        },
    }


async def export_weekly_report_markdown_impl(
    *,
    generate_scrum_report_fn: Callable[..., Awaitable[Dict[str, Any]]],
    user_id: Optional[Union[str, int]] = None,
    project_id: Optional[Union[str, int]] = None,
    top_n_items: int = 7,
    template_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    file_name: Optional[str] = None,
    unit_name: str = "TRUNG TÂM CSE",
    reporter_name: str = "NGƯỜI BÁO CÁO",
    location: str = "Đà Nẵng",
    today: Optional[date] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Export a weekly markdown report file from scrum analytics data."""
    try:
        render_payload = await _build_weekly_report_render_payload(
            generate_scrum_report_fn=generate_scrum_report_fn,
            user_id=user_id,
            project_id=project_id,
            top_n_items=top_n_items,
            template_path=template_path,
            unit_name=unit_name,
            reporter_name=reporter_name,
            location=location,
            today=today,
            from_date=from_date,
            to_date=to_date,
        )
        if "error" in render_payload:
            return render_payload
        markdown = str(render_payload["markdown"])
        template_file = Path(render_payload["template_file"])
        analysis_range = dict(render_payload["analysis_range"])
        from_date = str(analysis_range["from_date"])
        to_date = str(analysis_range["to_date"])
        week_report = int(analysis_range["week_report"])

        output_directory = _resolve_weekly_report_output_dir(output_dir)
        output_directory.mkdir(parents=True, exist_ok=True)
        resolved_file_name = (
            _validate_export_file_name(file_name, ".md")
            if file_name
            else f"weekly-report-w{week_report}-{from_date}-to-{to_date}.md"
        )
        output_path = (output_directory / resolved_file_name).resolve()
        if not _is_within_directory(output_path, output_directory):
            raise ValueError(
                f"file_name escapes output directory: {resolved_file_name}"
            )
        output_path.write_text(markdown, encoding="utf-8")

        return {
            "exported": True,
            "template_path": str(template_file),
            "output_path": str(output_path),
            "output_file_name": output_path.name,
            "markdown_size_bytes": output_path.stat().st_size,
            "analysis_range": analysis_range,
            "report_summary": render_payload.get("report_summary", {}),
            "preview": markdown[:2000],
        }
    except Exception as e:
        return handle_error(e, "exporting weekly report markdown", None)


async def export_weekly_report_docx_impl(
    *,
    generate_scrum_report_fn: Callable[..., Awaitable[Dict[str, Any]]],
    user_id: Optional[Union[str, int]] = None,
    project_id: Optional[Union[str, int]] = None,
    top_n_items: int = 7,
    template_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    file_name: Optional[str] = None,
    unit_name: str = "TRUNG TÂM CSE",
    reporter_name: str = "NGƯỜI BÁO CÁO",
    location: str = "Đà Nẵng",
    today: Optional[date] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Export weekly report to a plain-text .docx wrapper rendered from markdown."""
    try:
        render_payload = await _build_weekly_report_render_payload(
            generate_scrum_report_fn=generate_scrum_report_fn,
            user_id=user_id,
            project_id=project_id,
            top_n_items=top_n_items,
            template_path=template_path,
            unit_name=unit_name,
            reporter_name=reporter_name,
            location=location,
            today=today,
            from_date=from_date,
            to_date=to_date,
        )
        if "error" in render_payload:
            return render_payload

        markdown_text = str(render_payload["markdown"])
        analysis_range = dict(render_payload["analysis_range"])
        from_date = str(analysis_range["from_date"])
        to_date = str(analysis_range["to_date"])
        week_report = int(analysis_range["week_report"])
        output_directory = _resolve_weekly_report_output_dir(output_dir)
        output_directory.mkdir(parents=True, exist_ok=True)
        docx_name = (
            _validate_export_file_name(file_name, ".docx")
            if file_name
            else f"weekly-report-w{week_report}-{from_date}-to-{to_date}.docx"
        )
        docx_path = (output_directory / docx_name).resolve()
        if not _is_within_directory(docx_path, output_directory):
            raise ValueError(f"file_name escapes output directory: {docx_name}")
        docx_bytes = _build_minimal_docx_from_text(markdown_text)
        docx_path.write_bytes(docx_bytes)

        return {
            "exported": True,
            "output_path": str(docx_path),
            "output_file_name": docx_path.name,
            "docx_size_bytes": docx_path.stat().st_size,
            "analysis_range": analysis_range,
            "report_summary": render_payload.get("report_summary", {}),
            "render_mode": "plain_text_docx_from_markdown",
            "format_note": (
                "This DOCX preserves markdown content as plain text; "
                "headings/tables are not converted to native Word formatting."
            ),
        }
    except Exception as e:
        return handle_error(e, "exporting weekly report docx", None)


async def summarize_project_status_impl(
    project_id: int,
    days: int = 30,
    *,
    get_client: Callable[[], Any],
    analyze_issues: Callable[[List[Any]], Dict[str, Any]],
    handle_error: HandleErrorFn,
    resource_not_found_error: Type[Exception],
) -> Dict[str, Any]:
    """Provide summary statistics for project activity over a date window."""
    try:
        client = get_client()
        try:
            project = await asyncio.to_thread(client.project.get, project_id)
        except resource_not_found_error:
            return {"error": f"Project {project_id} not found."}

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        date_filter = f">={start_date.strftime('%Y-%m-%d')}"

        created_issues = await asyncio.to_thread(
            lambda: list(
                client.issue.filter(project_id=project_id, created_on=date_filter)
            )
        )
        updated_issues = await asyncio.to_thread(
            lambda: list(
                client.issue.filter(project_id=project_id, updated_on=date_filter)
            )
        )

        created_stats = analyze_issues(created_issues)
        updated_stats = analyze_issues(updated_issues)

        total_created = len(created_issues)
        total_updated = len(updated_issues)

        all_issues = await asyncio.to_thread(
            lambda: list(client.issue.filter(project_id=project_id))
        )
        all_stats = analyze_issues(all_issues)

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "identifier": getattr(project, "identifier", ""),
            },
            "analysis_period": {
                "days": days,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
            },
            "recent_activity": {
                "issues_created": total_created,
                "issues_updated": total_updated,
                "created_breakdown": created_stats,
                "updated_breakdown": updated_stats,
            },
            "project_totals": {
                "total_issues": len(all_issues),
                "overall_breakdown": all_stats,
            },
            "insights": {
                "daily_creation_rate": round(total_created / days, 2),
                "daily_update_rate": round(total_updated / days, 2),
                "recent_activity_percentage": round(
                    (total_updated / len(all_issues) * 100) if all_issues else 0,
                    2,
                ),
            },
        }
    except Exception as e:
        return handle_error(
            e,
            f"summarizing project {project_id}",
            {"resource_type": "project", "resource_id": project_id},
        )


async def search_entire_redmine_impl(
    query: str,
    resources: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    resource_to_dict: Callable[[Any, str], Dict[str, Any]],
    handle_error: HandleErrorFn,
    version_mismatch_error: Type[Exception],
) -> Dict[str, Any]:
    """Search issues and wiki pages across the Redmine instance."""
    try:
        await ensure_cleanup_started()

        allowed_types = ["issues", "wiki_pages"]
        if resources:
            resources = [
                resource for resource in resources if resource in allowed_types
            ]
            if not resources:
                resources = allowed_types
        else:
            resources = allowed_types

        limit = min(limit, 100)
        if limit <= 0:
            limit = 100

        search_options = {
            "resources": resources,
            "limit": limit,
            "offset": offset,
        }
        client = get_client()

        def _search_and_serialize() -> Dict[str, Any]:
            categorized_results = client.search(query, **search_options)
            if not categorized_results:
                return {
                    "results": [],
                    "results_by_type": {},
                    "total_count": 0,
                    "query": query,
                }

            all_results = []
            results_by_type: Dict[str, int] = {}
            for resource_type, resource_set in categorized_results.items():
                if resource_type == "unknown":
                    continue
                if resource_type not in allowed_types:
                    continue

                if hasattr(resource_set, "__iter__"):
                    count = 0
                    for resource in resource_set:
                        all_results.append(resource_to_dict(resource, resource_type))
                        count += 1
                    if count > 0:
                        results_by_type[resource_type] = count

            return {
                "results": all_results,
                "results_by_type": results_by_type,
                "total_count": len(all_results),
                "query": query,
            }

        return await asyncio.to_thread(_search_and_serialize)
    except version_mismatch_error:
        return {"error": "Search requires Redmine 3.3.0 or higher."}
    except Exception as e:
        return handle_error(e, f"searching Redmine for '{query}'", None)
