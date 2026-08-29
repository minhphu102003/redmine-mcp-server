"""Unit tests for header cell padding, per-header column widths, date formatting,
text wrap, and markdown-to-rich-text conversion.

Verifies that the create_spreadsheet and _add_sheets_to_existing flows emit
repeatCell requests with cell padding, per-column updateDimensionProperties
sized to each header text, date number formats, and wrap strategies, instead of
autoResizeDimensions for columns.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from redmine_mcp_server.google_sheets_client import (  # noqa: E402
    GoogleSheetsManager,
    _build_column_format_requests,
    _build_row_height_requests,
    _build_width_requests,
    _is_markdown,
)
from redmine_mcp_server.serializers.google_sheets import (  # noqa: E402
    BUGS_HEADERS,
    HEADER_PADDING_PX,
    HEADER_WRAP_COLUMNS,
    TESTCASES_HEADERS,
    calculate_header_width,
    parse_markdown_to_rich_text,
)


# --- Pure function tests ---


def test_calculate_header_width_uses_text_plus_padding():
    assert calculate_header_width("BUG_ID") == 6 * 8 + HEADER_PADDING_PX
    assert calculate_header_width("TEST_CASE_ID") == 12 * 8 + HEADER_PADDING_PX
    assert calculate_header_width("EXPECTED_RESULT") == 15 * 8 + HEADER_PADDING_PX
    assert calculate_header_width("") == HEADER_PADDING_PX


def test_build_width_requests_emit_one_per_column():
    headers = ["A", "BUG_ID", "EXPECTED_RESULT"]
    requests = _build_width_requests(sheet_id=42, headers=headers)
    assert len(requests) == 3

    for idx, (header, req) in enumerate(zip(headers, requests)):
        update = req["updateDimensionProperties"]
        assert update["range"]["sheetId"] == 42
        assert update["range"]["dimension"] == "COLUMNS"
        assert update["range"]["startIndex"] == idx
        assert update["range"]["endIndex"] == idx + 1
        assert update["properties"]["pixelSize"] == calculate_header_width(header)
        assert update["fields"] == "pixelSize"


# --- Mocked service helpers ---


def _build_service_mock(
    *,
    existing_sheets: list[dict] | None = None,
    add_sheet_replies: list[dict] | None = None,
    create_replies: list[dict] | None = None,
) -> MagicMock:
    existing_sheets = existing_sheets or []
    add_sheet_replies = add_sheet_replies or []
    create_replies = create_replies or []

    service = MagicMock()
    spreadsheet_resource = service.spreadsheets.return_value

    spreadsheet_resource.get.return_value.execute.return_value = {
        "spreadsheetId": "fake_id_123",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/fake_id_123/edit",
        "sheets": existing_sheets,
    }

    spreadsheet_resource.batchUpdate.return_value.execute.return_value = {
        "replies": add_sheet_replies
    }

    if create_replies:
        spreadsheet_resource.create.return_value.execute.return_value = {
            "spreadsheetId": "new_id_xyz",
            "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new_id_xyz/edit",
            "sheets": create_replies,
        }

    spreadsheet_resource.values.return_value.batchUpdate.return_value.execute.return_value = (
        {}
    )

    return service


def _collect_format_requests(service_mock: MagicMock) -> list[dict]:
    """Return the list of requests from the format-only batchUpdate call
    (the one that contains repeatCell, updateSheetProperties, and width
    requests — NOT the addSheet/validation calls).
    """
    batch_calls = service_mock.spreadsheets.return_value.batchUpdate.call_args_list
    for call in batch_calls:
        requests = call.kwargs["body"]["requests"]
        if any("repeatCell" in r for r in requests):
            return requests
    return []


# --- create_spreadsheet (new spreadsheet) ---


def test_create_spreadsheet_new_applies_padding_and_widths(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()

    service = _build_service_mock(
        create_replies=[
            {
                "properties": {
                    "sheetId": 1,
                    "title": "TestCases",
                    "gridProperties": {"rowCount": 1000},
                }
            },
            {
                "properties": {
                    "sheetId": 2,
                    "title": "Bugs",
                    "gridProperties": {"rowCount": 1000},
                }
            },
        ],
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.create_spreadsheet(title="My Sheet", member_names=["Alice"])

    format_requests = _collect_format_requests(service)
    assert format_requests, "Expected a batchUpdate call with repeatCell"

    # repeatCell must include padding in fields and userEnteredFormat (header row)
    repeat_cells = [r for r in format_requests if "repeatCell" in r]
    # At minimum we expect header-style repeatCells
    header_cells = [
        r
        for r in repeat_cells
        if "padding" in r["repeatCell"]["cell"]["userEnteredFormat"]
    ]
    assert len(header_cells) == 2  # one for each sheet
    for rc in header_cells:
        assert rc["repeatCell"]["cell"]["userEnteredFormat"]["padding"] == {
            "top": 6,
            "bottom": 6,
            "left": 12,
            "right": 12,
        }
        assert "padding" in rc["repeatCell"]["fields"]

    # updateDimensionProperties must exist, one per column per sheet
    width_requests = [r for r in format_requests if "updateDimensionProperties" in r]
    test_widths = [
        r
        for r in width_requests
        if r["updateDimensionProperties"]["range"]["sheetId"] == 1
    ]
    bug_widths = [
        r
        for r in width_requests
        if r["updateDimensionProperties"]["range"]["sheetId"] == 2
    ]
    assert len(test_widths) == len(TESTCASES_HEADERS)
    assert len(bug_widths) == len(BUGS_HEADERS)

    # autoResizeDimensions for COLUMNS must NOT be used
    col_resize = [
        r
        for r in format_requests
        if "autoResizeDimensions" in r
        and r.get("autoResizeDimensions", {}).get("dimensions", {}).get("dimension")
        == "COLUMNS"
    ]
    assert len(col_resize) == 0, "autoResizeDimensions for COLUMNS should not appear"


# --- _add_sheets_to_existing ---


def test_add_sheets_to_existing_applies_padding_and_widths(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()

    add_replies = [
        {"addSheet": {"properties": {"sheetId": 100, "title": "TestCases"}}},
        {"addSheet": {"properties": {"sheetId": 101, "title": "Bugs"}}},
    ]
    service = _build_service_mock(existing_sheets=[], add_sheet_replies=add_replies)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager._add_sheets_to_existing("fake_id_123", ["Alice"])

    format_requests = _collect_format_requests(service)
    assert format_requests, "Expected a format batchUpdate call"

    header_cells = [
        r
        for r in format_requests
        if "repeatCell" in r
        and "padding" in r["repeatCell"]["cell"]["userEnteredFormat"]
    ]
    assert len(header_cells) == 2  # one per sheet

    width_requests = [r for r in format_requests if "updateDimensionProperties" in r]
    test_widths = [
        r
        for r in width_requests
        if r["updateDimensionProperties"]["range"]["sheetId"] == 100
    ]
    bug_widths = [
        r
        for r in width_requests
        if r["updateDimensionProperties"]["range"]["sheetId"] == 101
    ]
    assert len(test_widths) == len(TESTCASES_HEADERS)
    assert len(bug_widths) == len(BUGS_HEADERS)
    col_resize = [
        r
        for r in format_requests
        if "autoResizeDimensions" in r
        and r.get("autoResizeDimensions", {}).get("dimensions", {}).get("dimension")
        == "COLUMNS"
    ]
    assert len(col_resize) == 0


# --- Column format requests (date + wrap) ---


def test_date_columns_get_ddmmyyyy_format():
    headers = ["CREATED_DATE", "STEPS", "LAST_TEST_DATE"]
    requests = _build_column_format_requests(sheet_id=1, headers=headers)
    date_reqs = [
        r
        for r in requests
        if r["repeatCell"]["cell"]["userEnteredFormat"].get("numberFormat")
    ]
    assert len(date_reqs) == 2  # CREATED_DATE and LAST_TEST_DATE
    for r in date_reqs:
        assert r["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"] == {
            "type": "DATE",
            "pattern": "dd/mm/yyyy",
        }
        # Must target COLUMNS dimension
        assert r["repeatCell"]["range"]["dimension"] == "COLUMNS"


def test_wrap_columns_get_wrap_strategy():
    headers = ["BUG_ID", "STEPS", "TESTER"]
    requests = _build_column_format_requests(sheet_id=1, headers=headers)
    wrap_reqs = [
        r
        for r in requests
        if r["repeatCell"]["cell"]["userEnteredFormat"].get("wrapStrategy") == "WRAP"
    ]
    assert len(wrap_reqs) == 1  # only STEPS
    assert wrap_reqs[0]["repeatCell"]["range"]["startIndex"] == 1  # col E = index 1
    assert wrap_reqs[0]["repeatCell"]["range"]["dimension"] == "COLUMNS"
    assert (
        wrap_reqs[0]["repeatCell"]["cell"]["userEnteredFormat"]["verticalAlignment"]
        == "TOP"
    )


def test_non_formatted_columns_emit_no_request():
    headers = ["BUG_ID", "TESTER", "STATUS"]  # none are date or wrap columns
    requests = _build_column_format_requests(sheet_id=1, headers=headers)
    assert len(requests) == 0


def test_row_height_requests_sized_correctly():
    requests = _build_row_height_requests(sheet_id=5, row_count=500)
    assert len(requests) == 1
    assert requests[0]["autoResizeDimensions"]["dimensions"]["sheetId"] == 5
    assert requests[0]["autoResizeDimensions"]["dimensions"]["dimension"] == "ROWS"
    assert requests[0]["autoResizeDimensions"]["dimensions"]["startIndex"] == 1
    assert requests[0]["autoResizeDimensions"]["dimensions"]["endIndex"] == 500


# --- Markdown parsing ---


def test_markdown_bold_converted():
    runs = parse_markdown_to_rich_text("This is **bold** text")
    texts = [r["text"] for r in runs]
    assert "This is " in texts
    assert "bold" in texts
    bold_run = next(r for r in runs if r["text"] == "bold")
    assert bold_run["textFormat"]["bold"] is True


def test_markdown_italic_converted():
    runs = parse_markdown_to_rich_text("This is *italic* text")
    italic_run = next(r for r in runs if r["text"] == "italic")
    assert italic_run["textFormat"]["italic"] is True


def test_markdown_bold_italic_combined():
    runs = parse_markdown_to_rich_text("***bold italic***")
    assert len(runs) == 1
    assert runs[0]["text"] == "bold italic"
    assert runs[0]["textFormat"]["bold"] is True
    assert runs[0]["textFormat"]["italic"] is True


def test_markdown_code_converted():
    runs = parse_markdown_to_rich_text("Use `print()` function")
    code_run = next(r for r in runs if r["text"] == "print()")
    assert code_run["textFormat"]["fontFamily"] == "Roboto Mono"


def test_markdown_hyperlink_converted():
    runs = parse_markdown_to_rich_text("Click [here](http://example.com) now")
    link_runs = [r for r in runs if "hyperlink" in r]
    assert len(link_runs) == 1
    assert link_runs[0]["text"] == "here"
    assert link_runs[0]["hyperlink"] == "http://example.com"


def test_markdown_plain_text_unchanged():
    runs = parse_markdown_to_rich_text("plain text without any formatting")
    assert len(runs) == 1
    assert runs[0]["text"] == "plain text without any formatting"
    assert "textFormat" not in runs[0]


def test_markdown_empty_string():
    runs = parse_markdown_to_rich_text("")
    assert runs == [{"text": ""}]


def test_markdown_mixed_content():
    runs = parse_markdown_to_rich_text("Step 1: **click** the *button* then `submit`")
    texts = [r["text"] for r in runs]
    assert "Step 1: " in texts
    assert "click" in texts
    assert "button" in texts
    assert "submit" in texts


def test_is_markdown_detection():
    assert _is_markdown("This is **bold** text") is True
    assert _is_markdown("This is *italic* text") is True
    assert _is_markdown("This is `code` text") is True
    assert _is_markdown("Link [here](http://x.com)") is True
    assert _is_markdown("plain text") is False
    assert _is_markdown("") is False
    assert _is_markdown(None) is False
