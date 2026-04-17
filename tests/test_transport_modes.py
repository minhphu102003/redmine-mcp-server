"""
Tests for transport modes in main.py.
"""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestTransportModes:
    """Tests for the new transport argument and hybrid mode logic."""

    @patch("redmine_mcp_server.main.uvicorn")
    @patch("redmine_mcp_server.main.argparse.ArgumentParser.parse_known_args")
    def test_main_http_mode(self, mock_parse_args, mock_uvicorn):
        """Test that --transport http runs uvicorn in the main thread."""
        from redmine_mcp_server.main import main, app

        # Mock CLI arguments
        mock_args = MagicMock()
        mock_args.transport = "http"
        mock_args.host = "127.0.0.1"
        mock_args.port = 8000
        mock_parse_args.return_value = (mock_args, [])

        with patch("redmine_mcp_server.main.logger"):
            main()

        # Verify uvicorn.run was called once in the main flow
        mock_uvicorn.run.assert_called_once_with(
            app, host="127.0.0.1", port=8000, log_config=None
        )

    @patch("redmine_mcp_server.main.mcp")
    @patch("redmine_mcp_server.main.uvicorn")
    @patch("redmine_mcp_server.main.threading.Thread")
    @patch("redmine_mcp_server.main.argparse.ArgumentParser.parse_known_args")
    def test_main_stdio_mode(
        self, mock_parse_args, mock_thread, mock_uvicorn, mock_mcp
    ):
        """Test that --transport stdio starts uvicorn in a thread and runs mcp.run()."""
        from redmine_mcp_server.main import main, app

        # Mock CLI arguments
        mock_args = MagicMock()
        mock_args.transport = "stdio"
        mock_args.host = "127.0.0.1"
        mock_args.port = 8000
        mock_parse_args.return_value = (mock_args, [])

        # Mock thread instance
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance

        with patch("redmine_mcp_server.main.logger"):
            main()

        # Verify two threads were created: HTTP server + ready-poller
        assert mock_thread.call_count == 2
        call_kwargs = [call[1] for call in mock_thread.call_args_list]

        # First thread: uvicorn HTTP server
        http_kwargs = call_kwargs[0]
        assert http_kwargs["target"] == mock_uvicorn.run
        assert http_kwargs["args"] == (app,)
        assert http_kwargs["kwargs"]["host"] == "127.0.0.1"
        assert http_kwargs["kwargs"]["port"] == 8000
        assert http_kwargs["kwargs"]["access_log"] is False
        assert http_kwargs["daemon"] is True
        assert http_kwargs["name"] == "RedmineHTTPBackgroundThread"

        # Second thread: health-endpoint poller
        poll_kwargs = call_kwargs[1]
        assert poll_kwargs["daemon"] is True
        assert poll_kwargs["name"] == "RedmineHTTPReadyPoller"

        # Verify both threads were started
        assert mock_thread_instance.start.call_count == 2

        # Verify mcp.run (stdio) was called
        mock_mcp.run.assert_called_once()
