---
name: redmine-issue-workflow
description: Use when creating a Redmine issue from a GitHub commit or task (also triggers on Vietnamese requests like "tạo issue/task trên Redmine từ commit", "tạo task", "create issue", "redmine"). Covers gathering project context, verifying IDs against live data, mapping commit authors to Redmine members, applying the [FE/BE/Devops] naming rule, and filling the standard English description template. Use ONLY for Redmine issue creation from commit/repo context, not for general Redmine queries or wiki work.
---

# Redmine Issue Workflow

This skill documents the exact workflow to create a Redmine issue from a GitHub commit. It is **generic across projects and agents** — no hardcoded project IDs, member IDs, tool names, or instance-specific values.

**IMPORTANT:** Every ID, name, and value in this skill is an example or a default proposal. The only source of truth is the live data fetched from Redmine in the current session. Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides for that capability (e.g. Redmine MCP tools, `gh` CLI, shell).

---

## 1. Core principles

- **Never trust memory, tool-description defaults, or this skill's examples** — always fetch live data from Redmine first. Values change per project, per instance, and over time.
- **Always verify before creating**: project, trackers, statuses, priorities, members, versions, categories.
- Issue content (subject + description) is written in **English**.
- The workflow below applies when the user asks to "tạo issue/task từ commit", "create issue from commit", or hands you a GitHub commit + Redmine project.

### Ask-before-create rule

- **Every required parameter must be asked/confirmed with the user** — never silently pick values (subject, tracker, status, priority, assignee, start/due date, estimate, done_ratio).
- If the parameter has **options from live data** (tracker list, status list, priority list, member list), present the available options to the user and ask them to choose — use the agent's ask/choice capability (e.g. the `question` tool) with the real options fetched from Redmine.
- Defaults proposed in this skill (tracker Feature, status New, estimate 8h, priority Normal, dates from commit) are **proposals**, not final values — present them, get explicit confirmation, then create.
- Unknown data that cannot be derived (e.g. commit author not in the member list) → always ask, never guess.

---

## 2. Step 1 — Gather Redmine project context

Use the agent's Redmine tools (capabilities in parentheses — names may differ across agents):

1. **List projects** (e.g. `redmine_list_redmine_projects`) → find the target project and its ID.
2. **Get project issue context** (e.g. `redmine_get_project_issue_context`, project_id) → returns **trackers, members + roles, categories, versions, custom_fields and statuses** (recent versions of redmine-mcp-server include statuses in the response).
3. **Statuses**: use the `statuses` section from step 2 when present (valid statuses, e.g. `New`, `In Progress`, `Done`, `Closed` — IDs vary per instance). If the response has **no** `statuses` section, call a separate status-list capability (e.g. `redmine_list_redmine_issue_statuses`).
4. If priorities are not provided by any tool, derive the real priority list by **listing existing issues** (e.g. `redmine_list_redmine_issues` with fields `["id", "priority"]`) and reading the names from real issues — **never assume** `1=Low, 2=Normal, 3=High, 4=Urgent`; instances often differ.

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

- Match the commit author (GitHub username/name) to a Redmine member from Step 1's live member list. Build the mapping from the **fetched data only**.
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
- **tracker**: Feature by default (confirm actual ID from Step 1).
- **status**: New by default (confirm actual ID from Step 1).
- **estimated_hours**: 8 by default.
- **start_date** = the commit date; **due_date** = start_date + 1 day.
- **done_ratio**: 0.
- **priority**: Normal by default (confirm actual ID from live data).
- **assigned_to**: the mapped member (step 4a).

---

## 5. Step 4 — Create the issue

1. **Before calling create**: present the full param plan to the user — subject, tracker (from options), status (from options), priority (from options), assignee (from options), dates, estimate, done_ratio. Ask for confirmation using the agent's ask capability; adjust any param the user changes.
2. Call the agent's **create issue** capability (e.g. `redmine_create_redmine_issue`) with all required params: `project_id, subject, description, tracker_id, priority_id, status_id, assigned_to_id, start_date, due_date, estimated_hours, done_ratio`.
3. **Verify the created issue's returned values** (priority/status names especially) — if any doesn't match what you intended, call the agent's **update issue** capability (e.g. `redmine_update_redmine_issue`) with the correct value and a note explaining the change.
4. Report back: issue ID, subject, project, tracker, status, assignee, priority, dates, estimate.

---

## 6. Description template (English, fixed format)

Copy this structure into the `description` field — **fully in English**, all 8 sections, placeholders filled from the commit/PR:

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

- [ ] Priority IDs cannot be assumed from any default description — verify via live issue data (instances have differed before: id 3 was once "High" where a default claimed "Normal").
- [ ] Private repos → use `gh` CLI, not GitHub API/web (404).
- [ ] Don't parse `gh api --paginate` output; clone + `git log` instead.
- [ ] The project-context tool returns `statuses` (recent versions); if the section is absent, call a separate status-list capability too.
- [ ] Ask/confirm every required param with the user; present live options (tracker/status/priority/assignee) via the agent's ask capability.
- [ ] Description must be English with the exact template above.
- [ ] Confirm the returned values after creation; fix with update if needed.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
