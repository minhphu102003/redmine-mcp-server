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
        # Must use GridRange (startColumnIndex/endColumnIndex), not DimensionRange
        assert "startColumnIndex" in r["repeatCell"]["range"]
        assert "endColumnIndex" in r["repeatCell"]["range"]
        assert "dimension" not in r["repeatCell"]["range"]
        assert "startIndex" not in r["repeatCell"]["range"]
        assert "endIndex" not in r["repeatCell"]["range"]


def test_wrap_columns_get_wrap_strategy():
    headers = ["BUG_ID", "STEPS", "TESTER"]
    requests = _build_column_format_requests(sheet_id=1, headers=headers)
    wrap_reqs = [
        r
        for r in requests
        if r["repeatCell"]["cell"]["userEnteredFormat"].get("wrapStrategy") == "WRAP"
    ]
    assert len(wrap_reqs) == 1  # only STEPS
    # STEPS is at column index 1 (0=B, 1=E) — verify GridRange fields
    assert wrap_reqs[0]["repeatCell"]["range"]["startColumnIndex"] == 1
    assert wrap_reqs[0]["repeatCell"]["range"]["endColumnIndex"] == 2
    assert "dimension" not in wrap_reqs[0]["repeatCell"]["range"]
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


# --- US section header ---


def _mock_service_with_sheet(sheet_id: int = 0) -> MagicMock:
    service = MagicMock()
    meta = {
        "sheets": [
            {
                "properties": {
                    "sheetId": sheet_id,
                    "title": "TestCases",
                    "gridProperties": {"rowCount": 100, "columnCount": 10},
                }
            }
        ]
    }
    service.spreadsheets.return_value.get.return_value.execute.return_value = meta
    service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}
    return service


