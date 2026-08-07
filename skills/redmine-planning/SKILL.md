---
name: redmine-planning
description: Use when the user wants to plan or create a structured plan in Redmine, e.g. "lập kế hoạch", "planning", "tạo plan", "lên kế hoạch cho quý/sprint/tháng", "breakdown task", "epic", "user story", "roadmap", "kế hoạch cho project", "tạo kế hoạch từ ghi chú", "add tasks to the plan", "thêm task vào plan", "cập nhật plan", "đổi estimate", "chuyển version", "task nào làm trước", "dependon", "dependency". The plan always belongs to the repo's project (the top-level `project` in `.redmine`) — planning a different project/repo is refused because the agent lacks that repo's context and architecture for the breakdown. Runs in two checkpoints: (1) turns a natural-language goal or meeting notes into a proposal of user stories in the defined format (Epic → Story), iterates with the user until the proposal is confirmed — every ambiguous business point (context, role, capability, value, acceptance criteria) is resolved by the user through questions, never self-interpreted — then persists the confirmed state as JSON in the `.redmine` plan section — nothing is written to Redmine yet; (2) after the user explicitly says to continue, grounds the plan in the repository architecture read ONLY from designated files (AGENTS.md / CLAUDE.md / ARCHITECTURE.md) or from questions to the user — never by scanning the repo — breaks each story into tasks (estimates = implementation time + 20 % buffer, leaf tasks kept in the 4–8 h band, each estimate justified with the risks it covers; assignees from module ownership), collects dependencies ("task nào nên làm trước") as precedes/follows issue relations, then bulk-creates issues + relations via the Redmine MCP tools and marks the state as created. Also covers updating an existing plan (add tasks to a story, change estimates/version/priority, add/remove dependencies). Use ONLY for planning work — NOT for creating a single issue from a commit/PR (use redmine-issue-workflow), NOT for init/refresh of the `.redmine` cache (use redmine-init).
---

# Redmine Planning

Turn a goal into a structured, visible plan inside Redmine — without plugins, without new server code. You (the agent) act as the **planning interface**, in **two checkpoints** the user can pause between:

```
Checkpoint 1 — PROPOSAL (no Redmine writes)
  natural-language goal/notes
    → you draft user stories in the defined format
    → iterate until the user confirms ("chốt")
    → persist confirmed state to .redmine as JSON (plan section)
    → ask: continue to Redmine? (yes → checkpoint 2, no → stop, state is kept)

Checkpoint 2 — COMMIT (writes to Redmine)
  user says continue
    → read architecture ONLY from designated files
      (AGENTS.md / CLAUDE.md / ARCHITECTURE.md) — never scan the repo;
      files missing → ask the user instead
    → break each story into tasks (complexity → estimates,
      module ownership → assignees) and collect dependencies
      ("task nào nên làm trước" → precedes/follows)
    → confirm the whole batch once (dates: user decides)
    → bulk-create epics → stories+subtasks → issue relations →
      mark state "created" with IDs
```

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (e.g. Redmine MCP tools). No platform/planning MCP server is required: everything happens through the Redmine MCP server the user already configured.

---

## 1. Core rules

