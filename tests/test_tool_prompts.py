"""Tests for MCP prompt playbooks associated with tool usage."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import tool_prompts as prompts  # noqa: E402


def test_render_tool_prompt_contains_expected_sections():
    """Shared prompt renderer should include common guide sections."""
    prompt = prompts._render_tool_prompt(
        tool_name="demo_tool",
        objective="Demo objective",
        required_inputs=["x=1"],
        recommended_resources=["redmine://demo/resource"],
        pre_checks=["Check inputs"],
        result_shape="Dict",
    )
    assert "You are preparing to call `demo_tool`." in prompt
    assert "Required inputs:" in prompt
    assert "Read these resources first when available:" in prompt
    assert "Pre-call checks:" in prompt
    assert "Expected result shape: Dict" in prompt
    assert "Output format for the user:" in prompt


def test_create_redmine_issue_prompt_references_contract_resources():
    """Issue creation prompt should direct callers to template + contract resources."""
    prompt = prompts.create_redmine_issue_prompt(project_id=5, subject="Fix login")
    assert "`create_redmine_issue`" in prompt
    assert "redmine://issue-template/default" in prompt
    assert "redmine://issue-contract/5" in prompt
    assert "Validate required custom fields from issue-contract." in prompt


def test_manage_time_entries_prompt_references_time_entry_contract():
    """Time entry prompt should require action semantics and contract resource."""
    prompt = prompts.manage_time_entries_prompt(action="create")
    assert "`manage_time_entries`" in prompt
    assert "action=create (list|create|update|activities)" in prompt
    assert "redmine://time-entry/contract" in prompt
    assert "hours for create" in prompt


def test_server_operating_prompt_has_global_protocol():
    """Global server prompt should define mandatory pre-tool protocol."""
    prompt = prompts.redmine_server_operating_prompt(user_goal="Create bug issue")
    assert "Global protocol (must run before any tool call):" in prompt
    assert "redmine://issue-template/default" in prompt
    assert "redmine://issue-contract/{project_id}[/{tracker_id}]" in prompt
    assert "redmine://workflow/{project_id}[/{tracker_id}]" in prompt
    assert "redmine://time-entry/contract" in prompt


def test_prompt_functions_exist_for_all_tools():
    """Each MCP tool in handler should have a sibling prompt playbook function."""
    expected_prompt_functions = [
        "redmine_server_operating_prompt",
        "get_redmine_issue_prompt",
        "list_redmine_projects_prompt",
        "list_project_issue_custom_fields_prompt",
        "list_redmine_versions_prompt",
        "list_redmine_issues_prompt",
        "search_redmine_issues_prompt",
        "create_redmine_issue_prompt",
        "update_redmine_issue_prompt",
        "list_redmine_issue_statuses_prompt",
        "get_redmine_issue_allowed_statuses_prompt",
        "get_redmine_project_workflow_prompt",
        "get_issue_workflow_context_prompt",
        "manage_time_entries_prompt",
        "get_redmine_attachment_download_url_prompt",
        "summarize_project_status_prompt",
        "search_entire_redmine_prompt",
        "get_redmine_wiki_page_prompt",
        "create_redmine_wiki_page_prompt",
        "update_redmine_wiki_page_prompt",
        "delete_redmine_wiki_page_prompt",
        "list_project_members_prompt",
        "list_time_entries_prompt",
        "create_time_entry_prompt",
        "update_time_entry_prompt",
        "list_time_entry_activities_prompt",
        "cleanup_attachment_files_prompt",
    ]

    missing = [name for name in expected_prompt_functions if not hasattr(prompts, name)]
    assert not missing, f"Missing prompt functions: {missing}"


def test_register_tool_prompts_registers_all_prompts():
    """Registration helper should expose one MCP prompt per tool prompt function."""

    class _DummyMCP:
        def __init__(self):
            self.registered = []

        def prompt(self, name):
            def _decorator(fn):
                self.registered.append((name, fn.__name__))
                return fn

            return _decorator

    mcp = _DummyMCP()
    prompts.register_tool_prompts(mcp)

    assert len(mcp.registered) == len(prompts._PROMPT_REGISTRY)
    assert (
        "create_redmine_issue_prompt",
        "create_redmine_issue_prompt",
    ) in mcp.registered