def test_add_us_section_header_emits_insert_merge_background_text(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    import asyncio

    asyncio.run(
        manager.add_us_section_header(
            spreadsheet_id="abc123",
            sheet_name="TestCases",
            us_title="[US-1] Login Feature",
            row_index=2,
            color="#4285F4",
            get_user_memory=None,
        )
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 1
    requests = batch_calls[0].kwargs["body"]["requests"]

    # Must have 4 requests: insertDimension, repeatCell(background), mergeCells, repeatCell(text)
    assert len(requests) == 4

    # insertDimension (with inheritFromBefore=false so the new row inherits
    # from rows below, not the colored US title above)
    insert = next(r for r in requests if "insertDimension" in r)
    assert insert["insertDimension"]["range"]["sheetId"] == 5
    assert insert["insertDimension"]["range"]["dimension"] == "ROWS"
    assert insert["insertDimension"]["range"]["startIndex"] == 2
    assert insert["insertDimension"]["range"]["endIndex"] == 3
    assert insert["insertDimension"]["inheritFromBefore"] is False

    # repeatCell background + text format (full row A-K)
    fmt_cell = next(
        r
        for r in requests
        if "repeatCell" in r
        and "backgroundColor" in r["repeatCell"]["cell"]["userEnteredFormat"]
    )
    assert fmt_cell["repeatCell"]["range"]["startRowIndex"] == 2
    assert fmt_cell["repeatCell"]["range"]["endRowIndex"] == 3
    assert fmt_cell["repeatCell"]["range"]["startColumnIndex"] == 0
    assert fmt_cell["repeatCell"]["range"]["endColumnIndex"] == 11
    rgb = fmt_cell["repeatCell"]["cell"]["userEnteredFormat"]["backgroundColor"]
    # #4285F4 → 66/255=0.259, 133/255=0.522, 244/255=0.957
    assert 0.25 < rgb["red"] < 0.27
    assert 0.51 < rgb["green"] < 0.53
    assert 0.95 < rgb["blue"] < 0.97
    tf = fmt_cell["repeatCell"]["cell"]["userEnteredFormat"]["textFormat"]
    assert tf["bold"] is True
    assert tf["foregroundColor"] == {"red": 1.0, "green": 1.0, "blue": 1.0}
    assert tf["fontSize"] == 10
    ha = fmt_cell["repeatCell"]["cell"]["userEnteredFormat"]["horizontalAlignment"]
    assert ha == "LEFT"
    va = fmt_cell["repeatCell"]["cell"]["userEnteredFormat"]["verticalAlignment"]
    assert va == "MIDDLE"

    # mergeCells
    merge = next(r for r in requests if "mergeCells" in r)
    assert merge["mergeCells"]["range"]["sheetId"] == 5
    assert merge["mergeCells"]["range"]["startRowIndex"] == 2
    assert merge["mergeCells"]["range"]["endRowIndex"] == 3
    assert merge["mergeCells"]["range"]["startColumnIndex"] == 0
    assert merge["mergeCells"]["range"]["endColumnIndex"] == 11
    assert merge["mergeCells"]["mergeType"] == "MERGE_ALL"

    # repeatCell value (column A only)
    value_cell = next(
        r
        for r in requests
        if "repeatCell" in r and "userEnteredValue" in r["repeatCell"]["cell"]
    )
    assert value_cell["repeatCell"]["range"]["startColumnIndex"] == 0
    assert value_cell["repeatCell"]["range"]["endColumnIndex"] == 1
    assert (
        value_cell["repeatCell"]["cell"]["userEnteredValue"]["stringValue"]
        == "[US-1] Login Feature"
    )


def test_add_us_section_header_handles_missing_sheet(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    # Return no matching sheet
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 99, "title": "OtherSheet"}}]
    }
    monkeypatch.setattr(manager, "get_service", lambda: service)

    # Should not raise — just silently skip
    import asyncio

    asyncio.run(
        manager.add_us_section_header(
            spreadsheet_id="abc123",
            sheet_name="TestCases",
            us_title="[US-2] Register",
            row_index=5,
            color="#34A853",
            get_user_memory=None,
        )
    )

    # batchUpdate should NOT have been called
    service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_add_us_section_header_reapplies_validation_with_members(monkeypatch):
    """When get_user_memory is provided AND .redmine.project_contexts has
    members for the mapped redmine_project_id, a SECOND batchUpdate is
    emitted containing setDataValidation + addConditionalFormatRule
    for the TESTER (col 6) and LAST_TEST_RESULT (col 8) columns.

    The first batchUpdate still contains only the 4 original requests
    (insertDimension, repeatCell, mergeCells, repeatCell value).
    """
    import asyncio

    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    # Mock memory fetch
    async def fake_get_user_memory(key: str):
        if key == ".google-sheets":
            return {
                "value": {
                    "projects": [
                        {
                            "spreadsheet_id": "abc123",
                            "redmine_project_id": 12,
                        }
                    ]
                }
            }
        if key == ".redmine":
            return {
                "value": {
                    "project_contexts": {
                        "12": {
                            "members": [
                                {"user": {"id": 1, "name": "Alice"}},
                                {"user": {"id": 2, "name": "Bob"}},
                            ]
                        }
                    }
                }
            }
        return {}

    asyncio.run(
        manager.add_us_section_header(
            spreadsheet_id="abc123",
            sheet_name="TestCases",
            us_title="[US-1] Login Feature",
            row_index=2,
            color="#4285F4",
            get_user_memory=fake_get_user_memory,
        )
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    # 1st call: insert + format (4 requests). 2nd call: re-apply validation.
    assert len(batch_calls) == 2

    reapply_requests = batch_calls[1].kwargs["body"]["requests"]
    # 2 columns (tester, last_test_result) + conditional formats
    set_data_validations = [r for r in reapply_requests if "setDataValidation" in r]
    assert len(set_data_validations) == 2

    # Column 6 (tester) must contain both member names
    tester_rule = next(
        r
        for r in set_data_validations
        if r["setDataValidation"]["range"]["startColumnIndex"] == 6
    )
    tester_values = [
        v["userEnteredValue"]
        for v in tester_rule["setDataValidation"]["rule"]["condition"]["values"]
    ]
    assert "Alice" in tester_values
    assert "Bob" in tester_values

    # Column 8 (last_test_result) must contain 4 options incl. Blocked
    result_rule = next(
        r
        for r in set_data_validations
        if r["setDataValidation"]["range"]["startColumnIndex"] == 8
    )
    result_values = [
        v["userEnteredValue"]
        for v in result_rule["setDataValidation"]["rule"]["condition"]["values"]
    ]
    assert "Not Tested" in result_values
    assert "Pass" in result_values
    assert "Fail" in result_values
    assert "Blocked" in result_values


def test_add_us_section_header_skips_reapply_without_memory(monkeypatch):
    """When get_user_memory is None, add_us_section_header must NOT call
    batchUpdate a second time. Backward-compatible behavior — the 4
    original requests are still emitted once.
    """
    import asyncio

    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    asyncio.run(
        manager.add_us_section_header(
            spreadsheet_id="abc123",
            sheet_name="TestCases",
            us_title="[US-1] Login Feature",
            row_index=2,
            color="#4285F4",
            get_user_memory=None,
        )
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    # Only the original 4 requests — no re-apply call
    assert len(batch_calls) == 1


def test_us_title_cell_format():
    """Verify the US title cell format matches the expected pattern."""
    us_id_counter = 1
    us_title = "Login Feature"
    us_title_cell = f"[US-{us_id_counter}] {us_title}"
    assert us_title_cell == "[US-1] Login Feature"

    us_id_counter = 3
    us_title_cell = f"[US-{us_id_counter}] {us_title}"
    assert us_title_cell == "[US-3] Login Feature"


def test_color_palette_rotates():
    """Verify palette has 8 colors and rotation works."""
    palette = [
        "#4285F4",
        "#34A853",
        "#FBBC04",
        "#EA4335",
        "#9334E6",
        "#FF6D01",
        "#46BDC6",
        "#7BAAF7",
    ]
    assert len(palette) == 8
    # index 0 → blue, index 7 → light blue
    assert palette[0] == "#4285F4"
    assert palette[7] == "#7BAAF7"
    # rotation: index 8 wraps back to 0
    color_8 = palette[8 % 8]
    assert color_8 == palette[0]
    color_15 = palette[15 % 8]
    assert color_15 == palette[7]


# --- TC row default formatting (prevent inheritance from US header) ---


def test_apply_tc_rows_default_formatting_emits_repeat_cell(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.apply_tc_rows_default_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        start_row=3,  # 1-based
        row_count=5,
        num_columns=11,
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 1
    requests = batch_calls[0].kwargs["body"]["requests"]
    assert len(requests) == 1

    repeat = requests[0]["repeatCell"]
    assert repeat["range"]["sheetId"] == 5
    # 1-based start_row=3 → 0-based startRowIndex=2, endRowIndex=7
    assert repeat["range"]["startRowIndex"] == 2
    assert repeat["range"]["endRowIndex"] == 7
    assert repeat["range"]["startColumnIndex"] == 0
    assert repeat["range"]["endColumnIndex"] == 11

    fmt = repeat["cell"]["userEnteredFormat"]
    # White background
    assert fmt["backgroundColor"] == {"red": 1.0, "green": 1.0, "blue": 1.0}
    # Black text
    assert fmt["textFormat"]["foregroundColor"] == {
        "red": 0.0,
        "green": 0.0,
        "blue": 0.0,
    }
    # Wrap and top-aligned for readability
    assert fmt["wrapStrategy"] == "WRAP"
    assert fmt["verticalAlignment"] == "TOP"
    assert fmt["horizontalAlignment"] == "LEFT"

    # fields mask must list every format field we are resetting
    assert repeat["fields"] == (
        "userEnteredFormat("
        "backgroundColor,textFormat,horizontalAlignment,"
        "verticalAlignment,wrapStrategy"
        ")"
    )


def test_apply_tc_rows_default_formatting_skips_when_zero_rows(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.apply_tc_rows_default_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        start_row=3,
        row_count=0,
        num_columns=11,
    )
    service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_apply_tc_rows_default_formatting_handles_missing_sheet(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 99, "title": "OtherSheet"}}]
    }
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.apply_tc_rows_default_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        start_row=3,
        row_count=5,
        num_columns=11,
    )
    service.spreadsheets.return_value.batchUpdate.assert_not_called()


