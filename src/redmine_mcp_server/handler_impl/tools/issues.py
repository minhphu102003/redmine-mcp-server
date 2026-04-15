"""Undecorated issue tool implementations extracted from redmine_handler."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union

from redminelib.exceptions import ValidationError

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]

logger = logging.getLogger(__name__)


def _normalize_limit(limit: Optional[int], default: int = 25) -> int:
    """Normalize and clamp limit value."""
    if limit is None:
        return default

    if not isinstance(limit, int):
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            logger.warning(
                "Invalid limit type %s, using default %s", type(limit), default
            )
            return default

    if limit <= 0:
        return limit

    if limit > 1000:
        logger.warning("Limit %s exceeds maximum 1000, capped to 1000", limit)
        return 1000

    return limit


def _normalize_offset(offset: int) -> int:
    """Normalize offset value."""
    if not isinstance(offset, int) or offset < 0:
        logger.warning("Invalid offset %s, reset to 0", offset)
        return 0
    return offset


def _empty_issues_response(
    *, limit: int, offset: int, include_pagination_info: bool, include_total: bool
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Return empty issues payload preserving list/dict response modes."""
    if not include_pagination_info:
        return []

    pagination: Dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "count": 0,
        "has_next": False,
        "has_previous": False,
        "next_offset": None,
        "previous_offset": None,
    }
    if include_total:
        pagination["total"] = 0

    return {"issues": [], "pagination": pagination}


def _pagination_info(
    *, limit: int, offset: int, count: int, total: Optional[int] = None
) -> Dict[str, Any]:
    """Build normalized pagination metadata."""
    has_next = count == limit
    info: Dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "count": count,
        "has_next": has_next,
        "has_previous": offset > 0,
        "next_offset": offset + limit if has_next else None,
        "previous_offset": max(0, offset - limit) if offset > 0 else None,
    }
    if total is not None:
        info["total"] = total
    return info


