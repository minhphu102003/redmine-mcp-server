"""Undecorated Google Sheets tool implementations extracted from redmine_handler."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

HandleErrorFn = Callable[[Exception, str, Optional[dict[str, Any]]], dict[str, Any]]


# --- Tool 1: read_google_sheet ---


async def read_google_sheet_impl(
    spreadsheet_id: str,
    range_name: str,
    *,
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Read data from a Google Sheets range."""
    try:
        service = get_sheets_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        values = result.get("values", [])
        if not values:
            return {"headers": [], "rows": [], "total_rows": 0}

        headers = values[0]
        rows = values[1:] if len(values) > 1 else []
        return {
            "headers": headers,
            "rows": rows,
            "total_rows": len(rows),
        }
    except Exception as e:
        return handle_error(e, f"reading Google Sheet {spreadsheet_id}")


# --- Tool 2: write_google_sheet ---


async def write_google_sheet_impl(
    spreadsheet_id: str,
    range_name: str,
    values: List[List[str]],
    *,
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Write data to a specific Google Sheets range (overwrite)."""
    try:
        service = get_sheets_service()
        body = {"values": values}
        result = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                body=body,
            )
            .execute()
        )
        return {
            "updated_cells": result.get("updatedCells", 0),
            "updated_rows": result.get("updatedRows", 0),
            "range": result.get("updatedRange", range_name),
        }
    except Exception as e:
        return handle_error(e, f"writing to Google Sheet {spreadsheet_id}")


# --- Tool 3: append_google_sheet ---


import re

# Markdown detection compiled pattern (shared by append and create_test_cases)
_MARKDOWN_RE = re.compile(r"\*\*|\*|`|\[.+\]\(")


def _has_markdown(text: str) -> bool:
    """Return True if text contains bold/italic/code/hyperlink markdown."""
    return bool(_MARKDOWN_RE.search(text or ""))


def _rich_text_runs(text: str) -> List[Dict[str, Any]]:
    """Parse markdown text and return Google Sheets textFormatRuns list.

    Supports: ***bold italic***, **bold**, *italic*, `code`, [label](url).
    """
    from ...serializers.google_sheets import parse_markdown_to_rich_text

    return parse_markdown_to_rich_text(text)


async def append_google_sheet_impl(
    spreadsheet_id: str,
    sheet_name: str,
    values: List[List[str]],
    *,
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Append rows to the end of a Google Sheet.

    Cells containing markdown (bold/italic/code/hyperlink) in the first
    5 columns are automatically formatted as rich text after writing.
    """
    try:
        service = get_sheets_service()
        body = {"values": values}
        range_name = f"{sheet_name}!A:Z"
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )
        updates = result.get("updates", {})
        updated_rows = updates.get("updatedRows", 0)
        table_range = updates.get("updatedRange", range_name)

        # Post-process: apply rich text to markdown cells in the written rows
        if updated_rows > 0:
            _apply_markdown_rich_text(
                service=service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                start_row=1,  # rows appended from row 1 onward
                row_count=updated_rows,
                markdown_col_indices={3, 4, 5},  # D, E, F
            )

        return {
            "updated_rows": updated_rows,
            "updated_cells": updates.get("updatedCells", 0),
            "table_range": table_range,
        }
    except Exception as e:
        return handle_error(e, f"appending to Google Sheet {spreadsheet_id}")


