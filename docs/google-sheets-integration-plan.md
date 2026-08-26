# Plan: Google Sheets + Redmine Test Management Integration

## Overview

Tich hop Google Sheets API vao `redmine-mcp-server` de xay dung test management pipeline:

```
User Story/Breakdown
        ↓
   AI tao Test Cases (definition + execution tracking)
        ↓
  Tester + AI refine (markdown/JSON)
        ↓
  AI tao spreadsheet + 2 sheets co headers san
  Push test cases → Sheet "TestCases"
        ↓
  Tester dung TestCases de test
        ↓
  Neu bug ↓
  Tester tu nhap bug vao Sheet "Bugs" (headers da co san)
  HOAC yeu cau AI dien noi dung bug giup
        ↓
  Tester yeu cau AI tao Redmine issues + assign dev
        ↓
  Dev fix → AI sync status ve Sheet
        ↓
  Tester retest → Closed / Reopen / Reject
```

**Phan tach ro rang:**
- **TestCases**: Library test cases + execution tracking (result + date)
- **Bugs**: Work tracking — bug reports + Redmine sync + status updates
- **AI tao san headers**: Khi push test cases, AI cung tao Sheet "Bugs" voi headers san sang de tester nhap lieu

---

## Bug Status Flow

```
New (tester vua phat hien, chua tao issue)
  ↓  [AI tao Redmine issue]
Open (da co issue tren Redmine, dev chua pickup)
  │
  ├── In Progress (dev pickup, dang fix)
  │     │
  │     ├── Done (dev fix xong, done_ratio=100%)
  │     │     │
  │     │     ├── Closed (tester retest OK)
  │     │     ├── Reopen (tester retest fail → quay lai In Progress)
  │     │     └── Reject (dev reject cuoi cung)
  │     │
  │     ├── Reject (dev reject sau khi investigate)
  │     ├── Deferred (dev hoãn sang sprint sau)
  │     └── Need Info (dev can them info tu tester)
  │
  ├── Reject (dev reject ngay lap tuc)
  ├── Deferred (dev/PM hoãn ngay)
  ├── Need Info (dev can them info ngay)
  └── Duplicate (bug trung voi issue da co)
```

### Status transitions hop le

| Tu | Den | Dieu kien |
|---|---|---|
| `New` | `Open` | AI tao Redmine issue thanh cong |
| `Open` | `In Progress` | Dev pickup (sync tu Redmine) |
| `Open` | `Reject` | Dev reject ngay |
| `Open` | `Deferred` | Dev/PM hoan |
| `Open` | `Need Info` | Dev can them info |
| `Open` | `Duplicate` | Bug trung voi issue da co |
| `In Progress` | `Done` | Dev fix xong (done_ratio=100%) |
| `In Progress` | `Reject` | Dev reject sau khi investigate |
| `In Progress` | `Deferred` | Dev hoan giua chung |
| `In Progress` | `Need Info` | Dev can them info |
| `Done` | `Closed` | Tester retest OK |
| `Done` | `Reopen` | Tester retest fail |
| `Done` | `Reject` | Dev reject cuoi cung |
| `Reopen` | `In Progress` | Dev fix lai |
| `Need Info` | `Open` | Tester cung cap du info |
| `Deferred` | `Open` | Sprint sau pickup lai |
| `Duplicate` | *(end)* | Khong chuyen them |
| `Closed` | *(end)* | Khong chuyen them |
| `Reject` | *(end)* | Khong chuyen them |

### Mo ta tung status

