"""Per-tool MCP prompt playbooks and registration helpers."""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Union


def _render_tool_prompt(
    *,
    tool_name: str,
    objective: str,
    required_inputs: List[str],
    recommended_resources: Optional[List[str]] = None,
    pre_checks: Optional[List[str]] = None,
    result_shape: Optional[str] = None,
) -> str:
    """Render a consistent per-tool operating prompt for MCP clients."""
    sections: List[str] = [
        f"You are preparing to call `{tool_name}`.",
        f"Objective: {objective}",
        "",
        "Required inputs:",
        *[f"- {item}" for item in required_inputs],
    ]
    if recommended_resources:
        sections.extend(
            [
                "",
                "Read these resources first when available:",
                *[f"- {resource}" for resource in recommended_resources],
            ]
        )
    if pre_checks:
        sections.extend(
            ["", "Pre-call checks:", *[f"- {check}" for check in pre_checks]]
        )
    if result_shape:
        sections.extend(["", f"Expected result shape: {result_shape}"])
    sections.extend(
        [
            "",
            "Output format for the user:",
            "- intent",
            "- tool arguments to send",
            "- result summary and next step",
        ]
    )
    return "\n".join(sections)


def redmine_server_operating_prompt(user_goal: str = "") -> str:
    """Global operating playbook for safe, consistent Redmine MCP usage."""
    normalized_goal = (user_goal or "").strip() or "not provided"
    return "\n".join(
        [
            "You are operating the Redmine MCP server.",
            f"User goal: {normalized_goal}",
            "",
            "Global protocol (must run before any tool call):",
            "1) Restate intent and identify whether action is read-only or write.",
            "2) Discover constraints using MCP resources:",
            "   - redmine://issue-template/default (issue description rules)",
            (
                "   - redmine://issue-contract/{project_id}[/{tracker_id}] "
                "for issue writes"
            ),
            (
                "   - redmine://workflow/{project_id}[/{tracker_id}] "
                "for status/workflow actions"
            ),
            "   - redmine://time-entry/contract for time-entry actions",
            (
                "3) Validate required fields, allowed transitions, "
                "and read-only constraints."
            ),
            "4) Prefer list/get/search tools first when context is incomplete.",
            (
                "5) Execute the minimum required tool calls and "
                "report structured outcomes."
            ),
            "",
            "Output contract for every action:",
            "- intent",
            "- constraints checked",
            "- tool arguments sent",
            "- result summary",
            "- next step (or completion)",
        ]
    )


def get_redmine_issue_prompt(issue_id: int) -> str:
    """Playbook for calling get_redmine_issue."""
    return _render_tool_prompt(
        tool_name="get_redmine_issue",
        objective=(
            "Fetch one issue with optional journals, attachments, "
            "and relation context."
        ),
        required_inputs=[
            f"issue_id={issue_id}",
            "Choose include_* flags based on user need.",
        ],
        pre_checks=["Verify issue_id is a positive integer."],
        result_shape="Dict with issue core fields and optional related sections.",
    )


def list_redmine_projects_prompt() -> str:
    """Playbook for calling list_redmine_projects."""
    return _render_tool_prompt(
        tool_name="list_redmine_projects",
        objective="List all projects the current credential can access.",
        required_inputs=["No arguments required."],
        result_shape="List[project] with IDs, names, and identifiers.",
    )


def list_project_issue_custom_fields_prompt(
    project_id: Union[str, int], tracker_id: Optional[Union[str, int]] = None
) -> str:
    """Playbook for calling list_project_issue_custom_fields."""
    tracker_hint = tracker_id if tracker_id is not None else "optional"
    return _render_tool_prompt(
        tool_name="list_project_issue_custom_fields",
        objective="Inspect custom fields for issue create/update in a project.",
        required_inputs=[f"project_id={project_id}", f"tracker_id={tracker_hint}"],
        pre_checks=["Use tracker_id to narrow required fields for a specific tracker."],
        result_shape="List[custom_field] including required flag and allowed values.",
    )


def list_redmine_versions_prompt(project_id: Union[str, int]) -> str:
    """Playbook for calling list_redmine_versions."""
    return _render_tool_prompt(
        tool_name="list_redmine_versions",
        objective="List milestones/versions for planning or filtering issues.",
        required_inputs=[f"project_id={project_id}", "status_filter (optional)."],
        result_shape="List[version] with status and due-date metadata.",
    )


def list_redmine_issues_prompt(project_id: Optional[Union[str, int]] = None) -> str:
    """Playbook for calling list_redmine_issues."""
    scope = project_id if project_id is not None else "all visible projects"
    return _render_tool_prompt(
        tool_name="list_redmine_issues",
        objective="Fetch issues with filters, pagination, and selective fields.",
        required_inputs=[
            f"project scope={scope}",
            "limit/offset for pagination",
            "optional filters/status/tracker/assignee",
        ],
        pre_checks=["Set include_pagination_info=true when users need total counts."],
        result_shape="List[issue] or pagination wrapper with issues + metadata.",
    )


