"""
Main entry point for the MCP Redmine server.

This module uses FastMCP's native HTTP transport for MCP protocol communication.
The server runs with built-in HTTP endpoints and handles MCP requests natively.

Endpoints:
    - /mcp: Handles MCP requests via streamable HTTP transport.

Modules:
    - .redmine_handler: Contains the MCP server logic with FastMCP integration.
"""

import logging
import os
import uvicorn
import httpx
from importlib.metadata import version, PackageNotFoundError
from starlette.requests import Request
from starlette.responses import JSONResponse
import argparse
import threading

# Configure basic logging before importing modules that log during init
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from .redmine_handler import mcp, _is_true_env  # noqa: E402
from .oauth_middleware import RedmineOAuthMiddleware  # noqa: E402
from .dynamic_auth_middleware import RedmineDynamicAuthMiddleware  # noqa: E402

logger = logging.getLogger(__name__)

REDMINE_URL = os.environ.get("REDMINE_URL", "").rstrip("/")
REDMINE_MCP_BASE_URL = os.environ.get(
    "REDMINE_MCP_BASE_URL", "http://localhost:3040"
).rstrip("/")
REDMINE_AUTH_MODE = os.environ.get("REDMINE_AUTH_MODE", "legacy").lower()


def get_version() -> str:
    """Get package version from metadata."""
    try:
        return version("redmine-mcp-server")
    except PackageNotFoundError:
        return "dev"


def _is_public_bind(host: str) -> bool:
    """Return whether host binds beyond loopback interfaces."""
    normalized = (host or "").strip().lower()
    return normalized not in {"", "127.0.0.1", "localhost", "::1"}


# --- OAuth2 route handlers (registered conditionally) ---


async def oauth_protected_resource(request: Request):
    """RFC 8707 — Protected Resource Metadata."""
    return JSONResponse(
        {
            "resource": f"{REDMINE_MCP_BASE_URL}/mcp",
            "authorization_servers": [REDMINE_MCP_BASE_URL],
            "bearer_methods_supported": ["header"],
            "resource_name": "Redmine MCP Server",
        }
    )


async def oauth_authorization_server(request: Request):
    """RFC 8414 — Authorization Server Metadata.

    Redmine uses Doorkeeper but does not serve this discovery document itself.
    We serve it manually, pointing to Redmine's real Doorkeeper endpoints.
    """
    return JSONResponse(
        {
            "issuer": REDMINE_MCP_BASE_URL,
            "authorization_endpoint": f"{REDMINE_URL}/oauth/authorize",
            "token_endpoint": f"{REDMINE_URL}/oauth/token",
            "revocation_endpoint": f"{REDMINE_URL}/oauth/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
            ],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": [
                "client_secret_post",
                "client_secret_basic",
            ],
        }
    )


async def revoke_token(request: Request):
    """RFC 7009 — Revoke an OAuth2 access or refresh token.

    Proxies token revocation to Redmine's Doorkeeper /oauth/revoke endpoint.

    Accepts token via:
    - Authorization header: Bearer <token>
    - POST body: {"token": "<token>"} or form-encoded token=<token>

    Returns:
        200 OK on success (per RFC 7009, even if token was already invalid)
        400 Bad Request if no token provided
        502 Bad Gateway if Redmine is unreachable
    """
    token = None
    allow_unauthenticated_revoke = _is_true_env(
        "REDMINE_ALLOW_UNAUTHENTICATED_REVOKE", "false"
    )

    # Authorization header is required by default.
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
    elif not allow_unauthenticated_revoke:
        return JSONResponse(
            status_code=401,
            content={
                "error": "unauthorized",
                "error_description": (
                    "Authorization: Bearer <token> is required for token revocation. "
                    "Set REDMINE_ALLOW_UNAUTHENTICATED_REVOKE=true only in trusted "
                    "internal networks."
                ),
            },
        )

    if not token and allow_unauthenticated_revoke:
        content_type = request.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                body = await request.json()
                token = body.get("token")
            except Exception:
                token = None
        else:
            try:
                form = await request.form()
                token = form.get("token")
            except Exception:
                token = None

    if not token:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "No token provided",
            },
        )

    # Forward revocation to Redmine's Doorkeeper endpoint
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{REDMINE_URL}/oauth/revoke",
                data={"token": token},
                timeout=10,
            )
        except httpx.RequestError as e:
            logger.error(f"Failed to reach Redmine for token revocation: {e}")
            return JSONResponse(
                status_code=502,
                content={"error": "upstream_unavailable"},
            )

    # RFC 7009: return 200 regardless of whether token was valid
    # (to prevent token scanning attacks)
    if response.status_code in (200, 204):
        return JSONResponse(status_code=200, content={"success": True})

    # If Redmine returns an error, log but still return success per RFC 7009
    logger.warning(
        f"Redmine revocation returned {response.status_code}: " f"{response.text}"
    )
    return JSONResponse(status_code=200, content={"success": True})


