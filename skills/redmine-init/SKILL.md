---
name: redmine-init
description: Use when the user asks to initialize or refresh the Redmine project mapping for the current repository, e.g. "redmine init", "khởi tạo redmine", "map repo này với project redmine", "tạo file .redmine", "refresh redmine context", "redmine context bị cũ". Creates or refreshes the `.redmine` JSON cache file holding the project ID and static ID lists (trackers, statuses, priorities, members, versions, categories, custom fields) with a fetched_at timestamp, so issue-creation skills can work without re-fetching every value. Devs store it at the git worktree root; testers use server-side memory with per-project contexts fetched lazily during Google Sheets setup. Use ONLY for init/refresh of the cache, NOT for creating issues, logging time, or wiki work.
---

# Redmine Init

Creates/refreshes a `.redmine` JSON cache mapping the repo to a Redmine project with static ID lists. For testers, also creates/refreshes `.google-sheets` memory. Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides.

---

## 1. Core principles

- **Memory access (CRITICAL)**:
  - **Tester** → use MCP memory tools: `set_user_memory(key=".redmine", value=...)` and `set_user_memory(key=".google-sheets", value=...)`
  - **Dev/Leader** → write to local file at git worktree root (`git rev-parse --show-toplevel`)
  - If not a git repo AND role ≠ tester → ask the user where to place the file.

- **Memory tool fallback**: If MCP memory tools are unavailable (e.g. legacy mode), fall back to local files at `~/.redmine-mcp/`.

- The `.redmine` file is a **snapshot** — it is a trusted source for *static* ID lists (project, trackers, statuses, priorities, members, versions, categories, custom fields) while fresh. It never stores per-issue state (e.g. which priority/status an issue currently has) — that changes hourly and is always fetched live.
- The file is **NOT** a source of truth for *dynamic* state — allowed status transitions, parent-issue validity, or members who joined after the snapshot. Those must still be verified live.
- Freshness is decided by `fetched_at` (ISO 8601, UTC) vs the TTL of **14 days**.
- Tool responses wrap every name in `<insecure-content-...>` tags — **always strip these tags** before writing the cache.
- v1 supports exactly **one project per repository**. For a monorepo that spans multiple Redmine projects, ask the user which project the repo maps to and keep one file.
- **Role detection**: the first step asks whether the user is a **dev** or **tester** (or leader). This determines the init flow: dev → `.redmine` only; tester → `.redmine` + `.google-sheets`; leader → `.redmine` + GitHub mapping + member working rules.
- **Testers manage multiple projects**: each project gets its own spreadsheet mapping in `.google-sheets`. A tester can have project A with spreadsheet X and project B with spreadsheet Y.
- After moving/editing this skill file, remind the user to **restart the agent** for the skill to load.

---

## 2. Init flow (no `.redmine` file yet)

### Step 0 — Detect role

Ask the user (structured ask tool, plain text as fallback):

**"Bạn là ai trong dự án này?"**
1. **Developer** — chỉ cần init `.redmine` (Redmine cache)
2. **Tester** — cần init `.redmine` + `.google-sheets` (Google Sheets memory)
3. **Leader** — init `.redmine` + hỏi mapping GitHub + hỏi member working rules

| Role | Files created | Flow | GitHub↔Redmine mapping | Member working rules | Storage path |
|---|---|---|---|---|---|
| Developer | `.redmine` | Section 2a | ✅ Asked | ❌ Skipped | Git worktree root |
| Tester | `.redmine` + `.google-sheets` | Section 2a + 2b | ❌ Skipped | ❌ Skipped | MCP memory tools |
| Leader | `.redmine` | Section 2a + Step 6 + Step 7 | ✅ Asked | ✅ Asked | Git worktree root |

### 2a. Dev flow — Init `.redmine`

