---
name: redmine-issue-workflow
description: Use when creating a Redmine issue from a GitHub commit or task (also triggers on Vietnamese requests like "tạo issue/task trên Redmine từ commit", "tạo task", "create issue", "redmine"). Covers gathering project context, verifying IDs against live data, mapping commit authors to Redmine members via `.redmine` `user_mappings` if available, applying the [FE/BE/Devops] naming rule, and filling the standard English description template. Use ONLY for Redmine issue creation from commit/repo context, not for general Redmine queries or wiki work.
---

# Redmine Issue Workflow

This skill documents the exact workflow to create a Redmine issue from a GitHub commit. It is **generic across projects and agents** — no hardcoded project IDs, member IDs, tool names, or instance-specific values.

**IMPORTANT:** Every ID, name, and value in this skill is an example or a default proposal. The only source of truth is the live data fetched from Redmine in the current session. Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides for that capability (e.g. Redmine MCP tools, `gh` CLI, shell).

---

## 1. Core principles

- **Never trust memory, tool-description defaults, or this skill's examples** — always fetch live data from Redmine first. Values change per project, per instance, and over time.
- **Exception — the `.redmine` cache file**: if a `.redmine` file exists at the git worktree root and its `fetched_at` is within **14 days**, its static ID lists (project, trackers, statuses, priorities, members, versions, categories, custom fields) are a trusted fast path (see Step 1). Live verification is still required for dynamic state: allowed status transitions, parent-issue validity, and any ID that is missing from the cache.
- **Always verify before creating**: project, trackers, statuses, priorities, members, versions, categories.
- Issue content (subject + description) is written in **English**.
- The workflow below applies when the user asks to "tạo issue/task từ commit", "create issue from commit", or hands you a GitHub commit + Redmine project.

### Ask-before-create rule

- **Every required parameter must be asked/confirmed with the user** — never silently pick values (subject, description, tracker, status, priority, assignee, start/due date, estimate, done_ratio).
- **The description is auto-drafted by you, not by the user**: fill the English template (Section 6) entirely from the commit/PR/repo context (actual code, files, changes). The user never writes it from scratch — they only review/edit the draft shown in the confirmation step.
- **start_date/due_date are pre-proposed**: start = the commit date, due = start + 1 day. Present them as defaults in the confirmation — the user can adjust, they never have to invent them.
- If the parameter has **options from live data** (tracker list, status list, priority list, member list), present the available options to the user and ask them to choose via the agent's structured ask/choice tool, with the real options fetched from Redmine:
  - opencode → `question` tool
  - Claude Code → `AskUserQuestion` tool
  - Codex CLI → `request_user_input` tool
  - Any other agent (or when no ask tool exists) → ask in **plain text** (always works)
- Structured ask tools share tight limits: **1–4 questions per call** and **≤ 4 clickable options per question**. For longer live lists (trackers, members, priorities), do NOT chunk or truncate them — embed the **full numbered list in the question text** (e.g. "Tracker? 1. Bug, 2. Feature, 3. Support, 4. Common, 5. Testing Task — type the number or name") and let the user answer by typing (opencode `question` custom input, Claude Code `Other`, Codex freeform); optionally add 2–4 clickable shortcuts of the most likely picks on top. Never silently drop valid options.
- Claude Code's `AskUserQuestion` is **unavailable inside subagents** — if you are running as a subagent, ask via plain text or return to the main agent to ask.
- Defaults proposed in this skill (tracker Feature, status New, estimate 8h, priority Normal, dates from commit) are **proposals**, not final values — present them, get explicit confirmation, then create.
- Unknown data that cannot be derived (e.g. commit author not in the member list) → always ask, never guess.

---

## 2. Step 1 — Gather Redmine project context

Use the agent's Redmine tools (capabilities in parentheses — names may differ across agents):

