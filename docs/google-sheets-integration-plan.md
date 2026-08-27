# Kế hoạch: Tích hợp Google Sheets + Quản lý kiểm thử Redmine

## Tổng quan

Tích hợp Google Sheets API vào `redmine-mcp-server` để xây dựng quy trình quản lý kiểm thử:

```
User Story / Phân tách công việc
        ↓
   AI tạo Test Cases (định nghĩa + theo dõi thực thi)
        ↓
  Tester + AI chỉnh sửa (markdown/JSON)
        ↓
  AI tạo spreadsheet + 2 sheet có headers sẵn
  Đẩy test cases → Sheet "TestCases"
        ↓
  Tester dùng TestCases để test
        ↓
  Nếu bug ↓
  Tester tự nhập bug vào Sheet "Bugs" (headers đã có sẵn)
  HOẶC yêu cầu AI điền nội dung bug giúp
        ↓
  Tester yêu cầu AI tạo Redmine issues + assign dev
        ↓
  Dev fix → AI sync trạng thái về Sheet
        ↓
  Tester retest → Closed / Reopen / Reject
```

**Phân tách rõ ràng:**
- **TestCases**: Thư viện test cases + theo dõi thực thi (kết quả + ngày)
- **Bugs**: Theo dõi công việc — báo cáo lỗi + đồng bộ Redmine + cập nhật trạng thái
- **AI tạo sẵn headers**: Khi đẩy test cases, AI cũng tạo Sheet "Bugs" với headers sẵn sàng để tester nhập liệu

---

## Luồng trạng thái lỗi

```
New (tester vừa phát hiện, chưa tạo issue)
  ↓  [AI tạo Redmine issue]
Open (đã có issue trên Redmine, dev chưa pickup)
  │
  ├── In Progress (dev pickup, đang fix)
  │     │
  │     ├── Done (dev fix xong, done_ratio=100%)
  │     │     │
  │     │     ├── Closed (tester retest OK)
  │     │     ├── Reopen (tester retest fail → quay lại In Progress)
  │     │     └── Reject (dev reject cuối cùng)
  │     │
  │     ├── Reject (dev reject sau khi investigate)
  │     ├── Deferred (dev hoãn sang sprint sau)
  │     └── Need Info (dev cần thêm info từ tester)
  │
  ├── Reject (dev reject ngay lập tức)
  ├── Deferred (dev/PM hoãn ngay)
  ├── Need Info (dev cần thêm info ngay)
  └── Duplicate (bug trùng với issue đã có)
```

### Các chuyển đổi trạng thái hợp lệ

| Từ | Đến | Điều kiện |
|---|---|---|
| `New` | `Open` | AI tạo Redmine issue thành công |
| `Open` | `In Progress` | Dev pickup (đồng bộ từ Redmine) |
| `Open` | `Reject` | Dev reject ngay |
| `Open` | `Deferred` | Dev/PM hoãn |
| `Open` | `Need Info` | Dev cần thêm info |
| `Open` | `Duplicate` | Bug trùng với issue đã có |
| `In Progress` | `Done` | Dev fix xong (done_ratio=100%) |
| `In Progress` | `Reject` | Dev reject sau khi investigate |
| `In Progress` | `Deferred` | Dev hoãn giữa chừng |
| `In Progress` | `Need Info` | Dev cần thêm info |
| `Done` | `Closed` | Tester retest OK |
| `Done` | `Reopen` | Tester retest fail |
| `Done` | `Reject` | Dev reject cuối cùng |
| `Reopen` | `In Progress` | Dev fix lại |
| `Need Info` | `Open` | Tester cung cấp đủ info |
| `Deferred` | `Open` | Sprint sau pickup lại |
| `Duplicate` | *(kết thúc)* | Không chuyển thêm |
| `Closed` | *(kết thúc)* | Không chuyển thêm |
| `Reject` | *(kết thúc)* | Không chuyển thêm |

### Mô tả từng trạng thái

