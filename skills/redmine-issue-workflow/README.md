# redmine-issue-workflow skill

A user-facing agent skill that teaches **any AI agent** (opencode, Claude Code, Cursor, ...) the exact workflow for creating a Redmine issue from a GitHub commit: verify live Redmine data, map the commit author to a Redmine member, apply the `[FE/BE/Devops]` naming rule and fill the standard English description template. When a fresh `.redmine` cache exists (created by the [`redmine-init`](../redmine-init/README.md) skill), the workflow skips the live lookups and uses the cached IDs directly.

> Agent (LLM) instruction file: [`SKILL.md`](./SKILL.md). This README is for **humans** — installation, how the skill works, and GitHub CLI (`gh`) setup.

---

## 1. How the skill works

The skill is a single Markdown file with frontmatter (`name` + `description`). When you ask your agent to create a Redmine issue from a commit, the agent loads the skill and follows its 7 steps:

| Step | What happens |
|---|---|
| 1 | **Gather Redmine context** — fast path: read the `.redmine` cache (fresh ≤ 14 days); otherwise list projects, fetch project issue context (trackers, members, categories, versions, custom fields, statuses), verify priorities from real issues. Also reads `user_mappings` (GitHub↔Redmine account mapping) if present. |
| 2 | **Read the GitHub repo** — authenticate with `gh` for private repos, clone to a temp dir, read commits via `git log` |
| 3 | **Map commit → issue** — author → Redmine member (uses `.redmine` `user_mappings` if available, otherwise matches against live member list and asks if no confident match), files changed → `[FE]` / `[BE]` / `[Devops]` prefix |
| 4 | **Ask before create** — every parameter is confirmed with you using live option lists (tracker/status/priority/assignee) shown in the agent's structured ask UI (opencode `question`, Claude Code `AskUserQuestion`, Codex `request_user_input`): full list embedded in the question, answer by typing the number/name or picking a shortcut, plain text as fallback |
| 5 | **Create** — `create_redmine_issue` with all 11 required fields, then verify the returned values |
| 6 | **Description** — 8-section English template (Context, User story, Scope, Proposed solution, Related data, Acceptance criteria, Success measurement, PR link) |
| 7 | **Gotchas checklist** — no hardcoded IDs, no guessing, private-repo auth via `gh` |

Key rule: **nothing is assumed** — every ID/name is fetched live from Redmine in the current session, and defaults are only proposals confirmed with you first.

---

## 2. Installation

This repo ships the skill at `skills/redmine-issue-workflow/` as a **distribution copy**. It is not auto-loaded from here — install it into the repository where you want to use it, then restart your agent.

### One-liner installer (recommended)

Run this from the repository you develop in — it downloads only the `SKILL.md` files into `.agents/skills/` of that repository (both this skill and its companion `redmine-init`):

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
| `.agents/skills/redmine-issue-workflow/` (inside your repo) | opencode + Claude Code + Agent SDK (auto-scan) |
| `.claude/skills/redmine-issue-workflow/` (inside your repo) | Claude Code + opencode (auto-scan) |
| `.opencode/skills/redmine-issue-workflow/` (inside your repo) | opencode only |
| `~/.config/opencode/skills/redmine-issue-workflow/` (global) | opencode, all projects |

Example for opencode (project-level), from the project you want the skill in:

```bash
cp -r <path-to-this-repo>/skills/redmine-issue-workflow .agents/skills/
```

Then **restart your agent** (quit and reopen opencode / Claude Code) — skills are loaded at startup. Verify with: ask your agent "list your skills" or check that `redmine-issue-workflow` appears.

To use the cache fast path, also install the sibling [`redmine-init`](../redmine-init/README.md) skill and run `redmine init` once in your repository — it writes the `.redmine` file this skill reads.

### Prerequisites

- A running Redmine MCP server (see the server repo [README](../../README.md)) — the skill talks to Redmine through your agent's MCP tools.
- `gh` CLI installed and authenticated (below) — required for private GitHub repos.
- Read access to the target GitHub repo via `gh`.

---

## 3. Install GitHub CLI (`gh`)

### Windows

