"""Google Sheets API client factory using Service Account authentication."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from .serializers.google_sheets import (
    BUGS_COLORS,
    BUGS_HEADERS,
    BUGS_VALIDATIONS,
    TESTCASES_COLORS,
    TESTCASES_HEADERS,
    TESTCASES_VALIDATIONS,
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _hex_to_rgb(hex_color: str) -> Dict[str, float]:
    """Convert a hex color string to RGB dict for Google Sheets API."""
    h = hex_color.lstrip("#")
    return {
        "red": int(h[0:2], 16) / 255.0,
        "green": int(h[2:4], 16) / 255.0,
        "blue": int(h[4:6], 16) / 255.0,
    }


class GoogleSheetsManager:
    """Singleton manager for Google Sheets API service."""

    _instance: Optional["GoogleSheetsManager"] = None
    _service: Any = None
    _credentials_file: Optional[str] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "GoogleSheetsManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def get_service(self) -> Any:
        """Get or create the Google Sheets API service.

        Returns:
            googleapiclient.discovery.Resource: Authorized Sheets API service.

        Raises:
            ImportError: If google-api-python-client is not installed.
            FileNotFoundError: If credentials file does not exist.
            Exception: If authentication fails.
        """
        credentials_file = os.getenv(
            "GOOGLE_SHEETS_CREDENTIALS_FILE", "./credentials/service-account.json"
        )

        if self._service is not None and self._credentials_file == credentials_file:
            return self._service

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Google API client libraries are required. "
                "Install with: pip install google-api-python-client google-auth"
            )

        if not os.path.exists(credentials_file):
            raise FileNotFoundError(
                f"Google Service Account credentials file not found: "
                f"{credentials_file}. Please set "
                "GOOGLE_SHEETS_CREDENTIALS_FILE env var or place "
                "service-account.json in the credentials/ directory."
            )

        creds = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES
        )
        self._service = build("sheets", "v4", credentials=creds)
        self._credentials_file = credentials_file
        logger.info(
            "Google Sheets API service initialized with credentials: %s",
            credentials_file,
        )
        return self._service

    def reset(self) -> None:
        """Reset the service (useful for testing or credential rotation)."""
        self._service = None
        self._credentials_file = None

    def set_data_validation(
        self,
        spreadsheet_id: str,
        sheet_id: int,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
        options: List[str],
        *,
        strict: bool = True,
        input_message: str = "",
    ) -> Dict[str, Any]:
        """Set data validation (dropdown) on a cell range.

        Args:
            spreadsheet_id: Google Spreadsheet ID.
            sheet_id: Sheet tab ID (0-based, from sheet metadata).
            start_row: Start row index (0-based, inclusive).
            end_row: End row index (0-based, exclusive).
            start_col: Start column index (0-based, inclusive).
            end_col: End column index (0-based, exclusive).
            options: List of dropdown options.
            strict: If True, only values from the list are allowed.
            input_message: Message shown when user clicks the cell.

        Returns:
            API response dict.

        Raises:
            Exception: On API failure.
        """
        service = self.get_service()
        request_body = {
            "requests": [
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col,
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
        return (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=request_body)
            .execute()
        )

    def create_spreadsheet(
        self, title: str, member_names: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a new Google Spreadsheet with TestCases and Bugs sheets.

        Includes UPPERCASE headers, styled headers (blue bg, white bold text),
        frozen header row, auto-resized columns, and data validation dropdowns.

        Args:
            title: The spreadsheet title.
            member_names: List of Redmine member names for TESTER/ASSIGNED_TO dropdowns.

        Returns:
            Dict with spreadsheet_id, spreadsheet_url, sheets info.

        Raises:
            Exception: On API failure.
        """
        service = self.get_service()

        # Step 1: Create spreadsheet
        create_body = {
            "properties": {"title": title},
            "sheets": [
                {"properties": {"title": "TestCases"}},
                {"properties": {"title": "Bugs"}},
            ],
        }
        result = service.spreadsheets().create(body=create_body).execute()

        spreadsheet_id = result["spreadsheetId"]
        spreadsheet_url = result["spreadsheetUrl"]

        # Get sheet IDs from metadata
        sheets_info = {}
        for sheet in result.get("sheets", []):
            props = sheet.get("properties", {})
            sheets_info[props["title"]] = {
                "sheet_id": props["sheetId"],
                "row_count": props.get("gridProperties", {}).get("rowCount", 0),
            }

        # Step 2: Write headers (UPPERCASE)
        test_cols = len(TESTCASES_HEADERS)
        bug_cols = len(BUGS_HEADERS)
        test_last_col = chr(ord("A") + test_cols - 1) if test_cols <= 26 else "Z"
        bug_last_col = chr(ord("A") + bug_cols - 1) if bug_cols <= 26 else "Z"

        headers_body = {
            "valueInputOption": "USER_ENTERED",
            "data": [
                {
                    "range": f"TestCases!A1:{test_last_col}1",
                    "values": [TESTCASES_HEADERS],
                },
                {
                    "range": f"Bugs!A1:{bug_last_col}1",
                    "values": [BUGS_HEADERS],
                },
            ],
        }
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id, body=headers_body
        ).execute()

        # Step 3: Style headers + freeze row + auto-resize
        header_format = {
            "backgroundColor": _hex_to_rgb("#4472C4"),
            "textFormat": {
                "foregroundColor": _hex_to_rgb("#FFFFFF"),
                "fontSize": 11,
                "bold": True,
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        }

        requests = []
        for sheet_name in ["TestCases", "Bugs"]:
            sheet_id = sheets_info[sheet_name]["sheet_id"]
            num_cols = test_cols if sheet_name == "TestCases" else bug_cols

            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "cell": {"userEnteredFormat": header_format},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                    }
                }
            )
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": sheet_id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                }
            )
            requests.append(
                {
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": sheet_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": num_cols,
                        }
                    }
                }
            )

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()

        # Step 4: Set data validation dropdowns
        self._set_validations(spreadsheet_id, sheets_info, member_names or [])

        return {
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": spreadsheet_url,
            "sheets": {name: info["sheet_id"] for name, info in sheets_info.items()},
        }

    def _set_validations(
        self,
        spreadsheet_id: str,
        sheets_info: Dict[str, Dict[str, Any]],
        member_names: List[str],
    ) -> None:
        """Set data validation dropdowns for TestCases and Bugs sheets.

        Also applies conditional formatting with colors for each option.

        Args:
            spreadsheet_id: Google Spreadsheet ID.
            sheets_info: Dict mapping sheet names to their info.
            member_names: List of Redmine member names for TESTER/ASSIGNED_TO.
        """
        service = self.get_service()
        requests = []

        # TestCases validations
        test_sheet_id = sheets_info["TestCases"]["sheet_id"]
        test_row_count = sheets_info["TestCases"].get("row_count", 1000)
        for col_idx, options in TESTCASES_VALIDATIONS.items():
            if options is None:
                # Dynamic column (TESTER) - use member_names
                options = member_names if member_names else []
            if not options:
                continue

            # Add data validation
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": test_sheet_id,
                            "startRowIndex": 1,  # Skip header
                            "endRowIndex": test_row_count,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": opt} for opt in options
                                ],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                }
            )

            # Add conditional formatting with colors if available
            color_map = TESTCASES_COLORS.get(col_idx, {})
            for option in options:
                if option in color_map:
                    requests.append(
                        {
                            "addConditionalFormatRule": {
                                "rule": {
                                    "ranges": [
                                        {
                                            "sheetId": test_sheet_id,
                                            "startRowIndex": 1,
                                            "endRowIndex": test_row_count,
                                            "startColumnIndex": col_idx,
                                            "endColumnIndex": col_idx + 1,
                                        }
                                    ],
                                    "booleanRule": {
                                        "condition": {
                                            "type": "TEXT_EQ",
                                            "values": [{"userEnteredValue": option}],
                                        },
                                        "format": {
                                            "backgroundColor": _hex_to_rgb(
                                                color_map[option]
                                            )
                                        },
                                    },
                                },
                                "index": 0,
                            }
                        }
                    )

        # Bugs validations
        bug_sheet_id = sheets_info["Bugs"]["sheet_id"]
        bug_row_count = sheets_info["Bugs"].get("row_count", 1000)
        for col_idx, options in BUGS_VALIDATIONS.items():
            if options is None:
                # Dynamic column (ASSIGNED_TO) - use member_names
                options = member_names if member_names else []
            if not options:
                continue

            # Add data validation
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": bug_sheet_id,
                            "startRowIndex": 1,  # Skip header
                            "endRowIndex": bug_row_count,
                            "startColumnIndex": col_idx,
                            "endColumnIndex": col_idx + 1,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": [
                                    {"userEnteredValue": opt} for opt in options
                                ],
                            },
                            "showCustomUi": True,
                            "strict": True,
                        },
                    }
                }
            )

            # Add conditional formatting with colors if available
            color_map = BUGS_COLORS.get(col_idx, {})
            for option in options:
                if option in color_map:
                    requests.append(
                        {
                            "addConditionalFormatRule": {
                                "rule": {
                                    "ranges": [
                                        {
                                            "sheetId": bug_sheet_id,
                                            "startRowIndex": 1,
                                            "endRowIndex": bug_row_count,
                                            "startColumnIndex": col_idx,
                                            "endColumnIndex": col_idx + 1,
                                        }
                                    ],
                                    "booleanRule": {
                                        "condition": {
                                            "type": "TEXT_EQ",
                                            "values": [{"userEnteredValue": option}],
                                        },
                                        "format": {
                                            "backgroundColor": _hex_to_rgb(
                                                color_map[option]
                                            )
                                        },
                                    },
                                },
                                "index": 0,
                            }
                        }
                    )

        if requests:
            service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": requests}
            ).execute()


google_sheets_manager = GoogleSheetsManager()
