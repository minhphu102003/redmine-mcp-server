---
name: redmine-init
description: Use when the user asks to initialize or refresh the Redmine project mapping for the current repository, e.g. "redmine init", "khởi tạo redmine", "map repo này với project redmine", "tạo file .redmine", "refresh redmine context", "redmine context bị cũ". Creates or refreshes the `.redmine` JSON cache file at the git worktree root, storing the project ID and the static ID lists (trackers, statuses, priorities, members, versions, categories, custom fields) with a `fetched_at` timestamp, so issue-creation skills can create tasks without re-fetching every value. Use ONLY for init/refresh of the cache, NOT for creating issues, logging time, or wiki work.
---

# Redmine Init

This skill creates and refreshes a `.redmine` JSON cache file at the git worktree root of the current repository. The cache maps the repository to exactly one Redmine project and snapshots its static ID lists, so the `redmine-issue-workflow` skill can create issues fast without re-fetching every value.

**IMPORTANT:** Tool calls below are described by **capability**, not by name — use whatever tool the current agent provides (e.g. Redmine MCP tools).

---

## 1. Core principles

- The `.redmine` file is a **snapshot** — it is a trusted source for *static* ID lists (project, trackers, statuses, priorities, members, versions, categories, custom fields) while fresh. It never stores per-issue state (e.g. which priority/status an issue currently has) — that changes hourly and is always fetched live.
- The file is **NOT** a source of truth for *dynamic* state — allowed status transitions, parent-issue validity, or members who joined after the snapshot. Those must still be verified live.
- Freshness is decided by `fetched_at` (ISO 8601, UTC) vs the TTL of **14 days**.
- Tool responses wrap every name in `<insecure-content-...>` tags — **always strip these tags** before writing the cache.
- v1 supports exactly **one project per repository**. For a monorepo that spans multiple Redmine projects, ask the user which project the repo maps to and keep one file.

---

## 2. Init flow (no `.redmine` file yet)

1. **Locate the repo root**: run `git rev-parse --show-toplevel`. The `.redmine` file goes at that root (not the current working directory when they differ). If the directory is not a git repository → ask the user where to place the file.
2. **Check for an existing file**: if `.redmine` already exists at the root → follow the refresh flow (section 3) instead.
3. **List projects**: call the list-projects capability (e.g. `redmine_list_redmine_projects`) → returns `id`, `name`, `identifier`, `description`, `created_on`.
4. **Ask the user to choose**: present the project list (id + name + identifier) and ask "repo này tương ứng với project Redmine nào?" using the agent's ask capability (e.g. the `question` tool). Do NOT guess. If the list is long (> ~30 rows), cap it and ask the user to narrow by keyword.
5. **Fetch project context**: call the project-context capability (e.g. `redmine_get_project_issue_context`, project_id) → returns project, trackers, categories, members (with roles), versions, statuses (`is_closed`), **priorities**, custom_fields, required_custom_fields. The `priorities` section is the **complete** list (e.g. `{"id": 2, "name": "Normal"}`); Redmine has no separate "list priorities" endpoint, the context tool provides it. This caches only the **static option list** (the dropdown of values), never any issue's current priority — per-issue priority state changes hourly and is always fetched live.
6. **Strip wrapper tags**: remove every `<insecure-content-...>` and `</insecure-content-...>` marker from names.
7. **Write `.redmine`**: a single JSON file at the repo root, exact schema in section 4, `fetched_at` = current UTC timestamp (ISO 8601, e.g. `2026-08-06T00:00:00Z`).
8. **Verify**: read the file back; confirm it parses as valid JSON, contains no wrapper tags, and `fetched_at` is set.
9. **Report**: project id/name/identifier, counts of trackers/members/statuses/priorities, the file path, and the reminder: re-run `redmine init` later to refresh; the file is safe to commit (no secrets).

---

## 3. Refresh flow (`.redmine` already exists)

1. Read the existing `.redmine`.
2. **Reuse the stored `project.id`** — do NOT re-ask which project.
3. If the user hints the repo maps to a *different* project than the file says → confirm with the user before overwriting.
4. Re-fetch project context + priorities (step 5 of the init flow) and overwrite the file with a fresh `fetched_at`, keeping the same schema.
5. Verify and report as in init steps 8–9.

---

## 4. `.redmine` schema (exact)

```json
{
  "version": 1,
  "project": {"id": 313, "name": "[AI] Chatbot Tuyển Sinh", "identifier": "ai-chatbot-tuyen-sinh", "created_on": "2026-05-29T01:50:49"},
  "trackers": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Feature"}],
  "categories": [],
  "members": [{"id": 2847, "user": {"id": 79, "name": "Huỳnh Ngọc Đăng Khoa"}, "roles": [{"id": 4, "name": "Developer"}]}],
  "versions": [],
  "statuses": [{"id": 1, "name": "New", "is_closed": false}, {"id": 5, "name": "Closed", "is_closed": true}],
  "custom_fields": [],
  "required_custom_fields": [],
  "priorities": [{"id": 2, "name": "Normal"}],
  "fetched_at": "2026-08-06T00:00:00Z"
}
```

- `version`: `1`.
- `fetched_at`: current time, ISO 8601 with `Z` (UTC).
- Keep keys verbatim; empty lists stay as `[]`.
- Strip all `<insecure-content-...>` wrapper tags from names.

---

## 5. TTL policy

- Default TTL: **14 days**.
- Consumers (`redmine-issue-workflow`) use the cache while `fetched_at` is within TTL, and warn the user + suggest `redmine init` when older.
- This skill never auto-refreshes in the middle of another task — refresh only when invoked.

---

## 6. Gotchas checklist

- [ ] Strip `<insecure-content-...>` wrapper tags before writing; the file must contain clean names only.
- [ ] Write at the **git worktree root** (`git rev-parse --show-toplevel`), not the current working directory when they differ.
- [ ] Not a git repo → ask the user where to place `.redmine`.
- [ ] One project per repo (v1). If a repo maps to multiple projects, ask the user to pick one for the file.
- [ ] Priorities come from the context tool as a complete list — no sampling or guessing; consumers still live-verify an ID absent from the cache instead of inventing one.
- [ ] The file contains no secrets (IDs, names, roles only) — safe to commit for the whole team.
- [ ] After moving/editing this skill file, remind the user to **restart the agent** (quit and reopen opencode / Claude Code) for the skill to load.
