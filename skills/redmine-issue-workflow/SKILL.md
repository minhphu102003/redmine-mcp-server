---
name: redmine-issue-workflow
description: Use when creating or updating a Redmine issue from a GitHub commit or PR (also triggers on Vietnamese requests like "tạo issue/task trên Redmine từ commit", "tạo task", "create issue", "redmine", "cập nhật issue từ PR", "update issue from PR", "đọc commit rồi update issue", "commit rồi tạo task", "commit rồi tạo issue", "tạo issue sau khi push"). Covers gathering project context, verifying IDs against live data, mapping commit authors to Redmine members via `.redmine` `user_mappings` if available, applying the [FE/BE/Devops] naming rule, filling the standard English description template, and updating existing issues with changelog + time logging. Also runs a user-provided commit workflow first (via the {{COMMIT_WORKFLOW_PATH}} placeholder) when the user wants to commit and create/update an issue; without one, the commit pre-step is skipped. Use ONLY for Redmine issue creation/update from commit/repo context, not for general Redmine queries or wiki work.
---

# Redmine Issue Workflow

Create or update a Redmine issue from a GitHub commit/PR. **Generic across projects and agents** — no hardcoded project/member IDs, tool names, or instance values. Every ID, name and default below is an example/proposal: **the only source of truth is live Redmine data fetched in the current session**. Tools are described by **capability**, not name — use whatever the current agent provides (Redmine MCP tools, `gh` CLI, shell).

---

## 1. Core rules

1. **Live data first** — never trust memory, tool-description defaults, or this skill's examples. Exception: a `.redmine` cache at the git worktree root with `fetched_at` within **14 days** is a trusted fast path for its static lists (project, trackers, statuses, priorities, members, versions, categories, custom fields, `user_mappings`). Anything missing from the cache, or dynamic (allowed status transitions, parent-issue validity), must be fetched live. Stale cache → warn and suggest `redmine init`; no cache → live lookups (the `redmine-init` skill creates it).
2. **Verify before creating**: project, trackers, statuses, priorities, members, versions, categories.
3. **Issue content is English** (subject + description).
4. **Ask-before-create**: every required parameter is confirmed with the user — never silently chosen. For params with options from live data (tracker, status, priority, assignee), present the real list and let the user choose:
   - Use the agent's structured ask tool: opencode `question` / Claude Code `AskUserQuestion` / Codex `request_user_input` — plain text always works as fallback (and is required inside Claude Code subagents, where `AskUserQuestion` is unavailable).
   - Ask-tool limits: **1–4 questions per call**, **≤ 4 clickable options per question**. For longer live lists (trackers, members, priorities), embed the **full numbered list in the question text** and let the user type the number/name; optionally add 2–4 clickable shortcuts of the most likely picks on top — never drop valid options. Batch confirmations (e.g. tracker/status/priority in one call, assignee/dates in another).
   - If the ask tool is unavailable or the session is non-interactive (e.g. Codex `exec`, CI) → ask in plain text and wait; never proceed on guessed values.
   - Data that cannot be derived (e.g. commit author not mappable to a member) → **ask, never guess**.
5. **Description is auto-drafted by you**, not the user: fill the template (Section 7) fully from commit/PR/repo context. The user only reviews/edits the draft at confirmation.
6. **Dates are pre-proposed**: start = commit date, due = start + 1 day — present as defaults, the user adjusts if needed.
7. **Two modes**: **create** (new issue from commit/PR) and **update** (reflect PR/commit onto an existing issue). Mode = user-provided issue ID, or a subject-prefix match on an existing issue (Section 6).

---

## Pre-step — Commit workflow (optional, install-time placeholder)

Runs **before** Step 1 when the code is not yet committed/pushed (user says "commit rồi tạo task/issue", "tạo issue sau khi push"). If a commit workflow is configured, the agent commits, pushes and opens a PR first, then continues this skill with that PR/commit. If not configured, the pre-step is **skipped** — the skill then works on an existing commit/PR the user provides (or asks for one).

**Install-time config — the only value to fill in this skill:** `{{COMMIT_WORKFLOW_PATH}}` (path relative to the repo root of a commit workflow file):

| Value | Behavior |
|---|---|
| a real path (e.g. `.agents/workflows/commit-python.md`) | Read that file and follow it end-to-end |
| empty / still `{{...}}` / `none` (default) | **Skip** the pre-step; go straight to Step 1 |

Agent rule: a real existing path → read and follow that file. Otherwise (empty, still `{{...}}`, `none`, or missing file) → **skip the pre-step entirely — never invent generic commit steps**; if the user wants a combined commit+issue flow without a configured workflow, ask the user how they want to proceed. After a commit/PR exists, continue at Section 6 (update mode if a matching issue exists) or Section 5 (create mode), using the latest commit/PR as input.

