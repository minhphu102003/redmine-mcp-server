import pytest
from unittest.mock import MagicMock, patch
from starlette.requests import Request
from starlette.responses import JSONResponse
from redmine_mcp_server.dynamic_auth_middleware import (
    RedmineDynamicAuthMiddleware,
    current_redmine_url,
    current_redmine_key,
)
from redmine_mcp_server.redmine_handler import _get_redmine_client


@pytest.mark.asyncio
async def test_middleware_extracts_headers():
    """Test that middleware correctly extracts URL and API Key from headers."""
    middleware = RedmineDynamicAuthMiddleware(MagicMock())

    headers = {
        "X-Redmine-URL": "https://test-redmine.com",
        "X-Redmine-API-Key": "test-api-key",
    }
    request = MagicMock(spec=Request)
    request.headers = headers
    request.url.path = "/mcp"

    async def call_next(req):
        assert current_redmine_url.get() == "https://test-redmine.com"
        assert current_redmine_key.get() == "test-api-key"
        return JSONResponse({"status": "ok"})

    await middleware.dispatch(request, call_next)

    # Verify cleanup
    assert current_redmine_url.get() is None
    assert current_redmine_key.get() is None


@pytest.mark.asyncio
async def test_middleware_authorization_fallback():
    """Test that middleware falls back to Authorization header for API Key."""
    middleware = RedmineDynamicAuthMiddleware(MagicMock())

    headers = {
        "X-Redmine-URL": "https://test-redmine.com",
        "Authorization": "Bearer key-from-auth-header",
    }
    request = MagicMock(spec=Request)
    request.headers = headers
    request.url.path = "/mcp"

    async def call_next(req):
        assert current_redmine_url.get() == "https://test-redmine.com"
        assert current_redmine_key.get() == "key-from-auth-header"
        return JSONResponse({"status": "ok"})

    await middleware.dispatch(request, call_next)


@pytest.mark.asyncio
async def test_middleware_missing_url():
    """Test that middleware returns 401 if URL is missing."""
    middleware = RedmineDynamicAuthMiddleware(MagicMock())

    headers = {"X-Redmine-API-Key": "test-api-key"}
    request = MagicMock(spec=Request)
    request.headers = headers
    request.url.path = "/mcp"

    response = await middleware.dispatch(request, MagicMock())
    assert response.status_code == 401
    assert b"X-Redmine-URL header is required" in response.body


@pytest.mark.unit
def test_get_redmine_client_uses_dynamic_config():
    """Test that _get_redmine_client prioritizes dynamic context configuration."""

    test_url = "https://dynamic-redmine.com"
    test_key = "dynamic-key-123"

    # Set context manually
    token_url = current_redmine_url.set(test_url)
    token_key = current_redmine_key.set(test_key)

    try:
        with patch("redmine_mcp_server.redmine_handler.Redmine") as MockRedmine:
            _get_redmine_client()

            # Verify Redmine was instantiated with dynamic values
            MockRedmine.assert_called_once()
            args, kwargs = MockRedmine.call_args
            assert args[0] == test_url
            assert kwargs["key"] == test_key
    finally:
        current_redmine_url.reset(token_url)
        current_redmine_key.reset(token_key)


@pytest.mark.unit
def test_get_redmine_client_fallback_to_legacy():
    """Test that _get_redmine_client falls back to legacy config if context is empty."""

    # Ensure context is empty
    assert current_redmine_url.get() is None

    with patch(
        "redmine_mcp_server.redmine_handler.REDMINE_URL", "https://default-redmine.com"
    ):
        with patch("redmine_mcp_server.redmine_handler.REDMINE_API_KEY", "default-key"):
            with patch("redmine_mcp_server.redmine_handler.Redmine") as MockRedmine:
                _get_redmine_client()

                # Verify fallback to global settings
                args, kwargs = MockRedmine.call_args
                assert args[0] == "https://default-redmine.com"
                assert kwargs["key"] == "default-key"
