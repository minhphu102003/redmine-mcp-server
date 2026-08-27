---
name: bug-to-redmine
description: Use when the user wants to create Redmine issues from bug rows on the Google Sheet "Bugs", e.g. "tạo issue cho các bug", "push bugs to Redmine", "create Redmine issues from sheet", "tạo Redmine issue từ bug trên sheet", "sync bugs to Redmine". Reads bugs with status "New", creates Redmine issues, writes issue IDs back to the sheet, and updates status to "Open". Use ONLY for creating Redmine issues from sheet bugs, NOT for status sync, reopening, or test case generation.
---

# Bug to Redmine

Read bug rows from the Google Sheet "Bugs" and create Redmine issues for each. The skill validates status transitions, maps fields to Redmine, creates issues via the MCP tools, and writes the Redmine issue IDs back to the sheet.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools + Redmine MCP tools).

---

## 1. Core rules

1. **Ask-before-create**: confirm spreadsheet, project, tracker, and assignee before creating issues.
2. **Only process "New" bugs**: bugs with status other than "New" or with an existing redmine_issue_id are skipped.
3. **Status transition**: New → Open is the only valid transition for issue creation.
4. **Field mapping**:
   - bug title → Redmine subject
   - bug description → Redmine description
   - priority (High/Medium/Low) → Redmine priority_id (must be looked up from live data)
   - assigned_to (name) → Redmine assigned_to_id (must be resolved from members list)
5. **Write back immediately**: after each issue is created, update the sheet with the Redmine issue ID and status "Open".
6. **Partial failure handling**: if one bug fails, continue with the rest. Report successes and failures separately.
7. **Read-only mode**: if `REDMINE_MCP_READ_ONLY` is set, block creation and present the full list for manual creation.
8. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the parameters

**Memory check first**: before asking the user for a spreadsheet ID, check if `.google-sheets` exists at the git worktree root and has a mapping for the current project.

1. If `.google-sheets` exists and has a mapping → use its `spreadsheet_id` and `sheets.bugs`. Skip the spreadsheet question.
2. If not → fall back to asking.

Ask the user (structured ask tool, plain text as fallback):

1. **Spreadsheet ID** (skip if `.google-sheets` has a mapping): or use `GOOGLE_SHEETS_SPREADSHEET_ID` env var.
2. **Bug sheet name**: default = "Bugs" (or from `.google-sheets` mapping).
3. **Redmine project ID**: which project to create issues in.
4. **Tracker ID**: default = 1 (Bug). Look up from live data and present options.
5. **Assignee** (optional): default user ID or "unassigned".
6. **Range**: process all "New" bugs, or a specific range (e.g. "A2:M20").

---

## 3. Step 2 — Read bug rows from the sheet

1. **Read the Bugs sheet** starting from row 2 (skip headers).
2. **Filter**: only rows where:
   - status (column F) = "New"
   - redmine_issue_id (column H) is empty
3. **Parse each row** into: bug_id, test_case_id, title, description, priority, assigned_to, reporter.
4. **Report**: "Tìm thấy N bug cần tạo issue." — present the list to the user.

---

## 4. Step 3 — Look up Redmine context

1. **Get project context**: call `get_project_issue_context` with the project ID → returns trackers, members, priorities, statuses.
2. **Map priority**: look up the user's priority (High/Medium/Low) in the live priorities list → get the priority_id. If no match → ask the user.
3. **Map assignee** (if provided): look up the assigned_to name in the members list → get the user_id. If no match → ask the user or leave unassigned.
4. **Get "New" status ID**: from the statuses list, find the status named "New" → get its ID.
5. **Get "Open" status ID**: from the statuses list, find the status named "Open" → get its ID.

---

## 5. Step 4 — Create Redmine issues

For each bug row:

1. **Validate status**: confirm the bug status is "New" (re-check before creating).
2. **Build the issue**:
   - project_id = confirmed project
   - subject = `[BUG] <bug title>` (or just the title, confirm with user)
   - description = bug description (structured: steps + actual + expected)
   - tracker_id = confirmed tracker (Bug)
   - priority_id = mapped priority
   - status_id = "New" status ID
   - assigned_to_id = mapped assignee (or null)
   - start_date = today
   - done_ratio = 0
3. **Create the issue** via the MCP tool.
4. **Verify returned values**: check that status/priority names match expectations.
5. **Write back to sheet**:
   - Column H (redmine_issue_id) = the new issue ID
   - Column F (status) = "Open"
6. **Continue to the next bug**.

---

## 6. Step 5 — Report results

Present a summary:

```
Kết quả tạo Redmine issues:
- Thành công: 5
- Thất bại: 1

Thành công:
| Bug ID | Redmine Issue | Title |
|--------|---------------|-------|
| BUG-001 | #1234 | Login fails with special chars |
| BUG-002 | #1235 | Dashboard timeout |

Thất bại:
| Bug ID | Title | Lý do |
|--------|-------|-------|
| BUG-003 | API error | Priority "Critical" không tồn tại trong project |
```

---

## 7. Gotchas checklist

- [ ] Only process bugs with status "New" and empty redmine_issue_id.
- [ ] Always look up priority_id and assignee_id from live Redmine data — never assume IDs.
- [ ] Write back issue IDs immediately after each successful creation.
- [ ] Handle partial failures gracefully — don't stop on the first error.
- [ ] Respect read-only mode — block creation if `REDMINE_MCP_READ_ONLY` is set.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
