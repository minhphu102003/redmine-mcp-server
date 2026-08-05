# Redmine MCP Tools (Current Repository)

This document provides a comprehensive summary of every MCP tool, resource,
prompt, and HTTP route currently exposed by the `redmine-mcp-server`.

- Implementation: `src/redmine_mcp_server/redmine_handler.py`
- Tool internals (dependency-injected): `src/redmine_mcp_server/handler_impl/tools/`
- Detailed per-tool reference with examples: [Tool Reference](./tool-reference.md)
- Client bootstrap guide: [client-bootstrap-prompt.md](./client-bootstrap-prompt.md)

## Surface summary

| Kind | Count |
|---|---|
| MCP tools (`@mcp.tool()`) | 28 |
| MCP resources (`@mcp.resource()`) | 6 |
| MCP prompts (`@mcp.prompt()`) | 29 (1 global + 28 per-tool) |
| Custom HTTP routes (`@mcp.custom_route()`) | 3 |

## Quick reference (all 28 tools)

| Tool | Category | Description |
|---|---|---|
| [`get_redmine_issue`](#get_redmine_issue) | Issues | Retrieve a specific issue by ID (journals, attachments, custom fields, watchers, relations, children) |
| [`list_redmine_issues`](#list_redmine_issues) | Issues | List issues with flexible filtering and pagination |
| [`search_redmine_issues`](#search_redmine_issues) | Issues | Search issues matching a text query |
| [`create_redmine_issue`](#create_redmine_issue) | Issues | Create a new issue (template enforcement, required custom-field autofill) |
| [`create_redmine_issue_with_subtasks`](#create_redmine_issue_with_subtasks) | Issues | Create one parent issue plus multiple subtasks in a single call |
| [`update_redmine_issue`](#update_redmine_issue) | Issues | Update an existing issue |
| [`list_redmine_issue_statuses`](#list_redmine_issue_statuses) | Issues | List all issue statuses defined in Redmine |
| [`get_redmine_issue_allowed_statuses`](#get_redmine_issue_allowed_statuses) | Issues | Get allowed status transitions for a specific issue |
| [`get_redmine_project_workflow`](#get_redmine_project_workflow) | Issues | Infer project workflow from issue-level allowed statuses (sample-based) |
| [`get_issue_workflow_context`](#get_issue_workflow_context) | Consolidated | Unified entry point for status/workflow context (4 modes) |
| [`list_redmine_projects`](#list_redmine_projects) | Projects | List all accessible projects |
| [`summarize_project_status`](#summarize_project_status) | Projects | Summary of project status over a time period |
| [`get_project_issue_context`](#get_project_issue_context) | Consolidated | Complete issue-creation context for a project (replaces 5 project lookups) |
| [`manage_time_entries`](#manage_time_entries) | Consolidated | Unified time-entry tool (list/create/update/activities) |
| [`list_time_entries`](#list_time_entries) | Time entries | List time entries with filters and pagination |
| [`create_time_entry`](#create_time_entry) | Time entries | Create a new time entry |
| [`update_time_entry`](#update_time_entry) | Time entries | Update an existing time entry |
| [`list_time_entry_activities`](#list_time_entry_activities) | Time entries | List available time-entry activities |
| [`generate_scrum_report`](#generate_scrum_report) | Consolidated | Generate daily/weekly/custom scrum report drafts |
| [`export_weekly_report_markdown`](#export_weekly_report_markdown) | Consolidated | Export weekly report as a markdown file |
| [`export_weekly_report_docx`](#export_weekly_report_docx) | Consolidated | Export weekly report as a `.docx` file |
| [`search_entire_redmine`](#search_entire_redmine) | Search / attachment | Search issues and wiki pages across the instance |
| [`get_redmine_attachment_download_url`](#get_redmine_attachment_download_url) | Search / attachment | Get an HTTP download URL for an attachment |
| [`cleanup_attachment_files`](#cleanup_attachment_files) | Search / attachment | Clean up expired attachment files, return storage stats |
| [`get_redmine_wiki_page`](#get_redmine_wiki_page) | Wiki | Retrieve full wiki page content |
| [`create_redmine_wiki_page`](#create_redmine_wiki_page) | Wiki | Create a new wiki page |
| [`update_redmine_wiki_page`](#update_redmine_wiki_page) | Wiki | Update an existing wiki page |
| [`delete_redmine_wiki_page`](#delete_redmine_wiki_page) | Wiki | Delete a wiki page |

---

## Consolidated tools (recommended for agent workflows)

Consolidated tools group related operations behind one entry point to reduce
tool-selection overhead and token usage in agent workflows. The legacy direct
tools remain available for backward compatibility where noted.

### `get_issue_workflow_context`

Unified entry point for issue-status/workflow context.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `mode` | str | `"issue"` | `"statuses"`, `"issue"`, `"project"`, or `"transition_check"` |
| `issue_id` | int | `None` | Required for `"issue"` and `"transition_check"` modes |
| `project_id` | str/int | `None` | Required for `"project"` mode |
| `tracker_id` | int | `None` | Optional tracker filter (project mode) |
| `status_id` | str/int | `None` | Optional starting status (project mode) |
| `sample_limit` | int | `25` | Max issues sampled to infer workflow |
| `target_status_id` | int | `None` | Target status for `"transition_check"` |
| `target_status_name` | str | `None` | Target status name for `"transition_check"` |

Modes:

- `"statuses"` — list globally defined issue statuses.
- `"issue"` — current status + allowed transitions for one issue.
- `"project"` — infer project workflow snapshot from sampled issues.
- `"transition_check"` — validate whether a target status is currently allowed
  (matches by `target_status_id` or `target_status_name`).

**Returns:** `Dict` with a `mode` key plus `data` (or `error`).

**Example:**

```json
{
  "mode": "transition_check",
  "issue_id": 42,
  "current_status": {"id": 1, "name": "New"},
  "target": {"id": 4, "name": "Closed"},
  "allowed": true,
  "matched_status": {"id": 4, "name": "Closed"}
}
```

---

### `get_project_issue_context`

Fetch complete issue-creation context for a project in a single call.
Consolidates the former project lookups (`list_project_trackers`,
`list_project_issue_categories`, `list_project_members`, `list_redmine_versions`,
`list_project_issue_custom_fields`) so agents get everything needed to create a
task with one call.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | (required) | Project ID or identifier |
| `tracker_id` | str/int | `None` | Restrict custom fields to one tracker |

**Returns:** `Dict` with:

- `project` — id, name, identifier, description, created_on
- `tracker_id` — echoed input tracker filter
- `trackers` — tracker types available for issue creation
- `categories` — issue categories in the project
- `members` — memberships with user/group and roles
- `versions` — versions (roadmap milestones)
- `custom_fields` — custom-field metadata (allowed values, required flags, tracker bindings)
- `required_custom_fields` — custom fields flagged required (directly usable when creating a task)

Sections are fetched concurrently; if one lookup fails, its section keeps the
`{"error": ...}` payload while the other sections are still returned.

**Example:**

```json
{
  "project": {"id": 10, "name": "Core", "identifier": "core", "description": "", "created_on": null},
  "tracker_id": null,
  "trackers": [{"id": 1, "name": "Bug"}, {"id": 2, "name": "Task"}],
  "categories": [{"id": 1, "name": "Frontend", "assigned_to": null}],
  "members": [{"id": 5, "user": {"id": 3, "name": "Alice"}, "roles": [{"id": 3, "name": "Developer"}]}],
  "versions": [{"id": 1, "name": "v1.0", "status": "open"}],
  "custom_fields": [{"id": 6, "name": "Size", "is_required": true, "possible_values": ["S", "M", "L"]}],
  "required_custom_fields": [{"id": 6, "name": "Size", "is_required": true, "possible_values": ["S", "M", "L"]}]
}
```

---

### `manage_time_entries`

Unified entry point for time logging operations.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `action` | str | (required) | `"list"`, `"create"`, `"update"`, or `"activities"` |
| `time_entry_id` | int | `None` | Required for `"update"` |
| `hours` | float | `None` | Required for `"create"` |
| `project_id` | str/int | `None` | Project filter / target |
| `issue_id` | int | `None` | Issue filter / target |
| `user_id` | str/int | `None` | User filter (list only) |
| `activity_id` | int | `None` | Activity for create/update |
| `comments` | str | `None` | Comments for create/update |
| `spent_on` | str | `None` | Date (`YYYY-MM-DD`) for create/update |
| `from_date` | str | `None` | Range start (list only) |
| `to_date` | str | `None` | Range end (list only) |
| `limit` | int | `25` | Page size (list only) |
| `offset` | int | `0` | Page offset (list only) |

**Returns:** `Dict` with an `action` key plus `data` (or `error`).

---

### `generate_scrum_report`

Generate daily/weekly/custom scrum report drafts from logged time entries.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `report_type` | str | `"daily"` | `"daily"`, `"weekly"`, or `"custom"` |
| `user_id` | str/int | `None` | Restrict to one user (cross-project scope) |
| `project_id` | str/int | `None` | Restrict to one project (team scope) |
| `from_date` | str | `None` | Required for `"custom"` |
| `to_date` | str | `None` | Required for `"custom"` |
| `top_n_items` | int | `7` | Number of top items in lists |
| `include_entries` | bool | `False` | Include raw time entries in output |

Behavior:

- `"daily"` — auto-reads the **yesterday** range.
- `"weekly"` — auto-reads the **previous week** range (Mon–Sun).
- `"custom"` — requires both `from_date` and `to_date`; the range limit is
  controlled by `REDMINE_SCRUM_REPORT_MAX_DAYS` (default: 31).

Output includes summary metrics, `top_issues`, `top_activities`, `top_users`,
`report_draft`, and `report_templates` (`standup_three_questions`,
`standup_workflow_focused`, `weekly_status_summary`).

Tips:

- Pass only `project_id` → team-level report across multiple users.
- Pass only `user_id` → individual report across projects.
- Pass both → one user's report inside one project.
- The tool always reads fresh data; re-generate anytime by calling it again.

---

### `export_weekly_report_markdown`

Export a weekly report to a markdown file based on a template.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `user_id` | str/int | `None` | User filter passed to the scrum report |
| `project_id` | str/int | `None` | Project filter passed to the scrum report |
| `top_n_items` | int | `7` | Number of top items |
| `template_path` | str | `docs/templates/weekly_work_report_plan_template.md` | Custom template file |
| `output_dir` | str | `reports/weekly` | Output directory |
| `file_name` | str | auto | Output file name |
| `unit_name` | str | `"TRUNG TÂM CSE"` | Unit name shown in the report |
| `reporter_name` | str | `"NGƯỜI BÁO CÁO"` | Reporter name shown in the report |
| `location` | str | `"Đà Nẵng"` | Location shown in the report |
| `from_date` | str | `None` | Custom range start (falls back to previous week) |
| `to_date` | str | `None` | Custom range end |

Internally calls `generate_scrum_report(report_type="weekly")`, renders the
template, and writes a `.md` file so devs can share/edit quickly.

---

### `export_weekly_report_docx`

Export a weekly report to `.docx` for client delivery.

Same parameters and defaults as `export_weekly_report_markdown`. Reuses the
weekly markdown template and generates a plain-text Word document under
`reports/weekly` (or custom `output_dir`). Current behavior keeps markdown
semantics as text (not native Word tables/headings).

---

## Core issue tools

### `get_redmine_issue`

Retrieve a specific Redmine issue by ID.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `issue_id` | int | (required) | Issue ID |
| `include_journals` | bool | `True` | Include history journals |
| `include_attachments` | bool | `True` | Include attachment metadata |
| `include_custom_fields` | bool | `True` | Include custom fields |
| `journal_limit` | int | `None` | Max journals to return |
| `journal_offset` | int | `0` | Journal pagination offset |
| `include_watchers` | bool | `False` | Include watcher list |
| `include_relations` | bool | `False` | Include issue relations |
| `include_children` | bool | `False` | Include child issues |

**Returns:** `Dict` with issue details.

---

### `list_redmine_issues`

List Redmine issues with flexible filtering and pagination support.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | `None` | Project ID or identifier |
| `status_id` | int | `None` | Filter by status ID |
| `tracker_id` | int | `None` | Filter by tracker ID |
| `assigned_to_id` | str/int | `None` | Filter by assignee (ID or `"me"`) |
| `priority_id` | int | `None` | Filter by priority ID |
| `fixed_version_id` | int | `None` | Filter by target version ID |
| `sort` | str | `None` | Sort expression (e.g. `"priority:desc"`) |
| `limit` | int | `25` | Page size |
| `offset` | int | `0` | Page offset |
| `include_pagination_info` | bool | `False` | Return `total`/`offset`/`limit` wrapper |
| `fields` | list[str] | `None` | Restrict issue fields returned |
| `filters` | dict | `None` | Additional Redmine filters |

**Returns:** `List[Dict]`, or `Dict` with `issues`/`total`/`offset`/`limit` when
`include_pagination_info=True`.

---

### `search_redmine_issues`

Search Redmine issues matching a query string with pagination support.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | str | (required) | Search text |
| `limit` | int | `25` | Page size |
| `offset` | int | `0` | Page offset |
| `include_pagination_info` | bool | `False` | Return pagination wrapper |
| `fields` | list[str] | `None` | Restrict issue fields returned |
| `scope` | str | `None` | Search scope |
| `open_issues` | bool | `False` | Only open issues |
| `options` | dict | `None` | Extra search options |

**Returns:** `List[Dict]` or pagination-wrapped `Dict`.

---

### `create_redmine_issue`

Create a new issue in Redmine.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | int | (required) | Project ID |
| `subject` | str | (required) | Issue subject |
| `description` | str | `""` | Issue description |
| `fields` | dict/str | `None` | Structured fields (tracker, priority, assignee, custom fields...) |
| `extra_fields` | dict/str | `None` | Extra custom fields |

Behavior:

- Respects `REDMINE_MCP_READ_ONLY` (write blocked in read-only mode).
- Validates the description against the issue template when
  `REDMINE_ENFORCE_ISSUE_TEMPLATE=true` (see `redmine://issue-template/default`).
- Autofills required custom fields when autofill is enabled.
- Supports strict input validation via `REDMINE_STRICT_ISSUE_CREATION_INPUTS`.

**Returns:** `Dict` with the created issue.

---

### `create_redmine_issue_with_subtasks`

Create one parent issue and multiple subtasks in a single call.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | int | (required) | Project ID |
| `parent_subject` | str | (required) | Parent issue subject |
| `parent_description` | str | `""` | Parent issue description |
| `parent_fields` | dict/str | `None` | Structured fields for the parent |
| `parent_extra_fields` | dict/str | `None` | Extra custom fields for the parent |
| `subtasks` | list[dict] | `None` | List of subtask specs (subject, description, fields...) |
| `stop_on_subtask_error` | bool | `False` | Abort remaining subtasks on first failure |

**Returns:** `Dict` with parent issue plus per-subtask results.

---

### `update_redmine_issue`

Update an existing Redmine issue.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `issue_id` | int | (required) | Issue ID |
| `fields` | dict | (required) | Fields to update (custom fields can be set by name, e.g. `{"size": "S"}`) |

Behavior: respects read-only mode, autofills required custom fields when
enabled, and disambiguates ambiguous status names instead of silently picking
the first match.

**Returns:** `Dict` with the updated issue.

---

### `list_redmine_issue_statuses`

List all issue statuses defined in Redmine.

**Parameters:** None

**Returns:** `List[Dict]` of statuses (`id`, `name`, `is_closed`, `is_default`).

---

### `get_redmine_issue_allowed_statuses`

Get allowed status transitions for a specific issue.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `issue_id` | int | (required) | Issue ID |

**Returns:** `Dict` with `current_status` and `allowed_statuses`.

---

### `get_redmine_project_workflow`

Infer project workflow from issue-level allowed statuses (sample-based).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | (required) | Project ID or identifier |
| `tracker_id` | int | `None` | Restrict to one tracker |
| `status_id` | str/int | `None` | Restrict to one starting status |
| `sample_limit` | int | `25` | Max issues sampled |

**Returns:** `Dict` with a normalized transition matrix and status list.

---

## Project tools

### `list_redmine_projects`

Lists all accessible projects in Redmine.

**Parameters:** None

**Returns:** `List[Dict]` with `id`, `name`, `identifier`, `description`.

---

### `summarize_project_status`

Provide a summary of project status over the specified time period.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | int | (required) | Project ID |
| `days` | int | `30` | Look-back window in days |

**Returns:** `Dict` with issue analytics and status summary. Raises
`ResourceNotFoundError` for unknown projects.

---

## Time entry tools (legacy direct tools)

### `list_time_entries`

List time entries from Redmine with filtering and pagination.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | `None` | Project filter |
| `issue_id` | int | `None` | Issue filter |
| `user_id` | str/int | `None` | User filter |
| `from_date` | str | `None` | Range start (`YYYY-MM-DD`) |
| `to_date` | str | `None` | Range end (`YYYY-MM-DD`) |
| `limit` | int | `25` | Page size |
| `offset` | int | `0` | Page offset |

**Returns:** `List[Dict]` or pagination-wrapped `Dict`.

---

### `create_time_entry`

Create a new time entry in Redmine.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `hours` | float | (required) | Hours logged |
| `project_id` | str/int | `None` | Project (if not linked to an issue) |
| `issue_id` | int | `None` | Issue the entry is logged against |
| `activity_id` | int | `None` | Activity type ID |
| `comments` | str | `""` | Comments |
| `spent_on` | str | `None` | Date (`YYYY-MM-DD`) |

**Returns:** `Dict` with the created time entry.

---

### `update_time_entry`

Update an existing time entry in Redmine.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `time_entry_id` | int | (required) | Time entry ID |
| `hours` | float | `None` | New hours |
| `activity_id` | int | `None` | New activity type |
| `comments` | str | `None` | New comments |
| `spent_on` | str | `None` | New date |

**Returns:** `Dict` with the updated time entry.

---

### `list_time_entry_activities`

List available time entry activities from Redmine.

**Parameters:** None

**Returns:** `List[Dict]` of activities (`id`, `name`, `is_default`, `active`).

---

## Wiki tools

### `get_redmine_wiki_page`

Retrieve full wiki page content from Redmine.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | (required) | Project ID or identifier |
| `wiki_page_title` | str | (required) | Page title |
| `version` | int | `None` | Specific page version |
| `include_attachments` | bool | `True` | Include attachment metadata |

**Returns:** `Dict` with page text, version, and metadata.

---

### `create_redmine_wiki_page`

Create a new wiki page in a Redmine project.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | (required) | Project ID or identifier |
| `wiki_page_title` | str | (required) | Page title |
| `text` | str | (required) | Page content |
| `comments` | str | `""` | Edit comment |

**Returns:** `Dict` with the created page.

---

### `update_redmine_wiki_page`

Update an existing wiki page in a Redmine project.

Same parameters as `create_redmine_wiki_page`.

**Returns:** `Dict` with the updated page.

---

### `delete_redmine_wiki_page`

Delete a wiki page from a Redmine project.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | str/int | (required) | Project ID or identifier |
| `wiki_page_title` | str | (required) | Page title |

**Returns:** `Dict` confirming deletion.

---

## Search / attachment / maintenance tools

### `search_entire_redmine`

Search for issues and wiki pages across the Redmine instance.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | str | (required) | Search text |
| `resources` | list[str] | `None` | Restrict to resource types |
| `limit` | int | `100` | Max results |
| `offset` | int | `0` | Result offset |

Requires Redmine 3.3.0+. Raises `VersionMismatchError` on unsupported versions.

**Returns:** `Dict` with matches grouped by resource type.

---

### `get_redmine_attachment_download_url`

Get HTTP download URL for a Redmine attachment.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `attachment_id` | int | (required) | Attachment ID |

**Returns:** `Dict` with a time-limited download URL (expiry controlled by
`ATTACHMENT_EXPIRES_MINUTES`, default 60). Served via `GET /files/{file_id}`.

---

### `cleanup_attachment_files`

Clean up expired attachment files and return storage statistics.

**Parameters:** None

**Returns:** `Dict` with cleanup counters and storage statistics.

---

## Resources

Resources expose read-only contracts that agents should load before performing
write operations.

- `redmine://issue-template/default`
  - Issue creation template metadata: `template_markdown`, `required_sections`,
    `enforced`.
  - When `REDMINE_ENFORCE_ISSUE_TEMPLATE=true`, `create_redmine_issue` validates
    description headings against this template.

- `redmine://issue-contract/{project_id}`
- `redmine://issue-contract/{project_id}/{tracker_id}`
  - Issue create/update contract: required base fields, custom fields (required
    flags + allowed values), tracker bindings, linked description template
    contract.

- `redmine://workflow/{project_id}`
- `redmine://workflow/{project_id}/{tracker_id}`
  - Workflow transition contract: sampled workflow snapshot, normalized
    transition matrix (`from -> allowed`), status list for the current auth
    context.

- `redmine://time-entry/contract`
  - Time logging contract: required fields and validation rules, available
    activities (id/name/active/default), create/update payload examples.

## Prompts

### `redmine_server_operating_prompt`

Global operating prompt for this MCP server. Designed to be loaded first by
client/agent orchestration before any tool calls. Client enforcement guide:
`docs/client-bootstrap-prompt.md`.

### Per-tool prompts (28)

Every tool has a corresponding prompt named `<tool_name>_prompt` (e.g.
`get_redmine_issue_prompt`, `manage_time_entries_prompt`,
`cleanup_attachment_files_prompt`). Each prompt renders the tool's objective,
required inputs, recommended resources, pre-checks, and result shape, guiding
agents toward correct usage.

## Custom HTTP routes

| Route | Method | Description |
|---|---|---|
| `/health` | GET | Health check for orchestration |
| `/files/{file_id}` | GET | Serve downloaded attachment files (expiry-checked) |
| `/cleanup/status` | GET | Cleanup task status and storage statistics |

## Notes

- **Consolidated vs legacy tools**: Consolidated tools (`get_issue_workflow_context`,
  `manage_time_entries`, `generate_scrum_report`, `export_weekly_report_markdown`,
  `export_weekly_report_docx`) are recommended for agent workflows; the legacy
  direct tools remain for backward compatibility.
- **Read-only mode**: All write tools (create/update/delete) respect
  `REDMINE_MCP_READ_ONLY` and return an `error` payload when write access is
  disabled.
- **Authentication**: Tools support Legacy (API key / Basic Auth) and OAuth2
  per-user modes via `_get_redmine_client()`. See [oauth-setup.md](./oauth-setup.md).
- **Content safety**: User-controlled content in responses is wrapped with
  `wrap_insecure_content()` (`<insecure-content-...>` tags) so clients do not
  treat remote content as trusted instructions.
- **Error convention**: On failure, tools return `Dict` payloads with an
  `"error"` key (exception types include `ValidationError`,
  `ResourceNotFoundError`, `VersionMismatchError`).