| Status | Ai set? | Khi nao |
|---|---|---|
| `New` | Tester/AI | Vua phat hien bug, chua tao issue Redmine |
| `Open` | AI (auto) | Da tao Redmine issue thanh cong |
| `In Progress` | AI (sync tu Redmine) | Dev da chuyen status tren Redmine |
| `Done` | AI (sync tu Redmine) | Dev danh dau done_ratio=100%, san sang retest |
| `Reopen` | Tester/AI | Retest fail → cap nhat status tren Redmine |
| `Closed` | Tester/AI | Retest OK → xac nhan fix thanh cong |
| `Reject` | AI (sync tu Redmine) | Dev cho rang bug ngoai scope, duplicate, khong phai bug |
| `Deferred` | AI (sync tu Redmine) | Dev/PM quyet dinh hoan sang sprint sau |
| `Need Info` | AI (sync tu Redmine) | Dev can them info tu tester (khong reproduce duoc) |
| `Duplicate` | AI (sync tu Redmine) | Bug trung voi issue da co |

---

## Google Sheets Structure

### Sheet 1: TestCases — Test Case Definition + Execution Tracking

| Cot | Field | Type | Mo ta |
|---|---|---|---|
| A | test_case_id | string | ID tu dong (TC-001, TC-002...) |
| B | module | string | Module/Feature |
| C | title | string | Tieu de test case |
| D | precondition | string | Dieu kien tien quyet |
| E | steps | string | Cac buoc thuc hien (moi buoc 1 dong) |
| F | expected_result | string | Ket qua mong doi |
| G | tester | string | Nguoi duoc giao test |
| H | created_date | string | Ngay tao test case (YYYY-MM-DD) |
| I | last_test_result | string | Pass / Fail / Not Tested |
| J | last_test_date | string | Ngay test gan nhat (YYYY-MM-DD) |

### Sheet 2: Bugs — Work Tracking

| Cot | Field | Type | Mo ta |
|---|---|---|---|
| A | bug_id | string | ID tu dong (BUG-001...) |
| B | test_case_id | string | Link ve test case tuong ung |
| C | title | string | Tieu de bug |
| D | description | string | Mo ta bug (steps to reproduce, actual, expected) |
| E | priority | string | High / Medium / Low |
| F | status | string | New / Open / In Progress / Done / Reopen / Closed / Reject / Deferred / Need Info / Duplicate |
| G | assigned_to | string | Ten dev duoc assign |
| H | redmine_issue_id | string | Redmine issue ID (1 ID duy nhat, luon giu nguyen) |
| I | redmine_status | string | Trang thai tren Redmine (sync tu Redmine) |
| J | reporter | string | Nguoi bao bug |
| K | report_date | string | Ngay bao bug (YYYY-MM-DD) |
| L | reject_reason | string | Ly do dev reject (lay tu Redmine notes) |
| M | duplicate_of | string | Bug ID goc neu status = Duplicate |

### redmine_issue_id — luon 1 ID duy nhat

```
Luon la: "1234"  (issue goc, khong bao gio thay doi)
Reopen → cap nhat status tren Redmine, KHONG tao subtask
```

---

## Files

### Files moi

| File | Mo ta |
|---|---|
| src/redmine_mcp_server/google_sheets_client.py | Client factory: tao Sheets service tu Service Account JSON |
| src/redmine_mcp_server/handler_impl/tools/google_sheets.py | Impl functions cho Google Sheets operations |
| src/redmine_mcp_server/serializers/google_sheets.py | Sheet data serialization (validate, transform) |
| tests/test_google_sheets_tools.py | Unit tests |

### Files sua doi

| File | Thay doi |
|---|---|
| pyproject.toml | Them dependencies |
| src/redmine_mcp_server/redmine_handler.py | Import + register MCP tools |
| src/redmine_mcp_server/handler_impl/tools/__init__.py | Export impl functions |
| .env.example | Them env vars |
| .env.docker | Them env vars |
| docker-compose.yml | Mount service account credentials |
| .gitignore | Them credentials/ folder |

---

## Environment Variables

```env
# Google Sheets Configuration
GOOGLE_SHEETS_CREDENTIALS_FILE=/app/credentials/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id_here
```

---

## MCP Tools (8 tools)

### Tool 1: read_google_sheet

