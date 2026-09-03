---
name: redmine-issue-workflow
description: Use when creating or updating a Redmine issue (also triggers on Vietnamese: "tạo issue/task trên Redmine", "tạo task", "create issue", "cập nhật issue", "update issue", "đọc commit rồi update issue", "tạo issue từ code"). Covers gathering project context, verifying IDs against live data, mapping commit authors to Redmine members via `.redmine` `user_mappings`, applying the [Module] [Role] naming rule, choosing tracker by change type (Bug for fixes, Feature otherwise), checking for duplicates before creating, filling the standard English description template, and updating existing issues by comparing code context with current issue fields. Use ONLY for Redmine issue creation/update, not for general Redmine queries or wiki work.
---

# Redmine Issue Workflow

Create or update a Redmine issue from a description, uncommitted code changes, a GitHub PR, or a specific commit. **Generic across projects and agents** — no hardcoded project/member IDs, tool names, or instance values. The only source of truth is live Redmine data fetched in the current session. Tools are described by **capability**, not name.

---

## 1. Core rules

1. **Live data first** — never trust memory or this skill's examples. Exception: a fresh `.redmine` cache (≤ 14 days) is a trusted fast path for static lists. Anything missing from cache or dynamic (allowed status transitions, parent-issue validity) must be fetched live. Stale cache → warn + suggest `redmine init`; no cache → live lookups.
2. **Verify before creating/updating**: project, trackers, statuses, priorities, members, versions, categories.
3. **Issue content is English** (subject + description).
4. **Ask-before-act**: every required parameter is confirmed with the user — never silently chosen. Use the agent's structured ask tool; plain text as fallback. Ask-tool limits: 1–4 questions per call, ≤ 4 clickable options per question. For longer lists, embed full numbered list in question text. Batch confirmations when possible. This rule applies to all "default" fields below (status, priority, tracker, assignee, dates, category, version, custom fields, estimated_hours, done_ratio).
5. **Description is auto-drafted by you**, not the user: fill the template (Step 6) fully from context. The user only reviews/edits at confirmation.
6. **Dates are pre-proposed**: start = commit date or today, due = start + 1 day — present as defaults, user adjusts.
7. **Two modes**: **create** (new issue) and **update** (existing issue). User chooses first.
8. **Subject format**: `[<module>] [<role>] <title>` — module and role chosen by the user, title comes from input.
9. **"Task này đang làm gì?"** — this question appears in both create and update flows to gather context about the work.
10. After moving/editing this skill file, remind the user to **restart the agent** for the skill to load.

---

## Step 0 — Create hay Update?

Hỏi user:

**"Bạn muốn tạo issue mới hay cập nhật issue có sẵn?"**
1. **Tạo issue mới** (create) → Step 1
2. **Cập nhật issue** (update) → Step 5

---

## Step 1 — Gather Redmine project context

1. **Cache check (fast path)**: if `.redmine` exists at git worktree root and fresh (≤ 14 days) → use its lists. Stale → warn + suggest `redmine init`. Missing ID → fetch live. No file → fetch all live.
2. **List projects** → find target project and its ID.
3. **Get project issue context** → trackers, members + roles, categories, versions, custom_fields, statuses, priorities.
4. **Statuses**: from context when present; otherwise call separate status-list tool.
5. **Priorities**: from context. **Never assume** `1=Low, 2=Normal, 3=High, 4=Urgent` — instances differ.

---

## Step 2 — Task này đang làm gì?

Ask the user for the context of the work:

**"Task này đang làm gì?"**

| # | Mode | Input | Agent |
|---|------|-------|-------|
| 1 | **describe** | User gõ mô tả tay | Dùng trực tiếp làm title/description |
| 2 | **changes** | Code chưa commit | `git status` + `git diff --stat` + `git diff` |
| 3 | **PR** | PR trên GitHub | User paste link/number → `gh api pulls/<n>` |
| 4 | **commit** | Commit cụ thể | User paste hash → `git show <hash>` |

### Mode: describe
- User cung cấp: mô tả task (title và/hoặc description)
- Agent: draft title nếu user chỉ cung description

### Mode: changes
- User cung cấp: không gì (dùng working tree hiện tại)
- Agent: `git status` + `git diff --stat` + `git diff`
- Draft title từ files changed và nội dung diff
- Author: `git config user.name` / `user.email`

### Mode: PR
- User cung cấp: PR number hoặc URL
- Agent: `gh api "repos/<owner>/<repo>/pulls/<n>"` → title, body, state, merged date, files changed, author
- Also: `pulls/<n>/commits` → latest commit for subject/date

### Mode: commit
- User cung cấp: commit hash
- Agent: `git show <hash>` hoặc `gh api repos/.../commits/<sha>` → subject, files changed, author, date
- Local: `git log -1 --format="%s%n%b%n%an <%ae>" <sha>` + `git diff <sha>~1 <sha> --stat`

---

## Step 3 — Map data to issue

### 3a. Author → Redmine member

- Read `.redmine` `user_mappings` (set up by `redmine-init`); match by `github` login or `git_email` → use `redmine_user_id` directly.
- No mapping or no confident match → **ask the user**.

### 3b. Ask user — `[Module] [Role]`

Ask two questions:

1. **Module/Feature name**: what module does this change belong to? (e.g. `Auth`, `Payment`, `Dashboard`, `Chat`)
2. **Role**: what layer?
   - `Backend`
   - `Frontend`
   - `Mobile`
   - `Devops`
   - `Other` — gõ tay

The user chooses both. Never auto-detect from files changed.

### 3c. Title from input