1. **Locate the storage path**:
   - **Tester role**: use MCP memory tools (`set_user_memory`). No local file path needed.
   - **Dev/Leader role**: run `git rev-parse --show-toplevel` → use that root. If not a git repo → ask the user where to place the file.
2. **Check for an existing file**: if `.redmine` already exists at the storage path → follow the refresh flow (section 3) instead.
3. **List projects**: call the list-projects capability (e.g. `redmine_list_redmine_projects`) → returns `id`, `name`, `identifier`, `description`, `created_on`.
4. **Ask the user to choose — role-dependent**:
   - **Dev/Leader**: ask "repo này tương ứng với project Redmine nào?" (map repo → 1 project). **Full-list rule** applies: before calling any ask tool, render the **complete** project list as a markdown table (every row, no truncation):

   ```markdown
   | # | ID | Project | Identifier |
   |---|----|---------|------------|
   | 1 | 313 | [AI] Chatbot Tuyển Sinh | ai-chatbot-tuyen-sinh |
   | 2 | 156 | [MobileApp] CLICK-Ed app platform | du-an-qa-app |
   | ... | ... | ... | ... |
   ```

   Then ask the question with the full list repeated as a numbered list in the question text. Add ≤ 4 clickable shortcuts of the most likely projects on top, plus a "Khác — gõ số hoặc tên từ bảng trên" free-text option. Lists > ~30 rows: still render full table, then ask the user to narrow by keyword in a follow-up.
   - **Tester**: **SKIP this step entirely**. Testers don't map repos to projects — they work with multiple projects at once via the `projects` array in step 5b. The `project` field in `.redmine` is only written after the user picks a project in §2b step 2.
5. **Fetch project context**:
   - **Dev/Leader**: call the project-context capability (e.g. `redmine_get_project_issue_context`, project_id) with the project chosen in step 4 → returns project, trackers, categories, members (with roles), versions, statuses (`is_closed`), **priorities**, custom_fields, required_custom_fields. The `priorities` section is the **complete** list (e.g. `{"id": 2, "name": "Normal"}`); Redmine has no separate "list priorities" endpoint, the context tool provides it. This caches only the **static option list** (the dropdown of values), never any issue's current priority — per-issue priority state changes hourly and is always fetched live.
   - **Tester**: **SKIP this step entirely**. Testers do NOT fetch any project context at init. Per-project context (trackers/members/priorities/etc.) is fetched **lazily and per-project** during Google Sheets setup (section 2b step 2.0) so that each project gets its own context — never reuse one project's context for another. The `.redmine` file for a tester does NOT contain root-level `trackers`/`members`/`priorities`/`statuses` fields; it only contains `projects[]` (lean list) and `project_contexts{}` (per-project dict, populated during 2b).