def search_redmine_issues_prompt(query: str) -> str:
    """Playbook for calling search_redmine_issues."""
    return _render_tool_prompt(
        tool_name="search_redmine_issues",
        objective="Search issues by free-text query with optional scope controls.",
        required_inputs=[f"query={query}", "limit/offset for paging optional."],
        pre_checks=["Use scope/open_issues options to reduce noisy results."],
        result_shape="List[issue] or pagination wrapper.",
    )


def create_redmine_issue_prompt(project_id: Union[str, int], subject: str) -> str:
    """Playbook for calling create_redmine_issue."""
    return _render_tool_prompt(
        tool_name="create_redmine_issue",
        objective=(
            "Create a new Redmine issue that satisfies template and " "field contracts."
        ),
        required_inputs=[f"project_id={project_id}", f"subject={subject}"],
        recommended_resources=[
            "redmine://issue-template/default",
            f"redmine://issue-contract/{project_id}",
        ],
        pre_checks=[
            "Validate required custom fields from issue-contract.",
            "Respect read-only mode when enabled.",
        ],
        result_shape="Dict with created issue payload or validation error.",
    )


def update_redmine_issue_prompt(issue_id: int) -> str:
    """Playbook for calling update_redmine_issue."""
    return _render_tool_prompt(
        tool_name="update_redmine_issue",
        objective=(
            "Update issue fields while preserving workflow and "
            "custom-field constraints."
        ),
        required_inputs=[
            f"issue_id={issue_id}",
            "fields object with intended changes.",
        ],
        pre_checks=[
            "Resolve custom field names to IDs if names are ambiguous.",
            "Respect read-only mode when enabled.",
        ],
        result_shape="Dict with updated issue payload or error details.",
    )


def list_redmine_issue_statuses_prompt() -> str:
    """Playbook for calling list_redmine_issue_statuses."""
    return _render_tool_prompt(
        tool_name="list_redmine_issue_statuses",
        objective="List all statuses configured in the Redmine instance.",
        required_inputs=["No arguments required."],
        result_shape="List[status] with IDs and names.",
    )


def get_redmine_issue_allowed_statuses_prompt(issue_id: int) -> str:
    """Playbook for calling get_redmine_issue_allowed_statuses."""
    return _render_tool_prompt(
        tool_name="get_redmine_issue_allowed_statuses",
        objective="Get allowed transitions for a specific issue.",
        required_inputs=[f"issue_id={issue_id}"],
        pre_checks=["Use this before status changes to avoid invalid transitions."],
        result_shape="Dict with current_status and allowed_statuses.",
    )


def get_redmine_project_workflow_prompt(project_id: Union[str, int]) -> str:
    """Playbook for calling get_redmine_project_workflow."""
    return _render_tool_prompt(
        tool_name="get_redmine_project_workflow",
        objective=(
            "Infer transition patterns at project/tracker scope " "from sampled issues."
        ),
        required_inputs=[
            f"project_id={project_id}",
            "tracker_id/status_id/sample_limit optional.",
        ],
        recommended_resources=[f"redmine://workflow/{project_id}"],
        pre_checks=[
            "Increase sample_limit only when default snapshot is insufficient."
        ],
        result_shape="Dict containing workflow_by_current_status and sample metadata.",
    )


def get_issue_workflow_context_prompt(mode: str = "issue") -> str:
    """Playbook for calling get_issue_workflow_context."""
    return _render_tool_prompt(
        tool_name="get_issue_workflow_context",
        objective=(
            "Use one consolidated endpoint for statuses, issue transitions, "
            "or project workflow."
        ),
        required_inputs=[
            f"mode={mode} (statuses|issue|project|transition_check)",
            "issue_id for issue/transition_check modes",
            "project_id for project mode",
        ],
        pre_checks=[
            "Provide target_status_id or target_status_name for transition_check mode."
        ],
        result_shape="Dict with mode + data or validation error.",
    )


def manage_time_entries_prompt(action: str) -> str:
    """Playbook for calling manage_time_entries."""
    return _render_tool_prompt(
        tool_name="manage_time_entries",
        objective=(
            "Run list/create/update/activities workflows for "
            "time entries via one interface."
        ),
        required_inputs=[
            f"action={action} (list|create|update|activities)",
            "hours for create",
            "time_entry_id for update",
        ],
        recommended_resources=["redmine://time-entry/contract"],
        pre_checks=[
            "For create ensure project_id or issue_id is provided.",
            "Use spent_on format YYYY-MM-DD when provided.",
        ],
        result_shape="Dict with action + data or error.",
    )


