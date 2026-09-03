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
import re
import time
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional, Set, Union

from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file as early as possible
# so that modules like .security (imported later) see the correct values.
_env_paths = [
    Path.cwd() / ".env",  # User's current working directory (highest priority)
    Path(__file__).parent.parent.parent / ".env",  # Package directory (fallback)
]

_env_loaded = False
for _env_path in _env_paths:
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path))
        _env_loaded = True
        break

if not _env_loaded:
    load_dotenv()

from redminelib import Redmine  # noqa: E402
from redminelib.exceptions import (  # noqa: E402
    ResourceNotFoundError,
    VersionMismatchError,
    ValidationError,
)
from fastmcp import FastMCP  # noqa: E402

# Configure logging early (but after env loading)
logger = logging.getLogger(__name__)
if _env_loaded:
    logger.info("Loaded .env for Redmine MCP Server")

from .handler_impl import issue_fields as _issue_fields  # noqa: E402
from .handler_impl.errors import handle_redmine_error  # noqa: E402
from .security import (  # noqa: E402
    validate_redmine_url,
    SecurityValidationError,
    ssrf_redirect_hook,
    SSRFSafeHTTPAdapter,
)
from .handler_impl.tools import (  # noqa: E402
    append_google_sheet_impl,
    create_redmine_issue_with_subtasks_impl,
    create_redmine_issue_impl,
    create_redmine_issue_relation_impl,
    create_redmine_wiki_page_impl,
    create_redmine_issues_from_bugs_impl,
    create_test_cases_on_sheet_impl,
    create_time_entry_impl,
    delete_redmine_wiki_page_impl,
    delete_redmine_issue_relation_impl,
    delete_time_entry_impl,
    get_project_issue_context_impl,
    get_redmine_issue_impl,
    get_redmine_issue_allowed_statuses_impl,
    get_redmine_wiki_page_impl,
    get_sheet_metadata_impl,
    list_redmine_issue_statuses_impl,
    list_redmine_issues_impl,
    list_redmine_projects_impl,
    list_time_entries_impl,
    list_time_entry_activities_impl,
    read_google_sheet_impl,
    reopen_bug_impl,
    search_entire_redmine_impl,
    search_redmine_issues_impl,
    set_sheet_data_validation_impl,
    create_test_sheet_structure_impl,
    sync_redmine_status_to_sheet_impl,
    update_redmine_issue_impl,
    update_redmine_wiki_page_impl,
    update_time_entry_impl,
    write_google_sheet_impl,
)
from .handler_impl.http_routes import (  # noqa: E402
    health_payload,
)
from .serializers import (  # noqa: E402
    wrap_insecure_content,
    _issue_to_dict,
    _resource_to_dict,
    _issue_to_dict_selective,
    _journals_to_list,
    _attachments_to_list,
    _version_to_dict,
    _membership_to_dict,
    _time_entry_to_dict,
    _wiki_page_to_dict,
)
from . import memory_store  # noqa: E402
from .handler_impl.tools.memory import (  # noqa: E402
    get_user_memory_impl,
    set_user_memory_impl,
    delete_user_memory_impl,
    list_user_memory_impl,
)
from .google_sheets_client import google_sheets_manager  # noqa: E402
from .serializers.google_sheets import (  # noqa: E402
    map_priority_to_redmine as _map_priority_to_redmine,
    map_redmine_status_to_sheet as _map_redmine_status_to_sheet,
    parse_reject_reason as _parse_reject_reason,
    is_duplicate_rejection as _is_duplicate_rejection,
    parse_duplicate_issue_id as _parse_duplicate_issue_id,
)
from .resources import (  # noqa: E402
    ISSUE_TEMPLATE_RESOURCE_URI,
    TIME_ENTRY_CONTRACT_RESOURCE_URI,
    build_issue_contract_payload,
    build_issue_template_payload,
    build_time_entry_contract_payload,
    is_issue_template_enforced,
    required_issue_template_sections,
    validate_issue_description_template,
)

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

# Validation of required environment variables based on authentication mode
if REDMINE_AUTH_MODE == "dynamic":
    # In dynamic mode, URL and Key are provided per-request via headers.
    # No global URL/Key are required at startup.
    pass
elif not REDMINE_URL:
    logger.warning(
        "REDMINE_URL not set. "
        "Please create a .env file in your working directory with REDMINE_URL defined."
    )
elif REDMINE_AUTH_MODE == "legacy":
    try:
        validate_redmine_url(REDMINE_URL)
    except SecurityValidationError as e:
        logger.warning(
            f"Global REDMINE_URL fails security validation: {e}. "
            "If this is intentional (e.g. local dev), "
            "set REDMINE_SECURITY_STRICT=false."
        )

if (
    REDMINE_AUTH_MODE != "oauth"
    and REDMINE_AUTH_MODE != "dynamic"
    and not (REDMINE_API_KEY or (REDMINE_USERNAME and REDMINE_PASSWORD))
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
    # NOTE: hooks and adapters are intentionally NOT added here.
    # python-redmine ignores unknown keys in the requests= dict.
    # SSRF protection is applied separately via _apply_ssrf_protection()
    # which patches the actual requests.Session after client construction.
    return requests_config


def _apply_ssrf_protection(client: Redmine) -> Redmine:
    """Mount SSRF-safe adapter and redirect hook on a Redmine client's session.

    python-redmine does not forward 'adapters' or 'hooks' from the requests=
    config dict to its internal requests.Session, so we must patch the session
    directly after the client is constructed.

    This function:
    - Mounts SSRFSafeHTTPAdapter for both http:// and https://, which resolves
      DNS once, validates the IP, and pins the connection (TOCTOU defence).
    - Appends ssrf_redirect_hook to the session's response hooks so that any
      HTTP redirect target is validated before requests follows it.
    """
    session = client.engine.session
    adapter = SSRFSafeHTTPAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.hooks["response"].append(ssrf_redirect_hook)
    return client


# Test-compatibility hook: existing unit tests patch this module-level variable
# directly (e.g. @patch("redmine_mcp_server.redmine_handler.redmine", mock)).
# When non-None, _get_redmine_client() returns it immediately.
# In production this stays None so per-request Dynamic/OAuth auth is always used.
redmine = None

# Cached legacy-mode client — avoids recreating Redmine() on every tool call
# when running without OAuth.
_legacy_client = None


def _build_legacy_client(strict: bool = True) -> Optional[Redmine]:
    """Build a Redmine client using legacy credentials (API key or user/pass).

    Returns None (instead of raising) when strict=False and no credentials
    are configured. Callers must never cache a None return value.
    """
    requests_config = _build_requests_config()
    if REDMINE_API_KEY:
        return _apply_ssrf_protection(
            Redmine(REDMINE_URL, key=REDMINE_API_KEY, requests=requests_config)
        )
    elif REDMINE_USERNAME and REDMINE_PASSWORD:
        return _apply_ssrf_protection(
            Redmine(
                REDMINE_URL,
                username=REDMINE_USERNAME,
                password=REDMINE_PASSWORD,
                requests=requests_config,
            )
        )
    else:
        if strict:
            raise RuntimeError(
                "No Redmine authentication available. "
                "Set REDMINE_AUTH_MODE=oauth or configure REDMINE_API_KEY / "
                "REDMINE_USERNAME+REDMINE_PASSWORD."
            )
        return None


def _get_redmine_client(strict: bool = True) -> Optional[Redmine]:
    global _legacy_client

    if redmine is not None:
        return redmine

    # 1. Check for Dynamic Proxy mode (per-request URL and API Key)
    from .dynamic_auth_middleware import get_dynamic_config

    dyn_url, dyn_key = get_dynamic_config()
    if dyn_url and dyn_key:
        # Dynamic mode: never uses cached client, always per-request
        requests_config = _build_requests_config()
        client = Redmine(dyn_url, key=dyn_key, requests=requests_config)
        return _apply_ssrf_protection(client)

    # 2. Check for OAuth mode (per-request Bearer token)
    from .oauth_middleware import current_redmine_token

    token = current_redmine_token.get()

    if token:
        # OAuth mode: per-request client with Bearer token (cannot be cached)
        requests_config = _build_requests_config()
        headers = {"Authorization": f"Bearer {token}"}
        client = Redmine(REDMINE_URL, requests={"headers": headers, **requests_config})
        return _apply_ssrf_protection(client)

    # 3. Legacy mode: reuse a cached singleton configured via .env.
    # Never cache None — if no credentials are available, return None without
    # storing it so that a future call with credentials will still build a client.
    if _legacy_client is None:
        client = _build_legacy_client(strict=strict)
        if client is None:
            return None
        _legacy_client = client
    return _legacy_client


# Initialize FastMCP server
mcp = FastMCP("redmine_mcp_tools")


_STATUS_ID_CACHE: Dict[str, tuple[Optional[int], float]] = {}
_PRIORITY_ID_CACHE: Dict[str, tuple[Optional[int], float]] = {}
_TRACKER_NAME_CACHE: Dict[tuple[str, int], tuple[Optional[str], float]] = {}
_METADATA_CACHE_TTL_SECONDS = 300.0
_CACHE_MISS = object()


async def _no_op_cleanup() -> None:
    """No-op cleanup hook kept for tool API stability."""


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for container orchestration and monitoring."""
    from starlette.responses import JSONResponse

    return JSONResponse(health_payload(REDMINE_AUTH_MODE))


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
_INSECURE_CONTENT_TAG_RE = re.compile(
    r"^<insecure-content-[^>]+>\s*(.*?)\s*</insecure-content-[^>]+>$",
    flags=re.DOTALL,
)


def _is_true_env(var_name: str, default: str = "false") -> bool:
    """Parse common truthy env-var values."""
    return os.getenv(var_name, default).strip().lower() in {"1", "true", "yes", "on"}


def _conditional_tool(enabled: bool = True):
    """Return ``@mcp.tool()`` decorator when *enabled* is True, otherwise a no-op."""
    if enabled:
        return mcp.tool()

    def _noop(fn: Any) -> Any:
        return fn

    return _noop


_WIKI_TOOLS_ENABLED = not _is_true_env("REDMINE_MCP_DISABLE_WIKI_TOOLS", "false")


def _normalize_insecure_text(value: Any) -> str:
    """Normalize possibly wrapped insecure-content text for safe comparisons."""
    text = str(value or "").strip()
    match = _INSECURE_CONTENT_TAG_RE.fullmatch(text)
    if match:
        return match.group(1).strip().lower()
    return text.lower()


def _is_valid_date_yyyy_mm_dd(value: Any) -> bool:
    """Return whether value is a valid YYYY-MM-DD date string."""
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _is_non_empty_value(value: Any) -> bool:
    """Return whether a create field value should be considered present."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _cache_get(
    cache: Dict[Any, tuple[Any, float]],
    key: Any,
    ttl_seconds: float = _METADATA_CACHE_TTL_SECONDS,
) -> Any:
    """Get cache value if present and not expired."""
    cached = cache.get(key)
    if cached is None:
        return _CACHE_MISS
    value, stored_at = cached
    if (time.monotonic() - stored_at) > ttl_seconds:
        cache.pop(key, None)
        return _CACHE_MISS
    return value


