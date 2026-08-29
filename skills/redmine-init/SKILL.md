---
name: redmine-init
description: Use when the user asks to initialize or refresh the Redmine project mapping for the current repository, e.g. "redmine init", "khởi tạo redmine", "map repo này với project redmine", "tạo file .redmine", "refresh redmine context", "redmine context bị cũ". Creates or refreshes the `.redmine` JSON cache file, storing the project ID and the static ID lists (trackers, statuses, priorities, members, versions, categories, custom fields) with a `fetched_at` timestamp, so issue-creation skills can create tasks without re-fetching every value. For testers: files are stored in `~/.redmine-mcp/` (persistent across sessions); for devs: files are stored at the git worktree root. Use ONLY for init/refresh of the cache, NOT for creating issues, logging time, or wiki work.
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
- **Role detection**: the first step asks whether the user is a **dev** or **tester** (or both). This determines the init flow: dev → `.redmine` only; tester → `.redmine` + `.google-sheets`.
- **Testers manage multiple projects**: each project gets its own spreadsheet mapping in `.google-sheets`. A tester can have project A with spreadsheet X and project B with spreadsheet Y.

---

## 2. Init flow (no `.redmine` file yet)

### Step 0 — Detect role

Ask the user (structured ask tool, plain text as fallback):

**"Bạn là ai trong dự án này?"**
1. **Developer** — chỉ cần init `.redmine` (Redmine cache)
2. **Tester** — cần init `.redmine` + `.google-sheets` (Google Sheets memory)
3. **Leader** — init `.redmine` + hỏi mapping GitHub + hỏi member working rules
4. **Cả hai** — init cả hai file

| Role | Files created | Flow |
|---|---|---|
| Developer | `.redmine` | Section 2a (Dev flow) |
| Tester | `.redmine` + `.google-sheets` | Section 2a + 2b (Dev flow + Tester flow) |
| Leader | `.redmine` | Section 2a (Dev flow) + Step 6 + Step 7 |
| Cả hai | `.redmine` + `.google-sheets` | Section 2a + 2b |

**Role-based behavior:**
| Feature | Developer | Tester | Leader |
|---|---|---|---|
| GitHub↔Redmine mapping | ✅ Asked | ❌ Skipped | ✅ Asked |
| Member working rules | ❌ Skipped | ❌ Skipped | ✅ Asked |
| `.google-sheets` | ❌ Not created | ✅ Created | ❌ Not created |
| **Storage path** | Git worktree root | MCP memory tools (server-side) | Git worktree root |

### 2a. Dev flow — Init `.redmine`

1. **Locate the storage path**:
   - **Tester role**: use MCP memory tools (`set_user_memory`). No local file path needed.
   - **Dev/Leader role**: run `git rev-parse --show-toplevel` → use that root. If not a git repo → ask the user where to place the file.
2. **Check for an existing file**: if `.redmine` already exists at the storage path → follow the refresh flow (section 3) instead.
3. **List projects**: call the list-projects capability (e.g. `redmine_list_redmine_projects`) → returns `id`, `name`, `identifier`, `description`, `created_on`.
4. **Ask the user to choose — full list always visible (full-list rule)**: NEVER ask with only a couple of options, and NEVER guess. Before calling any ask tool, render the **complete** project list to the user in the chat message as a markdown table — every single row, no truncation, no capping:
   ```markdown
   | # | ID | Project | Identifier |
   |---|----|---------|------------|
   | 1 | 313 | [AI] Chatbot Tuyển Sinh | ai-chatbot-tuyen-sinh |
   | 2 | 156 | [MobileApp] CLICK-Ed app platform | du-an-qa-app |
   | ... | ... | ... | ... |
   ```
   Then ask "repo này tương ứng với project Redmine nào?" with the agent's structured ask tool (opencode `question`, opencode `AskUserQuestion`, Codex `request_user_input`; plain text as fallback). Rules for the ask:
   - The question text must **repeat the full list as a numbered list** (ask tools accept custom/free-text answers — the user types the number or name from the table).
   - Always include a catch-all custom/free-text option like "Khác — gõ số hoặc tên từ bảng trên".
   - Add at most 2–4 clickable shortcuts of the most likely projects **on top of** the full list — they are conveniences, never a replacement; users must always be able to see and choose ALL entries.
   - Very long list (> ~30 rows): still render the full table, then ask the user to narrow by keyword in a follow-up — never drop rows silently.
