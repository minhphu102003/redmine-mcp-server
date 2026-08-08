# redmine-daily-report skill

A user-facing agent skill that writes a **personal daily work report** from yesterday's real activity — commits in the current repository plus Redmine issues that changed that day — in a fixed two-part template: a **Business** part (jargon-free, for leaders at any level) and a **Technical** part (`Shipped / In flight / Blocked on`, for the dev team). The user always approves the final text; delivery to a chat channel only happens when a send capability is configured at install time, otherwise the report is presented for copy-paste.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, usage and troubleshooting.

---

## 1. How the skill works

| Step | What happens |
|---|---|
| 1 | **Clarify** — confirms the report date (default: yesterday; Monday → asks about the previous working day), the person (default: current user via `git config` + `.redmine` `user_mappings`), and commit scope (all vs. author-filtered) |
| 2 | **Gather** — reads the `.redmine` cache (fresh ≤ 14 days) or fetches live project context; runs `git log` for the date window (subject + body); queries Redmine issues with `updated_on` in the window; reads **PR descriptions / commit bodies** to learn what was actually done (never titles alone); collects **business context** (parent story `So that` value, version/sprint goal); asks the user for blockers directly |
| 3 | **Draft** — fills the fixed two-part template: **Business** (what advanced + what it means for the business, jargon-free for leaders — derived from confirmed context, never invented) and **Technical** (`Shipped / In flight / Blocked on`, English, ≤ 10 lines, links to issues/PRs, `—` for empty sections). Shipped lines describe the real work + solution flow from PR descriptions/commit bodies — never titles, and never commit hashes |
| 4 | **Approval gate (mandatory)** — iterates with the user until the final text is explicitly approved ("chốt"); nothing is handed over or sent before that |
| 5 | **Delivery (optional)** — if a delivery config was set at install time (`{{MESSAGE_DELIVERY}}`), sends the approved text to the configured channel; otherwise presents a copy-paste block |

Key rules: **nothing is invented** (no fake commits/issues/blockers — empty data is reported as empty), **business lines always trace to confirmed context** (story `So that`, version goal, project context, or the user's own words — no context → `[?]` and ask, never impact claims), blockers always come from the user, and the report is **personal only** (team/aggregate reports are declined, one person per run).

---

## 2. Installation

This repo ships the skill at `skills/redmine-daily-report/` as a **distribution copy**. It is not auto-loaded from here — install it into the repository where you want to use it, then restart your agent.

### One-liner installer (recommended)

Run this from the repository you develop in — it downloads the `SKILL.md` files into `.agents/skills/` of that repository (this skill plus the `redmine-init`, `redmine-issue-workflow` and `redmine-planning` companions):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

If you have a local clone of this repo (e.g. `D:\redmine-mcp-server`), run the script from it instead — no download needed:

```powershell
& D:\redmine-mcp-server\scripts\install-skills.ps1
```

The script installs into `.agents/skills/`, which **opencode and Claude Code / Agent SDK auto-scan** — no config required. You are free to move the skill folder to another location afterwards (see table below).

### Manual copy

| Location | Works with |
|---|---|
| `.agents/skills/redmine-daily-report/` (inside your repo) | opencode + Claude Code + Agent SDK (auto-scan) |
| `.claude/skills/redmine-daily-report/` (inside your repo) | Claude Code + opencode (auto-scan) |
| `.opencode/skills/redmine-daily-report/` (inside your repo) | opencode only |
| `~/.config/opencode/skills/redmine-daily-report/` (global) | opencode, all projects |

Example for opencode (project-level), from the project you want the skill in:

```bash
cp -r <path-to-this-repo>/skills/redmine-daily-report .agents/skills/
```

Then **restart your agent** (quit and reopen opencode / Claude Code) — skills are loaded at startup.

To use the cache fast path, also install the sibling [`redmine-init`](../redmine-init/README.md) skill and run `redmine init` once in your repository — it writes the `.redmine` file this skill reads.

### Optional — configure message delivery (install-time)

For combined requests like *"viết daily report rồi gửi lên channel"*, you can plug in a delivery config that the agent follows **after your approval** — just replace the `{{MESSAGE_DELIVERY}}` placeholder in the installed `SKILL.md`:

| Placeholder value | Behavior |
|---|---|
| a real config (e.g. "send via the Slack MCP `send_message` tool to channel `#daily-report`") | After you approve the final report, the agent sends the exact approved text to that channel |
| empty / left as `{{...}}` / `none` (default) | **No sending** — the skill presents the approved report as a copy-paste block |

Manual: edit the installed `.agents/skills/redmine-daily-report/SKILL.md` and replace the placeholder. Automatic: pass the config to the installer:

```powershell
& D:\redmine-mcp-server\scripts\install-skills.ps1 -MessageDelivery "send via Slack MCP tool to channel #daily-report"
# or explicitly disable sending in the installed copy:
& D:\redmine-mcp-server\scripts\install-skills.ps1 -MessageDelivery "none"
```

Restart your agent after re-installing. The approval gate is always in place regardless of this config.

### Prerequisites

- A running Redmine MCP server (see the server repo [README](../../README.md)) — the skill reads Redmine through your agent's MCP tools.
- `git` — for `git log` of yesterday's commits in the current repository.
- Optional: `gh` CLI authenticated — only when you want merged-PR links in the report.
- Optional: an MCP tool that can send messages to your channel (Slack/Teams/Telegram/...) — only when you configure `{{MESSAGE_DELIVERY}}`.

---

## 3. Usage

### Writing a daily report

> "Viết daily report hôm qua"
> "Tạo báo cáo ngày cho tôi"
> "daily report please"
> "Gửi report hôm nay lên channel" (requires the delivery config, see above)

### Answers the skill will ask for

1. The report date (default: yesterday; Monday → previous working day)
2. Whether to include all commits or only yours
3. Blockers from yesterday (type "none" if nothing)

### What you get

- A fixed two-part English report: **Business** (for leaders — what advanced and what it means, jargon-free, traced to confirmed context) + **Technical** (`Shipped / In flight / Blocked on`, for the dev team, with links to issues/PRs). Shipped lines are written from the PR description / commit body — what was actually done and the solution flow, never titles and never commit hashes
- Full control: you review, edit and **explicitly approve** the final text before anything is sent
- No invented activity: empty days are reported as empty

---

## 4. Troubleshooting

| Problem | Fix |
|---|---|
| Skill not triggering | Restart the agent; confirm the skill file has `name` + `description` frontmatter; check the install path in section 2 |
| Report shows nothing for the date | Likely no commits/time-tracked issues that day — confirm the date (yesterday vs. today) and the repo; fill lines manually if needed |
| Commits from other people appear | Ask the agent to filter by author (`--author`), or trim the lines at approval |
| Redmine project unknown / stale cache | Run `redmine init` once in the repo, or let the skill fetch live data |
| The agent tried to send but nothing was configured | Install-time config is required — replace `{{MESSAGE_DELIVERY}}` (section 2) and restart the agent; without it the skill only presents the draft |
| Report written in the wrong language | The template is English by design; if you want another language, ask the agent explicitly and it adapts for that run |

---

## 5. Keeping the skill up to date

The skill tracks the server's behavior. Update by pulling this repo, then re-running the installer in the repository that uses the skill:

```bash
git pull --rebase
# re-run the one-liner installer from section 2
```

For changes to take effect, **restart the agent** afterwards.
