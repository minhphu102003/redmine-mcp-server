"""
Tests for HTTP endpoints in the MCP server.

Tests cover:
- /health endpoint
"""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient


@pytest.mark.unit
class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    @pytest.fixture
    def app(self):
        """Get the Starlette app for testing."""
        from redmine_mcp_server.main import app

        return app

    @pytest.mark.asyncio
    async def test_health_check_returns_ok(self, app):
        """Test that /health returns 200 with status ok."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "redmine_mcp_tools"
