"""
MCP tools for Redmine integration.

This module provides Model Context Protocol (MCP) tools for interacting with Redmine
project management systems. It includes functionality to retrieve issue details,
list projects, and manage Redmine data through MCP-compatible interfaces.

The module handles authentication via either API key or username/password credentials,
and provides comprehensive error handling for network and authentication issues.

Tools provided:
    - get_redmine_issue: Retrieve detailed information about a specific issue
    - list_redmine_projects: Get a list of all accessible Redmine projects

Environment Variables Required:
    - REDMINE_URL: Base URL of the Redmine instance
    - REDMINE_API_KEY: API key for authentication (preferred), OR
    - REDMINE_USERNAME + REDMINE_PASSWORD: Username/password authentication

Dependencies:
    - redminelib: Python library for Redmine API interactions
    - python-dotenv: Environment variable management
    - fastmcp: FastMCP server implementation
"""

import os
import asyncio  # noqa: F401
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from dotenv import load_dotenv
from redminelib import Redmine
from redminelib.exceptions import (
    ResourceNotFoundError,
    VersionMismatchError,
    ValidationError,
)
from fastmcp import FastMCP
from .file_manager import AttachmentFileManager
from .handler_impl import issue_fields as _issue_fields
from .handler_impl.errors import handle_redmine_error
from .handler_impl.tools import (
    cleanup_attachment_files_impl,
    create_redmine_issue_impl,
    create_redmine_wiki_page_impl,
    create_time_entry_impl,
    delete_redmine_wiki_page_impl,
    get_redmine_attachment_download_url_impl,
    get_redmine_issue_impl,
    get_redmine_wiki_page_impl,
    list_project_issue_custom_fields_impl,
    list_project_members_impl,
    list_redmine_issues_impl,
    list_redmine_projects_impl,
    list_redmine_versions_impl,
    list_time_entries_impl,
    list_time_entry_activities_impl,
    search_entire_redmine_impl,
    search_redmine_issues_impl,
    summarize_project_status_impl,
    update_redmine_issue_impl,
    update_redmine_wiki_page_impl,
    update_time_entry_impl,
)
from .handler_impl.http_routes import (
    CleanupTaskManager,
    cleanup_status_payload,
    ensure_cleanup_started,
    health_payload,
    serve_attachment_by_id,
)
from .serialization import (  # noqa: F401
    wrap_insecure_content,
    _coerce_json_safe,
    _custom_fields_to_list,
    _issue_to_dict,
    _resource_to_dict,
    _issue_to_dict_selective,
    _journals_to_list,
    _attachments_to_list,
    _version_to_dict,
    _analyze_issues,
    _membership_to_dict,
    _time_entry_to_dict,
    _wiki_page_to_dict,
)

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables from .env file
# Search order: current working directory first, then package directory
_env_paths = [
    Path.cwd() / ".env",  # User's current working directory (highest priority)
    Path(__file__).parent.parent.parent / ".env",  # Package directory (fallback)
]

_env_loaded = False
for _env_path in _env_paths:
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path))
        logger.info(f"Loaded .env from: {_env_path}")
        _env_loaded = True
        break

if not _env_loaded:
    # Try default load_dotenv() behavior as final fallback
    load_dotenv()

# Load Redmine configuration
REDMINE_URL = os.getenv("REDMINE_URL")
REDMINE_USERNAME = os.getenv("REDMINE_USERNAME")
REDMINE_PASSWORD = os.getenv("REDMINE_PASSWORD")
REDMINE_API_KEY = os.getenv("REDMINE_API_KEY")

# Auth mode: "oauth" uses per-request Bearer tokens via OAuth middleware;
# "legacy" uses REDMINE_API_KEY or REDMINE_USERNAME/REDMINE_PASSWORD (default).
REDMINE_AUTH_MODE = os.getenv("REDMINE_AUTH_MODE", "legacy").lower()

# SSL Configuration (optional)
REDMINE_SSL_VERIFY = os.getenv("REDMINE_SSL_VERIFY", "true").lower() == "true"
REDMINE_SSL_CERT = os.getenv("REDMINE_SSL_CERT")
REDMINE_SSL_CLIENT_CERT = os.getenv("REDMINE_SSL_CLIENT_CERT")

