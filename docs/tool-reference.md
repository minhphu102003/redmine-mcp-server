# Tool Reference

Complete documentation for all available Redmine MCP Server tools.

## Security Best Practices

### SSL/TLS Configuration

The Redmine MCP Server supports comprehensive SSL/TLS configuration for secure connections to your Redmine instance.

**Recommended Practices:**

1. **Always Use HTTPS**
   ```bash
   # In .env file
   REDMINE_URL=https://redmine.company.com  # Use https://, not http://
   ```

2. **Enable SSL Verification (Default)**
   - SSL verification is enabled by default for security
   - Never disable in production environments
   - Only disable for development/testing when absolutely necessary

3. **Self-Signed Certificates**

   For Redmine servers with self-signed certificates or internal CA infrastructure:

   ```bash
   # In .env file
   REDMINE_SSL_CERT=/path/to/ca-certificate.crt
   ```

   **Security Considerations:**
   - Verify certificate authenticity before trusting
   - Obtain certificates from trusted administrators
   - Use absolute paths for certificate files
   - Ensure certificate files have appropriate permissions (644)

4. **Mutual TLS (Client Certificates)**

   For high-security environments requiring client certificate authentication:

   ```bash
   # In .env file
   REDMINE_SSL_CLIENT_CERT=/path/to/cert.pem,/path/to/key.pem
   ```

   **Security Considerations:**
   - Private keys MUST be unencrypted (Python requests library requirement)
   - Store private keys securely with restricted permissions (600)
   - Never commit certificates or keys to version control
   - Rotate client certificates regularly per security policy

5. **Development vs Production**

   ⚠️ **Development Only:**
   ```bash
   REDMINE_SSL_VERIFY=false  # WARNING: Only for development/testing!
   ```

   Disabling SSL verification makes your connection vulnerable to man-in-the-middle attacks. **Never use in production.**

### Authentication Best Practices

1. **API Key Authentication (Recommended)**

   Prefer API key authentication over username/password:

   ```bash
   # In .env file
   REDMINE_API_KEY=your_api_key_here
   ```

   **Benefits:**
   - More secure than password storage
   - Can be revoked without changing password
   - Granular access control
   - Better audit trail

2. **Username/Password Authentication**

   Only use when API key is not available:

   ```bash
   # In .env file
   REDMINE_USERNAME=your_username
   REDMINE_PASSWORD=your_password
   ```

   **Security Considerations:**
   - Never commit credentials to version control
   - Use strong, unique passwords
   - Rotate passwords regularly
   - Consider using API keys instead

3. **Credential Storage**

   - Store credentials in `.env` file (not in code)
   - Add `.env` to `.gitignore`
   - Use environment variables in production
   - Consider using secret management systems (e.g., HashiCorp Vault, AWS Secrets Manager)

### File Handling Security

Attachment download/cleanup is not handled by this server. To download a
Redmine attachment, use the `content_url` field returned in the issue or wiki
page metadata (when `include_attachments=True`). All metadata text returned to
the agent is wrapped in prompt-injection boundary tags.

### Docker Deployment Security

When deploying with Docker, follow these additional practices:

1. **Certificate Management**
   ```yaml
   # In docker-compose.yml
   volumes:
     - ./certs:/certs:ro  # Read-only mount
   ```

2. **Environment Variable Security**
   - Use separate `.env.docker` file
   - Never include credentials in Dockerfile
   - Use Docker secrets for sensitive data in production

3. **Network Security**
   - Separate internal binding from external URLs
   - Use reverse proxy (nginx, traefik) for SSL termination
   - Restrict container network access

### Read-Only Mode

Block all write operations by setting the `REDMINE_MCP_READ_ONLY` environment variable:

```bash
# In .env file
REDMINE_MCP_READ_ONLY=true
```

When enabled, the following tools return an error instead of executing:
- `create_redmine_issue`
- `update_redmine_issue`
- `create_redmine_wiki_page`
- `update_redmine_wiki_page`
- `delete_redmine_wiki_page`

All read tools (`get_redmine_issue`, `list_redmine_issues`, `list_redmine_projects`, etc.) continue to work normally.

### Prompt Injection Protection

All user-controlled content returned from Redmine (issue descriptions, journal notes, wiki page text, search excerpts, version descriptions) is automatically wrapped in unique boundary tags:

```
<insecure-content-a1b2c3d4e5f67890>
User-controlled content here...
</insecure-content-a1b2c3d4e5f67890>
```

This allows LLM consumers to distinguish trusted tool output from untrusted user data, preventing prompt injection attacks via Redmine content. Empty strings and non-string values are returned unchanged.

### Issue Template Resource and Enforcement

The server exposes an MCP resource at `redmine://issue-template/default` that agents can read before creating issues.

- `template_markdown`: canonical issue description template
- `required_sections`: section headings that must be present
- `enforced`: whether validation is currently active

When `REDMINE_ENFORCE_ISSUE_TEMPLATE=true`, `create_redmine_issue` rejects descriptions missing required headings and returns `template_resource_uri` plus `missing_sections`.

Tracker-aware template variants are supported by file naming convention under
`src/redmine_mcp_server/resources/templates/`:
- `issue_description_bug.md` for Bug tracker
- `issue_description_feature.md` for Feature tracker

When `tracker_id` is provided on create, the server resolves tracker name in
the target project and validates against the matching template variant when available.

### Contract Resources for Agent Planning