def _apply_markdown_rich_text(
    service: Any,
    spreadsheet_id: str,
    sheet_name: str,
    start_row: int,
    row_count: int,
    markdown_col_indices: set[int],
) -> None:
    """Apply rich-text formatting to cells in markdown columns that contain
    markdown tokens, using textFormatRuns via repeatCell."""
    try:
        # Read back the written values to find which cells need formatting
        end_row = start_row + row_count
        read_range = f"{sheet_name}!A{start_row}:Z{end_row}"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=read_range)
            .execute()
        )
        written = result.get("values", [])
    except Exception:
        return

    if not written:
        return

    # Build repeatCell requests for cells with markdown
    requests: List[Dict[str, Any]] = []
    for row_offset, row in enumerate(written):
        actual_row = start_row + row_offset
        for col_idx in markdown_col_indices:
            if col_idx >= len(row):
                continue
            cell_text = row[col_idx] if row[col_idx] else ""
            if not _has_markdown(cell_text):
                continue
            rich_runs = _rich_text_runs(cell_text)
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": None,  # filled after sheetId lookup
                            "startRowIndex": actual_row - 1,
                            "endRowIndex": actual_row,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "cell": {"textFormatRuns": rich_runs},
                        "fields": "textFormatRuns",
                    }
                }
            )

    if not requests:
        return

    # Resolve sheetId from sheet name
    try:
        meta = (
            service.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties",
            )
            .execute()
        )
        sheet_id_map = {
            s["properties"]["title"]: s["properties"]["sheetId"]
            for s in meta.get("sheets", [])
        }
        target_sheet_id = sheet_id_map.get(sheet_name)
    except Exception:
        return

    if target_sheet_id is None:
        return

    for req in requests:
        req["repeatCell"]["range"]["sheetId"] = target_sheet_id

    try:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()
    except Exception as e:
        logger.warning("_apply_markdown_rich_text failed: %s", e)


# --- Tool 4: get_sheet_metadata ---


async def get_sheet_metadata_impl(
    spreadsheet_id: str,
    *,
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Get metadata about all sheets in a spreadsheet."""
    try:
        service = get_sheets_service()
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets_info = []
        for sheet in spreadsheet.get("sheets", []):
            props = sheet.get("properties", {})
            sheet_title = props.get("title", "")
            sheet_id = props.get("sheetId", 0)
            row_count = props.get("gridProperties", {}).get("rowCount", 0)

            # Get headers (first row)
            try:
                header_result = (
                    service.spreadsheets()
                    .values()
                    .get(
                        spreadsheetId=spreadsheet_id,
                        range=f"{sheet_title}!A1:Z1",
                    )
                    .execute()
                )
                header_values = header_result.get("values", [])
                headers = header_values[0] if header_values else []
            except Exception:
                headers = []

            sheets_info.append(
                {
                    "name": sheet_title,
                    "sheet_id": sheet_id,
                    "headers": headers,
                    "row_count": row_count,
                }
            )

        return {
            "spreadsheet_title": spreadsheet.get("properties", {}).get("title", ""),
            "sheets": sheets_info,
        }
    except Exception as e:
        return handle_error(e, f"getting metadata for Google Sheet {spreadsheet_id}")


# --- Tool 5: create_test_cases_on_sheet ---


async def create_test_cases_on_sheet_impl(
    spreadsheet_id: str,
    sheet_name: str,
    test_cases: List[Dict[str, str]],
    clear_existing: bool,
    *,
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Parse test cases and push to Google Sheets. Create Bugs sheet if needed."""
    try:
        from ...serializers.google_sheets import (
            TESTCASES_HEADERS,
            BUGS_HEADERS,
            build_test_case_id,
            parse_markdown_to_rich_text,
            validate_test_case,
        )

        service = get_sheets_service()
        today = date.today().isoformat()

        # Validate all test cases
        all_errors = []
        for i, tc in enumerate(test_cases):
            errors = validate_test_case(tc)
            if errors:
                all_errors.append({"index": i, "errors": errors})
        if all_errors:
            return {
                "error": "Validation failed for some test cases",
                "details": all_errors[:5],
            }

        # Get existing test case IDs to generate next ID
        existing_ids: List[str] = []
        try:
            existing = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A:A",
                )
                .execute()
            )
            for row in existing.get("values", [])[1:]:  # skip header
                if row and row[0]:
                    existing_ids.append(row[0])
        except Exception:
            pass

        # Build rows
        rows = []
        for tc in test_cases:
            tc_id = build_test_case_id(existing_ids)
            existing_ids.append(tc_id)
            row = [
                tc_id,  # A: test_case_id
                tc.get("module", ""),  # B: module
                tc.get("title", ""),  # C: title
                tc.get("precondition", ""),  # D: precondition
                tc.get("steps", ""),  # E: steps
                tc.get("expected_result", ""),  # F: expected_result
                tc.get("tester", ""),  # G: tester
                today,  # H: created_date
                "Not Tested",  # I: last_test_result
                "",  # J: last_test_date
            ]
            rows.append(row)

        if not rows:
            return {"error": "No test cases to create"}

        # Check if sheet exists, create if not
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_names = [s["properties"]["title"] for s in spreadsheet.get("sheets", [])]

        if sheet_name not in sheet_names:
            # Create the test cases sheet
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    "requests": [{"addSheet": {"properties": {"title": sheet_name}}}]
                },
            ).execute()

        # Clear existing data if requested
        if clear_existing:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A2:Z",
                body={},
            ).execute()

        # Write headers if sheet is empty, then append rows
        # First try to read header
        try:
            header_check = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A1:J1",
                )
                .execute()
            )
            existing_headers = header_check.get("values", [])
            if not existing_headers:
                # Write headers first
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [TESTCASES_HEADERS]},
                ).execute()
        except Exception:
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [TESTCASES_HEADERS]},
            ).execute()

        # Append test case rows
        body = {"values": rows}
        append_result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A:Z",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

        # Post-process: apply rich text to markdown columns (precondition D, steps E, expected_result F)
        if rows:
            first_new_row = (
                len(existing_ids) + 2
            )  # row index (1-based) of first appended row
            _apply_markdown_rich_text(
                service=service,
                spreadsheet_id=spreadsheet_id,
                sheet_name=sheet_name,
                start_row=first_new_row,
                row_count=len(rows),
                markdown_col_indices={
                    3,
                    4,
                    5,
                },  # D: precondition, E: steps, F: expected_result
            )

        # Create Bugs sheet if it doesn't exist
        bugs_sheet_name = "Bugs"
        bugs_sheet_ready = bugs_sheet_name in sheet_names
        if not bugs_sheet_ready:
            try:
                service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "requests": [
                            {"addSheet": {"properties": {"title": bugs_sheet_name}}}
                        ]
                    },
                ).execute()
                # Write Bugs headers
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{bugs_sheet_name}!A1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [BUGS_HEADERS]},
                ).execute()
                bugs_sheet_ready = True
            except Exception as e:
                logger.warning("Failed to create Bugs sheet: %s", e)

        updates = append_result.get("updates", {})
        return {
            "created": len(rows),
            "sheet_name": sheet_name,
            "first_id": rows[0][0] if rows else None,
            "last_id": rows[-1][0] if rows else None,
            "range": updates.get("updatedRange", f"{sheet_name}"),
            "bugs_sheet_ready": bugs_sheet_ready,
            "bugs_sheet_name": bugs_sheet_name,
        }
    except Exception as e:
        return handle_error(e, f"creating test cases on Google Sheet {spreadsheet_id}")