if not REDMINE_URL:
    logger.warning(
        "REDMINE_URL not set. "
        "Please create a .env file in your working directory with REDMINE_URL defined."
    )
elif REDMINE_AUTH_MODE != "oauth" and not (
    REDMINE_API_KEY or (REDMINE_USERNAME and REDMINE_PASSWORD)
):
    logger.warning(
        "No Redmine authentication configured. "
        "Please set REDMINE_API_KEY or REDMINE_USERNAME/REDMINE_PASSWORD "
        "in your .env file, or set REDMINE_AUTH_MODE=oauth."
    )


# Build SSL requests config from environment (used by _get_redmine_client)
def _build_requests_config() -> dict:
    requests_config = {}
    if not REDMINE_SSL_VERIFY:
        requests_config["verify"] = False
        logger.warning("SSL verification is DISABLED - use only for development!")
    elif REDMINE_SSL_CERT:
        cert_path = Path(REDMINE_SSL_CERT).resolve()
        if not cert_path.exists():
            raise FileNotFoundError(
                f"SSL certificate not found: {REDMINE_SSL_CERT} "
                f"(resolved to: {cert_path})"
            )
        if not cert_path.is_file():
            raise ValueError(
                f"SSL certificate path must be a file, not directory: {cert_path}"
            )
        requests_config["verify"] = str(cert_path)
        logger.info(f"Using custom SSL certificate: {cert_path}")
    if REDMINE_SSL_CLIENT_CERT:
        if "," in REDMINE_SSL_CLIENT_CERT:
            cert, key = REDMINE_SSL_CLIENT_CERT.split(",", 1)
            requests_config["cert"] = (cert.strip(), key.strip())
            logger.info("Using client certificate for mutual TLS")
        else:
            requests_config["cert"] = REDMINE_SSL_CLIENT_CERT
            logger.info("Using client certificate for mutual TLS")
    return requests_config


# Test-compatibility hook: existing unit tests patch this module-level variable
# directly. When non-None, _get_redmine_client() returns it immediately.
# In production this stays None and per-request auth is always used.
redmine = None

# Cached legacy-mode client — avoids recreating Redmine() on every tool call
# when running without OAuth.
_legacy_client = None


def _build_legacy_client() -> Redmine:
    """Build a Redmine client using legacy credentials (API key or user/pass)."""
    requests_config = _build_requests_config()
    if REDMINE_API_KEY:
        if requests_config:
            return Redmine(REDMINE_URL, key=REDMINE_API_KEY, requests=requests_config)
        return Redmine(REDMINE_URL, key=REDMINE_API_KEY)
    elif REDMINE_USERNAME and REDMINE_PASSWORD:
        if requests_config:
            return Redmine(
                REDMINE_URL,
                username=REDMINE_USERNAME,
                password=REDMINE_PASSWORD,
                requests=requests_config,
            )
        return Redmine(
            REDMINE_URL, username=REDMINE_USERNAME, password=REDMINE_PASSWORD
        )
    else:
        raise RuntimeError(
            "No Redmine authentication available. "
            "Set REDMINE_AUTH_MODE=oauth or configure REDMINE_API_KEY / "
            "REDMINE_USERNAME+REDMINE_PASSWORD."
        )


def _get_redmine_client() -> Redmine:
    global _legacy_client

    if redmine is not None:
        return redmine

    from .oauth_middleware import current_redmine_token

    token = current_redmine_token.get()

    if token:
        # OAuth mode: per-request client with Bearer token (cannot be cached)
        requests_config = _build_requests_config()
        headers = {"Authorization": f"Bearer {token}"}
        if requests_config:
            return Redmine(
                REDMINE_URL, requests={"headers": headers, **requests_config}
            )
        return Redmine(REDMINE_URL, requests={"headers": headers})

    # Legacy mode: reuse a cached singleton
    if _legacy_client is None:
        _legacy_client = _build_legacy_client()
    return _legacy_client


