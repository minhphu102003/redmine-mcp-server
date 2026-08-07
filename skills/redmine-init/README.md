# redmine-init skill

A user-facing agent skill that maps the current repository to its Redmine project and writes a `.redmine` JSON cache file at the git root. The cache snapshots the project ID and the static ID lists (trackers, statuses, priorities, members, versions, categories, custom fields) with a `fetched_at` timestamp, so the `redmine-issue-workflow` skill can create issues without re-fetching live data on every task.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

Running `redmine init` once in a repository:  

| Step | What happens |
|---|---|
| 1 | Detects the git worktree root (`git rev-parse --show-toplevel`) |
| 2 | Lists all Redmine projects (`list_redmine_projects`) |
| 3 | Asks you which project the repository corresponds to |
| 4 | Fetches full project context (trackers, members, categories, versions, statuses, priorities, custom fields) |
| 5 | **Maps GitHub account ↔ Redmine member** — detects your GitHub identity via `gh api user`, matches against the project member list, confirms with you, and optionally maps additional committers. Stored in `.redmine` for reuse. |
| 6 | **Asks for each member's working rules** — role/stack (backend, frontend, mobile, devops, AI, DA, QA, ...) and personal conventions (tests, review, AI-tool usage, reporting...). You can answer or skip per member ("bỏ qua"); nothing is invented. Stored in `.redmine` (`member_rules`). |
| 7 | Strips server wrapper tags and writes `.redmine` (JSON) at the repo root |

The file is a snapshot with a `fetched_at` timestamp. Consumers such as `redmine-issue-workflow` use it as the fast path while it is fresh (TTL: **14 days**) and tell you to re-run `redmine init` when it is stale.

---

## 2. Installation

This repo ships the skill at `skills/redmine-init/` as a **distribution copy**. It is not auto-loaded from here — install it into the repository where you want to use it, then restart your agent.

### One-liner installer (recommended)

Run this from the repository you develop in — it downloads only the `SKILL.md` files into `.agents/skills/` of that repository (both this skill and its consumer `redmine-issue-workflow`):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

If you have a local clone of this repo (e.g. `D:\redmine-mcp-server`), run the script from it instead — no download needed:

```powershell
& D:\redmine-mcp-server\scripts\install-skills.ps1
```

The script installs into `.agents/skills/`, which **opencode and Claude Code / Agent SDK auto-scan** — no config required. You are free to move the skill folders to another location afterwards (see table below).

### Manual copy

| Location | Works with |
|---|---|
| `.agents/skills/redmine-init/` (inside your repo) | opencode + Claude Code + Agent SDK (auto-scan) |
| `.claude/skills/redmine-init/` (inside your repo) | Claude Code + opencode (auto-scan) |
| `.opencode/skills/redmine-init/` (inside your repo) | opencode only |
| `~/.config/opencode/skills/redmine-init/` (global) | opencode, all projects |

Example for opencode (project-level), from the project you want the skill in:

```bash
cp -r <path-to-this-repo>/skills/redmine-init .agents/skills/
```

Also copy `redmine-issue-workflow` (see its [README](../redmine-issue-workflow/README.md)) — it is the consumer that reads the cache when creating issues.

Then **restart your agent** (quit and reopen opencode / Claude Code) — skills are loaded at startup.

### Prerequisites

- A running Redmine MCP server (see the server repo [README](../../README.md)) — the skill talks to Redmine through your agent's MCP tools.

---

## 3. Usage

1. Open a session in the repository and ask: `redmine init`
2. Answer the question about which Redmine project the repo maps to.
3. Confirm the GitHub ↔ Redmine member mapping (the agent detects your GitHub identity via `gh` and suggests the match).
4. For each mapped member, answer (or skip with "bỏ qua") their working rules — role/stack and personal conventions. The agent prompts with a researched catalog of rule areas per role.
5. The agent writes `.redmine` at the repo root and reports a summary.
6. Later, re-run `redmine init` any time to refresh the snapshot (e.g. when you get a stale-cache warning, or after team/member changes).

The `.redmine` file contains no secrets (IDs, names and roles only) — it is safe to commit so the whole team shares the mapping.

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| Skill not triggering | Restart the agent; confirm the skill file has `name` + `description` frontmatter; check the install path in section 2 |
| `.redmine` maps the wrong project | Re-run `redmine init` and confirm the correct project |
| Stale-cache warning when creating issues | Re-run `redmine init` to refresh `fetched_at` |

---

## 5. Keeping the skill up to date

The skill tracks the server's behavior. Update by pulling this repo, then re-running the installer in the repository that uses the skill:

```bash
git pull --rebase
# re-run the one-liner installer from section 2
```

For changes to take effect, **restart the agent** afterwards.
