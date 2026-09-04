"""Unit tests for post-append format restoration on Google Sheets.

Regression tests for the bug where rows inserted by ``values.append``
(``INSERT_ROWS``) lost data validation (TESTER, LAST_TEST_RESULT) and
the CREATED_DATE number format, because the validation re-apply ran
BEFORE the append. The fix restores formatting AFTER the last
row-mutating call, for ALL sheets:

- ``copy_format_to_new_rows``: copyPaste PASTE_FORMAT from the nearest
  older data row (covers sheet-specific formats the tool does not know).
- ``restore_sheet_formatting``: re-apply validations (known sheets) +
  date/wrap column formats (any sheet, driven by the live header row).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from redmine_mcp_server.google_sheets_client import (  # noqa: E402
    GoogleSheetsManager,
    google_sheets_manager,
)
from redmine_mcp_server.handler_impl.tools.google_sheets import (  # noqa: E402
    _parse_append_start_row,
    append_google_sheet_impl,
    create_test_cases_on_sheet_impl,
)
from redmine_mcp_server.serializers.google_sheets import (  # noqa: E402
    TESTCASES_HEADERS,
)


def _meta(sheet_id=5, title="TestCases", row_count=1000):
    return {
        "sheets": [
            {
                "properties": {
                    "sheetId": sheet_id,
                    "title": title,
                    "gridProperties": {"rowCount": row_count},
                }
            }
        ]
    }


def _service_with_sequences(
    get_results: List[Any], values_results: Optional[Dict[str, Any]] = None
):
    """Mock service where spreadsheets().get().execute() pops from
    get_results, and values().get() answers by range substring."""
    service = MagicMock()
    service.spreadsheets.return_value.get.return_value.execute.side_effect = list(
        get_results
    )
    values_results = values_results or {}

    def _values_get(**kwargs):
        rng = kwargs.get("range", "")
        for key, result in values_results.items():
            if key in rng:
                return MagicMock(execute=MagicMock(return_value=result))
        return MagicMock(execute=MagicMock(return_value={"values": []}))

    service.spreadsheets.return_value.values.return_value.get.side_effect = (
        _values_get
    )
    append_mock = (
        service.spreadsheets.return_value.values.return_value.append
    )
    append_mock.return_value.execute.return_value = {
        "updates": {"updatedRange": "TestCases!A3:J3"}
    }
    update_mock = (
        service.spreadsheets.return_value.values.return_value.update
    )
    update_mock.return_value.execute.return_value = {}
    batch_mock = service.spreadsheets.return_value.batchUpdate
    batch_mock.return_value.execute.return_value = {}
    return service


async def _null_memory(key: str):
    return {}


def _member_memory():
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

    return fake_get_user_memory


# --- _parse_append_start_row ---


def test_parse_append_start_row():
    assert _parse_append_start_row("TestCases!A14:J24") == 14
    assert _parse_append_start_row("'My Sheet'!B2:C5") == 2
    assert _parse_append_start_row("TestCases!A:Z") is None
    assert _parse_append_start_row("") is None


# --- resolve_member_names ---


def test_resolve_member_names_none_without_memory(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    result = asyncio.run(manager.resolve_member_names("abc123", None))
    assert result is None


def test_resolve_member_names_returns_names(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    result = asyncio.run(manager.resolve_member_names("abc123", _member_memory()))
    assert result == ["Alice", "Bob"]


def test_resolve_member_names_empty_when_no_project_linked(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()

    async def fake_mem(key: str):
        return {"value": {"projects": []}}

    result = asyncio.run(manager.resolve_member_names("abc123", fake_mem))
    assert result == []


def test_add_us_section_header_returns_members(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _service_with_sequences([_meta(), _meta()])
    monkeypatch.setattr(manager, "get_service", lambda: service)

    result = asyncio.run(
        manager.add_us_section_header(
            spreadsheet_id="abc123",
            sheet_name="TestCases",
            us_title="[US-1] Login",
            row_index=2,
            color="#4285F4",
            get_user_memory=_member_memory(),
        )
    )
    assert result == ["Alice", "Bob"]


# --- reapply_column_formats ---


def test_reapply_column_formats_emits_date_number_format(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _service_with_sequences(
        [_meta()],
        values_results={"A1:Z1": {"values": [TESTCASES_HEADERS]}},
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.reapply_column_formats(spreadsheet_id="abc123", sheet_name="TestCases")

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 1
    requests = batch_calls[0].kwargs["body"]["requests"]
    date_idx = TESTCASES_HEADERS.index("CREATED_DATE")
    date_reqs = [
        r
        for r in requests
        if "repeatCell" in r
        and r["repeatCell"]["range"]["startColumnIndex"] == date_idx
        and "numberFormat" in r["repeatCell"]["fields"]
    ]
    assert len(date_reqs) == 1


# --- copy_format_to_new_rows ---


def test_copy_format_skips_when_only_us_header_above(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _service_with_sequences(
        [_meta()],
        values_results={"A1:A2": {"values": [["TEST_CASE_ID"], ["[US-1] x"]]}},
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.copy_format_to_new_rows(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        first_new_row=3,
        row_count=2,
        num_columns=10,
    )
    service.spreadsheets.return_value.batchUpdate.assert_not_called()


def test_copy_format_copies_from_nearest_data_row(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _service_with_sequences(
        [_meta()],
        values_results={
            "A1:A3": {"values": [["TEST_CASE_ID"], ["TC-001"], ["[US-2] y"]]}
        },
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.copy_format_to_new_rows(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        first_new_row=4,
        row_count=2,
        num_columns=10,
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 1
    requests = batch_calls[0].kwargs["body"]["requests"]
    assert len(requests) == 2
    for req in requests:
        assert req["copyPaste"]["pasteType"] == "PASTE_FORMAT"
        # source = row 2 (TC-001), 0-based 1..2
        assert req["copyPaste"]["source"]["startRowIndex"] == 1
        assert req["copyPaste"]["source"]["endRowIndex"] == 2
    dests = sorted(r["copyPaste"]["destination"]["startRowIndex"] for r in requests)
    assert dests == [3, 4]  # 1-based rows 4 and 5


# --- restore_sheet_formatting ---


def test_restore_emits_validation_and_date_format(monkeypatch):
    manager = GoogleSheetsManager()
    manager.reset()
    service = _service_with_sequences(
        [_meta(), _meta()],
        values_results={"A1:Z1": {"values": [TESTCASES_HEADERS]}},
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    manager.restore_sheet_formatting(
        spreadsheet_id="abc123",
        sheet_name="TestCases",
        member_names=["Alice"],
    )

    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) == 2
    bodies = [c.kwargs["body"]["requests"] for c in batch_calls]
    assert any(any("setDataValidation" in r for r in reqs) for reqs in bodies)
    assert any(
        any(
            "repeatCell" in r and "numberFormat" in r["repeatCell"]["fields"]
            for r in reqs
        )
        for reqs in bodies
    )


# --- Ordering regression tests (impl level) ---


class _RecordingService:
    """Fake Sheets service recording the order of mutating calls."""

    def __init__(
        self,
        col_a: List[List[str]],
        headers: List[str],
        title: str = "TestCases",
        append_range: str = "TestCases!A3:J3",
        append_rows: int = 1,
        append_cells: int = 10,
    ):
        self.events: List[str] = []
        self.col_a = col_a
        self.headers = headers
        self.title = title
        self.append_range = append_range
        self.append_rows = append_rows
        self.append_cells = append_cells
        self._spreadsheets = self._Spreadsheets(self)

    def spreadsheets(self):
        return self._spreadsheets

    class _Spreadsheets:
        def __init__(self, outer):
            self.outer = outer
            self._values = self._Values(outer)

        def get(self, **kwargs):
            outer = self.outer

            class _Exec:
                def execute(self):
                    return _meta(title=outer.title)

            return _Exec()

        def batchUpdate(self, **kwargs):
            outer = self.outer
            body = kwargs.get("body", {})

            class _Exec:
                def execute(self):
                    reqs = body.get("requests", [])
                    if any("setDataValidation" in r for r in reqs):
                        outer.events.append("batch.setDataValidation")
                    elif any("copyPaste" in r for r in reqs):
                        outer.events.append("batch.copyPaste")
                    elif any(
                        "repeatCell" in r
                        and "numberFormat" in r["repeatCell"].get("fields", "")
                        for r in reqs
                    ):
                        outer.events.append("batch.numberFormat")
                    else:
                        outer.events.append("batch.other")
                    return {}

            return _Exec()

        def values(self):
            return self._values

        class _Values:
            def __init__(self, outer):
                self.outer = outer

            def get(self, **kw):
                outer = self.outer
                rng = kw.get("range", "")

                class _Exec:
                    def execute(self):
                        if "A1:J1" in rng:
                            # header check in create_test_cases: empty sheet
                            return {"values": []}
                        if "A1:Z1" in rng:
                            return {"values": [outer.headers]}
                        return {"values": outer.col_a}

                return _Exec()

            def update(self, **kw):
                outer = self.outer

                class _Exec:
                    def execute(self):
                        outer.events.append("values.update")
                        return {}

                return _Exec()

            def clear(self, **kw):
                outer = self.outer

                class _Exec:
                    def execute(self):
                        outer.events.append("values.clear")
                        return {}

                return _Exec()

            def append(self, **kw):
                outer = self.outer

                class _Exec:
                    def execute(self):
                        outer.events.append("values.append")
                        return {
                            "updates": {
                                "updatedRange": outer.append_range,
                                "updatedRows": outer.append_rows,
                                "updatedCells": outer.append_cells,
                            }
                        }

                return _Exec()


def _handle_error(e, msg):
    return {"error": f"{msg}: {e}"}


def _sample_tc() -> Dict[str, str]:
    return {
        "title": "Login happy path",
        "module": "Auth",
        "precondition": "clean account",
        "steps": "open app and login",
        "expected_result": "dashboard shows",
        "tester": "",
    }


def test_create_test_cases_restores_format_after_append(monkeypatch):
    """setDataValidation + date numberFormat batchUpdates must be emitted
    AFTER values.append (the regression: they used to run only before)."""
    service = _RecordingService([["TEST_CASE_ID"]], TESTCASES_HEADERS)
    monkeypatch.setattr(
        google_sheets_manager,
        "get_service",
        lambda: service,
    )

    async def fake_set_memory(key, value):
        return {"ok": True}

    result = asyncio.run(
        create_test_cases_on_sheet_impl(
            spreadsheet_id="abc123",
            sheet_name="TestCases",
            test_cases=[_sample_tc()],
            clear_existing=False,
            us_title="Login",
            get_sheets_service=google_sheets_manager.get_service,
            get_user_memory=_null_memory,
            set_user_memory=fake_set_memory,
            handle_error=_handle_error,
        )
    )

    assert result.get("created") == 1
    events = service.events
    assert "values.append" in events
    assert "batch.setDataValidation" in events
    assert "batch.numberFormat" in events
    # The LAST validation/format restore must run after the append
    # (a pre-append re-apply from add_us_section_header is expected too).
    last_validation = max(
        i for i, e in enumerate(events) if e == "batch.setDataValidation"
    )
    last_number_format = max(
        i for i, e in enumerate(events) if e == "batch.numberFormat"
    )
    assert events.index("values.append") < last_validation
    assert events.index("values.append") < last_number_format


def test_append_google_sheet_restores_format_after_append(monkeypatch):
    service = _RecordingService(
        [["H1", "CREATED_DATE"]],
        ["H1", "CREATED_DATE"],
        title="Misc",
        append_range="Misc!A5:B6",
        append_rows=2,
        append_cells=4,
    )
    monkeypatch.setattr(
        google_sheets_manager,
        "get_service",
        lambda: service,
    )

    result = asyncio.run(
        append_google_sheet_impl(
            spreadsheet_id="abc123",
            sheet_name="Misc",
            values=[["a", "b"], ["c", "d"]],
            get_sheets_service=google_sheets_manager.get_service,
            handle_error=_handle_error,
        )
    )

    assert result.get("updated_rows") == 2
    events = service.events
    assert events.index("values.append") < events.index("batch.numberFormat")
