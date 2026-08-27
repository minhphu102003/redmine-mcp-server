---
name: bug-to-redmine
description: Use when the user wants to create Redmine issues from bug rows on the Google Sheet "Bugs", e.g. "tạo issue cho các bug", "push bugs to Redmine", "create Redmine issues from sheet", "tạo Redmine issue từ bug trên sheet", "sync bugs to Redmine". Reads bugs with status "New", creates Redmine issues, writes issue IDs back to the sheet, and updates status to "Open". Use ONLY for creating Redmine issues from sheet bugs, NOT for status sync, reopening, or test case generation.
---

# Bug to Redmine

Read bug rows from the Google Sheet "Bugs" and create Redmine issues for each. The skill validates status transitions, maps fields to Redmine, creates issues via the MCP tools, and writes the Redmine issue IDs back to the sheet.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools + Redmine MCP tools).

---

## 1. Core rules

1. **Memory check first**: read `.google-sheets` → auto-detect project from spreadsheet mapping. Read `.redmine` → get trackers/members/priorities.
2. **Auto-fill project**: if `.google-sheets` has only one project → use its `redmine_project_id` without asking. Multiple projects → ask which one.
3. **Ask-before-create**: confirm tracker, assignee, and bug range before creating issues.
4. **Only process "New" bugs**: bugs with status other than "New" or with an existing redmine_issue_id are skipped.
5. **Status transition**: New → Open is the only valid transition for issue creation.
6. **Field mapping**:
   - bug title → Redmine subject: `[<module>] [BUG] <bug title>` (1-2 lines, concise)
   - bug description → Redmine description (auto-drafted from template)
   - priority (High/Medium/Low) → Redmine priority_id (must be looked up from live data)
   - assigned_to (name) → Redmine assigned_to_id (must be resolved from members list)
7. **Write back immediately**: after each issue is created, update the sheet with the Redmine issue ID and status "Open".
8. **Partial failure handling**: if one bug fails, continue with the rest. Report successes and failures separately.
9. **Read-only mode**: if `REDMINE_MCP_READ_ONLY` is set, block creation and present the full list for manual creation.
10. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the parameters

**Memory check first**: read both files before asking anything.

1. Read `.google-sheets` → find the project mapping. If the tester has only one project → use its `redmine_project_id` automatically. If multiple → ask which project.
2. Read `.redmine` → get trackers, members, priorities, statuses for the confirmed project.

Ask the user (structured ask tool, plain text as fallback):

1. **Redmine project** (skip if `.google-sheets` has only one project): which project to create issues in.
2. **Tracker ID**: default = 1 (Bug). Look up from live data and present options.
3. **Assignee** (optional): default user ID or "unassigned".
4. **Range**: process all "New" bugs, or a specific range (e.g. "A2:M20").

---

## 3. Step 2 — Read bug rows from the sheet

1. **Read the Bugs sheet** starting from row 2 (skip headers).
2. **Pre-read TestCases sheet**: read column A (test_case_id) and column B (module) once to build a lookup dict `{test_case_id: module}` for O(1) access.
3. **Filter**: only rows where:
   - status (column F) = "New"
   - redmine_issue_id (column H) is empty
4. **Parse each row** into: bug_id, test_case_id, title, description, priority, assigned_to, reporter.
5. **Report**: "Tìm thấy N bug cần tạo issue." — present the list to the user.

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
   - subject = `[<module>] [BUG] <bug title>`
   - description = auto-drafted from bug sheet data (see template below)
   - **Module**: auto-lookup from linked test case → TestCases sheet column B (module). If no linked test case → ask user.
   - tracker_id = confirmed tracker (Bug)
   - priority_id = mapped priority
   - status_id = "New" status ID
   - assigned_to_id = mapped assignee (or null)
   - start_date = today
   - done_ratio = 0
3. **Create the issue** via the MCP tool.
4. **Verify returned values**: check that status/priority names match expectations.
5. **Write back to sheet** (MANDATORY — use write-to-sheet tool):
   - Find the row number from step 2
   - Write to range `<sheet_name>!F<row>:H<row>` with values: `[["Open", "", "<redmine_issue_id>"]]`
   - Column F (status) = "Open"
   - Column H (redmine_issue_id) = the new issue ID (integer, no quotes)
   - Verify the write succeeded before moving to the next bug.