# --- Tool 6: create_redmine_issues_from_bugs ---


async def create_redmine_issues_from_bugs_impl(
    spreadsheet_id: str,
    sheet_name: str,
    project_id: int,
    tracker_id: int,
    assigned_to_id: Optional[int],
    bug_row_range: Optional[str],
    *,
    get_sheets_service: Callable[[], Any],
    get_client: Callable[[], Any],
    map_priority: Callable[[str], int],
    is_read_only_mode: Callable[[], bool],
    read_only_error: dict[str, Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Read bug rows from Sheet, create Redmine issues, write issue IDs back."""
    if is_read_only_mode():
        return read_only_error
    try:
        from ...serializers.google_sheets import (
            bug_row_to_dict,
            format_redmine_issue_id,
        )

        service = get_sheets_service()

        # Pre-read TestCases sheet to build test_case_id → module mapping
        test_case_sheet_name = "TestCases"
        tc_module_map: Dict[str, str] = {}
        try:
            tc_result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=f"{test_case_sheet_name}!A:B",
                )
                .execute()
            )
            tc_rows = tc_result.get("values", [])
            # tc_rows[0] is header, data starts from index 1
            for tc_row in tc_rows[1:]:
                if tc_row and len(tc_row) >= 2:
                    tc_id = tc_row[0].strip()
                    module = tc_row[1].strip() if len(tc_row) > 1 else ""
                    if tc_id:
                        tc_module_map[tc_id] = module
        except Exception as e:
            logger.warning(
                "Failed to pre-read TestCases sheet for module lookup: %s", e
            )

        # Read "New" status ID from Redmine for default status
        client = get_client()
        new_status_id = None
        try:
            statuses = client.issue_status.all()
            for status in statuses:
                if status.name == "New":
                    new_status_id = status.id
                    break
        except Exception as e:
            logger.warning("Failed to read Redmine statuses: %s", e)

        # Read all bug rows
        read_range = (
            f"{sheet_name}!A2:M"
            if not bug_row_range
            else f"{sheet_name}!{bug_row_range}"
        )
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=read_range)
            .execute()
        )
        all_rows = result.get("values", [])

        if not all_rows:
            return {"created": 0, "failed": 0, "issues": [], "errors": []}

        # Filter: status = "New" and redmine_issue_id is empty
        bugs_to_create = []
        for i, row in enumerate(all_rows):
            row_dict = bug_row_to_dict(row)

            status = row_dict.get("status", "")
            redmine_id = row_dict.get("redmine_issue_id", "")

            if status == "New" and not redmine_id.strip():
                bugs_to_create.append((i, row_dict))

        if not bugs_to_create:
            return {"created": 0, "failed": 0, "issues": [], "errors": []}

        # Create Redmine issues
        created_issues = []
        errors = []

        for row_index, bug in bugs_to_create:
            try:
                priority_id = map_priority(bug.get("priority", "Medium"))

                # Auto-lookup module from linked test case
                linked_tc_id = bug.get("test_case_id", "").strip()
                module = tc_module_map.get(linked_tc_id, "") if linked_tc_id else ""

                # Format subject: [<module>] [BUG] <title>
                title = bug.get("title", "Untitled Bug")
                if module:
                    subject = f"[{module}] [BUG] {title}"
                else:
                    subject = f"[BUG] {title}"

                # Build issue fields
                issue_fields = {
                    "project_id": project_id,
                    "tracker_id": tracker_id,
                    "subject": subject,
                    "description": bug.get("description", ""),
                    "priority_id": priority_id,
                }

                if new_status_id:
                    issue_fields["status_id"] = new_status_id

                if assigned_to_id:
                    issue_fields["assigned_to_id"] = assigned_to_id

                # Create issue on Redmine
                issue = client.issue.create(**issue_fields)
                issue_id = issue.id

                # Update sheet row: write redmine_issue_id and change status to Open
                sheet_row = row_index + 2  # +2 because row 1 = header, 0-indexed

                # Column H = redmine_issue_id (index 7)
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!H{sheet_row}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[format_redmine_issue_id(issue_id)]]},
                ).execute()

                # Column F = status (index 5) → "Open"
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!F{sheet_row}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [["Open"]]},
                ).execute()

                created_issues.append(
                    {
                        "bug_id": bug.get("bug_id", ""),
                        "redmine_issue_id": issue_id,
                        "subject": subject,
                    }
                )
            except Exception as e:
                errors.append(
                    {
                        "bug_id": bug.get("bug_id", ""),
                        "error": str(e),
                    }
                )

        return {
            "created": len(created_issues),
            "failed": len(errors),
            "issues": created_issues,
            "errors": errors,
        }
    except Exception as e:
        return handle_error(
            e, f"creating Redmine issues from Google Sheet {spreadsheet_id}"
        )


# --- Tool 7: sync_redmine_status_to_sheet ---


async def sync_redmine_status_to_sheet_impl(
    spreadsheet_id: str,
    bug_sheet: str,
    test_case_sheet: str,
    *,
    get_sheets_service: Callable[[], Any],
    get_client: Callable[[], Any],
    map_redmine_status: Callable[[str, float], Optional[str]],
    parse_reject_reason: Callable[[List[Dict[str, Any]]], str],
    is_duplicate_rejection: Callable[[str], bool],
    parse_duplicate_issue_id: Callable[[str], Optional[str]],
    is_read_only_mode: Callable[[], bool],
    read_only_error: dict[str, Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Sync Redmine issue statuses back to Google Sheet."""
    if is_read_only_mode():
        return read_only_error
    try:
        from ...serializers.google_sheets import bug_row_to_dict

        service = get_sheets_service()
        today = date.today().isoformat()

        # Read all bug rows
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{bug_sheet}!A2:M")
            .execute()
        )
        all_rows = result.get("values", [])

        if not all_rows:
            return {"checked": 0, "updated": 0, "summary": {}, "details": []}

        client = get_client()
        updated_details = []
        summary: Dict[str, int] = {}
        checked = 0
        updated = 0

        # Pre-read TestCases sheet once to avoid N+1 reads
        tc_row_map: Dict[str, int] = {}
        try:
            tc_result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=f"{test_case_sheet}!A:A",
                )
                .execute()
            )
            tc_rows = tc_result.get("values", [])
            for ti, tc_row in enumerate(tc_rows):
                if tc_row and tc_row[0]:
                    tc_row_map[tc_row[0]] = ti + 1
        except Exception as e:
            logger.warning("Failed to pre-read TestCases sheet: %s", e)

        for i, row in enumerate(all_rows):
            row_dict = bug_row_to_dict(row)

            redmine_id_str = row_dict.get("redmine_issue_id", "")
            if not redmine_id_str.strip():
                continue

            # Parse single issue ID
            redmine_id = None
            clean_id = redmine_id_str.strip().split(",")[0].strip()
            try:
                redmine_id = int(clean_id)
            except ValueError:
                continue

            checked += 1
            sheet_row = i + 2  # +2 for header + 0-indexed

            try:
                issue = client.issue.get(
                    redmine_id,
                    include=["journals"],
                )
                redmine_status = issue.status.name
                done_ratio = getattr(issue, "done_ratio", 0) or 0
                journals = getattr(issue, "journals", []) or []

                # Convert journals to dicts for parsing
                journal_dicts = []
                for j in journals:
                    journal_dicts.append(
                        {
                            "notes": getattr(j, "notes", "") or "",
                            "created_on": str(getattr(j, "created_on", "")),
                        }
                    )

                # Map Redmine status → Sheet status
                new_sheet_status = map_redmine_status(redmine_status, done_ratio)

                # Handle rejection
                if redmine_status.lower() == "rejected":
                    reject_reason = parse_reject_reason(journal_dicts)
                    # Column L = reject_reason (index 11)
                    service.spreadsheets().values().update(
                        spreadsheetId=spreadsheet_id,
                        range=f"{bug_sheet}!L{sheet_row}",
                        valueInputOption="USER_ENTERED",
                        body={"values": [[reject_reason]]},
                    ).execute()

                    # Check if duplicate
                    if is_duplicate_rejection(reject_reason):
                        new_sheet_status = "Duplicate"
                        dup_issue_id = parse_duplicate_issue_id(reject_reason)
                        if dup_issue_id:
                            # Column M = duplicate_of (index 12)
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"{bug_sheet}!M{sheet_row}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[dup_issue_id]]},
                            ).execute()

                if new_sheet_status:
                    old_status = row_dict.get("status", "")
                    if old_status != new_sheet_status:
                        # Column F = status (index 5)
                        service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f"{bug_sheet}!F{sheet_row}",
                            valueInputOption="USER_ENTERED",
                            body={"values": [[new_sheet_status]]},
                        ).execute()
                        updated += 1
                        updated_details.append(
                            {
                                "redmine_issue_id": redmine_id,
                                "old_status": old_status,
                                "new_status": new_sheet_status,
                            }
                        )

                # Column I = redmine_status (index 8)
                service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{bug_sheet}!I{sheet_row}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[redmine_status]]},
                ).execute()

                # Track summary
                status_key = new_sheet_status or row_dict.get("status", "Unknown")
                summary[status_key] = summary.get(status_key, 0) + 1

                # If Closed → update TestCases last_test_result
                if new_sheet_status == "Closed":
                    test_case_id = row_dict.get("test_case_id", "")
                    if test_case_id and test_case_id in tc_row_map:
                        try:
                            tc_sheet_row = tc_row_map[test_case_id]
                            # Column I = last_test_result (index 8)
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"{test_case_sheet}!I{tc_sheet_row}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [["Pass"]]},
                            ).execute()
                            # Column J = last_test_date (index 9)
                            service.spreadsheets().values().update(
                                spreadsheetId=spreadsheet_id,
                                range=f"{test_case_sheet}!J{tc_sheet_row}",
                                valueInputOption="USER_ENTERED",
                                body={"values": [[today]]},
                            ).execute()
                        except Exception as e:
                            logger.warning(
                                "Failed to update test case %s: %s",
                                test_case_id,
                                e,
                            )

            except Exception as e:
                logger.warning("Failed to sync issue %s: %s", redmine_id, e)
                summary["error"] = summary.get("error", 0) + 1

        return {
            "checked": checked,
            "updated": updated,
            "summary": summary,
            "details": updated_details,
        }
    except Exception as e:
        return handle_error(
            e, f"syncing Redmine status to Google Sheet {spreadsheet_id}"
        )


