---
name: redmine-init
description: Use when the user asks to initialize or refresh the Redmine project mapping for the current repository, e.g. "redmine init", "khởi tạo redmine", "map repo này với project redmine", "tạo file .redmine", "refresh redmine context", "redmine context bị cũ". Creates or refreshes the `.redmine` JSON cache file at the git worktree root, storing the project ID and the static ID lists (trackers, statuses, priorities, members, versions, categories, custom fields) with a `fetched_at` timestamp, so issue-creation skills can create tasks without re-fetching every value. Also asks the user to map their GitHub account to a Redmine member and stores the mapping in `.redmine` so the issue-workflow skill can auto-assign assignees without guessing. Also asks the user for each team member's working rules (role/stack, coding conventions, testing, code review, AI-assistant usage, reporting — the user may answer or skip per member) and stores them in `.redmine` (`member_rules`) so the planning/issue skills respect each person's constraints. Use ONLY for init/refresh of the cache, NOT for creating issues, logging time, or wiki work.
---

# Redmine Init

This skill creates and refreshes a `.redmine` JSON cache file at the git worktree root of the current repository. The cache maps the repository to exactly one Redmine project and snapshots its static ID lists, so the `redmine-issue-workflow` skill can create issues fast without re-fetching every value.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (e.g. Redmine MCP tools).

---

## 1. Core principles

- The `.redmine` file is a **snapshot** — it is a trusted source for *static* ID lists (project, trackers, statuses, priorities, members, versions, categories, custom fields) while fresh. It never stores per-issue state (e.g. which priority/status an issue currently has) — that changes hourly and is always fetched live.
- The file is **NOT** a source of truth for *dynamic* state — allowed status transitions, parent-issue validity, or members who joined after the snapshot. Those must still be verified live.
- Freshness is decided by `fetched_at` (ISO 8601, UTC) vs the TTL of **14 days**.
- Tool responses wrap every name in `<insecure-content-...>` tags — **always strip these tags** before writing the cache.
- v1 supports exactly **one project per repository**. For a monorepo that spans multiple Redmine projects, ask the user which project the repo maps to and keep one file.

---

## 2. Init flow (no `.redmine` file yet)

1. **Locate the repo root**: run `git rev-parse --show-toplevel`. The `.redmine` file goes at that root (not the current working directory when they differ). If the directory is not a git repository → ask the user where to place the file.
2. **Check for an existing file**: if `.redmine` already exists at the root → follow the refresh flow (section 3) instead.
3. **List projects**: call the list-projects capability (e.g. `redmine_list_redmine_projects`) → returns `id`, `name`, `identifier`, `description`, `created_on`.
4. **Ask the user to choose — full list always visible (full-list rule)**: NEVER ask with only a couple of options, and NEVER guess. Before calling any ask tool, render the **complete** project list to the user in the chat message as a markdown table — every single row, no truncation, no capping:
   ```markdown
   | # | ID | Project | Identifier |
   |---|----|---------|------------|
   | 1 | 313 | [AI] Chatbot Tuyển Sinh | ai-chatbot-tuyen-sinh |
   | 2 | 156 | [MobileApp] CLICK-Ed app platform | du-an-qa-app |
   | ... | ... | ... | ... |
   ```
   Then ask "repo này tương ứng với project Redmine nào?" with the agent's structured ask tool (opencode `question`, Claude Code `AskUserQuestion`, Codex `request_user_input`; plain text as fallback). Rules for the ask:
   - The question text must **repeat the full list as a numbered list** (ask tools accept custom/free-text answers — the user types the number or name from the table).
   - Always include a catch-all custom/free-text option like "Khác — gõ số hoặc tên từ bảng trên".
   - Add at most 2–4 clickable shortcuts of the most likely projects **on top of** the full list — they are conveniences, never a replacement; users must always be able to see and choose ALL entries.
   - Very long list (> ~30 rows): still render the full table, then ask the user to narrow by keyword in a follow-up — never drop rows silently.