6. **Continue to the next bug**.

### Description template (auto-draft from bug sheet)

Agent drafts the description from bug sheet fields — **never ask the user to write it**. The template is in English, structured for developers:

```markdown
## Bug Summary
- **Bug ID**: <bug_id from sheet>
- **Priority**: <priority from sheet>
- **Reporter**: <reporter from sheet>
- **Test Case**: <test_case_id from sheet, or "N/A">

## Steps to Reproduce
1. [step 1]
2. [step 2]
3. [step 3]

## Actual Result
[what actually happened]

## Expected Result
[what should have happened]

## Environment
- Browser/OS/Device: [if mentioned in bug description]
- App Version: [if mentioned in bug description]

## Attachments
- [screenshot/log path if mentioned in bug description, or "None"]
```

Rules:
- All content in **English**.
- `Bug Summary` section: pull from sheet columns (bug_id, priority, reporter, test_case_id).
- `Steps to Reproduce` / `Actual Result` / `Expected Result`: parse from the bug description (column D). If already structured → keep as-is. If raw → restructure into this format.
- `Environment`: extract from bug description if present, otherwise omit the bullet.
- `Attachments`: note any referenced files/paths, otherwise "None".
- Do NOT invent details — only use what's in the bug sheet.

---

## 6. Step 5 — Report results

Present a summary with clickable links so the user can view issues on Redmine and the sheet on Google Sheets.

**Links to include:**
- Redmine issue URL: `<REDMINE_BASE_URL>/issues/<issue_id>` (base URL from MCP server config or `.redmine`)
- Google Sheet URL: from `.google-sheets` → `spreadsheet_url`

```
Kết quả tạo Redmine issues:
- Thành công: 5
- Thất bại: 1

Thành công:
| Bug ID | Redmine Issue | Title | Link |
|--------|---------------|-------|------|
| BUG-001 | #1234 | Login fails with special chars | [View](https://redmine.example.com/issues/1234) |
| BUG-002 | #1235 | Dashboard timeout | [View](https://redmine.example.com/issues/1235) |

Thất bại:
| Bug ID | Title | Lý do |
|--------|-------|-------|
| BUG-003 | API error | Priority "Critical" không tồn tại trong project |

Sheet: [Open Google Sheet](https://docs.google.com/spreadsheets/d/<spreadsheet_id>/edit)
```

---

## 7. Gotchas checklist

- [ ] **Read `.google-sheets` first** — auto-detect project from spreadsheet mapping, don't ask if only one project.
- [ ] **Read `.redmine` first** — get trackers/members/priorities for the confirmed project.
- [ ] Only process bugs with status "New" and empty redmine_issue_id.
- [ ] Always look up priority_id and assignee_id from live Redmine data — never assume IDs.
- [ ] **Subject format**: `[<module>] [BUG] <bug title>` — module auto-lookup from linked test case, ask if no test case linked.
- [ ] **Bug title is short** — 1-2 lines, concise summary, not a full sentence.
- [ ] **Pre-read TestCases** once to build `{test_case_id: module}` lookup — avoid N+1 API calls.
- [ ] **Auto-draft description** from bug sheet data — never ask user to write it, never pass raw description as-is.
- [ ] Description template has 6 sections: Bug Summary, Steps to Reproduce, Actual Result, Expected Result, Environment, Attachments.
- [ ] **Include links in report** — Redmine issue URL + Google Sheet URL for each created issue.
- [ ] **Write back to sheet is MANDATORY** — after each successful creation, use write-to-sheet tool to update F<row> (status="Open") and H<row> (redmine_issue_id).
- [ ] Write back issue IDs immediately after each successful creation — don't batch.
- [ ] Handle partial failures gracefully — don't stop on the first error.
- [ ] Respect read-only mode — block creation if `REDMINE_MCP_READ_ONLY` is set.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
