"""Google Sheets API client factory using Service Account authentication."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, List, Optional

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


google_sheets_manager = GoogleSheetsManager()