async def get_redmine_issue_impl(
    issue_id: int,
    include_journals: bool = True,
    include_attachments: bool = True,
    include_custom_fields: bool = True,
    journal_limit: Optional[int] = None,
    journal_offset: int = 0,
    include_watchers: bool = False,
    include_relations: bool = False,
    include_children: bool = False,
    *,
    ensure_cleanup_started: Callable[[], Any],
    get_client: Callable[[], Any],
    issue_to_dict: Callable[[Any, bool], Dict[str, Any]],
    journals_to_list: Callable[[Any], List[Dict[str, Any]]],
    attachments_to_list: Callable[[Any], List[Dict[str, Any]]],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Retrieve a specific Redmine issue by ID."""
    await ensure_cleanup_started()

    try:
        includes = []
        if include_journals:
            includes.append("journals")
        if include_attachments:
            includes.append("attachments")
        if include_watchers:
            includes.append("watchers")
        if include_relations:
            includes.append("relations")
        if include_children:
            includes.append("children")

        client = get_client()
        if includes:
            issue = client.issue.get(issue_id, include=",".join(includes))
        else:
            issue = client.issue.get(issue_id)

        result = issue_to_dict(issue, include_custom_fields=include_custom_fields)
        if include_journals:
            all_journals = journals_to_list(issue)
            if journal_limit is not None:
                total = len(all_journals)
                offset = journal_offset
                paginated = all_journals[offset : offset + journal_limit]
                result["journals"] = paginated
                result["journal_pagination"] = {
                    "total": total,
                    "offset": offset,
                    "limit": journal_limit,
                    "count": len(paginated),
                    "has_more": (offset + journal_limit) < total,
                }
            else:
                result["journals"] = all_journals

        if include_attachments:
            result["attachments"] = attachments_to_list(issue)

        if include_watchers:
            raw = getattr(issue, "watchers", None) or []
            result["watchers"] = [{"id": w.id, "name": w.name} for w in raw]

        if include_relations:
            raw = getattr(issue, "relations", None) or []
            result["relations"] = [
                {
                    "id": r.id,
                    "issue_id": r.issue_id,
                    "issue_to_id": r.issue_to_id,
                    "relation_type": r.relation_type,
                }
                for r in raw
            ]

        if include_children:
            raw = getattr(issue, "children", None) or []
            result["children"] = [
                {
                    "id": c.id,
                    "subject": getattr(c, "subject", ""),
                    "tracker": (
                        {"id": c.tracker.id, "name": c.tracker.name}
                        if getattr(c, "tracker", None)
                        else None
                    ),
                }
                for c in raw
            ]

        return result
    except Exception as e:
        return handle_error(
            e,
            f"fetching issue {issue_id}",
            {"resource_type": "issue", "resource_id": issue_id},
        )


async def list_redmine_issues_impl(
    project_id: Optional[Union[int, str]] = None,
    status_id: Optional[int] = None,
    tracker_id: Optional[int] = None,
    assigned_to_id: Optional[Union[int, str]] = None,
    priority_id: Optional[int] = None,
    fixed_version_id: Optional[int] = None,
    sort: Optional[str] = None,
    limit: Optional[int] = 25,
    offset: int = 0,
    include_pagination_info: bool = False,
    fields: Optional[List[str]] = None,
    filters: Optional[Dict[str, Any]] = None,
    *,
    ensure_cleanup_started: Callable[[], Any],
    get_client: Callable[[], Any],
    issue_to_dict_selective: Callable[[Any, Optional[List[str]]], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """List Redmine issues with flexible filtering and pagination support."""
    await ensure_cleanup_started()

    try:
        redmine_api_filters: Dict[str, Any] = {}
        if project_id is not None:
            redmine_api_filters["project_id"] = project_id
        if status_id is not None:
            redmine_api_filters["status_id"] = status_id
        if tracker_id is not None:
            redmine_api_filters["tracker_id"] = tracker_id
        if assigned_to_id is not None:
            redmine_api_filters["assigned_to_id"] = assigned_to_id
        if priority_id is not None:
            redmine_api_filters["priority_id"] = priority_id
        if fixed_version_id is not None:
            redmine_api_filters["fixed_version_id"] = fixed_version_id
        if sort is not None:
            redmine_api_filters["sort"] = sort
        if filters:
            redmine_api_filters.update(filters)
        filters = redmine_api_filters

        limit = _normalize_limit(limit)
        offset = _normalize_offset(offset)

        if limit <= 0:
            return _empty_issues_response(
                limit=limit,
                offset=offset,
                include_pagination_info=include_pagination_info,
                include_total=True,
            )

        filter_keys = list(filters.keys()) if filters else []
        logger.info(
            "Pagination request: limit=%s, offset=%s, filters=%s",
            limit,
            offset,
            filter_keys,
        )

        redmine_filters = {
            "offset": offset,
            "limit": min(limit, 100),
            **filters,
        }

        logger.debug("Calling issue.filter with: %s", redmine_filters)
        client = get_client()
        issues = client.issue.filter(**redmine_filters)
        issues_list = list(issues)

        result_issues = [
            issue_to_dict_selective(issue, fields) for issue in issues_list
        ]

        if include_pagination_info:
            total_count: int
            try:
                count_query = client.issue.filter(**filters)
                list(count_query)
                total_count = count_query.total_count
                logger.debug("Got total count from separate query: %s", total_count)
            except Exception as e:
                logger.warning(
                    "Could not get total count: %s, using estimated value", e
                )
                if len(result_issues) == limit:
                    total_count = offset + len(result_issues) + 1
                else:
                    total_count = offset + len(result_issues)

            return {
                "issues": result_issues,
                "pagination": _pagination_info(
                    limit=limit,
                    offset=offset,
                    count=len(result_issues),
                    total=total_count,
                ),
            }

        return result_issues
    except Exception as e:
        return [handle_error(e, "listing issues", None)]


async def search_redmine_issues_impl(
    query: str,
    limit: Optional[int] = 25,
    offset: int = 0,
    include_pagination_info: bool = False,
    fields: Optional[List[str]] = None,
    scope: Optional[str] = None,
    open_issues: bool = False,
    options: Optional[Dict[str, Any]] = None,
    *,
    get_client: Callable[[], Any],
    issue_to_dict_selective: Callable[[Any, Optional[List[str]]], Dict[str, Any]],
    handle_error: HandleErrorFn,
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Search Redmine issues matching a query string with pagination support."""
    try:
        search_options: Dict[str, Any] = {}
        if scope is not None:
            search_options["scope"] = scope
        if open_issues:
            search_options["open_issues"] = open_issues
        if options:
            search_options.update(options)

        limit = _normalize_limit(limit)
        offset = _normalize_offset(offset)
        if limit <= 0:
            return _empty_issues_response(
                limit=limit,
                offset=offset,
                include_pagination_info=include_pagination_info,
                include_total=False,
            )

        option_keys = list(search_options.keys()) if search_options else []
        logger.info(
            "Search request: query='%s', limit=%s, offset=%s, options=%s",
            query,
            limit,
            offset,
            option_keys,
        )

        search_params = {"offset": offset, "limit": limit, **search_options}

        logger.debug("Calling issue.search with: %s", search_params)
        results = get_client().issue.search(query, **search_params)
        if results is None:
            results = []

        issues_list = list(results)
        result_issues = [
            issue_to_dict_selective(issue, fields) for issue in issues_list
        ]

        if include_pagination_info:
            return {
                "issues": result_issues,
                "pagination": _pagination_info(
                    limit=limit,
                    offset=offset,
                    count=len(result_issues),
                ),
            }

        return result_issues
    except Exception as e:
        return handle_error(e, f"searching issues with query '{query}'", None)


async def create_redmine_issue_impl(
    project_id: int,
    subject: str,
    description: str = "",
    fields: Optional[Union[Dict[str, Any], str]] = None,
    extra_fields: Optional[Union[Dict[str, Any], str]] = None,
    *,
    is_read_only_mode: Callable[[], bool],
    read_only_error: Dict[str, Any],
    parse_create_issue_fields: Callable[
        [Optional[Union[Dict[str, Any], str]]], Dict[str, Any]
    ],
    parse_optional_object_payload: Callable[
        [Optional[Union[Dict[str, Any], str]], str], Dict[str, Any]
    ],
    get_client: Callable[[], Any],
    issue_to_dict: Callable[[Any], Dict[str, Any]],
    is_required_custom_field_autofill_enabled: Callable[[], bool],
    extract_missing_required_field_names: Callable[[str], List[str]],
    augment_fields_with_required_custom_fields: Callable[
        [int, Dict[str, Any], List[str]], Dict[str, Any]
    ],
    handle_error: HandleErrorFn,
    validation_error: Type[Exception] = ValidationError,
) -> Dict[str, Any]:
    """Create a new issue in Redmine."""
    if is_read_only_mode():
        return dict(read_only_error)

    try:
        issue_fields = parse_create_issue_fields(fields)
    except ValueError as e:
        return {"error": str(e)}

    try:
        parsed_extra_fields = parse_optional_object_payload(
            extra_fields, "extra_fields"
        )
    except ValueError as e:
        return {"error": str(e)}

    if parsed_extra_fields:
        issue_fields.update(parsed_extra_fields)

    issue_fields.pop("project_id", None)
    issue_fields.pop("subject", None)
    issue_fields.pop("description", None)
    issue_fields.pop("extra_fields", None)

    try:
        issue = get_client().issue.create(
            project_id=project_id,
            subject=subject,
            description=description,
            **issue_fields,
        )
        return issue_to_dict(issue)
    except validation_error as e:
        if not is_required_custom_field_autofill_enabled():
            return handle_error(e, f"creating issue in project {project_id}", None)

        missing_names = extract_missing_required_field_names(str(e))
        if not missing_names:
            return handle_error(e, f"creating issue in project {project_id}", None)

        try:
            retry_fields = augment_fields_with_required_custom_fields(
                project_id,
                issue_fields,
                missing_names,
            )
            if retry_fields == issue_fields:
                return handle_error(e, f"creating issue in project {project_id}", None)

            logger.info(
                "Retrying issue creation with auto-filled custom fields: %s",
                missing_names,
            )
            issue = get_client().issue.create(
                project_id=project_id,
                subject=subject,
                description=description,
                **retry_fields,
            )
            return issue_to_dict(issue)
        except Exception as retry_error:
            return handle_error(
                retry_error, f"creating issue in project {project_id}", None
            )
    except Exception as e:
        return handle_error(e, f"creating issue in project {project_id}", None)


async def update_redmine_issue_impl(
    issue_id: int,
    fields: Dict[str, Any],
    *,
    is_read_only_mode: Callable[[], bool],
    read_only_error: Dict[str, Any],
    get_client: Callable[[], Any],
    map_named_custom_fields_for_update: Callable[[int, Dict[str, Any]], Dict[str, Any]],
    issue_to_dict: Callable[[Any, bool], Dict[str, Any]],
    is_required_custom_field_autofill_enabled: Callable[[], bool],
    extract_missing_required_field_names: Callable[[str], List[str]],
    augment_fields_with_required_custom_fields: Callable[
        [int, Dict[str, Any], List[str]], Dict[str, Any]
    ],
    handle_error: HandleErrorFn,
    validation_error: Type[Exception] = ValidationError,
) -> Dict[str, Any]:
    """Update an existing Redmine issue."""
    if is_read_only_mode():
        return dict(read_only_error)

    update_fields = dict(fields)

    if "status_name" in update_fields and "status_id" not in update_fields:
        name = str(update_fields.pop("status_name")).lower()
        try:
            statuses = get_client().issue_status.all()
            for status in statuses:
                if getattr(status, "name", "").lower() == name:
                    update_fields["status_id"] = status.id
                    break
        except Exception as e:
            logger.warning("Error resolving status name '%s': %s", name, e)

    try:
        update_fields = map_named_custom_fields_for_update(issue_id, update_fields)
        client = get_client()
        client.issue.update(issue_id, **update_fields)
        updated_issue = client.issue.get(issue_id)
        return issue_to_dict(updated_issue, include_custom_fields=True)
    except validation_error as e:
        if not is_required_custom_field_autofill_enabled():
            return handle_error(
                e,
                f"updating issue {issue_id}",
                {"resource_type": "issue", "resource_id": issue_id},
            )

        missing_names = extract_missing_required_field_names(str(e))
        if not missing_names:
            return handle_error(
                e,
                f"updating issue {issue_id}",
                {"resource_type": "issue", "resource_id": issue_id},
            )

        try:
            issue = get_client().issue.get(issue_id)
            project = getattr(issue, "project", None)
            project_id = getattr(project, "id", None)
            if project_id is None:
                return handle_error(
                    e,
                    f"updating issue {issue_id}",
                    {"resource_type": "issue", "resource_id": issue_id},
                )

            retry_fields = augment_fields_with_required_custom_fields(
                project_id,
                update_fields,
                missing_names,
            )

            if retry_fields == update_fields:
                return handle_error(
                    e,
                    f"updating issue {issue_id}",
                    {"resource_type": "issue", "resource_id": issue_id},
                )

            logger.info(
                "Retrying issue update with auto-filled custom fields: %s",
                missing_names,
            )
            get_client().issue.update(issue_id, **retry_fields)
            updated_issue = get_client().issue.get(issue_id)
            return issue_to_dict(updated_issue, include_custom_fields=True)
        except Exception as retry_error:
            return handle_error(
                retry_error,
                f"updating issue {issue_id}",
                {"resource_type": "issue", "resource_id": issue_id},
            )
    except Exception as e:
        return handle_error(
            e,
            f"updating issue {issue_id}",
            {"resource_type": "issue", "resource_id": issue_id},
        )