# Initialize FastMCP server
mcp = FastMCP("redmine_mcp_tools")


# Initialize cleanup manager
cleanup_manager = CleanupTaskManager()


# Global flag to track if cleanup has been initialized
_cleanup_initialized = False


async def _ensure_cleanup_started():
    """Ensure cleanup task is started (lazy initialization)."""
    global _cleanup_initialized
    _cleanup_initialized, _ = await ensure_cleanup_started(
        cleanup_manager, _cleanup_initialized
    )


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for container orchestration and monitoring."""
    from starlette.responses import JSONResponse

    await _ensure_cleanup_started()
    return JSONResponse(health_payload(REDMINE_AUTH_MODE))


@mcp.custom_route("/files/{file_id}", methods=["GET"])
async def serve_attachment(request):
    """Serve downloaded attachment files via HTTP."""
    from starlette.exceptions import HTTPException

    result = serve_attachment_by_id(request.path_params["file_id"])
    if isinstance(result, dict):
        raise HTTPException(
            status_code=result.get("status_code", 500),
            detail=result.get("detail", "Unknown error"),
        )

    return result


@mcp.custom_route("/cleanup/status", methods=["GET"])
async def cleanup_status(request):
    """Get cleanup task status and statistics."""
    from starlette.responses import JSONResponse

    return JSONResponse(cleanup_status_payload(cleanup_manager))


def _handle_redmine_error(
    e: Exception, operation: str, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Compatibility wrapper for centralized error handling."""
    return handle_redmine_error(
        e=e,
        operation=operation,
        redmine_url=REDMINE_URL or "REDMINE_URL not configured",
        context=context,
    )


_DEFAULT_REQUIRED_CUSTOM_FIELD_VALUES: Dict[str, Any] = (
    _issue_fields._DEFAULT_REQUIRED_CUSTOM_FIELD_VALUES
)
_STANDARD_ISSUE_UPDATE_FIELDS: Set[str] = _issue_fields._STANDARD_ISSUE_UPDATE_FIELDS


def _is_true_env(var_name: str, default: str = "false") -> bool:
    """Parse common truthy env-var values."""
    return os.getenv(var_name, default).strip().lower() in {"1", "true", "yes", "on"}


def _is_read_only_mode() -> bool:
    """Check if the server is in read-only mode."""
    return _is_true_env("REDMINE_MCP_READ_ONLY", "false")


_READ_ONLY_ERROR = {
    "error": "This server is in read-only mode (REDMINE_MCP_READ_ONLY=true). "
    "Write operations are disabled."
}


def _load_required_custom_field_defaults() -> Dict[str, Any]:
    """Load normalized custom field defaults from env + built-in fallbacks."""
    return _issue_fields._load_required_custom_field_defaults(
        defaults=_DEFAULT_REQUIRED_CUSTOM_FIELD_VALUES
    )


def _augment_fields_with_required_custom_fields(
    project_id: int,
    issue_fields: Dict[str, Any],
    missing_field_names: List[str],
) -> Dict[str, Any]:
    """Populate missing required custom fields based on project metadata."""
    return _issue_fields._augment_fields_with_required_custom_fields(
        project_id,
        issue_fields,
        missing_field_names,
        get_client=_get_redmine_client,
        defaults=_DEFAULT_REQUIRED_CUSTOM_FIELD_VALUES,
    )


def _resolve_project_issue_custom_fields(issue_id: int) -> List[Any]:
    """Load project custom-field definitions for a given issue."""
    return _issue_fields._resolve_project_issue_custom_fields(
        issue_id,
        get_client=_get_redmine_client,
    )


def _map_named_custom_fields_for_update(
    issue_id: int, update_fields: Dict[str, Any]
) -> Dict[str, Any]:
    """Map named custom fields in an update payload to custom_fields entries."""
    return _issue_fields._map_named_custom_fields_for_update(
        issue_id,
        update_fields,
        get_client=_get_redmine_client,
    )