# --- Reset all TC blocks (clears inherited color from old pushes) ---


def _mock_service_with_col_a(
    sheet_id: int, col_a_values: list[list[str]], row_count: int = 100
) -> MagicMock:
    """Build a mock service where ``values().get(A:A)`` returns the given rows."""
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [
            {
                "properties": {
                    "sheetId": sheet_id,
                    "title": "TestCases",
                    "gridProperties": {"rowCount": row_count, "columnCount": 11},
                }
            }
        ]
    }
    # values().get for column A
    col_a_resp = {"values": col_a_values}

    # Use side_effect to dispatch by range
    def _values_get(*args, **kwargs):
        response = MagicMock()
        rng = kwargs.get("range", "") or (args[0] if args else "")
        if rng.endswith("!A:A"):
            response.execute.return_value = col_a_resp
        else:
            response.execute.return_value = {"values": []}
        return response

    service.spreadsheets.return_value.values.return_value.get.side_effect = _values_get
    service.spreadsheets.return_value.batchUpdate.return_value.execute.return_value = {}
    return service


def test_reset_all_tc_blocks_emits_one_repeat_per_block(monkeypatch):
    """Two US blocks: header (row 0), US-1 (row 1), TC rows (2-4), US-2 (row 5),
    TC rows (6-9). Expect 2 repeatCell requests covering rows 2-4 and 6-9."""
    manager = GoogleSheetsManager()
    manager.reset()
    # 0-based col A rows. Row 0 = header, row 1 = [US-1], row 5 = [US-2]
    col_a = [
        ["TEST_CASE_ID"],
        ["[US-1] Login"],
        ["TC-001"],
        ["TC-002"],
        ["TC-003"],
        ["[US-2] Register"],
        ["TC-004"],
        ["TC-005"],
        ["TC-006"],
        ["TC-007"],
    ]
    service = _mock_service_with_col_a(sheet_id=5, col_a_values=col_a, row_count=10)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.reset_all_tc_blocks_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        num_columns=11,
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 1
    requests = batch_calls[0].kwargs["body"]["requests"]
    assert len(requests) == 2

    # First block: rows 2-5 (0-based, end-exclusive) → TC-001..TC-003
    r1 = requests[0]["repeatCell"]
    assert r1["range"]["sheetId"] == 5
    assert r1["range"]["startRowIndex"] == 2
    assert r1["range"]["endRowIndex"] == 5
    assert r1["range"]["startColumnIndex"] == 0
    assert r1["range"]["endColumnIndex"] == 11
    assert r1["cell"]["userEnteredFormat"]["backgroundColor"] == {
        "red": 1.0,
        "green": 1.0,
        "blue": 1.0,
    }
    assert r1["cell"]["userEnteredFormat"]["textFormat"]["foregroundColor"] == {
        "red": 0.0,
        "green": 0.0,
        "blue": 0.0,
    }

    # Second block: rows 6-10 (0-based, end-exclusive) → TC-004..TC-007
    r2 = requests[1]["repeatCell"]
    assert r2["range"]["startRowIndex"] == 6
    assert r2["range"]["endRowIndex"] == 10


