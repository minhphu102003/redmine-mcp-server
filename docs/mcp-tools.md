# Redmine MCP Tools (Current Repository)

This document lists MCP tools currently exposed by `src/redmine_mcp_server/redmine_handler.py`.

## Prompts

- `redmine_server_operating_prompt`
  - Global operating prompt for this MCP server.
  - Designed to be loaded first by client/agent orchestration before tool calls.
  - Client enforcement guide: `docs/client-bootstrap-prompt.md`.

## Consolidated tools (recommended for agent workflows)

### `get_issue_workflow_context`
Unified entry point for issue-status/workflow context.

- `mode="statuses"`: list globally defined issue statuses
- `mode="issue"`: get current + allowed statuses for one issue
- `mode="project"`: infer project workflow snapshot from sampled issues
- `mode="transition_check"`: validate whether target status is currently allowed

Key params: `issue_id`, `project_id`, `tracker_id`, `status_id`, `sample_limit`, `target_status_id`, `target_status_name`.

---

### `manage_time_entries`
Unified entry point for time logging operations.

- `action="list"`: list time entries with filters/pagination
- `action="create"`: create a time entry
- `action="update"`: update a time entry
- `action="activities"`: list available time-entry activities

Key params: `time_entry_id`, `hours`, `project_id`, `issue_id`, `user_id`, `activity_id`, `comments`, `spent_on`, `from_date`, `to_date`, `limit`, `offset`.

---

### `generate_scrum_report`
Generate daily/weekly/custom scrum report drafts from logged time entries.

- `report_type="daily"`: auto-reads **yesterday** range
- `report_type="weekly"`: auto-reads **previous week** range (Mon-Sun)
- `report_type="custom"`: requires both `from_date` and `to_date`
- Custom range limit is controlled by `REDMINE_SCRUM_REPORT_MAX_DAYS` (default: 31)

Optional filters: `user_id`, `project_id`.
Output includes summary metrics, `top_issues`, `top_activities`, `top_users`, and:
- `report_draft` (quick draft)
- `report_templates.standup_three_questions`
- `report_templates.standup_workflow_focused`
- `report_templates.weekly_status_summary`

Tip:
- Pass only `project_id` to generate team-level report across multiple users.
- Pass only `user_id` to generate individual report (cross-project scope).
- Pass both `project_id` + `user_id` to generate one user's report inside a specific project.
- Re-generate anytime by calling the same tool again (it always reads fresh data in the selected range).

---

### `export_weekly_report_markdown`
Export weekly report to a markdown file based on your template:
- default template: `docs/templates/weekly_work_report_plan_template.md`
- default output dir: `reports/weekly`

This tool internally calls `generate_scrum_report(report_type="weekly")`, renders
the template, and writes `.md` output so devs can share/edit quickly.

---

### `export_weekly_report_docx`
Export weekly report to `.docx` for client delivery.

This tool reuses the weekly markdown template and generates a plain-text Word
document wrapper under `reports/weekly` (or custom `output_dir`).
Current behavior keeps markdown semantics as text (not native Word tables/headings).

## Core issue tools

- `get_redmine_issue`
- `list_redmine_issues`
- `search_redmine_issues`
- `create_redmine_issue`
- `update_redmine_issue`
- `list_redmine_issue_statuses`
- `get_redmine_issue_allowed_statuses`
- `get_redmine_project_workflow`

## Project tools

- `list_redmine_projects`
- `list_project_issue_custom_fields`
- `list_redmine_versions`
- `list_project_members`
- `summarize_project_status`

## Time entry tools (legacy direct tools)

- `list_time_entries`
- `create_time_entry`
- `update_time_entry`
- `list_time_entry_activities`

## Wiki tools

- `get_redmine_wiki_page`
- `create_redmine_wiki_page`
- `update_redmine_wiki_page`
- `delete_redmine_wiki_page`

## Search / attachment / maintenance tools

- `search_entire_redmine`
- `get_redmine_attachment_download_url`
- `cleanup_attachment_files`

## Notes

- Consolidated tools are intended to reduce tool-selection overhead and token usage in agent workflows.
- Legacy direct tools are still available for backward compatibility.

## Resources

- `redmine://issue-template/default`
  - Provides issue creation template metadata for agents:
    - `template_markdown`
    - `required_sections`
    - `enforced`
  - When `REDMINE_ENFORCE_ISSUE_TEMPLATE=true`, `create_redmine_issue` validates description headings against this template.

- `redmine://issue-contract/{project_id}`
- `redmine://issue-contract/{project_id}/{tracker_id}`
  - Issue create/update contract for agents:
    - required base fields
    - custom fields + required fields + allowed values
    - tracker bindings
    - linked description template contract

- `redmine://workflow/{project_id}`
- `redmine://workflow/{project_id}/{tracker_id}`
  - Workflow transition contract:
    - sampled workflow snapshot
    - normalized transition matrix (`from -> allowed`)
    - statuses list for current auth context

- `redmine://time-entry/contract`
  - Time logging contract:
    - required fields and validation rules
    - available activities (id/name/active/default)
    - create/update payload examples
