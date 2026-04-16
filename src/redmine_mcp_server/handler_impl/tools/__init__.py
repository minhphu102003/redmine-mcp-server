"""Dependency-injected tool implementations extracted from redmine_handler."""

from .analytics import search_entire_redmine_impl, summarize_project_status_impl
from .attachments import (
    cleanup_attachment_files_impl,
    get_redmine_attachment_download_url_impl,
)
from .issues import (
    create_redmine_issue_impl,
    get_redmine_issue_impl,
    list_redmine_issues_impl,
    search_redmine_issues_impl,
    update_redmine_issue_impl,
)
from .projects import (
    list_project_issue_custom_fields_impl,
    list_project_members_impl,
    list_redmine_projects_impl,
    list_redmine_versions_impl,
)
from .time_entries import (
    create_time_entry_impl,
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

__all__ = [
    "cleanup_attachment_files_impl",
    "create_redmine_issue_impl",
    "create_redmine_wiki_page_impl",
    "create_time_entry_impl",
    "delete_redmine_wiki_page_impl",
    "get_redmine_attachment_download_url_impl",
    "get_redmine_issue_impl",
    "get_redmine_wiki_page_impl",
    "list_project_issue_custom_fields_impl",
    "list_project_members_impl",
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
]
