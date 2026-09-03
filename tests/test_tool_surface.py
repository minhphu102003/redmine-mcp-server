"""Tests for the MCP server surface (tools only, no prompts)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server.redmine_handler import mcp  # noqa: E402


@pytest.mark.asyncio
async def test_server_exposes_no_prompts():
    """The server must not register any MCP prompts (tool descriptions are enough)."""
    prompts = await mcp.list_prompts()
    assert prompts == []


@pytest.mark.asyncio
async def test_server_still_exposes_all_tools():
    """All MCP tools must remain registered (after removal of reporting/workflow tools)."""
    tools = await mcp.list_tools()
    assert len(tools) == 39


@pytest.mark.asyncio
async def test_every_tool_has_description():
    """Every registered tool must carry a non-empty description for agents."""
    tools = await mcp.list_tools()
    missing = [t.name for t in tools if not (t.description or "").strip()]
    assert not missing, f"Tools missing descriptions: {missing}"