0. **Cache check (fast path)**: if a `.redmine` file exists at the git worktree root of the current repo, **read it first**:
    - `fetched_at` within 14 days → use `project`, `trackers`, `statuses`, `priorities`, `members`, `versions`, `categories`, `custom_fields`, **`user_mappings`** from the cache. **Skip steps 1–4 below** — no live calls needed for these lists.
    - `fetched_at` older than 14 days → warn the user and suggest running `redmine init` to refresh; ask whether to proceed with live data.
   - Any ID you need that is **not** in the cache (e.g. a rarely-used priority) → fetch live data for that item only — never invent values.
   - No `.redmine` file → proceed with the live steps below. (The `redmine-init` skill creates the file; suggest it to the user for future speed.)
1. **List projects** (e.g. `redmine_list_redmine_projects`) → find the target project and its ID.
2. **Get project issue context** (e.g. `redmine_get_project_issue_context`, project_id) → returns **trackers, members + roles, categories, versions, custom_fields, statuses and priorities** (recent versions of redmine-mcp-server include statuses and priorities in the response).
3. **Statuses**: use the `statuses` section from step 2 when present (valid statuses, e.g. `New`, `In Progress`, `Done`, `Closed` — IDs vary per instance). If the response has **no** `statuses` section, call a separate status-list capability (e.g. `redmine_list_redmine_issue_statuses`).
4. **Priorities**: use the `priorities` section from step 2 (valid priorities, e.g. `Normal`, `High` — IDs vary per instance). **Never assume** `1=Low, 2=Normal, 3=High, 4=Urgent`; instances often differ.

---

## 3. Step 2 — Read the GitHub repo

- Private repos return **404** via GitHub API/web. Authenticate with the `gh` CLI:
  - `gh auth status` — confirm login + token scope `repo`.
  - `gh repo view <owner>/<repo>` — check the repo exists and read its README.
  - `gh repo clone <owner>/<repo> <temp-dir>` — clone into a temp/scratch directory (e.g. the OS temp folder), never into the workspace.
  - `git log --reverse` in the cloned repo to read the **first/oldest commits**.
- Commit details + PR link:
  - `gh api "repos/<owner>/<repo>/commits/<sha>"` → files changed, author, date.
  - `gh api "repos/<owner>/<repo>/pulls/<n>"` → PR title/URL/merged date.
- Gotcha: parsing `gh api --paginate` output can be unreliable — clone the repo and use `git log` instead.

---

## 4. Step 3 — Map commit data to the issue

### 4a. Map commit author → Redmine member

- If the `.redmine` cache has a `user_mappings` section, match the commit author (GitHub login or git email) against the stored mappings first:
  - Match by `github` (GitHub login) or `git_email` — whichever is present and matches the commit author.
  - If a match is found → use `redmine_user_id` directly, **no ask needed**.
- If no match in `user_mappings` (or no `user_mappings` section) → match against the live `members` list from Step 1 (same logic as before).
- If the author cannot be matched confidently → **ask the user**, never guess.

### 4b. Determine the [FE/BE/Devops] prefix by files changed

| Files changed | Prefix |
|---|---|
| Backend code (API, backend services, backend tests, backend dependencies) | `[BE]` |
| Frontend code (UI, widgets, web assets) | `[FE]` |
| Infrastructure (Docker, nginx, CI/workflows, deployment scripts) | `[Devops]` |

Mixed changes → pick the dominant layer; ask the user if ambiguous.

### 4c. Issue naming rules

- **subject** = `[FE/BE/Devops] <commit subject>` — the commit subject verbatim, English, no extra prefixes.
- **description** = your auto-drafted English template from Section 6 — never ask the user to write it.
- **tracker**: Feature by default (confirm actual ID from Step 1).
- **status**: New by default (confirm actual ID from Step 1).
- **estimated_hours**: 8 by default.
- **start_date** = the commit date; **due_date** = start_date + 1 day (pre-proposed defaults — adjustable on confirmation).
- **done_ratio**: 0.
- **priority**: Normal by default (confirm actual ID from live data).
- **assigned_to**: the mapped member (step 4a).