def get_redmine_attachment_download_url_prompt(attachment_id: int) -> str:
    """Playbook for calling get_redmine_attachment_download_url."""
    return _render_tool_prompt(
        tool_name="get_redmine_attachment_download_url",
        objective="Get temporary HTTP URL for attachment retrieval.",
        required_inputs=[f"attachment_id={attachment_id}"],
        pre_checks=[
            "Call this after confirming the attachment belongs to the "
            "user-requested issue/wiki page."
        ],
        result_shape="Dict with download URL and expiry metadata.",
    )


def summarize_project_status_prompt(project_id: Union[str, int], days: int = 30) -> str:
    """Playbook for calling summarize_project_status."""
    return _render_tool_prompt(
        tool_name="summarize_project_status",
        objective="Generate status summary trends over a defined lookback window.",
        required_inputs=[f"project_id={project_id}", f"days={days}"],
        pre_checks=[
            "Use small day range for focused status checks and faster responses."
        ],
        result_shape="Dict with aggregate issue signals and summary text.",
    )


def search_entire_redmine_prompt(query: str) -> str:
    """Playbook for calling search_entire_redmine."""
    return _render_tool_prompt(
        tool_name="search_entire_redmine",
        objective="Search issues and wiki pages across accessible projects.",
        required_inputs=[
            f"query={query}",
            "optional resources filter and pagination params.",
        ],
        pre_checks=[
            "Use resources filter when users want only issues or only wiki pages."
        ],
        result_shape="Dict with matched resources and pagination metadata.",
    )


def get_redmine_wiki_page_prompt(
    project_id: Union[str, int], wiki_page_title: str
) -> str:
    """Playbook for calling get_redmine_wiki_page."""
    return _render_tool_prompt(
        tool_name="get_redmine_wiki_page",
        objective=(
            "Load wiki page content, optionally with attachments "
            "and historical version."
        ),
        required_inputs=[
            f"project_id={project_id}",
            f"wiki_page_title={wiki_page_title}",
            "version/include_attachments optional",
        ],
        result_shape="Dict with page content, metadata, and optional attachments.",
    )


def create_redmine_wiki_page_prompt(
    project_id: Union[str, int], wiki_page_title: str
) -> str:
    """Playbook for calling create_redmine_wiki_page."""
    return _render_tool_prompt(
        tool_name="create_redmine_wiki_page",
        objective="Create new wiki page content in a project.",
        required_inputs=[
            f"project_id={project_id}",
            f"wiki_page_title={wiki_page_title}",
            "text body",
        ],
        pre_checks=["Respect read-only mode when enabled."],
        result_shape="Dict with created wiki page payload.",
    )


def update_redmine_wiki_page_prompt(
    project_id: Union[str, int], wiki_page_title: str
) -> str:
    """Playbook for calling update_redmine_wiki_page."""
    return _render_tool_prompt(
        tool_name="update_redmine_wiki_page",
        objective="Update wiki page text and optional edit comments.",
        required_inputs=[
            f"project_id={project_id}",
            f"wiki_page_title={wiki_page_title}",
            "text body",
        ],
        pre_checks=["Respect read-only mode when enabled."],
        result_shape="Dict with updated wiki page payload.",
    )


def delete_redmine_wiki_page_prompt(
    project_id: Union[str, int], wiki_page_title: str
) -> str:
    """Playbook for calling delete_redmine_wiki_page."""
    return _render_tool_prompt(
        tool_name="delete_redmine_wiki_page",
        objective="Delete a wiki page from a project namespace.",
        required_inputs=[
            f"project_id={project_id}",
            f"wiki_page_title={wiki_page_title}",
        ],
        pre_checks=["Respect read-only mode when enabled."],
        result_shape="Dict confirming deletion or reporting failure.",
    )


def list_project_members_prompt(project_id: Union[str, int]) -> str:
    """Playbook for calling list_project_members."""
    return _render_tool_prompt(
        tool_name="list_project_members",
        objective="List project members and role assignments.",
        required_inputs=[f"project_id={project_id}"],
        result_shape="List[membership] entries with user and role data.",
    )


def list_time_entries_prompt(project_id: Optional[Union[str, int]] = None) -> str:
    """Playbook for calling list_time_entries."""
    scope = project_id if project_id is not None else "all accessible scope"
    return _render_tool_prompt(
        tool_name="list_time_entries",
        objective="List time entries with optional project/issue/user/date filters.",
        required_inputs=[f"project scope={scope}", "limit/offset for pagination"],
        recommended_resources=["redmine://time-entry/contract"],
        pre_checks=[
            "Use from_date/to_date in YYYY-MM-DD format when filtering by date."
        ],
        result_shape="List[time_entry] or error payload.",
    )


