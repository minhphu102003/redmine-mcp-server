# Redmine MCP Tools (Current Repository)

This document lists MCP tools currently exposed by `src/redmine_mcp_server/redmine_handler.py`.

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
