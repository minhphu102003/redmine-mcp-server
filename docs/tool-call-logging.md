# Tool-call logging (e2e trace per tool)

Every MCP tool call on the deployed server is logged as two single-line JSON
records on stdout (visible via `docker logs`). No code changes per tool are
needed — all 39 wrappers in `redmine_handler.py` share the `@log_tool_call`
decorator (`src/redmine_mcp_server/tool_logging.py`).

## What is logged

- `tool.call` — tool name, `request_id`, full input `params`.
- `tool.result` — same `request_id`, `duration_ms`, `ok`, full `output`.
  Results shaped as `{"error": ...}` (or a list of those) are logged with
  `"ok": false`. Raised exceptions are logged with `error` + full
  `traceback` at ERROR level, then re-raised.

Example (pretty-printed, real log is one line):

```json
{"event": "tool.call", "tool": "get_redmine_issue", "request_id": "36a8e7…", "params": {"issue_id": 1, "include_journals": false, …}}
{"event": "tool.result", "tool": "get_redmine_issue", "request_id": "36a8e7…", "ok": false, "duration_ms": 0.22, "output": {"error": "…"}}
```

Secrets (`api_key`, `password`, `token`, `X-Redmine-*`, …) are masked as
`"***"` everywhere, including nested objects.

## Tracing one call

```bash
# all lines for one request
docker logs <container> 2>&1 | grep '<request_id>'

# every failed tool call
docker logs <container> 2>&1 | grep '"tool.result"' | grep '"ok": false'

# slow calls (eyeball duration_ms), or pipe through jq:
docker logs <container> 2>&1 | grep '"tool.result"' | jq -s 'sort_by(.duration_ms) | reverse | .[0:5]'
```

(Note: stdlib logging writes to stderr by default — `docker logs` merges
both streams, so one command covers everything.)

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `REDMINE_MCP_TOOL_LOG` | `true` | Set to `false`/`0`/`off` to disable per-call logging (emergency kill switch). |
| `REDMINE_MCP_LOG_LEVEL` | `INFO` | Root log level (`DEBUG`, `INFO`, `WARNING`, …). |

Server startup prints `Tool-call logging: enabled|disabled` so you can
confirm the setting in `docker logs` right after deploy.

## For developers

- Add the decorator **below** `@mcp.tool()` on any new tool wrapper so
  FastMCP still resolves the original signature (covered by
  `tests/test_tool_logging.py::test_decorated_tool_registers_with_schema`).
- `tests/test_tool_logging.py` covers: full params/output, `{"error"}`
  and `[{...error...}]` → `ok:false`, exception + traceback + re-raise,
  secret redaction, kill switch, 39-tool registration intact.