| Trạng thái | Ai set? | Khi nào |
|---|---|---|
| `New` | Tester/AI | Vừa phát hiện bug, chưa tạo issue Redmine |
| `Open` | AI (tự động) | Đã tạo Redmine issue thành công |
| `In Progress` | AI (đồng bộ từ Redmine) | Dev đã chuyển trạng thái trên Redmine |
| `Done` | AI (đồng bộ từ Redmine) | Dev đánh dấu done_ratio=100%, sẵn sàng retest |
| `Reopen` | Tester/AI | Retest fail → cập nhật trạng thái trên Redmine |
| `Closed` | Tester/AI | Retest OK → xác nhận fix thành công |
| `Reject` | AI (đồng bộ từ Redmine) | Dev cho rằng bug ngoài scope, trùng, không phải bug |
| `Deferred` | AI (đồng bộ từ Redmine) | Dev/PM quyết định hoãn sang sprint sau |
| `Need Info` | AI (đồng bộ từ Redmine) | Dev cần thêm info từ tester (không reproduce được) |
| `Duplicate` | AI (đồng bộ từ Redmine) | Bug trùng với issue đã có |

---

## Cấu trúc Google Sheets

### Sheet 1: TestCases — Định nghĩa Test Case + Theo dõi thực thi

| Cột | Trường | Kiểu | Mô tả |
|---|---|---|---|
| A | test_case_id | string | ID tự động (TC-001, TC-002...) |
| B | module | string | Module/Chức năng |
| C | title | string | Tiêu đề test case |
| D | precondition | string | Điều kiện tiên quyết |
| E | steps | string | Các bước thực hiện (mỗi bước 1 dòng) |
| F | expected_result | string | Kết quả mong đợi |
| G | tester | string | Người được giao test |
| H | created_date | string | Ngày tạo test case (YYYY-MM-DD) |
| I | last_test_result | string | Pass / Fail / Not Tested |
| J | last_test_date | string | Ngày test gần nhất (YYYY-MM-DD) |

### Sheet 2: Bugs — Theo dõi công việc

| Cột | Trường | Kiểu | Mô tả |
|---|---|---|---|
| A | bug_id | string | ID tự động (BUG-001...) |
| B | test_case_id | string | Liên kết về test case tương ứng |
| C | title | string | Tiêu đề bug |
| D | description | string | Mô tả bug (cách tái hiện, thực tế, mong đợi) |
| E | priority | string | High / Medium / Low |
| F | status | string | New / Open / In Progress / Done / Reopen / Closed / Reject / Deferred / Need Info / Duplicate |
| G | assigned_to | string | Tên dev được assign |
| H | redmine_issue_id | string | Redmine issue ID (1 ID duy nhất, luôn giữ nguyên) |
| I | redmine_status | string | Trạng thái trên Redmine (đồng bộ từ Redmine) |
| J | reporter | string | Người báo bug |
| K | report_date | string | Ngày báo bug (YYYY-MM-DD) |
| L | reject_reason | string | Lý do dev reject (lấy từ Redmine notes) |
| M | duplicate_of | string | Bug ID gốc nếu status = Duplicate |

### redmine_issue_id — Luôn 1 ID duy nhất

```
Luôn là: "1234"  (issue gốc, không bao giờ thay đổi)
Reopen → cập nhật trạng thái trên Redmine, KHÔNG tạo subtask
```

---

## Các file

### Files mới

| File | Mô tả |
|---|---|
| src/redmine_mcp_server/google_sheets_client.py | Factory client: tạo Sheets service từ Service Account JSON |
| src/redmine_mcp_server/handler_impl/tools/google_sheets.py | Hàm triển khai cho các thao tác Google Sheets |
| src/redmine_mcp_server/serializers/google_sheets.py | serialize dữ liệu Sheet (validate, transform) |
| tests/test_google_sheets_tools.py | Unit tests |

### Files sửa đổi

