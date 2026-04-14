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
import uuid
import json
import asyncio  # noqa: F401
import logging
from datetime import datetime, timedelta, timezone
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
    """Retrieve a specific Redmine issue by ID.

    Args:
        issue_id: The ID of the issue to retrieve
        include_journals: Whether to include journals (comments) in the result.
            Defaults to ``True``.
        include_attachments: Whether to include attachments metadata in the
            result. Defaults to ``True``.
        include_custom_fields: Whether to include custom fields in the
            result. Defaults to ``True``.
        journal_limit: Maximum number of journals to return. When set,
            enables journal pagination and adds ``journal_pagination``
            metadata to the response.
        journal_offset: Number of journals to skip (used with
            ``journal_limit``). Defaults to ``0``.

    Returns:
        A dictionary containing issue details. If ``include_journals`` is ``True``
        and the issue has journals, they will be returned under the ``"journals"``
        key. If ``include_attachments`` is ``True`` and attachments exist they
        will be returned under the ``"attachments"`` key. On failure a dictionary
        with an ``"error"`` key is returned.
    """

    # Ensure cleanup task is started (lazy initialization)
    await _ensure_cleanup_started()
    try:
        # python-redmine is synchronous, so we don't use await here for the library call
        includes = []
        if include_journals:
            includes.append("journals")
        if include_attachments:
            includes.append("attachments")
        if include_watchers:
            includes.append("watchers")
        if include_relations:
            includes.append("relations")
        if include_children:
            includes.append("children")

        if includes:
            issue = _get_redmine_client().issue.get(
                issue_id, include=",".join(includes)
            )
        else:
            issue = _get_redmine_client().issue.get(issue_id)

        result = _issue_to_dict(issue, include_custom_fields=include_custom_fields)
        if include_journals:
            all_journals = _journals_to_list(issue)
            if journal_limit is not None:
                total = len(all_journals)
                offset = journal_offset
                paginated = all_journals[offset : offset + journal_limit]
                result["journals"] = paginated
                result["journal_pagination"] = {
                    "total": total,
                    "offset": offset,
                    "limit": journal_limit,
                    "count": len(paginated),
                    "has_more": (offset + journal_limit) < total,
                }
            else:
                result["journals"] = all_journals
        if include_attachments:
            result["attachments"] = _attachments_to_list(issue)

        if include_watchers:
            raw = getattr(issue, "watchers", None) or []
            result["watchers"] = [{"id": w.id, "name": w.name} for w in raw]
        if include_relations:
            raw = getattr(issue, "relations", None) or []
            result["relations"] = [
                {
                    "id": r.id,
                    "issue_id": r.issue_id,
                    "issue_to_id": r.issue_to_id,
                    "relation_type": r.relation_type,
                }
                for r in raw
            ]
        if include_children:
            raw = getattr(issue, "children", None) or []
            result["children"] = [
                {
                    "id": c.id,
                    "subject": getattr(c, "subject", ""),
                    "tracker": (
                        {"id": c.tracker.id, "name": c.tracker.name}
                        if getattr(c, "tracker", None)
                        else None
                    ),
                }
                for c in raw
            ]

        return result
    except Exception as e:
        return _handle_redmine_error(
            e,
            f"fetching issue {issue_id}",
            {"resource_type": "issue", "resource_id": issue_id},
        )


@mcp.tool()
async def list_redmine_projects() -> List[Dict[str, Any]]:
    """
    Lists all accessible projects in Redmine.
    Returns:
        A list of dictionaries, each representing a project.
    """
    try:
        projects = _get_redmine_client().project.all()
        return [
            {
                "id": project.id,
                "name": project.name,
                "identifier": project.identifier,
                "description": getattr(project, "description", ""),
                "created_on": (
                    project.created_on.isoformat()
                    if getattr(project, "created_on", None) is not None
                    else None
                ),
            }
            for project in projects
        ]
    except Exception as e:
        return [_handle_redmine_error(e, "listing projects")]


@mcp.tool()
async def list_project_issue_custom_fields(
    project_id: Union[str, int], tracker_id: Optional[Union[str, int]] = None
) -> List[Dict[str, Any]]:
    """List issue custom fields configured for a project.

    Args:
        project_id: Project identifier (ID number or string identifier).
        tracker_id: Optional tracker ID to filter custom fields by applicability.

    Returns:
        A list of custom field metadata dictionaries. On failure a list containing
        a single dictionary with an ``"error"`` key is returned.
    """

    parsed_tracker_id: Optional[int] = None
    if tracker_id is not None:
        try:
            parsed_tracker_id = int(tracker_id)
        except (TypeError, ValueError):
            return [
                {
                    "error": (
                        f"Invalid tracker_id '{tracker_id}'. "
                        "Expected an integer tracker ID."
                    )
                }
            ]

    await _ensure_cleanup_started()

    try:
        project = _get_redmine_client().project.get(
            project_id, include="issue_custom_fields"
        )
        custom_fields = getattr(project, "issue_custom_fields", None) or []

        result: List[Dict[str, Any]] = []
        for custom_field in custom_fields:
            if not _issue_fields._custom_field_applies_to_tracker(
                custom_field,
                parsed_tracker_id,
            ):
                continue
            result.append(_issue_fields._custom_field_to_dict(custom_field))

        return result
    except Exception as e:
        return [
            _handle_redmine_error(
                e,
                f"listing issue custom fields for project {project_id}",
                {"resource_type": "project", "resource_id": project_id},
            )
        ]


