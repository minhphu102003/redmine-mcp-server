"""Undecorated HTTP-route helper implementations for Redmine MCP."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def health_payload(auth_mode: str) -> dict[str, str]:
    """Build health endpoint payload."""
    return {
        "status": "ok",
        "service": "redmine_mcp_tools",
        "auth_mode": auth_mode,
    }
