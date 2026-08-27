---
name: reopen-bug
description: Use when the user wants to reopen a bug that was previously fixed but still fails retest, e.g. "reopen bug này", "mở lại bug", "bug vẫn lỗi, reopen", "retest fail, reopen", "reopen BUG-001". Updates the Redmine issue status to "New" with a reopen note, and updates the Google Sheet status to "Reopen". Keeps the same Redmine issue ID — no subtask is created. Use ONLY for reopening bugs, NOT for creating issues, syncing status, or generating test cases.
---

# Reopen Bug

Reopen a bug by updating its status on both Redmine and the Google Sheet. The skill keeps the same issue ID (no subtask), adds a reopen note to the Redmine journal, and updates the sheet to reflect the new state.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools + Redmine MCP tools).

---

## 1. Core rules

1. **Ask-before-reopen**: confirm bug ID, reopen reason, and spreadsheet before making changes.
2. **Only reopen from "Done"**: the bug must have status "Done" on the sheet to be reopened. Other statuses → refuse with explanation.
3. **Same issue ID**: reopen updates the existing Redmine issue, never creates a subtask.
4. **Reopen note is mandatory**: the user must provide a reason (what still fails). No reason → ask.
5. **Redmine update**: set status to "New" (or the Redmine status that means "not fixed") + add `[REOPEN] <note>` to journal.
6. **Sheet update**: column F (status) → "Reopen", column I (redmine_status) → "New".
7. **Partial failure handling**: if Redmine update succeeds but sheet update fails, warn the user (Redmine is already mutated).
8. **Read-only mode**: if `REDMINE_MCP_READ_ONLY` is set, block the update and present the action for manual application.
9. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the bug

**Memory check first**: before asking the user for a spreadsheet ID, check if `.google-sheets` exists at the git worktree root and has a mapping for the current project.

1. If `.google-sheets` exists and has a mapping → use its `spreadsheet_id` and `sheets.bugs`. Skip the spreadsheet question.
2. If not → fall back to asking.

Ask the user (structured ask tool, plain text as fallback):

1. **Bug ID**: which bug to reopen? (e.g. BUG-001)
2. **Reopen reason**: what still fails? (mandatory — describe the failing behavior)
3. **Spreadsheet ID** (skip if `.google-sheets` has a mapping): or use `GOOGLE_SHEETS_SPREADSHEET_ID` env var.
4. **Sheet name**: default = "Bugs" (or from `.google-sheets` mapping).

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

1. **Get the issue**: call `get_redmine_issue` with the redmine_issue_id.
2. **Find "New" status ID**: call `list_redmine_issue_statuses` and find the status named "New" → get its ID.
3. **Update the issue**:
   - Set `status_id` to the "New" status ID.
   - Add `[REOPEN] <reopen_note>` to the journal/notes.
4. **If update fails**: return the error and stop (don't update the sheet).
5. **If update succeeds**: proceed to step 4.

---

## 5. Step 4 — Update the Google Sheet

1. **Find the row** (same row index from step 2).
2. **Update column F** (status) → "Reopen".
3. **Update column I** (redmine_status) → "New".
4. **If sheet update fails**: log a warning but don't roll back the Redmine update. Report: "Redmine đã cập nhật nhưng sheet cập nhật thất bại. Cần cập nhật sheet thủ công."

---

## 6. Step 5 — Report results

On success:
```
Đã reopen bug BUG-001:
- Redmine issue #1234: status → "New", note added
- Sheet: status → "Reopen", redmine_status → "New"
```

On partial failure:
```
Cảnh báo: Redmine issue #1234 đã được reopen nhưng sheet chưa cập nhật.
Cần cập nhật sheet thủ công.
```

---

## 7. Gotchas checklist

- [ ] Only reopen from "Done" status — validate before attempting.
- [ ] Reopen note is mandatory — never reopen without a reason.
- [ ] Same issue ID — never create a subtask for reopening.
- [ ] Redmine update uses status "New" (or the appropriate "not fixed" status for the instance).
- [ ] Partial failure: Redmine succeeds + sheet fails → warn, don't rollback.
- [ ] Respect read-only mode — block if `REDMINE_MCP_READ_ONLY` is set.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