5. **Fetch project context**: call the project-context capability (e.g. `redmine_get_project_issue_context`, project_id) → returns project, trackers, categories, members (with roles), versions, statuses (`is_closed`), **priorities**, custom_fields, required_custom_fields. The `priorities` section is the **complete** list (e.g. `{"id": 2, "name": "Normal"}`); Redmine has no separate "list priorities" endpoint, the context tool provides it. This caches only the **static option list** (the dropdown of values), never any issue's current priority — per-issue priority state changes hourly and is always fetched live.
5b. **For testers only — save all projects**: if role = Tester or Both, the `projects` list (from step 3) is saved into `.redmine` as `projects` array. This allows QA skills to list all projects when setting up Google Sheets, without calling `list_redmine_projects` again. Devs do NOT get this field — they only need the single `project`.
6. **Map GitHub account ↔ Redmine member (dev/leader only)**: **SKIP this step if role = Tester.** Testers don't need GitHub↔Redmine mapping — they work in Google Sheets, not Git commits.
   1. Detect GitHub side: run `gh api user` (requires `gh` CLI, installed first per the issue-workflow skill's prerequisites) → returns `login`, `name`, `email`. If `gh` is unavailable, fall back to `git config user.name` + `git config user.email`.
   2. Match the detected GitHub identity against the `members` list from step 5. Match by **name** (case-insensitive) first, then by **email** if name doesn't match.
   3. If exactly **one** confident match → confirm with the user via the structured ask tool: "GitHub account `janedoe` (Jane Doe) maps to Redmine member nào?" with the matched member pre-selected and 1–3 other likely members as clickable shortcuts.
   4. If **no match** or **multiple matches** → apply the **full-list rule** from step 4: render the complete `members` list as a markdown table (| # | ID | Name | Roles |) in the chat message — all rows visible, no truncation — then present the full list in the question text of the structured ask tool (user types number or name; ≤4 clickable shortcuts of the most likely picks on top, never instead of the full list).
   5. **Optional — map additional committers** (ask only if the user seems interested; do NOT exhaustively map every committer to save tokens): run `git shortlog -sne --since="6 months"` to get a compact list of recent committers (1 line each: `count  Name <email>`). Ask the user: "Có muốn map thêm committer nào không?" — if yes, present the shortlist and let them pick entries to map (same ask pattern). Default: **only the current user** (tiết kiệm token).
   6. Build the `user_mappings` array: each entry `{"github": "<login>", "git_email": "<email>", "redmine_user_id": <id>, "redmine_name": "<name>"}`. Strip wrapper tags from all names.
7. **Collect member working leaders only**: **SKIP this step if role ≠ Leader.** Only team leaders/tech leads need to provide working rules for team members. For each member mapped in step 6, ask the user for that person's working rules — "Người này làm role gì và có rule/đặc thù riêng khi làm việc không? (gõ 'bỏ qua' để skip)". Prompt with the researched catalog below as a reminder of what rule areas exist (role/stack, required tests, code-review expectations, AI-assistant usage policy, reporting cadence, definition of done). The user answers, skips, or says "bỏ qua" per member — **never invent a rule**; store only what the user explicitly said, as short verbatim bullets (Vietnamese OK). Non-leaders skip this entirely — no rules are collected.
8. **Strip wrapper tags**: remove every `<insecure-content-...>` and `</insecure-content-...>` marker from names.
9. **Write `.redmine`**:
   - **Tester**: call `set_user_memory(key=".redmine", value=<data>)` to store in server-side memory.
   - **Dev/Leader**: write a single JSON file at git worktree root, exact schema in section 4, `fetched_at` = current UTC timestamp (ISO 8601, e.g. `2026-08-06T00:00:00Z`).
10. **Verify**:
    - **Tester**: call `get_user_memory(key=".redmine")` → confirm it returns valid data with no wrapper tags and `fetched_at` is set.
    - **Dev/Leader**: read the file back; confirm it parses as valid JSON, contains no wrapper tags, and `fetched_at` is set.
11. **Report**: project id/name/identifier, counts of trackers/members/statuses/priorities, the `user_mappings` count (dev/leader only), the `member_rules` count (leaders only), the storage location (file path for dev, server memory for tester), and the reminder: re-run `redmine init` later to refresh; the file is safe to commit (no secrets, dev only).
12. **If role = Tester or Both → continue to section 2b (Google Sheets memory setup)**.

### 2b. Tester flow — Init `.google-sheets`

After `.redmine` is created, set up Google Sheets memory for test management.

**Service Account**: `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`
The MCP server authenticates with this service account. Users create their own Google Sheet and share it with this email (Editor permission).

1. **Check existing `.google-sheets`**: call `get_user_memory(key=".google-sheets")` → if data exists, follow the refresh flow (section 3b) instead.
2. **Ask per project**: iterate over ALL projects from `.redmine` (full-list rule). For each project:

   **"Project '<project_name>' (ID: <id>) — setup Google Sheet:"**
   ```
   1. Go to https://sheets.new → create a new spreadsheet
   2. Name it: '<project_name> - QA Test Management' (or your preferred name)
   3. Click Share → paste: redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com → Editor → Send
   4. Copy the spreadsheet URL and paste it here
   5. Type 'skip' to skip this project
   ```

   Each project gets its own spreadsheet mapping. The user creates and shares one sheet per project.

3. **Parse the user's response per project**:
   - Extract spreadsheet ID from the URL (part between `/d/` and `/edit`)
   - If user pastes just the ID, use it directly
   - If "skip" → no mapping for this project
   - Verify access by calling `get_sheet_metadata` MCP tool with the spreadsheet_id

4. **Auto-create sheet structure**:
   - Call `create_test_sheet_structure` MCP tool with:
     - `title`: spreadsheet title
     - `member_names`: list of member names from `.redmine` members
   - Tool automatically:
     - Creates "TestCases" and "Bugs" sheets with UPPERCASE headers
     - Applies data validation dropdowns:
       - TESTER (col G) → member names
       - LAST_TEST_RESULT (col I) → Pass/Fail/Not Tested
       - PRIORITY (col E) → High/Medium/Low
       - STATUS (col F) → 10 statuses
       - ASSIGNED_TO (col G) → member names
   - Skips sheets that already have data

5. **Write `.google-sheets`**: call `set_user_memory(key=".google-sheets", value=<data>)` to store in server-side memory. Exact schema in section 5.
6. **Verify**: read the file back; confirm it parses as valid JSON.
7. **Report**: project-sheet mappings, sheet URLs, created sheets.

### Member rules catalog (leaders only)

> **Leaders**: see [member-rules-catalog.md](./member-rules-catalog.md) for the full role-by-rule-area table. Ask the user which apply per member; never assume.

---

## 3. Refresh flow (`.redmine` already exists)

1. **Read existing data**:
   - **Tester**: call `get_user_memory(key=".redmine")` → get the existing data.
   - **Dev/Leader**: read the existing `.redmine` from git worktree root.
2. **Reuse the stored `project.id`** — do NOT re-ask which project. Just re-fetch project context using the stored ID.
3. Re-fetch project context + priorities (step 5 of the init flow) and update with a fresh `fetched_at`, keeping the same schema.
4. **Write updated data**:
   - **Tester**: call `set_user_memory(key=".redmine", value=<updated_data>)`.
   - **Dev/Leader**: overwrite the local file.
4. **Refresh `user_mappings` (dev/leader only, skip for testers)**: keep existing mappings whose `redmine_user_id` is still in the new `members` list; drop entries for members that no longer exist; do NOT re-ask for existing mappings.
5. **Refresh `member_rules` (leaders only, skip for non-leaders)**: keep entries whose `redmine_user_id` still exists in the new `members` list, drop stale ones; do NOT re-ask every person's rules — only ask again if the user is a leader and explicitly wants to update them.
6. Verify and report as in init steps 10–11.
7. **If role = Tester or Both → continue to section 3b (Google Sheets refresh)**.

### 3b. Refresh `.google-sheets`

Also triggered when user says: "thêm project mới vào google sheets", "add project to sheet", "map project với sheet".

1. **Read existing data**: call `get_user_memory(key=".google-sheets")` → get the existing data.
2. **Verify each mapped spreadsheet still exists** by reading its metadata. If a spreadsheet was deleted or access was revoked → warn the user and remove the mapping.
3. **Add new projects**: if `.redmine` has projects not yet in `.google-sheets` → for each new project:
   - Show project name + ID
   - Instruct user to create sheet and share with `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`
   - User pastes spreadsheet URL
   - Verify access + sheet structure
   - Add mapping to `.google-sheets`
4. **Remove stale projects**: if a project in `.google-sheets` no longer exists in `.redmine` → remove the mapping.
5. **Sync sheet structure**: for each mapped spreadsheet, verify "TestCases" and "Bugs" sheets exist → if not, ask whether to create them.
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
- `project`: the main project this repo maps to (always present, singular).
- `projects` (testers only): `[{id, name, identifier}]` — used by QA skills.
- `user_mappings` (dev/leader only): GitHub↔Redmine mapping. Optional — if absent, issue-workflow asks per author.
- `member_rules` (leaders only): per-member working rules as told by the user. Never invent rules.

---

## 5. `.google-sheets` schema

> **Testers only**: see [google-sheets-schema.md](./google-sheets-schema.md) for the full schema with field definitions. Service account: `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`

---

## 6. TTL policy

- Default TTL: **14 days**.
- Consumers (`redmine-issue-workflow`, Google Sheets skills) use the cache while `fetched_at` is within TTL, and warn the user + suggest `redmine init` when older.
- This skill never auto-refreshes in the middle of another task — refresh only when invoked.
- `.google-sheets` follows the same TTL as `.redmine` — refresh together.

---

## 7. Gotchas checklist

- [ ] **Memory access**: Tester → MCP memory tools (`set_user_memory`/`get_user_memory`), Dev/Leader → local file at git worktree root. Not a git repo and not tester → ask the user.
- [ ] `user_mappings` is optional — if absent, the issue-workflow skill falls back to asking the user for each author. Only for dev/leader (testers skip this step entirely).
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / opencode) for the skill to load.
