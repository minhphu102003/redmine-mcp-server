"""Top-level package for redmine_mcp_server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("redmine-mcp-server")
except PackageNotFoundError:
    __version__ = "dev"

__all__ = ["__version__"]
