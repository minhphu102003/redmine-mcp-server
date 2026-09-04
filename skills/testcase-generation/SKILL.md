---
name: testcase-generation
description: Use when the user wants to generate test cases from a user story, e.g. "tạo test case từ user story này", "generate test cases", "tạo test cases cho feature", "write test cases to sheet", "tạo test case lên sheet", "create test cases from US". Reads the user story (from file, text, or Redmine issue), extracts test scenarios, writes a DRAFT file for user review/refinement, and ONLY pushes to Google Sheet after the user explicitly approves ("chốt" / "ok" / "approve"). Use ONLY for test case generation, NOT for bug reporting, Redmine issue creation, or status sync.
---

# Testcase Generation

Generate test cases from a user story, let the user review and refine them in a draft file, and only push to Google Sheets after explicit approval.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (Google Sheets MCP tools).

---

## 1. Core rules

1. **Draft first, push last**: test cases are written to a temp file for review BEFORE touching Google Sheets. Never push directly without user approval.
2. **Mandatory approval gate**: the user must explicitly approve ("chốt", "ok", "approve", "xong rồi", "looks good") before pushing to Google Sheets. Nothing is written to the sheet until this gate passes.
3. **Iterative refinement**: the user can edit the draft file freely — add/remove/reorder test cases, change fields. The agent re-reads the file when the user says it's ready.
4. **Auto-generated IDs**: test_case_id follows the pattern TC-001, TC-002, TC-003... based on existing rows in the sheet (assigned at push time, not in the draft).
5. **Bugs sheet auto-creation**: when pushing, always check if "Bugs" sheet exists. If not, create it with all 14 headers.
6. **Strip `<insecure-content-...>` wrapper tags** from any Redmine-sourced names.
7. **ASK, DON'T ASSUME (CRITICAL)**: never invent business rules, edge cases, validation rules, workflows, UI details, or test data. If the US file is missing info → ask the user. See `USER_STORY_TEMPLATE.md` for the full template and validation rules.
8. **Traceability**: every test case must trace to a specific Acceptance Criteria or Business Rule from the US. Use the "Source" field in the draft.
9. **Output limit (max ~10 detailed TCs per turn) + mandatory continuation message**: avoid generating too much output in one turn — longer single-turn generation causes attention drift, self-repetition, and technique dilution. If the US requires more than 10 test cases, generate detailed versions for the first 10 (prioritize happy path + critical edge cases), and write self-contained outlines for the rest. Whenever a turn ends with outlines still remaining, the response MUST end with the plain-language status template in Section 6 — never assume the user infers this is normal.
10. After moving/editing this skill file, remind the user to **restart the agent**.

---

## 2. Step 1 — Resolve spreadsheet

**Memory check first**: before asking the user for a spreadsheet ID, call `get_user_memory(key=".google-sheets")` to check if a mapping exists.

1. If `.google-sheets` exists → read it and find the mapping for the current project (match `redmine_project_id` against `.redmine` `project.id`).
2. If a mapping exists → use its `spreadsheet_id`, `sheets.testcases`, `sheets.bugs`. Skip to "Resolve user story source" below.
3. If `.google-sheets` doesn't exist, or no mapping for this project → **setup new project sheet**:

   a. Call `get_user_memory(key=".redmine")` → `projects` array (all projects the user has access to). Full-list rule: show all, no truncation.
   b. Ask user: "Bạn đang làm test case cho project nào?" with project list.
   c. User picks a project → instruct:
      ```
      1. Go to https://sheets.new → create a new spreadsheet
      2. Name it: '<project_name> - QA Test Management'
      3. Click Share → paste: redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com → Editor → Send
      4. Paste the spreadsheet URL here
      ```
   d. Extract spreadsheet_id from URL → verify access via `get_sheet_metadata`.
   e. Call `create_test_sheet_structure(spreadsheet_id=<id>, title=<title>, member_names=[...])`.
      The tool adds TestCases and Bugs sheets into the user's spreadsheet (no need to re-share).
   f. Save mapping: call `set_user_memory(key=".google-sheets", value={redmine_project_id, redmine_project_name, spreadsheet_id, spreadsheet_url, sheets, us_color_index: 0, us_id_counter: 1})`.
   g. Proceed with this project.