| File | Thay đổi |
|---|---|
| pyproject.toml | Thêm dependencies |
| src/redmine_mcp_server/redmine_handler.py | Import + đăng ký MCP tools |
| src/redmine_mcp_server/handler_impl/tools/__init__.py | Export impl functions |
| .env.example | Thêm env vars |
| .env.docker | Thêm env vars |
| docker-compose.yml | Mount service account credentials |
| .gitignore | Thêm thư mục credentials/ |

---

## Biến môi trường

```env
# Cấu hình Google Sheets
GOOGLE_SHEETS_CREDENTIALS_FILE=/app/credentials/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_spreadsheet_id_here
```

---

## Công cụ MCP (8 tools)

### Tool 1: read_google_sheet

Đọc dữ liệu từ 1 range trên Google Sheets.

```python
@mcp.tool()
async def read_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    range: Annotated[str, Field(description="Range cần đọc, ví dụ 'TestCases!A1:J100'")],
) -> Dict[str, Any]:
```

Kết quả:
```json
{
  "headers": ["test_case_id", "module", "title", "precondition", "steps", "expected_result", "tester", "created_date", "last_test_result", "last_test_date"],
  "rows": [["TC-001", "Login", "Đăng nhập hợp lệ", "User có tài khoản", "1. Vào trang login\n2. Nhập thông tin", "Chuyển đến trang chủ", "tester1", "2025-08-26", "Pass", "2025-08-27"]],
  "total_rows": 15
}
```

---

### Tool 2: write_google_sheet

Ghi dữ liệu vào range cụ thể (ghi đè).

```python
@mcp.tool()
async def write_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    range: Annotated[str, Field(description="Range cần ghi, ví dụ 'TestCases!A1:J16'")],
    values: Annotated[List[List[str]], Field(description="Mảng 2 chiều chứa dữ liệu cần ghi")],
) -> Dict[str, Any]:
```

Kết quả:
```json
{
  "updated_cells": 160,
  "updated_rows": 16,
  "range": "TestCases!A1:J16"
}
```

---

### Tool 3: append_google_sheet

Thêm rows mới vào cuối sheet (không ghi đè).

```python
@mcp.tool()
async def append_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Tên sheet cần thêm dữ liệu")],
    values: Annotated[List[List[str]], Field(description="Mảng 2 chiều chứa các rows cần thêm")],
) -> Dict[str, Any]:
```

Kết quả:
```json
{
  "updated_rows": 5,
  "updated_cells": 65,
  "table_range": "Bugs!A12:M16"
}
```

---

### Tool 4: get_sheet_metadata

Lấy thông tin về các sheet trong spreadsheet.

```python
@mcp.tool()
async def get_sheet_metadata(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
) -> Dict[str, Any]:
```

