---
name: reopen-bug
description: Use when the user wants to reopen a bug that was previously fixed but still fails retest, e.g. "reopen bug này", "mở lại bug", "bug vẫn lỗi, reopen", "retest fail, reopen", "reopen BUG-001". Checks allowed Redmine workflow transitions (never hardcodes "New"), picks the best reopen status, updates Redmine with a reopen note, and updates the Google Sheet. Keeps the same Redmine issue ID — no subtask is created. Use ONLY for reopening bugs, NOT for creating issues, syncing status, or generating test cases.
---

# Reopen Bug

Reopen a bug by updating its status on both Redmine and the Google Sheet. The skill keeps the same issue ID (no subtask), adds a reopen note to the Redmine journal, and updates the sheet to reflect the new state.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools + Redmine MCP tools).

---

## 1. Core rules

1. **Ask-before-reopen**: confirm bug ID, reopen reason, and spreadsheet before making changes.
2. **Only reopen from "Done" or "Closed"**: the bug must have status "Done" or "Closed" on the sheet to be reopened. Other statuses → refuse with explanation.
3. **Same issue ID**: reopen updates the existing Redmine issue, never creates a subtask.
4. **Reopen note is mandatory**: the user must provide a reason (what still fails). No reason → ask.
5. **Check allowed transitions**: call `get_redmine_issue_allowed_statuses` to find which statuses are reachable from the current status. Never hardcode "New" — use the actual allowed status.
6. **Preferred reopen status** (in priority order): pick the first match from the allowed transitions:
   - "Reopen" (if exists in Redmine)
   - "In Progress"
   - "Feedback"
   - "Open"
   - If none of these are allowed → refuse: "Không thể reopen từ trạng thái '<current>'. Các trạng thái cho phép: <list>."
7. **Redmine update**: set status to the chosen status + add `[REOPEN] <note>` to journal.
8. **Sheet update**: column F (status) → "Reopen", column I (redmine_status) → chosen status name.
9. **Partial failure handling**: if Redmine update succeeds but sheet update fails, warn the user (Redmine is already mutated).
10. **Read-only mode**: if `REDMINE_MCP_READ_ONLY` is set, block the update and present the action for manual application.
11. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the bug

**Memory check first**: before asking the user for a spreadsheet ID, check if `~/.redmine-mcp/.google-sheets` exists and has a mapping for the current project.

1. If `.google-sheets` exists and has a mapping → use its `spreadsheet_id` and `sheets.bugs`. Skip to "Verify access".
2. If no mapping → **setup new project sheet**:

   a. Read `~/.redmine-mcp/.redmine` → list all projects (full-list rule).
   b. Ask user: "Bạn đang reopen bug cho project nào?" with project list.
   c. User picks a project → instruct:
      ```
      1. Go to https://sheets.new → create a new spreadsheet
      2. Name it: '<project_name> - QA Test Management'
      3. Click Share → paste: redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com → Editor → Send
      4. Paste the spreadsheet URL here
      ```
   d. Extract spreadsheet_id → verify access → verify sheet structure.
   e. Save mapping to `~/.redmine-mcp/.google-sheets`.
   f. Proceed with this project.

**Verify access**: call `get_sheet_metadata` with the spreadsheet_id to confirm access. If access denied → remind user to share the sheet with `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com` (Editor permission).

Ask the user (structured ask tool, plain text as fallback):

1. **Bug ID**: which bug to reopen? (e.g. BUG-001)
2. **Reopen reason**: what still fails? (mandatory — describe the failing behavior)
3. **Sheet name**: default = "Bugs" (or from `~/.redmine-mcp/.google-sheets` mapping).

---

## 3. Step 2 — Find and validate the bug

1. **Read the Bugs sheet** (all rows starting from row 2).
2. **Find the bug** by matching bug_id (column A) with the user's input.
3. **If not found**: report "Bug <bug_id> không tìm thấy trên sheet." and stop.
4. **Check current status**: column F must be "Done".
   - If status is not "Done" → refuse: "Bug đang ở trạng thái '<current>'. Chỉ có thể reopen từ trạng thái 'Done'."
5. **Check redmine_issue_id**: column H must have a value.
   - If empty → refuse: "Bug chưa có Redmine issue ID. Cần tạo issue trước."
6. **Parse the redmine_issue_id** (single integer from column H).

---

## 4. Step 3 — Update Redmine

1. **Get the issue**: call `get_redmine_issue` with the redmine_issue_id to get current status.
2. **Check allowed transitions**: call `get_redmine_issue_allowed_statuses` with the redmine_issue_id → returns list of reachable statuses.
3. **Pick reopen status** from allowed transitions (priority order):
   - "Reopen" → use if available
   - "In Progress" → use if available
   - "Feedback" → use if available
   - "Open" → use if available
   - None of these → refuse with explanation and list of allowed statuses.
4. **Update the issue**:
   - Set `status_id` to the chosen status's ID.
   - Add `[REOPEN] <reopen_note>` to the journal/notes.
5. **If update fails**: return the error and stop (don't update the sheet).
6. **If update succeeds**: proceed to step 4.

---

## 5. Step 4 — Update the Google Sheet

1. **Find the row** (same row index from step 2).
2. **Update column F** (status) → "Reopen".
3. **Update column I** (redmine_status) → chosen status name (e.g. "In Progress", "Feedback").
4. **If sheet update fails**: log a warning but don't roll back the Redmine update. Report: "Redmine đã cập nhật nhưng sheet cập nhật thất bại. Cần cập nhật sheet thủ công."

---

## 6. Step 5 — Report results

On success:
```
Đã reopen bug BUG-001:
- Redmine issue #1234: status → "In Progress", note added
- Sheet: status → "Reopen", redmine_status → "In Progress"
```

On partial failure:
```
Cảnh báo: Redmine issue #1234 đã được reopen nhưng sheet chưa cập nhật.
Cần cập nhật sheet thủ công.
```

---

## 7. Gotchas checklist

- [ ] Only reopen from "Done" or "Closed" status — validate before attempting.
- [ ] **Never hardcode "New"** — always check allowed transitions via `get_redmine_issue_allowed_statuses`.
- [ ] Preferred reopen status order: Reopen → In Progress → Feedback → Open.
- [ ] Reopen note is mandatory — never reopen without a reason.
- [ ] Same issue ID — never create a subtask for reopening.
- [ ] Partial failure: Redmine succeeds + sheet fails → warn, don't rollback.
- [ ] Respect read-only mode — block if `REDMINE_MCP_READ_ONLY` is set.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
