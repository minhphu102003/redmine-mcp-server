# reopen-bug skill

A user-facing agent skill that reopens a bug by updating its status on Redmine and the Google Sheet when retest fails, keeping the same issue ID (no subtask created).

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Clarify** — confirms bug ID, reopen reason, and spreadsheet |
| 2 | **Validate** — checks status transition Done → Reopen is valid |
| 3 | **Update Redmine** — sets status to "New" + adds reopen note to journal |
| 4 | **Update Sheet** — sets status → "Reopen", redmine_status → "New" |
| 5 | **Report** — returns success/failure with issue ID and note |

---

## 2. Installation

### One-liner installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Manual copy

```bash
cp -r <path-to-this-repo>/skills/reopen-bug .agents/skills/
```

Then **restart your agent**.

### Prerequisites

- Redmine MCP server running (Google Sheets auth is handled server-side)
- Bug must have status "Done" and a redmine_issue_id

---

## 3. Usage

### Reopen bug

> "Reopen bug này..."
> "Bug vẫn còn lỗi, reopen lại"
> "Retest fail, reopen bug BUG-001"
> "Mở lại bug"

### Câu hỏi skill sẽ hỏi

1. Bug ID nào cần reopen? (e.g. BUG-001)
2. Lý do reopen? (phần nào vẫn còn lỗi)
3. Spreadsheet ID nào?

### Kết quả

- Redmine issue status → "New" + reopen note added
- Sheet status → "Reopen"
- Sheet redmine_status → "New"
- Trả về success/failure với issue ID

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| "Cannot reopen from status X" | Bug phải có status "Done" trên sheet mới reopen được |
| "Bug has no Redmine issue ID" | Bug chưa được tạo Redmine issue, chạy bug-to-redmine trước |
| "Redmine issue not found" | Kiểm tra lại issue ID trên Redmine |
| Status transition invalid | Kiểm tra Redmine workflow cho phép New → In Progress |

---

## 5. Keeping the skill up to date

```bash
git pull --rebase
# re-run installer
```

Restart agent after update.