Doc data tu 1 range tren Google Sheets.

```python
@mcp.tool()
async def read_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    range: Annotated[str, Field(description="Range to read, e.g. 'TestCases!A1:J100'")],
) -> Dict[str, Any]:
```

Return:
```json
{
  "headers": ["test_case_id", "module", "title", "precondition", "steps", "expected_result", "tester", "created_date", "last_test_result", "last_test_date"],
  "rows": [["TC-001", "Login", "Valid login", "User has account", "1. Go to login\n2. Enter creds", "Redirect to dashboard", "tester1", "2025-08-26", "Pass", "2025-08-27"]],
  "total_rows": 15
}
```

---

### Tool 2: write_google_sheet

Ghi data vao range cu the (overwrite).

```python
@mcp.tool()
async def write_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    range: Annotated[str, Field(description="Range to write, e.g. 'TestCases!A1:J16'")],
    values: Annotated[List[List[str]], Field(description="2D array of values to write")],
) -> Dict[str, Any]:
```

Return:
```json
{
  "updated_cells": 160,
  "updated_rows": 16,
  "range": "TestCases!A1:J16"
}
```

---

### Tool 3: append_google_sheet

Them rows moi vao cuoi sheet (khong overwrite).

```python
@mcp.tool()
async def append_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Sheet name to append to")],
    values: Annotated[List[List[str]], Field(description="2D array of rows to append")],
) -> Dict[str, Any]:
```

Return:
```json
{
  "updated_rows": 5,
  "updated_cells": 65,
  "table_range": "Bugs!A12:M16"
}
```

---

### Tool 4: get_sheet_metadata

Lay thong tin ve cac sheet trong spreadsheet.

```python
@mcp.tool()
async def get_sheet_metadata(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
) -> Dict[str, Any]:
```

Return:
```json
{
  "spreadsheet_title": "QA Test Management",
  "sheets": [
    {
      "name": "TestCases",
      "sheet_id": 0,
      "headers": ["test_case_id", "module", "title", "precondition", "steps", "expected_result", "tester", "created_date", "last_test_result", "last_test_date"],
      "row_count": 20
    },
    {
      "name": "Bugs",
      "sheet_id": 1,
      "headers": ["bug_id", "test_case_id", "title", "description", "priority", "status", "assigned_to", "redmine_issue_id", "redmine_status", "reporter", "report_date", "reject_reason", "duplicate_of"],
      "row_count": 8
    }
  ]
}
```

---

### Tool 5: create_test_cases_on_sheet

Parse test cases tu markdown/JSON → push len Google Sheets. Tu dong tao Sheet "Bugs" voi headers san sang neu chua co.

```python
@mcp.tool()
async def create_test_cases_on_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Target sheet name, e.g. 'TestCases'")],
    test_cases: Annotated[List[Dict[str, str]], Field(description="List of test case dicts with keys: title, module, precondition, steps, expected_result, tester")],
    clear_existing: Annotated[bool, Field(description="Clear existing data before writing (keep headers)")] = False,
) -> Dict[str, Any]:
```

Flow:
1. Validate input test cases
2. Generate test_case_id tu dong (TC-001, TC-002...)
3. Set created_date = today, last_test_result = "Not Tested"
4. Kiem tra Sheet "Bugs" co ton tai chua → neu chua tao moi voi headers
5. Neu clear_existing=True → xoa data tu row 2 tro di
6. Append headers (neu sheet trong) + rows vao TestCases
7. Return summary

TestCases headers khi tao moi:
```
test_case_id | module | title | precondition | steps | expected_result | tester | created_date | last_test_result | last_test_date
```

Bugs headers khi tao moi:
```
bug_id | test_case_id | title | description | priority | status | assigned_to | redmine_issue_id | redmine_status | reporter | report_date | reject_reason | duplicate_of
```