@mcp.tool()
async def get_redmine_issue(
    issue_id: int,
    include_journals: bool = True,
    include_attachments: bool = True,
    include_custom_fields: bool = True,
    journal_limit: Optional[int] = None,
    journal_offset: int = 0,
    include_watchers: bool = False,
    include_relations: bool = False,
    include_children: bool = False,
) -> Dict[str, Any]:
    """Retrieve a specific Redmine issue by ID."""
    return await get_redmine_issue_impl(
        issue_id,
        include_journals,
        include_attachments,
        include_custom_fields,
        journal_limit,
        journal_offset,
        include_watchers,
        include_relations,
        include_children,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        issue_to_dict=_issue_to_dict,
        journals_to_list=_journals_to_list,
        attachments_to_list=_attachments_to_list,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_redmine_projects() -> List[Dict[str, Any]]:
    """Lists all accessible projects in Redmine."""
    return await list_redmine_projects_impl(
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_project_issue_custom_fields(
    project_id: Union[str, int], tracker_id: Optional[Union[str, int]] = None
) -> List[Dict[str, Any]]:
    """List issue custom fields configured for a project."""
    return await list_project_issue_custom_fields_impl(
        project_id,
        tracker_id,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        custom_field_applies_to_tracker=_issue_fields._custom_field_applies_to_tracker,
        custom_field_to_dict=_issue_fields._custom_field_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_redmine_versions(
    project_id: Union[str, int],
    status_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List versions (roadmap milestones) for a Redmine project."""
    return await list_redmine_versions_impl(
        project_id,
        status_filter,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        version_to_dict=_version_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_redmine_issues(
    project_id: Optional[Union[int, str]] = None,
    status_id: Optional[int] = None,
    tracker_id: Optional[int] = None,
    assigned_to_id: Optional[Union[int, str]] = None,
    priority_id: Optional[int] = None,
    fixed_version_id: Optional[int] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = 25,
    offset: int = 0,
    include_pagination_info: bool = False,
    fields: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List Redmine issues with flexible filtering and pagination support."""
    return await list_redmine_issues_impl(
        project_id,
        status_id,
        tracker_id,
        assigned_to_id,
        priority_id,
        fixed_version_id,
        sort,
        limit,
        offset,
        include_pagination_info,
        fields,
        filters,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        issue_to_dict_selective=_issue_to_dict_selective,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def search_redmine_issues(
    query: str,
    limit: Optional[int] = 25,
    offset: int = 0,
    include_pagination_info: bool = False,
    fields: Optional[List[str]] = None,
    scope: Optional[str] = None,
    open_issues: bool = False,
    options: Optional[Dict[str, Any]] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Search Redmine issues matching a query string with pagination support."""
    return await search_redmine_issues_impl(
        query,
        limit,
        offset,
        include_pagination_info,
        fields,
        scope,
        open_issues,
        options,
        get_client=_get_redmine_client,
        issue_to_dict_selective=_issue_to_dict_selective,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def create_redmine_issue(
    project_id: int,
    subject: str,
    description: str = "",
    fields: Optional[Union[Dict[str, Any], str]] = None,
    extra_fields: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """Create a new issue in Redmine."""
    return await create_redmine_issue_impl(
        project_id,
        subject,
        description,
        fields,
        extra_fields,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        parse_create_issue_fields=_issue_fields._parse_create_issue_fields,
        parse_optional_object_payload=_issue_fields._parse_optional_object_payload,
        get_client=_get_redmine_client,
        issue_to_dict=_issue_to_dict,
        is_required_custom_field_autofill_enabled=(
            _issue_fields._is_required_custom_field_autofill_enabled
        ),
        extract_missing_required_field_names=(
            _issue_fields._extract_missing_required_field_names
        ),
        augment_fields_with_required_custom_fields=(
            _augment_fields_with_required_custom_fields
        ),
        handle_error=_handle_redmine_error,
        validation_error=ValidationError,
    )


@mcp.tool()
async def update_redmine_issue(issue_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing Redmine issue."""
    return await update_redmine_issue_impl(
        issue_id,
        fields,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        get_client=_get_redmine_client,
        map_named_custom_fields_for_update=_map_named_custom_fields_for_update,
        issue_to_dict=_issue_to_dict,
        is_required_custom_field_autofill_enabled=(
            _issue_fields._is_required_custom_field_autofill_enabled
        ),
        extract_missing_required_field_names=(
            _issue_fields._extract_missing_required_field_names
        ),
        augment_fields_with_required_custom_fields=(
            _augment_fields_with_required_custom_fields
        ),
        handle_error=_handle_redmine_error,
        validation_error=ValidationError,
    )


@mcp.tool()
async def get_redmine_attachment_download_url(
    attachment_id: int,
) -> Dict[str, Any]:
    """Get HTTP download URL for a Redmine attachment."""
    return await get_redmine_attachment_download_url_impl(
        attachment_id,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def summarize_project_status(project_id: int, days: int = 30) -> Dict[str, Any]:
    """Provide a summary of project status over the specified time period."""
    return await summarize_project_status_impl(
        project_id,
        days,
        get_client=_get_redmine_client,
        analyze_issues=_analyze_issues,
        handle_error=_handle_redmine_error,
        resource_not_found_error=ResourceNotFoundError,
    )


@mcp.tool()
async def search_entire_redmine(
    query: str,
    resources: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Search for issues and wiki pages across the Redmine instance."""
    return await search_entire_redmine_impl(
        query,
        resources,
        limit,
        offset,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        resource_to_dict=_resource_to_dict,
        handle_error=_handle_redmine_error,
        version_mismatch_error=VersionMismatchError,
    )


@mcp.tool()
async def get_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
    version: Optional[int] = None,
    include_attachments: bool = True,
) -> Dict[str, Any]:
    """Retrieve full wiki page content from Redmine."""
    return await get_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        version,
        include_attachments,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_ensure_cleanup_started,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def create_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
    text: str,
    comments: str = "",
) -> Dict[str, Any]:
    """Create a new wiki page in a Redmine project."""
    return await create_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        text,
        comments,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_ensure_cleanup_started,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def update_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
    text: str,
    comments: str = "",
) -> Dict[str, Any]:
    """Update an existing wiki page in a Redmine project."""
    return await update_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        text,
        comments,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_ensure_cleanup_started,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def delete_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
) -> Dict[str, Any]:
    """Delete a wiki page from a Redmine project."""
    return await delete_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_ensure_cleanup_started,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_project_members(
    project_id: Union[str, int],
) -> List[Dict[str, Any]]:
    """List members of a Redmine project."""
    return await list_project_members_impl(
        project_id,
        get_client=_get_redmine_client,
        membership_to_dict=_membership_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_time_entries(
    project_id: Optional[Union[str, int]] = None,
    issue_id: Optional[int] = None,
    user_id: Optional[Union[str, int]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List time entries from Redmine with filtering and pagination."""
    return await list_time_entries_impl(
        project_id,
        issue_id,
        user_id,
        from_date,
        to_date,
        limit,
        offset,
        get_client=_get_redmine_client,
        time_entry_to_dict=_time_entry_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def create_time_entry(
    hours: float,
    project_id: Optional[Union[str, int]] = None,
    issue_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    comments: str = "",
    spent_on: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new time entry in Redmine."""
    return await create_time_entry_impl(
        hours,
        project_id,
        issue_id,
        activity_id,
        comments,
        spent_on,
        get_client=_get_redmine_client,
        time_entry_to_dict=_time_entry_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def update_time_entry(
    time_entry_id: int,
    hours: Optional[float] = None,
    activity_id: Optional[int] = None,
    comments: Optional[str] = None,
    spent_on: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing time entry in Redmine."""
    return await update_time_entry_impl(
        time_entry_id,
        hours,
        activity_id,
        comments,
        spent_on,
        get_client=_get_redmine_client,
        time_entry_to_dict=_time_entry_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_time_entry_activities() -> List[Dict[str, Any]]:
    """List available time entry activities from Redmine."""
    return await list_time_entry_activities_impl(
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def cleanup_attachment_files() -> Dict[str, Any]:
    """Clean up expired attachment files and return storage statistics."""
    return await cleanup_attachment_files_impl(
        attachment_manager_factory=AttachmentFileManager,
        log=logger,
    )


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