**Resolve user story source**: where is the story?
- A file path (e.g. `docs/user-stories/login.md`)
- Pasted text
- A Redmine issue ID (read via MCP tools)

**Verify access**: before proceeding, call `get_sheet_metadata` with the spreadsheet_id to confirm the service account can access it. If access denied → remind the user to share the sheet with the service account email (Editor permission).

---

## 3. Step 2 — Parse the user story

Read the user story and extract:

1. **Feature/module name** — from the story title or context.
2. **Test scenarios** — derive from:
   - Acceptance criteria (each AC → at least one test case)
   - Happy path flows
   - Edge cases (invalid input, boundary values, error conditions)
3. For each test case, draft:
   - **title**: short descriptive name (e.g. "Login with valid credentials")
   - **module**: the feature/module name
   - **precondition**: what must be true before executing the steps
   - **steps**: numbered steps to reproduce (each step on a new line)
   - **expected_result**: what should happen

If the source is a Redmine issue, use the issue's description, acceptance criteria, and user story fields.

---

## 4. Step 2.5 — Validate US completeness (CRITICAL)

**Never assume business logic.** If the US file is missing critical information, ASK the user before drafting. See [`USER_STORY_TEMPLATE.md`](./USER_STORY_TEMPLATE.md) for the full template, validation checklist, and 8 specific questions to ask.

### Validation table (summary)

| Field | If missing |
|-------|-----------|
| **Title** | Block |
| **User Story** (As a / I want / So that) | Block |
| **Acceptance Criteria** (≥1) | Block |
| **Module/Feature** | Block |
| **UI Map** (screens + exact labels + navigation) | Block — never invent element names |
| **Business Rules** | Ask — don't auto-invent (UI-visible only) |
| **Preconditions** | Ask — don't auto-invent |
| **Test Data** | Synthesize from AC — don't ask |
| **Out of Scope** | Ask — default to narrow scope (UI-only) |
| **Edge cases** | Ask — offer standard set |
| **Integration concerns** | Ask — visible effects + setup needs only (no API/timeout/500) |

### 4 anti-patterns (NEVER do)

1. **Don't auto-define business rules** — if US doesn't say "only Admin can delete", don't write test for that
2. **Don't auto-define edge cases** — if US doesn't say "handle timeout", don't add timeout test
3. **Don't auto-define validation rules** — if US doesn't specify email format, don't assume
4. **Don't auto-generate test data** without flagging it as placeholder

### If US is severely incomplete

If the US has only a vague idea (e.g. just a title like "Login feature"):
1. Tell the user: "This US is missing too much information. I need at minimum: As a/I want/So that, Module, and 1 Acceptance Criteria to start."
2. Show the [`USER_STORY_TEMPLATE.md`](./USER_STORY_TEMPLATE.md) and ask user to fill in.
3. Once user provides minimum info → continue with validation.

---

## 5. Step 2.75 — Select test design techniques (CRITICAL)

Before writing any test case, **analyze the US characteristics** and **select which test design techniques to apply**. This step ensures every test case is grounded in a systematic methodology, not random guessing.

**CRITICAL PRINCIPLE: Techniques are COMBINED per test case, not applied in isolation.** The goal is ~10-15 well-designed test cases per US, not 30+ scattered tests. One test case can cover EP + BVA + Error Guessing simultaneously.

> Detailed technique catalog, full worked example, and dedup walkthrough → see [`TEST_DESIGN_TECHNIQUES.md`](./TEST_DESIGN_TECHNIQUES.md). Summary below.

### Technique catalog

| # | Technique | When to use |
|---|-----------|-------------|
| 1 | **Equivalence Partitioning (EP)** | Input fields with defined valid/invalid ranges |
| 2 | **Boundary Value Analysis (BVA)** | Any numeric range, length constraint, or count limit |
| 3 | **Decision Table Testing** | Business rules with multiple interacting conditions (≥2 conditions interact) |
| 4 | **State Transition Testing** | Features with states, workflows, or sequential logic |
| 5 | **Error Guessing** | Every test case (experience-based layer) |
| 6 | **Pairwise Testing** | Multiple configuration parameters (≥3 params × ≥2 values) |
| 7 | **Use Case / Scenario Testing** | End-to-end user journeys |