1. **Two checkpoints, explicit user gate**: Checkpoint 1 never writes to Redmine. Checkpoint 2 only starts after the user explicitly agrees to continue. Each checkpoint ends with a report; the user can stop after either.
2. **State lives in `.redmine`**: the confirmed proposal is persisted as JSON in the `plan` section of `.redmine` (schema in Section 6) — the file is the durable state, not the conversation.
3. **Never scan the repository**: architecture context comes ONLY from designated doc files at the repo root (`AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md` — read all that exist) and from questions to the user. If no such file exists, **ask the user** about modules/ownership/complexity — browsing the tree, running `git log`, or reading source to "understand the code" is forbidden (it burns tokens and is the user's explicit rule).
4. **Live data first** — never trust memory or tool-description defaults for Redmine IDs. Exception: a `.redmine` cache with `fetched_at` within **14 days** is a trusted fast path for its static lists (project, trackers, statuses, priorities, members, versions, categories, custom fields). Anything missing from the cache, or dynamic (allowed status transitions, parent-issue validity), must be fetched live. Stale cache → warn and suggest `redmine init`. Planning is not repo-bound: no `.redmine` → live lookups.
5. **Ask-before-create**: every required parameter is confirmed — never silently chosen. Use the agent's structured ask tool (opencode `question` / Claude Code `AskUserQuestion` / Codex `request_user_input`; plain text as fallback). Ask-tool limits: **1–4 questions per call**, **≤ 4 clickable options per question**; for longer live lists (trackers, members, versions) embed the **full numbered list in the question text** and let the user type the number/name. If the ask tool is unavailable or the session is non-interactive → ask in plain text and wait; never proceed on guessed values.
6. **Dates are the user's call — never auto-proposed**: scheduling depends on context complexity only the user knows. Ask once at confirmation; if the user gives none, create the issues with **empty dates**.
7. **Assignees follow real ownership**: from architecture docs (owner sections) + `.redmine` `user_mappings` / live members; "unassigned" is the safe default when unknown.
8. **Issue content is English** (subject + description) unless the user asks otherwise.
9. **The agent drafts everything** — user stories, acceptance criteria, breakdown, estimates — as *proposals*. The user only reviews/edits at confirmation.
10. **Ask, don't interpret**: every ambiguous business point — why the story matters, who uses it (role), what it does (capability), why it is worth it (business value), what counts as done (acceptance criteria) — is resolved by **the user through questions**, never self-interpreted. Unresolved points are marked `[?]` in the draft; the proposal is not confirmed (2d) until the user answers all of them. The same applies to **technical feasibility**: if implementing a business requirement is not feasible (technical gap), ask the user how to proceed (re-scope, alternative approach, or drop) — never silently reword, shrink or drop a requirement to fit what is easy.
11. **The plan always belongs to the repo's project**: the target project is the repo's project — the top-level `project` in `.redmine` (the one `redmine init` mapped). If the user asks to plan a **different project or repo**, **refuse**: "Skill này chỉ planning cho project của repo hiện tại — tôi không có context/architecture của repo kia để breakdown." Never plan another project even if the user insists (offer the redmine-issue-workflow skill for ad-hoc issues there instead).
12. **Read-only guard**: if the server is in read-only mode (`REDMINE_MCP_READ_ONLY`), creation tools return an error — detect it early and tell the user Checkpoint 2 cannot write; offer to finish Checkpoint 1 (proposal + state) only.

---

## 2. Checkpoint 1 — Proposal (no Redmine writes)

### 2a. Gather context

1. **Cache check (fast path)**: if a `.redmine` file exists at the git worktree root, read it — fresh (≤ 14 days) → reuse its static lists; stale → warn + suggest `redmine init`; ID missing from cache → fetch that one live; no file → live lookups. Strip `<insecure-content-...>` wrapper tags from any names you reuse.
2. **The target project is fixed — the repo's project**: the top-level `project` in `.redmine` (or fetched per the `redmine-init` skill when no cache). If the user names another project or repo → **refuse** (rule 11): the breakdown needs that repo's context and architecture, which you do not have.
3. **Get project issue context** → trackers, members + roles, categories, versions, statuses, priorities, custom_fields. Priorities come from this call as the complete list — never assume `1=Low, 2=Normal, 3=High, 4=Urgent`.
4. Note whether a version exists that can hold the plan (a version = a sprint/release milestone in Redmine). This context is needed for Checkpoint 2 but cheap to have now.

### 2b. Capture the input

Detect the mode from the user's request; for ambiguity ask "bạn muốn hỏi từng bước hay gửi ghi chú sẵn có?".

**Guided mode** — ask in this order (batch into 1–4 questions per ask call):
1. **Scope**: the repo's project is fixed (rule 11 — never another project); ask only the horizon — sprint / month / quarter / version?
2. **Goals**: "Mục tiêu của kế hoạch này là gì?" (1–3 outcomes the plan must deliver).
3. **Epics**: what are the big work streams (epics)? Propose an initial list from the goals; let the user add/remove.
4. **Stories**: per epic, which user stories — or tell the user "tôi sẽ tự proposal phần còn lại" and draft them (2c), which is the default. **Task breakdown is NOT part of Checkpoint 1** — tasks need the architecture context from Checkpoint 2.
5. **Batch defaults** (one ask call): default priority, default assignee (or "unassigned"), default estimate per task, target version (or "new version needed"). **Dates are NOT part of the defaults.**

**From-notes mode**:
1. Ask the user to paste the notes (or point at a wiki page via the wiki-read capability).
2. Parse the notes into the same tree (epics → stories). Preserve explicit facts (names, dates, priorities, owners, any ordering hints); mark anything unclear as a **question** in the confirmation step — never invent facts. Note ordering hints (e.g. "làm X trước rồi mới Y") for the dependency step in Checkpoint 2.
3. Follow the same batch-defaults ask call as guided mode.

### 2c. Draft the proposal (user-story format)

Structure at Checkpoint 1 — **two levels only**; the task breakdown happens in Checkpoint 2 after architecture grounding (3b):

```
Epic (node type: epic)
└─ Story (node type: story)
```

- **Epic subject**: short English noun phrase, e.g. `Payment flow revamp`. Description: Context (why), Goals/outcomes, In scope / Out of scope.
- **Story subject**: short English capability statement. Description: the user-story template below.
- **Story estimates (proposals)**: default 4–8 h per implied work unit (batch default, user-tunable); epic = sum of its stories. (Final task-level estimates are fixed in Checkpoint 2: implementation time + 20 % buffer, leaf tasks 4–8 h — see 3b.) Story points custom field — if the project defines one, ask whether to fill it.
- **Assignees (proposals)**: batch default, or per-node overrides the user asks for. Real ownership grounding happens in Checkpoint 2.
- **Dependencies (proposals, optional)**: note any ordering the user states ("task nào nên làm trước") — store as `depends_on` refs in Checkpoint 1 state if explicit, otherwise propose them in Checkpoint 2 (3c).

Story description template (you draft fully in English):

```markdown
## Context
- Why this story matters / problem it solves.

## User story
- **As a** [role]
- **I want** [capability]
- **So that** [business value]

## Acceptance criteria
- [ ] AC1: [verifiable outcome]
- [ ] AC2: [verifiable outcome]
```

Rules: user story uses exactly **As a → I want → So that**, each phrase **bolded**; keep section headers verbatim; fill only the bullet content.

**No self-interpretation**: Checkpoint 1 is where **all ambiguous business points are clarified with the user** — before or while drafting each story, surface every uncertainty in Context (why it matters), role (who uses it), capability (what it does), business value (why it is worth it) and acceptance criteria (what proves it done) as **questions to the user**. The user resolves them; you never fill the gap from assumptions. Keep each unresolved point visible in the draft as `[?]` (e.g. `- [ ] AC2: [?]`); the proposal cannot be confirmed (2d) while any `[?]` remains.

**Technical feasibility**: if a business requirement cannot be implemented as stated (technical gap — no API available, platform limit, architecture conflict, ...), ask the user how to proceed (re-scope, alternative approach, or drop it) and mark the point `[?]` — never silently adapt the requirement to what is easy to build.

### 2d. Iterate until the user confirms ("chốt")

1. Present the full draft tree (subjects + descriptions + estimates + assignee/priority proposals, totals per epic). List every `[?]` from 2c as open questions first — the **user** resolves each ambiguous business point; you never self-interpret.
2. Apply every adjustment the user makes and re-present — **repeat until the user explicitly confirms the proposal**. Do not accept "chốt" while a `[?]` is still unanswered: each one is a question for the user, not a guess you are allowed to make. Never skip to Checkpoint 2 on your own judgment.
3. On confirmation, summarize the decisions: project, tracker mapping (epic/story/task), priority, assignee (or unassigned), version (or "create via UI"), story-points field (if applicable). **Ask about dates separately, only if the user wants to set them** — leave empty otherwise.

### 2e. Persist state to `.redmine`

Write the confirmed proposal into the `plan` section of `.redmine` (exact schema in Section 5), `status: "proposed"`, with a per-node `ref` (E1, S1, T1...) and parent links. If `.redmine` does not exist (e.g. no `redmine init` run), create it with the plan section plus the static lists you fetched in 2a, keeping the exact schema and the top-level `project` set to the **repo's** project (never another project — rule 11). Verify the file parses as JSON and contains no wrapper tags.

**One plan in memory**: the `plan` section holds **exactly one plan at a time**. If a plan already exists (even a `"created"` one), warn the user it will be replaced and ask to confirm before overwriting — issues already created in Redmine are NOT affected. Set `created_at` (ngày tạo của plan) when the plan is first persisted; bump `updated_at` on every later change.

### 2f. Checkpoint-1 report

Show: tree summary, estimate totals, where the state is stored, and ask — *"Bạn muốn lưu lên Redmine luôn không?"* (yes → Checkpoint 2; no → stop here, state is kept for later; user can resume with "tiếp tục plan X").

---

## 3. Checkpoint 2 — Commit (writes to Redmine)

Only run after the user explicitly agrees to continue (2f). If the user resumes later, start by reading the `plan` section back from `.redmine`.

### 3a. Architecture grounding — designated files only, or ask

1. At the repo root, read **all** of these files if they exist: `AGENTS.md`, `CLAUDE.md`, `ARCHITECTURE.md` (plus a `docs/architecture.md` if present at the root of docs/). Use them for: module/layer breakdown (to sanity-check epics), ownership hints, complexity signals.
2. **If none of these files exist → do NOT scan the repo. Ask the user instead**, e.g.: "Repo này chưa có AGENTS.md/ARCHITECTURE.md — mô tả giúp: (a) hệ thống gồm những module/layer nào?, (b) ai phụ trách module nào?, (c) module nào phức tạp nhất?" Use the answers to adjust epics, estimates and assignee proposals.
3. Map ownership → assignees via `.redmine` `user_mappings` or the live members list; no match → keep the batch default or "unassigned" (never guess).
4. **Feasibility re-check**: if the architecture contradicts a confirmed story (the business requirement is not implementable as stated — technical gap), ask the user how to proceed (re-scope, alternative approach, or drop) — never silently rewrite the story to fit the architecture.

### 3b. Break down tasks (architecture-driven)

With the architecture context from 3a, break **every story into tasks** (one task = one deliverable) — this is where complexity, estimates and assignees become concrete:

- **Tasks follow real modules**: name tasks after the components the story touches (from 3a). No architecture info → ask the user for the module breakdown; never guess module names.
- **Estimate rule (mandatory)**: `estimate = implementation time × 1.2` — the time the task actually takes to implement **plus a 20 % buffer** for the problems listed below. Round to sensible half-hours.
- **Size rule (mandatory)**: every leaf task must be between **4 h and 8 h**. A task needing < 4 h → merge it into a related task (re-scope the deliverable); a task needing > 8 h → split it into several tasks. Story = sum of its tasks; epic = sum of its stories.
- **Prove the estimate with risks**: for every task, list the problems it may hit ("các vấn đề có thể gặp phải") — unclear requirements, tricky integration, hidden dependencies, platform limits, test-data setup, ... — that justify the estimate is just enough. Put them in the task description as a `## Risks` section and surface them again in the 3e confirmation.
- **Assignees from ownership**: per task, assign the owner of that module (3a step 3 → `.redmine` `user_mappings` / live members); no owner → batch default or "unassigned".
- Task description: single-paragraph deliverable + `Part of story #<ref>` + `## Risks` bullet list.

### 3c. Dependencies — "task nào nên làm trước"

1. **Collect ordering**: the user's stated ordering (from 2b/2c) + module-dependency hints from 3a (e.g. "API trước, UI sau").
2. **Propose `precedes` pairs** (task A precedes task B ⇒ A must be done first); only between tasks of the plan (or tasks ↔ stories when the user wants story-level ordering). Optional `delay` in days.
3. **Confirm the dependency list** with the user; record each pair in the state as `depends_on` refs (A `depends_on` B means B must be done first — B precedes A). Never invent dependencies beyond architecture hints; ask when unsure.

### 3d. Finalize fields

- **Trackers**: ask which live tracker maps to each level (Epic / Story / Task) if not already decided — full numbered list from live data. If no dedicated `Epic`/`Story` trackers exist, the user picks existing ones; never invent a tracker. If the user wants a proper `Epic` tracker, note an admin must create it first (then re-run).
- **Version**: prefer an existing version (full numbered list). A **new** version cannot be created via MCP — tell the user to create it in the Redmine UI (`/projects/<identifier>/versions/new`) or ask an admin, then continue; alternatively proceed without a version.
- **Status**: `New` (confirm the live ID).
- **Dates**: ask once — if the user gives none, create with empty dates.

### 3e. Confirm the whole batch once

Present the final tree (epics → stories → tasks) with all resolved values (tracker/priority/assignee/version/status per node, estimate totals) **plus the dependency list** in one compact summary + 1–4 ask questions for any remaining decisions. Each task line shows its estimate and the key risks justifying it (from 3b). Apply adjustments and re-present once if the user asks for a restructure.

### 3f. Bulk-create

1. **Create epics first** (create-issue capability, no parent) → collect the returned IDs.
2. **Per story**: create-issue-with-subtasks capability (parent = story, subtasks = its tasks), with `parent_issue_id` = the epic's ID. The tool enforces: parent exists, same project, parent not itself a subtask — epics are plain issues so this holds.
3. **Create the dependencies** — after all issues exist, for each confirmed `precedes` pair call the create-issue-relation capability (`issue_id` = the issue that must be done first, `issue_to_id` = the dependent issue, `relation_type: "precedes"`, optional `delay`). Redmine mirrors the complementary `follows` automatically. A failed relation is reported, not fatal — tell the user which pair to retry.
4. **Verify the returned values** (status/priority/tracker names especially) — mismatch → update that issue with the correct value.
5. **Mark state created**: update the `.redmine` `plan` section — `status: "created"`, each node gets its `redmine_id`, each created relation gets its `relation_id` under the pair; `created_at` recorded. Verify the file parses.

### 3g. Checkpoint-2 report

The full tree with issue URLs, estimate totals per epic, **the dependency summary** (which task must finish before which), and links to the native views — Roadmap: `<redmine-url>/projects/<identifier>/roadmap` (when a version is set), Gantt: `<redmine-url>/projects/<identifier>/issues/gantt` (relations are drawn as arrows). Close with: "plan đã lưu — sửa bất cứ lúc nào qua 'cập nhật plan'".

---

## 4. Update an existing plan

Use when the user asks to change an existing plan (state is in `.redmine` `plan`, or find by issue ID / subject search: one match → use it; multiple → ask; none → ask for the ID).

| Request | Action |
|---|---|
| Add task to a story | create-issue with `parent_issue_id` = story ID (confirm fields); update state JSON with the new node + `redmine_id` |
| Add a new story to an epic | create-issue with `parent_issue_id` = epic ID; update state JSON |
| Change estimate / priority / assignee / dates / version / status | update-issue capability with confirmed fields; update state JSON |
| Move tasks between stories | update-issue `parent_issue_id` per task; re-balance estimates (ask); update state JSON |
| Add a dependency ("task X trước task Y") | create-issue-relation capability (`precedes`, optional delay); update state JSON `depends_on` |
| Remove a dependency | delete-issue-relation capability with the pair's `relation_id`; update state JSON |
| Cancel a node | confirm; update status to `Closed`/`Rejected` (confirm live ID) or delete only if the user explicitly asks; update state JSON |

Report what changed with URLs. Invalid status transition → fetch allowed statuses and suggest the nearest valid one. Whenever state changes, **keep `.redmine` `plan` in sync** and re-verify the JSON parses.

---

## 5. `.redmine` plan state schema (exact)

The `plan` section is written by this skill (Checkpoint 1) and updated through Checkpoint 2 / updates. Example (shows one epic with one story and one task):

```json
{
  "version": 1,
  "project": {"id": 12, "name": "Example Project", "identifier": "example-project"},
  "trackers": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Feature"}],
  "statuses": [{"id": 1, "name": "New", "is_closed": false}, {"id": 5, "name": "Closed", "is_closed": true}],
  "priorities": [{"id": 2, "name": "Normal"}, {"id": 3, "name": "High"}],
  "members": [],
  "versions": [],
  "categories": [],
  "custom_fields": [],
  "required_custom_fields": [],
  "user_mappings": [],
  "fetched_at": "2026-08-07T00:00:00Z",
  "plan": {
    "status": "proposed",
    "version_id": null,
    "decisions": {
      "tracker_epic_id": 2,
      "tracker_story_id": 3,
      "tracker_task_id": 4,
      "priority_id": 2,
      "assignee_default": null,
      "story_points_field_id": null
    },
    "nodes": [
      {"ref": "E1", "type": "epic", "subject": "Payment flow revamp", "description": "## Context\n- ...", "estimate_hours": 12, "priority_id": 2, "redmine_id": null},
      {"ref": "S1", "type": "story", "subject": "Add refund support", "description": "## Context\n- ...", "estimate_hours": 8, "priority_id": 2, "parent": "E1", "depends_on": [], "redmine_id": null},
      {"ref": "T1", "type": "task", "subject": "Implement refund API endpoint", "description": "Refund API endpoint\n\n## Risks\n- Refund calculation edge cases\n- External payment provider limits", "estimate_hours": 4.8, "priority_id": 2, "parent": "S1", "depends_on": ["T2"], "redmine_id": null},
      {"ref": "T2", "type": "task", "subject": "Build refund UI", "description": "...", "estimate_hours": 4, "priority_id": 2, "parent": "S1", "depends_on": [], "redmine_id": null}
    ],
    "relations": [
      {"precedes": "T2", "follows": "T1", "relation_id": null}
    ],
    "created_at": "2026-08-07T00:00:00Z",
    "updated_at": "2026-08-07T00:00:00Z"
  }
}
```

Rules:
- `status`: `"proposed"` after Checkpoint 1; `"created"` after Checkpoint 2 succeeds.
- **The plan always belongs to the repo's project**: the target project is the top-level `project.id` — `plan` carries no `project_id` of its own. Planning a different project/repo is refused (rule 11) — never write a `plan` for another project, and re-verify after any `redmine init` that the top-level `project` still matches the repo before continuing.
- **The `plan` section holds exactly one plan at a time** — starting a new plan replaces the old `plan` state (confirm with the user first; already-created Redmine issues are untouched).
- `created_at`: ngày tạo của plan — set when the plan is first persisted (Checkpoint 1); `updated_at` bumps on every state change.
- `redmine_id`: `null` until the issue is created, then the real ID.
- `depends_on` (per node): refs of nodes that must be **done first** ("task nào nên làm trước"). Confirmed in 3c.
- `relations`: the confirmed dependency pairs — `precedes` = ref done first, `follows` = ref done later; `relation_id` filled when the Redmine relation is created (`precedes` type; Redmine mirrors `follows` automatically).
- Task `description` includes the deliverable, `Part of story #<ref>`, and a `## Risks` section (the problems justifying the estimate, from 3b).
- Keep the static-list keys verbatim (a `redmine init` run may have written them); this skill only manages the `plan` key plus the lists it needed to fetch itself.
- Strip all `<insecure-content-...>` wrapper tags from names.
- **Gotcha**: re-running `redmine init` rewrites `.redmine` from scratch and drops the `plan` section — after any `redmine init`, re-persist `plan` from the last confirmed state (read it back first if the file still has it, or ask the user to re-confirm the stored tree).

---

## 6. Gotchas checklist

- [ ] Two checkpoints: Checkpoint 1 writes **nothing** to Redmine; Checkpoint 2 starts only on the user's explicit "continue".
- [ ] State is durable in `.redmine` `plan` — never rely on the conversation alone; keep it in sync on every change.
- [ ] **Never scan the repository** — architecture comes only from `AGENTS.md` / `CLAUDE.md` / `ARCHITECTURE.md` (+ `docs/architecture.md`); files missing → ask the user.
- [ ] **Task breakdown happens only in Checkpoint 2** (after architecture grounding) — never in Checkpoint 1; complexity → estimates, module ownership → assignees.
- [ ] **No self-interpretation at Checkpoint 1**: every ambiguous business point (Context / role / capability / value / acceptance criteria) is a question for the user, marked `[?]` in the draft — the proposal is never confirmed while any `[?]` remains. Same for a **technical gap** (requirement not feasible to implement): ask the user how to proceed (re-scope / alternative / drop), never silently change the requirement.
- [ ] **Estimate rule**: `estimate = implementation time × 1.2`; every leaf task must be **4–8 h** (merge tasks < 4 h, split tasks > 8 h); each task's description lists the risks ("các vấn đề có thể gặp phải") proving the estimate is just enough.
- [ ] **One plan in memory**: `.redmine` `plan` holds exactly one plan at a time — starting a new plan replaces the old state (confirm first; Redmine issues are unaffected).
- [ ] **Plan scope = the repo's project**: the plan always targets the top-level `project` of `.redmine`; planning another project/repo is **refused** (no context/architecture for its breakdown) — even if the user insists.
- [ ] **Dependencies**: collect/confirm the ordering ("task nào nên làm trước") in 3c; create relations **only after both issues exist** (3f step 3) with `precedes`; Redmine mirrors `follows` automatically — never create both directions.
- [ ] A failed relation creation is reported, not fatal — tell the user which pair to retry.
- [ ] `redmine init` rewrites `.redmine` and drops `plan` — re-persist after any refresh.
- [ ] No create-version MCP tool → new versions are created in the Redmine UI by the user/admin; never pretend a version exists.
- [ ] Tracker names differ per instance — never assume an "Epic" tracker exists; ask from the live list.
- [ ] Priority IDs differ per instance — never assume an ID→name mapping.
- [ ] **Dates are never proposed** — the user decides them manually; create with empty dates when the user gives none.
- [ ] Assignees come from architecture docs / `user_mappings` / live members; "unassigned" is the safe default when unknown.
- [ ] Read-only mode (`REDMINE_MCP_READ_ONLY`) blocks all creation — detect and finish with Checkpoint 1 only (proposal + state).
- [ ] Strip `<insecure-content-...>` wrapper tags from any Redmine-sourced names you reuse.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
