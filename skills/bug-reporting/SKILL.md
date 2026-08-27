---
name: bug-reporting
description: Use when the user wants to log a bug to the Google Sheet "Bugs", e.g. "ghi bug này vào sheet", "log bug to sheet", "tạo bug report trên sheet", "ghi lỗi vào sheet", "create bug row on sheet". Parses the bug description, auto-generates bug_id (BUG-001, BUG-002...), links to a test case if provided, sets status = "New", and appends to the Bugs sheet. Use ONLY for bug reporting to Google Sheets, NOT for Redmine issue creation, status sync, or test case generation.
---

# Bug Reporting

Log a bug to the Google Sheet "Bugs" from a description. The skill auto-generates a bug ID, links to the corresponding test case if provided, and sets the initial status to "New" — ready for the `bug-to-redmine` skill to create Redmine issues.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools).

---

## 1. Core rules

1. **Memory check first**: read `.redmine` and `.google-sheets` before asking anything.
2. **Auto-fill reporter**: `reporter` is ALWAYS auto-filled from `.redmine` → `user_mappings[0].redmine_name`. This skill is for testers only; init has already identified the current user. **Never ask.**
3. **Ask-before-create**: confirm bug details and linked test case before writing.
4. **Auto-generated IDs**: bug_id follows the pattern BUG-001, BUG-002... based on existing rows.
5. **Initial status**: always "New" — the bug has not been sent to Redmine yet.
6. **Required fields**: title, description, priority. Missing → ask the user.
7. **Test case link**: if the bug comes from a test failure, link the test_case_id. Otherwise leave empty.
8. **Description format**: structured as steps to reproduce + actual result + expected result.
9. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the bug

**Memory check first** (both files must exist after init):

1. Read `.redmine` → `user_mappings[0].redmine_name` → auto-fill `reporter`. If missing → init was not run, tell user to run `redmine init` first.
2. Read `.google-sheets` → find mapping for current project (match `redmine_project_id` against `.redmine` `project.id`).
3. If mapping exists → use its `spreadsheet_id` + `sheets.bugs`.
4. If no mapping → **setup new project sheet**:

   a. Read `.redmine` → `projects` array (full-list rule).
   b. Ask user: "Bạn đang report bug cho project nào?" with project list.
   c. User picks a project → instruct:
      ```
      1. Go to https://sheets.new → create a new spreadsheet
      2. Name it: '<project_name> - QA Test Management'
      3. Click Share → paste: redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com → Editor → Send
      4. Paste the spreadsheet URL here
      ```
   d. Extract spreadsheet_id → verify access → verify sheet structure.
   e. Save mapping to `.google-sheets`.
   f. Proceed with this project.

**Verify access**: before writing, call `get_sheet_metadata` with the spreadsheet_id to confirm access. If access denied → remind user to share the sheet with `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com` (Editor permission).

Ask the user (structured ask tool, plain text as fallback):

1. **Bug description**: paste the bug, point to a file, or reference a test case ID that failed.
2. **Linked test case** (optional): if this bug was found during testing, provide the test_case_id (e.g. TC-005).
3. **Priority**: High / Medium / Low (default: Medium).

---

## 3. Step 2 — Parse the bug description

From the user's input, extract:

1. **title**: short bug title, 1-2 lines max, descriptive enough for devs to understand at a glance (e.g. "Login fails with special characters in password"). **Not** a full sentence — a concise summary.
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
4. **reporter**: auto-fill from `.redmine` → `user_mappings[0].redmine_name` (always available after init).

If the user pastes a raw description, help structure it into the format above.

---

## 4. Step 3 — Generate bug ID and validate

1. **Read the Bugs sheet** to find the highest BUG-XXX number.
2. **Generate new ID**: if the highest is BUG-005, the new one is BUG-006. If the sheet is empty, start at BUG-001.
3. **Validate required fields**: title, description, priority must all be present. Missing → ask the user.
4. **Set metadata**: report_date = today (YYYY-MM-DD), status = "New", reporter = auto-filled, assigned_to = empty, all Redmine-related fields empty.

---

## 5. Step 4 — Push to the Bugs sheet

### Field mapping (draft → sheet)

| Field | Sheet column | Value | Dropdown? |
|-------|-------------|-------|-----------|
| bug_id | A | Auto-generated: BUG-001, BUG-002... | No |
| test_case_id | B | From user input, or empty | No |
| title | C | From parsed bug description | No |
| description | D | Structured: steps + actual + expected | No |
| priority | E | From user input — **MUST be exactly**: `High`, `Medium`, or `Low` | Yes |
| status | F | Always `New` | Yes (10 values) |
| assigned_to | G | **Always empty** — user selects via UI dropdown later | Yes (from `.redmine` members) |
| redmine_issue_id | H | Empty (set by `bug-to-redmine` skill) | No |
| redmine_status | I | Empty (set by `status-sync` skill) | No |
| reporter | J | Auto-fill from `.redmine` → `user_mappings[0].redmine_name` | No |
| report_date | K | Today (YYYY-MM-DD) | No |
| reject_reason | L | Empty (set by `status-sync` skill) | No |
| duplicate_of | M | Empty (set by `status-sync` skill) | No |

**Dropdown notes**: Columns E/F/G have data validation (dropdown) on the sheet. Agent writes values via API — must use **exact values** from the dropdown list. Invalid values will show as invalid on the sheet UI but data is still written.

### Push steps

1. **Confirm with the user**: present the bug row (ID, title, priority, linked test case) and ask for approval.
2. **Append to sheet**: add the row at the end of the Bugs sheet.
3. **Verify**: read back to confirm the row was added.
4. **Report**: bug_id, title, status, linked test case (if any).

---

## 6. Gotchas checklist

- [ ] **Read `.redmine` first** — reporter is always auto-filled, never ask.
- [ ] **Read `.google-sheets` first** — auto-fill spreadsheet_id and sheet name, never ask if mapping exists.
- [ ] **assigned_to always empty** — user selects via UI dropdown later, never write a value.
- [ ] **Priority exact values** — MUST be `High`, `Medium`, or `Low` (no typos, no Vietnamese).
- [ ] **Status always `New`** — must be exact match to dropdown value.
- [ ] Always read existing BUG-XXX IDs to avoid duplicate generation.
- [ ] Description should follow the structured format (steps + actual + expected).
- [ ] If no test case is linked, the test_case_id field stays empty.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