### Selection process

```
FOR EACH technique in [EP, BVA, Decision Table, State Transition, Error Guessing, Pairwise, Use Case]:
  1. Read the US characteristics identified in Step 2
  2. Ask: "Does this US have <technique trigger>?"
  3. If YES → mark technique as APPLICABLE with specific reasons
  4. If NO → mark as NOT APPLICABLE with reason
```

### COMBINE techniques, don't stack them (CRITICAL)

**The #1 mistake: generating separate test cases for each technique.** This creates 30+ redundant tests. Instead, **layer techniques into single test cases**:

```
WRONG (3 separate TCs for the same email field):
  TC-1: EP — test valid email format
  TC-2: BVA — test email at boundary length
  TC-3: Error Guessing — test SQL injection in email

RIGHT (1 combined TC per scenario):
  TC-1: EP+BVA+EG — email='a@b.co' (valid, min length) → success
  TC-2: EP+BVA+EG — email='' (empty, EP invalid partition) → error
  TC-3: EP+EG — email="'; DROP TABLE users;--" (SQL injection) → error
```

### Combination rules (summary)

| Combination | How to combine |
|-------------|----------------|
| **EP + BVA** | Always pair. One test per boundary value. |
| **EP + Error Guessing** | Add error scenarios (null, empty, special chars) as additional partitions in EP. |
| **BVA + Error Guessing** | Test boundary values that are also error-inducing (max+1 overflow, min-1 negative). |
| **Decision Table + EP** | Each rule uses EP-derived values for its conditions. |
| **State Transition + Error Guessing** | Test invalid transitions (already-closed issue, etc.). |
| **Pairwise + EP** | Use EP to define values, then pairwise to reduce combinations. |

### Deduplication rules (reduce TC count)

After generating TCs from all techniques, **merge and deduplicate**:

1. **Same field, same expected outcome → merge.** (TC-1 empty → error + TC-2 null → error → keep 1, mark "EP+EG")
2. **Same boundary, same side → merge.** (BVA min-1 + EP invalid-below-range → keep 1)
3. **Decision Table: merge rules with same action.**
4. **Happy path already covers Use Case** — don't write a separate Use Case TC if the happy path EP test already walks through the full flow.
5. **Error Guessing: max 3-5 error TCs per feature** — pick 3-5 most likely based on field type (text → injection, numeric → overflow, file → size/type).

### Risk-based depth

| Risk level | Technique depth | Example |
|------------|----------------|---------|
| **High** (core business logic, revenue, security) | Full: EP + BVA + Decision Table + Error Guessing | Payment calculation, authentication, data deletion |
| **Medium** (important but not critical) | Standard: EP + BVA + basic Error Guessing | Form validation, search filters, notification settings |
| **Low** (minor features, cosmetic) | Light: EP only + 1-2 Error Guessing | About page, footer links, tooltip text |

### Output: technique matrix

Write a technique selection table into the draft file header (visible to user for verification):

```markdown
# Test Cases — <Feature/Module Name>
Source: <user story source>
Generated: <YYYY-MM-DD>

## Applied test design techniques:
| # | Technique | Status | Reason |
|---|-----------|--------|--------|
| 1 | Equivalence Partitioning | APPLIED | Email field: valid/invalid format partitions |
| 2 | Boundary Value Analysis | APPLIED | Password length 8-50 chars: test at 7, 8, 9, 49, 50, 51 |
| 3 | Decision Table | APPLIED | Role × Permission × Resource = 3 conditions → merged to 5 rules |
| 4 | State Transition | SKIPPED | No workflow states in this US |
| 5 | Error Guessing | APPLIED | Layered into EP/BVA tests (0 extra TCs) |
| 6 | Pairwise | SKIPPED | Only 2 parameters with <3 values each |
| 7 | Use Case | SKIPPED | Covered by happy path EP test |

## Deduplication summary:
- EP + BVA merged for email field (3 boundary tests instead of 6)
- Decision Table: 8 rules → 5 after merging rules with same action
- Error Guessing layered into existing EP/BVA tests (0 extra TCs)
- Total: 15 test cases (vs 30+ without combining)

> Total: N test cases
> - Detailed (this turn): 10
> - Outline (next turns): Y
```

