"""Dependency-injected tool implementations extracted from redmine_handler."""

from .analytics import (
    export_weekly_report_docx_impl,
    export_weekly_report_markdown_impl,
    generate_scrum_report_impl,
    search_entire_redmine_impl,
    summarize_project_status_impl,
)
from .attachments import (
    cleanup_attachment_files_impl,
    get_redmine_attachment_download_url_impl,
)
from .issues import (
    create_redmine_issue_with_subtasks_impl,
    create_redmine_issue_impl,
    get_redmine_issue_impl,
    list_redmine_issues_impl,
    search_redmine_issues_impl,
    update_redmine_issue_impl,
)
from .projects import (
    list_project_issue_categories_impl,
    list_project_issue_custom_fields_impl,
    list_project_members_impl,
    list_project_trackers_impl,
    list_redmine_projects_impl,
    list_redmine_versions_impl,
)
from .project_context import get_project_issue_context_impl
from .relations import (
    create_redmine_issue_relation_impl,
    delete_redmine_issue_relation_impl,
)
from .time_entries import (
    create_time_entry_impl,
    delete_time_entry_impl,
    list_time_entries_impl,
    list_time_entry_activities_impl,
    update_time_entry_impl,
)
from .wiki import (
    create_redmine_wiki_page_impl,
    delete_redmine_wiki_page_impl,
    get_redmine_wiki_page_impl,
    update_redmine_wiki_page_impl,
)
from .workflow import (
    get_redmine_issue_allowed_statuses_impl,
    get_redmine_project_workflow_impl,
    list_redmine_issue_statuses_impl,
)
from .google_sheets import (
    append_google_sheet_impl,
    create_redmine_issues_from_bugs_impl,
    create_test_cases_on_sheet_impl,
    create_test_sheet_structure_impl,
    get_sheet_metadata_impl,
    read_google_sheet_impl,
    reopen_bug_impl,
    set_sheet_data_validation_impl,
    sync_redmine_status_to_sheet_impl,
    write_google_sheet_impl,
)

__all__ = [
    "cleanup_attachment_files_impl",
    "create_redmine_issue_with_subtasks_impl",
    "create_redmine_issue_impl",
    "create_redmine_wiki_page_impl",
    "create_time_entry_impl",
    "delete_redmine_wiki_page_impl",
    "delete_time_entry_impl",
    "get_redmine_attachment_download_url_impl",
    "get_redmine_issue_impl",
    "get_redmine_wiki_page_impl",
    "list_project_issue_categories_impl",
    "list_project_issue_custom_fields_impl",
    "list_project_members_impl",
    "list_project_trackers_impl",
    "list_redmine_issues_impl",
    "list_redmine_projects_impl",
    "list_redmine_versions_impl",
    "list_time_entries_impl",
    "list_time_entry_activities_impl",
    "search_entire_redmine_impl",
    "search_redmine_issues_impl",
    "summarize_project_status_impl",
    "update_redmine_issue_impl",
    "update_redmine_wiki_page_impl",
    "update_time_entry_impl",
    "list_redmine_issue_statuses_impl",
    "get_redmine_issue_allowed_statuses_impl",
    "get_redmine_project_workflow_impl",
    "generate_scrum_report_impl",
    "export_weekly_report_markdown_impl",
    "export_weekly_report_docx_impl",
    "get_project_issue_context_impl",
    "create_redmine_issue_relation_impl",
    "delete_redmine_issue_relation_impl",
    "append_google_sheet_impl",
    "create_redmine_issues_from_bugs_impl",
    "create_test_cases_on_sheet_impl",
    "create_test_sheet_structure_impl",
    "get_sheet_metadata_impl",
    "read_google_sheet_impl",
    "reopen_bug_impl",
    "set_sheet_data_validation_impl",
    "sync_redmine_status_to_sheet_impl",
    "write_google_sheet_impl",
]
