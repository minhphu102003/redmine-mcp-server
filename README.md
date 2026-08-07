# Redmine MCP Server

Redmine MCP Server connects your AI coding agent (opencode, Claude Code, VS Code, ...) to your Redmine instance. But it is **not just a box of tools** — it ships with agent skills that package a complete workflow: install the skills into your repo once, and your agent automates the whole "commit → Redmine issue" loop end-to-end. You only confirm each step; the agent does the rest.

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

**You only confirm. Everything else is automated.** Confirmations use your agent's structured ask UI (opencode `question`, Claude Code `AskUserQuestion`), so you pick from real option lists — no IDs to memorize, no text to draft.

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

See [.env.example](./.env.example) for all available settings (read-only mode, attachment cleanup, SSL, SSRF protection, ...).

### 3. Connect your MCP client

The server exposes MCP at `http://127.0.0.1:8000/mcp`. Register it in your agent. The `X-Redmine-*` headers are required only when `REDMINE_AUTH_MODE=dynamic` — in the default `legacy` mode the server uses the API key from `.env.docker` and ignores them:

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
<summary><b>Claude Code</b> — `claude mcp add`</summary>

```bash
claude mcp add --transport http redmine http://127.0.0.1:8000/mcp \
  --header "X-Redmine-URL: https://redmine.yourcompany.com" \
  --header "X-Redmine-API-Key: your_api_key"
```
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

This repo ships three skills that teach your agent the workflow above:

- [`redmine-init`](./skills/redmine-init/README.md) — maps the current repo to its Redmine project and writes the `.redmine` cache (project ID, members, trackers, ...)
- [`redmine-issue-workflow`](./skills/redmine-issue-workflow/README.md) — creates/updates Redmine issues from GitHub commits and PRs (author mapping, `[FE/BE/Devops]` naming, description template, changelog, time logging)
- [`redmine-planning`](./skills/redmine-planning/README.md) — plans a goal or meeting notes into a structured plan (Epic → Story → Task) in two checkpoints: a confirmed proposal first, then an architecture-grounded task breakdown (estimates, assignees, dependencies) before bulk-creating everything in Redmine

Install all three into your repo with one command (opencode and Claude Code auto-scan `.agents/skills/`):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

**GitHub OAuth is built in** — the workflow authenticates to GitHub through the `gh` CLI (device flow, no tokens to paste):

```bash
gh auth login
```

Then restart your agent, run `redmine init` once in your repo, and start with e.g. *"create a Redmine issue for this commit"*.

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