### Rules for technique application

1. **Always apply at least EP + Error Guessing** — EP for input coverage, Error Guessing as an experience layer.
2. **Never skip BVA if the US has any numeric range or count limit.**
3. **Never skip Decision Table if the US has ≥2 conditions that interact.**
4. **Never skip State Transition if the US has workflow/status/sequential logic.**
5. **Don't apply a technique if there's nothing to apply it to** — skipping is valid when the trigger is absent.
6. **Each generated TC must declare which techniques it came from** in the `Source` field (e.g. "EP+BVA" or "Decision Table — merged R1+R3").
7. **Target 10-15 TCs per US.** If you're generating 25+, you're not combining — go back and merge.
8. **After generating all TCs, run deduplication** before writing the draft.

---

## 6. Step 3 — Write draft file

**Output limit: max ~10 detailed test cases per turn.** If the US requires more than 10, AI generates detailed versions for the first 10 (prioritize happy path + critical edge cases), writes **self-contained outlines** for the rest, and asks the user to request more detail.

### Draft file location and preview (CRITICAL — do this every time the draft is created or updated)

Write the draft directly to `/mnt/user-data/outputs/testcases-draft.md` (not a workspace-only path like `.tmp/`) so the user can open, preview, and download it immediately from the chat — never make the user ask "how do I see this file" first.

After every `create_file`/`str_replace` on this file (initial draft, every refine edit in Step 7, every batch of detailed outlines), call `present_files` on it again so an updated preview card appears in the conversation. Re-presenting the same path is expected and cheap — do it on every change, not just the first.

**One-way sync limitation — say this explicitly the first time the draft is presented:** the user can open/download the presented file, but if they edit that downloaded copy directly, those edits are invisible — nothing syncs back. Tell them plainly: to change anything, describe the change in chat (or paste back the edited content) and the draft will be regenerated and re-presented; don't rely on them discovering this on their own.

### Outline self-contained (CRITICAL)

Each outline must be self-contained — AI can read a single outline and re-generate the full TC without re-reading the US. Every outline has 4 mandatory fields:

| Field | Purpose | Example |
|-------|---------|---------|
| **Do** | Specific action (verb + object) | "Submit form with empty email" |
| **With** | Specific input/data used (exact values) | "email='', password='abc123'" |
| **Expect** | Expected result (including error message if any) | "Show error 'Please enter email' below field" |
| **Source** | Trace to AC/Business Rule + technique | "AC4 + EP" or "BVA — boundary max" |

**Do NOT use vague placeholders** (e.g. "test with invalid input") — always state which input and what to expect.

### Format draft

```markdown
# Test Cases — <Feature/Module Name>
US Title: <tên US đầy đủ>          ← thêm vào đây
Source: <user story source>
Generated: <YYYY-MM-DD>

## Applied test design techniques:
| # | Technique | Status | Reason |
|---|-----------|--------|--------|
| 1 | Equivalence Partitioning | APPLIED | <reason> |
| 2 | Boundary Value Analysis | APPLIED | <reason> |
| 3 | Decision Table | SKIPPED | No multi-condition rules in this US |
| 4 | State Transition | SKIPPED | No workflow states |
| 5 | Error Guessing | APPLIED | Standard layer |
| 6 | Pairwise | SKIPPED | <reason> |
| 7 | Use Case | APPLIED | <reason> |

> Total: N test cases
> - Detailed (this turn): 10
> - Outline (next turns): Y

---

## TC-1: <title>
- **Source**: AC1 + EP *(traceability — not pushed to sheet)*
- **US Title**: <us_title>          ← thêm vào đây
- **Module**: <module>
- **Tester**: <tester name or empty>
- **Precondition**: <precondition>
- **Steps**:
  1. <step 1>
  2. <step 2>
  3. <step 3>
- **Expected**: <expected_result>

[... TC-2 to TC-10: detailed as above ...]

---

## TC-11: <title> (outline — awaiting detail)
- **Source**: AC4 + EP
- **US Title**: <us_title>          ← thêm vào outline
- **Do**: Submit login form with empty email
- **With**: email='', password='abc123'
- **Expect**: Show error "Please enter email" below email field, submit button disabled

## TC-12: <title> (outline)
- **Source**: AC4 + BVA
- **US Title**: <us_title>          ← thêm vào outline
- **Do**: Submit login form with password shorter than 8 chars
- **With**: email='user@example.com', password='abc'
- **Expect**: Show error "Password must be at least 8 characters" below the password field, user stays on the form

## TC-13: <title> (outline)
- **Source**: AC5 + State Transition
- **US Title**: <us_title>          ← thêm vào outline
- **Do**: Try logging in 5 times in a row with wrong password
- **With**: email='user@example.com', password='wrong' (×5 within 5 minutes)
- **Expect**: Account locked for 15 minutes, show error "Account temporarily locked"
```