def register_oauth_routes(target_app):
    """Register OAuth2 discovery and revocation routes on a Starlette app."""
    target_app.add_route(
        "/.well-known/oauth-protected-resource",
        oauth_protected_resource,
        methods=["GET"],
    )
    target_app.add_route(
        "/.well-known/oauth-authorization-server",
        oauth_authorization_server,
        methods=["GET"],
    )
    target_app.add_route("/revoke", revoke_token, methods=["POST"])


# Export the Starlette app for testing and external use
app = mcp.http_app(stateless_http=True)

# Register OAuth2 middleware and endpoints only when auth mode is oauth
if REDMINE_AUTH_MODE == "oauth":
    app.add_middleware(RedmineOAuthMiddleware)
    register_oauth_routes(app)
elif REDMINE_AUTH_MODE == "dynamic":
    app.add_middleware(RedmineDynamicAuthMiddleware)

# Log version at module load time so it appears regardless of how the server is started
logger.info("Redmine MCP Server v%s", get_version())
logger.info("Auth mode: %s", REDMINE_AUTH_MODE)


def main():
    """Main entry point for the console script."""

    # Note: .env is already loaded during redmine_handler import
    # Note: version/auth mode are logged at module level
    # (works for both direct and uvicorn invocation)

    parser = argparse.ArgumentParser(description="Redmine MCP Server")
    parser.add_argument(
        "--transport",
        choices=["http", "stdio"],
        default="http",
        help="Transport mode: 'http' (default) or 'stdio' (hybrid mode)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("SERVER_HOST", "127.0.0.1"),
        help="Host to bind HTTP server to (default: 127.0.0.1 or SERVER_HOST env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("SERVER_PORT", "8000")),
        help="Port to bind HTTP server to (default: 8000 or SERVER_PORT env)",
    )

    # Use parse_known_args to avoid conflicts with other potential injectors
    args, _ = parser.parse_known_args()

    if (
        REDMINE_AUTH_MODE == "legacy"
        and _is_public_bind(args.host)
        and not _is_true_env("REDMINE_ALLOW_INSECURE_LEGACY_PUBLIC", "false")
    ):
        logger.error(
            "Refusing to start in legacy mode on public host '%s'. "
            "Use REDMINE_AUTH_MODE=oauth or REDMINE_AUTH_MODE=dynamic. "
            "Override only if you understand the risk by setting "
            "REDMINE_ALLOW_INSECURE_LEGACY_PUBLIC=true.",
            args.host,
        )
        raise SystemExit(2)

    if args.transport == "stdio":
        logger.info("Starting in HYBRID mode (MCP tools via stdio, files via HTTP)")

        # threading.Event lets the health-poll thread signal us the moment
        # the HTTP server is accepting connections, so we can detect startup
        # failures (e.g., port already in use) before proceeding with mcp.run().
        _http_ready = threading.Event()

        def _poll_ready(host: str, port: int, event: threading.Event):
            """Poll /health until the server responds or we give up."""
            import time
            import urllib.request
            import urllib.error

            url = f"http://{host}:{port}/health"
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                try:
                    urllib.request.urlopen(url, timeout=0.5)  # noqa: S310
                    event.set()
                    return
                except Exception:
                    time.sleep(0.1)
            # Timeout — leave event unset so main thread can warn

        # Start uvicorn in a background thread for file serving and health checks.
        # daemon=True so the thread exits automatically when the main thread ends.
        http_thread = threading.Thread(
            target=uvicorn.run,
            args=(app,),
            kwargs={
                "host": args.host,
                "port": args.port,
                "log_config": None,
                "access_log": False,  # Keep stderr clean for stdio
            },
            daemon=True,
            name="RedmineHTTPBackgroundThread",
        )
        http_thread.start()

        # Start a lightweight poller that sets _http_ready once /health responds
        poll_thread = threading.Thread(
            target=_poll_ready,
            args=(args.host, args.port, _http_ready),
            daemon=True,
            name="RedmineHTTPReadyPoller",
        )
        poll_thread.start()

        _STARTUP_TIMEOUT = 5.0
        if _http_ready.wait(timeout=_STARTUP_TIMEOUT):
            logger.info(
                "HTTP background server ready on %s:%d (file serving & health)",
                args.host,
                args.port,
            )
        else:
            logger.warning(
                "HTTP background server did not become ready within %.0fs "
                "(port %d may already be in use). "
                "File serving may be unavailable — continuing with stdio MCP.",
                _STARTUP_TIMEOUT,
                args.port,
            )

        # Run MCP on stdio (blocking)
        mcp.run()
    else:
        logger.info("Starting in HTTP mode (MCP and files via HTTP)")
        # Run with our app directly so custom routes (well-known endpoints) are served
        uvicorn.run(app, host=args.host, port=args.port, log_config=None)


if __name__ == "__main__":
    main()
