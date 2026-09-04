# Redmine MCP Server

> 🌐 Tiếng Việt: [README.vi.md](./README.vi.md) · 한국어: [README.ko.md](./README.ko.md) · 日本語: [README.ja.md](./README.ja.md) · 中文: [README.zh.md](./README.zh.md)

Your AI agent works with Redmine so you don't have to. Connect once, install a skill, then just talk — *"create a Redmine issue for this commit"*, *"is An on track this week?"*, *"generate test cases for this story"* — and confirm each step. The agent does the rest.

## Who are you? Pick your lane

| 👔 Boss / Manager | 💻 Developer | 🧪 Tester |
|---|---|---|
| Ask about one employee at a time — *"what is An working on?"*, *"any overdue tasks?"* — and get a visual day/week performance widget grouped by project. Read-only, nothing can be changed by accident. | Commits and PRs become Redmine issues automatically: naming, description, verified IDs, changelog, time logging. You only confirm. | User stories become test cases, bugs flow between Google Sheets and Redmine, statuses sync back. You review and approve. |

Each lane is powered by an agent skill below. Tell your agent which lane you're in with one sentence, and it takes it from there.

## Quick start — 5 minutes

### 1. Get your Redmine API key

Log in to Redmine, open **My account → API access key → Show** and copy the key.

> Redmine 6.1+ can use per-user OAuth2 login instead of a shared key — see [OAuth Setup](./docs/oauth-setup.md). Managers: the oversight skill needs an **admin** key to resolve people.

### 2. Start the server with Docker

```bash
cp .env.example .env.docker
# set REDMINE_URL and REDMINE_API_KEY in .env.docker, then:
docker compose up --build -d
curl http://localhost:8000/health
```

See [.env.example](./.env.example) for all settings (auth modes, read-only mode, SSL, ...).

### 3. Install the skills for your lane (one command)

**For developers** (issue workflow, planning, daily report):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-dev.ps1 | iex
```

**For testers** (QA test management with Google Sheets):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-tester.ps1 | iex
```

**For both** (all skills):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

### Where do I run these commands?

