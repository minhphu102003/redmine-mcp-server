"""Shared Redmine error handling helpers."""

from __future__ import annotations

import logging
from typing import Any, Optional

from redminelib.exceptions import (
    AuthError,
    ForbiddenError,
    HTTPProtocolError,
    ResourceNotFoundError,
    ServerError,
    UnknownError,
    ValidationError,
    VersionMismatchError,
)
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    SSLError as RequestsSSLError,
    Timeout as RequestsTimeout,
)

logger = logging.getLogger(__name__)


def handle_redmine_error(
    e: Exception,
    operation: str,
    redmine_url: str,
    context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Convert exceptions into user-friendly, actionable error payloads."""
    context = context or {}
    resolved_redmine_url = redmine_url or "REDMINE_URL not configured"

    # Check SSLError BEFORE ConnectionError (SSLError inherits from ConnectionError)
    if isinstance(e, RequestsSSLError):
        logger.error(f"SSL error during {operation}: {e}")
        return {
            "error": (
                f"SSL/TLS error connecting to {resolved_redmine_url}. "
                "Please check: 1) SSL certificate validity, "
                "2) REDMINE_SSL_VERIFY setting, 3) REDMINE_SSL_CERT path"
            )
        }

    if isinstance(e, RequestsConnectionError):
        logger.error(f"Connection error during {operation}: {e}")
        return {
            "error": (
                f"Cannot connect to Redmine at {resolved_redmine_url}. "
                "Please check: 1) URL is correct, 2) Network is accessible, "
                "3) Redmine server is running"
            )
        }

    if isinstance(e, RequestsTimeout):
        logger.error(f"Timeout during {operation}: {e}")
        return {
            "error": (
                f"Connection to Redmine at {resolved_redmine_url} timed out. "
                "Please check: 1) Network connectivity, 2) Redmine server load"
            )
        }

    if isinstance(e, AuthError):
        logger.error(f"Authentication failed during {operation}")
        return {
            "error": (
                "Authentication failed. Please check your credentials: "
                "1) REDMINE_API_KEY is valid, or "
                "2) REDMINE_USERNAME and REDMINE_PASSWORD are correct"
            )
        }

    if isinstance(e, ForbiddenError):
        logger.error(f"Access denied during {operation}")
        return {
            "error": (
                "Access denied. Your Redmine user lacks the required permission "
                "for this action. Contact your Redmine administrator."
            )
        }

    if isinstance(e, ServerError):
        logger.error(f"Redmine server error during {operation}: {e}")
        return {
            "error": (
                "Redmine server returned an internal error (HTTP 500). "
                "Check the Redmine server logs or contact your administrator."
            )
        }

    if isinstance(e, ResourceNotFoundError):
        resource_type = context.get("resource_type", "resource")
        resource_id = context.get("resource_id", "")
        if resource_id:
            return {"error": f"{resource_type.capitalize()} {resource_id} not found."}
        return {"error": f"Requested {resource_type} not found."}

    if isinstance(e, ValidationError):
        logger.warning(f"Validation error during {operation}: {e}")
        return {"error": f"Validation failed: {str(e)}"}

    if isinstance(e, VersionMismatchError):
        return {"error": str(e)}

    if isinstance(e, HTTPProtocolError):
        logger.error(f"HTTP protocol error during {operation}: {e}")
        return {
            "error": (
                "HTTP/HTTPS protocol mismatch. Ensure REDMINE_URL uses the correct "
                "protocol (http:// or https://) matching your server configuration."
            )
        }

    if isinstance(e, UnknownError):
        logger.error(f"Unknown HTTP error during {operation}: status={e.status_code}")
        return {"error": f"Redmine returned HTTP {e.status_code}. Check server logs."}

    logger.error(f"Unexpected error during {operation}: {type(e).__name__}: {e}")
    return {"error": f"An unexpected error occurred while {operation}: {str(e)}"}
