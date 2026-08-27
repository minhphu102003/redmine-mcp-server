---
name: bug-reporting
description: Use when the user wants to log a bug to the Google Sheet "Bugs", e.g. "ghi bug này vào sheet", "log bug to sheet", "tạo bug report trên sheet", "ghi lỗi vào sheet", "create bug row on sheet". Parses the bug description, auto-generates bug_id (BUG-001, BUG-002...), links to a test case if provided, sets status = "New", and appends to the Bugs sheet. Use ONLY for bug reporting to Google Sheets, NOT for Redmine issue creation, status sync, or test case generation.
---

# Bug Reporting

Log a bug to the Google Sheet "Bugs" from a description. The skill auto-generates a bug ID, links to the corresponding test case if provided, and sets the initial status to "New" — ready for the `bug-to-redmine` skill to create Redmine issues.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools).

---

## 1. Core rules

1. **Ask-before-create**: confirm spreadsheet ID, bug details, and linked test case before writing.
2. **Auto-generated IDs**: bug_id follows the pattern BUG-001, BUG-002... based on existing rows.
3. **Initial status**: always "New" — the bug has not been sent to Redmine yet.
4. **Required fields**: title, description, priority, reporter. Missing → ask the user.
5. **Test case link**: if the bug comes from a test failure, link the test_case_id. Otherwise leave empty.
6. **Description format**: structured as steps to reproduce + actual result + expected result.
7. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the bug

**Memory check first**: before asking the user for a spreadsheet ID, check if `.google-sheets` exists at the git worktree root and has a mapping for the current project.

1. If `.google-sheets` exists and has a mapping → use its `spreadsheet_id` and `sheets.bugs`. Skip the spreadsheet question.
2. If not → fall back to asking.

Ask the user (structured ask tool, plain text as fallback):

1. **Bug description**: paste the bug, point to a file, or reference a test case ID that failed.
2. **Spreadsheet ID** (skip if `.google-sheets` has a mapping): or use `GOOGLE_SHEETS_SPREADSHEET_ID` env var.
3. **Linked test case** (optional): if this bug was found during testing, provide the test_case_id (e.g. TC-005).
4. **Priority**: High / Medium / Low (default: Medium).
5. **Reporter**: who found the bug (default: current user).

---

## 3. Step 2 — Parse the bug description

From the user's input, extract:

1. **title**: short bug title (e.g. "Login fails with special characters in password")
2. **description**: structured format:
   ```
   Steps to reproduce:
   1. [step 1]
   2. [step 2]
   3. [step 3]

   Actual result: [what actually happened]
   Expected result: [what should have happened]
   ```
3. **priority**: from the user's answer (High/Medium/Low).
4. **reporter**: from the user's answer.

If the user pastes a raw description, help structure it into the format above.

---

## 4. Step 3 — Generate bug ID and validate

1. **Read the Bugs sheet** to find the highest BUG-XXX number.
2. **Generate new ID**: if the highest is BUG-005, the new one is BUG-006. If the sheet is empty, start at BUG-001.
3. **Validate required fields**: title, description, priority, reporter must all be present. Missing → ask the user.
4. **Set metadata**: report_date = today (YYYY-MM-DD), status = "New", all Redmine-related fields empty.

---

## 5. Step 4 — Push to the Bugs sheet

1. **Confirm with the user**: present the bug row (ID, title, priority, linked test case) and ask for approval.
2. **Append to sheet**: add the row at the end of the Bugs sheet.
3. **Verify**: read back to confirm the row was added.
4. **Report**: bug_id, title, status, linked test case (if any).

---

## 6. Gotchas checklist

- [ ] Always read existing BUG-XXX IDs to avoid duplicate generation.
- [ ] Status is always "New" for newly created bugs.
- [ ] Description should follow the structured format (steps + actual + expected).
- [ ] If no test case is linked, the test_case_id field stays empty.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