To reduce invalid tool calls, the server exposes contract resources:

- `redmine://issue-contract/{project_id}`
- `redmine://issue-contract/{project_id}/{tracker_id}`
  - Describes issue create/update fields, required custom fields, allowed values, and tracker bindings.

- `redmine://time-entry/contract`
  - Provides time-entry validation rules, allowed activities, and payload examples.

These resources are intended to be read before `create_redmine_issue`, `update_redmine_issue`, and time-entry update/create operations.

### Additional Resources

- [SSL Certificate Configuration](../README.md#ssl-certificate-configuration) - Detailed configuration examples
- [Troubleshooting Guide - SSL Errors](./troubleshooting.md#ssl-certificate-errors) - Common SSL issues and solutions
- [Environment Variables](../README.md#environment-variables) - Complete configuration reference

---

## Project Management

### `list_redmine_projects`

Lists all accessible projects in the Redmine instance.

**Parameters:** None

**Returns:** List of project dictionaries with id, name, identifier, and description

**Example:**
```json
[
  {
    "id": 1,
    "name": "My Project",
    "identifier": "my-project",
    "description": "Project description"
  }
]
```

---

### `get_project_issue_context`

Complete issue-creation context for a project in one call: trackers, issue
categories, members, versions, statuses, priorities, and issue custom fields
(optionally filtered by tracker). This is the single recommended entry point for
gathering project metadata before creating issues — it replaces the former
separate `list_project_trackers`, `list_project_issue_categories`,
`list_project_members`, `list_redmine_versions`, and
`list_project_issue_custom_fields` lookups.

**Parameters:**
- `project_id` (integer or string, required): Project ID (numeric) or identifier (string)
- `tracker_id` (integer or string, optional): Restrict custom fields to those applicable to the given tracker

**Returns:** Dict with `project`, `tracker_id`, `trackers`, `categories`,
`members`, `versions`, `statuses`, `priorities`, `custom_fields`, and
`required_custom_fields` sections. `statuses` lists all issue statuses defined
in Redmine (`id`, `name`, `is_closed`); `priorities` lists all issue priorities
(`id`, `name`). Each section is fetched concurrently; a failed section returns
its own error dict without failing the others.

**Example:**
```python
context = await get_project_issue_context(project_id="my-project")
# context["project"]["id"], context["trackers"], context["categories"],
# context["members"], context["versions"], context["statuses"],
# context["priorities"], context["custom_fields"]
```

---


## Issue Operations

### `get_redmine_issue`

Retrieve detailed information about a specific Redmine issue.

**Parameters:**
- `issue_id` (integer, required): The ID of the issue to retrieve
- `include_journals` (boolean, optional): Include journals (comments) in result. Default: `true`
- `include_attachments` (boolean, optional): Include attachments metadata. Default: `true`
- `include_custom_fields` (boolean, optional): Include custom fields in result. Default: `true`
- `journal_limit` (integer, optional): Maximum number of journals to return. When set, enables journal pagination and adds `journal_pagination` metadata. Default: `null` (all journals)
- `journal_offset` (integer, optional): Number of journals to skip (used with `journal_limit`). Default: `0`
- `include_watchers` (boolean, optional): Include watcher list. Default: `false`
- `include_relations` (boolean, optional): Include issue relations. Default: `false`
- `include_children` (boolean, optional): Include child issues. Default: `false`

**Returns:** Issue dictionary with details, journals, and attachments

**Example:**
```json
{
  "id": 123,
  "subject": "Bug in login form",
  "description": "<insecure-content-...>\nUsers cannot login...\n</insecure-content-...>",
  "status": {"id": 1, "name": "New"},
  "priority": {"id": 2, "name": "Normal"},
  "custom_fields": [{"id": 6, "name": "Size", "value": "S"}],
  "journals": [...],
  "attachments": [...]
}
```

**Journal pagination:**
```python
get_redmine_issue(123, journal_limit=5, journal_offset=10)
# Returns:
# {
#   ...
#   "journals": [...],  # 5 journals starting from position 10
#   "journal_pagination": {
#     "total": 42,
#     "offset": 10,
#     "limit": 5,
#     "count": 5,
#     "has_more": true
#   }
# }
```

**Include watchers, relations, and children:**
```python
get_redmine_issue(
    123,
    include_watchers=True,
    include_relations=True,
    include_children=True
)
# Returns:
# {
#   ...
#   "watchers": [{"id": 10, "name": "Alice"}, {"id": 11, "name": "Bob"}],
#   "relations": [{"id": 5, "issue_id": 123, "issue_to_id": 456, "relation_type": "relates"}],
#   "children": [{"id": 200, "subject": "Sub-task", "tracker": {"id": 1, "name": "Bug"}}]
# }
```

**Notes:**
- User-controlled content (`description`, journal `notes`) is wrapped in `<insecure-content-{boundary}>` boundary tags to prevent prompt injection
- Journal pagination metadata is only included when `journal_limit` is set
- Watchers, relations, and children default to `false` for backward compatibility

---

### `list_redmine_issues`

List Redmine issues with flexible filtering and pagination support. A general-purpose tool for listing issues from Redmine. Supports filtering by project, status, assignee, tracker, priority, and any other Redmine issue filter.

**Parameters:**
- `project_id` (integer or string, optional): Filter by project (numeric ID or string identifier)
- `status_id` (integer, optional): Filter by status ID
- `tracker_id` (integer, optional): Filter by tracker ID
- `assigned_to_id` (integer or string, optional): Filter by assignee. Use a numeric user ID or the special value `'me'` to retrieve issues assigned to the currently authenticated user.
- `priority_id` (integer, optional): Filter by priority ID
- `fixed_version_id` (integer, optional): Filter by target version/milestone ID
- `parent_id` (integer, optional): Filter by parent issue ID — list subtasks of a specific task
- `sort` (string, optional): Sort order (e.g., `"updated_on:desc"`)
- `limit` (integer, optional): Maximum issues to return. Default: `25`, Max: `1000`
- `offset` (integer, optional): Number of issues to skip for pagination. Default: `0`
- `include_pagination_info` (boolean, optional): Return structured response with metadata. Default: `false`
- `fields` (array of strings, optional): List of field names to include in results. Default: all fields
  - Available fields: `id`, `subject`, `description`, `project`, `parent`, `status`, `priority`, `author`, `assigned_to`, `created_on`, `updated_on`
  - Special values: `["*"]` or `["all"]` for all fields

**Returns:** List of issue dictionaries, or structured response with pagination metadata.
Each issue includes a `parent` key (`{"id", "subject"}` or `None`) so task
hierarchy is visible.

**Examples:**

List all issues in a project:
```python
list_redmine_issues(project_id="my-project")
```

List all subtasks of a task:
```python
list_redmine_issues(parent_id=42)
```

Filter by multiple criteria:
```python
list_redmine_issues(
    project_id=1,
    status_id=1,
    assigned_to_id="me",
    sort="updated_on:desc"
)
```

With pagination metadata:
```python
list_redmine_issues(
    project_id=1,
    limit=25,
    offset=50,
    include_pagination_info=True
)
# Returns:
# {
#   "issues": [...],
#   "pagination": {
#     "total": 150,
#     "limit": 25,
#     "offset": 50,
#     "has_next": true,
#     "has_previous": true,
#     "next_offset": 75,
#     "previous_offset": 25
#   }
# }
```

With field selection (reduces token usage):
```python
list_redmine_issues(
    project_id=1,
    fields=["id", "subject", "status"]
)
# Returns: [{"id": 1, "subject": "Bug fix", "status": {...}}, ...]
```

---

### `search_redmine_issues`

Search issues using text queries with support for pagination, field selection, and native Search API filters.

**Parameters:**
- `query` (string, required): Text to search for in issues
- `limit` (integer, optional): Maximum number of issues to return. Default: `25`, Max: `1000`
- `offset` (integer, optional): Number of issues to skip for pagination. Default: `0`
- `include_pagination_info` (boolean, optional): Return structured response with pagination metadata. Default: `false`
- `fields` (array of strings, optional): List of field names to include in results. Default: `null` (all fields)
  - Available fields: `id`, `subject`, `description`, `project`, `status`, `priority`, `author`, `assigned_to`, `created_on`, `updated_on`
  - Special values: `["*"]` or `["all"]` for all fields
- `scope` (string, optional): Search scope. Default: `"all"`
  - Values: `"all"`, `"my_project"`, `"subprojects"`
- `open_issues` (boolean, optional): Search only open issues. Default: `false`

**Returns:**
- By default: List of issue dictionaries
- With `include_pagination_info=true`: Dictionary with `issues` and `pagination` keys

**When to Use:**
- **Use `search_redmine_issues()`** for text-based searches across issues
- **Use `list_redmine_issues()`** for advanced filtering by project_id, status_id, priority_id, etc.

**Search API Limitations:**
The Search API supports text search with `scope` and `open_issues` filters only. For advanced filtering by specific field values (project_id, status_id, priority_id, etc.), use `list_redmine_issues()` instead.

**Examples:**

Basic search:
```python
search_redmine_issues("bug fix")
```

With pagination:
```python
# First page
search_redmine_issues("performance", limit=10, offset=0)

# Second page
search_redmine_issues("performance", limit=10, offset=10)
```

With pagination metadata:
```python
search_redmine_issues(
    "security",
    limit=25,
    offset=0,
    include_pagination_info=True
)
# Returns:
# {
#   "issues": [...],
#   "pagination": {
#     "limit": 25,
#     "offset": 0,
#     "count": 25,
#     "has_next": true,
#     "has_previous": false,
#     "next_offset": 25,
#     "previous_offset": null
#   }
# }
```

With field selection (token reduction):
```python
# Minimal fields for better performance
search_redmine_issues("urgent", fields=["id", "subject", "status"])
```

With native filters:
```python
# Search only in my projects for open issues
search_redmine_issues(
    "bug",
    scope="my_project",
    open_issues=True
)
```

All features combined:
```python
search_redmine_issues(
    "critical",
    scope="my_project",
    open_issues=True,
    limit=10,
    offset=0,
    fields=["id", "subject", "priority", "status"],
    include_pagination_info=True
)
```

**Performance Tips:**
- Use pagination (default limit: 25) to prevent token overflow
- Use field selection to minimize data transfer and token usage
- Combine pagination + field selection for optimal performance
- Token reduction: ~95% fewer tokens with minimal fields vs all fields

---

### `create_redmine_issue`

Creates a new issue in the specified project. All core issue fields are
**required** — the tool will not create an issue with any of them missing.
Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters (all required):**
- `project_id` (integer): Target project ID
- `subject` (string): Issue subject/title
- `description` (string): Issue description (Textile/Wiki markup supported)
- `tracker_id` (integer): Issue type — `1` (Bug), `2` (Feature), `3` (Support),
  `4` (Common), `5` (Testing Task)
- `priority_id` (integer): Priority level — e.g. `3` = Normal, `4` = High,
  `5` = Urgent, `2` = Low
- `status_id` (integer): Initial status — e.g. `1` = New, `2` = In Progress,
  `3` = Resolved, `4` = Feedback, `5` = Closed, `6` = Rejected
- `assigned_to_id` (integer): Assignee user ID (e.g. `79`, `80`, `75`, `77`,
  `30`)
- `start_date` (string): Start date, `YYYY-MM-DD`
- `due_date` (string): Due date, `YYYY-MM-DD`
- `estimated_hours` (number): Estimated hours to complete the issue
- `done_ratio` (integer): Completion percentage, `0` to `100`

**Optional parameters:**
- `fields` (object|string, optional): Extra Redmine fields as an object or a
  serialized JSON object string. Used for `category_id`, `fixed_version_id`,
  and custom fields (`"custom_fields": [{"id": X, "value": Y}]`). All other
  issue fields are passed as the dedicated required parameters above
- `extra_fields` (object|string, optional): Advanced fields passed through to
  Redmine that are not in `fields`
- `parent_issue_id` (integer or string, optional): ID of an existing task to
  create this issue as a subtask of. When omitted, a standalone task is created

**Returns:** Created issue dictionary (includes a `parent` key with the parent
issue's `id`/`subject`, or `None` for standalone tasks, and a `url` key with
the web link to the created issue, e.g. `https://redmine.example.com/issues/42`).

**Behavior note:** If `REDMINE_AUTOFILL_REQUIRED_CUSTOM_FIELDS=true` and Redmine returns relevant custom-field validation errors (for example `<Field Name> cannot be blank` or `<Field Name> is not included in the list`), the server fetches project custom fields, auto-fills missing/invalid required custom fields from Redmine `default_value` or `REDMINE_REQUIRED_CUSTOM_FIELD_DEFAULTS`, and retries once.

**Creating a subtask of an existing task:**
- When `parent_issue_id` is provided, the server first fetches the parent and
  validates:
  - the parent exists (otherwise a clear error is returned),
  - the parent belongs to the same project (subtasks must share the parent's
    project).
  Redmine supports unlimited nesting depth, so the parent may itself be a
  subtask.
- Only then is the issue created with `parent_issue_id` set.

```python
# Create a subtask under an existing task
create_redmine_issue(
    project_id=1,
    subject="Implement refresh token flow",
    description="Details...",
    tracker_id=2,
    priority_id=3,
    status_id=1,
    assigned_to_id=5,
    start_date="2026-08-05",
    due_date="2026-08-12",
    estimated_hours=8.0,
    done_ratio=0,
    parent_issue_id=42,
)
```

**Strict input policy (optional):**
- Enable with `REDMINE_STRICT_ISSUE_CREATION_INPUTS=true`.
- Enforced checks:
  - `subject` must match: `[module name] task name`
  - caller must provide: `tracker_id`, `assigned_to_id`, `category_id`,
    `fixed_version_id`, `estimated_hours`, `start_date`, `due_date`
  - `start_date`/`due_date` format `YYYY-MM-DD` and `due_date >= start_date`
  - `estimated_hours > 0`

**Example:**
```python
# Create a bug report
create_redmine_issue(
    project_id=1,
    subject="[web] Login button not working",
    description="The login button does not respond to clicks",
    tracker_id=1,
    priority_id=4,
    status_id=1,
    assigned_to_id=80,
    start_date="2026-08-05",
    due_date="2026-08-12",
    estimated_hours=4.0,
    done_ratio=0,
)
```

---

### `create_redmine_issue_with_subtasks`

Creates one parent issue and multiple subtasks in a single tool call. All
core fields are **required** for the parent and for **every** subtask —
subtasks missing any required field are reported as failed, not created.
Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters (all required):**
- `project_id` (integer): Target project ID
- `parent_subject` (string): Parent issue title
- `parent_description` (string): Parent issue description
- `tracker_id` (integer): Issue type of the parent — `1` (Bug), `2` (Feature),
  `3` (Support), `4` (Common), `5` (Testing Task)
- `priority_id` (integer): Priority of the parent (e.g. `3` = Normal, `4` = High)
- `status_id` (integer): Initial status of the parent (e.g. `1` = New, `2` = In Progress)
- `assigned_to_id` (integer): Assignee of the parent (e.g. `80`)
- `start_date` (string): Parent start date, `YYYY-MM-DD`
- `due_date` (string): Parent due date, `YYYY-MM-DD`
- `estimated_hours` (number): Estimated hours for the parent
- `done_ratio` (integer): Parent completion percentage, `0` to `100`

**Optional parameters:**
- `parent_fields` (object|string, optional): Extra fields for parent issue
  (`category_id`, `fixed_version_id`, custom fields)
- `parent_extra_fields` (object|string, optional): Additional fields merged into parent fields
- `subtasks` (array, optional): List of subtask objects, each **requiring**:
  - `subject` (string)
  - `description` (string)
  - `tracker_id` (integer)
  - `priority_id` (integer)
  - `status_id` (integer)
  - `assigned_to_id` (integer)
  - `start_date` (string, `YYYY-MM-DD`)
  - `due_date` (string, `YYYY-MM-DD`)
  - `estimated_hours` (number)
  - `done_ratio` (integer)
  - `fields` (object|string, optional): extra fields for the subtask
  - `extra_fields` (object|string, optional)
- `stop_on_subtask_error` (boolean, optional): Stop processing on first failed subtask. Default: `false`

**Returns:** Dictionary containing:
- `parent_issue`
- `created_subtasks`
- `failed_subtasks`
- `summary`

The parent and each created subtask include a `url` key with the web link to
the issue (e.g. `https://redmine.example.com/issues/42`).

**Behavior notes:**
- Each subtask is forced to use `parent_issue_id=<created_parent_id>`.
- Subtasks missing any required field are skipped and reported in
  `failed_subtasks` with `Missing required subtask fields: ...`.
- Parent/subtask creation follows the same validation, template, and read-only rules as `create_redmine_issue`.
- Subtasks are processed in batches of **50** by default (`REDMINE_MCP_SUBTASK_BATCH_LIMIT`).

**Example:**
```python
create_redmine_issue_with_subtasks(
    project_id=1,
    parent_subject="Implement OAuth login flow",
    parent_description="Break down this epic into implementable tasks.",
    tracker_id=2,
    priority_id=3,
    status_id=1,
    assigned_to_id=80,
    start_date="2026-08-05",
    due_date="2026-08-19",
    estimated_hours=16.0,
    done_ratio=0,
    subtasks=[
        {
            "subject": "Design callback handler",
            "description": "Design the OAuth callback flow",
            "tracker_id": 1,
            "priority_id": 3,
            "status_id": 1,
            "assigned_to_id": 80,
            "start_date": "2026-08-05",
            "due_date": "2026-08-07",
            "estimated_hours": 4.0,
            "done_ratio": 0,
        },
        {
            "subject": "Implement token refresh",
            "description": "Implement refresh token rotation",
            "tracker_id": 1,
            "priority_id": 3,
            "status_id": 1,
            "assigned_to_id": 79,
            "start_date": "2026-08-08",
            "due_date": "2026-08-12",
            "estimated_hours": 8.0,
            "done_ratio": 0,
        },
    ],
)
```

---

### `update_redmine_issue`

Updates an existing issue with the provided fields, and optionally logs worked time against it in the same call. Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters:**
- `issue_id` (integer, required): ID of the issue to update
- `fields` (object, required): Dictionary of fields to update. May be empty when only logging time
- `spent_hours` (number, optional): Hours to log as a time entry on this issue (e.g. `1.5`). Must be a positive number. When set, a time entry is created on the issue after a successful update
- `activity_id` (integer, optional): Activity type ID for the logged time entry (use `list_time_entry_activities` to discover valid values)
- `time_comments` (string, optional): Work description for the logged time entry (distinct from the issue `notes` comment)
- `spent_on` (string, optional): Date the work was done (YYYY-MM-DD). Defaults to today

**Returns:** Updated issue dictionary. When `spent_hours` is provided, the created time entry is included under the `time_entry` key. If logging fails after a successful issue update, the update is kept and the result contains `time_entry` with an `error` key plus `time_entry_error: true`.

**Note:** You can use either `status_id` or `status_name` in fields. When `status_name` is provided, the tool automatically resolves the corresponding status ID.
You can also update custom fields by name (for example `{"size": "S"}`) and the tool will resolve them to Redmine `custom_fields` entries using project custom-field metadata. You can still pass explicit `custom_fields` with field IDs.

**Example:**
```python
# Update issue status using status name
update_redmine_issue(
    issue_id=123,
    fields={
        "status_name": "Resolved",
        "notes": "Fixed the issue"
    }
)

# Or use status_id directly
update_redmine_issue(
    issue_id=123,
    fields={
        "status_id": 3,
        "assigned_to_id": 5
    }
)

# Update Agile/custom field by name
update_redmine_issue(
    issue_id=123,
    fields={
        "size": "S"
    }
)

# Update the issue and log 1.5 hours of work in one call
update_redmine_issue(
    issue_id=123,
    fields={"status_id": 3},
    spent_hours=1.5,
    activity_id=9,
    time_comments="Implemented the fix",
    spent_on="2026-08-05",
)
```

---

## Issue Relations (dependencies)

### `create_redmine_issue_relation`

Creates an issue relation (dependency) between two Redmine issues — e.g. task A `precedes` task B, so the Gantt chart and roadmap reflect "task nào nên làm trước". Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters:**
- `issue_id` (integer, required): ID of the first issue (the one that comes first, blocks, or is related)
- `issue_to_id` (integer, required): ID of the second issue (the one that comes later, is blocked, or is related)
- `relation_type` (string, required): `precedes` / `follows`, `blocks` / `blocked`, `relates`, `duplicates` / `duplicated`, `copied_to` / `copied_from`. Pick one direction — Redmine mirrors the complementary type automatically
- `delay` (integer, optional): Delay in days (precedes/follows only), e.g. `1` = `issue_to_id` starts 1 day after `issue_id`

**Behavior:** validates the relation type, rejects self-relations, verifies both issues exist before creating; both issue subjects are returned wrapped in insecure-content tags.

**Returns:** `success`, the created `relation` (`id`, `issue_id`, `issue_to_id`, `relation_type`, `delay`) and both `issues` (id + subject).

**Example:**
```python
# Task 100 (Setup API) must be done before task 200 (Build UI)
create_redmine_issue_relation(
    issue_id=100,
    issue_to_id=200,
    relation_type="precedes",
    delay=0,
)
```

---

### `delete_redmine_issue_relation`

Deletes an issue relation from Redmine. Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters:**
- `relation_id` (integer, required): ID of the issue relation to delete

**Returns:** `success`, `relation_id` and a `message`.

---

## Time Tracking

### `list_time_entries`

List time entries from Redmine with optional filtering and pagination.

**Parameters:**
- `project_id` (integer or string, optional): Filter by project (numeric ID or string identifier)
- `issue_id` (integer, optional): Filter by issue ID
- `user_id` (integer or string, optional): Filter by user ID. Use `"me"` for current user
- `from_date` (string, optional): Start date filter (YYYY-MM-DD format)
- `to_date` (string, optional): End date filter (YYYY-MM-DD format)
- `limit` (integer, optional): Maximum entries to return. Default: `25`, Max: `100`
- `offset` (integer, optional): Number of entries to skip for pagination. Default: `0`

**Returns:** List of time entry dictionaries

**Example:**
```json
[
  {
    "id": 1,
    "hours": 2.5,
    "comments": "Bug fix work",
    "spent_on": "2024-03-15",
    "user": {"id": 5, "name": "John Doe"},
    "project": {"id": 10, "name": "My Project"},
    "issue": {"id": 123},
    "activity": {"id": 9, "name": "Development"},
    "created_on": "2024-03-15T10:30:00",
    "updated_on": "2024-03-15T10:30:00"
  }
]
```

**Usage:**
```python
# List all time entries for a project
entries = list_time_entries(project_id="my-project")

# Filter by issue and date range
entries = list_time_entries(
    issue_id=123,
    from_date="2024-01-01",
    to_date="2024-03-31"
)

# Get current user's time entries
my_entries = list_time_entries(user_id="me")
```

---

### `create_time_entry`

Create a new time entry in Redmine. Log time against a project or issue.

**Parameters:**
- `hours` (float, required): Number of hours spent. Must be positive. Can be decimal (e.g., `1.5`)
- `project_id` (integer or string, optional): Project to log time against. Required if `issue_id` is not provided
- `issue_id` (integer, optional): Issue to log time against. If provided, `project_id` is optional
- `activity_id` (integer, optional): Time entry activity ID (e.g., Development, Design). Uses default if not provided
- `comments` (string, optional): Description of work performed
- `spent_on` (string, optional): Date when time was spent (YYYY-MM-DD). Defaults to today

**Returns:** Created time entry dictionary

**Example:**
```json
{
  "id": 1,
  "hours": 2.5,
  "comments": "Bug fix",
  "spent_on": "2024-03-15",
  "user": {"id": 5, "name": "John Doe"},
  "project": {"id": 10, "name": "My Project"},
  "issue": {"id": 123},
  "activity": {"id": 9, "name": "Development"}
}
```

**Usage:**
```python
# Log time against an issue
create_time_entry(
    hours=2.5,
    issue_id=123,
    comments="Fixed login bug"
)

# Log time against a project with specific date
create_time_entry(
    hours=1.0,
    project_id="my-project",
    activity_id=9,
    comments="Code review",
    spent_on="2024-03-15"
)
```

---

### `update_time_entry`

Update an existing time entry in Redmine.

**Parameters:**
- `time_entry_id` (integer, required): ID of the time entry to update
- `hours` (float, optional): New hours value. Must be positive if provided
- `activity_id` (integer, optional): New activity ID
- `comments` (string, optional): New comments/description
- `spent_on` (string, optional): New date (YYYY-MM-DD format)

**Returns:** Updated time entry dictionary

**Example:**
```json
{
  "id": 1,
  "hours": 3.0,
  "comments": "Extended work on bug fix",
  "spent_on": "2024-03-15"
}
```

**Usage:**
```python
# Update hours
update_time_entry(time_entry_id=1, hours=3.0)

# Update multiple fields
update_time_entry(
    time_entry_id=1,
    hours=4.0,
    comments="Extended debugging session",
    spent_on="2024-03-16"
)
```

---

### `delete_time_entry`

Delete a time entry from Redmine. Destructive: permanently removes the entry. Respects read-only mode.

**Parameters:**
- `time_entry_id` (integer, required): ID of the time entry to delete

**Returns:** Confirmation dictionary with `success`, `time_entry_id` and `message`

**Example:**
```json
{
  "success": true,
  "time_entry_id": 1,
  "message": "Time entry 1 deleted successfully."
}
```

**Usage:**
```python
# Delete a mislogged entry
delete_time_entry(time_entry_id=1)
```

---

### `list_time_entry_activities`

List all available time entry activity types from Redmine.

Use this tool to discover valid `activity_id` values before calling `create_time_entry` or `update_time_entry`.

**Parameters:** None

**Returns:** List of activity dictionaries

**Example:**
```json
[
  {"id": 4, "name": "Development", "active": true, "is_default": false},
  {"id": 5, "name": "Design", "active": true, "is_default": false},
  {"id": 6, "name": "Testing", "active": true, "is_default": false}
]
```

---

## Personnel & Performance (manager oversight, read-only)

### `list_personnel`

List unique project members across projects — step 1 of the boss workflow
(the boss picks one person from this list).

**Parameters:**
- `project_ids` (array of integers, optional): Restrict to these project IDs. Omit for all accessible projects.

**Returns:** Dictionary with `personnel` (each: `id`, `name`, `projects` with `id`/`name`/`roles`), `count`, `project_count`, `groups_skipped` (group memberships are not people and are skipped), and `errors` (per-project failures kept without failing the whole call).

**Example:**
```python
people = list_personnel()
# {"personnel": [{"id": 7, "name": "An Nguyen",
#    "projects": [{"id": 1, "name": "Web", "roles": ["Developer"]}]}],
#  "count": 1, ...}
```

---

### `get_person_work_summary`

Summarize one person's performance for a day or a Monday–Sunday week, grouped by project — step 3 of the boss workflow (the backend aggregates, the agent renders the UI).

**Parameters:**
- `person` (integer or string, required): User ID (from `list_personnel`) or name/login. Ambiguous names return an error listing candidates instead of guessing
- `window` (string, optional): `"day"` (default) or `"week"` (Mon–Sun week containing the reference date, even when it is a Sunday)
- `date_str` (string, optional): Reference date `YYYY-MM-DD`. Defaults to today (server date)
- `project_ids` (array of integers, optional): Restrict to these project IDs. Omit for all accessible projects
- `compact` (boolean, optional): When `true`, skip the per-project detail and return only `person`, `window`, `widget_data`, `totals`, and `evidence` (smaller payload for the oversight widget). Default: `false`

**Returns:** Dictionary with:
- `person` (`id`, `name`, `login`, `mail`)
- `window` (`type`, `from`, `to`)
- `widget_data`: completed tasks bucketed per weekday (`Thứ 2` … `Chủ nhật`), each item `id`, `name`, `project`, `est`, `actual`, `url` — embed verbatim into the oversight widget. A task counts as completed when `done_ratio == 100` (even with an open status) and it was updated inside the window; `est` is 0 when Redmine has no estimate, `actual` sums the time entries logged on that issue inside the window (0 when none)
- `per_project`: per project, `activity` (`hours`, `touched`/`touched_count`, `closed`/`closed_count`) and `backlog` (`open_count`, `overdue`/`overdue_count`, `no_due_date`/`no_due_date_count`, `in_progress`). Each issue brief carries `id`, `subject`, `status`, `due_date`, `done_ratio`, `estimated_hours`, `actual_hours`, `updated_on`, and `url`. Omitted when `compact=true`
- `totals`: `hours`, `time_entries`, `touched_count`, `closed_count`, `open_count`, `overdue_count`, `no_due_date_count`
- `evidence`: `queried_at`, `person_query`, `filters_used`, `totals` — cite this block so the boss can cross-check every answer in the Redmine UI

**Overdue rule (fixed):** status is open (`is_closed == false`) AND `due_date < today`. Due today is not overdue; closed issues are never overdue; issues without `due_date` are listed separately and never counted.

**Example:**
```python
summary = get_person_work_summary(7, window="week", date_str="2026-09-03")
# {"person": {"id": 7, ...},
#  "window": {"type": "week", "from": "2026-08-31", "to": "2026-09-06"},
#  "per_project": [...], "totals": {...}, "evidence": {...}}
```

**Notes:**
- Person resolution uses the admin `/users.json` API — the caller's API key needs admin rights
- Pure read tool: works with `REDMINE_MCP_READ_ONLY=true`

---

## Search & Wiki

### `search_entire_redmine`

Search across issues and wiki pages in the Redmine instance. Requires Redmine 3.3.0 or higher.

**Parameters:**
- `query` (string, required): Text to search for
- `resources` (list, optional): Filter by resource types. Allowed: `["issues", "wiki_pages"]`. Default: both types
- `limit` (integer, optional): Maximum results to return (max 100). Default: 100
- `offset` (integer, optional): Pagination offset. Default: 0

**Returns:**
```json
{
    "results": [
        {
            "id": 123,
            "type": "issues",
            "title": "Bug in login page",
            "project": "Web App",
            "status": "Open",
            "updated_on": "2025-01-15T10:00:00Z",
            "excerpt": "First 200 characters of description..."
        },
        {
            "id": null,
            "type": "wiki_pages",
            "title": "Installation Guide",
            "project": "Documentation",
            "status": null,
            "updated_on": "2025-01-10T14:30:00Z",
            "excerpt": "First 200 characters of wiki text..."
        }
    ],
    "results_by_type": {
        "issues": 1,
        "wiki_pages": 1
    },
    "total_count": 2,
    "query": "installation"
}
```

**Example:**
```python
# Search all resource types
search_entire_redmine(query="installation guide")

# Search only wiki pages
search_entire_redmine(query="setup", resources=["wiki_pages"])

# With pagination
search_entire_redmine(query="bug", limit=25, offset=0)
```

**Notes:**
- Requires Redmine 3.3.0+ for search API support
- v1.4 scope limitation: Only `issues` and `wiki_pages` supported
- Invalid resource types are silently filtered out
- Search is case-sensitive/insensitive based on Redmine server DB config

---

### `get_redmine_wiki_page`

Retrieve full wiki page content from a Redmine project.

**Parameters:**
- `project_id` (string or integer, required): Project identifier (ID number or string identifier)
- `wiki_page_title` (string, required): Wiki page title (e.g., "Installation_Guide")
- `version` (integer, optional): Specific version number. Default: latest version
- `include_attachments` (boolean, optional): Include attachment metadata. Default: true

**Returns:**
```json
{
    "title": "Installation Guide",
    "text": "# Installation\n\nFollow these steps to install...",
    "version": 5,
    "created_on": "2025-01-15T10:00:00Z",
    "updated_on": "2025-01-20T14:30:00Z",
    "author": {
        "id": 123,
        "name": "John Doe"
    },
    "project": {
        "id": 1,
        "name": "My Project"
    },
    "attachments": [
        {
            "id": 456,
            "filename": "diagram.png",
            "filesize": 102400,
            "content_type": "image/png",
            "description": "Architecture diagram",
            "created_on": "2025-01-15T10:00:00Z"
        }
    ]
}
```

**Example:**
```python
# Get latest version
get_redmine_wiki_page(
    project_id="my-project",
    wiki_page_title="Installation_Guide"
)

# Get specific version
get_redmine_wiki_page(
    project_id=123,
    wiki_page_title="Installation",
    version=3
)

# Without attachments
get_redmine_wiki_page(
    project_id="docs",
    wiki_page_title="FAQ",
    include_attachments=False
)
```

**Notes:**
- Attachment download is not provided by this server; use the `content_url` field in attachment metadata to download from the Redmine host directly
- Supports both string identifiers (e.g., "my-project") and numeric IDs

---

### `create_redmine_wiki_page`

Create a new wiki page in a Redmine project. Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters:**
- `project_id` (string or integer, required): Project identifier (ID number or string identifier)
- `wiki_page_title` (string, required): Wiki page title (e.g., "Installation_Guide")
- `text` (string, required): Wiki page content (Textile or Markdown depending on Redmine config)
- `comments` (string, optional): Comment for the change log. Default: empty

**Returns:**
```json
{
    "title": "New Page",
    "text": "# New Page\n\nContent here.",
    "version": 1,
    "created_on": "2025-01-15T10:00:00Z",
    "updated_on": "2025-01-15T10:00:00Z",
    "author": {
        "id": 123,
        "name": "John Doe"
    },
    "project": {
        "id": 1,
        "name": "My Project"
    }
}
```

**Example:**
```python
# Create a simple wiki page
create_redmine_wiki_page(
    project_id="my-project",
    wiki_page_title="Getting_Started",
    text="# Getting Started\n\nWelcome to the project!"
)

# Create with change log comment
create_redmine_wiki_page(
    project_id=123,
    wiki_page_title="API_Reference",
    text="# API Reference\n\n## Endpoints\n...",
    comments="Initial API documentation"
)
```

**Notes:**
- Wiki page titles typically use underscores instead of spaces
- Content format (Textile/Markdown) depends on Redmine server configuration
- Requires wiki edit permissions in the target project

---

### `update_redmine_wiki_page`

Update an existing wiki page in a Redmine project. Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters:**
- `project_id` (string or integer, required): Project identifier (ID number or string identifier)
- `wiki_page_title` (string, required): Wiki page title (e.g., "Installation_Guide")
- `text` (string, required): New wiki page content
- `comments` (string, optional): Comment for the change log. Default: empty

**Returns:**
```json
{
    "title": "Installation Guide",
    "text": "# Installation\n\nUpdated content...",
    "version": 6,
    "created_on": "2025-01-10T10:00:00Z",
    "updated_on": "2025-01-20T14:30:00Z",
    "author": {
        "id": 123,
        "name": "John Doe"
    },
    "project": {
        "id": 1,
        "name": "My Project"
    }
}
```

**Example:**
```python
# Update wiki page content
update_redmine_wiki_page(
    project_id="my-project",
    wiki_page_title="Installation_Guide",
    text="# Installation\n\nUpdated installation steps..."
)

# Update with change log comment
update_redmine_wiki_page(
    project_id=123,
    wiki_page_title="FAQ",
    text="# FAQ\n\n## New Questions\n...",
    comments="Added new FAQ entries"
)
```

**Notes:**
- Version number increments automatically on each update
- Redmine maintains version history for rollback
- Requires wiki edit permissions in the target project

---

### `delete_redmine_wiki_page`

Delete a wiki page from a Redmine project. Blocked when `REDMINE_MCP_READ_ONLY=true`.

**Parameters:**
- `project_id` (string or integer, required): Project identifier (ID number or string identifier)
- `wiki_page_title` (string, required): Wiki page title to delete

**Returns:**
```json
{
    "success": true,
    "title": "Obsolete_Page",
    "message": "Wiki page 'Obsolete_Page' deleted successfully."
}
```

**Example:**
```python
# Delete a wiki page
delete_redmine_wiki_page(
    project_id="my-project",
    wiki_page_title="Obsolete_Page"
)

# Delete by numeric project ID
delete_redmine_wiki_page(
    project_id=123,
    wiki_page_title="Old_Documentation"
)
```

**Notes:**
- Deletion is permanent - page and all versions are removed
- Requires wiki delete permissions in the target project
- Child pages (if any) may become orphaned

---

## File Operations

> **Note:** The `get_redmine_attachment_download_url` and
> `cleanup_attachment_files` tools were removed to reduce MCP tool surface area
> and per-request memory. Use the `content_url` field returned in attachment
> metadata (via `get_redmine_issue` / `get_redmine_wiki_page` with
> `include_attachments=True`) to download files directly from your Redmine
> instance.

