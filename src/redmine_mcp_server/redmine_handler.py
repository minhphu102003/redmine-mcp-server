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

from .file_manager import AttachmentFileManager  # noqa: E402
from .handler_impl import issue_fields as _issue_fields  # noqa: E402
from .handler_impl.errors import handle_redmine_error  # noqa: E402
from .security import (  # noqa: E402
    validate_redmine_url,
    SecurityValidationError,
    ssrf_redirect_hook,
    SSRFSafeHTTPAdapter,
)
from .handler_impl.tools import (  # noqa: E402
    cleanup_attachment_files_impl,
    create_redmine_issue_with_subtasks_impl,
    create_redmine_issue_impl,
    create_redmine_wiki_page_impl,
    create_time_entry_impl,
    delete_redmine_wiki_page_impl,
    export_weekly_report_docx_impl,
    export_weekly_report_markdown_impl,
    generate_scrum_report_impl,
    get_redmine_attachment_download_url_impl,
    get_project_issue_context_impl,
    get_redmine_issue_impl,
    get_redmine_issue_allowed_statuses_impl,
    get_redmine_project_workflow_impl,
    get_redmine_wiki_page_impl,
    list_redmine_issue_statuses_impl,
    list_redmine_issues_impl,
    list_redmine_projects_impl,
    list_time_entries_impl,
    list_time_entry_activities_impl,
    search_entire_redmine_impl,
    search_redmine_issues_impl,
    summarize_project_status_impl,
    update_redmine_issue_impl,
    update_redmine_wiki_page_impl,
    update_time_entry_impl,
)
from .handler_impl.http_routes import (  # noqa: E402
    CleanupTaskManager,
    cleanup_status_payload,
    ensure_cleanup_started,
    health_payload,
    serve_attachment_by_id,
)
from .serialization import (  # noqa: E402,F401
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
from .resources import (  # noqa: E402
    ISSUE_TEMPLATE_RESOURCE_URI,
    TIME_ENTRY_CONTRACT_RESOURCE_URI,
    build_issue_contract_payload,
    build_issue_template_payload,
    build_time_entry_contract_payload,
    build_workflow_contract_payload,
    is_issue_template_enforced,
    required_issue_template_sections,
    validate_issue_description_template,
)
from .tool_prompts import register_tool_prompts  # noqa: E402

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
register_tool_prompts(mcp)


# Initialize cleanup manager
cleanup_manager = CleanupTaskManager()


# Global flag to track if cleanup has been initialized
_cleanup_initialized = False

_STATUS_ID_CACHE: Dict[str, tuple[Optional[int], float]] = {}
_PRIORITY_ID_CACHE: Dict[str, tuple[Optional[int], float]] = {}
_TRACKER_NAME_CACHE: Dict[tuple[str, int], tuple[Optional[str], float]] = {}
_METADATA_CACHE_TTL_SECONDS = 300.0
_CACHE_MISS = object()


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
_INSECURE_CONTENT_TAG_RE = re.compile(
    r"^<insecure-content-[^>]+>\s*(.*?)\s*</insecure-content-[^>]+>$",
    flags=re.DOTALL,
)


def _is_true_env(var_name: str, default: str = "false") -> bool:
    """Parse common truthy env-var values."""
    return os.getenv(var_name, default).strip().lower() in {"1", "true", "yes", "on"}


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
        priorities = await asyncio.to_thread(client.issue_priority.all)
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


@mcp.resource("redmine://workflow/{project_id}")
async def workflow_contract_resource(project_id: Union[str, int]) -> Dict[str, Any]:
    """Workflow transition contract inferred for a project."""
    return await build_workflow_contract_payload(
        project_id=project_id,
        tracker_id=None,
        get_workflow_snapshot=get_redmine_project_workflow_impl,
        list_statuses=list_redmine_issue_statuses_impl,
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.resource("redmine://workflow/{project_id}/{tracker_id}")
async def workflow_tracker_contract_resource(
    project_id: Union[str, int], tracker_id: Union[str, int]
) -> Dict[str, Any]:
    """Workflow transition contract inferred for a project tracker."""
    return await build_workflow_contract_payload(
        project_id=project_id,
        tracker_id=tracker_id,
        get_workflow_snapshot=get_redmine_project_workflow_impl,
        list_statuses=list_redmine_issue_statuses_impl,
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
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
        ensure_cleanup_started=_ensure_cleanup_started,
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

    Returns project info, trackers, categories, members, versions and custom
    fields. Call this once before create_redmine_issue to learn the valid
    tracker/priority/assignee/version values for that project.
    """
    return await get_project_issue_context_impl(
        project_id,
        tracker_id,
        ensure_cleanup_started=_ensure_cleanup_started,
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
        ensure_cleanup_started=_ensure_cleanup_started,
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
    ] = "",
    fields: Annotated[
        Optional[Union[Dict[str, Any], str]],
        Field(
            description=(
                "Structured issue fields: tracker_id, priority_id, assigned_to_id,"
                " category_id, fixed_version_id, estimated_hours, start_date/due_date"
                " (YYYY-MM-DD), done_ratio, and custom field values via"
                " 'custom_fields': [{'id': X, 'value': Y}]."
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
                " must exist, be in the same project, and not itself be a subtask."
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Create a new issue, standalone or as a subtask of an existing task.

    Use when the user asks to create/track a task. Pass parent_issue_id to
    create the issue as a child of an existing task. Respects the issue
    template when enforced by policy; returns the created issue including
    its parent key.
    """
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
    ] = "",
    parent_fields: Annotated[
        Optional[Union[Dict[str, Any], str]],
        Field(
            description=(
                "Structured fields for the parent issue (same keys as"
                " create_redmine_issue.fields)."
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
                "List of subtask dicts, each with 'subject' (required) and optional"
                " 'description', 'fields', 'extra_fields'."
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

    Use for work items that decompose into several child tasks. Each subtask
    is created under the new parent in the same project; returns the parent
    issue with per-subtask results.
    """
    return await create_redmine_issue_with_subtasks_impl(
        project_id=project_id,
        parent_subject=parent_subject,
        parent_description=parent_description,
        parent_fields=parent_fields,
        parent_extra_fields=parent_extra_fields,
        subtasks=subtasks,
        stop_on_subtask_error=stop_on_subtask_error,
        create_issue_fn=create_redmine_issue,
        wrap_content=wrap_insecure_content,
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
                " Y}]}. Omitted keys stay unchanged."
            )
        ),
    ],
) -> Dict[str, Any]:
    """Update an existing Redmine issue.

    Use to change status/assignee/priority/dates, add comments, or reparent
    a task. Returns the updated issue including its parent key.
    """
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
async def get_redmine_project_workflow(
    project_id: Annotated[
        Union[str, int],
        Field(description="ID or identifier of the project whose workflow to infer."),
    ],
    tracker_id: Annotated[
        Optional[int],
        Field(
            description=(
                "Restrict the workflow sample to one tracker. Omit for all trackers."
            )
        ),
    ] = None,
    status_id: Annotated[
        Optional[Union[int, str]],
        Field(description="Restrict the workflow sample to issues with this status."),
    ] = None,
    sample_limit: Annotated[
        int,
        Field(
            description=(
                "Maximum number of issues sampled to infer the workflow. Defaults"
                " to 25."
            )
        ),
    ] = 25,
) -> Dict[str, Any]:
    """Infer project workflow from issue-level allowed statuses (sample-based).

    Use to get an approximate status-transition map for a project when the
    exact per-status workflow is not available.
    """
    return await get_redmine_project_workflow_impl(
        project_id,
        tracker_id,
        status_id,
        sample_limit,
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def get_issue_workflow_context(
    mode: Annotated[
        Literal["issue", "transition_check", "project", "statuses"],
        Field(
            description=(
                "Which workflow data to fetch: 'issue' = allowed transitions for an"
                " issue; 'transition_check' = verify one specific target status;"
                " 'project' = workflow snapshot for a project; 'statuses' = list all"
                " statuses."
            )
        ),
    ] = "issue",
    issue_id: Annotated[
        Optional[int],
        Field(
            description="Issue ID, required for modes 'issue' and 'transition_check'."
        ),
    ] = None,
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Project ID or identifier, required for mode 'project'."),
    ] = None,
    tracker_id: Annotated[
        Optional[int],
        Field(description="Restrict the 'project' workflow snapshot to one tracker."),
    ] = None,
    status_id: Annotated[
        Optional[Union[int, str]],
        Field(
            description=(
                "Restrict the 'project' workflow snapshot to issues with this status."
            )
        ),
    ] = None,
    sample_limit: Annotated[
        int,
        Field(
            description=(
                "Maximum number of issues sampled for mode 'project'. Defaults to 25."
            )
        ),
    ] = 25,
    target_status_id: Annotated[
        Optional[int],
        Field(description="Target status ID to verify in mode 'transition_check'."),
    ] = None,
    target_status_name: Annotated[
        Optional[str],
        Field(
            description=(
                "Target status name to verify in mode 'transition_check' (matched"
                " case-insensitively)."
            )
        ),
    ] = None,
) -> Dict[str, Any]:
    """Consolidated workflow context tool.

    One entry point for status and workflow questions: pick the mode that
    matches the task ('issue', 'transition_check', 'project' or 'statuses').
    Returns mode-specific data; this tool replaces the legacy status/workflow
    tools.
    """
    resolved_mode = (mode or "issue").strip().lower()

    if resolved_mode == "statuses":
        data = await list_redmine_issue_statuses()
        return {"mode": "statuses", "data": data}

    if resolved_mode == "project":
        if project_id is None:
            return {"error": "project_id is required when mode='project'."}
        data = await get_redmine_project_workflow(
            project_id=project_id,
            tracker_id=tracker_id,
            status_id=status_id,
            sample_limit=sample_limit,
        )
        return {"mode": "project", "data": data}

    if issue_id is None:
        return {
            "error": (
                "issue_id is required for mode='issue' and mode='transition_check'."
            )
        }

    issue_data = await get_redmine_issue_allowed_statuses(issue_id)
    if isinstance(issue_data, dict) and "error" in issue_data:
        return {"mode": resolved_mode, "error": issue_data["error"]}

    if resolved_mode == "issue":
        return {"mode": "issue", "data": issue_data}

    if resolved_mode == "transition_check":
        if target_status_id is None and not target_status_name:
            return {
                "error": (
                    "target_status_id or target_status_name is required when "
                    "mode='transition_check'."
                )
            }

        allowed = (
            issue_data.get("allowed_statuses", [])
            if isinstance(issue_data, dict)
            else []
        )
        match = None
        if target_status_id is not None:
            for status in allowed:
                if status.get("id") == target_status_id:
                    match = status
                    break
        elif target_status_name:
            expected = _normalize_insecure_text(target_status_name)
            for status in allowed:
                if _normalize_insecure_text(status.get("name")) == expected:
                    match = status
                    break

        return {
            "mode": "transition_check",
            "issue_id": issue_id,
            "current_status": (
                issue_data.get("current_status")
                if isinstance(issue_data, dict)
                else None
            ),
            "target": {
                "id": target_status_id,
                "name": target_status_name,
            },
            "allowed": bool(match),
            "matched_status": match,
            "allowed_statuses": allowed,
        }

    return {
        "error": (
            "Invalid mode. Supported modes: statuses, issue, project, transition_check."
        )
    }


@mcp.tool()
async def manage_time_entries(
    action: Annotated[
        Literal["list", "create", "update", "activities"],
        Field(
            description=(
                "Operation to perform: 'list' time entries for a range, 'create' a new"
                " entry, 'update' an existing entry, 'activities' list valid activity"
                " types."
            )
        ),
    ],
    time_entry_id: Annotated[
        Optional[int],
        Field(description="ID of the entry to update (required when action='update')."),
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

    return {"error": "Invalid action. Supported: list, create, update, activities."}


@mcp.tool()
async def get_redmine_attachment_download_url(
    attachment_id: Annotated[
        int,
        Field(
            description=(
                "ID of the attachment (found in get_redmine_issue results or issue"
                " journals)."
            )
        ),
    ],
) -> Dict[str, Any]:
    """Get an HTTP download URL for a Redmine attachment.

    Use to obtain a temporary download link for an attached file; the file is
    fetched through this server so downloads work even when the Redmine
    instance is not directly reachable by the agent.
    """
    return await get_redmine_attachment_download_url_impl(
        attachment_id,
        ensure_cleanup_started=_ensure_cleanup_started,
        get_client=_get_redmine_client,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def summarize_project_status(
    project_id: Annotated[
        int,
        Field(description="ID of the project to summarize."),
    ],
    days: Annotated[
        int,
        Field(description="Look back window in days for the analysis. Defaults to 30."),
    ] = 30,
) -> Dict[str, Any]:
    """Provide a summary of project status over the specified time period.

    Use for high-level project health questions: issue counts by status,
    recent activity and trends in the given window.
    """
    return await summarize_project_status_impl(
        project_id,
        days,
        get_client=_get_redmine_client,
        analyze_issues=_analyze_issues,
        handle_error=_handle_redmine_error,
        resource_not_found_error=ResourceNotFoundError,
    )


@mcp.tool()
async def generate_scrum_report(
    report_type: Annotated[
        Literal["daily", "weekly", "custom"],
        Field(
            description=(
                "Report granularity: 'daily' for a day, 'weekly' for the last week,"
                " 'custom' requires from_date and to_date."
            )
        ),
    ] = "daily",
    user_id: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Restrict the report to one user (defaults to the authenticated user)."
            )
        ),
    ] = None,
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Restrict the report to one project."),
    ] = None,
    from_date: Annotated[
        Optional[str],
        Field(
            description="Start date (YYYY-MM-DD), required when report_type='custom'."
        ),
    ] = None,
    to_date: Annotated[
        Optional[str],
        Field(description="End date (YYYY-MM-DD), required when report_type='custom'."),
    ] = None,
    top_n_items: Annotated[
        int,
        Field(
            description=(
                "How many top issues/tasks to include in the report. Defaults to 7."
            )
        ),
    ] = 7,
    include_entries: Annotated[
        bool,
        Field(
            description="When True, include the raw time entries in the report output."
        ),
    ] = False,
) -> Dict[str, Any]:
    """Generate daily/weekly scrum report drafts from Redmine time entries.

    Use for standup/daily-status questions: returns a draft report grouping
    time entries by task with summaries.
    """
    return await generate_scrum_report_impl(
        report_type=report_type,
        user_id=user_id,
        project_id=project_id,
        from_date=from_date,
        to_date=to_date,
        top_n_items=top_n_items,
        include_entries=include_entries,
        get_client=_get_redmine_client,
        time_entry_to_dict=_time_entry_to_dict,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def export_weekly_report_markdown(
    user_id: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Restrict the report to one user (defaults to the authenticated user)."
            )
        ),
    ] = None,
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Restrict the report to one project."),
    ] = None,
    top_n_items: Annotated[
        int,
        Field(description="How many top items to include. Defaults to 7."),
    ] = 7,
    template_path: Annotated[
        Optional[str],
        Field(
            description=(
                "Path to a custom markdown template file. Omit for the built-in"
                " template."
            )
        ),
    ] = None,
    output_dir: Annotated[
        Optional[str],
        Field(
            description=(
                "Directory where the exported file is written. Defaults to the server's"
                " reports directory."
            )
        ),
    ] = None,
    file_name: Annotated[
        Optional[str],
        Field(
            description=(
                "Output file name (without extension). Defaults to an auto-generated"
                " name."
            )
        ),
    ] = None,
    unit_name: Annotated[
        str,
        Field(
            description=(
                "Unit/organization name shown in the report header. Defaults to 'TRUNG"
                " TÂM CSE'."
            )
        ),
    ] = "TRUNG TÂM CSE",
    reporter_name: Annotated[
        str,
        Field(
            description=(
                "Reporter name shown in the report. Defaults to 'NGƯỜI BÁO CÁO'."
            )
        ),
    ] = "NGƯỜI BÁO CÁO",
    location: Annotated[
        str,
        Field(description="Location shown in the report. Defaults to 'Đà Nẵng'."),
    ] = "Đà Nẵng",
    from_date: Annotated[
        Optional[str],
        Field(description="Custom start date (YYYY-MM-DD). Omit for the current week."),
    ] = None,
    to_date: Annotated[
        Optional[str],
        Field(description="Custom end date (YYYY-MM-DD). Omit for the current week."),
    ] = None,
) -> Dict[str, Any]:
    """Export the weekly report as a markdown file on the server.

    Use when the user asks for a weekly report document rather than a chat
    summary. Returns the path to the generated file.
    """
    return await export_weekly_report_markdown_impl(
        generate_scrum_report_fn=generate_scrum_report,
        user_id=user_id,
        project_id=project_id,
        top_n_items=top_n_items,
        template_path=template_path,
        output_dir=output_dir,
        file_name=file_name,
        unit_name=unit_name,
        reporter_name=reporter_name,
        location=location,
        from_date=from_date,
        to_date=to_date,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def export_weekly_report_docx(
    user_id: Annotated[
        Optional[Union[str, int]],
        Field(
            description=(
                "Restrict the report to one user (defaults to the authenticated user)."
            )
        ),
    ] = None,
    project_id: Annotated[
        Optional[Union[str, int]],
        Field(description="Restrict the report to one project."),
    ] = None,
    top_n_items: Annotated[
        int,
        Field(description="How many top items to include. Defaults to 7."),
    ] = 7,
    template_path: Annotated[
        Optional[str],
        Field(
            description=(
                "Path to a custom docx template file. Omit for the built-in template."
            )
        ),
    ] = None,
    output_dir: Annotated[
        Optional[str],
        Field(
            description=(
                "Directory where the exported file is written. Defaults to the server's"
                " reports directory."
            )
        ),
    ] = None,
    file_name: Annotated[
        Optional[str],
        Field(
            description=(
                "Output file name (without extension). Defaults to an auto-generated"
                " name."
            )
        ),
    ] = None,
    unit_name: Annotated[
        str,
        Field(
            description=(
                "Unit/organization name shown in the report header. Defaults to 'TRUNG"
                " TÂM CSE'."
            )
        ),
    ] = "TRUNG TÂM CSE",
    reporter_name: Annotated[
        str,
        Field(
            description=(
                "Reporter name shown in the report. Defaults to 'NGƯỜI BÁO CÁO'."
            )
        ),
    ] = "NGƯỜI BÁO CÁO",
    location: Annotated[
        str,
        Field(description="Location shown in the report. Defaults to 'Đà Nẵng'."),
    ] = "Đà Nẵng",
    from_date: Annotated[
        Optional[str],
        Field(description="Custom start date (YYYY-MM-DD). Omit for the current week."),
    ] = None,
    to_date: Annotated[
        Optional[str],
        Field(description="Custom end date (YYYY-MM-DD). Omit for the current week."),
    ] = None,
) -> Dict[str, Any]:
    """Export the weekly report as a .docx file for client-facing sharing.

    Use when the user asks for a Word document version of the weekly report.
    Returns the path to the generated file.
    """
    return await export_weekly_report_docx_impl(
        generate_scrum_report_fn=generate_scrum_report,
        user_id=user_id,
        project_id=project_id,
        top_n_items=top_n_items,
        template_path=template_path,
        output_dir=output_dir,
        file_name=file_name,
        unit_name=unit_name,
        reporter_name=reporter_name,
        location=location,
        from_date=from_date,
        to_date=to_date,
        handle_error=_handle_redmine_error,
    )


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
        ensure_cleanup_started=_ensure_cleanup_started,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
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
        ensure_cleanup_started=_ensure_cleanup_started,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
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
        ensure_cleanup_started=_ensure_cleanup_started,
        is_read_only_mode=_is_read_only_mode,
        read_only_error=_READ_ONLY_ERROR,
        wiki_page_to_dict=_wiki_page_to_dict,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
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
        ensure_cleanup_started=_ensure_cleanup_started,
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