5b. **For testers only — save all projects**: if role = Tester, the `projects` list (from step 3) is saved into `.redmine` as `projects` array. This allows QA skills to list all projects when setting up Google Sheets, without calling `list_redmine_projects` again. Devs do NOT get this field — they only need the single `project`.
6. **Map GitHub account ↔ Redmine member (dev/leader only)**: **SKIP this step if role = Tester.** Testers don't need GitHub↔Redmine mapping — they work in Google Sheets, not Git commits.
   1. Detect GitHub side: run `gh api user` (requires `gh` CLI, installed first per the issue-workflow skill's prerequisites) → returns `login`, `name`, `email`. If `gh` is unavailable, fall back to `git config user.name` + `git config user.email`.
   2. Match the detected GitHub identity against the `members` list from step 5. Match by **name** (case-insensitive) first, then by **email** if name doesn't match.
   3. If exactly **one** confident match → confirm with the user via the structured ask tool: "GitHub account `janedoe` (Jane Doe) maps to Redmine member nào?" with the matched member pre-selected and 1–3 other likely members as clickable shortcuts. If the user **rejects** the pre-selected member → fall through to case 6.4 (re-ask with full members list).
   4. If **no match** or **multiple matches** → apply the **full-list rule** from step 4: render the complete `members` list as a markdown table (| # | ID | Name | Roles |) in the chat message — all rows visible, no truncation — then present the full list in the question text of the structured ask tool (user types number or name; ≤4 clickable shortcuts of the most likely picks on top, never instead of the full list).
   5. **Optional — map additional committers**: ask "Có muốn map thêm committer nào không?" — if yes, run `git shortlog -sne --since="6 months"` and let the user pick. Default: **only the current user** (tiết kiệm token).
   6. Build the `user_mappings` array: each entry `{"github": "<login>", "git_email": "<email>", "redmine_user_id": <id>, "redmine_name": "<name>"}`. Strip wrapper tags from all names.
7. **Collect member working rules (leaders only)**: for each member mapped in step 6, ask the user for that person's working rules — "Người này làm role gì và có rule/đặc thù riêng khi làm việc không? (gõ 'bỏ qua' để skip)". Prompt with the catalog (role/stack, required tests, code-review expectations, AI-assistant usage policy, reporting cadence, definition of done) — see [`member-rules-catalog.md`](./member-rules-catalog.md). User answers, skips, or says "bỏ qua" per member. **Never invent a rule**; store only what the user explicitly said as short verbatim bullets (Vietnamese OK).
8. **Strip wrapper tags**: remove every `<insecure-content-...>` and `</insecure-content-...>` marker from names.
9. **Write `.redmine`**:
   - **Tester**: call `set_user_memory(key=".redmine", value=<data>)` to store in server-side memory.
   - **Dev/Leader**: write a single JSON file at git worktree root, exact schema in section 4, `fetched_at` = current UTC timestamp (ISO 8601, e.g. `2026-08-06T00:00:00Z`).
10. **Verify**:
    - **Tester**: call `get_user_memory(key=".redmine")` → confirm it returns valid data with no wrapper tags and `fetched_at` is set.
    - **Dev/Leader**: read the file back; confirm it parses as valid JSON, contains no wrapper tags, and `fetched_at` is set.
11. **Report**:
    - **Dev/Leader**: project id/name/identifier, counts of trackers/members/statuses/priorities, the `user_mappings` count, the `member_rules` count (leaders only), the storage location (file path), reminder to re-run `redmine init` to refresh; the file is safe to commit (no secrets, dev only).
    - **Tester**: the full `projects` array length, the storage location (server memory), reminder to re-run `redmine init` to refresh. Note: no `project` field is set yet — it will be written in §2b step 2 after the user picks a project. QA skills will use the `projects` array until then.
12. **If role = Tester → continue to section 2b (Google Sheets memory setup)**.

### 2b. Tester flow — Init `.google-sheets`

After `.redmine` is created, set up Google Sheets memory for test management.

**Service Account**: `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`
The MCP server authenticates with this service account. Users create their own Google Sheet and share it with this email (Editor permission).

1. **Check existing `.google-sheets`**: call `get_user_memory(key=".google-sheets")` → if data exists, follow the refresh flow (section 3b) instead.

2. **Ask which project(s) to setup**:
   - Call `get_user_memory(key=".redmine")` → `projects` array (full-list rule).
   - Render all projects as a markdown table — every row, no truncation:

     ```markdown
     | # | ID | Project | Identifier |
     |---|----|---------|------------|
     | 1 | 313 | [AI] Chatbot Tuyển Sinh | ai-chatbot-tuyen-sinh |
     | 2 | 156 | [MobileApp] CLICK-Ed app platform | du-an-qa-app |
     | ... | ... | ... | ... |
     ```
   - Ask: "Bạn muốn setup Google Sheet cho project nào? (gõ số/tên từ bảng, hoặc 'all' để setup tất cả, hoặc 'done' nếu không setup project nào bây giờ)"
   - User picks 1+ projects (or 'all' / 'done').

2.0. **Fetch per-project context (lazily, one project at a time)**:
   - For EACH project the user picked in step 2, call `get_project_issue_context(project_id)` and save the full result into `.redmine.project_contexts["<project_id>"]` (key is the string form of the project ID; create the dict if absent, update if present).
   - This is the **only** point where project context is fetched for testers — one project at a time, never reused across projects. This prevents the cross-project contamination bug where one project's trackers/priorities/members get applied to a different project.
   - Skip this step for projects the user did NOT pick in step 2 (e.g. they chose 'done' or only a subset). Per-project context is also written when the user picks "skip" later in step 3 for that project (treated as "no context needed for this project").
   - After fetching, show a one-line context summary to the user before the per-project setup begins: "Project X (id 12) — 3 trackers, 5 priorities, 10 members, 2 versions, 0 custom fields" so the user can confirm they're setting up the right project.

3. **For each picked project, do the per-project setup**:

   a. **Show instructions** and **parse response**:
      ```
      Project '<project_name>' (ID: <id>) — setup Google Sheet:

      1. Go to https://sheets.new → create a new spreadsheet
      2. Name it: '<project_name> - QA Test Management' (or your preferred name)
      3. Click Share → paste: redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com → Editor → Send
      4. Copy the spreadsheet URL and paste it here
      5. Type 'skip' to skip this project
      ```
      Extract spreadsheet ID from URL (between `/d/` and `/edit`); accept bare ID too; "skip" → no mapping (but context already saved in step 2.0 is kept). Verify access via `get_sheet_metadata`.

   b. **Add TestCases/Bugs sheets**: read `.redmine.project_contexts["<project_id>"].members` (per-project, from step 2.0) → call `create_test_sheet_structure(spreadsheet_id, title, member_names)`. Tool auto-skips existing sheets, applies UPPERCASE headers + dropdowns (TESTER/PRIORITY/STATUS/ASSIGNED_TO/LAST_TEST_RESULT), returns `created`/`skipped` lists — log both. The spreadsheet stays owned by the user (no re-share needed).

   c. **Save mapping**: append `{redmine_project_id, redmine_project_name, spreadsheet_id, spreadsheet_url, sheets, us_color_index: 0, us_id_counter: 1}` to the local `projects` array being built (don't write to disk yet — written in step 4 below). Also set `.redmine.project = {id, name, identifier}` to the first project user picked (singular field is now written).

4. **Write `.google-sheets`**: call `set_user_memory(key=".google-sheets", value=<data>)` to store in server-side memory. Exact schema in section 5.

5. **Verify**: read back via `get_user_memory(key=".google-sheets")` → confirm valid mapping.

6. **Report**:
   - Projects mapped: N (list with spreadsheet URLs)
   - Projects skipped: M (list)
   - Sheets created/skipped per project
   - Reminder: use `redmine init` again (refresh flow → section 3b) to add more projects later.

---

## 3. Refresh flow (`.redmine` already exists)

1. **Read existing data**:
   - **Tester**: call `get_user_memory(key=".redmine")` → get the existing data.
   - **Dev/Leader**: read the existing `.redmine` from git worktree root.
2. **Reuse the stored `project.id`** — do NOT re-ask which project. Just re-fetch project context using the stored ID.
3. **Re-fetch project context**:
   - **Dev/Leader**: re-fetch project context + priorities (step 5 of the init flow) and update with a fresh `fetched_at`, keeping the same schema.
   - **Tester**: re-fetch `projects[]` by calling `list_redmine_projects` again. For each existing `project_id` in `.redmine.project_contexts`, re-call `get_project_issue_context(project_id)` and overwrite the entry with a fresh per-project `fetched_at`. Do NOT touch root-level fields (tester files don't have them).
4. **Write updated data**:
   - **Tester**: call `set_user_memory(key=".redmine", value=<updated_data>)`.
   - **Dev/Leader**: overwrite the local file.
5. **Refresh `user_mappings` (dev/leader only)**: keep existing mappings whose `redmine_user_id` is still in the new `members` list; drop entries for members that no longer exist; do NOT re-ask for existing mappings.
6. **Refresh `member_rules` (leaders only)**: keep entries whose `redmine_user_id` still exists in the new `members` list, drop stale ones; do NOT re-ask every person's rules — only ask again if the user is a leader and explicitly wants to update them.
7. Verify and report as in init steps 10–11.
8. **If role = Tester → continue to section 3b (Google Sheets refresh)**.

### 3b. Refresh `.google-sheets`

Also triggered when user says: "thêm project mới vào google sheets", "add project to sheet", "map project với sheet".

1. **Read existing data**: call `get_user_memory(key=".google-sheets")` → get the existing data.
2. **Verify each mapped spreadsheet still exists** by reading its metadata. If a spreadsheet was deleted or access was revoked → warn the user and remove the mapping.
3. **Add new projects**: if `.redmine` has projects not yet in `.google-sheets` → for each new project:
   - Show project name + ID
   - **Fetch project context**: call `get_project_issue_context(project_id)` and save into `.redmine.project_contexts["<project_id>"]` (create new key). Same as init flow step 2.0 — never reuse another project's context.
   - Show context summary to user
   - Instruct user to create sheet and share with `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`
   - User pastes spreadsheet URL
   - Verify access via `get_sheet_metadata`
   - Call `create_test_sheet_structure(spreadsheet_id=<id>, title=<title>, member_names=[...])` to inject TestCases/Bugs sheets into the user's spreadsheet (no re-share needed). Use `member_names` from the freshly-fetched `project_contexts["<project_id>"].members`.
   - Add mapping to `.google-sheets` with `us_color_index: 0, us_id_counter: 1`
4. **Remove stale projects**: if a project in `.google-sheets` no longer exists in `.redmine` → remove the mapping.
5. **Sync sheet structure**: for each mapped spreadsheet, call `get_sheet_metadata` to verify "TestCases" and "Bugs" sheets exist → if missing, call `create_test_sheet_structure(spreadsheet_id=<id>, ...)` (it auto-skips sheets that already exist, safe to re-run).
6. Call `set_user_memory(key=".google-sheets", value=<updated_data>)` to store updated data with fresh `fetched_at`.

---

## 4. `.redmine` schema (exact)

```json
{
  "version": 1,
  "project": {"id": 12, "name": "Example Project", "identifier": "example-project", "created_on": "2026-01-15T08:30:00Z"},
  "projects": [
    {"id": 12, "name": "Example Project", "identifier": "example-project"},
    {"id": 45, "name": "Another Project", "identifier": "another-project"}
  ],
  "trackers": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Feature"}],
  "categories": [],
  "members": [{"id": 101, "user": {"id": 5, "name": "Jane Doe"}, "roles": [{"id": 4, "name": "Developer"}]}],
  "versions": [],
  "statuses": [{"id": 1, "name": "New", "is_closed": false}, {"id": 5, "name": "Closed", "is_closed": true}],
  "custom_fields": [],
  "required_custom_fields": [],
  "priorities": [{"id": 2, "name": "Normal"}, {"id": 3, "name": "High"}],
  "user_mappings": [
    {"github": "janedoe", "git_email": "jane@example.com", "redmine_user_id": 101, "redmine_name": "Jane Doe"}
  ],
  "member_rules": [
    {"redmine_user_id": 101, "redmine_name": "Jane Doe", "roles": ["backend"], "rules": ["luôn viết test trước khi code", "API cần OpenAPI spec trước khi implement"]}
  ],
  "fetched_at": "2026-01-15T08:30:00Z"
}
```

- `version`: `1`. Keep keys verbatim; empty lists as `[]`. `fetched_at` = ISO 8601 UTC.
- `project` (testers only, set lazily): the first project the user picks in §2b step 2. **Not present** for users who only ran init as dev/leader, and **not present** for testers who haven't picked a project yet. Schema: `{id, name, identifier}`.
- `projects` (testers only): `[{id, name, identifier}]` — used by QA skills. Set in §2a step 5b.
- `user_mappings` (dev/leader only): GitHub↔Redmine mapping. Optional — if absent, issue-workflow asks per author.
- `member_rules` (leaders only): per-member working rules as told by the user. Never invent rules.

### Per-project context (testers only)

For testers, `.redmine` also stores a `project_contexts` dict keyed by `project_id` (string). Each entry holds the full context fetched **lazily during Google Sheets setup** (section 2b step 2.0) — never at init time, and never shared between projects.

```json
{
  "project_contexts": {
    "12": {
      "project": {...},
      "trackers": [...],
      "categories": [...],
      "members": [...],
      "versions": [...],
      "statuses": [...],
      "custom_fields": [...],
      "required_custom_fields": [...],
      "priorities": [...],
      "fetched_at": "2026-09-01T00:00:00Z"
    },
    "45": {
      "project": {...},
      "trackers": [...],
      ...
      "fetched_at": "2026-09-01T00:00:00Z"
    }
  }
}
```

- Each `project_contexts["<project_id>"]` entry has its own `fetched_at` (per-project TTL).
- A project the tester has never set up will NOT have an entry — fetched on demand.
- Dev/leader `.redmine` files do NOT have this field.
- This is the **only** source of per-project trackers/priorities/members for QA skills — root-level fields like `trackers` are NOT present in tester files (would be misleading cross-project data).

---

## 5. `.google-sheets` schema

> **Testers only**: service account `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`

```json
{
  "projects": [
    {
      "redmine_project_id": 12,
      "redmine_project_name": "Example Project",
      "spreadsheet_id": "abc123XYZ",
      "spreadsheet_url": "https://docs.google.com/spreadsheets/d/abc123XYZ",
      "sheets": {
        "testcases": "TestCases",
        "bugs": "Bugs"
      },
      "us_color_index": 0,
      "us_id_counter": 1,
      "fetched_at": "2026-08-29T00:00:00Z"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `projects` | array | List of project-to-spreadsheet mappings |
| `redmine_project_id` | int | Redmine project ID |
| `redmine_project_name` | string | Redmine project name |
| `spreadsheet_id` | string | Google Spreadsheet ID |
| `spreadsheet_url` | string | Full spreadsheet URL |
| `sheets.testcases` | string | TestCases sheet tab name |
| `sheets.bugs` | string | Bugs sheet tab name |
| `us_color_index` | int | Current palette index (0-7) for US section header colors. Auto-incremented by `create_test_cases_on_sheet` tool. |
| `us_id_counter` | int | Next US ID number (e.g. 1 → US-1, 2 → US-2). Auto-incremented by `create_test_cases_on_sheet` tool. |
| `fetched_at` | string | ISO 8601 UTC timestamp of last refresh |

---

## 6. TTL policy

- Default TTL: **14 days**.
- Consumers (`redmine-issue-workflow`, Google Sheets skills) use the cache while `fetched_at` is within TTL, and warn the user + suggest `redmine init` when older.
- This skill never auto-refreshes in the middle of another task — refresh only when invoked.
- `.google-sheets` follows the same TTL as `.redmine` — refresh together.

---

## 7. Gotchas checklist

- [ ] **Per-project context is mandatory for Tester**: `.redmine.project_contexts["<project_id>"]` must be present for any project the tester actively uses. Missing entry → re-fetch on demand (call `get_project_issue_context` for that specific project). Never substitute another project's context.
- [ ] **No cross-project fallback**: if a tester asks QA skills to operate on a project not in `project_contexts`, the skill must live-fetch via `get_project_issue_context` — never read root-level `trackers`/`priorities`/`members` (tester files do not have them, and dev files' values belong to a different project).
