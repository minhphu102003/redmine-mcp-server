---
name: status-sync
description: Use when the user wants to sync Redmine issue statuses back to the Google Sheet "Bugs", e.g. "check dev fix chưa", "sync trạng thái từ Redmine", "update sheet status from Redmine", "đồng bộ trạng thái Redmine về sheet", "check Redmine status". Requires: Bugs sheet with redmine_issue_id already filled (run bug-to-redmine first). Reads bugs with redmine_issue_id, checks Redmine for current status/done_ratio/journals, maps to sheet status, detects reject/deferred/need_info/duplicate, and updates TestCases when bugs close. Use ONLY for status synchronization, NOT for creating issues, reopening bugs, or generating test cases.
---

# Status Sync

Synchronize Redmine issue statuses back to the Google Sheet "Bugs". The skill checks each Redmine issue, maps statuses, detects special states (reject, duplicate, deferred, need_info) from journal notes, and updates both the Bugs and TestCases sheets.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools + Redmine MCP tools).

---

## 1. Core rules

### Prerequisites (MUST have before using this skill)

| Prerequisite | Required? | How to get it |
|---|---|---|
| **Bugs sheet** | ✅ Must | Created by `testcase-generation` or `bug-reporting` skill |
| **Bugs with `redmine_issue_id`** | ✅ Must | Created by `bug-to-redmine` skill (column H must be filled) |
| **TestCases sheet** | Optional | Created by `testcase-generation` skill |

**If no bugs have `redmine_issue_id` → tell the user to run `bug-to-redmine` first.**

### Skill flow dependency

```
testcase-generation → bug-reporting → bug-to-redmine → status-sync ← YOU ARE HERE
```

### Rules

1. **Ask-before-sync**: confirm spreadsheet ID and sheet names before reading/writing.
2. **Only process linked bugs**: only rows where redmine_issue_id (column H) is not empty.
3. **Status mapping** (Redmine → Sheet):

   | Redmine Status | Sheet Status | Extra Action |
   |---|---|---|
   | New | Open | — |
   | In Progress | In Progress | — |
   | Resolved (done_ratio=100%) | Done | — |
   | Closed | Closed | Update TestCases: last_test_result = "Pass" |
   | Rejected | Reject | Parse reject reason from journals → column L |
   | Rejected + "duplicate" | Duplicate | Parse issue ID → column M |
   | Deferred | Deferred | — |
   | Need Info / Feedback | Need Info | — |

4. **Reject reason parsing**: scan journal notes for the rejection reason. Look for notes from a developer explaining why the bug was rejected.
5. **Duplicate detection**: if reject reason contains "duplicate" (case-insensitive), set status to "Duplicate" and parse the referenced issue ID into column M.
6. **TestCases update**: when a bug's status becomes "Closed" and it has a test_case_id, update the TestCases sheet:
   - Column I (last_test_result) = "Pass"
   - Column J (last_test_date) = today
7. **Batch reads**: pre-read TestCases sheet once to build a lookup dict, avoid N+1 API calls.
8. **Read-only mode**: if `REDMINE_MCP_READ_ONLY` is set, block updates and present the diff for manual application.
9. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.

---

## 2. Step 1 — Clarify the parameters

**Memory check first**: before asking the user for a spreadsheet ID, check if `.google-sheets` exists at the git worktree root and has a mapping for the current project.

1. If `.google-sheets` exists and has a mapping → use its `spreadsheet_id`, `sheets.testcases`, `sheets.bugs`. Skip to "Verify access".
2. If no mapping → **setup new project sheet**:

   a. Read `.redmine` → `projects` array (full-list rule).
   b. Ask user: "Bạn đang sync status cho project nào?" with project list.
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

**Verify access**: call `get_sheet_metadata` with the spreadsheet_id to confirm access. If access denied → remind user to share the sheet with `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com` (Editor permission).

Ask the user (structured ask tool, plain text as fallback):

1. **Bug sheet name**: default = "Bugs" (or from `.google-sheets` mapping).
2. **TestCases sheet name**: default = "TestCases" (or from `.google-sheets` mapping).

---

## 3. Step 2 — Read and process bugs

1. **Read the Bugs sheet** (all rows starting from row 2).
2. **Filter**: only rows where redmine_issue_id (column H) is not empty.
3. **Pre-read TestCases sheet**: read column A (test_case_id) once to build a lookup dict `{test_case_id: row_number}` for O(1) access.
4. **For each linked bug**:
   - Parse the redmine_issue_id (single integer, from column H).
   - Call `get_redmine_issue` with journals included.
   - Extract: status name, done_ratio, journals (notes + created_on).
   - Map Redmine status → Sheet status per the mapping table.
   - If status changed → update column F (status).
   - Always update column I (redmine_status) with the current Redmine status name.

---

## 4. Step 3 — Handle special states

### Reject handling

When Redmine status = "Rejected":
1. Scan journal notes (most recent first) for the rejection reason.
2. Write the reason to column L (reject_reason).
3. Check if the reason contains "duplicate" (case-insensitive):
   - If yes → set Sheet status to "Duplicate", parse the referenced issue ID, write to column M (duplicate_of).
   - If no → set Sheet status to "Reject".

### Deferred handling

When Redmine status = "Deferred":
1. Set Sheet status to "Deferred".
2. No extra action needed.

### Need Info handling

When Redmine status = "Need Info" or "Feedback":
1. Set Sheet status to "Need Info".
2. No extra action needed.

---

## 5. Step 4 — Update TestCases for closed bugs

For each bug with Sheet status = "Closed" that has a test_case_id:
1. Look up the test_case_id in the pre-built TestCases lookup dict.
2. If found:
   - Update column I (last_test_result) = "Pass"
   - Update column J (last_test_date) = today (YYYY-MM-DD)
3. If not found → log a warning and continue.

---

## 6. Step 5 — Report results

Present a summary:

```
Kết quả đồng bộ:
- Đã kiểm tra: 20 issues
- Đã cập nhật: 5

Phân theo trạng thái:
- Open: 3
- In Progress: 8
- Done: 5
- Closed: 3
- Reject: 1

Chi tiết thay đổi:
| Issue ID | Trạng thái cũ | Trạng thái mới |
|----------|----------------|-----------------|
| 1234 | New | In Progress |
| 1235 | In Progress | Done |
```

---

## 7. Gotchas checklist

- [ ] **MUST have bugs with redmine_issue_id** — if no bugs are linked, tell user to run `bug-to-redmine` first.
- [ ] Only process rows with non-empty redmine_issue_id.
- [ ] Pre-read TestCases once to avoid N+1 API calls.
- [ ] Reject reason comes from journal notes, not from the issue status itself.
- [ ] Duplicate detection checks for "duplicate" keyword in the reject reason.
- [ ] TestCases update only happens for "Closed" bugs with a linked test_case_id.
- [ ] Respect read-only mode — block updates if `REDMINE_MCP_READ_ONLY` is set.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] After moving/editing this skill file, remind the user to **restart the agent**.
