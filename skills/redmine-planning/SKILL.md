---
name: redmine-planning
description: Use when the user wants to break a single user story down into tasks in Redmine, e.g. "breakdown user story này", "tách task cho story này", "gỡ task", "lập kế hoạch cho story", "planning", "add tasks to the story", "thêm task vào story", "cập nhật plan", "đổi estimate", "chuyển version", "task nào làm trước", "assign người cho task", "dependon", "dependency". Scope: ONE user story per run — never a whole sprint/epic. Two checkpoints: (1) clarify every ambiguous business point with the user (never self-interpret; technical gaps are asked back), persist the confirmed story (+ optional sub-stories) as JSON in the `.redmine` plan section — nothing written to Redmine yet; (2) after the user says continue, ground the breakdown in architecture read ONLY from AGENTS.md / CLAUDE.md / ARCHITECTURE.md (never scan the repo), break into tasks (estimate = implementation time × 1.2, leaf tasks 4–8 h; assignees from module ownership), collect precedes/follows dependencies, then create everything via the Redmine MCP tools and mark the state created. The plan always belongs to the repo's project (top-level `project` in `.redmine`) — planning another project/repo is refused. Also covers updating an existing breakdown.
---

# Redmine Planning

Break a user story down into tasks with the right assignees, inside Redmine — without plugins, without new server code. You (the agent) act as the **planning interface**, in **two checkpoints** the user can pause between:

**Checkpoint 1 — Proposal (no Redmine writes)**: clarify all ambiguous business points of ONE story with the user, optionally split it into sub-stories, iterate until the user confirms ("chốt"), persist the confirmed state to `.redmine` (plan section).

**Checkpoint 2 — Commit (writes to Redmine)**: after the user explicitly says continue, ground the breakdown in architecture from designated files only (or ask), break the story/sub-stories into tasks with estimates and assignees, collect dependencies, confirm once, then create story → sub-stories → tasks → relations and mark the state "created" with IDs.

**Scope — one user story per run.** This skill never plans a whole sprint/epic at once: teams can be large and business logic complex, so reviewing a full sprint overflows the context. If the user asks for a sprint/quarter plan, decline and ask for the first story: *"Tôi chỉ breakdown 1 user story một lần — bạn muốn làm story nào trước?"*; several stories → process them one at a time, each with its own two checkpoints.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (e.g. Redmine MCP tools). No platform/planning MCP server is required: everything happens through the Redmine MCP server the user already configured.

---

## 1. Core rules

