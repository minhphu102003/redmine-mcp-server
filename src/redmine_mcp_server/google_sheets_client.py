"""Google Sheets API client factory using Service Account authentication."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

from .serializers.google_sheets import BUGS_HEADERS, TESTCASES_HEADERS

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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

    def create_spreadsheet(self, title: str) -> Dict[str, Any]:
        """Create a new Google Spreadsheet with TestCases and Bugs sheets.

        Includes styled headers (blue bg, white bold text), frozen header row,
        and auto-resized columns.

        Args:
            title: The spreadsheet title.

        Returns:
            Dict with spreadsheet_id, spreadsheet_url, and sheet IDs.

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
            sheets_info[props["title"]] = props["sheetId"]

        # Step 2: Write headers
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
        def hex_to_rgb(hex_color: str) -> Dict[str, float]:
            h = hex_color.lstrip("#")
            return {
                "red": int(h[0:2], 16) / 255.0,
                "green": int(h[2:4], 16) / 255.0,
                "blue": int(h[4:6], 16) / 255.0,
            }

        header_format = {
            "backgroundColor": hex_to_rgb("#4472C4"),
            "textFormat": {
                "foregroundColor": hex_to_rgb("#FFFFFF"),
                "fontSize": 11,
                "bold": True,
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        }

        requests = []
        for sheet_name in ["TestCases", "Bugs"]:
            sheet_id = sheets_info[sheet_name]
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

        return {
            "spreadsheet_id": spreadsheet_id,
            "spreadsheet_url": spreadsheet_url,
            "sheets": sheets_info,
        }


google_sheets_manager = GoogleSheetsManager()
