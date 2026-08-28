# redmine-planning skill

A user-facing agent skill that **breaks ONE user story down into tasks** (optionally via lower-level sub-stories) and assigns the right people — inside Redmine, without plugins, without new server code. It runs in **two checkpoints** you control:

1. **Checkpoint 1 — Proposal**: the agent clarifies every ambiguous business point of your story with you (context, role, capability, value, acceptance criteria — never self-interpreted), optionally splits it into sub-stories, you iterate until you confirm ("chốt"), then the confirmed story is saved as **state JSON in `.redmine`** — nothing is written to Redmine yet.
2. **Checkpoint 2 — Commit**: you say "tiếp tục / lưu lên Redmine" — the agent reads the repo architecture **only from designated files** (`AGENTS.md` / `CLAUDE.md` / `ARCHITECTURE.md`; if missing, it **asks you**, it never scans the repo), breaks the story into tasks (estimates = implementation time + 20 % buffer, leaf tasks 4–8 h, each justified with the risks it may hit; assignees from module ownership), confirms the whole batch once, then creates the story, sub-stories and tasks through the Redmine MCP server.

**Scope — one user story per run.** The skill never plans a whole sprint/epic: teams can be large and business logic complex, so a full sprint overflows the context. If you ask for a sprint plan, it declines and asks for the first story — the rest are processed one at a time.

You review and steer the tasks afterwards in Redmine's native **Roadmap** (versions) and **Gantt** views.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. Why this skill exists

Redmine's planning UI is basic: no drag-and-drop board, no sprint planner. That is a **process gap**, not a hard limit — Redmine natively supports everything a breakdown needs:

- **Issue hierarchy** (parent → child) = Story → Task
- **Issue relations** (precedes/follows/blocks) = dependencies — "task nào nên làm trước"
- Built-in **Gantt chart** and calendar
- Versions with a built-in **Roadmap** view (progress %, due dates)
- Trackers, priorities, assignees, estimates, custom fields

This skill closes the gap by making the **agent** the breakdown workflow: one template, one naming convention, one confirmation step, one batch create. The UI stays basic; the process becomes consistent.

---

## 2. How the skill works

