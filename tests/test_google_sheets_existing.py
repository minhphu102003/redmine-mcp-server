"""Unit tests for google_sheets_client._add_sheets_to_existing.

These tests mock the Google Sheets API service so they run without
credentials or network access.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from redmine_mcp_server.google_sheets_client import GoogleSheetsManager  # noqa: E402
from redmine_mcp_server.serializers.google_sheets import (  # noqa: E402
    BUGS_HEADERS,
    TESTCASES_HEADERS,
)


def _build_service_mock(
    *,
    existing_sheets: list[dict] | None = None,
    add_sheet_replies: list[dict] | None = None,
) -> MagicMock:
    """Build a mocked Sheets API service.

    Args:
        existing_sheets: list of {"properties": {"sheetId": N, "title": "..."}}.
        add_sheet_replies: list of replies for batchUpdate(addSheet).
    """
    existing_sheets = existing_sheets or []
    add_sheet_replies = add_sheet_replies or []

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

    spreadsheet_resource.values.return_value.batchUpdate.return_value.execute.return_value = (
        {}
    )

    return service


def test_add_sheets_to_existing_creates_both_when_missing(monkeypatch):
    """When neither TestCases nor Bugs exist, both should be created."""
    manager = GoogleSheetsManager()
    manager.reset()

    add_replies = [
        {"addSheet": {"properties": {"sheetId": 100, "title": "TestCases"}}},
        {"addSheet": {"properties": {"sheetId": 101, "title": "Bugs"}}},
    ]
    service = _build_service_mock(existing_sheets=[], add_sheet_replies=add_replies)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    result = manager._add_sheets_to_existing("fake_id_123", ["Alice", "Bob"])

    assert result["spreadsheet_id"] == "fake_id_123"
    assert result["created"] == ["TestCases", "Bugs"]
    assert result["skipped"] == []
    assert result["sheets"]["TestCases"] == 100
    assert result["sheets"]["Bugs"] == 101

    # batchUpdate was called twice: addSheet + format
    assert service.spreadsheets.return_value.batchUpdate.call_count >= 1

    # Headers were written
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.batchUpdate.assert_called_once()
    body = values_resource.batchUpdate.call_args.kwargs["body"]
    written_ranges = [d["range"] for d in body["data"]]
    assert any(r.startswith("TestCases!A1:") for r in written_ranges)
    assert any(r.startswith("Bugs!A1:") for r in written_ranges)
    assert body["data"][0]["values"][0] == TESTCASES_HEADERS
    assert body["data"][1]["values"][0] == BUGS_HEADERS


def test_add_sheets_to_existing_skips_existing(monkeypatch):
    """If TestCases already exists, only Bugs should be created."""
    manager = GoogleSheetsManager()
    manager.reset()

    existing = [
        {
            "properties": {
                "sheetId": 50,
                "title": "TestCases",
                "gridProperties": {"rowCount": 1000},
            }
        }
    ]
    add_replies = [
        {"addSheet": {"properties": {"sheetId": 51, "title": "Bugs"}}},
    ]
    service = _build_service_mock(
        existing_sheets=existing, add_sheet_replies=add_replies
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    result = manager._add_sheets_to_existing("fake_id_123", [])

    assert result["created"] == ["Bugs"]
    assert result["skipped"] == ["TestCases"]
    assert result["sheets"]["TestCases"] == 50
    assert result["sheets"]["Bugs"] == 51

    # Only one new sheet created → only one batchUpdate for addSheet
    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    add_sheet_requests = batch_calls[0].kwargs["body"]["requests"]
    assert len(add_sheet_requests) == 1
    assert "addSheet" in add_sheet_requests[0]
    assert add_sheet_requests[0]["addSheet"]["properties"]["title"] == "Bugs"

    # Only Bugs header is written (TestCases was skipped)
    values_resource = service.spreadsheets.return_value.values.return_value
    values_resource.batchUpdate.assert_called_once()
    body = values_resource.batchUpdate.call_args.kwargs["body"]
    assert len(body["data"]) == 1
    assert body["data"][0]["range"].startswith("Bugs!")


def test_add_sheets_to_existing_all_exist(monkeypatch):
    """If both sheets exist, nothing new is created, no headers written,
    but data validations are still (re-)applied — safe to re-apply."""
    manager = GoogleSheetsManager()
    manager.reset()

    existing = [
        {
            "properties": {
                "sheetId": 50,
                "title": "TestCases",
                "gridProperties": {"rowCount": 1000},
            }
        },
        {
            "properties": {
                "sheetId": 51,
                "title": "Bugs",
                "gridProperties": {"rowCount": 1000},
            }
        },
    ]
    service = _build_service_mock(existing_sheets=existing)
    monkeypatch.setattr(manager, "get_service", lambda: service)

    result = manager._add_sheets_to_existing("fake_id_123", [])

    assert result["created"] == []
    assert result["skipped"] == ["TestCases", "Bugs"]

    # No headers written (only happens for newly created sheets)
    service.spreadsheets.return_value.values.return_value.batchUpdate.assert_not_called()

    # batchUpdate IS called — once for setDataValidation (safe to re-apply).
    # The first batchUpdate call must NOT be an addSheet request.
    batch_calls = service.spreadsheets.return_value.batchUpdate.call_args_list
    assert len(batch_calls) >= 1
    first_requests = batch_calls[0].kwargs["body"]["requests"]
    assert not any("addSheet" in r for r in first_requests)


def test_create_spreadsheet_routes_to_existing(monkeypatch):
    """create_spreadsheet(spreadsheet_id=...) must delegate to _add_sheets_to_existing."""
    manager = GoogleSheetsManager()
    manager.reset()

    service = _build_service_mock(
        existing_sheets=[
            {
                "properties": {
                    "sheetId": 50,
                    "title": "TestCases",
                    "gridProperties": {"rowCount": 1000},
                }
            }
        ],
        add_sheet_replies=[
            {"addSheet": {"properties": {"sheetId": 51, "title": "Bugs"}}},
        ],
    )
    monkeypatch.setattr(manager, "get_service", lambda: service)

    result = manager.create_spreadsheet(
        title="ignored when spreadsheet_id given",
        member_names=["Alice"],
        spreadsheet_id="fake_id_123",
    )

    # The title must NOT be used to create a new spreadsheet
    service.spreadsheets.return_value.create.assert_not_called()
    assert result["spreadsheet_id"] == "fake_id_123"
    assert result["created"] == ["Bugs"]
    assert result["skipped"] == ["TestCases"]


def test_create_spreadsheet_routes_to_new(monkeypatch):
    """create_spreadsheet() without spreadsheet_id creates a new spreadsheet."""
    manager = GoogleSheetsManager()
    manager.reset()

    service = _build_service_mock()
    service.spreadsheets.return_value.create.return_value.execute.return_value = {
        "spreadsheetId": "new_id_xyz",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/new_id_xyz/edit",
        "sheets": [
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
    }
    monkeypatch.setattr(manager, "get_service", lambda: service)

    result = manager.create_spreadsheet(title="My New Sheet", member_names=["Alice"])

    service.spreadsheets.return_value.create.assert_called_once()
    assert result["spreadsheet_id"] == "new_id_xyz"
    # Existing flow: no "created"/"skipped" keys
    assert "created" not in result
    assert "skipped" not in result