### Presentation message (after writing draft) — MANDATORY plain-language format

**Audience assumption: the person reading this may have zero technical background and has never seen this skill before.** Never use bare jargon ("outline", "detail", "draft") without explaining it in plain words the first time it appears in a conversation. The message below is a template — always keep its 3 parts (status line, what's left, exact next action) even if wording is adapted:

```
Đã tạo xong 10/15 test case (còn 5 test case nữa CHƯA viết chi tiết — đây là bước bình thường của quy trình, không phải lỗi).

5 test case còn lại (mới có tên, chưa có đầy đủ các bước):
- TC-11: <title>
- TC-12: <title>
- TC-13: <title>
- TC-14: <title>
- TC-15: <title>

👉 Để mình viết tiếp phần còn lại, bạn chỉ cần gõ: "tiếp" (hoặc "làm hết")
👉 Nếu muốn xem/sửa file trước, cứ mở file draft rồi báo mình khi xong.
👉 Khi nào ưng ý toàn bộ, gõ "chốt" (hoặc "ok") — mình sẽ đẩy lên Google Sheet.
```

**Rules for this message:**
1. **Status line first, with a fraction (X/Y)** — so the person immediately sees this is partial, not final, without needing to count.
2. **Explicitly say "không phải lỗi" (not an error)** the first time in a conversation a turn ends with remaining test cases — non-technical users seeing an incomplete-looking list is the single most likely point of confusion.
3. **Give ONE literal word the user can type** ("tiếp") as the primary call-to-action, in addition to the more precise alternate phrasing ("detail all outlines") for users who prefer it. Never require the user to know the exact command syntax.
4. **Repeat this same 3-part message at the end of every subsequent turn** that still leaves outlines undetailed (not just the first draft) — see Section 7.
5. Accept `"tiếp"`, `"làm tiếp"`, `"còn nữa"`, `"detail all outlines"`, `"detail hết"` (and close variants) as equivalent to "continue with the next batch".

### When user requests "detail TC-N" or "detail all outlines"

**Process for reading an outline (self-contained → detailed):**

1. **Read outline TC-N** (only need to read 1 outline, no need to re-read US):
   - `Source` → know the original rule (to avoid drift)
   - `Do` → main action
   - `With` → specific input
   - `Expect` → expected result
2. **Generate full TC in detailed format**:
   - **title**: from outline (keep as-is)
   - **Module**: from file header
   - **Precondition**: inferred from `Do` (e.g. "User not logged in", "Form is open")
   - **Steps**: from `Do` + `With` (each step on a new line, more detailed than outline)
   - **Expected**: from `Expect` (copy verbatim or express more clearly)
3. **Overwrite the old outline** in the file (convert from `(outline)` → detailed format).
4. **Max 10 cases per turn** — if user requests "detail all outlines" with >10, process the first 10 and report the rest for the next turn.
5. **Re-present**: update the "Detailed: X, Outline: Y" summary.

---

## 7. Step 4 — Refine (iterative)

When the user requests to modify the draft, there are 2 types of requests:

**a) User edits existing detailed TCs** (edit/add/remove/reorder):
1. Re-read `/mnt/user-data/outputs/testcases-draft.md`.
2. Apply changes as requested.
3. Re-write the draft file.
4. Call `present_files` on it again so the user sees the updated version — an edit that isn't re-presented leaves the user looking at a stale preview.
5. Re-present the summary in chat.

