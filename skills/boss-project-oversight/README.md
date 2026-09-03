# boss-project-oversight skill

Manager-oversight skill for the boss workflow: list personnel → pick one person → day/week performance summary grouped by project.

This repo ships the skill at `skills/boss-project-oversight/` as a **distribution copy**. It is not auto-loaded from here — install it where your agent looks for skills, then restart your agent.

## Install

Per-repo (opencode / Agent SDK auto-scan `.agents/skills/`):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills.ps1 | iex
```

Claude Desktop: run `scripts/install-skills-claude-desktop.ps1` locally to build the ZIP files, then Settings → Customize → Skills → Add Skill → upload `boss-project-oversight.zip`.

User-level (opencode + ChatGPT desktop app auto-scan `~/.agents/skills/`):

```powershell
irm https://raw.githubusercontent.com/minhphu102003/redmine-mcp-server/develop/scripts/install-skills-user.ps1 | iex
```

## Requires

- The MCP server must expose `list_personnel` and `get_person_work_summary` (added in the same release as this skill).
- Boss access: read-only recommended (`REDMINE_MCP_READ_ONLY=true`); person resolution uses the admin `/users.json` API, so the boss API key needs admin rights.

## Widget template

Step 3 of the skill renders from `widget-template.html`, a reference template
living next to `SKILL.md`. The installers copy it alongside the skill payload
(boss skill only — other skills install exactly as before). After updating
the template, re-run the installer so the new file lands next to `SKILL.md`.