1. **Two checkpoints, explicit user gate**: Checkpoint 1 never writes to Redmine. Checkpoint 2 only starts after the user explicitly agrees to continue. Each checkpoint ends with a report; the user can stop after either.
2. **State lives in `.redmine`**: the confirmed proposal is persisted as JSON in the `plan` section of `.redmine` (schema in Section 5) — the file is the durable state, not the conversation.
3. **Never scan the repository**: architecture context comes ONLY from designated doc files at the repo root (`AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md` — read all that exist) and from questions to the user. If no such file exists, **ask the user** about modules/ownership/complexity — browsing the tree, running `git log`, or reading source to "understand the code" is forbidden (it burns tokens and is the user's explicit rule).
4. **Live data first** — never trust memory or tool-description defaults for Redmine IDs. Exception: a `.redmine` cache with `fetched_at` within **14 days** is a trusted fast path for its static lists (project, trackers, statuses, priorities, members, versions, categories, custom fields). Anything missing from the cache, or dynamic (allowed status transitions, parent-issue validity), must be fetched live. Stale cache → warn and suggest `redmine init`. No `.redmine` → live lookups.
5. **Ask-before-create**: every required parameter is confirmed — never silently chosen. Use the agent's structured ask tool (opencode `question` / Claude Code `AskUserQuestion` / Codex `request_user_input`; plain text as fallback). Ask-tool limits: **1–4 questions per call**, **≤ 4 clickable options per question**; for longer live lists (trackers, members, versions) embed the **full numbered list in the question text** and let the user type the number/name. If the ask tool is unavailable or the session is non-interactive → ask in plain text and wait; never proceed on guessed values.
6. **Dates are the user's call — never auto-proposed**: scheduling depends on context complexity only the user knows. Ask once at confirmation; if the user gives none, create the issues with **empty dates**.
7. **Assignees follow real ownership + member rules**: from architecture docs (owner sections) + `.redmine` `user_mappings` / live members; "unassigned" is the safe default when unknown. When proposing an assignee, also respect `.redmine` `member_rules` — each member's roles/stack (backend, frontend, mobile, devops, ai, da, qa, full-stack, lead, ...) and personal rules (e.g. "không nhận task UI", "mọi thay đổi DB phải qua lead review"): a task is only proposed to someone whose roles fit the work and whose rules don't exclude it; a Lead's rules typically describe review/approval gates, so lead review is proposed as a separate task or a check, not as the implementation assignee. No matching candidate → ask the user (never override a rule silently).
8. **Issue content is English** (subject + description) unless the user asks otherwise.
9. **The agent drafts everything** — the story description, sub-stories, tasks, estimates — as *proposals*. The user only reviews/edits at confirmation.
10. **Ask, don't interpret**: every ambiguous business point — why the story matters (context), who uses it (role), what it does (capability), why it is worth it (business value), what counts as done (acceptance criteria) — is resolved by **the user through questions**, never self-interpreted. Unresolved points are marked `[?]` in the draft; the proposal is not confirmed (2d) until the user answers all of them. The same applies to **technical feasibility**: if implementing a business requirement is not feasible (technical gap), ask the user how to proceed (re-scope, alternative approach, or drop) — never silently reword, shrink or drop a requirement to fit what is easy.
11. **The plan always belongs to the repo's project**: the target project is the repo's project — the top-level `project` in `.redmine` (the one `redmine init` mapped). If the user asks to plan a **different project or repo**, **refuse**: "Skill này chỉ planning cho project của repo hiện tại — tôi không có context/architecture của repo kia để breakdown." Never plan another project even if the user insists (offer the redmine-issue-workflow skill for ad-hoc issues there instead).
12. **One user story per run — never a whole sprint**: the breakdown covers **ONE story** at a time (optionally split into business-level sub-stories). A full-sprint plan is refused — team size and business complexity overflow the context; neither you nor the user can review every item at once. If the user insists, ask for the first story and offer to process the rest one by one.
13. **Read-only guard**: if the server is in read-only mode (`REDMINE_MCP_READ_ONLY`), creation tools return an error — detect it early and tell the user Checkpoint 2 cannot write; offer to finish Checkpoint 1 (proposal + state) only.

---

## 2. Checkpoint 1 — Proposal (no Redmine writes)

### 2a. Gather context

1. **Cache check (fast path)**: per Rule 4 — fresh (≤ 14 days) → reuse static lists; stale → warn + suggest `redmine init`; ID missing from cache → fetch that one live; no file → live lookups. Strip `<insecure-content-...>` wrapper tags from any names you reuse.
2. **The target project is fixed — the repo's project**: the top-level `project` in `.redmine` (or fetched per the `redmine-init` skill when no cache). If the user names another project or repo → **refuse** (rule 11): the breakdown needs that repo's context and architecture, which you do not have.
3. **Get project issue context** → trackers, members + roles, categories, versions, statuses, priorities, custom_fields. Priorities come from this call as the complete list — never assume `1=Low, 2=Normal, 3=High, 4=Urgent`.
4. Note whether a version exists that can hold the breakdown (a version = a sprint/release milestone in Redmine). This context is needed for Checkpoint 2 but cheap to have now.

### 2b. Capture the input — ONE story

Ask the user for **the story** (subject + what it does). Modes:

**Guided mode** — ask in this order:
1. **The story**: "User story bạn muốn breakdown là gì? (mô tả ngắn)" — if the user instead describes a whole sprint/epic, decline and ask for the first story (rule 12).
2. **Business intent**: "Mục tiêu / giá trị business của story này là gì? Ai là người dùng?" — answers feed the template in 2c.
3. **Acceptance criteria**: "Có AC sẵn không? (dán vào hoặc tôi sẽ đề xuất để bạn sửa)".
4. **Batch defaults** (one ask call): default priority, default assignee (or "unassigned"), default estimate per task, target version (or "new version needed"). **Dates are NOT part of the defaults** (rule 6).

**From-notes mode**:
1. Ask the user to paste notes about the story (or point at a wiki page via the wiki-read capability).
2. Parse the notes into the story's business points. Preserve explicit facts (names, dates, priorities, owners, any ordering hints); mark anything unclear as a **question** in the confirmation step — never invent facts. Note ordering hints (e.g. "làm X trước rồi mới Y") for the dependency step in Checkpoint 2.
3. Follow the same batch-defaults ask call as guided mode.

**Existing story mode**: if the user points at an existing Redmine issue (find by ID or subject search: one match → use it; multiple → ask; none → ask for the ID), read it with the read capability and use its content as the story; the breakdown will be created as its children (sub-stories/tasks). Confirm the tracker/parent of that issue before continuing.

### 2c. Draft the proposal (user-story format)

Structure at Checkpoint 1 — **business level only**; tasks come in Checkpoint 2 after architecture grounding (3b):

```
Story (node type: story)
└─ Sub-story (node type: story, optional — only if the user wants to split)
```

- **Story subject**: short English capability statement. Description: the user-story template below.
- **Sub-stories (optional)**: if the story is big, **propose** splitting it into lower-level sub-stories — each a business slice with its own As a / I want / So that / Acceptance criteria. The user decides whether to split; you never split silently. Sub-stories are still business requirements — not tasks.
- **Estimates (proposals)**: story-level ballpark only (batch default). Exact per-task estimates are fixed in Checkpoint 2: implementation time + 20 % buffer, leaf tasks 4–8 h (3b).
- **Assignees (proposals)**: batch default, or per-node overrides the user asks for. Real ownership grounding happens in Checkpoint 2.
- **Dependencies (proposals, optional)**: note any ordering the user states ("task nào nên làm trước") — store as `depends_on` refs in Checkpoint 1 state if explicit, otherwise propose them in Checkpoint 2 (3c).

Story description template (you draft fully in English):

```markdown
## Context
- Why this story matters / problem it solves / why it is needed now.

## User story
- **As a** [specific role — never "a user" or "the system"]
- **I want** [capability — the user's intent, not the UI or implementation]
- **So that** [real business value]

## Acceptance criteria (3–5, each pass/fail)
- [ ] AC1: [happy path, verifiable outcome]
- [ ] AC2: [edge case — invalid input / authorization / retry / partial failure]
- [ ] AC3: [Given/When/Then when the behavior depends on state]

## Out of scope
- [what this story deliberately does NOT cover]

## Notes & open questions
- [dependencies, assumptions, unresolved `[?]` points]
```

Rules: user story uses exactly **As a → I want → So that**, each phrase **bolded**; keep section headers verbatim; fill only the bullet content. Writing rules: `As a` names a **specific role** — if you cannot point at the real user, the role is decoration; `So that` must be a **real business value** (delete-test: if nothing is lost when the clause is removed, the value is not found yet); `## Acceptance criteria` holds **3–5** pass/fail conditions — fewer than 3 → too vague, more than 8 → split the story — covering the happy path plus the important edge cases (invalid input, authorization, retry, partial failure), using **Given/When/Then** when the outcome depends on a starting state (each scenario maps to a task in Checkpoint 2); `## Out of scope` prevents scope creep during task breakdown (most estimate disputes are two people sizing different scopes); `## Notes & open questions` holds dependencies, assumptions and unresolved `[?]` points.

**No self-interpretation / technical feasibility**: per Rule 10 — every ambiguous business point (context, role, capability, value, acceptance criteria) and every technical gap is a question for the user, never a gap you fill from assumptions. Keep each unresolved point visible in the draft as `[?]` in `## Notes & open questions` (e.g. `- [?] AC2: xử lý trùng lặp order thế nào?`); the proposal cannot be confirmed (2d) while any `[?]` remains.

### 2d. Iterate until the user confirms ("chốt")

1. Present the full draft (story + optional sub-stories with descriptions + estimate/assignee/priority proposals, totals). List every `[?]` from 2c as open questions first — the **user** resolves each one; you never self-interpret. Before presenting, run a quick quality check on the story: specific role (not "a user"), `So that` carries real value, 3–5 testable acceptance criteria, `## Out of scope` stated — flag anything failing.
2. Apply every adjustment the user makes and re-present — **repeat until the user explicitly confirms the proposal**. Do not accept "chốt" while a `[?]` is still unanswered: each one is a question for the user, not a guess you are allowed to make. Never skip to Checkpoint 2 on your own judgment.
3. On confirmation, summarize the decisions: project, tracker mapping (story/task), priority, assignee (or unassigned), version (or "create via UI"), story-points field (if applicable). **Ask about dates separately, only if the user wants to set them** — leave empty otherwise (rule 6).

### 2e. Persist state to `.redmine`

Write the confirmed proposal into the `plan` section of `.redmine` (exact schema in Section 5), `status: "proposed"`, with a per-node `ref` (S1 for the story, sub-stories as S2/S3..., tasks as T1/T2... once created in Checkpoint 2) and parent links. If `.redmine` does not exist (e.g. no `redmine init` run), create it with the plan section plus the static lists you fetched in 2a, keeping the exact schema and the top-level `project` set to the **repo's** project (never another project — rule 11). Verify the file parses as JSON and contains no wrapper tags.

**One plan in memory**: the `plan` section holds **exactly one plan at a time** — i.e. one story's breakdown. If a plan already exists (even a `"created"` one), warn the user it will be replaced and ask to confirm before overwriting — issues already created in Redmine are NOT affected. Set `created_at` when the plan is first persisted; bump `updated_at` on every later change (field meanings in Section 5).

### 2f. Checkpoint-1 report

Show: story summary (sub-stories if any), estimate totals, where the state is stored, and ask — *"Bạn muốn lưu lên Redmine luôn không?"* (yes → Checkpoint 2; no → stop here, state is kept for later; user can resume with "tiếp tục plan X").

---

## 3. Checkpoint 2 — Commit (writes to Redmine)

Only run after the user explicitly agrees to continue (2f). If the user resumes later, start by reading the `plan` section back from `.redmine`.

### 3a. Architecture grounding — designated files only, or ask

1. At the repo root, read **all** of these files if they exist: `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md` (plus a `docs/architecture.md` if present at the root of docs/). Use them for: module/layer breakdown (to sanity-check the story's scope and sub-stories), ownership hints, complexity signals.
2. **If none of these files exist → do NOT scan the repo. Ask the user instead**, e.g.: "Repo này chưa có AGENTS.md/ARCHITECTURE.md — mô tả giúp: (a) hệ thống gồm những module/layer nào?, (b) ai phụ trách module nào?, (c) module nào phức tạp nhất?" Use the answers to adjust the story's scope, sub-stories, estimates and assignee proposals.
3. Map ownership → assignees via `.redmine` `user_mappings` or the live members list, then **filter candidates through `.redmine` `member_rules`** (roles/stack + personal rules, rule 7): a module owner whose roles don't cover the task's stack (or whose rules exclude it) is not proposed — ask the user for the right assignee; no match → keep the batch default or "unassigned" (never guess).
4. **Feasibility re-check**: if the architecture contradicts a confirmed story (the business requirement is not implementable as stated — technical gap), ask the user how to proceed (re-scope, alternative approach, or drop) — never silently rewrite the story to fit the architecture.

### 3b. Break down tasks (architecture-driven)

With the architecture context from 3a, break **the story (and each sub-story) into tasks** (one task = one deliverable) — this is where complexity, estimates and assignees become concrete:

- **Tasks follow real modules**: name tasks after the components the story touches (from 3a). No architecture info → ask the user for the module breakdown; never guess module names.
- **Estimate rule (mandatory)**: `estimate = implementation time × 1.2` — the time the task actually takes to implement **plus a 20 % buffer** for the problems listed below. Round to sensible half-hours.
- **Size rule (mandatory)**: every leaf task must be between **4 h and 8 h**. A task needing < 4 h → merge it into a related task (re-scope the deliverable); a task needing > 8 h → split it into several tasks. Story/sub-story = sum of its tasks.
- **Prove the estimate with risks**: for every task, list the problems it may hit ("các vấn đề có thể gặp phải") — unclear requirements, tricky integration, hidden dependencies, platform limits, test-data setup, ... — that justify the estimate is just enough. Put them in the task description as a `## Risks` section and surface them again in the 3e confirmation.
- **Assignees from ownership + member rules**: per task, assign the owner of that module (3a step 3 → `.redmine` `user_mappings` / live members) whose `member_rules` roles fit the task's stack and whose rules don't exclude it; no owner or no fitting candidate → batch default, "unassigned", or ask the user (rule 7).
- Task description (English, exact template — headers verbatim, fill only the bullet content):

```markdown
## Deliverable
- [one concrete outcome this task produces]

## Scope of work
- [2–5 implementation steps: module/layer from 3a, endpoint, DB change, config, ...]

## Acceptance
- [ ] T-AC1: [pass/fail check — test passes / API returns X / UI flow works]
- [ ] T-AC2: [trace to the story's AC, e.g. "covers AC2 of S1"]

## Out of scope
- [what belongs to another task of this breakdown, named explicitly]

## Dependencies
- [what must be done first — mirrors the confirmed precedes pairs from 3c, e.g. "T2 (refund DB schema)"]

## Risks
- [the problems justifying the estimate, from 3b]
```

Writing rules: `## Deliverable` is one concrete outcome — "I wrote code" is not done; `## Scope of work` lists only steps grounded in the 3a architecture context (never invented module names); `## Acceptance` holds 1–3 pass/fail checks that **trace to the story's acceptance criteria** (each AC scenario maps to a task, per 2c — write which AC this task covers); `## Out of scope` names the other task(s) that own the leftover work so two tasks never silently overlap; `## Dependencies` mirrors exactly the confirmed `precedes` pairs from 3c (the same list is stored in the state as `depends_on` refs and created as issue relations in 3f) — never add a dependency that is not in that list, and never create one that the user rejected. Keep the `Part of story #<ref>` line at the top.

### 3c. Dependencies — "task nào nên làm trước"

1. **Collect ordering**: the user's stated ordering (from 2b/2c) + module-dependency hints from 3a (e.g. "API trước, UI sau").
2. **Propose `precedes` pairs** (task A precedes task B ⇒ A must be done first); only between tasks of this breakdown (or tasks ↔ sub-stories when the user wants business-level ordering). Optional `delay` in days.
3. **Confirm the dependency list** with the user; record each pair in the state as `depends_on` refs (A `depends_on` B means B must be done first — B precedes A). Never invent dependencies beyond architecture hints; ask when unsure.

### 3d. Finalize fields

- **Trackers**: ask which live tracker maps to each level (Story / Task) if not already decided — full numbered list from live data. If the story is an existing issue, keep its tracker (and parent) as-is. Never invent a tracker.
- **Version**: prefer an existing version (full numbered list). A **new** version cannot be created via MCP — tell the user to create it in the Redmine UI (`/projects/<identifier>/versions/new`) or ask an admin, then continue; alternatively proceed without a version.
- **Status**: `New` (confirm the live ID).
- **Dates**: ask once — if the user gives none, create with empty dates (rule 6).

### 3e. Confirm the whole batch once

Present the final tree (story → sub-stories → tasks) with all resolved values (tracker/priority/assignee/version/status per node, estimate totals) **plus the dependency list** in one compact summary + ask questions for any remaining decisions (batch per Rule 5). Each task line shows its estimate and the key risks justifying it (from 3b). Apply adjustments and re-present once if the user asks for a restructure.

### 3f. Create

1. **Create the story first** (create-issue capability; no parent — or its existing parent if the story is an existing issue) → collect the returned ID.
2. **Per sub-story**: create-issue with `parent_issue_id` = the story's ID → collect the returned ID.
3. **Per story/sub-story**: create-issue-with-subtasks capability (parent = story/sub-story, subtasks = its tasks). The tool enforces: parent exists, same project, parent not itself a subtask.
4. **Create the dependencies** — after all issues exist, for each confirmed `precedes` pair call the create-issue-relation capability (`issue_id` = the issue that must be done first, `issue_to_id` = the dependent issue, `relation_type: "precedes"`, optional `delay`). Redmine mirrors the complementary `follows` automatically — never create both directions. A failed relation is reported, not fatal — tell the user which pair to retry.
5. **Verify the returned values** (status/priority/tracker names especially) — mismatch → update that issue with the correct value.
6. **Mark state created**: update the `.redmine` `plan` section — `status: "created"`, each node gets its `redmine_id`, each created relation gets its `relation_id` under the pair; bump `updated_at`. Verify the file parses.

### 3g. Checkpoint-2 report

The full tree with issue URLs, total estimate, **the dependency summary** (which task must finish before which), and links to the native views — Roadmap: `<redmine-url>/projects/<identifier>/roadmap` (when a version is set), Gantt: `<redmine-url>/projects/<identifier>/issues/gantt` (relations are drawn as arrows). Close with: "plan đã lưu — sửa bất cứ lúc nào qua 'cập nhật plan'".

---

## 4. Update an existing plan

Use when the user asks to change an existing plan (state is in `.redmine` `plan`, or find by issue ID / subject search: one match → use it; multiple → ask; none → ask for the ID).

| Request | Action |
|---|---|
| Add task to a story | create-issue with `parent_issue_id` = story ID (confirm fields); update state JSON with the new node + `redmine_id` |
| Add a sub-story | create-issue with `parent_issue_id` = story ID; update state JSON |
| Change estimate / priority / assignee / dates / version / status | update-issue capability with confirmed fields; update state JSON |
| Move tasks between stories | update-issue `parent_issue_id` per task; re-balance estimates (ask); update state JSON |
| Add a dependency ("task X trước task Y") | create-issue-relation capability (`precedes`, optional delay); update state JSON `depends_on` |
| Remove a dependency | delete-issue-relation capability with the pair's `relation_id`; update state JSON |
| Cancel a node | confirm; update status to `Closed`/`Rejected` (confirm live ID) or delete only if the user explicitly asks; update state JSON |

Report what changed with URLs. Invalid status transition → fetch allowed statuses and suggest the nearest valid one. Whenever state changes, **keep `.redmine` `plan` in sync** and re-verify the JSON parses.

---

## 5. `.redmine` plan state schema (exact)

The `plan` section holds **one story's breakdown** — written by this skill (Checkpoint 1) and updated through Checkpoint 2 / updates. Example (a fully created plan, one story with two tasks):

```json
{
  "version": 1,
  "project": {"id": 12, "name": "Example Project", "identifier": "example-project"},
  "trackers": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Feature"}, {"id": 3, "name": "Story"}, {"id": 4, "name": "Task"}],
  "statuses": [{"id": 1, "name": "New", "is_closed": false}, {"id": 5, "name": "Closed", "is_closed": true}],
  "priorities": [{"id": 2, "name": "Normal"}, {"id": 3, "name": "High"}],
  "members": [],
  "versions": [],
  "categories": [],
  "custom_fields": [],
  "required_custom_fields": [],
  "user_mappings": [],
  "member_rules": [],
  "fetched_at": "2026-08-07T00:00:00Z",
  "plan": {
    "status": "created",
    "version_id": null,
    "decisions": {
      "tracker_story_id": 3,
      "tracker_task_id": 4,
      "priority_id": 2,
      "assignee_default": null,
      "story_points_field_id": null
    },
    "nodes": [
      {"ref": "S1", "type": "story", "subject": "Add refund support", "description": "## Context\n- ...\n\n## User story\n- **As a** ...\n- **I want** ...\n- **So that** ...\n\n## Acceptance criteria\n- [ ] AC1: ...\n\n## Out of scope\n- ...\n\n## Notes & open questions\n- ...", "estimate_hours": 8.8, "priority_id": 2, "redmine_id": 101},
      {"ref": "T1", "type": "task", "subject": "Implement refund API endpoint", "description": "Part of story #S1\n\n## Deliverable\n- Refund API endpoint accepting order + amount\n\n## Scope of work\n- Add refund route in orders module\n- Validate amount against paid total\n- Call payment provider refund API\n\n## Acceptance\n- [ ] T-AC1: POST /refunds returns 201 and refund id\n- [ ] T-AC2: covers AC1 of S1\n\n## Out of scope\n- Refund UI (T2)\n\n## Dependencies\n- T2 (refund DB schema)\n\n## Risks\n- Refund calculation edge cases\n- External payment provider limits", "estimate_hours": 4.8, "priority_id": 2, "parent": "S1", "depends_on": ["T2"], "redmine_id": 102},
      {"ref": "T2", "type": "task", "subject": "Build refund UI", "description": "Part of story #S1\n\n## Deliverable\n- Refund form and confirmation flow\n\n## Scope of work\n- Refund form on order detail page\n- Confirmation screen with result\n\n## Acceptance\n- [ ] T-AC1: refund flow completes end-to-end\n- [ ] T-AC2: covers AC3 of S1\n\n## Out of scope\n- Refund API endpoint (T1)\n\n## Dependencies\n- T1 (refund API endpoint)\n\n## Risks\n- Async status update from provider", "estimate_hours": 4, "priority_id": 2, "parent": "S1", "depends_on": [], "redmine_id": 103}
    ],
    "relations": [
      {"precedes": "T2", "follows": "T1", "relation_id": 55}
    ],
    "created_at": "2026-08-07T00:00:00Z",
    "updated_at": "2026-08-07T00:00:00Z"
  }
}
```

Rules:
- `status`: `"proposed"` after Checkpoint 1; `"created"` after Checkpoint 2 succeeds.
- Node `type`: `"story"` (the story itself and any sub-stories — nested via `parent` refs) or `"task"`.
- **The plan always belongs to the repo's project**: the target project is the top-level `project.id` — `plan` carries no `project_id` of its own. Planning a different project/repo is refused (rule 11) — never write a `plan` for another project, and re-verify after any `redmine init` that the top-level `project` still matches the repo before continuing.
- **One plan at a time**: the `plan` section holds exactly one plan (one story's breakdown) — starting a new plan replaces the old `plan` state (confirm with the user first; already-created Redmine issues are untouched) — see 2e.
- `created_at`: set when the plan is first persisted (Checkpoint 1); `updated_at` bumps on every state change.
- `redmine_id`: `null` until the issue is created, then the real ID.
- `depends_on` (per node): refs of nodes that must be **done first** ("task nào nên làm trước"). Confirmed in 3c.
- `relations`: the confirmed dependency pairs — `precedes` = ref done first, `follows` = ref done later; `relation_id` filled when the Redmine relation is created (`precedes` type; Redmine mirrors `follows` automatically).
- Task `description` follows the 3b template: `Part of story #<ref>` + `## Deliverable` / `## Scope of work` / `## Acceptance` (tracing the story's AC) / `## Out of scope` / `## Dependencies` (mirroring `depends_on`) / `## Risks` (the problems justifying the estimate).
- Keep the static-list keys verbatim (a `redmine init` run may have written them); this skill only manages the `plan` key plus the lists it needed to fetch itself.
- **Gotcha**: re-running `redmine init` rewrites `.redmine` from scratch and drops the `plan` section — after any `redmine init`, re-persist `plan` from the last confirmed state (read it back first if the file still has it, or ask the user to re-confirm the stored tree).

---

## 6. Gotchas checklist

- [ ] A failed relation creation is reported, not fatal — tell the user which pair to retry.
- [ ] No create-version MCP tool → new versions are created in the Redmine UI by the user/admin; never pretend a version exists.
- [ ] Tracker and priority IDs differ per instance — never assume a "Story"/"Task" tracker exists or an ID→name mapping; take them from the live list.
- [ ] Strip `<insecure-content-...>` wrapper tags from any Redmine-sourced names you reuse.
- [ ] Read-only mode (`REDMINE_MCP_READ_ONLY`) blocks all creation — detect it early and finish with Checkpoint 1 only (proposal + state).
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