Return:
```json
{
  "created": 15,
  "sheet_name": "TestCases",
  "first_id": "TC-001",
  "last_id": "TC-015",
  "range": "TestCases!A1:J16",
  "bugs_sheet_ready": true,
  "bugs_sheet_name": "Bugs"
}
```

---

### Tool 6: create_redmine_issues_from_bugs

Doc bug rows tu Sheet → tao Redmine issues → ghi issue ID nguoc lai.

```python
@mcp.tool()
async def create_redmine_issues_from_bugs(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Bug sheet name, e.g. 'Bugs'")],
    project_id: Annotated[int, Field(description="Redmine project ID")],
    tracker_id: Annotated[int, Field(description="Redmine tracker ID (1=Bug, 2=Feature, 3=Task)")],
    assigned_to_id: Annotated[Optional[int], Field(description="Default assignee user ID on Redmine")] = None,
    bug_row_range: Annotated[Optional[str], Field(description="Specific range, e.g. 'A2:M50'. None = all rows with status 'New'")] = None,
) -> Dict[str, Any]:
```

Flow:
1. Doc bug rows tu Sheet (filter: status = "New" va redmine_issue_id trong)
2. Validate status transitions: chi cho phep New → Open
3. Map fields: title → subject, description → description, priority → priority_id, assigned_to → assigned_to_id
4. Goi create_redmine_issue (su dung existing tool)
5. Ghi redmine_issue_id (column H) + update status (column F) → "Open"
6. Return summary

Return:
```json
{
  "created": 5,
  "failed": 0,
  "issues": [
    {"bug_id": "BUG-001", "redmine_issue_id": 1234, "title": "Login fails with special chars"},
    {"bug_id": "BUG-002", "redmine_issue_id": 1235, "title": "Dashboard timeout on large dataset"}
  ],
  "errors": []
}
```

---

### Tool 7: sync_redmine_status_to_sheet

Doc issue IDs tu Sheet "Bugs" → check Redmine → update Sheet. Detect reject/deferred/need_info/duplicate o moi giai doan.

```python
@mcp.tool()
async def sync_redmine_status_to_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    bug_sheet: Annotated[str, Field(description="Bug sheet name")] = "Bugs",
    test_case_sheet: Annotated[str, Field(description="Test case sheet name")] = "TestCases",
) -> Dict[str, Any]:
```

Flow:
1. Doc tat ca bug rows tu Bugs sheet
2. Chi process nhung row co redmine_issue_id (column H khong trong)
3. Voi moi issue ID: goi get_redmine_issue → lay status name + done_ratio + journals
4. Map Redmine status → Sheet status:

| Redmine status | Sheet status | Xu ly them |
|---|---|---|
| New | Open | — |
| In Progress | In Progress | — |
| Resolved (done_ratio=100%) | Done | — |
| Closed | Closed | Cap nhat TestCases: last_test_result = "Pass" |
| Rejected | Reject | Lay reject reason tu notes → column L |
| Rejected (contains "duplicate") | Duplicate | Parse issue ID tuong ung → column M |
| Deferred | Deferred | — |
| Need Info / Feedback | Need Info | — |

5. Validate status transitions hop le truoc khi cap nhat
6. Neu status chuyen thanh "Closed" → cap nhat TestCases: last_test_result = "Pass", last_test_date = today
7. Return summary

Return:
```json
{
  "checked": 20,
  "updated": 5,
  "summary": {
    "open": 3,
    "in_progress": 8,
    "done": 5,
    "closed": 3,
    "rejected": 1
  },
  "details": [
    {"redmine_issue_id": 1234, "old_status": "New", "new_status": "In Progress"},
    {"redmine_issue_id": 1235, "old_status": "In Progress", "new_status": "Done"}
  ]
}
```

---

### Tool 8: reopen_bug

Cap nhat status tren Redmine khi tester retest fail. Giu nguyen issue ID, KHONG tao subtask.