Kết quả:
```json
{
  "spreadsheet_title": "Quản lý kiểm thử QA",
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

Phân tích test cases từ markdown/JSON → đẩy lên Google Sheets. Tự động tạo Sheet "Bugs" với headers sẵn sàng nếu chưa có.

```python
@mcp.tool()
async def create_test_cases_on_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Tên sheet đích, ví dụ 'TestCases'")],
    test_cases: Annotated[List[Dict[str, str]], Field(description="Danh sách test case dict với các khóa: title, module, precondition, steps, expected_result, tester")],
    clear_existing: Annotated[bool, Field(description="Xóa dữ liệu cũ trước khi ghi (giữ headers)")] = False,
) -> Dict[str, Any]:
```

Quy trình:
1. Validate dữ liệu đầu vào
2. Tạo test_case_id tự động (TC-001, TC-002...)
3. Đặt created_date = hôm nay, last_test_result = "Not Tested"
4. Kiểm tra Sheet "Bugs" đã tồn tại chưa → nếu chưa tạo mới với headers
5. Nếu clear_existing=True → xóa dữ liệu từ row 2 trở đi
6. Thêm headers (nếu sheet trống) + rows vào TestCases
7. Trả về tổng kết

Headers khi tạo mới TestCases:
```
test_case_id | module | title | precondition | steps | expected_result | tester | created_date | last_test_result | last_test_date
```

Headers khi tạo mới Bugs:
```
bug_id | test_case_id | title | description | priority | status | assigned_to | redmine_issue_id | redmine_status | reporter | report_date | reject_reason | duplicate_of
```

Kết quả:
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

Đọc bug rows từ Sheet → tạo Redmine issues → ghi issue ID ngược lại.

```python
@mcp.tool()
async def create_redmine_issues_from_bugs(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Tên sheet bug, ví dụ 'Bugs'")],
    project_id: Annotated[int, Field(description="ID dự án Redmine")],
    tracker_id: Annotated[int, Field(description="ID tracker Redmine (1=Bug, 2=Feature, 3=Task)")],
    assigned_to_id: Annotated[Optional[int], Field(description="ID user được assign mặc định trên Redmine")] = None,
    bug_row_range: Annotated[Optional[str], Field(description="Range cụ thể, ví dụ 'A2:M50'. None = tất cả rows có trạng thái 'New'")] = None,
) -> Dict[str, Any]:
```

Quy trình:
1. Đọc bug rows từ Sheet (lọc: status = "New" và redmine_issue_id trống)
2. Validate chuyển đổi trạng thái: chỉ cho phép New → Open
3. Ánh xạ trường: title → subject, description → description, priority → priority_id, assigned_to → assigned_to_id
4. Gọi create_redmine_issue (sử dụng tool hiện có)
5. Ghi redmine_issue_id (cột H) + cập nhật status (cột F) → "Open"
6. Trả về tổng kết

Kết quả:
```json
{
  "created": 5,
  "failed": 0,
  "issues": [
    {"bug_id": "BUG-001", "redmine_issue_id": 1234, "title": "Đăng nhập lỗi khi nhập ký tự đặc biệt"},
    {"bug_id": "BUG-002", "redmine_issue_id": 1235, "title": "Dashboard timeout khi dữ liệu lớn"}
  ],
  "errors": []
}
```

---

### Tool 7: sync_redmine_status_to_sheet

Đọc issue IDs từ Sheet "Bugs" → kiểm tra Redmine → cập nhật Sheet. Phát hiện reject/deferred/need_info/duplicate ở mọi giai đoạn.

```python
@mcp.tool()
async def sync_redmine_status_to_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    bug_sheet: Annotated[str, Field(description="Tên sheet bug")] = "Bugs",
    test_case_sheet: Annotated[str, Field(description="Tên sheet test case")] = "TestCases",
) -> Dict[str, Any]:
```

Quy trình:
1. Đọc tất cả bug rows từ Bugs sheet
2. Chỉ xử lý những row có redmine_issue_id (cột H không trống)
3. Với mỗi issue ID: gọi get_redmine_issue → lấy status name + done_ratio + journals
4. Ánh xạ Redmine status → Sheet status:

| Redmine status | Sheet status | Xử lý thêm |
|---|---|---|
| New | Open | — |
| In Progress | In Progress | — |
| Resolved (done_ratio=100%) | Done | — |
| Closed | Closed | Cập nhật TestCases: last_test_result = "Pass" |
| Rejected | Reject | Lấy lý do reject từ notes → cột L |
| Rejected (chứa "duplicate") | Duplicate | Phân tích issue ID tương ứng → cột M |
| Deferred | Deferred | — |
| Need Info / Feedback | Need Info | — |

5. Validate chuyển đổi trạng thái hợp lệ trước khi cập nhật
6. Nếu trạng thái chuyển thành "Closed" → cập nhật TestCases: last_test_result = "Pass", last_test_date = hôm nay
7. Trả về tổng kết

Kết quả:
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

Cập nhật trạng thái trên Redmine khi tester retest fail. Giữ nguyên issue ID, KHÔNG tạo subtask.

```python
@mcp.tool()
async def reopen_bug(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Tên sheet bug, ví dụ 'Bugs'")],
    bug_id: Annotated[str, Field(description="Bug ID cần reopen, ví dụ 'BUG-001'")],
    reopen_note: Annotated[str, Field(description="Ghi chú lý do reopen (phần nào vẫn còn lỗi)")],
    project_id: Annotated[int, Field(description="ID dự án Redmine")],
) -> Dict[str, Any]:
```

Quy trình:
1. Đọc bug row từ Sheet theo bug_id
2. Validate: chỉ cho phép Reopen từ trạng thái "Done"
3. Lấy redmine_issue_id từ cột H (1 ID duy nhất)
4. Cập nhật trạng thái trên Redmine: update status → "New" (hoặc trạng thái mà Redmine dùng cho "chưa fix")
5. Thêm reopen_note vào Redmine journal/notes
6. Cập nhật cột F → "Reopen"
7. Cập nhật cột I → "New" (trạng thái trên Redmine)
8. Validate: sau Reopen, trạng thái tiếp theo chỉ có thể là "In Progress"
9. Trả về tổng kết

Kết quả:
```json
{
  "success": true,
  "redmine_issue_id": 1234,
  "title": "Đăng nhập lỗi khi nhập ký tự đặc biệt",
  "reopen_note": "Vẫn lỗi khi mật khẩu chứa ký tự đặc biệt: @, #, $"
}
```

---

## Dependencies

```toml
# pyproject.toml
dependencies = [
    # ...hiện có...
    "google-api-python-client>=2.100.0",
    "google-auth>=2.23.0",
    "google-auth-httplib2>=0.1.0",
]
```

---

## Kiến trúc

```
src/redmine_mcp_server/
├── google_sheets_client.py              ← MỚI
│   class GoogleSheetsManager:
│     __init__(credentials_file: str)
│     get_service() → googleapiclient.discovery.Resource
│     - Singleton懒加载 theo credentials file
│     - Tự động kết nối lại khi lỗi xác thực
│
├── handler_impl/tools/
│   ├── google_sheets.py                 ← MỚI
│   │   read_google_sheet_impl()
│   │   write_google_sheet_impl()
│   │   append_google_sheet_impl()
│   │   get_sheet_metadata_impl()
│   │   create_test_cases_on_sheet_impl()
│   │   create_redmine_issues_from_bugs_impl()
│   │   sync_redmine_status_to_sheet_impl()
│   │   reopen_bug_impl()
│   │
│   └── __init__.py                      ← SỬA: thêm exports
│
├── serializers/
│   └── google_sheets.py                 ← MỚI
│     _validate_test_case(row) → dict
│     _validate_bug(row) → dict
│     _build_test_case_id(existing_ids) → str
│     _build_bug_id(existing_ids) → str
│     _map_priority_to_redmine(priority) → int
│     _is_valid_status_transition(current, target) → bool
│     _parse_redmine_issue_id(id_string) → str  (luôn 1 ID)
│
├── redmine_handler.py                   ← SỬA: đăng ký tools
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
    # ...hiện có...
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
      - ./credentials:/app/credentials:ro    # ← MỚI
    env_file:
      - .env.docker