def _cache_set(cache: Dict[Any, tuple[Any, float]], key: Any, value: Any) -> None:
    """Store cache value with monotonic timestamp."""
    cache[key] = (value, time.monotonic())


async def _resolve_status_id_by_name(status_name: str) -> Optional[int]:
    """Resolve issue status id by display name (case-insensitive)."""
    cache_key = status_name.strip().lower()
    cached = _cache_get(_STATUS_ID_CACHE, cache_key)
    if cached is not _CACHE_MISS:
        return cached

    client = _get_redmine_client(strict=False)
    if client is None:
        _cache_set(_STATUS_ID_CACHE, cache_key, None)
        return None
    try:
        statuses = await asyncio.to_thread(client.issue_status.all)
    except Exception:
        _cache_set(_STATUS_ID_CACHE, cache_key, None)
        return None
    try:
        iterator = iter(statuses)
    except TypeError:
        _cache_set(_STATUS_ID_CACHE, cache_key, None)
        return None
    expected = status_name.strip().lower()
    for status in iterator:
        if str(getattr(status, "name", "")).strip().lower() == expected:
            resolved = getattr(status, "id", None)
            _cache_set(_STATUS_ID_CACHE, cache_key, resolved)
            return resolved
    _cache_set(_STATUS_ID_CACHE, cache_key, None)
    return None


async def _resolve_priority_id_by_name(priority_name: str) -> Optional[int]:
    """Resolve issue priority id by display name (case-insensitive)."""
    cache_key = priority_name.strip().lower()
    cached = _cache_get(_PRIORITY_ID_CACHE, cache_key)
    if cached is not _CACHE_MISS:
        return cached

    client = _get_redmine_client(strict=False)
    if client is None:
        _cache_set(_PRIORITY_ID_CACHE, cache_key, None)
        return None
    try:
        priorities = await asyncio.to_thread(
            lambda: list(client.enumeration.filter(resource="issue_priorities"))
        )
    except Exception:
        _cache_set(_PRIORITY_ID_CACHE, cache_key, None)
        return None
    try:
        iterator = iter(priorities)
    except TypeError:
        _cache_set(_PRIORITY_ID_CACHE, cache_key, None)
        return None
    expected = priority_name.strip().lower()
    for priority in iterator:
        if str(getattr(priority, "name", "")).strip().lower() == expected:
            resolved = getattr(priority, "id", None)
            _cache_set(_PRIORITY_ID_CACHE, cache_key, resolved)
            return resolved
    _cache_set(_PRIORITY_ID_CACHE, cache_key, None)
    return None