```python
@mcp.tool()
async def reopen_bug(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Bug sheet name, e.g. 'Bugs'")],
    bug_id: Annotated[str, Field(description="Bug ID to reopen, e.g. 'BUG-001'")],
    reopen_note: Annotated[str, Field(description="Note describing why the bug is reopened (what still fails)")],
    project_id: Annotated[int, Field(description="Redmine project ID")],
) -> Dict[str, Any]:
```

Flow:
1. Doc bug row tu Sheet theo bug_id
2. Validate: chi cho phep Reopen tu trang thai "Done"
3. Lay redmine_issue_id tu column H (1 ID duy nhat)
4. Cap nhat status tren Redmine: update status → "New" (hoac status ma Redmine su dung cho "chua fix")
5. Them reopen_note vao Redmine journal/notes
6. Update column F → "Reopen"
7. Update column I → "New" (trang thai tren Redmine)
8. Validate: sau Reopen, trang thai tiep theo chi co the la "In Progress"
9. Return summary

Return:
```json
{
  "success": true,
  "redmine_issue_id": 1234,
  "title": "Login fails with special chars",
  "reopen_note": "Still fails when password contains special chars: @, #, $"
}
```

---

## Dependencies

```toml
# pyproject.toml
dependencies = [
    # ...existing...
    "google-api-python-client>=2.100.0",
    "google-auth>=2.23.0",
    "google-auth-httplib2>=0.1.0",
]
```

---

## Architecture

```
src/redmine_mcp_server/
├── google_sheets_client.py              ← NEW
│   class GoogleSheetsManager:
│     __init__(credentials_file: str)
│     get_service() → googleapiclient.discovery.Resource
│     - Lazy singleton per credentials file
│     - Auto-reconnect on auth errors
│
├── handler_impl/tools/
│   ├── google_sheets.py                 ← NEW
│   │   read_google_sheet_impl()
│   │   write_google_sheet_impl()
│   │   append_google_sheet_impl()
│   │   get_sheet_metadata_impl()
│   │   create_test_cases_on_sheet_impl()
│   │   create_redmine_issues_from_bugs_impl()
│   │   sync_redmine_status_to_sheet_impl()
│   │   reopen_bug_impl()
│   │
│   └── __init__.py                      ← MODIFY: add exports
│
├── serializers/
│   └── google_sheets.py                 ← NEW
│     _validate_test_case(row) → dict
│     _validate_bug(row) → dict
│     _build_test_case_id(existing_ids) → str
│     _build_bug_id(existing_ids) → str
│     _map_priority_to_redmine(priority) → int
│     _is_valid_status_transition(current, target) → bool
│     _parse_redmine_issue_id(id_string) → str  (luon 1 ID)
│
├── redmine_handler.py                   ← MODIFY: register tools
│   @mcp.tool() read_google_sheet(...)
│   @mcp.tool() write_google_sheet(...)
│   @mcp.tool() append_google_sheet(...)
│   @mcp.tool() get_sheet_metadata(...)
│   @mcp.tool() create_test_cases_on_sheet(...)
│   @mcp.tool() create_redmine_issues_from_bugs(...)
│   @mcp.tool() sync_redmine_status_to_sheet(...)
│   @mcp.tool() reopen_bug(...)
```

---

## Docker

```yaml
# docker-compose.yml
services:
  redmine-mcp-server:
    # ...existing...
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
      - ./credentials:/app/credentials:ro    # ← NEW
    env_file:
      - .env.docker
```

```env
# .env.docker
# ...existing...
GOOGLE_SHEETS_CREDENTIALS_FILE=/app/credentials/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_id_here
```

---

## Error Handling

Follow existing pattern tu `handler_impl/errors.py`:

```python
# google_sheets.py
from googleapiclient.errors import HttpError

async def read_google_sheet_impl(...):
    try:
        service = google_sheets_manager.get_service()
        result = service.spreadsheets().values().get(...).execute()
        return {"headers": ..., "rows": ...}
    except FileNotFoundError as e:
        return {"error": str(e)}
    except ImportError as e:
        return {"error": str(e)}
    except HttpError as e:
        if e.resp.status == 404:
            return {"error": f"Spreadsheet not found: {spreadsheet_id}"}
        elif e.resp.status == 403:
            return {"error": "Access denied. Check service account permissions."}
        else:
            return {"error": f"Google Sheets API error: {e}"}
    except Exception as e:
        return {"error": f"Unexpected error reading sheet: {e}"}
```

---

## Skills (tao sau khi tools xong)

| Skill | Trigger Phrase | Mo ta |
|---|---|---|
| testcase-generation | "Tao test case tu user story nay..." | AI doc file user story → tao test cases → push Sheet |
| bug-reporting | "Ghi bug nay vao sheet..." | AI tao bug row tren Sheet tu mo ta |
| bug-to-redmine | "Tao issue cho cac bug..." | Doc Sheet → tao Redmine issues + assign |
| status-sync | "Check dev fix chua..." | Doc Sheet → check Redmine → update Sheet |
| reopen-bug | "Reopen bug nay..." | Cap nhat status tren Redmine + update Sheet |

---

## Implementation Order

| Step | Task | Est. |
|---|---|---|
| 1 | google_sheets_client.py — Client factory + env config | 30 min |
| 2 | serializers/google_sheets.py — Validation + transform + status transitions | 45 min |
| 3 | handler_impl/tools/google_sheets.py — 4 CRUD tools co ban | 1h |
| 4 | Register tools trong redmine_handler.py | 15 min |
| 5 | Tool 5: create_test_cases_on_sheet (2 sheets headers) | 45 min |
| 6 | Tool 6: create_redmine_issues_from_bugs | 1h |
| 7 | Tool 7: sync_redmine_status_to_sheet (detect reject/deferred/need_info/duplicate) | 1.5h |
| 8 | Tool 8: reopen_bug (giu nguyen issue ID) | 45 min |
| 9 | Unit tests | 1h |
| 10 | Docker + env config | 15 min |
| 11 | Skills definitions | 1h |
| 12 | Docs update | 30 min |

---

## Da quyet dinh

- [x] 2 sheets (TestCases + Bugs) — khong tach 3 sheets
- [x] TestCases = definition + execution tracking (last_test_result + last_test_date)
- [x] Bugs = work tracking + Redmine sync
- [x] Sync chi tu Bugs sheet (khong sync tu TestCases)
- [x] Chi giu priority (bo severity) — tester tu set High/Medium/Low
- [x] 10 status values: New, Open, In Progress, Done, Reopen, Closed, Reject, Deferred, Need Info, Duplicate
- [x] Reject/duplicate/deferred/need_info detect o moi giai doan (khong chi sau Done)
- [x] Reopen = giu nguyen issue ID, KHONG tao subtask
- [x] Luon 1 ID duy nhat trong redmine_issue_id column
- [x] Status transitions validate hop le
- [x] Duplicate: them column duplicate_of, parse reject reason chua "duplicate"
- [x] Need Info: dev can them info tu tester
- [x] Deferred: dev/PM hoan sang sprint sau
- [x] TestCases cap nhat last_test_result = "Pass" khi bug linked Closed
- [x] AI tao san Bugs sheet headers khi push test cases
- [x] Priority mapping: de xay sau (khong lien quan den issue hien tai)

## Con open questions

- **Redmine status names**: Can biet exact status names tren Redmine instance de map dung
- **Assignee mapping**: assigned_to trong Sheet la ten hay ID? Can resolve ten → user ID tren Redmine
- **Read-only mode**: Google Sheets tools co can bi anh huong boi REDMINE_MCP_READ_ONLY khong?
- **Redmine status cho Reopen**: Khi reopen, status tren Redmine nen dat la "New" hay "Reopened"? Tuy Redmine config