5. **Fetch project context**: call the project-context capability (e.g. `redmine_get_project_issue_context`, project_id) → returns project, trackers, categories, members (with roles), versions, statuses (`is_closed`), **priorities**, custom_fields, required_custom_fields. The `priorities` section is the **complete** list (e.g. `{"id": 2, "name": "Normal"}`); Redmine has no separate "list priorities" endpoint, the context tool provides it. This caches only the **static option list** (the dropdown of values), never any issue's current priority — per-issue priority state changes hourly and is always fetched live.
6. **Map GitHub account ↔ Redmine member**: detect the current GitHub identity and confirm the Redmine member.
   1. Detect GitHub side: run `gh api user` (requires `gh` CLI, installed first per the issue-workflow skill's prerequisites) → returns `login`, `name`, `email`. If `gh` is unavailable, fall back to `git config user.name` + `git config user.email`.
   2. Match the detected GitHub identity against the `members` list from step 5. Match by **name** (case-insensitive) first, then by **email** if name doesn't match.
   3. If exactly **one** confident match → confirm with the user via the structured ask tool: "GitHub account `janedoe` (Jane Doe) maps to Redmine member nào?" with the matched member pre-selected and 1–3 other likely members as clickable shortcuts.
   4. If **no match** or **multiple matches** → apply the **full-list rule** from step 4: render the complete `members` list as a markdown table (| # | ID | Name | Roles |) in the chat message — all rows visible, no truncation — then present the full list in the question text of the structured ask tool (user types number or name; ≤4 clickable shortcuts of the most likely picks on top, never instead of the full list).
   5. **Optional — map additional committers** (ask only if the user seems interested; do NOT exhaustively map every committer to save tokens): run `git shortlog -sne --since="6 months"` to get a compact list of recent committers (1 line each: `count  Name <email>`). Ask the user: "Có muốn map thêm committer nào không?" — if yes, present the shortlist and let them pick entries to map (same ask pattern). Default: **only the current user** (tiết kiệm token).
   6. Build the `user_mappings` array: each entry `{"github": "<login>", "git_email": "<email>", "redmine_user_id": <id>, "redmine_name": "<name>"}`. Strip wrapper tags from all names.
7. **Collect member working rules** (ask, never assume): for each member mapped in step 6, ask the user for that person's working rules — "Người này làm role gì và có rule/đặc thù riêng khi làm việc không? (gõ 'bỏ qua' để skip)". Prompt with the researched catalog below as a reminder of what rule areas exist (role/stack, required tests, code-review expectations, AI-assistant usage policy, reporting cadence, definition of done). The user answers, skips, or says "bỏ qua" per member — **never invent a rule**; store only what the user explicitly said, as short verbatim bullets (Vietnamese OK).
8. **Strip wrapper tags**: remove every `<insecure-content-...>` and `</insecure-content-...>` marker from names.
9. **Write `.redmine`**: a single JSON file at the repo root, exact schema in section 4, `fetched_at` = current UTC timestamp (ISO 8601, e.g. `2026-08-06T00:00:00Z`).
10. **Verify**: read the file back; confirm it parses as valid JSON, contains no wrapper tags, and `fetched_at` is set.
11. **Report**: project id/name/identifier, counts of trackers/members/statuses/priorities, the `user_mappings` count, the `member_rules` count, the file path, and the reminder: re-run `redmine init` later to refresh; the file is safe to commit (no secrets).

### Member rules catalog (research summary — use as prompt material)

Researched rule areas per role (ask the user which apply; do NOT assume any apply):

| Role | Typical rule areas |
|---|---|
| Backend | API-first contract (OpenAPI), schema/validation, authn/z + PII handling, error handling, database access rules, performance/scalability, test coverage |
| Frontend (web) | Design system + tokens, responsive + accessibility, performance (bundle/lazy), state management pattern, API contract alignment, e2e for critical flows |
| Mobile | Platform (native Swift/Kotlin vs Flutter/React Native), offline/caching + network retries, store policies + signing/release, crash monitoring, performance (cold start, memory, battery), secure storage |
| DevOps | CI/CD quality gates, IaC (Terraform/Ansible), Docker/K8s, observability/alerting, release management + rollback, security gates, secrets handling |
| AI (LLM) | RAG + evals (golden datasets), prompt management, guardrails, inference latency/cost, drift monitoring, model API rate limits/retries/fallbacks |
| Data analyst (DA) | SQL + BI dashboards, metric definitions, data quality/freshness, source of truth |
| Data engineer | dbt models, orchestration (Airflow), lineage, data quality tests, schema migrations |
| QA | Test pyramid, page objects/factories, e2e on critical paths only, adversarial/negative paths, contract testing |
| Full-stack | Both sides of the API contract, end-to-end feature ownership incl. tests |
| Lead (Tech/Team/Project) | Architecture decisions + review/approval gates (review rules, who must approve PRs/merge), task delegation (what they assign vs. keep), technical risk ownership, mentoring/onboarding, reporting to stakeholders, definition of done enforcement |
| Security | Threat modeling, SAST/DAST, auth, compliance |
| SRE | SLOs, error budgets, incidents, chaos testing |
| PM/PO | Intent + acceptance criteria + out-of-scope, definition of ready |

Cross-role dimensions to ask once per person: commit/branch conventions, code-review expectations, AI-assistant usage policy (allowed? verify output?), reporting cadence (standup/weekly), definition of done, preferred communication.

---

## 3. Refresh flow (`.redmine` already exists)

1. Read the existing `.redmine`.
2. **Reuse the stored `project.id`** — do NOT re-ask which project.
3. If the user hints the repo maps to a *different* project than the file says → confirm with the user before overwriting.
4. Re-fetch project context + priorities (step 5 of the init flow) and overwrite the file with a fresh `fetched_at`, keeping the same schema.
5. **Refresh `user_mappings`**: keep existing mappings whose `redmine_user_id` is still in the new `members` list; drop entries for members that no longer exist; do NOT re-ask for existing mappings.
6. **Refresh `member_rules`**: keep entries whose `redmine_user_id` still exists in the new `members` list, drop stale ones; do NOT re-ask every person's rules — only ask again if the user explicitly wants to update them.
7. Verify and report as in init steps 10–11.

---

## 4. `.redmine` schema (exact)

```json
{
  "version": 1,
  "project": {"id": 12, "name": "Example Project", "identifier": "example-project", "created_on": "2026-01-15T08:30:00Z"},
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

- `version`: `1`.
- `fetched_at`: current time, ISO 8601 with `Z` (UTC).
- Keep keys verbatim; empty lists stay as `[]`.
- Strip all `<insecure-content-...>` wrapper tags from names.
- `member_rules` (optional): per-member working rules as told by the user — `roles` = role/stack tags (backend, frontend, mobile, devops, ai, da, qa, full-stack, ...), `rules` = short verbatim bullets (Vietnamese OK). A member without entries means the user skipped them — never invent rules.

---

## 5. TTL policy

- Default TTL: **14 days**.
- Consumers (`redmine-issue-workflow`) use the cache while `fetched_at` is within TTL, and warn the user + suggest `redmine init` when older.
- This skill never auto-refreshes in the middle of another task — refresh only when invoked.

---

## 6. Gotchas checklist

- [ ] **Full-list rule**: before ANY list-based ask (projects, members), render the complete list as a markdown table in the chat message — every row visible, no capping/truncation; the ask-tool options are only shortcuts on top of the full list, never a replacement, and the question text always repeats the full numbered list so the user can type the number or name.
- [ ] Strip `<insecure-content-...>` wrapper tags before writing; the file must contain clean names only.
- [ ] Write at the **git worktree root** (`git rev-parse --show-toplevel`), not the current working directory when they differ.
- [ ] Not a git repo → ask the user where to place `.redmine`.
- [ ] One project per repo (v1). If a repo maps to multiple projects, ask the user to pick one for the file.
- [ ] Priorities come from the context tool as a complete list — no sampling or guessing; consumers still live-verify an ID absent from the cache instead of inventing one.
- [ ] The file contains no secrets (IDs, names, roles only) — safe to commit for the whole team.
- [ ] `user_mappings` is optional — if absent, the issue-workflow skill falls back to asking the user for each author. Existing mappings are kept across refreshes; entries for members no longer in the project are dropped automatically.
- [ ] GitHub identity is detected via `gh api user` (requires `gh` CLI, installed first per the issue-workflow prerequisites); falls back to `git config user.name` + `git config user.email` if `gh` is unavailable.
- [ ] Mapping the current user is the default — do NOT exhaustively map every committer (saves tokens); offer to map additional committers optionally via `git shortlog -sne --since="6 months"`.
- [ ] Member rules are **user-provided only** — never invent a rule; a member the user skips simply has no entry. Use the researched catalog (roles × rule areas) as prompts, not as assumptions.
- [ ] Re-ask member rules on refresh only when the user asks to update them — keep existing entries otherwise.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
