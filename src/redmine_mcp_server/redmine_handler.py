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
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from dotenv import load_dotenv

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
    create_redmine_issue_impl,
    create_redmine_wiki_page_impl,
    create_time_entry_impl,
    delete_redmine_wiki_page_impl,
    get_redmine_attachment_download_url_impl,
    get_redmine_issue_impl,
    get_redmine_issue_allowed_statuses_impl,
    get_redmine_project_workflow_impl,
    get_redmine_wiki_page_impl,
    list_redmine_issue_statuses_impl,
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
_INSECURE_CONTENT_TAG_RE = re.compile(
    r"^<insecure-content-[^>]+>\s*(.*?)\s*</insecure-content-[^>]+>$",
    flags=re.DOTALL,
)
_ISSUE_TEMPLATE_RESOURCE_URI = "redmine://issue-template/default"
_DEFAULT_ISSUE_DESCRIPTION_TEMPLATE = (
    "## Mục tiêu\n"
    "- Nêu mục tiêu/ngữ cảnh nghiệp vụ.\n\n"
    "## Hiện trạng\n"
    "- Mô tả hành vi hiện tại hoặc vấn đề đang gặp.\n\n"
    "## Kỳ vọng\n"
    "- Mô tả kết quả mong muốn.\n\n"
    "## Tiêu chí chấp nhận\n"
    "- [ ] Điều kiện chấp nhận 1\n"
    "- [ ] Điều kiện chấp nhận 2\n"
)
_ISSUE_TEMPLATE_SECTION_RE = re.compile(r"^\s{0,3}#{2,6}\s+(.+?)\s*$", re.MULTILINE)


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


def _is_read_only_mode() -> bool:
    """Check if the server is in read-only mode."""
    return _is_true_env("REDMINE_MCP_READ_ONLY", "false")


_READ_ONLY_ERROR = {
    "error": "This server is in read-only mode (REDMINE_MCP_READ_ONLY=true). "
    "Write operations are disabled."
}


def _is_issue_template_enforced() -> bool:
    """Return whether issue description template validation is enabled."""
    return _is_true_env("REDMINE_ENFORCE_ISSUE_TEMPLATE", "false")


def _load_issue_description_template() -> str:
    """Load issue description template from env with a safe default."""
    template = os.getenv("REDMINE_ISSUE_DESCRIPTION_TEMPLATE", "").strip()
    if template:
        return template
    return _DEFAULT_ISSUE_DESCRIPTION_TEMPLATE


def _extract_template_sections(template: str) -> List[str]:
    """Extract markdown heading names from template text."""
    sections: List[str] = []
    for match in _ISSUE_TEMPLATE_SECTION_RE.findall(template or ""):
        cleaned = match.strip()
        if cleaned:
            sections.append(cleaned)
    return sections


def _template_required_sections() -> List[str]:
    """Return required sections from env override or template headings."""
    raw = os.getenv("REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS", "").strip()
    if raw:
        return [section.strip() for section in raw.split(",") if section.strip()]
    return _extract_template_sections(_load_issue_description_template())


def _missing_template_sections(
    description: str, required_sections: List[str]
) -> List[str]:
    """Detect missing required markdown sections in issue description."""
    if not required_sections:
        return []

    normalized_description = description or ""
    detected_sections = {
        heading.strip().lower()
        for heading in _ISSUE_TEMPLATE_SECTION_RE.findall(normalized_description)
        if heading.strip()
    }
    return [
        section
        for section in required_sections
        if section.strip().lower() not in detected_sections
    ]


def _validate_issue_description_template(description: str) -> Optional[Dict[str, Any]]:
    """Validate issue description against required template sections."""
    if not _is_issue_template_enforced():
        return None

    required_sections = _template_required_sections()
    missing_sections = _missing_template_sections(description, required_sections)
    if not missing_sections:
        return None

    return {
        "error": (
            "Issue description does not match required template sections. "
            "Please follow the issue template resource before creating issue."
        ),
        "template_resource_uri": _ISSUE_TEMPLATE_RESOURCE_URI,
        "missing_sections": missing_sections,
    }


@mcp.resource(_ISSUE_TEMPLATE_RESOURCE_URI)
def issue_creation_template_resource() -> Dict[str, Any]:
    """Template guidance used by agents when creating Redmine issues."""
    template = _load_issue_description_template()
    required_sections = _template_required_sections()
    return {
        "resource": "issue_creation_template",
        "enforced": _is_issue_template_enforced(),
        "required_sections": required_sections,
        "template_markdown": template,
        "usage_note": (
            "When REDMINE_ENFORCE_ISSUE_TEMPLATE=true, create_redmine_issue "
            "rejects descriptions missing required sections."
        ),
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
        validate_issue_template=_validate_issue_description_template,
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
async def list_redmine_issue_statuses() -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List all issue statuses defined in Redmine."""
    return await list_redmine_issue_statuses_impl(
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def get_redmine_issue_allowed_statuses(issue_id: int) -> Dict[str, Any]:
    """Get allowed status transitions for a specific issue."""
    return await get_redmine_issue_allowed_statuses_impl(
        issue_id,
        get_client=_get_redmine_client,
        wrap_content=wrap_insecure_content,
        handle_error=_handle_redmine_error,
    )


@mcp.tool()
async def get_redmine_project_workflow(
    project_id: Union[str, int],
    tracker_id: Optional[int] = None,
    status_id: Optional[Union[int, str]] = None,
    sample_limit: int = 25,
) -> Dict[str, Any]:
    """Infer project workflow from issue-level allowed statuses (sample-based)."""
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
    mode: str = "issue",
    issue_id: Optional[int] = None,
    project_id: Optional[Union[str, int]] = None,
    tracker_id: Optional[int] = None,
    status_id: Optional[Union[int, str]] = None,
    sample_limit: int = 25,
    target_status_id: Optional[int] = None,
    target_status_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Consolidated workflow context tool.

    Supports statuses, issue transitions, and project workflow snapshots.
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
                "issue_id is required for mode='issue' and " "mode='transition_check'."
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
    action: str,
    time_entry_id: Optional[int] = None,
    hours: Optional[float] = None,
    project_id: Optional[Union[str, int]] = None,
    issue_id: Optional[int] = None,
    user_id: Optional[Union[str, int]] = None,
    activity_id: Optional[int] = None,
    comments: Optional[str] = None,
    spent_on: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """Consolidated time-entry tool (list/create/update/activities)."""
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
