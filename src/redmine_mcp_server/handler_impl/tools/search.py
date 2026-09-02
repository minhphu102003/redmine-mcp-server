"""Undecorated cross-resource search tool implementation.

Originally lived in the now-removed analytics.py module alongside the
removed reporting tools (generate_scrum_report, export_weekly_report_*,
summarize_project_status). Kept here as a leaf because the search tool
itself has no workflow / reporting coupling and is registered as a
standalone MCP tool.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional, Type

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


async def search_entire_redmine_impl(
    query: str,
    resources: Optional[List[str]] = None,
    limit: int = 100,
    offset: int = 0,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    resource_to_dict: Callable[[Any, str], Dict[str, Any]],
    handle_error: HandleErrorFn,
    version_mismatch_error: Type[Exception],
) -> Dict[str, Any]:
    """Search issues and wiki pages across the Redmine instance."""
    try:
        await ensure_cleanup_started()

        allowed_types = ["issues", "wiki_pages"]
        if resources:
            resources = [
                resource for resource in resources if resource in allowed_types
            ]
            if not resources:
                resources = allowed_types
        else:
            resources = allowed_types

        limit = min(limit, 100)
        if limit <= 0:
            limit = 100

        search_options = {
            "resources": resources,
            "limit": limit,
            "offset": offset,
        }
        client = get_client()

        def _search_and_serialize() -> Dict[str, Any]:
            categorized_results = client.search(query, **search_options)
            if not categorized_results:
                return {
                    "results": [],
                    "results_by_type": {},
                    "total_count": 0,
                    "query": query,
                }

            all_results = []
            results_by_type: Dict[str, int] = {}
            for resource_type, resource_set in categorized_results.items():
                if resource_type == "unknown":
                    continue
                if resource_type not in allowed_types:
                    continue

                if hasattr(resource_set, "__iter__"):
                    count = 0
                    for resource in resource_set:
                        all_results.append(resource_to_dict(resource, resource_type))
                        count += 1
                    if count > 0:
                        results_by_type[resource_type] = count

            return {
                "results": all_results,
                "results_by_type": results_by_type,
                "total_count": len(all_results),
                "query": query,
            }

        return await asyncio.to_thread(_search_and_serialize)
    except version_mismatch_error:
        return {"error": "Search requires Redmine 3.3.0 or higher."}
    except Exception as e:
        return handle_error(e, f"searching Redmine for '{query}'", None)