@mcp.tool()
async def list_redmine_versions(
    project_id: Union[str, int],
    status_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List versions (roadmap milestones) for a Redmine project.

    Args:
        project_id: The project ID (numeric) or identifier (string).
        status_filter: Optional filter by version status.
            Allowed values: open, locked, closed.
            When None, all versions are returned.

    Returns:
        A list of version dictionaries. On failure a list containing
        a single dictionary with an ``"error"`` key is returned.
    """

    # Validate status_filter before making API call
    valid_statuses = {"open", "locked", "closed"}
    if status_filter is not None:
        status_filter = str(status_filter).lower()
        if status_filter not in valid_statuses:
            return [
                {
                    "error": (
                        f"Invalid status_filter '{status_filter}'. "
                        f"Allowed values: open, locked, closed"
                    )
                }
            ]

    await _ensure_cleanup_started()
    try:
        versions = _get_redmine_client().version.filter(project_id=project_id)
        result = []
        for version in versions:
            if status_filter is not None:
                if getattr(version, "status", "") != status_filter:
                    continue
            result.append(_version_to_dict(version))
        return result
    except Exception as e:
        return [
            _handle_redmine_error(
                e,
                f"listing versions for project {project_id}",
                {"resource_type": "project", "resource_id": project_id},
            )
        ]


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
    """List Redmine issues with flexible filtering and pagination support.

    A general-purpose tool for listing issues from Redmine. Supports
    filtering by project, status, assignee, tracker, priority, and any
    other Redmine issue filter. Use this to list all issues in a project,
    find unassigned issues, or apply any combination of filters.

    Args:
        project_id: Filter by project (ID or string identifier).
        status_id: Filter by status ID.
        tracker_id: Filter by tracker ID.
        assigned_to_id: Filter by assignee. Use a numeric user ID or the
            special value 'me' to retrieve issues assigned to the currently
            authenticated user.
        priority_id: Filter by priority ID.
        fixed_version_id: Filter by target version/milestone ID.
        sort: Sort order (e.g., "updated_on:desc").
        limit: Maximum number of issues to return (default: 25, max: 1000).
        offset: Number of issues to skip for pagination (default: 0).
        include_pagination_info: Return structured response with pagination
            metadata (default: False).
        fields: List of field names to include in results (default: all).
            Available: id, subject, description, project, status, priority,
            author, assigned_to, created_on, updated_on.
        filters: Additional Redmine API filter parameters as a dict. Use this
            for any filter not listed above (e.g., {"cf_1": "value"}).

    Returns:
        List[Dict] (default) or Dict with 'issues' and 'pagination' keys.
        Issues are limited to prevent token overflow (25,000 token MCP limit).

    Examples:
        >>> await list_redmine_issues(project_id=1)
        [{"id": 1, "subject": "Issue 1", ...}, ...]

        >>> await list_redmine_issues(project_id="my-project", status_id=1)
        [{"id": 2, "subject": "Open issue", ...}, ...]

        >>> await list_redmine_issues(
        ...     project_id=1, limit=25, offset=50, include_pagination_info=True
        ... )
        {
            "issues": [...],
            "pagination": {"total": 150, "has_next": True, "next_offset": 75, ...}
        }

        >>> await list_redmine_issues(
        ...     project_id=1, fields=["id", "subject", "status"]
        ... )
        [{"id": 1, "subject": "Bug fix", "status": {...}}, ...]

    Performance:
        - Memory efficient: Uses server-side pagination
        - Token efficient: Default limit keeps response under 2000 tokens
        - Further reduce tokens: Use fields parameter for minimal data transfer
        - Time efficient: Typically <500ms for limit=25
    """

    # Ensure cleanup task is started (lazy initialization)
    await _ensure_cleanup_started()

    try:
        # Build Redmine API filter dict from explicit parameters
        redmine_api_filters: Dict[str, Any] = {}
        if project_id is not None:
            redmine_api_filters["project_id"] = project_id
        if status_id is not None:
            redmine_api_filters["status_id"] = status_id
        if tracker_id is not None:
            redmine_api_filters["tracker_id"] = tracker_id
        if assigned_to_id is not None:
            redmine_api_filters["assigned_to_id"] = assigned_to_id
        if priority_id is not None:
            redmine_api_filters["priority_id"] = priority_id
        if fixed_version_id is not None:
            redmine_api_filters["fixed_version_id"] = fixed_version_id
        if sort is not None:
            redmine_api_filters["sort"] = sort
        # Merge additional arbitrary Redmine filters if provided
        if filters:
            redmine_api_filters.update(filters)
        filters = redmine_api_filters

        # Log request for monitoring
        filter_keys = list(filters.keys()) if filters else []
        logging.info(
            f"Pagination request: limit={limit}, offset={offset}, filters={filter_keys}"
        )

        # Validate and sanitize parameters
        if limit is not None:
            if not isinstance(limit, int):
                try:
                    limit = int(limit)
                except (ValueError, TypeError):
                    logging.warning(
                        f"Invalid limit type {type(limit)}, using default 25"
                    )
                    limit = 25

            if limit <= 0:
                logging.debug(f"Limit {limit} <= 0, returning empty result")
                empty_result = []
                if include_pagination_info:
                    empty_result = {
                        "issues": [],
                        "pagination": {
                            "total": 0,
                            "limit": limit,
                            "offset": offset,
                            "count": 0,
                            "has_next": False,
                            "has_previous": False,
                            "next_offset": None,
                            "previous_offset": None,
                        },
                    }
                return empty_result

            # Cap at reasonable maximum
            original_limit = limit
            limit = min(limit, 1000)
            if original_limit > limit:
                logging.warning(
                    f"Limit {original_limit} exceeds maximum 1000, capped to {limit}"
                )

        # Validate offset
        if not isinstance(offset, int) or offset < 0:
            logging.warning(f"Invalid offset {offset}, reset to 0")
            offset = 0

        # Use python-redmine ResourceSet native pagination
        # Server-side filtering more efficient than client-side
        redmine_filters = {
            "offset": offset,
            "limit": min(limit or 25, 100),  # Redmine API max per request
            **filters,
        }

        # Get paginated issues from Redmine
        logging.debug(
            f"Calling _get_redmine_client().issue.filter with: {redmine_filters}"
        )
        issues = _get_redmine_client().issue.filter(**redmine_filters)

        # Convert ResourceSet to list (triggers server-side pagination)
        issues_list = list(issues)
        logging.debug(
            f"Retrieved {len(issues_list)} issues with offset={offset}, limit={limit}"
        )

        # Convert to dictionaries with optional field selection
        result_issues = [
            _issue_to_dict_selective(issue, fields) for issue in issues_list
        ]

        # Handle metadata response format
        if include_pagination_info:
            # Get total count from a separate query without offset/limit
            try:
                # Create clean query for total count (no pagination parameters)
                count_filters = {**filters}
                count_query = _get_redmine_client().issue.filter(**count_filters)
                # Must evaluate the query first to get accurate total_count
                list(count_query)  # Trigger evaluation
                total_count = count_query.total_count
                logging.debug(f"Got total count from separate query: {total_count}")
            except Exception as e:
                logging.warning(
                    f"Could not get total count: {e}, using estimated value"
                )
                # For unknown total, use a conservative estimate
                if len(result_issues) == limit:
                    # If we got a full page, there might be more
                    total_count = offset + len(result_issues) + 1
                else:
                    # If we got less than requested, this is likely the end
                    total_count = offset + len(result_issues)

            pagination_info = {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "count": len(result_issues),
                "has_next": len(result_issues) == limit,
                "has_previous": offset > 0,
                "next_offset": offset + limit if len(result_issues) == limit else None,
                "previous_offset": max(0, offset - limit) if offset > 0 else None,
            }

            result = {"issues": result_issues, "pagination": pagination_info}

            logging.info(
                f"Returning paginated response: {len(result_issues)} issues, "
                f"total={total_count}"
            )
            return result

        # Log success and return simple list
        logging.info(f"Successfully retrieved {len(result_issues)} issues")
        return result_issues

    except Exception as e:
        return [_handle_redmine_error(e, "listing issues")]


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
    """Search Redmine issues matching a query string with pagination support.

    Performs text search across issues using the Redmine Search API.
    Supports server-side pagination to prevent MCP token overflow.

    Args:
        query: Text to search for in issues.
        limit: Maximum number of issues to return (default: 25, max: 1000).
        offset: Number of issues to skip for pagination (default: 0).
        include_pagination_info: Return structured response with pagination
            metadata (default: False).
        fields: List of field names to include in results (default: all).
            Available: id, subject, description, project, status, priority,
            author, assigned_to, created_on, updated_on.
        scope: Search scope. Values: "all", "my_project", "subprojects".
        open_issues: Search only open issues (default: False).
        options: Additional Redmine Search API parameters as a dict.

    Returns:
        List[Dict] (default) or Dict with 'issues' and 'pagination' keys.
        Issues are limited to prevent token overflow (25,000 token MCP limit).

    Examples:
        >>> await search_redmine_issues("bug fix")
        [{"id": 1, "subject": "Bug in login", ...}, ...]

        >>> await search_redmine_issues(
        ...     "performance", limit=10, offset=0, include_pagination_info=True
        ... )
        {
            "issues": [...],
            "pagination": {"limit": 10, "offset": 0, "has_next": True, ...}
        }

        >>> await search_redmine_issues("urgent", fields=["id", "subject", "status"])
        [{"id": 1, "subject": "Critical bug", "status": {...}}, ...]

        >>> await search_redmine_issues("bug", scope="my_project", open_issues=True)
        [{"id": 1, "subject": "Open bug in my project", ...}, ...]

    Note:
        The Redmine Search API does not provide total_count. Pagination
        metadata uses conservative estimation: has_next=True if result
        count equals limit.

        Search API Limitations: The Search API supports text search with
        scope and open_issues filters only. For advanced filtering by
        project_id, status_id, priority_id, etc., use list_redmine_issues()
        instead, which uses the Issues API with full filter support.

    Performance:
        - Memory efficient: Uses server-side pagination
        - Token efficient: Default limit keeps response under 2000 tokens
        - Further reduce tokens: Use fields parameter for minimal data transfer
    """

    try:
        # Build search options dict from explicit parameters
        search_options: Dict[str, Any] = {}
        if scope is not None:
            search_options["scope"] = scope
        if open_issues:
            search_options["open_issues"] = open_issues
        # Merge additional arbitrary search options if provided
        if options:
            search_options.update(options)
        options = search_options

        # Log request for monitoring
        option_keys = list(options.keys()) if options else []
        logging.info(
            f"Search request: query='{query}', limit={limit}, "
            f"offset={offset}, options={option_keys}"
        )

        # Validate and sanitize limit parameter
        if limit is not None:
            if not isinstance(limit, int):
                try:
                    limit = int(limit)
                except (ValueError, TypeError):
                    logging.warning(
                        f"Invalid limit type {type(limit)}, using default 25"
                    )
                    limit = 25

            if limit <= 0:
                logging.debug(f"Limit {limit} <= 0, returning empty result")
                empty_result = []
                if include_pagination_info:
                    empty_result = {
                        "issues": [],
                        "pagination": {
                            "limit": limit,
                            "offset": offset,
                            "count": 0,
                            "has_next": False,
                            "has_previous": False,
                            "next_offset": None,
                            "previous_offset": None,
                        },
                    }
                return empty_result

            # Cap at reasonable maximum
            original_limit = limit
            limit = min(limit, 1000)
            if original_limit > limit:
                logging.warning(
                    f"Limit {original_limit} exceeds maximum 1000, "
                    f"capped to {limit}"
                )

        # Validate offset
        if not isinstance(offset, int) or offset < 0:
            logging.warning(f"Invalid offset {offset}, reset to 0")
            offset = 0

        # Pass offset and limit to Redmine Search API
        search_params = {"offset": offset, "limit": limit, **options}

        # Perform search with pagination
        logging.debug(
            f"Calling _get_redmine_client().issue.search with: {search_params}"
        )
        results = _get_redmine_client().issue.search(query, **search_params)

        if results is None:
            results = []

        # Convert results to list
        issues_list = list(results)
        logging.debug(
            f"Retrieved {len(issues_list)} issues with "
            f"offset={offset}, limit={limit}"
        )

        # Convert to dictionaries with optional field selection
        result_issues = [
            _issue_to_dict_selective(issue, fields) for issue in issues_list
        ]

        # Handle metadata response format
        if include_pagination_info:
            # Search API doesn't provide total_count
            # Use conservative estimation
            pagination_info = {
                "limit": limit,
                "offset": offset,
                "count": len(result_issues),
                "has_next": len(result_issues) == limit,
                "has_previous": offset > 0,
                "next_offset": (
                    offset + limit if len(result_issues) == limit else None
                ),
                "previous_offset": max(0, offset - limit) if offset > 0 else None,
            }

            result = {"issues": result_issues, "pagination": pagination_info}

            logging.info(
                f"Returning paginated search response: " f"{len(result_issues)} issues"
            )
            return result

        # Log success and return simple list
        logging.info(f"Successfully searched and retrieved {len(result_issues)} issues")
        return result_issues

    except Exception as e:
        return _handle_redmine_error(e, f"searching issues with query '{query}'")


@mcp.tool()
async def create_redmine_issue(
    project_id: int,
    subject: str,
    description: str = "",
    fields: Optional[Union[Dict[str, Any], str]] = None,
    extra_fields: Optional[Union[Dict[str, Any], str]] = None,
) -> Dict[str, Any]:
    """Create a new issue in Redmine.

    Compatibility notes:
    - Supports serialized ``fields`` payload (JSON object string)
    - Supports optional ``extra_fields`` payload as object/JSON string
    - Retries once with auto-filled required custom fields if Redmine reports
      relevant validation errors on required custom fields (e.g. blank/invalid)
      and
      ``REDMINE_AUTOFILL_REQUIRED_CUSTOM_FIELDS=true``.
    """

    if _is_read_only_mode():
        return dict(_READ_ONLY_ERROR)

    try:
        issue_fields = _issue_fields._parse_create_issue_fields(fields)
    except ValueError as e:
        return {"error": str(e)}

    try:
        parsed_extra_fields = _issue_fields._parse_optional_object_payload(
            extra_fields, "extra_fields"
        )
    except ValueError as e:
        return {"error": str(e)}

    if parsed_extra_fields:
        issue_fields.update(parsed_extra_fields)

    # Prevent callers from overriding explicit positional parameters.
    issue_fields.pop("project_id", None)
    issue_fields.pop("subject", None)
    issue_fields.pop("description", None)
    issue_fields.pop("extra_fields", None)

    try:
        issue = _get_redmine_client().issue.create(
            project_id=project_id,
            subject=subject,
            description=description,
            **issue_fields,
        )
        return _issue_to_dict(issue)
    except ValidationError as e:
        if not _issue_fields._is_required_custom_field_autofill_enabled():
            return _handle_redmine_error(e, f"creating issue in project {project_id}")

        missing_names = _issue_fields._extract_missing_required_field_names(str(e))
        if not missing_names:
            return _handle_redmine_error(e, f"creating issue in project {project_id}")

        try:
            retry_fields = _augment_fields_with_required_custom_fields(
                project_id=project_id,
                issue_fields=issue_fields,
                missing_field_names=missing_names,
            )

            # Retry only when we have actually augmented payload.
            if retry_fields == issue_fields:
                return _handle_redmine_error(
                    e, f"creating issue in project {project_id}"
                )

            logger.info(
                "Retrying issue creation with auto-filled custom fields: %s",
                missing_names,
            )
            issue = _get_redmine_client().issue.create(
                project_id=project_id,
                subject=subject,
                description=description,
                **retry_fields,
            )
            return _issue_to_dict(issue)
        except Exception as retry_error:
            return _handle_redmine_error(
                retry_error, f"creating issue in project {project_id}"
            )
    except Exception as e:
        return _handle_redmine_error(e, f"creating issue in project {project_id}")


@mcp.tool()
async def update_redmine_issue(issue_id: int, fields: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing Redmine issue.

    In addition to standard Redmine fields, a ``status_name`` key may be
    provided in ``fields``. When present and ``status_id`` is not supplied, the
    function will look up the corresponding status ID and use it for the update.

    Non-standard keys in ``fields`` are treated as candidate custom-field names.
    When a matching project custom field is found, it is translated into
    ``custom_fields`` entries for Redmine update payloads.
    """

    if _is_read_only_mode():
        return dict(_READ_ONLY_ERROR)

    update_fields = dict(fields)

    # Convert status name to id if requested
    if "status_name" in update_fields and "status_id" not in update_fields:
        name = str(update_fields.pop("status_name")).lower()
        try:
            statuses = _get_redmine_client().issue_status.all()
            for status in statuses:
                if getattr(status, "name", "").lower() == name:
                    update_fields["status_id"] = status.id
                    break
        except Exception as e:
            logger.warning(f"Error resolving status name '{name}': {e}")

    try:
        update_fields = _map_named_custom_fields_for_update(issue_id, update_fields)
        _get_redmine_client().issue.update(issue_id, **update_fields)
        updated_issue = _get_redmine_client().issue.get(issue_id)
        return _issue_to_dict(updated_issue, include_custom_fields=True)
    except ValidationError as e:
        if not _issue_fields._is_required_custom_field_autofill_enabled():
            return _handle_redmine_error(
                e,
                f"updating issue {issue_id}",
                {"resource_type": "issue", "resource_id": issue_id},
            )

        missing_names = _issue_fields._extract_missing_required_field_names(str(e))
        if not missing_names:
            return _handle_redmine_error(
                e,
                f"updating issue {issue_id}",
                {"resource_type": "issue", "resource_id": issue_id},
            )

        try:
            issue = _get_redmine_client().issue.get(issue_id)
            project = getattr(issue, "project", None)
            project_id = getattr(project, "id", None)
            if project_id is None:
                return _handle_redmine_error(
                    e,
                    f"updating issue {issue_id}",
                    {"resource_type": "issue", "resource_id": issue_id},
                )

            retry_fields = _augment_fields_with_required_custom_fields(
                project_id=project_id,
                issue_fields=update_fields,
                missing_field_names=missing_names,
            )

            # Retry only when we have actually augmented payload.
            if retry_fields == update_fields:
                return _handle_redmine_error(
                    e,
                    f"updating issue {issue_id}",
                    {"resource_type": "issue", "resource_id": issue_id},
                )

            logger.info(
                "Retrying issue update with auto-filled custom fields: %s",
                missing_names,
            )
            _get_redmine_client().issue.update(issue_id, **retry_fields)
            updated_issue = _get_redmine_client().issue.get(issue_id)
            return _issue_to_dict(updated_issue, include_custom_fields=True)
        except Exception as retry_error:
            return _handle_redmine_error(
                retry_error,
                f"updating issue {issue_id}",
                {"resource_type": "issue", "resource_id": issue_id},
            )
    except Exception as e:
        return _handle_redmine_error(
            e,
            f"updating issue {issue_id}",
            {"resource_type": "issue", "resource_id": issue_id},
        )


@mcp.tool()
async def get_redmine_attachment_download_url(
    attachment_id: int,
) -> Dict[str, Any]:
    """Get HTTP download URL for a Redmine attachment.

    Downloads the attachment to server storage and returns a time-limited
    HTTP URL that clients can use to download the file. Expiry time and
    storage location are controlled by server configuration.

    Args:
        attachment_id: The ID of the attachment to retrieve

    Returns:
        Dict containing download_url, filename, content_type, size,
        expires_at, and attachment_id

    Raises:
        ResourceNotFoundError: If attachment ID doesn't exist
        Exception: For other download or processing errors
    """

    # Ensure cleanup task is started (lazy initialization)
    await _ensure_cleanup_started()

    try:
        # Get attachment metadata from Redmine
        attachment = _get_redmine_client().attachment.get(attachment_id)

        # Server-controlled configuration (secure)
        attachments_dir = Path(os.getenv("ATTACHMENTS_DIR", "./attachments"))
        expires_minutes = float(os.getenv("ATTACHMENT_EXPIRES_MINUTES", "60"))

        # Create secure storage directory
        attachments_dir.mkdir(parents=True, exist_ok=True)

        # Generate secure UUID-based filename
        file_id = str(uuid.uuid4())

        # Download using existing approach - keeps original filename
        downloaded_path = attachment.download(savepath=str(attachments_dir))

        # Get file info
        original_filename = getattr(
            attachment, "filename", f"attachment_{attachment_id}"
        )

        # Create organized storage with UUID directory
        uuid_dir = attachments_dir / file_id
        uuid_dir.mkdir(exist_ok=True)

        # Move file to UUID-based location using atomic operations
        final_path = uuid_dir / original_filename
        temp_path = uuid_dir / f"{original_filename}.tmp"

        # Atomic file move with error handling
        try:
            os.rename(downloaded_path, temp_path)
            os.rename(temp_path, final_path)
        except (OSError, IOError) as e:
            # Cleanup on failure
            try:
                if temp_path.exists():
                    temp_path.unlink()
                if Path(downloaded_path).exists():
                    Path(downloaded_path).unlink()
            except OSError:
                pass  # Best effort cleanup
            return {"error": f"Failed to store attachment: {str(e)}"}

        # Calculate expiry time (timezone-aware)
        expires_hours = expires_minutes / 60.0
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

        # Store metadata atomically (following existing pattern)
        metadata = {
            "file_id": file_id,
            "attachment_id": attachment_id,
            "original_filename": original_filename,
            "file_path": str(final_path),
            "content_type": getattr(
                attachment, "content_type", "application/octet-stream"
            ),
            "size": final_path.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        metadata_file = uuid_dir / "metadata.json"
        temp_metadata = uuid_dir / "metadata.json.tmp"

        # Atomic metadata write with error handling
        try:
            with open(temp_metadata, "w") as f:
                json.dump(metadata, f, indent=2)
            os.rename(temp_metadata, metadata_file)
        except (OSError, IOError, ValueError) as e:
            # Cleanup on failure
            try:
                if temp_metadata.exists():
                    temp_metadata.unlink()
                if final_path.exists():
                    final_path.unlink()
            except OSError:
                pass  # Best effort cleanup
            return {"error": f"Failed to save metadata: {str(e)}"}

        # Generate server base URL from environment configuration
        # Use public configuration for external URLs
        public_host = os.getenv("PUBLIC_HOST", os.getenv("SERVER_HOST", "localhost"))
        public_port = os.getenv("PUBLIC_PORT", os.getenv("SERVER_PORT", "8000"))

        # Handle special case of 0.0.0.0 bind address
        if public_host == "0.0.0.0":
            public_host = "localhost"

        download_url = f"http://{public_host}:{public_port}/files/{file_id}"

        return {
            "download_url": download_url,
            "filename": original_filename,
            "content_type": metadata["content_type"],
            "size": metadata["size"],
            "expires_at": metadata["expires_at"],
            "attachment_id": attachment_id,
        }

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"downloading attachment {attachment_id}",
            {"resource_type": "attachment", "resource_id": attachment_id},
        )


@mcp.tool()
async def summarize_project_status(project_id: int, days: int = 30) -> Dict[str, Any]:
    """Provide a summary of project status based on issue activity over the
    specified time period.

    Args:
        project_id: The ID of the project to summarize
        days: Number of days to look back for analysis. Defaults to 30.

    Returns:
        A dictionary containing project status summary with issue counts,
        activity metrics, and trends. On error, returns a dictionary with
        an "error" key.
    """

    try:
        # Validate project exists
        try:
            project = _get_redmine_client().project.get(project_id)
        except ResourceNotFoundError:
            return {"error": f"Project {project_id} not found."}

        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        date_filter = f">={start_date.strftime('%Y-%m-%d')}"

        # Get issues created in the date range
        created_issues = list(
            _get_redmine_client().issue.filter(
                project_id=project_id, created_on=date_filter
            )
        )

        # Get issues updated in the date range
        updated_issues = list(
            _get_redmine_client().issue.filter(
                project_id=project_id, updated_on=date_filter
            )
        )

        # Analyze created issues
        created_stats = _analyze_issues(created_issues)

        # Analyze updated issues
        updated_stats = _analyze_issues(updated_issues)

        # Calculate trends
        total_created = len(created_issues)
        total_updated = len(updated_issues)

        # Get all project issues for context
        all_issues = list(_get_redmine_client().issue.filter(project_id=project_id))
        all_stats = _analyze_issues(all_issues)

        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "identifier": getattr(project, "identifier", ""),
            },
            "analysis_period": {
                "days": days,
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
            },
            "recent_activity": {
                "issues_created": total_created,
                "issues_updated": total_updated,
                "created_breakdown": created_stats,
                "updated_breakdown": updated_stats,
            },
            "project_totals": {
                "total_issues": len(all_issues),
                "overall_breakdown": all_stats,
            },
            "insights": {
                "daily_creation_rate": round(total_created / days, 2),
                "daily_update_rate": round(total_updated / days, 2),
                "recent_activity_percentage": round(
                    (total_updated / len(all_issues) * 100) if all_issues else 0, 2
                ),
            },
        }

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"summarizing project {project_id}",
            {"resource_type": "project", "resource_id": project_id},
        )