**b) User wants to detail from outline** — trigger on "detail TC-11", "detail all outlines", or any of the plain-language equivalents from Section 6 ("tiếp", "làm tiếp", "còn nữa", "detail hết"):
1. Re-read `/mnt/user-data/outputs/testcases-draft.md`, find the outlines to detail.
2. For each outline, read 4 fields: `Source`, `Do`, `With`, `Expect`.
3. Generate full TC in detailed format (see Step 3, "Process for reading outline").
4. Overwrite the old outline in the file (convert from `(outline)` → detailed).
5. Max 10 cases per turn — if "detail all outlines" with >10, process the first 10 and report the rest for the next turn.
6. Update the "Detailed: X, Outline: Y" summary, and call `present_files` again so the updated file preview shows in chat.
7. **If outlines still remain after this batch, repeat the exact mandatory presentation message from Section 6** (status fraction + "không phải lỗi" + literal next action) — do not shorten or skip it just because it's a later turn. A user who only sees the full message once may not remember it three turns later.
8. **If this batch cleared every remaining outline**, say so plainly and point to the approval gate, e.g.: "Đã viết chi tiết xong toàn bộ N/N test case. Bạn xem lại file, ưng ý thì gõ 'chốt' để mình đẩy lên Google Sheet."

Repeat until the user explicitly approves.

---

## 8. Step 5 — Approval gate