- 💻 **Developers — run it inside your repo.** Open a terminal in the repository you work in and paste the command there. The script finds the repo root via `git` and drops the skills into `<repo>/.agents/skills/` (opencode and Agent SDK auto-scan it). No repo, no skills — the dev workflow needs your code next to it.
- 🧪 **Testers — you don't need a repo.** If you do work in one, the tester command above works the same way. Otherwise skip it and use a desktop app instead (below): the user-level install or the ZIP upload puts the QA skills where Claude Desktop, Codex, or opencode desktop can see them — no repository required.
- 👔 **Boss — no repo, no terminal habits needed.** Install a desktop app ([Claude Desktop](https://claude.ai/download), [Codex](https://developers.openai.com/codex/), or [opencode](https://opencode.ai/docs) desktop), connect it to the server once (step 4), then get the oversight skill via the user-level install or the ZIP upload below. From then on it's just chatting.

Then restart your agent and say hello:

- 👔 *"Show me the employee list"* → pick a name → *"this week"*
- 💻 Run `redmine init` once in your repo, then *"create a Redmine issue for this commit"*
- 🧪 *"Generate test cases for this user story"* (needs the Google Sheets setup below)

> **GitHub access is built in** — the dev workflow reads commits/PRs through the `gh` CLI (device flow, no tokens to paste): `gh auth login`.

### 4. Connect your agent to the server

The server speaks MCP at `http://127.0.0.1:8000/mcp`. Example for opencode (`opencode.json`):

```json
{
  "mcp": {
    "redmine": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "X-Redmine-URL": "https://redmine.yourcompany.com",
        "X-Redmine-API-Key": "your_api_key"
      }
    }
  }
}
```

The `X-Redmine-*` headers are only needed in `dynamic` auth mode; the default `legacy` mode uses the key from `.env.docker`. Configs for Claude Desktop, VS Code, Grok, Codex, and Cline live in [integrations.md](./docs/integrations.md). Keep secrets out of git (`"{env:REDMINE_API_KEY}"`, `env_http_headers`, ...). Restart your agent after editing.

### 5. Google Sheets (testers only)

The QA skills track test cases and bugs in Google Sheets via a service account:

1. In [Google Cloud Console](https://console.cloud.google.com): enable **Google Sheets API**, create a **Service Account**, add a **JSON key**, save it as `credentials/service-account.json`.
2. Share your spreadsheet (Editor) with the service account email, e.g. `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com`.
3. Paste the sheet URL/ID when `redmine init` (tester flow) asks for it. Sheet ID = the middle of `docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`.

## All skills

| Skill | Lane | What you say → what you get |
|---|---|---|
| [`redmine-init`](./skills/redmine-init/README.md) | 💻 Dev | *"map this repo"* → repo ↔ Redmine project linked, members/trackers cached |
| [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) | 💻 Dev | *"issue for this commit"* → verified issue created, PR merge → status/time logged |
| [`redmine-planning`](./skills/redmine-planning/README.md) | 💻 Dev | *"break down this story"* → estimated, assigned tasks with dependencies |
| [`redmine-daily-report`](./skills/redmine-daily-report/README.md) | 💻 Dev | *"daily report"* → business + technical summary of yesterday |
| [`boss-project-oversight`](./skills/boss-project-oversight/README.md) | 👔 Boss | *"An's performance this week"* → interactive widget by project (read-only, admin key) |
| [`testcase-generation`](./skills/testcase-generation/README.md) | 🧪 Tester | *"test cases for this story"* → reviewed cases written to Sheets |
| [`bug-reporting`](./skills/bug-reporting/README.md) | 🧪 Tester | *"log this bug"* → bug row with auto ID on Sheets |
| [`bug-to-redmine`](./skills/bug-to-redmine/README.md) | 🧪 Tester | *"push bugs to Redmine"* → issues created, IDs written back |
| [`status-sync`](./skills/status-sync/README.md) | 🧪 Tester | *"are devs done fixing?"* → sheet statuses synced from Redmine |
| [`reopen-bug`](./skills/reopen-bug/README.md) | 🧪 Tester | *"reopen BUG-001"* → issue reopened via allowed workflow, sheet updated |

### For Claude Desktop users (testers & boss: no repo needed)

Claude Desktop imports skills as ZIP files — ideal when you don't work inside a repository. Build them with:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

Then **Settings → Customize → Skills → Add Skill → Upload ZIP** (repeat per skill):

| ZIP | Lane |
|---|---|
| `redmine-init` | 💻 Dev starter |
| `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug` | 🧪 Tester |
| `boss-project-oversight` | 👔 Boss |

### For user-level install (opencode global / ChatGPT desktop)

Prefer this when you want skills **everywhere**, not just one repo — opencode and the ChatGPT desktop app both auto-scan `%USERPROFILE%\.agents\skills\`. This is the easiest path for 🧪 testers and 👔 boss working in desktop apps (opencode, Codex, ChatGPT) with no repository involved:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

Installs 7 skills (`redmine-init`, `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug`, `boss-project-oversight`) plus their template files (`README.md` excluded). Hitting GitHub rate limits on re-runs? Set `$env:GITHUB_TOKEN = "<your_pat>"` first (`public_repo` scope is enough). Uninstall: `Remove-Item -Recurse -Force $env:USERPROFILE\.agents\skills`.

## 🎬 Video guides (tester & boss)

Short walkthroughs — watch first, then follow the steps above. (Links go live here once recorded; each row keeps its placeholder until then.)

| Lane | Video | Link |
|---|---|---|
| 🧪 Tester | Setup: desktop app + server connection + QA skills install | *coming soon* <!-- VIDEO-TESTER-SETUP: replace with https://... --> |
| 🧪 Tester | Usage: first end-to-end run (story → test cases → bug → Redmine) | *coming soon* <!-- VIDEO-TESTER-USAGE: replace with https://... --> |
| 👔 Boss | Setup: desktop app + read-only connection + oversight skill | *coming soon* <!-- VIDEO-BOSS-SETUP: replace with https://... --> |
| 👔 Boss | Usage: employee list → pick a person → day/week performance widget | *coming soon* <!-- VIDEO-BOSS-USAGE: replace with https://... --> |

## Under the hood

The server exposes **39 MCP tools** the skills call on your behalf: issues (create/list/update/relations), time entries, wiki pages, personnel & performance summaries, global search, plus Google Sheets and memory tools. See [MCP Tools](./docs/mcp-tools.md) and [Tool Reference](./docs/tool-reference.md).

| Auth mode | When to use |
|---|---|
| `legacy` (default) | Single user / shared credential — one API key in `.env` |
| `oauth` | Per-user login, Redmine 6.1+ — see [OAuth Setup](./docs/oauth-setup.md) |
| `dynamic` | Multi-tenant / shared VPS — agent sends `X-Redmine-URL` + `X-Redmine-API-Key` per request |

Set with `REDMINE_AUTH_MODE=legacy|oauth|dynamic`. Public deployments: prefer `oauth`/`dynamic`; boss machines: add `REDMINE_MCP_READ_ONLY=true`.

## Docs

- [MCP Tools](./docs/mcp-tools.md) — all tools and MCP resources
- [Tool Reference](./docs/tool-reference.md) — detailed parameter reference
- [Docker & VPS deployment](./docs/docker-deployment.md) — local Docker detail, hardened VPS + HTTPS setup
- [Claude Desktop setup](./docs/claude-desktop-setup.md) — MCP + skills on Claude Desktop
- [OAuth Setup](./docs/oauth-setup.md) — per-user OAuth2 (Redmine 6.1+)
- [Troubleshooting](./docs/troubleshooting.md) — common issues
- [Contributing](./docs/contributing.md) — development setup
- [Changelog](./CHANGELOG.md)

## License

MIT — see [LICENSE](./LICENSE).