@mcp.tool()
async def search_entire_redmine(
    query: str,
    resources: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Search for issues and wiki pages across the Redmine instance.

    Args:
        query: Text to search for. Case sensitivity controlled by server DB config.
        resources: Filter by resource types. Allowed: ['issues', 'wiki_pages']
                   Default: None (searches both issues and wiki_pages)
        limit: Maximum number of results to return (max 100)
        offset: Pagination offset for server-side pagination

    Returns:
        Dictionary containing search results, counts, and metadata.
        On error, returns {"error": "message"}.

    Note:
        v1.4 Scope Limitation: Only 'issues' and 'wiki_pages' are supported.
        Requires Redmine 3.3.0 or higher for search API support.
    """

    try:
        await _ensure_cleanup_started()

        # Validate and enforce scope limitation (v1.4)
        allowed_types = ["issues", "wiki_pages"]
        if resources:
            resources = [r for r in resources if r in allowed_types]
            if not resources:
                resources = allowed_types  # Fall back to default if all filtered
        else:
            resources = allowed_types

        # Cap limit at 100 (Redmine API maximum)
        limit = min(limit, 100)
        if limit <= 0:
            limit = 100

        # Build search options
        search_options = {
            "resources": resources,
            "limit": limit,
            "offset": offset,
        }

        # Execute search
        categorized_results = _get_redmine_client().search(query, **search_options)

        # Handle empty results (python-redmine returns None)
        if not categorized_results:
            return {
                "results": [],
                "results_by_type": {},
                "total_count": 0,
                "query": query,
            }

        # Process categorized results
        all_results = []
        results_by_type: Dict[str, int] = {}

        for resource_type, resource_set in categorized_results.items():
            # Skip 'unknown' category (plugin resources)
            if resource_type == "unknown":
                continue

            # Skip if not in allowed types
            if resource_type not in allowed_types:
                continue

            # Handle both ResourceSet and dict (for 'unknown')
            if hasattr(resource_set, "__iter__"):
                count = 0
                for resource in resource_set:
                    result_dict = _resource_to_dict(resource, resource_type)
                    all_results.append(result_dict)
                    count += 1
                if count > 0:
                    results_by_type[resource_type] = count

        return {
            "results": all_results,
            "results_by_type": results_by_type,
            "total_count": len(all_results),
            "query": query,
        }

    except VersionMismatchError:
        return {"error": "Search requires Redmine 3.3.0 or higher."}
    except Exception as e:
        return _handle_redmine_error(e, f"searching Redmine for '{query}'")


@mcp.tool()
async def get_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
    version: Optional[int] = None,
    include_attachments: bool = True,
) -> Dict[str, Any]:
    """
    Retrieve full wiki page content from Redmine.

    Args:
        project_id: Project identifier (ID number or string identifier)
        wiki_page_title: Wiki page title (e.g., "Installation_Guide")
        version: Specific version number (None = latest version)
        include_attachments: Include attachment metadata in response

    Returns:
        Dictionary containing full wiki page content and metadata

    Note:
        Use get_redmine_attachment_download_url() to download attachments.
    """

    try:
        await _ensure_cleanup_started()

        # Retrieve wiki page
        if version:
            wiki_page = _get_redmine_client().wiki_page.get(
                wiki_page_title, project_id=project_id, version=version
            )
        else:
            wiki_page = _get_redmine_client().wiki_page.get(
                wiki_page_title, project_id=project_id
            )

        return _wiki_page_to_dict(wiki_page, include_attachments)

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"fetching wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


@mcp.tool()
async def create_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
    text: str,
    comments: str = "",
) -> Dict[str, Any]:
    """
    Create a new wiki page in a Redmine project.

    Args:
        project_id: Project identifier (ID number or string identifier)
        wiki_page_title: Wiki page title (e.g., "Installation_Guide")
        text: Wiki page content (Textile or Markdown depending on Redmine config)
        comments: Optional comment for the change log

    Returns:
        Dictionary containing created wiki page metadata, or error dict on failure
    """

    if _is_read_only_mode():
        return dict(_READ_ONLY_ERROR)

    try:
        await _ensure_cleanup_started()

        # Create wiki page
        wiki_page = _get_redmine_client().wiki_page.create(
            project_id=project_id,
            title=wiki_page_title,
            text=text,
            comments=comments if comments else None,
        )

        return _wiki_page_to_dict(wiki_page)

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"creating wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


@mcp.tool()
async def update_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
    text: str,
    comments: str = "",
) -> Dict[str, Any]:
    """
    Update an existing wiki page in a Redmine project.

    Args:
        project_id: Project identifier (ID number or string identifier)
        wiki_page_title: Wiki page title (e.g., "Installation_Guide")
        text: New wiki page content
        comments: Optional comment for the change log

    Returns:
        Dictionary containing updated wiki page metadata, or error dict on failure
    """

    if _is_read_only_mode():
        return dict(_READ_ONLY_ERROR)

    try:
        await _ensure_cleanup_started()

        # Update wiki page
        _get_redmine_client().wiki_page.update(
            wiki_page_title,
            project_id=project_id,
            text=text,
            comments=comments if comments else None,
        )

        # Fetch updated page to return current state
        wiki_page = _get_redmine_client().wiki_page.get(
            wiki_page_title, project_id=project_id
        )

        return _wiki_page_to_dict(wiki_page)

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"updating wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


@mcp.tool()
async def delete_redmine_wiki_page(
    project_id: Union[str, int],
    wiki_page_title: str,
) -> Dict[str, Any]:
    """
    Delete a wiki page from a Redmine project.

    Args:
        project_id: Project identifier (ID number or string identifier)
        wiki_page_title: Wiki page title to delete

    Returns:
        Dictionary with success status, or error dict on failure
    """

    if _is_read_only_mode():
        return dict(_READ_ONLY_ERROR)

    try:
        await _ensure_cleanup_started()

        # Delete wiki page
        _get_redmine_client().wiki_page.delete(wiki_page_title, project_id=project_id)

        return {
            "success": True,
            "title": wiki_page_title,
            "message": f"Wiki page '{wiki_page_title}' deleted successfully.",
        }

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"deleting wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


@mcp.tool()
async def list_project_members(
    project_id: Union[str, int],
) -> List[Dict[str, Any]]:
    """List members of a Redmine project.

    Returns all users and groups that are members of the specified project,
    along with their assigned roles.

    Args:
        project_id: Project identifier (ID number or string identifier)

    Returns:
        A list of membership dictionaries containing user/group info and roles.
        On failure, a list containing a single dictionary with an "error" key.

    Examples:
        >>> await list_project_members("my-project")
        [
            {
                "id": 1,
                "user": {"id": 5, "name": "John Doe"},
                "group": null,
                "project": {"id": 1, "name": "My Project"},
                "roles": [{"id": 3, "name": "Developer"}]
            },
            ...
        ]
    """
    try:
        memberships = _get_redmine_client().project_membership.filter(
            project_id=project_id
        )
        return [_membership_to_dict(m) for m in memberships]
    except Exception as e:
        return [
            _handle_redmine_error(
                e,
                f"listing members for project {project_id}",
                {"resource_type": "project", "resource_id": project_id},
            )
        ]


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
    """List time entries from Redmine with filtering and pagination.

    Retrieve time entries with optional filtering by project, issue, user,
    and date range. Supports pagination for handling large result sets.

    Args:
        project_id: Filter by project (ID number or string identifier).
        issue_id: Filter by issue ID.
        user_id: Filter by user ID. Use "me" for current user.
        from_date: Start date filter (YYYY-MM-DD format).
        to_date: End date filter (YYYY-MM-DD format).
        limit: Maximum number of entries to return (default: 25, max: 100).
        offset: Number of entries to skip for pagination (default: 0).

    Returns:
        A list of time entry dictionaries. On failure, a list containing
        a single dictionary with an "error" key.

    Examples:
        >>> await list_time_entries(project_id="my-project")
        [{"id": 1, "hours": 2.5, "comments": "Bug fix", ...}, ...]

        >>> await list_time_entries(issue_id=123, from_date="2024-01-01")
        [{"id": 2, "hours": 1.0, "issue": {"id": 123}, ...}, ...]

        >>> await list_time_entries(user_id="me", limit=10)
        [{"id": 3, "hours": 4.0, "user": {"id": 5, "name": "Current User"}, ...}]
    """
    try:
        # Build filter parameters
        filters: Dict[str, Any] = {
            "limit": min(limit, 100),
            "offset": offset,
        }

        if project_id is not None:
            filters["project_id"] = project_id
        if issue_id is not None:
            filters["issue_id"] = issue_id
        if user_id is not None:
            filters["user_id"] = user_id
        if from_date is not None:
            filters["from_date"] = from_date
        if to_date is not None:
            filters["to_date"] = to_date

        time_entries = _get_redmine_client().time_entry.filter(**filters)
        return [_time_entry_to_dict(te) for te in time_entries]

    except Exception as e:
        return [_handle_redmine_error(e, "listing time entries")]


@mcp.tool()
async def create_time_entry(
    hours: float,
    project_id: Optional[Union[str, int]] = None,
    issue_id: Optional[int] = None,
    activity_id: Optional[int] = None,
    comments: str = "",
    spent_on: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new time entry in Redmine.

    Log time against a project or issue. Either project_id or issue_id
    must be provided. If issue_id is provided, the time entry will be
    associated with that issue's project.

    Args:
        hours: Number of hours spent (required). Can be decimal (e.g., 1.5).
        project_id: Project to log time against (ID or identifier).
            Required if issue_id is not provided.
        issue_id: Issue to log time against. If provided, project_id is optional.
        activity_id: Time entry activity ID (e.g., Development, Design).
            If not provided, Redmine uses the default activity.
        comments: Description of work performed.
        spent_on: Date when time was spent (YYYY-MM-DD). Defaults to today.

    Returns:
        Dictionary containing the created time entry, or error dict on failure.

    Examples:
        >>> await create_time_entry(hours=2.5, issue_id=123, comments="Bug fix")
        {"id": 1, "hours": 2.5, "issue": {"id": 123}, ...}

        >>> await create_time_entry(
        ...     hours=1.0,
        ...     project_id="my-project",
        ...     activity_id=9,
        ...     comments="Code review",
        ...     spent_on="2024-03-15"
        ... )
        {"id": 2, "hours": 1.0, "project": {"id": 1, "name": "My Project"}, ...}
    """
    if project_id is None and issue_id is None:
        return {"error": "Either project_id or issue_id must be provided."}

    if hours <= 0:
        return {"error": "Hours must be a positive number."}

    try:
        # Build create parameters
        params: Dict[str, Any] = {
            "hours": hours,
        }

        if project_id is not None:
            params["project_id"] = project_id
        if issue_id is not None:
            params["issue_id"] = issue_id
        if activity_id is not None:
            params["activity_id"] = activity_id
        if comments:
            params["comments"] = comments
        if spent_on is not None:
            params["spent_on"] = spent_on

        time_entry = _get_redmine_client().time_entry.create(**params)
        return _time_entry_to_dict(time_entry)

    except Exception as e:
        context = {}
        if issue_id:
            context = {"resource_type": "issue", "resource_id": issue_id}
        elif project_id:
            context = {"resource_type": "project", "resource_id": project_id}
        return _handle_redmine_error(e, "creating time entry", context)


@mcp.tool()
async def update_time_entry(
    time_entry_id: int,
    hours: Optional[float] = None,
    activity_id: Optional[int] = None,
    comments: Optional[str] = None,
    spent_on: Optional[str] = None,
) -> Dict[str, Any]:
    """Update an existing time entry in Redmine.

    Modify hours, activity, comments, or date of an existing time entry.
    Only provided fields will be updated.

    Args:
        time_entry_id: ID of the time entry to update (required).
        hours: New hours value. Must be positive if provided.
        activity_id: New activity ID.
        comments: New comments/description.
        spent_on: New date (YYYY-MM-DD format).

    Returns:
        Dictionary containing the updated time entry, or error dict on failure.

    Examples:
        >>> await update_time_entry(time_entry_id=1, hours=3.0)
        {"id": 1, "hours": 3.0, ...}

        >>> await update_time_entry(
        ...     time_entry_id=1,
        ...     comments="Updated description",
        ...     spent_on="2024-03-16"
        ... )
        {"id": 1, "comments": "Updated description", ...}
    """
    if hours is not None and hours <= 0:
        return {"error": "Hours must be a positive number."}

    try:
        # Build update parameters
        params: Dict[str, Any] = {}

        if hours is not None:
            params["hours"] = hours
        if activity_id is not None:
            params["activity_id"] = activity_id
        if comments is not None:
            params["comments"] = comments
        if spent_on is not None:
            params["spent_on"] = spent_on

        if not params:
            return {"error": "No fields provided for update."}

        client = _get_redmine_client()
        client.time_entry.update(time_entry_id, **params)

        # Fetch and return updated entry
        updated_entry = client.time_entry.get(time_entry_id)
        return _time_entry_to_dict(updated_entry)

    except Exception as e:
        return _handle_redmine_error(
            e,
            f"updating time entry {time_entry_id}",
            {"resource_type": "time entry", "resource_id": time_entry_id},
        )


@mcp.tool()
async def list_time_entry_activities() -> List[Dict[str, Any]]:
    """List available time entry activities from Redmine.

    Returns all activity types that can be used when creating or updating
    time entries (e.g., Development, Design, Testing).

    Returns:
        A list of activity dictionaries. On failure, a list containing
        a single dictionary with an "error" key.

    Examples:
        >>> await list_time_entry_activities()
        [{"id": 4, "name": "Development", "active": True, "is_default": False}, ...]
    """
    try:
        activities = _get_redmine_client().enumeration.filter(
            resource="time_entry_activities"
        )
        return [
            {
                "id": getattr(a, "id", None),
                "name": getattr(a, "name", None),
                "active": getattr(a, "active", None),
                "is_default": getattr(a, "is_default", None),
            }
            for a in activities
        ]

    except Exception as e:
        return [_handle_redmine_error(e, "listing time entry activities")]


@mcp.tool()
async def cleanup_attachment_files() -> Dict[str, Any]:
    """Clean up expired attachment files and return storage statistics.

    Returns:
        A dictionary containing cleanup statistics and current storage usage.
        On error, a dictionary with "error" is returned.
    """
    try:
        attachments_dir = os.getenv("ATTACHMENTS_DIR", "./attachments")
        manager = AttachmentFileManager(attachments_dir)
        cleanup_stats = manager.cleanup_expired_files()
        storage_stats = manager.get_storage_stats()

        return {"cleanup": cleanup_stats, "current_storage": storage_stats}
    except Exception as e:
        logger.error(f"Error during attachment cleanup: {e}")
        return {"error": f"An error occurred during cleanup: {str(e)}"}


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
