# bug-to-redmine skill

A user-facing agent skill that reads bug rows from the Google Sheet "Bugs" with status "New", creates Redmine issues for each, and writes the Redmine issue IDs back to the sheet.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Clarify** — confirms spreadsheet, project ID, tracker, and assignee |
| 2 | **Read** — fetches bug rows from "Bugs" sheet where status = "New" and redmine_issue_id is empty |
| 3 | **Validate** — checks status transition New → Open is valid |
| 4 | **Create** — calls Redmine API to create issues (Bug tracker by default) |
| 5 | **Write back** — updates redmine_issue_id (column H) and status → "Open" (column F) on the sheet |

---

## 2. Installation

### One-liner installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Manual copy

```bash
cp -r <path-to-this-repo>/skills/bug-to-redmine .agents/skills/
```

Then **restart your agent**.

### Prerequisites

- Redmine MCP server running (Google Sheets auth is handled server-side)
- Bugs sheet with status "New" rows ready

---

## 3. Usage

### Tạo Redmine issues từ bug rows

> "Tạo issue cho các bug trên sheet..."
> "Create Redmine issues from bugs"
> "Push bugs to Redmine"

### Câu hỏi skill sẽ hỏi

1. Spreadsheet ID nào?
2. Redmine project ID?
3. Tracker ID? (mặc định: 1 = Bug)
4. Assignee user ID? (hoặc leave blank)
5. Xử lý bug nào? (all "New" hoặc range cụ thể)

### Kết quả

- Redmine issues được tạo cho mỗi bug row
- Issue IDs được ghi ngược lại vào sheet
- Status cập nhật từ "New" → "Open"
- Trả về tổng kết: created/failed counts

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| "No bugs with status New" | Kiểm tra sheet, đảm bảo có rows cần xử lý |
| "Invalid status transition" | Bug phải có status "New" để tạo Redmine issue |
| "Project not found" | Kiểm tra project_id, chạy `list_redmine_projects` |
| "Assignee not found" | Kiểm tra user ID, chạy `list_project_members` |

---

## 5. Keeping the skill up to date

```bash
git pull --rebase
# re-run installer
```

Restart agent after update.