---

## 5. Step 4 — Create the issue

1. **Before calling create**: present the full param plan to the user — subject, **description (your draft from Section 6 — review/edit only, never ask the user to write it)**, tracker (from options), status (from options), priority (from options), assignee (from options), dates (pre-proposed: start = commit date, due = start + 1 day), estimate, done_ratio. Ask for confirmation using the agent's structured ask tool (opencode `question`, Claude Code `AskUserQuestion`, Codex `request_user_input`; plain text as fallback):
   - Batch confirmations into **1–4 questions per call** (e.g. one call for tracker/status/priority, another for assignee/dates).
   - The structured ask tool caps at **4 clickable options per question**; for longer live lists (e.g. 12 trackers, 20 members) embed the **full numbered list in the question text** and let the user type the number or name as the answer (custom/free-text input), optionally adding 2–4 clickable shortcuts of the most likely picks — never drop valid options silently.
   - If the ask tool is unavailable or the session is non-interactive (e.g. Codex `exec`, CI), ask in plain text and wait for the reply; never proceed on guessed values.
   Adjust any param the user changes.
2. Call the agent's **create issue** capability (e.g. `redmine_create_redmine_issue`) with all required params: `project_id, subject, description, tracker_id, priority_id, status_id, assigned_to_id, start_date, due_date, estimated_hours, done_ratio`.
3. **Verify the created issue's returned values** (priority/status names especially) — if any doesn't match what you intended, call the agent's **update issue** capability (e.g. `redmine_update_redmine_issue`) with the correct value and a note explaining the change.
4. Report back: issue ID, subject, project, tracker, status, assignee, priority, dates, estimate.

---

## 6. Description template (English, fixed format)

**You (the agent) draft the entire description** — the user never writes it from scratch. Fill all 8 sections **fully in English** from the commit/PR/repo context (actual code, files, changes); the user only reviews/edits the draft during confirmation (Section 5, step 1):

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
- User story must use exactly **As a → I want → So that**, each phrase **bolded**.
- Keep all section headers verbatim; fill only the bullet content.
- Append the PR link on the last line.
- Reference actual code/files from the commit when filling Context/Proposed solution.

---

## 7. Gotchas checklist

- [ ] Description is auto-drafted by you from the English template (Section 6) using commit/PR/repo context — never ask the user to write it from scratch.
- [ ] start/due dates are pre-proposed (commit date, +1 day) — present as defaults, user only adjusts if needed.
- [ ] Priority IDs cannot be assumed from any default description — verify via live issue data (instances have differed before: id 3 was once "High" where a default claimed "Normal").
- [ ] Private repos → use `gh` CLI, not GitHub API/web (404).
- [ ] Don't parse `gh api --paginate` output; clone + `git log` instead.
- [ ] The project-context tool returns `statuses` (recent versions); if the section is absent, call a separate status-list capability too.
- [ ] Ask/confirm every required param with the user; present live options (tracker/status/priority/assignee) via the agent's structured ask tool (opencode `question` / Claude Code `AskUserQuestion` / Codex `request_user_input`), plain text as fallback.
- [ ] Ask-tool limits: ≤ 4 clickable options per question, 1–4 questions per call — for longer live lists embed the full numbered list in the question text and let the user type the answer (custom input); in Claude Code subagents `AskUserQuestion` is unavailable, ask in plain text.
- [ ] Description must be English with the exact template above.
- [ ] Confirm the returned values after creation; fix with update if needed.
- [ ] Cache fast path: read `.redmine` at the git worktree root; use it only while `fetched_at` is within 14 days; warn + suggest `redmine init` when stale.
- [ ] Missing cache ID → verify that single item live; never invent IDs absent from the cache.
- [ ] `user_mappings` in `.redmine` takes priority over live member matching — if a commit author matches a stored mapping, use `redmine_user_id` directly without asking.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
