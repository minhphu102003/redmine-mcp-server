"""Structured per-tool-call logging for the Redmine MCP server.

Every MCP tool wrapper in ``redmine_handler`` is decorated with
:func:`log_tool_call`, so each real tool invocation on the deployed server
emits two single-line JSON records on stdout (visible via ``docker logs``):

- ``{"event": "tool.call", ...}`` — tool name, request id, full input params.
- ``{"event": "tool.result", ...}`` — same request id, duration in ms, full
  output on success (``ok: true``) or full error details on failure
  (``ok: false``), including results shaped as ``{"error": ...}`` which the
  handlers return instead of raising.

Secrets (API keys, passwords, tokens, ``X-Redmine-*`` headers) are masked as
``"***"`` before anything is logged, including inside nested dicts/lists.

Environment:
    - ``REDMINE_MCP_TOOL_LOG``: ``"off"``/``"0"``/``"false"`` disables all
      per-call logging (emergency kill switch). Enabled by default.
"""

import functools
import inspect
import json
import logging
import os
import time
import traceback
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)

REDACTED = "***"

# Case-insensitive substrings: any param/result key containing one of these
# has its value masked before logging.
_REDACT_KEY_PARTS = (
    "api_key",
    "apikey",
    "api-key",
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "x-redmine",
)


def _is_true(value: str, default: bool = True) -> bool:
    text = (value if value is not None else "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on"}


def tool_logging_enabled() -> bool:
    """Return whether per-tool-call logging is currently enabled."""
    return _is_true(os.getenv("REDMINE_MCP_TOOL_LOG", "true"), default=True)


def _should_redact(key: Any) -> bool:
    name = str(key).lower()
    return any(part in name for part in _REDACT_KEY_PARTS)


def redact(value: Any) -> Any:
    """Return a copy of *value* with secret fields masked as ``***``."""
    if isinstance(value, dict):
        return {
            key: REDACTED if _should_redact(key) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        redacted = [redact(item) for item in value]
        return type(value)(redacted) if isinstance(value, tuple) else redacted
    return value


def _is_error_result(result: Any) -> bool:
    """Return whether *result* is an error payload.

    Handlers usually return ``{"error": ...}`` on failure, but some return
    a *list* of such dicts (e.g. list tools surfacing one error entry).
    """
    if isinstance(result, dict):
        return "error" in result
    if isinstance(result, list) and result:
        return all(isinstance(item, dict) and "error" in item for item in result)
    return False


def _json_safe(value: Any) -> Any:
    """Round-trip *value* through JSON so logs never fail to serialize."""
    try:
        return json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        return str(value)


def _emit(record: dict) -> None:
    logger.info(json.dumps(_json_safe(record), ensure_ascii=False))


def log_tool_call(fn: Callable) -> Callable:
    """Decorate an MCP tool wrapper with full call/result logging.

    Must be applied *below* ``@mcp.tool()`` so FastMCP still sees the
    original signature (preserved via :func:`functools.wraps`).
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not tool_logging_enabled():
            return await fn(*args, **kwargs)
        request_id = uuid.uuid4().hex
        try:
            bound = inspect.signature(fn).bind(*args, **kwargs)
            bound.apply_defaults()
            params = dict(bound.arguments)
        except (TypeError, ValueError):
            params = {"args": list(args), **kwargs}
        _emit(
            {
                "event": "tool.call",
                "tool": fn.__name__,
                "request_id": request_id,
                "params": redact(params),
            }
        )
        start = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                json.dumps(
                    _json_safe(
                        {
                            "event": "tool.result",
                            "tool": fn.__name__,
                            "request_id": request_id,
                            "ok": False,
                            "duration_ms": duration_ms,
                            "error": f"{type(exc).__name__}: {exc}",
                            "traceback": traceback.format_exc(),
                        }
                    ),
                    ensure_ascii=False,
                )
            )
            raise
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        ok = not _is_error_result(result)
        _emit(
            {
                "event": "tool.result",
                "tool": fn.__name__,
                "request_id": request_id,
                "ok": ok,
                "duration_ms": duration_ms,
                "output": redact(result),
            }
        )
        return result

    return wrapper