- **describe mode**: title do user cung cấp, hoặc agent draft từ description
- **changes mode**: draft title từ git diff (files + changes summary)
- **PR mode**: PR title
- **commit mode**: commit subject
- **Meaningless title** (e.g. "fix", "update", "wip") → ask user to clarify or provide title

### 3d. Subject format

**subject** = `[<module>] [<role>] <title>` — e.g. `[Auth] [Backend] Fix login timeout`

### 3e. Other issue defaults (all confirmed per Rule 4)
- **description** = auto-drafted English template (Step 6) — never ask user to write it.
- **tracker by change type**: commit/PR fixes a bug → **Bug**; otherwise → **Feature**; ambiguous → ask.
- status **New**, priority **Normal**, estimated_hours **8**, done_ratio **0** — confirm actual IDs from live data.
- **custom fields**: if project has required custom fields → ask user at confirmation; otherwise skip.
- **category** (optional): only ask if project/cache has categories (non-empty list). Best-match from context → propose. No clear match → propose none.
- **target version** (optional): only ask if project/cache has open versions. List open versions, let user pick or skip.
- dates pre-proposed (Rule 6); assignee = mapped member (3a).

---

## Step 4 — Create the issue

1. **Check for duplicate**: search target project by subject keyword (without prefix) — one match → ask user whether to update instead; multiple → ask which; none → proceed.
2. **Confirm** full param plan per Rule 4: subject, drafted description, tracker/status/priority/assignee, optional fields (category, version, custom fields). Batch confirmations when possible.
3. **Create** with all fields: `project_id, subject, description, tracker_id, priority_id, status_id, assigned_to_id, start_date, due_date, estimated_hours, done_ratio` plus optional `category_id`, `fixed_version_id`.
4. **Verify returned values** — mismatch → update with correct value + note.
5. **Read-only server** (`REDMINE_MCP_READ_ONLY`): blocked → present full draft for manual creation.
6. **Report**: issue ID, subject, project, tracker, status, assignee, priority, dates, estimate, category, target version.

---

## Step 5 — Update issue

### 5a. Find issue

1. Ask user: **"Issue ID hoặc Redmine link?"**
2. Read issue info: subject, description, status, assignee, tracker, priority, estimated_hours, done_ratio, category, fixed_version, custom_fields.

### 5b. Gather Redmine context

Same as Step 1 — use cache or fetch live for statuses, priorities, members.

### 5c. Task này đang làm gì?

> Reuse Step 2 — same 4 modes (describe/changes/PR/commit). Ask: "Task này đang làm gì? Cung cấp context để so sánh với issue hiện tại."

### 5d. Diff context vs current issue + propose changes

| Source | Proposed changes |
|--------|-----------------|
| PR merged | Status → Done, done_ratio → 100 |
| PR open | Status → In Progress |
| PR closed (not merged) | Status → Closed/Rejected (ask) |
| Commit | Append changelog entry to description |
| Changes | Update description with diff summary |
| Describe | Update fields theo user mô tả |

Show this diff table for transparency:

```markdown
| Field | Issue hiện tại | Context (code/PR/commit) | Khác? |
|-------|---------------|--------------------------|-------|
| Subject | [Module] [Role] ... | PR title / commit subject | ✅/❌ |
| Status | Open | PR merged → Done | ❌ |
| Assignee | John Doe | Jane Smith (commit author) | ❌ |
| Files changed | — | file1.py, file2.py | ℹ️ |
| Description | (8 sections) | (PR body / diff summary) | ℹ️ |
```

### 5e. Confirm

Present: issue ID + current info, proposed changes, diff summary — per Rule 4. Hỏi user muốn update field nào (subject, description, status/assignee/priority, time log, category/version).

### 5f. Execute update

1. Update issue with confirmed fields (`status_id`, `done_ratio`, `description`, `assigned_to_id`, etc.).
2. If time logging confirmed → get valid `activity_id` first, then create time entry.
3. **Changelog entry format** (append to description, don't replace):

```markdown
## Changelog
- **<date>** — PR #<n> merged by <author>: <commit subject>
  - Files changed: <file1>, <file2>, ...
  - <one-line summary>
```

4. **Read-only server**: blocked → present full change list for manual application.
5. **Invalid status transition** → fetch allowed statuses, suggest nearest valid one.
6. **Report**: issue ID, subject, updated fields, time logged (if any), changelog entry.

---

## Step 6 — Description template (English, fixed format)

Agent drafts the entire description from context; user only reviews/edits at confirmation. Fill all 8 sections fully in English:

```markdown
## 1. Context
- Describe the problem/business context this change solves.

## 2. User story
- **As a** [role — e.g. system admin / ingest pipeline]
- **I want** [capability — e.g. upload PDF/DOCX and get Markdown via API]
- **So that** [business value — e.g. documents can be chunked, embedded, and loaded into the knowledge base]

## 3. Scope
- In scope:
  - [item 1]
  - [item 2]
- Out of scope:
  - [item 1]
  - [item 2]

## 4. Proposed solution
- Describe the high-level implementation approach.

## 5. Related data and integrations
- API/Service: [e.g. parsing service, endpoint]
- Schema/Fields: [relevant request/response fields]
- Constraints: [e.g. supported formats, limitations]

## 6. Acceptance criteria
- [ ] AC1: [verifiable outcome]
- [ ] AC2: [verifiable outcome]
- [ ] AC3: [verifiable outcome]

## 7. Success measurement
- KPI/metrics: [e.g. 100% test pass rate]

## 9. PR
PR: [GitHub PR URL]
```

> Headers verbatim (1-7, 9). User story uses bolded **As a / I want / So that**. Append PR link as section 9; no PR yet → `Commit: <sha>` or `Commit: working-tree changes`. Reference actual code/files in section 1 / 4.