# --- Tool 8: reopen_bug ---


async def reopen_bug_impl(
    spreadsheet_id: str,
    sheet_name: str,
    bug_id: str,
    reopen_note: str,
    project_id: int,
    *,
    get_sheets_service: Callable[[], Any],
    get_client: Callable[[], Any],
    is_read_only_mode: Callable[[], bool],
    read_only_error: dict[str, Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Reopen a bug by updating status on Redmine and sheet."""
    if is_read_only_mode():
        return read_only_error
    try:
        from ...serializers.google_sheets import (
            bug_row_to_dict,
            is_valid_status_transition,
            parse_redmine_issue_id,
        )

        service = get_sheets_service()

        # Find the bug row by bug_id
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=f"{sheet_name}!A2:M")
            .execute()
        )
        all_rows = result.get("values", [])

        target_row_index = None
        target_row_dict = None
        for i, row in enumerate(all_rows):
            row_dict = bug_row_to_dict(row)
            if row_dict.get("bug_id", "") == bug_id:
                target_row_index = i
                target_row_dict = row_dict
                break

        if target_row_dict is None:
            return {"error": f"Bug {bug_id} not found in sheet"}

        current_status = target_row_dict.get("status", "")
        if not is_valid_status_transition(current_status, "Reopen"):
            return {
                "error": (
                    f"Cannot reopen bug from status '{current_status}'. "
                    f"Valid transitions to Reopen: Done → Reopen"
                )
            }

        redmine_id = parse_redmine_issue_id(target_row_dict.get("redmine_issue_id", ""))
        if not redmine_id:
            return {"error": f"Bug {bug_id} has no Redmine issue ID"}

        # Update Redmine: set status to "In Progress" and add note
        redmine_updated = False
        client = get_client()
        try:
            issue = client.issue.get(redmine_id)

            # Find "In Progress" status ID
            statuses = client.issue_status.all()
            target_status_id = None
            for status in statuses:
                if status.name == "In Progress":
                    target_status_id = status.id
                    break

            if target_status_id:
                issue.status_id = target_status_id
            issue.notes = f"[REOPEN] {reopen_note}"
            issue.save()
            redmine_updated = True
        except Exception as e:
            return handle_error(e, f"updating Redmine issue {redmine_id} for reopen")

        # Update sheet
        sheet_row = target_row_index + 2  # +2 for header + 0-indexed
        sheet_updated = False
        try:
            # Column F = status (index 5) → "Reopen"
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!F{sheet_row}",
                valueInputOption="USER_ENTERED",
                body={"values": [["Reopen"]]},
            ).execute()

            # Column I = redmine_status (index 8) → "In Progress"
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!I{sheet_row}",
                valueInputOption="USER_ENTERED",
                body={"values": [["In Progress"]]},
            ).execute()
            sheet_updated = True
        except Exception as e:
            logger.warning(
                "Redmine issue %s reopened but sheet update failed: %s",
                redmine_id,
                e,
            )

        return {
            "success": redmine_updated,
            "redmine_issue_id": redmine_id,
            "title": target_row_dict.get("title", ""),
            "reopen_note": reopen_note,
            "sheet_synced": sheet_updated,
        }
    except Exception as e:
        return handle_error(e, f"reopening bug {bug_id}")


# --- Tool 9: set_sheet_data_validation ---


async def set_sheet_data_validation_impl(
    spreadsheet_id: str,
    sheet_name: str,
    column: int,
    options: List[str],
    *,
    start_row: int = 2,
    end_row: int = 1000,
    strict: bool = True,
    input_message: str = "",
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Set data validation (dropdown) on a column in a Google Sheet.

    Args:
        spreadsheet_id: Google Spreadsheet ID.
        sheet_name: Target sheet name (e.g. 'TestCases').
        column: Column index (0-based, e.g. 6 for column G).
        options: List of dropdown options.
        start_row: Start row (0-based, default 2 = row 3 in sheet, after headers).
        end_row: End row (0-based, default 1000).
        strict: If True, only values from the list are allowed.
        input_message: Message shown when user clicks the cell.
    """
    try:
        service = get_sheets_service()

        # Get sheet ID from sheet name
        meta = (
            service.spreadsheets()
            .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
            .execute()
        )
        sheet_id = None
        for s in meta.get("sheets", []):
            if s.get("properties", {}).get("title") == sheet_name:
                sheet_id = s["properties"]["sheetId"]
                break
        if sheet_id is None:
            return {"error": f"Sheet '{sheet_name}' not found in spreadsheet"}

        # Set data validation via batchUpdate
        request_body = {
            "requests": [
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": column,
                            "endColumnIndex": column + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": opt} for opt in options
                                ],
                            },
                            "showCustomUi": True,
                            "strict": strict,
                            **(
                                {"inputMessage": input_message} if input_message else {}
                            ),
                        },
                    }
                }
            ]
        }
        (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
            .execute()
        )

        return {
            "success": True,
            "sheet_name": sheet_name,
            "column": column,
            "options_count": len(options),
            "options": options,
            "start_row": start_row + 1,
            "end_row": end_row + 1,
            "strict": strict,
        }
    except Exception as e:
        return handle_error(
            e, f"setting data validation on {sheet_name} column {column}"
        )


