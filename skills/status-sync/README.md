# status-sync skill

A user-facing agent skill that synchronizes Redmine issue statuses back to the Google Sheet "Bugs", detecting reject/deferred/need_info/duplicate at every stage and updating the TestCases sheet when bugs are closed.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Clarify** — confirms spreadsheet ID and sheet names |
| 2 | **Read** — fetches all bug rows from "Bugs" sheet with redmine_issue_id |
| 3 | **Check Redmine** — for each issue: get status, done_ratio, journals |
| 4 | **Map status** — Redmine status → Sheet status (New→Open, Resolved→Done, Closed→Closed, Rejected→Reject, etc.) |
| 5 | **Detect special states** — reject reason, duplicate, deferred, need_info from journal notes |
| 6 | **Update sheet** — write new status, redmine_status, reject_reason, duplicate_of |
| 7 | **Update TestCases** — if bug closed → set last_test_result = "Pass", last_test_date = today |

---

## 2. Installation

### One-liner installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Manual copy

```bash
cp -r <path-to-this-repo>/skills/status-sync .agents/skills/
```

Then **restart your agent**.

### Prerequisites

- Redmine MCP server running (Google Sheets auth is handled server-side)
- Bugs sheet with rows that have redmine_issue_id populated

---

## 3. Usage

### Check và sync trạng thái

> "Check dev fix chưa..."
> "Sync trạng thái từ Redmine về sheet"
> "Update sheet status from Redmine"
> "Đồng bộ trạng thái Redmine"

### Câu hỏi skill sẽ hỏi

1. Spreadsheet ID nào?
2. Tên sheet Bugs? (mặc định: "Bugs")
3. Tên sheet TestCases? (mặc định: "TestCases")

### Kết quả

- Trạng thái trên Sheet được cập nhật theo Redmine
- Reject reason được parse từ journal notes
- Duplicate issues được detect và ghi vào cột duplicate_of
- TestCases sheet cập nhật "Pass" khi bug Closed
- Trả về tổng kết: checked, updated, summary by status

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| "No bugs with Redmine ID" | Kiểm tra bug-to-redmine skill đã tạo issues chưa |
| Status not updating | Kiểm tra status transitions có hợp lệ không |
| TestCases not updating | Chỉ bug linked test case và status "Closed" mới update TestCases |
| "Access denied" | Kiểm tra quyền Redmine API |

---

## 5. Keeping the skill up to date

```bash
git pull --rebase
# re-run installer
```

Restart agent after update.