| Step | What happens |
|---|---|
| 1 | Gathers project context (trackers, versions, members, priorities, custom fields) — via the `.redmine` cache when fresh, otherwise live. **The plan always targets the repo's project** — planning another project/repo is refused (no context/architecture for its breakdown) |
| 2 | Captures **ONE story**: guided (asks subject → business intent → acceptance criteria) or from notes (you paste text / point at a wiki page) or an existing Redmine issue |
| 3 | **Checkpoint 1** — clarifies all ambiguous business points with you (`[?]` markers, **never self-interpreted**; a technically infeasible requirement is asked back: re-scope / alternative / drop), optionally proposes sub-stories (business level only), drafts the user-story proposal (Context + User story + Acceptance criteria) |
| 4 | Iterates with you until you confirm the proposal — every `[?]` answered by you first; **nothing written to Redmine yet** |
| 5 | Persists the confirmed story as **state JSON** in the `.redmine` `plan` section (one plan = one story's breakdown), then asks: "lưu lên Redmine luôn không?" |
| 6 | **Checkpoint 2** — on your go-ahead, reads architecture **only from `AGENTS.md` / `CLAUDE.md` / `ARCHITECTURE.md`** (missing → asks you; **never scans the repo**) |
| 7 | **Breaks the story (and each sub-story) into tasks**: estimate = implementation time + 20 % buffer, leaf tasks kept in the **4–8 h band** (merge smaller / split larger), each estimate justified with the problems it may hit; assignees from module ownership; collects dependencies ("task nào nên làm trước") |
| 8 | Finalizes the batch (tracker mapping, version, priority, assignee; **dates only if you give them**), confirms once, then creates: story → sub-stories → tasks as subtasks, then the dependencies as issue relations (`precedes`) |
| 9 | Marks the state `created` with Redmine IDs and reports the tree + dependency summary with links to Roadmap/Gantt |
| 10 | **Update mode** any time later: "thêm task vào story X", "đổi estimate", "task A trước task B", "chuyển version" — state JSON stays in sync |

---

## 3. Installation

Same installer as the other skills — after installation the folder lives at `.agents/skills/redmine-planning/` and auto-loads on restart:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

If the installer does not list this skill yet (older commit), copy manually:

```bash
cp -r <path-to-this-repo>/skills/redmine-planning .agents/skills/
```

Then **restart your agent** (quit and reopen opencode / opencode) — skills are loaded at startup.

### Prerequisites

- A running Redmine MCP server (see the server repo [README](../../README.md)) — the skill talks to Redmine through your agent's MCP tools.
- Recommended: run `redmine init` once in the repo first — the planning skill reuses the `.redmine` cache (project, trackers, members, versions) as a fast path. It also works without it (live lookups).
- Optional (recommended for a clean hierarchy): ask your Redmine admin to create **Story** and **Task** trackers if they do not exist. Without them the skill uses existing trackers you pick from the live list.

---

## 4. Usage

### Breaking a story down

> "Breakdown user story 'Add refund support' thành các task và gán người phù hợp"
> "Tách task cho story #123"
> "Lập kế hoạch cho story này: <dán mô tả story>"

### From notes

> "Đây là story tôi muốn breakdown: <dán ghi chú>"

### Updating an existing plan

> "Thêm task 'Viết unit test cho parser' vào story #123, 4h"
> "Đổi estimate của task #456 thành 8h và chuyển sang version 1.3"
> "Cập nhật plan: chuyển hết task của story #789 sang story #790"
> "Task 'Implement refund API' phải làm trước task 'Build refund UI'"

---

## 5. What you get

- **Two checkpoints, you stay in control**: the proposal is reviewed and confirmed **before** anything touches Redmine; the confirmed state is saved as JSON in `.redmine`, so you can pause and resume ("tiếp tục plan") anytime.
- **Token-friendly**: the agent **never scans the repo** — architecture context comes only from `AGENTS.md` / `CLAUDE.md` / `ARCHITECTURE.md`, or from questions to you.
- **Small batches**: one user story per run — no context overflow from a whole sprint; several stories are processed one at a time.
- **Breakdown grounded in reality**: tasks are broken down only after architecture grounding — each estimate follows the mandatory rule (**implementation time + 20 % buffer**, leaf tasks kept in the 4–8 h band) and is justified with the problems the task may hit; assignees come from module ownership — not guesses.
- **You stay in control of the content**: at Checkpoint 1 every ambiguous business point (Context / role / capability / value / acceptance criteria) is a question for you, marked `[?]` — and if a requirement is **not technically feasible**, the agent asks you how to proceed (re-scope / alternative / drop) instead of silently changing it.
- **One plan in memory, one project**: `.redmine` holds a single plan (one story's breakdown) at a time — starting a new plan replaces the old state (you confirm first; issues already created in Redmine are untouched). The plan always belongs to the **repo's project** (the `.redmine` top-level `project`); planning another repo is refused because the agent has no architecture context for its breakdown.
- **Dependencies ("task nào nên làm trước")**: recorded as real Redmine issue relations (`precedes`/`follows`), so the Gantt chart shows the correct order of work.
- **You control the schedule**: the agent **never proposes dates** — start/due dates are set only when you explicitly give them (scheduling depends on context complexity only you know).
- **Consistent structure**: the story has Context + User story + Acceptance criteria + Out of scope + Notes & open questions; every task is one 4–8 h deliverable with a full description (Deliverable / Scope of work / Acceptance tracing the story's AC / Out of scope / Dependencies / Risks); estimates roll up.
- **One confirmation for the batch**: no per-issue questions, no ID hunting — you pick from real option lists (trackers, versions, members, priorities).
- **Visibility in native Redmine**: Roadmap (`/projects/<id>/roadmap` — needs a version), Gantt (`/projects/<id>/issues/gantt`), and the regular issue list with parent/child links.

---

## 6. Limitations (by design)

| Limitation | Workaround |
|---|---|
| No drag-and-drop board / sprint planner UI | The skill standardizes the breakdown process instead; views are Roadmap + Gantt + issue tree |
| **One story per run** — a whole sprint is not planned at once | Give the stories one at a time; each gets its own two checkpoints and its own state |
| **No create-version MCP tool** — a brand-new version cannot be created from the chat | Create the version once in the Redmine UI (`/projects/<id>/versions/new`) or ask an admin, then re-run the plan |
| No `Story`/`Task` trackers on some instances | The skill asks you to pick existing trackers from the live list (or admin creates them) |
| Read-only server (`REDMINE_MCP_READ_ONLY`) | Creation is blocked — the skill detects this and offers a text-draft of the plan instead |
| **Planning another project/repo** | **Refused by design** — the breakdown needs that repo's architecture context, which the skill does not have. Use the `redmine-issue-workflow` skill for ad-hoc issues in other projects |

---

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| Skill not triggering | Restart the agent; confirm the file has `name` + `description` frontmatter; check the install path in section 3 |
| It wants to scan the repo / browse files | It must not — architecture comes from `AGENTS.md` / `CLAUDE.md` / `ARCHITECTURE.md` or questions; point the agent at these files |
| Wants a version that doesn't exist | Create it in the Redmine UI (see section 6) and re-run the plan |
| Plan created but Roadmap shows nothing | The issues need a `fixed_version_id` (version) — pick one during confirmation, or add via "cập nhật plan: gán version" |
| `.redmine` `plan` section disappeared | A `redmine init` refresh rewrote the file — re-persist the plan state (or re-confirm the stored tree) |
| Issues have no start/due dates | Expected — dates are only set when you provide them; add them anytime via "cập nhật plan: đặt ngày bắt đầu/kết thúc cho <id>" |
| Estimates/assignees look off | They are proposals; adjust any node afterwards with "đổi estimate của <id> thành <n>h" / "gán <id> cho <tên>" |

---

## 8. Keeping the skill up to date

The skill tracks the server's behavior. Update by pulling this repo, then re-running the installer in the repository that uses the skill:

```bash
git pull --rebase
# re-run the one-liner installer from section 3
```

For changes to take effect, **restart the agent** afterwards.
