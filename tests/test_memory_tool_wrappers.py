"""Standalone test for the memory MCP tool wrappers' error handling.

The wrappers live in redmine_handler.py but that module imports
`redminelib` at the top, which isn't installed in this test env.
This file extracts just the wrapper functions by source-parse and
exec's them in isolation, so we can test the error-handling logic
without needing redminelib.
"""

from __future__ import annotations

import asyncio
import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# Mock the dynamic_auth_middleware before importing memory_store
@pytest.fixture(autouse=True)
def mock_dynamic_auth():
    """Mock dynamic auth to return test credentials."""
    with patch(
        "redmine_mcp_server.memory_store._resolve_user_hash",
        return_value="test_user_hash_123",
    ):
        yield


def _load_wrapper(name: str):
    """Extract a single MCP tool wrapper function by reading the
    source of redmine_handler.py and exec'ing just that function.

    Returns a plain async function (no @mcp.tool() decorator) that
    still contains the try/except wrapping logic.
    """
    src_path = (
        Path(__file__).parent.parent
        / "src"
        / "redmine_mcp_server"
        / "redmine_handler.py"
    )
    src = src_path.read_text(encoding="utf-8")

    # Find: @mcp.tool()\nasync def NAME(... -> T): ... and capture body.
    # The signature may span many lines (Annotated[ ... Field( ... )] style)
    # and end with `-> ReturnType:`, so we explicitly require that.
    pattern = re.compile(
        r"@mcp\.tool\(\)\s*\n"
        r"async def " + re.escape(name) + r"\("
        r"[\s\S]*?"
        r"\)\s*->\s*[^:]+:\s*\n"
        r"([\s\S]*?)"
        r"(?=\n@mcp\.tool\(\)|\nif __name__|\Z)",
    )
    m = pattern.search(src)
    assert m, f"could not locate {name} in redmine_handler.py"
    body = m.group(1)

    # Build a minimal namespace with stubs for the impl helpers and
    # the memory_store module — tests will inject real behavior.
    # The impl functions in handler_impl/tools/memory.py are async,
    # so we provide async stubs that delegate to whatever
    # `memory_store` exposes. The tests patch the underlying
    # `memory_store.<method>` to drive the wrapper's behavior.
    from typing import Annotated, Any, Dict
    from pydantic import Field
    import logging

    async def _async_set_impl(key, value, *, set_entry):
        return set_entry(key, value)

    async def _async_get_impl(key, *, get_entry):
        entry = get_entry(key)
        if entry is None:
            return {"error": f"No memory entry found for key '{key}'."}
        return {"key": key, "value": entry}

    async def _async_delete_impl(key, *, delete_entry):
        return delete_entry(key)

    async def _async_list_impl(*, list_keys, get_user_hash):
        keys = list_keys()
        return {
            "user_hash": get_user_hash(),
            "keys": keys,
            "count": len(keys),
        }

    ns = {
        "Annotated": Annotated,
        "Field": Field,
        "Dict": Dict,
        "Any": Any,
        "logger": logging.getLogger("test"),
        "set_user_memory_impl": _async_set_impl,
        "get_user_memory_impl": _async_get_impl,
        "delete_user_memory_impl": _async_delete_impl,
        "list_user_memory_impl": _async_list_impl,
        # Use the REAL memory_store so patches at
        # `redmine_mcp_server.memory_store.<method>` propagate to the
        # wrapper. We only use the `set_entry` / `get_entry` /
        # `delete_entry` / `list_keys` attributes.
        "memory_store": __import__("redmine_mcp_server.memory_store", fromlist=["*"]),
    }
    # Dedent and indent the body so it sits inside the new function
    # definition. We construct `async def _wrapper(<NEW_SIG>):<BODY>`
    # but the body already starts with a docstring, not a signature
    # — the regex captured everything after the `:` of the original
    # signature. We need to drop the original signature and only keep
    # the body, then attach it to a fresh signature that accepts
    # whatever the tests need.
    body_dedented = textwrap.dedent(body).lstrip("\n")
    body_indented = textwrap.indent(body_dedented, "    ")
    # `list_user_memory` takes no args; the others take (key, value).
    # Use a flexible signature and let the test pass what it needs.
    if name == "list_user_memory":
        code = f"async def _wrapper(**kwargs):\n{body_indented}"
    else:
        code = f"async def _wrapper(key, value=None, **kwargs):\n{body_indented}"
    exec(code, ns)
    return ns["_wrapper"]