```powershell
winget install --id GitHub.cli
```

Alternatives: `choco install gh` (Chocolatey) or download the MSI from <https://github.com/cli/cli/releases>.

After install, open a **new** terminal and check:

```powershell
gh --version
```

### macOS

```bash
brew install gh
```

### Linux

```bash
# Debian/Ubuntu (official repo)
sudo mkdir -p -m 755 /etc/apt/keyrings
wget -qO- https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null
sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update && sudo apt install gh

# or Fedora/RHEL: sudo dnf install 'dnf-command(config-manager)' && sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo && sudo dnf install gh
```

---

## 4. Authenticate `gh` with GitHub (OAuth)

The skill needs `gh` authenticated so your agent can read private repos (commits, PRs) on your behalf. `gh` uses **GitHub OAuth** with the device flow (you authorize in a browser, no passwords or tokens pasted).

```bash
gh auth login
```

Answer the prompts **exactly** like this:

1. `What account do you want to log into?` → **GitHub.com**
2. `What is your preferred protocol for Git operations?` → **HTTPS**
3. `Authenticate Git with your GitHub credentials?` → **Yes**
4. `How would you like to authenticate GitHub CLI?` → **Login with a web browser** (this is the OAuth device flow)
5. Copy the one-time code shown (e.g. `XXXX-XXXX`), press Enter — your browser opens `https://github.com/login/device`; paste the code and click **Authorize github**.
6. You may be asked for your GitHub password and a 2FA code in the browser — after authorizing, the terminal shows `✓ Logged in as <your-username>`.

> The browser step is the OAuth authorization. The token `gh` stores is scoped to **`repo`** by default (read/write private repos) plus `read:org` — exactly what the workflow needs. `gh auth login` also runs `git config --global credential.helper` so plain `git clone` of private repos works in future terminals.

### Verify the login

```bash
gh auth status
gh api user
```

- `gh auth status` must show `Logged in to github.com as <user>` and `Token scopes: 'repo', 'read:org', 'gist'` (read-only vs read-write is fine either way).
- If you see `not logged in`, re-run `gh auth login`.

### Alternative: personal access token (PAT)

If the browser flow is unavailable (e.g. headless server), use a PAT:

1. GitHub → **Settings → Developer settings → Personal access tokens → Tokens (classic)** → **Generate new token**.
2. Select scopes: **`repo`** (all private repos) and **`read:org`**.
3. Copy the token, then `gh auth login` → choose **Paste an authentication token** → paste it.

Security notes:

- Never paste a token in chat, issues, or commits; if it leaks, **revoke it immediately** at <https://github.com/settings/tokens>.
- `gh` stores the token in `~/.config/gh/hosts.yml` (Windows: `%APPDATA%\GitHub CLI\hosts.yml`) — never commit this file.
- To check which repos your agent can read before asking for an issue: `gh repo view <owner>/<repo>`.

---

## 5. Troubleshooting

| Problem | Fix |
|---|---|
| Skill not triggering | Restart the agent; confirm the skill file has `name` + `description` frontmatter; check the install path in section 2 |
| `gh` not found by the agent | The agent's shell needs a new environment — restart the agent after installing `gh` |
| `gh auth status` → `not logged in` | Re-run `gh auth login` (section 4) |
| `gh repo view` → 404 | You have no access to that repo, or login lacks `repo` scope — check `gh auth status` and re-login |
| `get_project_issue_context` has no `statuses` | Server is an older version — update it, or rely on the skill's fallback (`list_redmine_issue_statuses`) |
| Redmine asks for priority but none shown | The `priorities` section comes from `get_project_issue_context` — requires read access on Redmine |
| Stale-cache warning on create | The `.redmine` cache is older than 14 days — re-run `redmine init` to refresh, or continue with live data |

---

## 6. Keeping the skill up to date

The skill tracks the server's behavior (e.g. `get_project_issue_context` returning `statuses`). Update by pulling this repo, then re-running the installer in the repository that uses the skill:

```bash
git pull --rebase
# re-run the one-liner installer from section 2
```

For changes to take effect, **restart the agent** afterwards.
