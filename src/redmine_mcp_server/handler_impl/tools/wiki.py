"""Undecorated wiki tool implementations extracted from redmine_handler."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Mapping, Optional, Union

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


async def get_redmine_wiki_page_impl(
    project_id: Union[str, int],
    wiki_page_title: str,
    version: Optional[int] = None,
    include_attachments: bool = True,
    *,
    get_client: Callable[[], Any],
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    wiki_page_to_dict: Callable[[Any, bool], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Retrieve full wiki page content from Redmine."""
    try:
        await ensure_cleanup_started()

        if version:
            wiki_page = get_client().wiki_page.get(
                wiki_page_title,
                project_id=project_id,
                version=version,
            )
        else:
            wiki_page = get_client().wiki_page.get(
                wiki_page_title,
                project_id=project_id,
            )

        return wiki_page_to_dict(wiki_page, include_attachments)
    except Exception as e:
        return handle_error(
            e,
            f"fetching wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


async def create_redmine_wiki_page_impl(
    project_id: Union[str, int],
    wiki_page_title: str,
    text: str,
    comments: str = "",
    *,
    get_client: Callable[[], Any],
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    is_read_only_mode: Callable[[], bool],
    read_only_error: Mapping[str, Any],
    wiki_page_to_dict: Callable[[Any, bool], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Create a new wiki page in a Redmine project."""
    if is_read_only_mode():
        return dict(read_only_error)

    try:
        await ensure_cleanup_started()
        wiki_page = get_client().wiki_page.create(
            project_id=project_id,
            title=wiki_page_title,
            text=text,
            comments=comments if comments else None,
        )
        return wiki_page_to_dict(wiki_page, True)
    except Exception as e:
        return handle_error(
            e,
            f"creating wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


async def update_redmine_wiki_page_impl(
    project_id: Union[str, int],
    wiki_page_title: str,
    text: str,
    comments: str = "",
    *,
    get_client: Callable[[], Any],
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    is_read_only_mode: Callable[[], bool],
    read_only_error: Mapping[str, Any],
    wiki_page_to_dict: Callable[[Any, bool], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Update an existing wiki page in a Redmine project."""
    if is_read_only_mode():
        return dict(read_only_error)

    try:
        await ensure_cleanup_started()
        get_client().wiki_page.update(
            wiki_page_title,
            project_id=project_id,
            text=text,
            comments=comments if comments else None,
        )
        wiki_page = get_client().wiki_page.get(wiki_page_title, project_id=project_id)
        return wiki_page_to_dict(wiki_page, True)
    except Exception as e:
        return handle_error(
            e,
            f"updating wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )


async def delete_redmine_wiki_page_impl(
    project_id: Union[str, int],
    wiki_page_title: str,
    *,
    get_client: Callable[[], Any],
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    is_read_only_mode: Callable[[], bool],
    read_only_error: Mapping[str, Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Delete a wiki page from a Redmine project."""
    if is_read_only_mode():
        return dict(read_only_error)

    try:
        await ensure_cleanup_started()
        get_client().wiki_page.delete(wiki_page_title, project_id=project_id)
        return {
            "success": True,
            "title": wiki_page_title,
            "message": f"Wiki page '{wiki_page_title}' deleted successfully.",
        }
    except Exception as e:
        return handle_error(
            e,
            f"deleting wiki page '{wiki_page_title}' in project {project_id}",
            {"resource_type": "wiki page", "resource_id": wiki_page_title},
        )