```

```env
# .env.docker
# ...hiện có...
GOOGLE_SHEETS_CREDENTIALS_FILE=/app/credentials/service-account.json
GOOGLE_SHEETS_SPREADSHEET_ID=your_id_here
```

---

## Xử lý lỗi

Theo pattern hiện có từ `handler_impl/errors.py`:

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
            return {"error": f"Không tìm thấy spreadsheet: {spreadsheet_id}"}
        elif e.resp.status == 403:
            return {"error": "Truy cập bị từ chối. Kiểm tra quyền service account."}
        else:
            return {"error": f"Lỗi Google Sheets API: {e}"}
    except Exception as e:
        return {"error": f"Lỗi không mong đợi khi đọc sheet: {e}"}
```

---

## Kỹ năng (tạo sau khi tools xong)

| Kỹ năng | Câu kích hoạt | Mô tả |
|---|---|---|
| testcase-generation | "Tạo test case từ user story này..." | AI đọc file user story → tạo test cases → đẩy Sheet |
| bug-reporting | "Ghi bug này vào sheet..." | AI tạo bug row trên Sheet từ mô tả |
| bug-to-redmine | "Tạo issue cho các bug..." | Đọc Sheet → tạo Redmine issues + assign |
| status-sync | "Check dev fix chưa..." | Đọc Sheet → kiểm tra Redmine → cập nhật Sheet |
| reopen-bug | "Reopen bug này..." | Cập nhật trạng thái trên Redmine + cập nhật Sheet |

