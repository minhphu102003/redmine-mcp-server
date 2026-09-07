"""Tests for per-tool-call structured logging (tool_logging + wrappers)."""

import json
import logging
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from redmine_mcp_server import tool_logging  # noqa: E402
from redmine_mcp_server.tool_logging import log_tool_call, redact  # noqa: E402


@pytest.fixture
def log_records():
    """Capture records emitted by the tool_logging logger as parsed JSON."""
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(json.loads(record.getMessage()))

    handler = _Collector()
    target = logging.getLogger(tool_logging.__name__)
    target.addHandler(handler)
    old_level = target.level
    target.setLevel(logging.DEBUG)
    try:
        yield records
    finally:
        target.removeHandler(handler)
        target.setLevel(old_level)


def _by_event(records, event):
    return [r for r in records if r.get("event") == event]


def test_success_logs_full_params_and_output(log_records):
    """A successful call emits tool.call + tool.result with full payload."""

    @log_tool_call
    async def sample_tool(issue_id, verbose=False):
        return {"id": issue_id, "verbose": verbose, "rows": [1, 2, 3]}

    import asyncio

    result = asyncio.run(sample_tool(42, verbose=True))
    assert result == {"id": 42, "verbose": True, "rows": [1, 2, 3]}

    calls = _by_event(log_records, "tool.call")
    results = _by_event(log_records, "tool.result")
    assert len(calls) == 1
    assert len(results) == 1
    assert calls[0]["tool"] == "sample_tool"
    assert calls[0]["params"] == {"issue_id": 42, "verbose": True}
    assert results[0]["request_id"] == calls[0]["request_id"]
    assert results[0]["ok"] is True
    assert results[0]["output"] == {"id": 42, "verbose": True, "rows": [1, 2, 3]}
    assert isinstance(results[0]["duration_ms"], (int, float))


def test_error_dict_result_logged_as_not_ok(log_records):
    """Handlers return {"error": ...} instead of raising — still ok:false."""

    @log_tool_call
    async def failing_tool(issue_id):
        return {"error": f"No issue with id {issue_id}."}

    import asyncio

    result = asyncio.run(failing_tool(999))
    assert result == {"error": "No issue with id 999."}
    results = _by_event(log_records, "tool.result")
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert results[0]["output"] == {"error": "No issue with id 999."}


def test_exception_logs_traceback_and_reraises(log_records):
    """Raised exceptions are logged with traceback, then re-raised."""

    @log_tool_call
    async def boom_tool():
        raise RuntimeError("redmine down")

    import asyncio

    with pytest.raises(RuntimeError, match="redmine down"):
        asyncio.run(boom_tool())
    results = _by_event(log_records, "tool.result")
    assert len(results) == 1
    assert results[0]["ok"] is False
    assert "RuntimeError: redmine down" in results[0]["error"]
    assert "Traceback" in results[0]["traceback"]
    assert "boom_tool" in results[0]["traceback"]


def test_error_list_result_logged_as_not_ok(log_records):
    """List tools may return [{"error": ...}] — also ok:false."""

    @log_tool_call
    async def listy_tool():
        return [{"error": "boom"}]

    import asyncio

    assert asyncio.run(listy_tool()) == [{"error": "boom"}]
    results = _by_event(log_records, "tool.result")
    assert len(results) == 1
    assert results[0]["ok"] is False


def test_secrets_redacted_in_params_and_output():
    """API keys, passwords, tokens are masked, incl. nested structures."""
    payload = {
        "api_key": "live-key",
        "headers": {"X-Redmine-API-Key": "live-key", "other": "kept"},
        "auth": {"password": "pw", "user": "boss"},
        "items": [{"token": "tok", "id": 1}],
        "plain": "visible",
    }
    redacted = redact(payload)
    assert redacted["api_key"] == "***"
    assert redacted["headers"] == {"X-Redmine-API-Key": "***", "other": "kept"}
    assert redacted["auth"] == {"password": "***", "user": "boss"}
    assert redacted["items"] == [{"token": "***", "id": 1}]
    assert redacted["plain"] == "visible"


def test_redacted_values_reach_the_log(log_records):
    """Redaction applies to what is actually emitted, not just the helper."""

    @log_tool_call
    async def auth_tool(api_key):
        return {"api_key": api_key, "ok": True}

    import asyncio

    asyncio.run(auth_tool("super-secret"))
    calls = _by_event(log_records, "tool.call")
    results = _by_event(log_records, "tool.result")
    assert calls[0]["params"] == {"api_key": "***"}
    assert results[0]["output"] == {"api_key": "***", "ok": True}


def test_kill_switch_disables_logging(log_records):
    """REDMINE_MCP_TOOL_LOG=false passes through with zero log records."""

    @log_tool_call
    async def quiet_tool(x):
        return {"x": x}

    import asyncio

    with patch.dict(os.environ, {"REDMINE_MCP_TOOL_LOG": "false"}):
        result = asyncio.run(quiet_tool(1))
    assert result == {"x": 1}
    assert log_records == []


def test_wrapper_preserves_name():
    """functools.wraps keeps the original tool name for FastMCP."""

    @log_tool_call
    async def named_tool():
        """Doc."""
        return {}

    assert named_tool.__name__ == "named_tool"


@pytest.mark.asyncio
async def test_decorated_tool_registers_with_schema():
    """FastMCP still builds the input schema through the logging wrapper."""
    from fastmcp import FastMCP
    from pydantic import Field
    from typing import Annotated

    probe = FastMCP("probe-logging")

    @probe.tool()
    @log_tool_call
    async def probe_logged(x: Annotated[int, Field(description="x")] = 1):
        """Probe."""
        return {"v": x}

    tools = await probe.list_tools()
    match = [t for t in tools if t.name == "probe_logged"]
    assert len(match) == 1
    assert match[0].parameters["properties"]["x"]["type"] == "integer"


@pytest.mark.asyncio
async def test_all_server_tools_registered():
    """All 39 server tools stay registered after adding the decorator."""
    from redmine_mcp_server.redmine_handler import mcp

    tools = await mcp.list_tools()
    assert len(tools) == 39
