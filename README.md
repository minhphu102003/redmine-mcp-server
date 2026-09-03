# Redmine MCP Server

Redmine MCP Server connects your AI coding agent (opencode, VS Code, ...) to your Redmine instance. But it is **not just a box of tools** — it ships with agent skills that package a complete workflow: install the skills into your repo once, and your agent automates the whole "commit → Redmine issue" loop end-to-end. You only confirm each step; the agent does the rest.

## The workflow

```
1. redmine init                      (once per repo)
   └─ maps repo ↔ Redmine project, snapshots trackers/statuses/
      priorities/members/custom fields, maps GitHub account ↔
      Redmine member  → writes a .redmine cache (no re-fetching
      on every task)

2. "create issue from commit"        (any time)
   └─ agent reads the commit/PR via gh, applies [FE/BE/Devops]
      naming, auto-drafts the 8-section English description,
      verifies every ID against live Redmine data, then asks
      you once to confirm  → creates the issue

3. "update issue from PR"            (when the PR merges)
   └─ agent moves status → done, done_ratio → 100, appends a
      changelog entry, logs the time  → all confirmed first
```

**You only confirm. Everything else is automated.** Confirmations use your agent's structured ask UI (opencode `question`), so you pick from real option lists — no IDs to memorize, no text to draft.

## Setup — 3 steps to get the workflow running

### 1. Get your Redmine API key

Log in to Redmine, open **My account → API access key → Show** and copy the key.

> Redmine 6.1+ can use OAuth2 per-user login instead of a shared API key — see [OAuth Setup](./docs/oauth-setup.md).

### 2. Run with Docker

```bash
cp .env.example .env.docker
```

Edit `.env.docker` and set at minimum:

```bash
REDMINE_URL=https://redmine.yourcompany.com
REDMINE_API_KEY=your_api_key
```

Then start:

```bash
docker compose up --build -d
```

Verify it is running:

```bash
curl http://localhost:8000/health
```

Alternatively, run the image directly:

```bash
docker build -t redmine-mcp-server .
docker run -p 8000:8000 --env-file .env.docker redmine-mcp-server
```

See [.env.example](./.env.example) for all available settings (read-only mode, SSL, SSRF protection, ...).

### 3. Google Sheets (for testers)

If you use the QA test management skills (`testcase-generation`, `bug-reporting`, etc.), you need to set up Google Sheets access.

**Step 1: Create a Service Account** (one-time, project admin)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or use existing) → enable **Google Sheets API**
3. **APIs & Services → Credentials → Create Credentials → Service Account**
4. Name it (e.g. `redmine-mcp-sheets`) → **Create and Continue** → **Done**
5. Click the service account → **Keys → Add Key → Create new key → JSON**
6. Save the JSON file as `credentials/service-account.json`

**Step 2: Get the Service Account Email**

Your service account email is:
```
redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com
```

**Step 3: Create your Google Sheet and share it**