---

## 2. Step 1 — Gather Redmine project context

0. **Cache check (fast path)**: if a `.redmine` file exists at the git worktree root, read it first — fresh (≤ 14 days) → use its lists and skip steps 1–4; stale → warn + suggest `redmine init`; ID missing from cache → fetch that one live; no file → run steps 1–4 (and suggest the `redmine-init` skill for future speed).
1. **List projects** → find the target project and its ID.
2. **Get project issue context** → trackers, members + roles, categories, versions, custom_fields, statuses, priorities.
3. **Statuses**: from step 2 when present; otherwise call a separate status-list tool.
4. **Priorities**: from step 2. **Never assume** `1=Low, 2=Normal, 3=High, 4=Urgent` — instances differ.

---

## 3. Step 2 — Read the GitHub repo

0. **Ask the user for the data source first**: base the issue on (a) a **PR/commit on the remote** (PR number or commit SHA), or (b) the **current uncommitted changes** in the local working tree?

   **(a) Remote PR/commit** — private repos return **404** via API/web → authenticate with the `gh` CLI: `gh auth status` (needs `repo` scope), `gh repo view <owner>/<repo>`, `gh repo clone <owner>/<repo> <temp-dir>` (temp/scratch dir, never the workspace), `git log --reverse` to read the first commits. Commit/PR details: `gh api "repos/<owner>/<repo>/commits/<sha>"` (files changed, author, date); `gh api "repos/<owner>/<repo>/pulls/<n>"` (title/URL/merged date).

   **(b) Local uncommitted changes** — `git status` + `git diff --stat` / `git diff` for the files changed and their content. There is **no commit subject** → draft one from the change or ask the user. Author = `git config user.name` / `user.email` (map it in Step 3).

- Gotcha: don't parse `gh api --paginate` output — clone and use `git log` instead.

---

## 4. Step 3 — Map commit data to the issue

### 4a. Commit author → Redmine member

- Remote PR/commit → author from the commit. Local uncommitted changes → author = `git config user.name` / `user.email`.
- `.redmine` `user_mappings` first: match by `github` login or `git_email` → use `redmine_user_id` directly, no ask needed.
- No mapping (or no `user_mappings` section) → match against the live `members` list.
- No confident match → **ask the user**.

### 4b. [FE/BE/Devops] prefix by files changed

| Files changed | Prefix |
|---|---|
| Backend code (API, backend services, backend tests, backend dependencies) | `[BE]` |
| Frontend code (UI, widgets, web assets) | `[FE]` |
| Infrastructure (Docker, nginx, CI/workflows, deployment scripts) | `[Devops]` |

Mixed changes → pick the dominant layer; ask the user if ambiguous.

### 4c. Issue naming defaults (all confirmed per Section 1)

- **subject** = `[FE/BE/Devops] <commit subject verbatim>` — English, no extra prefixes. (For uncommitted changes there is no commit subject → ask the user for a short English subject, or derive it from the diff.)
- **description** = your auto-drafted English template (Section 7) — never ask the user to write it.
- tracker **Feature**, status **New**, priority **Normal**, estimated_hours **8**, done_ratio **0** — confirm actual IDs from live data.
- dates pre-proposed (Section 1, rule 6); assignee = the mapped member (4a).

---

## 5. Step 4 — Create the issue

1. **Confirm** the full param plan per Section 1, rule 4: subject, your drafted description, tracker/status/priority/assignee (live options), pre-proposed dates, estimate, done_ratio. Apply any adjustment the user makes.
2. **Create** with all fields: `project_id, subject, description, tracker_id, priority_id, status_id, assigned_to_id, start_date, due_date, estimated_hours, done_ratio`.
3. **Verify the returned values** (priority/status names especially) — mismatch → update the issue with the correct value and a note explaining the change.
4. **Report**: issue ID, subject, project, tracker, status, assignee, priority, dates, estimate.

---

## 6. Step 5 — Update an existing issue from a PR/commit

Use when the user provides an existing issue ID, or an issue matches by subject prefix (e.g. `[FE] Add PDF parsing` matches a PR whose latest commit subject is `Add PDF parsing`). Read the **latest commit/PR only** — never full git history.

### 6a. Find the existing issue

1. User-provided ID → use it directly.
2. Else search by subject keyword (without the prefix): **one** match → use it; **multiple** → ask which one; **none** → ask for the issue ID.

### 6b. Read the latest PR/commit