def create_time_entry_prompt(hours: float) -> str:
    """Playbook for calling create_time_entry."""
    return _render_tool_prompt(
        tool_name="create_time_entry",
        objective="Create a new time entry tied to project or issue scope.",
        required_inputs=[f"hours={hours}", "project_id or issue_id"],
        recommended_resources=["redmine://time-entry/contract"],
        pre_checks=[
            "Ensure hours > 0.",
            "Use spent_on in YYYY-MM-DD format when provided.",
        ],
        result_shape="Dict with created time entry.",
    )


def update_time_entry_prompt(time_entry_id: int) -> str:
    """Playbook for calling update_time_entry."""
    return _render_tool_prompt(
        tool_name="update_time_entry",
        objective="Update hours/activity/comments/date for an existing time entry.",
        required_inputs=[
            f"time_entry_id={time_entry_id}",
            "at least one field to update",
        ],
        recommended_resources=["redmine://time-entry/contract"],
        pre_checks=["Ensure updated hours remains positive when supplied."],
        result_shape="Dict with updated time entry.",
    )


def list_time_entry_activities_prompt() -> str:
    """Playbook for calling list_time_entry_activities."""
    return _render_tool_prompt(
        tool_name="list_time_entry_activities",
        objective="List active activities available for logging time.",
        required_inputs=["No arguments required."],
        recommended_resources=["redmine://time-entry/contract"],
        result_shape="List[activity] with id/name/default metadata.",
    )


def cleanup_attachment_files_prompt() -> str:
    """Playbook for calling cleanup_attachment_files."""
    return _render_tool_prompt(
        tool_name="cleanup_attachment_files",
        objective="Run maintenance cleanup for expired local attachment cache files.",
        required_inputs=["No arguments required."],
        pre_checks=[
            "Prefer running after attachment-heavy operations or on "
            "scheduled maintenance."
        ],
        result_shape="Dict with cleanup counters and storage statistics.",
    )


_PROMPT_REGISTRY: List[tuple[str, Callable[..., str]]] = [
    ("redmine_server_operating_prompt", redmine_server_operating_prompt),
    ("get_redmine_issue_prompt", get_redmine_issue_prompt),
    ("list_redmine_projects_prompt", list_redmine_projects_prompt),
    (
        "list_project_issue_custom_fields_prompt",
        list_project_issue_custom_fields_prompt,
    ),
    ("list_redmine_versions_prompt", list_redmine_versions_prompt),
    ("list_redmine_issues_prompt", list_redmine_issues_prompt),
    ("search_redmine_issues_prompt", search_redmine_issues_prompt),
    ("create_redmine_issue_prompt", create_redmine_issue_prompt),
    ("update_redmine_issue_prompt", update_redmine_issue_prompt),
    ("list_redmine_issue_statuses_prompt", list_redmine_issue_statuses_prompt),
    (
        "get_redmine_issue_allowed_statuses_prompt",
        get_redmine_issue_allowed_statuses_prompt,
    ),
    ("get_redmine_project_workflow_prompt", get_redmine_project_workflow_prompt),
    ("get_issue_workflow_context_prompt", get_issue_workflow_context_prompt),
    ("manage_time_entries_prompt", manage_time_entries_prompt),
    (
        "get_redmine_attachment_download_url_prompt",
        get_redmine_attachment_download_url_prompt,
    ),
    ("summarize_project_status_prompt", summarize_project_status_prompt),
    ("search_entire_redmine_prompt", search_entire_redmine_prompt),
    ("get_redmine_wiki_page_prompt", get_redmine_wiki_page_prompt),
    ("create_redmine_wiki_page_prompt", create_redmine_wiki_page_prompt),
    ("update_redmine_wiki_page_prompt", update_redmine_wiki_page_prompt),
    ("delete_redmine_wiki_page_prompt", delete_redmine_wiki_page_prompt),
    ("list_project_members_prompt", list_project_members_prompt),
    ("list_time_entries_prompt", list_time_entries_prompt),
    ("create_time_entry_prompt", create_time_entry_prompt),
    ("update_time_entry_prompt", update_time_entry_prompt),
    ("list_time_entry_activities_prompt", list_time_entry_activities_prompt),
    ("cleanup_attachment_files_prompt", cleanup_attachment_files_prompt),
]


def register_tool_prompts(mcp: Any) -> None:
    """Register all per-tool prompt playbooks on the provided FastMCP server."""
    for prompt_name, prompt_fn in _PROMPT_REGISTRY:
        mcp.prompt(name=prompt_name)(prompt_fn)
