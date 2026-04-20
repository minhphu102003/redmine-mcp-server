import logging
from contextvars import ContextVar
from urllib.parse import urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from .security import validate_redmine_url, SecurityValidationError

logger = logging.getLogger(__name__)

# Context variables to hold per-request Redmine configuration
current_redmine_url: ContextVar[str | None] = ContextVar(
    "current_redmine_url", default=None
)
current_redmine_key: ContextVar[str | None] = ContextVar(
    "current_redmine_key", default=None
)

SKIP_DYNAMIC_AUTH_PATHS = {
    "/health",
}


class RedmineDynamicAuthMiddleware(BaseHTTPMiddleware):
    """Middleware for Dynamic Multi-Tenant Proxy mode.

    Extracts Redmine URL and API Key from request headers:
    - X-Redmine-URL: The target Redmine instance URL
    - X-Redmine-API-Key: The user's API Key
    - Authorization: Bearer <API_KEY> (optional fallback for API Key)
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_DYNAMIC_AUTH_PATHS:
            return await call_next(request)

        # 1. Extract and Validate Redmine URL
        redmine_url = request.headers.get("X-Redmine-URL", "").rstrip("/")
        if not redmine_url:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "missing_configuration",
                    "error_description": (
                        "X-Redmine-URL header is required in dynamic mode."
                    ),
                },
            )

        try:
            validate_redmine_url(redmine_url)
        except SecurityValidationError as e:
            # Log full details server-side for debugging, but return a generic
            # message to the client to prevent internal network topology enumeration.
            parsed = urlparse(redmine_url)
            redacted_url = f"{parsed.scheme}://{parsed.hostname or 'unknown'}"
            if parsed.port:
                redacted_url = f"{redacted_url}:{parsed.port}"
            logger.warning("Blocked unsafe Redmine URL '%s': %s", redacted_url, e)
            return JSONResponse(
                status_code=403,
                content={
                    "error": "forbidden_configuration",
                    "error_description": "The provided Redmine URL is not allowed.",
                },
            )

        # 2. Extract Redmine API Key
        # Priority: X-Redmine-API-Key > Authorization Header
        api_key = request.headers.get("X-Redmine-API-Key", "").strip()

        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                api_key = auth_header.removeprefix("Bearer ").strip()

        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "error_description": (
                        "Redmine API Key is required via X-Redmine-API-Key "
                        "or Authorization header."
                    ),
                },
            )

        # Set context variables
        url_token = current_redmine_url.set(redmine_url)
        key_token = current_redmine_key.set(api_key)

        try:
            return await call_next(request)
        finally:
            # Reset context variables after request is processed
            current_redmine_url.reset(url_token)
            current_redmine_key.reset(key_token)


def get_dynamic_config() -> tuple[str | None, str | None]:
    """Retrieve the dynamic Redmine URL and Key from the current context."""
    return current_redmine_url.get(), current_redmine_key.get()