async def _prepare_create_issue_fields(
    project_id: int,
    subject: str,
    issue_fields: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Apply create-issue policy: defaults + optional strict validation."""
    issue_fields.setdefault("done_ratio", 0)

    if "status_id" not in issue_fields:
        status_id = await _resolve_status_id_by_name("New")
        if status_id is not None:
            issue_fields["status_id"] = status_id

    if "priority_id" not in issue_fields:
        priority_id = await _resolve_priority_id_by_name("Normal")
        if priority_id is not None:
            issue_fields["priority_id"] = priority_id

    strict_mode = _is_true_env("REDMINE_STRICT_ISSUE_CREATION_INPUTS", "false")
    if not strict_mode:
        return None

    if not re.match(r"^\[[^\[\]\r\n]+\]\s+.+$", str(subject or "").strip()):
        return {
            "error": (
                "Issue subject must follow format '[module name] task name'. "
                "Example: '[auth] implement refresh token flow'."
            )
        }

    required_user_fields = [
        "estimated_hours",
        "start_date",
        "due_date",
        "tracker_id",
        "assigned_to_id",
        "category_id",
        "fixed_version_id",
    ]
    missing_fields = [
        field
        for field in required_user_fields
        if not _is_non_empty_value(issue_fields.get(field))
    ]
    if missing_fields:
        return {
            "error": (
                "Missing required planning fields for issue creation. "
                "Please ask user to provide these fields explicitly."
            ),
            "missing_fields": missing_fields,
            "defaults_applied": {
                "status": "New",
                "priority": "Normal",
                "done_ratio": 0,
            },
            "project_id": project_id,
        }

    if not _is_valid_date_yyyy_mm_dd(issue_fields.get("start_date")):
        return {"error": "start_date must be in YYYY-MM-DD format."}
    if not _is_valid_date_yyyy_mm_dd(issue_fields.get("due_date")):
        return {"error": "due_date must be in YYYY-MM-DD format."}

    start_date = date.fromisoformat(str(issue_fields.get("start_date")))
    due_date = date.fromisoformat(str(issue_fields.get("due_date")))
    if due_date < start_date:
        return {"error": "due_date must be greater than or equal to start_date."}

    try:
        estimated_hours = float(issue_fields.get("estimated_hours"))
    except (TypeError, ValueError):
        return {"error": "estimated_hours must be a positive number."}
    if estimated_hours <= 0:
        return {"error": "estimated_hours must be a positive number."}

    return None


def _is_read_only_mode() -> bool:
    """Check if the server is in read-only mode."""
    return _is_true_env("REDMINE_MCP_READ_ONLY", "false")


_READ_ONLY_ERROR = {
    "error": (
        "This server is in read-only mode (REDMINE_MCP_READ_ONLY=true). "
        "Write operations are disabled."
    )
}


@mcp.resource(ISSUE_TEMPLATE_RESOURCE_URI)
def issue_creation_template_resource() -> Dict[str, Any]:
    """Template guidance used by agents when creating Redmine issues."""
    return build_issue_template_payload()


@mcp.resource("redmine://issue-contract/{project_id}")
async def issue_contract_resource(project_id: Union[str, int]) -> Dict[str, Any]:
    """Issue create/update contract for a given project."""
    return await build_issue_contract_payload(
        project_id=project_id,
        tracker_id=None,
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
        standard_issue_update_fields=_STANDARD_ISSUE_UPDATE_FIELDS,
        template_resource_uri=ISSUE_TEMPLATE_RESOURCE_URI,
        template_required_sections=required_issue_template_sections(),
        template_enforced=is_issue_template_enforced(),
    )


@mcp.resource("redmine://issue-contract/{project_id}/{tracker_id}")
async def issue_tracker_contract_resource(
    project_id: Union[str, int], tracker_id: Union[str, int]
) -> Dict[str, Any]:
    """Issue create/update contract for a specific project tracker."""
    return await build_issue_contract_payload(
        project_id=project_id,
        tracker_id=tracker_id,
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
        standard_issue_update_fields=_STANDARD_ISSUE_UPDATE_FIELDS,
        template_resource_uri=ISSUE_TEMPLATE_RESOURCE_URI,
        template_required_sections=required_issue_template_sections(),
        template_enforced=is_issue_template_enforced(),
    )


@mcp.resource(TIME_ENTRY_CONTRACT_RESOURCE_URI)
async def time_entry_contract_resource() -> Dict[str, Any]:
    """Time-entry create/update/list contract for agents."""
    return await build_time_entry_contract_payload(
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


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


async def _resolve_project_tracker_name(
    project_id: Union[int, str], tracker_id: Union[int, str, Any]
) -> Optional[str]:
    """Resolve tracker name for a project-scoped tracker id."""
    try:
        parsed_tracker_id = int(tracker_id)
    except (TypeError, ValueError):
        return None

    project_key = str(project_id)
    cache_key = (project_key, parsed_tracker_id)
    cached = _cache_get(_TRACKER_NAME_CACHE, cache_key)
    if cached is not _CACHE_MISS:
        return cached

    client = _get_redmine_client()
    if client is None:
        return None

    try:
        project = await asyncio.to_thread(
            client.project.get, project_id, include="trackers"
        )
        for tracker in getattr(project, "trackers", None) or []:
            if getattr(tracker, "id", None) == parsed_tracker_id:
                name = getattr(tracker, "name", None)
                if name:
                    resolved = str(name)
                    _cache_set(_TRACKER_NAME_CACHE, cache_key, resolved)
                    return resolved
    except Exception:
        return None
    _cache_set(_TRACKER_NAME_CACHE, cache_key, None)
    return None


@mcp.tool()
async def get_redmine_issue(
    issue_id: Annotated[int, Field(description="ID of the Redmine issue to retrieve.")],
    include_journals: Annotated[
        bool,
        Field(
            description="Include the issue's comment/journal history. Defaults to True."
        ),
    ] = True,
    include_attachments: Annotated[
        bool,
        Field(
            description="Include attached files and their metadata. Defaults to True."
        ),
    ] = True,
    include_custom_fields: Annotated[
        bool,
        Field(description="Include custom field values. Defaults to True."),
    ] = True,
    journal_limit: Annotated[
        Optional[int],
        Field(
            description=(
                "Maximum number of journal entries to return (most recent). Omit for"
                " all."
            )
        ),
    ] = None,
    journal_offset: Annotated[
        int,
        Field(description="Skip this many journal entries (for journal pagination)."),
    ] = 0,
    include_watchers: Annotated[
        bool,
        Field(description="Include watcher users of the issue."),
    ] = False,
    include_relations: Annotated[
        bool,
        Field(description="Include issue relations (related/linked issues)."),
    ] = False,
    include_children: Annotated[
        bool,
        Field(description="Include subtasks of the issue."),
    ] = False,
) -> Dict[str, Any]:
    """Retrieve a single Redmine issue by ID with optional detail sections.

    Use when you need the full picture of one task: description, project,
    tracker, status, assignee, priority, dates, custom fields, files and
    journals. Returns a dict including a parent key (the parent task, or
    null for standalone issues).
    """
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
        ensure_cleanup_started=_no_op_cleanup,
        get_client=_get_redmine_client,
        issue_to_dict=_issue_to_dict,
        journals_to_list=_journals_to_list,
        attachments_to_list=_attachments_to_list,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_redmine_projects() -> List[Dict[str, Any]]:
    """List all projects the current credential can access.

    Call this first to discover available project IDs/identifiers before
    creating issues or fetching project context.
    """
    return await list_redmine_projects_impl(
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def get_project_issue_context(
    project_id: Annotated[
        Union[str, int],
        Field(
            description="ID or identifier of the Redmine project to fetch context for."
        ),
    ],
    tracker_id: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Restrict custom fields to this tracker only. Omit for all trackers."
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Fetch complete issue-creation context for a project in one call.

    Returns project info, trackers, categories, members, versions, statuses,
    priorities and custom fields. Call this once before create_redmine_issue
    to learn the valid tracker/priority/status/assignee/version values for
    that project.
    """
    return await get_project_issue_context_impl(
        project_id,
        tracker_id,
        ensure_cleanup_started=_no_op_cleanup,
        get_client=_get_redmine_client,
        custom_field_applies_to_tracker=_issue_fields._custom_field_applies_to_tracker,
        custom_field_to_dict=_issue_fields._custom_field_to_dict,
        membership_to_dict=_membership_to_dict,
        version_to_dict=_version_to_dict,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_redmine_issues(
    project_id: Annotated[
        Optional[Union[int, str]],
        Field(
            description=(
                "ID or identifier of the project to list issues from. Omit for all"
                " accessible projects."
            )
        ),
    ] = None,
    status_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Filter by issue status ID (e.g. 1=New, 2=In Progress, 3=Resolved,"
                " 5=Closed). Omit for any status."
            )
        ),
    ] = None,
    tracker_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Filter by tracker ID (e.g. 1=Bug, 2=Feature, 3=Task). Omit for any"
                " tracker."
            )
        ),
    ] = None,
    assigned_to_id: Annotated[
        Optional[Union[int, str]],
        Field(description="Filter by assignee user ID. Omit for any assignee."),
    ] = None,
    priority_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Filter by priority ID (e.g. 3=Normal, 4=High, 5=Urgent). Omit for any"
                " priority."
            )
        ),
    ] = None,
    fixed_version_id: Annotated[
        Optional[int],
        Field(
            description="Filter by target version/milestone ID. Omit for any version."
        ),
    ] = None,
    parent_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Only list issues whose parent task has this ID (i.e. its subtasks)."
            )
        ),
    ] = None,
    sort: Annotated[
        Optional[str],
        Field(
            description="Sort order, e.g. 'priority:desc', 'updated_on:desc', 'id:asc'."
        ),
    ] = None,
    limit: Annotated[
        Optional[int],
        Field(
            description="Maximum number of issues to return (1-100). Defaults to 25."
        ),
    ] = 25,
    offset: Annotated[
        int,
        Field(description="Pagination offset — skip this many issues."),
    ] = 0,
    include_pagination_info: Annotated[
        bool,
        Field(
            description=(
                "When True, return {issues, total_count, limit, offset} instead of a"
                " plain list."
            )
        ),
    ] = False,
    fields: Annotated[
        Optional[List[str]],
        Field(
            description=(
                "Issue fields to include per issue, e.g. ['id', 'subject', 'status']."
                " Omit for the default set."
            )
        ),
    ] = None,
    filters: Annotated[
        Optional[Dict[str, Any]],
        Field(
            description=(
                "Extra Redmine query filters as a dict, e.g. {'parent_id': 123} or"
                " {'category_id': 4}."
            )
        ),
    ] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List issues with flexible filters and pagination.

    Use when you need to find tasks by project, status, assignee, priority or
    version, or list the subtasks of a task via parent_id. Returns a list of
    issues; every issue carries a parent key describing its parent task (null
    for standalone issues).
    """
    return await list_redmine_issues_impl(
        project_id,
        status_id,
        tracker_id,
        assigned_to_id,
        priority_id,
        fixed_version_id,
        parent_id,
        sort,
        limit,
        offset,
        include_pagination_info,
        fields,
        filters,
        ensure_cleanup_started=_no_op_cleanup,
        get_client=_get_redmine_client,
        issue_to_dict_selective=_issue_to_dict_selective,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def search_redmine_issues(
    query: Annotated[
        str,
        Field(
            description=(
                "Free-text search query matched against subject, description and notes."
            )
        ),
    ],
    limit: Annotated[
        Optional[int],
        Field(
            description="Maximum number of issues to return (1-100). Defaults to 25."
        ),
    ] = 25,
    offset: Annotated[
        int,
        Field(description="Pagination offset — skip this many issues."),
    ] = 0,
    include_pagination_info: Annotated[
        bool,
        Field(
            description=(
                "When True, return {issues, total_count, limit, offset} instead of a"
                " plain list."
            )
        ),
    ] = False,
    fields: Annotated[
        Optional[List[str]],
        Field(
            description=(
                "Issue fields to include per issue, e.g. ['id', 'subject', 'status']."
                " Omit for the default set."
            )
        ),
    ] = None,
    scope: Annotated[
        Optional[str],
        Field(
            description=(
                "Search scope: 'all' (default), 'my_project' (issues in your projects),"
                " 'mine' (issues assigned to you)."
            )
        ),
    ] = None,
    open_issues: Annotated[
        bool,
        Field(description="When True, restrict results to open issues only."),
    ] = False,
    options: Annotated[
        Optional[Dict[str, Any]],
        Field(description="Extra Redmine search options, e.g. {'titles_only': True}."),
    ] = None,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Search issues by free-text query with pagination support.

    Use when the user asks to find tasks by keywords rather than by filters.
    Returns a list of matching issues; every issue carries a parent key
    describing its parent task (null for standalone issues).
    """
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
    project_id: Annotated[
        int,
        Field(
            description=(
                "ID of the project the issue is created in. Use list_redmine_projects"
                " or get_project_issue_context to find it."
            )
        ),
    ],
    subject: Annotated[
        str,
        Field(description="Title of the issue."),
    ],
    description: Annotated[
        str,
        Field(
            description=(
                "Body/description of the issue. Supports Redmine Textile/Wiki markup."
            )
        ),
    ],
    tracker_id: Annotated[
        int,
        Field(
            description=(
                "Issue type: 1 (Bug), 2 (Feature), 3 (Support), 4 (Common), 5"
                " (Testing Task)."
            )
        ),
    ],
    priority_id: Annotated[
        int,
        Field(
            description=(
                "Priority level of the issue, e.g. 3 = Normal, 4 = High, 5 ="
                " Urgent, 2 = Low."
            )
        ),
    ],
    status_id: Annotated[
        int,
        Field(
            description=(
                "Initial status of the issue, e.g. 1 = New, 2 = In Progress, 3 ="
                " Resolved, 4 = Feedback, 5 = Closed, 6 = Rejected."
            )
        ),
    ],
    assigned_to_id: Annotated[
        int,
        Field(
            description=(
                "ID of the user the issue is assigned to, e.g. 79 (Huỳnh Ngọc Đăng"
                " Khoa), 80 (Nguyễn Minh Phú), 75 (Đoàn Ngọc Phương Linh), 77"
                " (Nguyễn Trần Khánh Vinh), 30 (Võ Văn Thuận)."
            )
        ),
    ],
    start_date: Annotated[
        str,
        Field(description="Start date of the issue (YYYY-MM-DD)."),
    ],
    due_date: Annotated[
        str,
        Field(description="Due date of the issue (YYYY-MM-DD)."),
    ],
    estimated_hours: Annotated[
        float,
        Field(description="Estimated hours required to complete the issue."),
    ],
    done_ratio: Annotated[
        int,
        Field(description="Completion percentage of the issue (0 to 100)."),
    ],
    fields: Annotated[
        Optional[Union[Dict[str, Any], str]],
        Field(
            description=(
                "Optional extra fields: category_id, fixed_version_id, and custom"
                " field values via 'custom_fields': [{'id': X, 'value': Y}]. All"
                " other issue fields (tracker_id, priority_id, status_id,"
                " assigned_to_id, dates, estimated_hours, done_ratio) are passed as"
                " dedicated required parameters."
            )
        ),
    ] = None,
    extra_fields: Annotated[
        Optional[Union[Dict[str, Any], str]],
        Field(
            description=(
                "Advanced fields passed through to Redmine that are not in `fields`."
                " Rarely needed."
            )
        ),
    ] = None,
    parent_issue_id: Annotated[
        Optional[Union[int, str]],
        Field(
            description=(
                "Create this issue as a subtask of the task with this ID. The parent"
                " must exist and be in the same project; Redmine allows unlimited"
                " nesting depth, so the parent may itself be a subtask."
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Create a new issue, standalone or as a subtask of an existing task.

    Use when the user asks to create/track a task. All core issue fields
    (project, subject, description, tracker, priority, status, assignee,
    start/due dates, estimated hours, completion ratio) are required. Pass
    parent_issue_id to create the issue as a child of an existing task.
    Respects the issue template when enforced by policy; returns the created
    issue including its parent key.
    """
    try:
        merged_fields = _issue_fields._parse_create_issue_fields(fields)
    except ValueError:
        merged_fields = None

    if merged_fields is not None:
        merged_fields.update(
            {
                "tracker_id": tracker_id,
                "priority_id": priority_id,
                "status_id": status_id,
                "assigned_to_id": assigned_to_id,
                "start_date": start_date,
                "due_date": due_date,
                "estimated_hours": estimated_hours,
                "done_ratio": done_ratio,
            }
        )
        fields = merged_fields

    return await create_redmine_issue_impl(
        project_id,
        subject,
        description,
        fields,
        extra_fields,
        parent_issue_id,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        parse_create_issue_fields=_issue_fields._parse_create_issue_fields,
        parse_optional_object_payload=_issue_fields._parse_optional_object_payload,
        prepare_issue_fields=_prepare_create_issue_fields,
        validate_issue_template=validate_issue_description_template,
        resolve_tracker_name=_resolve_project_tracker_name,
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
async def create_redmine_issue_with_subtasks(
    project_id: Annotated[
        int,
        Field(description="ID of the project for the parent issue and all subtasks."),
    ],
    parent_subject: Annotated[
        str,
        Field(description="Title of the parent issue."),
    ],
    parent_description: Annotated[
        str,
        Field(description="Body of the parent issue (Textile/Wiki markup supported)."),
    ],
    tracker_id: Annotated[
        int,
        Field(
            description=(
                "Issue type of the parent issue: 1 (Bug), 2 (Feature), 3 (Support),"
                " 4 (Common), 5 (Testing Task)."
            )
        ),
    ],
    priority_id: Annotated[
        int,
        Field(
            description=(
                "Priority level of the parent issue, e.g. 3 = Normal, 4 = High."
            )
        ),
    ],
    status_id: Annotated[
        int,
        Field(
            description=(
                "Initial status of the parent issue, e.g. 1 = New, 2 = In Progress."
            )
        ),
    ],
    assigned_to_id: Annotated[
        int,
        Field(
            description=(
                "ID of the user assigned to the parent issue, e.g. 79 (Huỳnh Ngọc"
                " Đăng Khoa), 80 (Nguyễn Minh Phú), 75 (Đoàn Ngọc Phương Linh), 77"
                " (Nguyễn Trần Khánh Vinh), 30 (Võ Văn Thuận)."
            )
        ),
    ],
    start_date: Annotated[
        str,
        Field(description="Start date of the parent issue (YYYY-MM-DD)."),
    ],
    due_date: Annotated[
        str,
        Field(description="Due date of the parent issue (YYYY-MM-DD)."),
    ],
    estimated_hours: Annotated[
        float,
        Field(description="Estimated hours for the parent issue."),
    ],
    done_ratio: Annotated[
        int,
        Field(description="Completion percentage of the parent issue (0 to 100)."),
    ],
    parent_fields: Annotated[
        Optional[Union[Dict[str, Any], str]],
        Field(
            description=(
                "Optional extra fields for the parent issue: category_id,"
                " fixed_version_id, and custom field values via 'custom_fields':"
                " [{'id': X, 'value': Y}]."
            )
        ),
    ] = None,
    parent_extra_fields: Annotated[
        Optional[Union[Dict[str, Any], str]],
        Field(
            description=(
                "Advanced fields passed through to Redmine for the parent issue."
            )
        ),
    ] = None,
    subtasks: Annotated[
        Optional[List[Dict[str, Any]]],
        Field(
            description=(
                "List of subtask dicts, each requiring 'subject', 'description',"
                " 'tracker_id', 'priority_id', 'status_id', 'assigned_to_id',"
                " 'start_date', 'due_date', 'estimated_hours', 'done_ratio' plus"
                " optional 'fields' and 'extra_fields'."
            )
        ),
    ] = None,
    stop_on_subtask_error: Annotated[
        bool,
        Field(
            description=(
                "When True, abort remaining subtasks if one fails; otherwise continue"
                " and report per-subtask results."
            )
        ),
    ] = False,
) -> Dict[str, Any]:
    """Create one parent issue and multiple subtasks in a single call.

    Use for work items that decompose into several child tasks. All core
    issue fields (project, subject, description, tracker, priority, status,
    assignee, dates, estimated hours, completion ratio) are required for the
    parent and for every subtask. Returns the parent issue with per-subtask
    results.
    """
    return await create_redmine_issue_with_subtasks_impl(
        project_id=project_id,
        parent_subject=parent_subject,
        parent_description=parent_description,
        tracker_id=tracker_id,
        priority_id=priority_id,
        status_id=status_id,
        assigned_to_id=assigned_to_id,
        start_date=start_date,
        due_date=due_date,
        estimated_hours=estimated_hours,
        done_ratio=done_ratio,
        parent_fields=parent_fields,
        parent_extra_fields=parent_extra_fields,
        subtasks=subtasks,
        stop_on_subtask_error=stop_on_subtask_error,
        create_issue_fn=create_redmine_issue,
        wrap_content=wrap_insecure_content,
    )


@mcp.tool()
async def create_redmine_issue_relation(
    issue_id: Annotated[
        int,
        Field(
            description=(
                "ID of the issue whose dependency is being declared (the issue that"
                " comes first, blocks, or is related to the other)."
            )
        ),
    ],
    issue_to_id: Annotated[
        int,
        Field(
            description=(
                "ID of the other issue in the relation (the one that comes later, is"
                " blocked, or is related to the first)."
            )
        ),
    ],
    relation_type: Annotated[
        str,
        Field(
            description=(
                "Type of relation: 'precedes'/'follows' (issue_id must be done before"
                " issue_to_id; pick one direction — Redmine mirrors the other),"
                " 'blocks'/'blocked', 'relates', 'duplicates'/'duplicated',"
                " 'copied_to'/'copied_from'. Use 'precedes' to express 'task nào nên"
                " làm trước'."
            )
        ),
    ],
    delay: Annotated[
        Optional[int],
        Field(
            description=(
                "Optional delay in days (precedes/follows only), e.g. 1 = issue_to_id"
                " starts 1 day after issue_id."
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Create an issue relation (dependency) between two Redmine issues.

    Use to declare which task must be done first, so the Gantt chart and
    roadmap reflect the dependency order. Returns the created relation plus
    both issue subjects.
    """
    return await create_redmine_issue_relation_impl(
        issue_id=issue_id,
        issue_to_id=issue_to_id,
        relation_type=relation_type,
        delay=delay,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def delete_redmine_issue_relation(
    relation_id: Annotated[
        int,
        Field(description="ID of the issue relation to delete."),
    ],
) -> Dict[str, Any]:
    """Delete an issue relation from Redmine."""
    return await delete_redmine_issue_relation_impl(
        relation_id=relation_id,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def update_redmine_issue(
    issue_id: Annotated[int, Field(description="ID of the issue to update.")],
    fields: Annotated[
        Dict[str, Any],
        Field(
            description=(
                "Issue attributes to change, e.g. {'status_id': 3, 'assigned_to_id': 5,"
                " 'priority_id': 4, 'subject': '...', 'description': '...',"
                " 'fixed_version_id': ..., 'estimated_hours': ..., 'start_date':"
                " 'YYYY-MM-DD', 'due_date': ..., 'done_ratio': ..., 'parent_issue_id':"
                " ..., 'notes': 'comment to add', 'custom_fields': [{'id': X, 'value':"
                " Y}]}. Omitted keys stay unchanged. May be empty when only logging"
                " time."
            )
        ),
    ],
    spent_hours: Annotated[
        Optional[float],
        Field(
            description=(
                "Hours to log as a time entry on this issue, e.g. 1.5. When set, a"
                " time entry is created on the issue after the update and returned"
                " under the 'time_entry' key."
            )
        ),
    ] = None,
    activity_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Activity type ID for the logged time entry (use"
                " list_time_entry_activities for valid values)."
            )
        ),
    ] = None,
    time_comments: Annotated[
        Optional[str],
        Field(
            description=(
                "Work description for the logged time entry (distinct from the issue"
                " 'notes' comment)."
            )
        ),
    ] = None,
    spent_on: Annotated[
        Optional[str],
        Field(
            description=(
                "Date the work was done (YYYY-MM-DD) for the logged time entry."
                " Defaults to today."
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Update an existing Redmine issue, optionally logging time against it.

    Use to change status/assignee/priority/dates, add comments, reparent a
    task, and/or log hours worked on the issue in one call. Returns the
    updated issue including its parent key; when spent_hours is set, the
    created time entry is included under 'time_entry' (with an 'error' key
    plus time_entry_error=true if logging failed).
    """
    return await update_redmine_issue_impl(
        issue_id,
        fields,
        spent_hours,
        activity_id,
        time_comments,
        spent_on,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        get_client=_get_redmine_client,
        map_named_custom_fields_for_update=_map_named_custom_fields_for_update,
        issue_to_dict=_issue_to_dict,
        time_entry_to_dict=_time_entry_to_dict,
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
async def list_redmine_issue_statuses() -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List all issue statuses defined in Redmine."""
    return await list_redmine_issue_statuses_impl(
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def get_redmine_issue_allowed_statuses(
    issue_id: Annotated[
        int,
        Field(description="ID of the issue whose allowed status transitions to fetch."),
    ],
) -> Dict[str, Any]:
    """Get allowed status transitions for a specific issue.

    Use before changing an issue's status with update_redmine_issue to learn
    which statuses are reachable from the issue's current status.
    """
    return await get_redmine_issue_allowed_statuses_impl(
        issue_id,
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def manage_time_entries(
    action: Annotated[
        Literal["list", "create", "update", "delete", "activities"],
        Field(
            description=(
                "Operation to perform: 'list' time entries for a range, 'create' a new"
                " entry, 'update' an existing entry, 'delete' an existing entry,"
                " 'activities' list valid activity types."
            )
        ),
    ],
    time_entry_id: Annotated[
        Optional[int],
        Field(
            description=(
                "ID of the entry to update or delete (required when action='update'"
                " or action='delete')."
            )
        ),
    ] = None,
    hours: Annotated[
        Optional[float],
        Field(description="Hours spent, e.g. 1.5 (required when action='create')."),
    ] = None,
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Project ID or identifier for the entry (required when action='create'"
                " and issue_id is not set)."
            )
        ),
    ] = None,
    issue_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Issue ID the entry is logged against (either project_id or issue_id is"
                " required for 'create')."
            )
        ),
    ] = None,
    user_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Filter by user ID when action='list'."),
    ] = None,
    activity_id: Annotated[
        Optional[int],
        Field(
            description="Activity type ID (see action='activities' for valid values)."
        ),
    ] = None,
    comments: Annotated[
        Optional[str],
        Field(description="Work description for the entry."),
    ] = None,
    spent_on: Annotated[
        Optional[str],
        Field(description="Date the work was done (YYYY-MM-DD). Defaults to today."),
    ] = None,
    from_date: Annotated[
        Optional[str],
        Field(description="Start of the range when action='list' (YYYY-MM-DD)."),
    ] = None,
    to_date: Annotated[
        Optional[str],
        Field(description="End of the range when action='list' (YYYY-MM-DD)."),
    ] = None,
    limit: Annotated[
        int,
        Field(
            description="Maximum number of entries when action='list'. Defaults to 25."
        ),
    ] = 25,
    offset: Annotated[
        int,
        Field(description="Pagination offset when action='list'."),
    ] = 0,
) -> Dict[str, Any]:
    """Consolidated time-entry tool (list/create/update/activities).

    Use for all time logging: querying what was logged, adding hours, fixing
    entries, and discovering valid activity types. Returns {'action': ...,
    'data': ...}.
    """
    resolved_action = (action or "").strip().lower()

    if resolved_action == "list":
        data = await list_time_entries(
            project_id=project_id,
            issue_id=issue_id,
            user_id=user_id,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
        )
        return {"action": "list", "data": data}

    if resolved_action == "activities":
        data = await list_time_entry_activities()
        return {"action": "activities", "data": data}

    if resolved_action == "create":
        if hours is None:
            return {"error": "hours is required when action='create'."}
        data = await create_time_entry(
            hours=hours,
            project_id=project_id,
            issue_id=issue_id,
            activity_id=activity_id,
            comments=comments or "",
            spent_on=spent_on,
        )
        return {"action": "create", "data": data}

    if resolved_action == "update":
        if time_entry_id is None:
            return {"error": "time_entry_id is required when action='update'."}
        data = await update_time_entry(
            time_entry_id=time_entry_id,
            hours=hours,
            activity_id=activity_id,
            comments=comments,
            spent_on=spent_on,
        )
        return {"action": "update", "data": data}

    if resolved_action == "delete":
        if time_entry_id is None:
            return {"error": "time_entry_id is required when action='delete'."}
        data = await delete_time_entry(
            time_entry_id=time_entry_id,
        )
        return {"action": "delete", "data": data}

    return {
        "error": "Invalid action. Supported: list, create, update, delete, activities."
    }


@mcp.tool()
async def search_entire_redmine(
    query: Annotated[
        str,
        Field(description="Free-text search query sent to Redmine's global search."),
    ],
    resources: Annotated[
        Optional[List[str]],
        Field(
            description=(
                "Resource types to search: 'issues' and/or 'wiki-pages'. Omit for all."
            )
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of results overall. Defaults to 100."),
    ] = 100,
    offset: Annotated[
        int,
        Field(description="Pagination offset — skip this many results."),
    ] = 0,
) -> Dict[str, Any]:
    """Search issues and wiki pages across the Redmine instance.

    Use for cross-project discovery when list_redmine_issues/search_redmine_issues
    scoped to one project is not enough. Returns grouped results per resource
    type.
    """
    if not _WIKI_TOOLS_ENABLED:
        if resources is None:
            resources = ["issues"]
        else:
            resources = [r for r in resources if r != "wiki-pages"]
    return await search_entire_redmine_impl(
        query,
        resources,
        limit,
        offset,
        ensure_cleanup_started=_no_op_cleanup,
        get_client=_get_redmine_client,
        resource_to_dict=_resource_to_dict,
        handle_error=_handle_redmine_error,
        version_mismatch_error=VersionMismatchError,
    )


@_conditional_tool(_WIKI_TOOLS_ENABLED)
async def get_redmine_wiki_page(
    project_id: Annotated[
        Union[str, int],
        Field(description="ID or identifier of the project that owns the wiki page."),
    ],
    wiki_page_title: Annotated[
        str,
        Field(
            description=(
                "Title of the wiki page (URL-encoded slug form, e.g. 'Project_Home')."
            )
        ),
    ],
    version: Annotated[
        Optional[int],
        Field(
            description="Page version number to retrieve. Omit for the latest version."
        ),
    ] = None,
    include_attachments: Annotated[
        bool,
        Field(description="Include the page's attachments. Defaults to True."),
    ] = True,
) -> Dict[str, Any]:
    """Retrieve full wiki page content from Redmine.

    Use to read project documentation stored in a project wiki. Returns the
    page text, metadata and optionally attachments.
    """
    return await get_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        version,
        include_attachments,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_no_op_cleanup,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@_conditional_tool(_WIKI_TOOLS_ENABLED)
async def create_redmine_wiki_page(
    project_id: Annotated[
        Union[str, int],
        Field(description="ID or identifier of the project that owns the wiki page."),
    ],
    wiki_page_title: Annotated[
        str,
        Field(
            description=(
                "Title of the new wiki page (URL-encoded slug form, e.g."
                " 'Project_Home')."
            )
        ),
    ],
    text: Annotated[
        str,
        Field(description="Page content in Textile/Wiki markup."),
    ],
    comments: Annotated[
        str,
        Field(description="Edit comment describing the change."),
    ] = "",
) -> Dict[str, Any]:
    """Create a new wiki page in a Redmine project.

    Use to document project knowledge. Respects read-only mode; returns the
    created page.
    """
    return await create_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        text,
        comments,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_no_op_cleanup,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@_conditional_tool(_WIKI_TOOLS_ENABLED)
async def update_redmine_wiki_page(
    project_id: Annotated[
        Union[str, int],
        Field(description="ID or identifier of the project that owns the wiki page."),
    ],
    wiki_page_title: Annotated[
        str,
        Field(description="Title of the wiki page to update (URL-encoded slug form)."),
    ],
    text: Annotated[
        str,
        Field(
            description=(
                "New page content in Textile/Wiki markup (replaces the whole page)."
            )
        ),
    ],
    comments: Annotated[
        str,
        Field(description="Edit comment describing the change."),
    ] = "",
) -> Dict[str, Any]:
    """Update an existing wiki page in a Redmine project.

    Use to revise project documentation. Respects read-only mode; returns the
    updated page.
    """
    return await update_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        text,
        comments,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_no_op_cleanup,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@_conditional_tool(_WIKI_TOOLS_ENABLED)
async def delete_redmine_wiki_page(
    project_id: Annotated[
        Union[str, int],
        Field(description="ID or identifier of the project that owns the wiki page."),
    ],
    wiki_page_title: Annotated[
        str,
        Field(description="Title of the wiki page to delete (URL-encoded slug form)."),
    ],
) -> Dict[str, Any]:
    """Delete a wiki page from a Redmine project.

    Destructive: permanently removes the page. Respects read-only mode and
    confirms the deletion result.
    """
    return await delete_redmine_wiki_page_impl(
        project_id,
        wiki_page_title,
        get_client=_get_redmine_client,
        ensure_cleanup_started=_no_op_cleanup,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_time_entries(
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Filter by project ID or identifier. Omit for all projects."),
    ] = None,
    issue_id: Annotated[
        Optional[int],
        Field(description="Filter by issue ID. Omit for all issues."),
    ] = None,
    user_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Filter by user ID. Omit for all users."),
    ] = None,
    from_date: Annotated[
        Optional[str],
        Field(description="Start of the range (YYYY-MM-DD)."),
    ] = None,
    to_date: Annotated[
        Optional[str],
        Field(description="End of the range (YYYY-MM-DD)."),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Maximum number of entries to return. Defaults to 25."),
    ] = 25,
    offset: Annotated[
        int,
        Field(description="Pagination offset — skip this many entries."),
    ] = 0,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List time entries from Redmine with filtering and pagination.

    Use to answer questions about logged hours (who worked how long, on what,
    in a date range).
    """
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
    hours: Annotated[
        float,
        Field(description="Hours spent, e.g. 1.5 or 2."),
    ],
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Project ID or identifier the entry is logged against (required if"
                " issue_id is not set)."
            )
        ),
    ] = None,
    issue_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Issue ID the entry is logged against (either project_id or issue_id is"
                " required)."
            )
        ),
    ] = None,
    activity_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Activity type ID (use list_time_entry_activities for valid values)."
            )
        ),
    ] = None,
    comments: Annotated[
        str,
        Field(description="Work description for the entry."),
    ] = "",
    spent_on: Annotated[
        Optional[str],
        Field(description="Date the work was done (YYYY-MM-DD). Defaults to today."),
    ] = None,
) -> Dict[str, Any]:
    """Create a new time entry in Redmine.

    Use to log hours spent on a project or issue. Returns the created entry.
    """
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
    time_entry_id: Annotated[
        int,
        Field(description="ID of the time entry to update."),
    ],
    hours: Annotated[
        Optional[float],
        Field(description="New hours value, e.g. 1.5. Omit to keep current."),
    ] = None,
    activity_id: Annotated[
        Optional[int],
        Field(description="New activity type ID. Omit to keep current."),
    ] = None,
    comments: Annotated[
        Optional[str],
        Field(description="New work description. Omit to keep current."),
    ] = None,
    spent_on: Annotated[
        Optional[str],
        Field(description="New date (YYYY-MM-DD). Omit to keep current."),
    ] = None,
) -> Dict[str, Any]:
    """Update an existing time entry in Redmine.

    Use to fix hours, activity type, comments or dates of a logged entry.
    Returns the updated entry.
    """
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
async def delete_time_entry(
    time_entry_id: Annotated[
        int,
        Field(description="ID of the time entry to delete."),
    ],
) -> Dict[str, Any]:
    """Delete a time entry from Redmine.

    Destructive: permanently removes the entry. Respects read-only mode and
    confirms the deletion result.
    """
    return await delete_time_entry_impl(
        time_entry_id,
        get_client=_get_redmine_client,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def list_time_entry_activities() -> List[Dict[str, Any]]:
    """List available time entry activities from Redmine."""
    return await list_time_entry_activities_impl(
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


# =============================================================================
# Google Sheets Tools
# =============================================================================


@mcp.tool()
async def read_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    range: Annotated[
        str,
        Field(description="Range to read, e.g. 'TestCases!A1:J100' or 'Sheet1'"),
    ],
) -> Dict[str, Any]:
    """Read data from a specific range on Google Sheets."""
    return await read_google_sheet_impl(
        spreadsheet_id,
        range,
        get_sheets_service=google_sheets_manager.get_service,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def write_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    range: Annotated[
        str,
        Field(description="Range to write, e.g. 'TestCases!A1:J16'"),
    ],
    values: Annotated[
        List[List[str]], Field(description="2D array of values to write")
    ],
) -> Dict[str, Any]:
    """Write data to a specific Google Sheets range (overwrite)."""
    return await write_google_sheet_impl(
        spreadsheet_id,
        range,
        values,
        get_sheets_service=google_sheets_manager.get_service,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def append_google_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[
        str, Field(description="Sheet name to append to, e.g. 'Bugs'")
    ],
    values: Annotated[List[List[str]], Field(description="2D array of rows to append")],
) -> Dict[str, Any]:
    """Append rows to the end of a Google Sheet (does not overwrite existing data)."""
    return await append_google_sheet_impl(
        spreadsheet_id,
        sheet_name,
        values,
        get_sheets_service=google_sheets_manager.get_service,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def get_sheet_metadata(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
) -> Dict[str, Any]:
    """Get metadata about all sheets in a spreadsheet (names, headers, row counts)."""
    return await get_sheet_metadata_impl(
        spreadsheet_id,
        get_sheets_service=google_sheets_manager.get_service,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def create_test_cases_on_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[
        str,
        Field(description="Target sheet name, e.g. 'TestCases'"),
    ],
    test_cases: Annotated[
        List[Dict[str, str]],
        Field(
            description=(
                "List of test case dicts with keys: "
                "title, module, precondition, steps, expected_result, tester"
            )
        ),
    ],
    us_title: Annotated[
        str,
        Field(
            description="User story title used for the US section header row, e.g. 'Login Feature'"
        ),
    ],
    clear_existing: Annotated[
        bool,
        Field(description="Clear existing data before writing (keep headers)"),
    ] = False,
) -> Dict[str, Any]:
    """Create test cases on a Google Sheet."""
    return await create_test_cases_on_sheet_impl(
        spreadsheet_id,
        sheet_name,
        test_cases,
        clear_existing,
        us_title,
        get_sheets_service=google_sheets_manager.get_service,
        get_user_memory=get_user_memory,
        set_user_memory=set_user_memory,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def create_redmine_issues_from_bugs(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[
        str,
        Field(description="Bug sheet name, e.g. 'Bugs'"),
    ],
    project_id: Annotated[int, Field(description="Redmine project ID")],
    tracker_id: Annotated[
        int,
        Field(description="Redmine tracker ID (1=Bug, 2=Feature, 3=Task)"),
    ],
    assigned_to_id: Annotated[
        Optional[int],
        Field(description="Default assignee user ID on Redmine"),
    ] = None,
    bug_row_range: Annotated[
        Optional[str],
        Field(
            description=(
                "Specific range to process, e.g. 'A2:M50'. "
                "None = all rows with status 'New'"
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Read bug rows from Google Sheet, create Redmine issues, write issue IDs back."""
    return await create_redmine_issues_from_bugs_impl(
        spreadsheet_id,
        sheet_name,
        project_id,
        tracker_id,
        assigned_to_id,
        bug_row_range,
        get_sheets_service=google_sheets_manager.get_service,
        get_client=_get_redmine_client,
        map_priority=_map_priority_to_redmine,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def sync_redmine_status_to_sheet(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    bug_sheet: Annotated[str, Field(description="Bug sheet name")] = "Bugs",
    test_case_sheet: Annotated[
        str, Field(description="Test case sheet name")
    ] = "TestCases",
) -> Dict[str, Any]:
    """Sync Redmine statuses back to Google Sheet."""
    return await sync_redmine_status_to_sheet_impl(
        spreadsheet_id,
        bug_sheet,
        test_case_sheet,
        get_sheets_service=google_sheets_manager.get_service,
        get_client=_get_redmine_client,
        map_redmine_status=_map_redmine_status_to_sheet,
        parse_reject_reason=_parse_reject_reason,
        is_duplicate_rejection=_is_duplicate_rejection,
        parse_duplicate_issue_id=_parse_duplicate_issue_id,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def reopen_bug(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[str, Field(description="Bug sheet name, e.g. 'Bugs'")],
    bug_id: Annotated[str, Field(description="Bug ID to reopen, e.g. 'BUG-001'")],
    reopen_note: Annotated[
        str,
        Field(description="Note describing why the bug is reopened (what still fails)"),
    ],
    project_id: Annotated[int, Field(description="Redmine project ID")],
) -> Dict[str, Any]:
    """Reopen a bug on Redmine and Google Sheet."""
    return await reopen_bug_impl(
        spreadsheet_id,
        sheet_name,
        bug_id,
        reopen_note,
        project_id,
        get_sheets_service=google_sheets_manager.get_service,
        get_client=_get_redmine_client,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def set_sheet_data_validation(
    spreadsheet_id: Annotated[str, Field(description="Google Spreadsheet ID")],
    sheet_name: Annotated[
        str,
        Field(description="Target sheet name, e.g. 'TestCases'"),
    ],
    column: Annotated[
        int,
        Field(description="Column index (0-based). E.g. 0=A, 6=G, 7=H"),
    ],
    options: Annotated[
        List[str],
        Field(description="List of dropdown options, e.g. ['Pass', 'Fail', 'Blocked']"),
    ],
    start_row: Annotated[
        int,
        Field(description="Start row index (0-based, default 2 = row 3 after headers)"),
    ] = 2,
    end_row: Annotated[
        int,
        Field(description="End row index (0-based, default 100000)"),
    ] = 100000,
    strict: Annotated[
        bool,
        Field(description="If True, only values from the list are allowed"),
    ] = True,
    input_message: Annotated[
        str,
        Field(description="Tooltip message shown when user clicks the cell"),
    ] = "",
) -> Dict[str, Any]:
    """Set data validation (dropdown list) on a column in a Google Sheet.

    Use this to create dropdown menus for columns like tester, priority,
    status, or test result. The dropdown appears in the Google Sheets UI
    and restricts cell values to the provided options.

    Common use cases:
    - tester column: list of team member names
    - priority column: ['Low', 'Normal', 'High', 'Urgent']
    - last_test_result column: ['Not Tested', 'Pass', 'Fail', 'Blocked']
    - status column (Bugs): ['New', 'Open', 'In Progress', 'Done', ...]
    """
    return await set_sheet_data_validation_impl(
        spreadsheet_id,
        sheet_name,
        column,
        options,
        start_row=start_row,
        end_row=end_row,
        strict=strict,
        input_message=input_message,
        get_sheets_service=google_sheets_manager.get_service,
        handle_error=_handle_google_sheets_error,
    )


@mcp.tool()
async def create_test_sheet_structure(
    title: str = Field(description="The spreadsheet title"),
    spreadsheet_id: Optional[str] = Field(
        default=None,
        description=(
            "Existing spreadsheet ID. If provided, adds TestCases and Bugs sheets "
            "to that spreadsheet instead of creating a new one. Sheets that already "
            "exist are skipped. Use this when the user has already created and shared "
            "a spreadsheet with the service account."
        ),
    ),
    member_names: Optional[List[str]] = Field(
        default=None,
        description="List of Redmine member names for TESTER/ASSIGNED_TO dropdowns",
    ),
) -> Dict[str, Any]:
    """Create a new Google Spreadsheet with TestCases and Bugs sheets,
    OR add TestCases/Bugs sheets to an existing spreadsheet.

    Two modes:
    - **Without spreadsheet_id**: creates a brand-new spreadsheet owned by
      the service account. The user must share the resulting URL with their
      own Google account to access it.
    - **With spreadsheet_id**: adds TestCases and Bugs sheets to a spreadsheet
      the user has already created and shared with the service account. No
      re-sharing needed.

    Both modes include UPPERCASE headers, styled headers (blue bg, white bold
    text), frozen header row, column widths sized to each header text +
    consistent 12px L/R padding, and data validation dropdowns for tester,
    status, priority, last_test_result, and assigned_to.

    Returns:
        spreadsheet_id, spreadsheet_url, sheets info, and (for the existing-
        spreadsheet mode) created/skipped lists.
    """
    return await create_test_sheet_structure_impl(
        title,
        member_names=member_names,
        spreadsheet_id=spreadsheet_id,
        get_sheets_service=google_sheets_manager.get_service,
        handle_error=_handle_google_sheets_error,
    )


def _handle_google_sheets_error(
    e: Exception, operation: str, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Error handler for Google Sheets operations."""
    logger.error("Google Sheets error during %s: %s", operation, e)
    error_msg = str(e)
    if "credentials" in error_msg.lower():
        return {"error": error_msg}
    if "permission" in error_msg.lower() or "403" in error_msg:
        return {
            "error": "Access denied. Check service account permissions "
            "and ensure the sheet is shared with the service account email."
        }
    if "404" in error_msg or "not found" in error_msg.lower():
        return {"error": f"Spreadsheet not found: {error_msg}"}
    return {"error": f"Google Sheets error: {error_msg}"}


# --- Memory Tools (server-side) ---


@mcp.tool()
async def get_user_memory(
    key: Annotated[
        str,
        Field(
            description=(
                "Memory key to retrieve. Common keys: '.redmine' (Redmine project "
                "cache), '.google-sheets' (spreadsheet mappings). Any string key "
                "is accepted."
            )
        ),
    ],
) -> Dict[str, Any]:
    """Retrieve a stored memory entry for the current user.

    Memory persists server-side across sessions, keyed by your Redmine
    credentials. Use this instead of local .redmine / .google-sheets files
    when running in dynamic auth mode or from Claude Desktop.

    Common keys:
      - '.redmine': project cache (trackers, members, statuses, priorities, etc.)
      - '.google-sheets': project-to-spreadsheet mappings for QA
    """
    logger.warning("DEBUG get_user_memory: ENTRY key=%r", key)
    try:
        result = await get_user_memory_impl(
            key,
            get_entry=memory_store.get_entry,
        )
        logger.warning("DEBUG get_user_memory: success keys=%s", list(result.keys()))
        return result
    except Exception as e:
        logger.exception("get_user_memory unexpected error")
        return {"error": f"Failed to get memory: {e}"}


@mcp.tool()
async def set_user_memory(
    key: Annotated[
        str,
        Field(
            description=(
                "Memory key to store. Use conventional names like '.redmine' or "
                "'.google-sheets' for project cache and sheet mappings."
            )
        ),
    ],
    value: Annotated[
        Dict[str, Any],
        Field(
            description=(
                "JSON-serializable dict to store under this key. "
                "Will overwrite any existing value for this key."
            )
        ),
    ],
) -> Dict[str, Any]:
    """Store a memory entry for the current user.

    Memory persists server-side across sessions. Use this to save
    project context, spreadsheet mappings, or any user-scoped data
    that needs to survive across Claude Desktop sessions.

    The value completely replaces any previous value for this key.
    """
    logger.warning(
        "DEBUG set_user_memory: ENTRY key=%r value_keys=%s",
        key,
        list(value.keys()) if isinstance(value, dict) else type(value).__name__,
    )
    try:
        result = await set_user_memory_impl(
            key,
            value,
            set_entry=memory_store.set_entry,
        )
        logger.warning("DEBUG set_user_memory: success result=%r", result)
        return result
    except RuntimeError as e:
        # Identity not resolved (legacy mode, or ContextVar not propagated).
        # Return a clear error instead of letting the exception kill the
        # session silently.
        logger.error("set_user_memory failed: %s", e)
        return {
            "error": str(e),
            "hint": (
                "Memory tools require dynamic auth mode "
                "(REDMINE_AUTH_MODE=dynamic) with X-Redmine-URL and "
                "X-Redmine-API-Key headers on every request."
            ),
        }
    except Exception as e:
        logger.exception("set_user_memory unexpected error")
        return {"error": f"Failed to set memory: {e}"}


@mcp.tool()
async def delete_user_memory(
    key: Annotated[
        str,
        Field(description="Memory key to delete."),
    ],
) -> Dict[str, Any]:
    """Delete a memory entry for the current user.

    Removes the specified key from server-side memory.
    """
    logger.warning("DEBUG delete_user_memory: ENTRY key=%r", key)
    try:
        return await delete_user_memory_impl(
            key,
            delete_entry=memory_store.delete_entry,
        )
    except RuntimeError as e:
        logger.error("delete_user_memory failed: %s", e)
        return {"error": str(e)}
    except Exception as e:
        logger.exception("delete_user_memory unexpected error")
        return {"error": f"Failed to delete memory: {e}"}


@mcp.tool()
async def list_user_memory() -> Dict[str, Any]:
    """List all stored memory keys for the current user.

    Returns the list of keys and a count. Use get_user_memory to
    retrieve the value of a specific key.
    """
    logger.warning("DEBUG list_user_memory: ENTRY")
    try:
        return await list_user_memory_impl(
            list_keys=memory_store.list_keys,
            get_user_hash=memory_store.get_user_hash,
        )
    except Exception as e:
        logger.exception("list_user_memory unexpected error")
        return {"error": f"Failed to list memory: {e}"}


if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport="stdio")