# --- Tool 10: create_test_sheet_structure ---


async def create_test_sheet_structure_impl(
    title: str,
    member_names: Optional[List[str]] = None,
    spreadsheet_id: Optional[str] = None,
    *,
    get_sheets_service: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Create a new Google Spreadsheet with TestCases and Bugs sheets,
    OR add TestCases/Bugs sheets to an existing spreadsheet.

    Includes UPPERCASE headers, styled headers (blue bg, white bold text),
    frozen header row, column widths sized to each header text + consistent
    12px L/R padding, and data validation dropdowns.

    Args:
        title: The spreadsheet title (used only when creating a new spreadsheet).
        member_names: List of Redmine member names for TESTER/ASSIGNED_TO dropdowns.
        spreadsheet_id: If provided, add TestCases and Bugs sheets to the existing
            spreadsheet with this ID instead of creating a new one. Sheets that
            already exist are skipped (no overwrite).

    Returns:
        Dict with success, spreadsheet_id, spreadsheet_url, sheets info,
        and (for existing spreadsheets) created/skipped lists.
    """
    try:
        from redmine_mcp_server.google_sheets_client import google_sheets_manager

        result = google_sheets_manager.create_spreadsheet(
            title,
            member_names=member_names,
            spreadsheet_id=spreadsheet_id,
        )
        response: Dict[str, Any] = {
            "success": True,
            "spreadsheet_id": result["spreadsheet_id"],
            "spreadsheet_url": result["spreadsheet_url"],
            "sheets": result["sheets"],
        }
        if spreadsheet_id:
            response["created"] = result.get("created", [])
            response["skipped"] = result.get("skipped", [])
            response["message"] = (
                f"TestCases and Bugs sheets added to existing spreadsheet. "
                f"Created: {result.get('created', [])}, "
                f"Skipped (already exist): {result.get('skipped', [])}."
            )
        else:
            response["message"] = (
                f"Spreadsheet '{title}' created with sheets: TestCases, Bugs. "
                f"UPPERCASE headers + data validation dropdowns applied. "
                f"Share it with the service account email before using QA skills."
            )
        return response
    except Exception as e:
        if spreadsheet_id:
            return handle_error(e, f"adding sheets to spreadsheet '{spreadsheet_id}'")
        return handle_error(e, f"creating spreadsheet '{title}'")
