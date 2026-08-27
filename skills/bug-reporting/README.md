# bug-reporting skill

A user-facing agent skill that creates bug rows on the Google Sheet "Bugs" from a bug description, automatically linking to the corresponding test case and setting initial status to "New".

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Clarify** — confirms the bug description source, target spreadsheet, and linked test case |
| 2 | **Parse** — extracts title, description (steps to reproduce, actual result, expected result), priority, reporter |
| 3 | **Generate ID** — creates bug_id (BUG-001, BUG-002...) based on existing rows |
| 4 | **Link to test case** — if the bug comes from a test failure, links test_case_id |
| 5 | **Push** — appends the bug row to "Bugs" sheet with status = "New" |

---

## 2. Installation

### One-liner installer (recommended)

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Manual copy

```bash
cp -r <path-to-this-repo>/skills/bug-reporting .agents/skills/
```

Then **restart your agent**.

### Prerequisites

- Redmine MCP server running (Google Sheets auth is handled server-side)
- "Bugs" sheet must exist (created by `testcase-generation` skill or during init)

---

## 3. Usage

### Ghi bug vào sheet

> "Ghi bug này vào sheet..."
> "Tạo bug report trên sheet"
> "Log this bug to the sheet"

### Câu hỏi skill sẽ hỏi

1. Bug mô tả ở đâu? (text, file, hoặc test case ID)
2. Spreadsheet ID nào?
3. Bug liên kết với test case nào? (nếu có)
4. Mức độ ưu tiên? (High/Medium/Low)

### Kết quả

- Bug row được thêm vào Sheet "Bugs" với ID tự động
- Status mặc định = "New"
- Trả về bug_id và thông tin đã ghi

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| "Bugs sheet not found" | Chạy `testcase-generation` skill trước để tạo sheet |
| "Duplicate bug_id" | Kiểm tra lại sheet, có thể ID đã tồn tại |
| Bug not linked to test case | Kiểm tra test_case_id có đúng format TC-XXX không |

---

## 5. Keeping the skill up to date

```bash
git pull --rebase
# re-run installer
```

Restart agent after update.