- **PR provided**: `gh api "repos/<owner>/<repo>/pulls/<n>"` (title, body, state, merged date, files changed) + `pulls/<n>/commits` (use only the **latest** commit for subject/date).
- **Commit SHA**: `gh api .../commits/<sha>`; or locally `git log -1 --format="%s%n%b%n%an <%ae>" <sha>` + `git diff <sha>~1 <sha> --stat`.
- **Nothing given, local repo**: `git log -1 --format="%s%n%b%n%an <%ae>"` + `git diff HEAD~1 HEAD --stat` (latest commit on the current branch). If the working tree has uncommitted changes, **ask the user** whether to base the update on the latest commit or on those changes (`git status` + `git diff`).
- Extract: commit subject (or drafted subject), files changed, PR/commit state, date, author.

### 6c. Proposed update actions (confirm with the user in 6e)

| Action | Rule |
|---|---|
| **Status** | PR merged → `Done`/`Closed` (confirm live ID); open → `In Progress`; closed-not-merged → `Closed` or `Rejected` (ask) |
| **done_ratio** | merged → `100`; open → keep current or proportional (ask); closed-not-merged → `0` |
| **Description** | **Append** a changelog entry (6d) — never replace the existing description |
| **Time log** | merged/final commit → log `estimated_hours` of the issue (or the PR estimate); `spent_on` = latest commit date; confirm with the user |

### 6d. Changelog entry format

Append the block (before the last line if it ends with `PR: <url>`, otherwise at the end); if a `## Changelog` section already exists, append a new bullet under it instead of duplicating the header:

```markdown
## Changelog
- **<date>** — PR #<n> merged by <author>: <commit subject>
  - Files changed: <file1>, <file2>, ...
  - <one-line summary of what changed>
```

### 6e. Confirm with the user

Present: issue ID + current subject, proposed status (live options), proposed done_ratio, proposed time log (hours, date), changelog entry preview — per Section 1, rule 4 (batch into 1–4 questions per call; apply adjustments and proceed).

### 6f. Execute the update

1. Update the issue with the confirmed fields (`status_id`, `done_ratio`, `description` with appended changelog).
2. If time logging is confirmed → create the time entry (`issue_id`, `hours`, `activity_id`, `spent_on`, `comments`).
3. Invalid status transition → fetch allowed statuses and suggest the nearest valid one.
4. Report: issue ID, subject, updated status, done_ratio, time logged (if any), changelog entry appended.

---

## 7. Description template (English, fixed format)

You (the agent) draft the entire description from the commit/PR/repo context (actual code, files, changes); the user only reviews/edits it at confirmation (Section 5, step 1). Fill all 8 sections fully in English:

```markdown
## Context
- Describe the problem/business context this change solves.

## User story
- **As a** [role — e.g. system admin / ingest pipeline]
- **I want** [capability — e.g. upload PDF/DOCX and get Markdown via API]
- **So that** [business value — e.g. documents can be chunked, embedded, and loaded into the knowledge base]

## Scope
- In scope:
  - [item 1]
  - [item 2]
- Out of scope:
  - [item 1]
  - [item 2]

## Proposed solution
- Describe the high-level implementation approach.

## Related data and integrations
- API/Service: [e.g. parsing service, endpoint]
- Schema/Fields: [relevant request/response fields]
- Constraints: [e.g. supported formats, limitations]

## Acceptance criteria
- [ ] AC1: [verifiable outcome]
- [ ] AC2: [verifiable outcome]
- [ ] AC3: [verifiable outcome]

## Success measurement
- KPI/metrics: [e.g. 100% test pass rate]

PR: [GitHub PR URL]
```

Rules:
- User story uses exactly **As a → I want → So that**, each phrase **bolded**.
- Keep all section headers verbatim; fill only the bullet content.
- Append the PR link on the last line.
- Reference actual code/files from the commit in Context / Proposed solution.

---

## 8. Gotchas

- [ ] Priority IDs differ per instance — never assume an ID→name mapping (id 3 was once "High" where a default claimed "Normal").
- [ ] Private repos → `gh` CLI only (API/web return 404).
- [ ] Don't parse `gh api --paginate` output; clone + `git log` instead.
- [ ] `get_project_issue_context` may lack a `statuses` section on older servers → call a separate status-list tool too.
- [ ] Update mode: append the changelog bullet under the existing `## Changelog` header — never create a duplicate header or replace the description.
- [ ] Update mode: invalid status transition → fetch allowed statuses and suggest the nearest valid one.
- [ ] Pre-step: `{{COMMIT_WORKFLOW_PATH}}` — real existing path → follow that file; otherwise (empty/`{{...}}`/`none`/missing file) → skip the pre-step, never invent generic commit steps.
- [ ] Ask the user the data source first (remote PR/commit vs current uncommitted changes) — never assume which one to read.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