When the user says "chốt", "ok", "approve", "push đi", "xong rồi", "looks good", or similar:
1. Re-read `/mnt/user-data/outputs/testcases-draft.md` one final time.
1.5. **Coverage & Dedup Audit (mandatory when the draft was built across more than one turn/batch)**:
   - **Coverage check**: list every AC and Business Rule from the US, confirm each has at least one TC tracing to it via the `Source` field. If any AC/BR has zero TCs → tell the user before proceeding (don't invent one silently).
   - **Global dedup check**: compare ALL test cases in the file against each other (not just within the last batch) — merge any pair that tests the same field/condition with the same expected outcome, per the dedup rules in Section 5. This catches duplicates that can appear when TCs were generated in separate batches across turns.
   - If any outline (`(outline)`) still remains undetailed at this point, stop and remind the user — do not push partial/outline-only rows to the sheet.
2. Parse all test cases from the draft.
3. **Extract `us_title`**: read the `US Title:` field from the draft file header (e.g. "Login Feature"). This is passed to the tool to generate the US section header row.
4. Read the existing TestCases sheet to find the highest TC-XXX number (for ID generation).
5. Generate IDs: continue from the highest existing TC-XXX. If the sheet is empty, start at TC-001.
6. **Field mapping (draft → sheet)**: `title` from `## TC-N: ...`, `module`, `precondition`, `steps` (join numbered lines), `expected_result`, `tester` (from draft or empty), `evidence` (optional URL string — text only, no file upload). Auto-fields (`test_case_id`, `created_date`, `last_test_result`="Not Tested", `last_test_date`) are handled by the push tool. `Source` is traceability only — not pushed. `US Title` is passed as `us_title` parameter (tool auto-inserts a merged colored header row before the TC rows).

---

## 9. Step 6 — Push to Google Sheets

1. **Check "Bugs" sheet**: if it doesn't exist, create it with 14 headers:
   ```
   bug_id | test_case_id | title | description | priority | status | assigned_to | redmine_issue_id | redmine_status | reporter | report_date | reject_reason | duplicate_of | evidence_url
   ```

2. **Ask about existing data**: if the TestCases sheet already has rows, ask whether to clear existing rows (keep headers) or append new rows.

3. **Write to sheet**:
   - If clearing: write headers + all test case rows starting from row 1.
   - If appending: append rows after the last existing row.
   - **US section header (automatic)**: before appending, the tool automatically inserts a merged colored row with the US title (e.g. `[US-1] Login Feature`) at the correct position. Color is chosen from a rotating 8-color palette and the US ID counter is auto-incremented. AI only needs to pass `us_title` — no manual color or ID management needed.

4. **Verify**: read back the sheet to confirm the data was written correctly.

5. **Set up dropdowns (data validation)**: after writing data, apply dropdown validation to key columns using `set_sheet_data_validation`:

   | Column | Index | Options | Source |
   |--------|-------|---------|--------|
   | `tester` | 6 (G) | Team member names | `get_user_memory(key=".redmine")` → `members[].user.name` |
   | `last_test_result` | 8 (I) | Not Tested, Pass, Fail, Blocked | Static |

   Example: set tester dropdown for TestCases sheet:
   ```
   set_sheet_data_validation(
     spreadsheet_id="<id>",
     sheet_name="TestCases",
     column=6,
     options=["Nguyen Van A", "Tran Thi B", "Le Van C"],
     start_row=2,
     end_row=100000,
     input_message="Select tester"
   )
   ```

   **The system auto-re-applies data validation after every push.** When `add_us_section_header` inserts a US section header row, `insertDimension` can drop existing data validation rules on the shifted rows. The push flow automatically calls `reapply_sheet_validations` (which fetches member names from `.redmine.project_contexts[<project_id>].members`) to restore the dropdowns. AI does NOT need to call `set_sheet_data_validation` manually for the normal push flow — only call it explicitly when setting up a brand new spreadsheet or fixing a column that was never configured.

6. **Report**:
   ```
   Push successful!
   - Test cases: N
   - IDs: TC-001 → TC-0XX
   - Sheet: <spreadsheet_url>
   - Draft file: /mnt/user-data/outputs/testcases-draft.md
   ```

---

## 10. Gotchas checklist

- [ ] **NEVER push without approval** — draft file is the gate, not a suggestion.
- [ ] Draft file goes to `/mnt/user-data/outputs/testcases-draft.md` — not the sheet directly.
- [ ] **Call `present_files` after every write to the draft** (create AND every later edit) — a draft that's written but never (re-)presented is invisible or stale to the user.
- [ ] **Never assume the user can edit the draft file directly and have it sync back** — the presented file is a one-way download; only chat-described changes (or pasted-back content) get applied. State this plainly the first time the draft is shown.
- [ ] IDs are generated at push time, not in the draft.
- [ ] Always re-read the draft file (your own last-written version, from `if_version`/last write result if available) before pushing — don't assume unstated external edits, since the user has no write-back path to the file.
- [ ] Bugs sheet must be created before any bug reporting can happen.
- [ ] Steps should be numbered and each step on a new line.
- [ ] Strip `<insecure-content-...>` wrapper tags from Redmine-sourced names.
- [ ] Each test case must trace to a specific AC or Business Rule (use "Source" field).
- [ ] When US is missing info → ask, never auto-define (see `USER_STORY_TEMPLATE.md`).
- [ ] **Max ~10 detailed TCs per turn** — the rest go in self-contained outlines (4 fields: Do/With/Expect/Source).
- [ ] **ALWAYS select techniques BEFORE writing TCs** — Step 2.75 must complete before Step 3.
- [ ] **Every TC must declare its techniques** in the Source field (e.g. "EP+BVA", "Decision Table — merged R1+R3").
- [ ] **COMBINE techniques per TC, don't stack separate TCs per technique.** Target 10-15 TCs per US, not 30+.
- [ ] **EP + BVA are always paired** — one test per boundary value, not one per partition AND one per boundary.
- [ ] **Error Guessing is a layer** — add to existing EP/BVA tests, don't create separate EG-only TCs.
- [ ] **After generating, run deduplication** — merge same-field/same-outcome TCs before writing draft.
- [ ] **Never end a turn with remaining outlines and no plain-language status message** — assume the reader is non-technical and may mistake a partial batch for an error. Always show X/Y fraction + "không phải lỗi" + literal next action (see Section 6).
- [ ] **Repeat the continuation message on every batch**, not just the first — don't assume the user remembers the syntax from turn 1.
- [ ] **Run the Coverage & Dedup Audit (Section 8, step 1.5) before pushing** whenever the draft was built across multiple turns — don't push if any AC/BR is uncovered or any outline is still undetailed.
- [ ] **Pre-existing column format is preserved on insert** — `add_us_section_header` uses `insertDimension` to insert the US section header row; this can drop data validation rules on the shifted rows. The system auto-re-applies `setDataValidation` + `addConditionalFormatRule` (tester/last_test_result dropdowns and their colors) after every push via `reapply_sheet_validations`. If you observe a row with plain text where a dropdown is expected, check the push log for the re-apply warning — most often it means `.redmine.project_contexts[<project_id>].members` is empty (re-run `redmine init` §2b step 2.0 to fetch it).