---

## Thứ tự triển khai

| Bước | Công việc | Ước tính |
|---|---|---|
| 1 | google_sheets_client.py — Factory client + env config | 30 phút |
| 2 | serializers/google_sheets.py — Validate + transform + trạng thái chuyển đổi | 45 phút |
| 3 | handler_impl/tools/google_sheets.py — 4 công cụ CRUD cơ bản | 1 giờ |
| 4 | Đăng ký tools trong redmine_handler.py | 15 phút |
| 5 | Tool 5: create_test_cases_on_sheet (2 sheet headers) | 45 phút |
| 6 | Tool 6: create_redmine_issues_from_bugs | 1 giờ |
| 7 | Tool 7: sync_redmine_status_to_sheet (phát hiện reject/deferred/need_info/duplicate) | 1.5 giờ |
| 8 | Tool 8: reopen_bug (giữ nguyên issue ID) | 45 phút |
| 9 | Unit tests | 1 giờ |
| 10 | Docker + env config | 15 phút |
| 11 | Định nghĩa kỹ năng | 1 giờ |
| 12 | Cập nhật tài liệu | 30 phút |

---

## Đã quyết định

- [x] 2 sheet (TestCases + Bugs) — không tách 3 sheet
- [x] TestCases = định nghĩa + theo dõi thực thi (last_test_result + last_test_date)
- [x] Bugs = theo dõi công việc + đồng bộ Redmine
- [x] Đồng bộ chỉ từ Bugs sheet (không đồng bộ từ TestCases)
- [x] Chỉ giữ priority (bỏ severity) — tester tự set High/Medium/Low
- [x] 10 giá trị trạng thái: New, Open, In Progress, Done, Reopen, Closed, Reject, Deferred, Need Info, Duplicate
- [x] Phát hiện reject/duplicate/deferred/need_info ở mọi giai đoạn (không chỉ sau Done)
- [x] Reopen = giữ nguyên issue ID, KHÔNG tạo subtask
- [x] Luôn 1 ID duy nhất trong cột redmine_issue_id
- [x] Validate chuyển đổi trạng thái hợp lệ
- [x] Duplicate: thêm cột duplicate_of, phân tích reject reason chứa "duplicate"
- [x] Need Info: dev cần thêm info từ tester
- [x] Deferred: dev/PM hoãn sang sprint sau
- [x] TestCases cập nhật last_test_result = "Pass" khi bug linked Closed
- [x] AI tạo sẵn Bugs sheet headers khi push test cases
- [x] Ánh xạ Priority: để xây sau (không liên quan đến issue hiện tại)

## Các câu hỏi còn mở

- **Tên trạng thái Redmine**: Cần biết tên chính xác các trạng thái trên Redmine instance để ánh xạ đúng
- **Ánh xạ assignee**: assigned_to trong Sheet là tên hay ID? Cần chuyển tên → user ID trên Redmine
- **Chế độ chỉ đọc**: Các công cụ Google Sheets có bị ảnh hưởng bởi REDMINE_MCP_READ_ONLY không?
- **Trạng thái Redmine cho Reopen**: Khi reopen, trạng thái trên Redmine nên đặt là "New" hay "Reopened"? Tùy cấu hình Redmine
