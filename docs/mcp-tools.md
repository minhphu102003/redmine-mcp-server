# Redmine MCP Tools (Current Repository)

This document provides a comprehensive summary of every MCP tool, resource,
and HTTP route currently exposed by the `redmine-mcp-server`.

- Implementation: `src/redmine_mcp_server/redmine_handler.py`
- Tool internals (dependency-injected): `src/redmine_mcp_server/handler_impl/tools/`
- Detailed per-tool reference with examples: [Tool Reference](./tool-reference.md)

## Surface summary

| Kind | Count |
|---|---|
| MCP tools (`@mcp.tool()`) | 39 |
| MCP resources (`@mcp.resource()`) | 4 |
| Custom HTTP routes (`@mcp.custom_route()`) | 1 |

## Quick reference (all 39 tools)

| Tool | Category | Description |
|---|---|---|
| [`get_redmine_issue`](#get_redmine_issue) | Issues | Retrieve a specific issue by ID (journals, attachments, custom fields, watchers, relations, children) |
| [`list_redmine_issues`](#list_redmine_issues) | Issues | List issues with flexible filtering and pagination |
| [`search_redmine_issues`](#search_redmine_issues) | Issues | Search issues matching a text query |
| [`create_redmine_issue`](#create_redmine_issue) | Issues | Create a new issue (template enforcement, required custom-field autofill) |
| [`create_redmine_issue_with_subtasks`](#create_redmine_issue_with_subtasks) | Issues | Create one parent issue plus multiple subtasks in a single call |
| [`update_redmine_issue`](#update_redmine_issue) | Issues | Update an existing issue |
| [`create_redmine_issue_relation`](#create_redmine_issue_relation) | Issues | Create an issue relation (dependency) between two issues |
| [`delete_redmine_issue_relation`](#delete_redmine_issue_relation) | Issues | Delete an issue relation |
| [`list_redmine_issue_statuses`](#list_redmine_issue_statuses) | Issues | List all issue statuses defined in Redmine |
| [`get_redmine_issue_allowed_statuses`](#get_redmine_issue_allowed_statuses) | Issues | Get allowed status transitions for a specific issue |
| [`list_redmine_projects`](#list_redmine_projects) | Projects | List all accessible projects |
| [`get_project_issue_context`](#get_project_issue_context) | Consolidated | Complete issue-creation context for a project (replaces 5 project lookups) |
| [`manage_time_entries`](#manage_time_entries) | Consolidated | Unified time-entry tool (list/create/update/delete/activities) |
| [`list_time_entries`](#list_time_entries) | Time entries | List time entries with filters and pagination |
| [`create_time_entry`](#create_time_entry) | Time entries | Create a new time entry |
| [`update_time_entry`](#update_time_entry) | Time entries | Update an existing time entry |
| [`delete_time_entry`](#delete_time_entry) | Time entries | Delete a time entry |
| [`list_time_entry_activities`](#list_time_entry_activities) | Time entries | List available time-entry activities |
| [`list_personnel`](#list_personnel) | Personnel | List unique project members across projects (boss step 1) |
| [`get_person_work_summary`](#get_person_work_summary) | Personnel | Per-person day/week performance grouped by project with evidence (boss step 3) |
| [`search_entire_redmine`](#search_entire_redmine) | Search | Search issues and wiki pages across the instance |
| [`get_redmine_wiki_page`](#get_redmine_wiki_page) | Wiki | Retrieve full wiki page content |
| [`create_redmine_wiki_page`](#create_redmine_wiki_page) | Wiki | Create a new wiki page |
| [`update_redmine_wiki_page`](#update_redmine_wiki_page) | Wiki | Update an existing wiki page |
| [`delete_redmine_wiki_page`](#delete_redmine_wiki_page) | Wiki | Delete a wiki page |

---

## Consolidated tools (recommended for agent workflows)

Consolidated tools group related operations behind one entry point to reduce
tool-selection overhead and token usage in agent workflows. The legacy direct
tools remain available for backward compatibility where noted.


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
- `statuses` — all issue statuses defined in Redmine (`id`, `name`, `is_closed`)
- `priorities` — all issue priorities defined in Redmine (`id`, `name`)
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
  "statuses": [{"id": 1, "name": "New", "is_closed": false}, {"id": 5, "name": "Closed", "is_closed": true}],
  "priorities": [{"id": 2, "name": "Normal"}, {"id": 4, "name": "High"}],
  "custom_fields": [{"id": 6, "name": "Size", "is_required": true, "possible_values": ["S", "M", "L"]}],
  "required_custom_fields": [{"id": 6, "name": "Size", "is_required": true, "possible_values": ["S", "M", "L"]}]
}
```

---

### `manage_time_entries`

Unified entry point for time logging operations.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `action` | str | (required) | `"list"`, `"create"`, `"update"`, `"delete"`, or `"activities"` |
| `time_entry_id` | int | `None` | Required for `"update"` and `"delete"` |
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
| `parent_id` | int | `None` | Filter by parent issue ID (list subtasks of a task) |
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

Create a new issue in Redmine. All core issue fields are **required** (the
tool refuses to create an issue with any of them missing).

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | int | (required) | Project ID |
| `subject` | str | (required) | Issue subject |
| `description` | str | (required) | Issue description (Textile/Wiki) |
| `tracker_id` | int | (required) | Issue type: 1 (Bug), 2 (Feature), 3 (Support), 4 (Common), 5 (Testing Task) |
| `priority_id` | int | (required) | Priority: 3 = Normal, 4 = High, ... |
| `status_id` | int | (required) | Initial status: 1 = New, 2 = In Progress, ... |
| `assigned_to_id` | int | (required) | Assignee user ID (e.g. 80 = Nguyễn Minh Phú) |
| `start_date` | str | (required) | Start date (YYYY-MM-DD) |
| `due_date` | str | (required) | Due date (YYYY-MM-DD) |
| `estimated_hours` | float | (required) | Estimated hours |
| `done_ratio` | int | (required) | Completion percentage (0-100) |
| `fields` | dict/str | `None` | Extra fields: category_id, fixed_version_id, custom_fields |
| `extra_fields` | dict/str | `None` | Extra custom fields |
| `parent_issue_id` | int/str | `None` | ID of an existing task to create this issue as a subtask of (must be in the same project) |

Behavior:

- Respects `REDMINE_MCP_READ_ONLY` (write blocked in read-only mode).
- Validates the description against the issue template when
  `REDMINE_ENFORCE_ISSUE_TEMPLATE=true` (see `redmine://issue-template/default`).
- Autofills required custom fields when autofill is enabled.
- Supports strict input validation via `REDMINE_STRICT_ISSUE_CREATION_INPUTS`.
- With `parent_issue_id`: the parent is fetched and validated first (must exist
  and belong to the same project; Redmine supports unlimited nesting depth, so
  the parent may itself be a subtask). Without it, a standalone task is created.
- Each returned issue includes a `parent` key (`{"id", "subject"}` or `None`),
  so hierarchy is visible in results.

**Returns:** `Dict` with the created issue, including a `url` key with the web
link to the issue (e.g. `https://redmine.example.com/issues/42`).

---

### `create_redmine_issue_with_subtasks`

Create one parent issue and multiple subtasks in a single call. All core
fields are **required** for the parent and for **every** subtask.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `project_id` | int | (required) | Project ID |
| `parent_subject` | str | (required) | Parent issue subject |
| `parent_description` | str | (required) | Parent issue description |
| `tracker_id` | int | (required) | Parent issue type: 1 (Bug), 2 (Feature), 3 (Support), 4 (Common), 5 (Testing Task) |
| `priority_id` | int | (required) | Parent priority: 3 = Normal, 4 = High, ... |
| `status_id` | int | (required) | Parent initial status: 1 = New, 2 = In Progress, ... |
| `assigned_to_id` | int | (required) | Parent assignee user ID |
| `start_date` | str | (required) | Parent start date (YYYY-MM-DD) |
| `due_date` | str | (required) | Parent due date (YYYY-MM-DD) |
| `estimated_hours` | float | (required) | Parent estimated hours |
| `done_ratio` | int | (required) | Parent completion percentage (0-100) |
| `parent_fields` | dict/str | `None` | Extra fields for the parent (category, version, custom fields) |
| `parent_extra_fields` | dict/str | `None` | Extra custom fields for the parent |
| `subtasks` | list[dict] | `None` | Subtask specs; each requires subject, description, tracker_id, priority_id, status_id, assigned_to_id, start_date, due_date, estimated_hours, done_ratio (plus optional fields/extra_fields) |
| `stop_on_subtask_error` | bool | `False` | Abort remaining subtasks on first failure |

Subtasks missing any required field are reported in `failed_subtasks`, not
created.

**Returns:** `Dict` with parent issue plus per-subtask results. The parent and
each created subtask include a `url` key with the web link to the issue.

---

### `update_redmine_issue`

Update an existing Redmine issue, optionally logging worked time against it.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `issue_id` | int | (required) | Issue ID |
| `fields` | dict | (required) | Fields to update (custom fields can be set by name, e.g. `{"size": "S"}`; may be empty when only logging time) |
| `spent_hours` | float | None | Hours to log as a time entry on this issue (must be > 0); requires no other field changes |
| `activity_id` | int | None | Activity type ID for the logged time entry (see `list_time_entry_activities`) |
| `time_comments` | str | None | Work description for the logged time entry (distinct from `notes`) |
| `spent_on` | str | None | Date the work was done (YYYY-MM-DD), defaults to today |

Behavior: respects read-only mode, autofills required custom fields when
enabled, and disambiguates ambiguous status names instead of silently picking
the first match. When `spent_hours` is set, a time entry is created on the
issue after a successful update; a logging failure keeps the update and
returns the error under `time_entry` with `time_entry_error: true`.

**Returns:** `Dict` with the updated issue, plus a `time_entry` key when `spent_hours` was provided.

---

### `create_redmine_issue_relation`

Create an issue relation (dependency) between two Redmine issues — e.g. task A
`precedes` task B, so the Gantt chart and roadmap reflect "task nào nên làm
trước". Redmine stores one row per relation and mirrors the complementary type
(`follows`, `blocked`, `duplicated`) on the other side automatically.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `issue_id` | int | (required) | ID of the first issue (comes first / blocks / is related) |
| `issue_to_id` | int | (required) | ID of the second issue (comes later / is blocked / is related) |
| `relation_type` | str | (required) | `precedes` / `follows`, `blocks` / `blocked`, `relates`, `duplicates` / `duplicated`, `copied_to` / `copied_from` |
| `delay` | int | None | Optional delay in days (precedes/follows only) |

Behavior: respects read-only mode; validates the relation type, rejects
self-relations, and verifies both issues exist before creating. Both issue
subjects are returned wrapped in insecure-content tags.

**Returns:** `Dict` with `success`, the created `relation` (`id`, `issue_id`,
`issue_to_id`, `relation_type`, `delay`) and both `issues` (id + subject).

---

### `delete_redmine_issue_relation`

Delete an issue relation from Redmine. Respects read-only mode.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `relation_id` | int | (required) | ID of the issue relation to delete |

**Returns:** `Dict` with `success`, `relation_id` and a `message`.

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


### `list_redmine_projects`

Lists all accessible projects in Redmine.

**Parameters:** None

**Returns:** `List[Dict]` with `id`, `name`, `identifier`, `description`.

---


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

### `delete_time_entry`

Delete a time entry from Redmine.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `time_entry_id` | int | (required) | Time entry ID to delete |

**Returns:** `Dict` with `success`, `time_entry_id` and `message`.

---

### `list_time_entry_activities`

List available time entry activities from Redmine.

**Parameters:** None

**Returns:** `List[Dict]` of activities (`id`, `name`, `is_default`, `active`).

---

## Personnel & performance tools (manager oversight, read-only)

### `list_personnel`

List unique project members across projects so the boss can pick one person.
Deduplicates by user id, merges each person's projects + roles, skips group
memberships (counted in `groups_skipped`), and keeps per-project errors without
failing the whole call.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `project_ids` | `List[int]` | no | Restrict to these projects. Omit for all accessible projects |

**Returns:** `Dict` with `personnel` (`id`, `name`, `projects[{id, name, roles}]`),
`count`, `project_count`, `groups_skipped`, `errors`.

### `get_person_work_summary`

Summarize one person's performance for a day or a Monday–Sunday week, grouped
by project. Resolves `person` (user id or name/login via the admin
`/users.json` API — ambiguous names return candidates instead of guessing),
then returns per-project activity (hours logged, issues touched/closed in the
window) plus the current backlog (open count, `overdue` where `due_date` is past
and the status is open, `no_due_date` listed separately) and an `evidence`
block (filters used, query time, totals) for Redmine-UI cross-checks.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `person` | `int \| str` | yes | User ID (from `list_personnel`) or name/login |
| `window` | `str` | no | `'day'` (default) or `'week'` (Mon–Sun containing the date) |
| `date_str` | `str` | no | Reference date `YYYY-MM-DD` (defaults to server today) |
| `project_ids` | `List[int]` | no | Restrict to these projects. Omit for all accessible projects |

**Returns:** `Dict` with `person`, `window{type, from, to}`,
`per_project[{project, activity, backlog}]`, `totals`, `evidence`.

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

## Search tools

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

- `redmine://time-entry/contract`
  - Time logging contract: required fields and validation rules, available
    activities (id/name/active/default), create/update payload examples.

## Custom HTTP routes

| Route | Method | Description |
|---|---|---|
| `/health` | GET | Health check for orchestration |

> **Note:** Attachment download/cleanup tools were removed in this release. To
> download a Redmine attachment, use the `content_url` field returned in the
> issue/journal metadata (still serialized by `get_redmine_issue` and
> `get_redmine_wiki_page` when `include_attachments=True`).
>
> **Note:** Reporting/workflow tools were removed in this release:
> `get_redmine_project_workflow`, `get_issue_workflow_context`,
> `summarize_project_status`, `generate_scrum_report`,
> `export_weekly_report_markdown`, `export_weekly_report_docx`, and the
> `redmine://workflow/...` resources. For per-issue transitions, use
> `get_redmine_issue_allowed_statuses`. For daily/weekly personal reports,
> use the `redmine-daily-report` skill which builds reports from `git log`
> and `get_redmine_issue`.

## Notes

- **Consolidated vs legacy tools**: Consolidated tools (`manage_time_entries`)
  are recommended for agent workflows; the legacy direct tools remain for
  backward compatibility. The previous project-workflow contract tool and
  resources (`get_redmine_project_workflow`, `get_issue_workflow_context`,
  `redmine://workflow/...`) were removed — use `get_redmine_issue_allowed_statuses`
  to inspect allowed transitions for a single issue instead.
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