class TestMemoryToolWrappers:
    """The MCP tool wrappers in redmine_handler.py must convert
    exceptions into structured error dicts instead of letting them
    propagate to FastMCP and kill the session silently.
    """

    @pytest.mark.asyncio
    async def test_set_user_memory_returns_error_on_runtimeerror(self):
        """set_user_memory must return a clear error dict, not raise,
        when set_entry raises RuntimeError (e.g. ContextVar not
        propagated). Otherwise the session is terminated silently."""
        set_user_memory = _load_wrapper("set_user_memory")

        with patch(
            "redmine_mcp_server.memory_store.set_entry",
            side_effect=RuntimeError(
                "Cannot determine user identity for memory storage."
            ),
        ):
            result = await set_user_memory(key=".redmine", value={"project": {"id": 1}})

        assert isinstance(result, dict)
        assert "error" in result
        assert "Cannot determine user identity" in result["error"]
        assert "hint" in result
        assert "dynamic" in result["hint"].lower()

    @pytest.mark.asyncio
    async def test_set_user_memory_returns_error_on_unexpected_exception(self):
        """set_user_memory must swallow unexpected exceptions too."""
        set_user_memory = _load_wrapper("set_user_memory")

        with patch(
            "redmine_mcp_server.memory_store.set_entry",
            side_effect=OSError("disk full"),
        ):
            result = await set_user_memory(key=".redmine", value={"project": {"id": 1}})

        assert isinstance(result, dict)
        assert "error" in result
        assert "Failed to set memory" in result["error"]

    @pytest.mark.asyncio
    async def test_get_user_memory_returns_error_on_exception(self):
        """get_user_memory must not let exceptions kill the session."""
        get_user_memory = _load_wrapper("get_user_memory")

        with patch(
            "redmine_mcp_server.memory_store.get_entry",
            side_effect=OSError("permission denied"),
        ):
            result = await get_user_memory(key=".redmine")

        assert isinstance(result, dict)
        assert "error" in result
        assert "Failed to get memory" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_user_memory_returns_error_on_runtimeerror(self):
        """delete_user_memory must return error, not raise."""
        delete_user_memory = _load_wrapper("delete_user_memory")

        with patch(
            "redmine_mcp_server.memory_store.delete_entry",
            side_effect=RuntimeError("Cannot determine user identity."),
        ):
            result = await delete_user_memory(key=".redmine")

        assert isinstance(result, dict)
        assert "error" in result
        assert "Cannot determine user identity" in result["error"]

    @pytest.mark.asyncio
    async def test_list_user_memory_returns_error_on_exception(self):
        """list_user_memory must not let exceptions kill the session."""
        list_user_memory = _load_wrapper("list_user_memory")

        with patch(
            "redmine_mcp_server.memory_store.list_keys",
            side_effect=OSError("disk error"),
        ):
            result = await list_user_memory()

        assert isinstance(result, dict)
        assert "error" in result
        assert "Failed to list memory" in result["error"]

    @pytest.mark.asyncio
    async def test_set_user_memory_passes_through_on_success(self):
        """When set_entry succeeds, the wrapper returns the success dict."""
        set_user_memory = _load_wrapper("set_user_memory")

        with patch(
            "redmine_mcp_server.memory_store.set_entry",
            return_value={"status": "ok", "key": ".redmine", "updated_at": "x"},
        ):
            result = await set_user_memory(key=".redmine", value={"project": {"id": 1}})

        assert result == {
            "status": "ok",
            "key": ".redmine",
            "updated_at": "x",
        }
