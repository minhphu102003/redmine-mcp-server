# AGENTS.md - Guide for AI Coding Assistants

This document provides essential context and instructions for AI agents (like Claude, Cursor, or ChatGPT) working on the `redmine-mcp-server` repository.

## Project Overview
`redmine-mcp-server` is a production-ready Model Context Protocol (MCP) server that bridges Redmine project management with AI agents. It is written in Python 3.10+ using FastMCP v3 and FastAPI.

## Core Rules & Processes

### 1. Mandatory Private Skills Check
Before starting any work, you MUST read all skills contained in the `.agents/private/skills/` directory. These skills contain project-specific rules, library research processes (e.g., Context7), and unique workflows that are not documented elsewhere.

### 2. Git Workflow (Python/uv)
Always use the following process for code changes:
1. **Analyze**: Run `git status` and `git diff`.
2. **Branch**: Create a new branch `feat/`, `fix/`, `chore/`, or `refactor/`.
3. **Format**: Run `uv run black .`
4. **Lint**: Run `uv run flake8 .`
5. **Test**: Run `uv run pytest`.
6. **Commit**: Use Conventional Commits.

### 3. MCP Tool Development
When adding or modifying tools:
-   Implement in `src/redmine_mcp_server/redmine_handler.py`.
-   Use the `@mcp.tool()` decorator.
-   Ensure all user-controlled content is wrapped using `wrap_insecure_content()`.
-   Tools must support both Legacy and OAuth2 authentication modes via `_get_redmine_client()`.

## Repository Structure
-   `src/redmine_mcp_server/`: Core logic and tools.
-   `docs/`: Detailed tool reference, setup guides, and troubleshooting.
-   `tests/`: Unit and integration tests (aim for 80%+ coverage).
-   `.agents/`: Private skills and internal workflows.

## Authentication Modes
-   **Legacy**: Single shared credential (API Key/Basic Auth).
-   **OAuth2**: Per-user tokens (requires Redmine 6.1+). This is handled via `RedmineOAuthMiddleware` in `main.py`.

## Security Considerations
-   **Read-Only Mode**: Controlled by `REDMINE_MCP_READ_ONLY`. Respect this guard in all write operations.
-   **SSL/TLS**: Support for custom CAs and mTLS is implemented via environment variables.

---
*Refer to [README.md](README.md) for installation and user-facing documentation.*