def test_reset_all_tc_blocks_with_one_block_resets_all_tc(monkeypatch):
    """If only one US block exists, reset from after that US title to sheet end."""
    manager = GoogleSheetsManager()
    manager.reset()
    col_a = [
        ["TEST_CASE_ID"],
        ["[US-1] Login"],
        ["TC-001"],
        ["TC-002"],
        ["TC-003"],
    ]
    service = _mock_service_with_col_a(sheet_id=5, col_a_values=col_a, row_count=5)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.reset_all_tc_blocks_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        num_columns=11,
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 1
    requests = batch_calls[0].kwargs["body"]["requests"]
    assert len(requests) == 1
    # Single range covering rows 2..5 (0-based end-exclusive) → TC-001..TC-003
    assert requests[0]["repeatCell"]["range"]["startRowIndex"] == 2
    assert requests[0]["repeatCell"]["range"]["endRowIndex"] == 5


def test_reset_all_tc_blocks_handles_missing_sheet(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _mock_service_with_sheet(sheet_id=5)
    service.spreadsheets.return_value.get.return_value.execute.return_value = {
        "sheets": [{"properties": {"sheetId": 99, "title": "OtherSheet"}}]
    }
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.reset_all_tc_blocks_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        num_columns=11,
    )
    service.spreadsheets.return_value.batchUpdate.assert_not_called()
