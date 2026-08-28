"""Google Sheets data serialization, validation, and status transition logic."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# --- Constants ---

# Internal keys (lowercase) - used for dict access and validation
TESTCASES_KEYS = [
    "test_case_id",
    "module",
    "title",
    "precondition",
    "steps",
    "expected_result",
    "tester",
    "created_date",
    "last_test_result",
    "last_test_date",
]

BUGS_KEYS = [
    "bug_id",
    "test_case_id",
    "title",
    "description",
    "priority",
    "status",
    "assigned_to",
    "redmine_issue_id",
    "redmine_status",
    "reporter",
    "report_date",
    "reject_reason",
    "duplicate_of",
]

# Display headers (UPPERCASE) - written to Google Sheets
TESTCASES_HEADERS = [k.upper() for k in TESTCASES_KEYS]
BUGS_HEADERS = [k.upper() for k in BUGS_KEYS]

VALID_BUG_STATUSES = [
    "New",
    "Open",
    "In Progress",
    "Done",
    "Reopen",
    "Closed",
    "Reject",
    "Deferred",
    "Need Info",
    "Duplicate",
]

VALID_TEST_RESULTS = ["Pass", "Fail", "Not Tested"]

VALID_PRIORITIES = ["High", "Medium", "Low"]

# Color mappings for dropdown options (hex colors)
TEST_RESULT_COLORS = {
    "Pass": "#00FF00",  # Green
    "Fail": "#FF0000",  # Red
    "Not Tested": "#D9D9D9",  # Gray
}

PRIORITY_COLORS = {
    "High": "#FF0000",  # Red
    "Medium": "#FFC000",  # Orange
    "Low": "#00FF00",  # Green
}

STATUS_COLORS = {
    "New": "#D9D9D9",  # Gray
    "Open": "#BDD7EE",  # Light blue
    "In Progress": "#FFC000",  # Orange
    "Done": "#00FF00",  # Green
    "Reopen": "#FF9999",  # Light red
    "Closed": "#A9A9A9",  # Dark gray
    "Reject": "#FF0000",  # Red
    "Deferred": "#FF9999",  # Light red
    "Need Info": "#FFC000",  # Orange
    "Duplicate": "#A9A9A9",  # Dark gray
}

# Data validation column indices (0-based)
TESTCASES_VALIDATIONS = {
    6: None,  # TESTER - dynamic from Redmine members
    8: VALID_TEST_RESULTS,  # LAST_TEST_RESULT
}

BUGS_VALIDATIONS = {
    4: VALID_PRIORITIES,  # PRIORITY
    5: VALID_BUG_STATUSES,  # STATUS
    6: None,  # ASSIGNED_TO - dynamic from Redmine members
}

# Conditional formatting color mappings (column index -> {option: hex_color})
TESTCASES_COLORS = {
    8: TEST_RESULT_COLORS,  # LAST_TEST_RESULT
}

BUGS_COLORS = {
    4: PRIORITY_COLORS,  # PRIORITY
    5: STATUS_COLORS,  # STATUS
}

# --- Status Transitions ---

VALID_STATUS_TRANSITIONS: Dict[str, List[str]] = {
    "New": ["Open"],
    "Open": ["In Progress", "Reject", "Deferred", "Need Info", "Duplicate"],
    "In Progress": ["Done", "Reject", "Deferred", "Need Info"],
    "Done": ["Closed", "Reopen", "Reject"],
    "Reopen": ["In Progress"],
    "Closed": [],
    "Reject": [],
    "Deferred": ["Open"],
    "Need Info": ["Open"],
    "Duplicate": [],
}


def is_valid_status_transition(current_status: str, target_status: str) -> bool:
    """Check if a status transition is valid."""
    allowed = VALID_STATUS_TRANSITIONS.get(current_status, [])
    return target_status in allowed


# --- ID Generation ---


def build_test_case_id(existing_ids: List[str]) -> str:
    """Generate the next test case ID (TC-001, TC-002, ...)."""
    max_num = 0
    for tc_id in existing_ids:
        match = re.match(r"^TC-(\d+)$", tc_id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    return f"TC-{max_num + 1:03d}"


def build_bug_id(existing_ids: List[str]) -> str:
    """Generate the next bug ID (BUG-001, BUG-002, ...)."""
    max_num = 0
    for bug_id in existing_ids:
        match = re.match(r"^BUG-(\d+)$", bug_id)
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    return f"BUG-{max_num + 1:03d}"


# --- Validation ---


def validate_test_case(row: Dict[str, str]) -> List[str]:
    """Validate a test case row. Returns list of error messages (empty = valid)."""
    errors = []
    required_fields = ["title", "module", "steps", "expected_result"]
    for field in required_fields:
        if not row.get(field, "").strip():
            errors.append(f"Missing required field: {field}")
    return errors


def validate_bug(row: Dict[str, str]) -> List[str]:
    """Validate a bug row. Returns list of error messages (empty = valid)."""
    errors = []
    required_fields = ["title", "description", "priority"]
    for field in required_fields:
        if not row.get(field, "").strip():
            errors.append(f"Missing required field: {field}")

    priority = row.get("priority", "")
    if priority and priority not in VALID_PRIORITIES:
        errors.append(
            f"Invalid priority: {priority}. Must be one of {VALID_PRIORITIES}"
        )

    status = row.get("status", "")
    if status and status not in VALID_BUG_STATUSES:
        errors.append(f"Invalid status: {status}. Must be one of {VALID_BUG_STATUSES}")

    return errors


# --- Priority Mapping ---


def map_priority_to_redmine(priority: str) -> int:
    """Map sheet priority to Redmine priority_id.

    Note: This is a default mapping. Actual priority IDs depend on the Redmine
    instance configuration. The skill should ask the user to confirm before syncing.
    """
    mapping = {
        "High": 4,
        "Medium": 3,
        "Low": 2,
    }
    return mapping.get(priority, 3)


# --- Redmine Issue ID Handling ---


def parse_redmine_issue_id(id_string: str) -> Optional[int]:
    """Parse redmine_issue_id from sheet. Always returns a single int or None."""
    if not id_string or not id_string.strip():
        return None
    clean = id_string.strip().split(",")[0].strip()
    if not clean:
        return None
    try:
        return int(clean)
    except ValueError:
        return None


def format_redmine_issue_id(issue_id: int) -> str:
    """Format a Redmine issue ID for the sheet."""
    return str(issue_id)


# --- Rejection Reason Parsing ---


def parse_reject_reason(journals: List[Dict[str, Any]]) -> str:
    """Extract reject reason from Redmine journals/notes."""
    for journal in reversed(journals):
        notes = journal.get("notes", "")
        if notes:
            return notes
    return ""


def is_duplicate_rejection(reject_reason: str) -> bool:
    """Check if a reject reason indicates the bug is a duplicate."""
    lower = reject_reason.lower()
    return "duplicate" in lower


def parse_duplicate_issue_id(reject_reason: str) -> Optional[str]:
    """Try to extract the original issue ID from a duplicate rejection reason.

    Looks for patterns like: "Duplicate of #1234", "duplicate of issue 1234", etc.
    """
    patterns = [
        r"duplicate\s+of\s+#(\d+)",
        r"duplicate\s+of\s+issue\s+(\d+)",
        r"duplicate\s+of\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, reject_reason, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


# --- Redmine Status Mapping ---


def map_redmine_status_to_sheet(
    redmine_status: str,
    done_ratio: float = 0,
) -> Optional[str]:
    """Map Redmine status name to sheet status.

    Returns None if no mapping found (status unchanged).
    """
    mapping = {
        "New": "Open",
        "In Progress": "In Progress",
        "Resolved": "Done" if done_ratio >= 100 else "In Progress",
        "Closed": "Closed",
        "Rejected": "Reject",
        "Deferred": "Deferred",
        "Feedback": "Need Info",
    }
    return mapping.get(redmine_status)


# --- Sheet Row Conversion ---


def bug_row_to_dict(row: List[str]) -> Dict[str, str]:
    """Convert a bug sheet row (list) to a dict using lowercase keys."""
    result = {}
    for i, key in enumerate(BUGS_KEYS):
        result[key] = row[i] if i < len(row) else ""
    return result


def dict_to_bug_row(data: Dict[str, str]) -> List[str]:
    """Convert a bug dict to a sheet row list using lowercase keys."""
    return [data.get(key, "") for key in BUGS_KEYS]


def test_case_row_to_dict(row: List[str]) -> Dict[str, str]:
    """Convert a test case sheet row (list) to a dict using lowercase keys."""
    result = {}
    for i, key in enumerate(TESTCASES_KEYS):
        result[key] = row[i] if i < len(row) else ""
    return result


def dict_to_test_case_row(data: Dict[str, str]) -> List[str]:
    """Convert a test case dict to a sheet row list using lowercase keys."""
    return [data.get(key, "") for key in TESTCASES_KEYS]