1. Go to [sheets.new](https://sheets.new) → create a new spreadsheet
2. Name it (e.g. `MyProject - QA Test Management`)
3. Click **Share** → paste `redmine-mcp-sheets@robotic-jet-430316-k5.iam.gserviceaccount.com` → choose **Editor** → **Send**
4. Copy the spreadsheet ID from the URL:
   ```
   https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit
                                         ^^^^^^^^^^^^^^^^^
   ```
5. During `redmine init` (tester flow), paste this URL or ID when asked

The MCP server authenticates with the service account — you only need to share your sheet with its email. The service account email is safe to share; without the JSON key file, it grants no access.

### 4. Connect your MCP client

The server exposes MCP at `http://127.0.0.1:8000/mcp`. Register it in your agent. The `X-Redmine-*` headers are required only when `REDMINE_AUTH_MODE=dynamic` — in the default `legacy` mode the server uses the API key from `.env.docker` and ignores them:

<details>
<summary><b>Claude Desktop</b> — `claude_desktop_config.json`</summary>

**Windows:**

```json
{
  "mcpServers": {
    "redmine": {
      "command": "C:\\Program Files\\nodejs\\npx.cmd",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8000/mcp",
        "--transport",
        "http-only",
        "--header",
        "X-Redmine-URL:https://redmine.yourcompany.com",
        "--header",
        "X-Redmine-API-Key:your_api_key"
      ]
    }
  }
}
```

**macOS:**

```json
{
  "mcpServers": {
    "redmine": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://127.0.0.1:8000/mcp",
        "--transport",
        "http-only",
        "--header",
        "X-Redmine-URL:https://redmine.yourcompany.com",
        "--header",
        "X-Redmine-API-Key:your_api_key"
      ]
    }
  }
}
```

Config file location:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

Restart Claude Desktop after editing.
</details>

<details>
<summary><b>opencode</b> — project `opencode.json`</summary>

```json
{
  "$schema": "https://opencode.ai/config.json",
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

Use `~/.config/opencode/opencode.json` to apply it to all projects. Restart opencode after editing.
</details>

<details>
<summary><b>VS Code</b> — `code --add-mcp`</summary>

```bash
code --add-mcp '{"name":"redmine","type":"http","url":"http://127.0.0.1:8000/mcp","headers":{"X-Redmine-URL":"https://redmine.yourcompany.com","X-Redmine-API-Key":"your_api_key"}}'
```
</details>

<details>
<summary><b>Grok CLI</b> — `grok mcp add`</summary>

```bash
grok mcp add redmine --transport http http://127.0.0.1:8000/mcp \
  -H "X-Redmine-URL: https://redmine.yourcompany.com" \
  -H "X-Redmine-API-Key: your_api_key"
```

Verify with `grok mcp list` or `grok inspect`, then restart Grok.
</details>

<details>
<summary><b>Codex CLI</b> — `~/.codex/config.toml`</summary>

```toml
[mcp_servers.redmine]
url = "http://127.0.0.1:8000/mcp"
http_headers = { "X-Redmine-URL" = "https://redmine.yourcompany.com", "X-Redmine-API-Key" = "your_api_key" }
```

Or register via CLI: `codex mcp add redmine --url http://127.0.0.1:8000/mcp` (headers are set in `config.toml` via `http_headers`, or `env_http_headers` to pull values from environment variables). Verify with `codex mcp list`.
</details>

<details>
<summary><b>Cline</b> — `~/.cline/mcp.json`</summary>

```json
{
  "mcpServers": {
    "redmine": {
      "type": "streamableHttp",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": {
        "X-Redmine-URL": "https://redmine.yourcompany.com",
        "X-Redmine-API-Key": "your_api_key"
      }
    }
  }
}
```

`"type": "streamableHttp"` is required — omitting it silently uses the legacy SSE transport and fails.
</details>

To keep keys out of git, read them from environment variables instead of literals — e.g. `"{env:REDMINE_API_KEY}"` in opencode, `env_http_headers` in Codex. See [integrations.md](./docs/integrations.md) for more examples.

## Install the skills — the workflow itself

This repo ships skills that teach your agent the workflow above:

**Core skills (all users):**
- [`redmine-init`](./skills/redmine-init/README.md) — maps the current repo to its Redmine project and writes the `.redmine` cache (project ID, members, trackers, ...)
- [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) — creates/updates Redmine issues from GitHub commits and PRs (author mapping, `[FE/BE/Devops]` naming, description template, changelog, time logging)
- [`redmine-planning`](./skills/redmine-planning/README.md) — breaks **one user story** down into tasks with the right assignees (optionally via lower-level sub-stories) in two checkpoints: a confirmed, ambiguity-free business proposal first, then an architecture-grounded task breakdown (estimates, assignees, dependencies) before creating everything in Redmine. Never plans a whole sprint at once — stories are processed one at a time to avoid context overflow

**QA skills (testers, requires Google Sheets setup above):**
- [`testcase-generation`](./skills/testcase-generation/README.md) — generates test cases from user stories, writes to Google Sheets
- [`bug-reporting`](./skills/bug-reporting/README.md) — creates bug entries in Google Sheets
- [`bug-to-redmine`](./skills/bug-to-redmine/README.md) — pushes bugs from Google Sheets to Redmine issues
- [`status-sync`](./skills/status-sync/README.md) — syncs Redmine issue statuses back to Google Sheets
- [`reopen-bug`](./skills/reopen-bug/README.md) — reopens bugs on Redmine and Google Sheets

Install skills into your repo with one command (opencode auto-scans `.agents/skills/`):

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

### For Claude Desktop users

Claude Desktop imports skills as ZIP files. Run this script to download and create ZIPs:

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-claude-desktop.ps1 -OutFile install-skills-claude-desktop.ps1; .\install-skills-claude-desktop.ps1
```

This creates ZIP files in `dist/claude-desktop-skills/`. Then:

1. Open Claude Desktop → **Settings** → **Customize** → **Skills**
2. Click **Add Skill** → **Upload ZIP file**
3. Select a ZIP and repeat for each skill you need

Available skill ZIPs (QA-focused):

| Skill | Description |
|-------|-------------|
| `redmine-init` | Maps repo ↔ Redmine project |
| `testcase-generation` | Generates test cases to Google Sheets |
| `bug-reporting` | Logs bugs to Google Sheets |
| `bug-to-redmine` | Pushes bugs to Redmine issues |
| `status-sync` | Syncs Redmine statuses to sheets |
| `reopen-bug` | Reopens fixed bugs |

**GitHub OAuth is built in** — the workflow authenticates to GitHub through the `gh` CLI (device flow, no tokens to paste):

```bash
gh auth login
```

Then restart your agent, run `redmine init` once in your repo, and start with e.g. *"create a Redmine issue for this commit"*.

### For user-level install (opencode global / ChatGPT desktop)

All the install scripts above drop skills into `<repo>/.agents/skills/`. If you want the skills to be available **everywhere** — so they auto-load no matter which directory the agent starts in — install them once at the user level instead. Both opencode and the ChatGPT desktop app auto-scan the same path:

```
%USERPROFILE%\.agents\skills\
```

**For testers (QA skills, recommended for tester machines):**

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

The script installs the 6 tester skills (`redmine-init`, `testcase-generation`, `bug-reporting`, `bug-to-redmine`, `status-sync`, `reopen-bug`) plus any `*.md` template files in each skill folder (e.g. `USER_STORY_TEMPLATE.md`, `member-rules-catalog.md`, `google-sheets-schema.md`). `README.md` is filtered out — only skill payload lands on disk.

**Optional — pass a GitHub token to lift the unauthenticated rate limit:**

By default the script uses the unauthenticated GitHub Contents API (60 requests/hour per IP). That is enough for a single install of all 6 skills. Re-run many times in the same hour and you may hit `403 rate limit exceeded`. To avoid that, set a token first (any PAT with `public_repo` scope is enough since the repo is public):

```powershell
$env:GITHUB_TOKEN = "<your_pat>"; irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

If you skip this and hit the rate limit, just wait an hour or generate a token — the script itself does not require a token to run.

To uninstall: `Remove-Item -Recurse -Force $env:USERPROFILE\.agents\skills`.

> Prefer the per-repo installer (`install-skills-dev.ps1` / `install-skills-tester.ps1` / `install-skills.ps1`) if you work on a single repo — the user-level install is for shared, machine-wide availability.

## Under the hood — the tools powering the workflow

The MCP server provides ~31 tools that the skills call on your behalf: issues (create/list/update/delete/relations), time entries, wiki pages, global search, scrum reports and weekly report export (markdown/docx). See [MCP Tools](./docs/mcp-tools.md) for the full list and [Tool Reference](./docs/tool-reference.md) for parameters.

### Authentication modes

| Mode | When to use | How it works |
|---|---|---|
| `legacy` (default) | Single user / shared credential | One API key in `.env`, used for every request |
| `oauth` | Per-user login, Redmine 6.1+ | Each user authenticates with their own Redmine account; see [OAuth Setup](./docs/oauth-setup.md) |
| `dynamic` | Multi-tenant / shared VPS | The agent sends `X-Redmine-URL` and `X-Redmine-API-Key` headers on each request |

Set the mode with `REDMINE_AUTH_MODE=legacy|oauth|dynamic` in `.env.docker`. For public deployments prefer `oauth` or `dynamic` over `legacy`.

## Docs

- [MCP Tools](./docs/mcp-tools.md) — all tools and MCP resources
- [Tool Reference](./docs/tool-reference.md) — detailed parameter reference
- [OAuth Setup](./docs/oauth-setup.md) — per-user OAuth2 setup (Redmine 6.1+)
- [Troubleshooting](./docs/troubleshooting.md) — common issues
- [Contributing](./docs/contributing.md) — development setup
- [Changelog](./CHANGELOG.md)

## License

MIT — see [LICENSE](./LICENSE).
