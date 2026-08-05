"""Undecorated issue tool implementations extracted from redmine_handler."""

from __future__ import annotations

import asyncio
import os
import logging
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Type, Union

from redminelib.exceptions import ValidationError

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]
ResolveTrackerNameFn = Callable[[int, Any], Any]


class IssueToDictFn(Protocol):
    """Callable signature for issue serialization helper."""

    def __call__(
        self, issue: Any, include_custom_fields: bool = False
    ) -> Dict[str, Any]: ...


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
    *,
    limit: int,
    offset: int,
    count: int,
    total: Optional[int] = None,
    page_size: Optional[int] = None,
) -> Dict[str, Any]:
    """Build normalized pagination metadata."""
    resolved_page_size = page_size if page_size is not None else limit
    if total is not None:
        has_next = (offset + count) < total
    else:
        has_next = count == resolved_page_size
    info: Dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "count": count,
        "has_next": has_next,
        "has_previous": offset > 0,
        "next_offset": offset + resolved_page_size if has_next else None,
        "previous_offset": (
            max(0, offset - resolved_page_size) if offset > 0 else None
        ),
    }
    if total is not None:
        info["total"] = total
    return info


def _coerce_optional_object_payload(
    payload: Optional[Union[Dict[str, Any], str]],
    payload_name: str,
) -> Dict[str, Any]:
    """Parse optional dict-or-JSON-string payload into a plain dict."""
    if payload is None:
        return {}
    if isinstance(payload, dict):
        parsed = dict(payload)
        if isinstance(parsed.get(payload_name), dict) and len(parsed) == 1:
            return dict(parsed[payload_name])
        return parsed
    if isinstance(payload, str):
        raw = payload.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception as exc:
            raise ValueError(
                f"Invalid {payload_name} payload. "
                "Expected a dict or JSON object string."
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError(
                f"Invalid {payload_name} payload. Parsed value must be an object/dict."
            )
        return dict(parsed)
    raise ValueError(
        f"Invalid {payload_name} payload. Expected a dict or JSON object string."
    )


def _resolve_subtask_batch_limit(default: int = 50) -> int:
    """Resolve subtask batch limit from environment with safe bounds."""
    raw = os.getenv("REDMINE_MCP_SUBTASK_BATCH_LIMIT", str(default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    return min(value, 200)


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
    issue_to_dict: IssueToDictFn,
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
            issue = await asyncio.to_thread(
                client.issue.get, issue_id, include=",".join(includes)
            )
        else:
            issue = await asyncio.to_thread(client.issue.get, issue_id)

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

        fetch_limit = min(limit, 100)
        redmine_filters = {
            "offset": offset,
            "limit": fetch_limit,
            **filters,
        }

        logger.debug("Calling issue.filter with: %s", redmine_filters)
        client = get_client()
        issues_list = await asyncio.to_thread(
            lambda: list(client.issue.filter(**redmine_filters))
        )

        result_issues = [
            issue_to_dict_selective(issue, fields) for issue in issues_list
        ]

        if include_pagination_info:
            total_count: Optional[int] = None
            try:
                total_count = await asyncio.to_thread(
                    lambda: client.issue.filter(**filters, limit=1).total_count
                )
                logger.debug("Got total count from separate query: %s", total_count)
            except Exception as e:
                logger.warning("Could not get total count: %s, omitting total", e)

            return {
                "issues": result_issues,
                "pagination": _pagination_info(
                    limit=limit,
                    offset=offset,
                    count=len(result_issues),
                    total=total_count,
                    page_size=fetch_limit,
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
        results = await asyncio.to_thread(
            get_client().issue.search, query, **search_params
        )
        issues_list = [] if results is None else list(results)
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
    prepare_issue_fields: Callable[
        [int, str, Dict[str, Any]], Awaitable[Optional[Dict[str, Any]]]
    ],
    validate_issue_template: Callable[[str, Optional[str]], Optional[Dict[str, Any]]],
    resolve_tracker_name: ResolveTrackerNameFn,
    get_client: Callable[[], Any],
    issue_to_dict: IssueToDictFn,
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

    policy_error = await prepare_issue_fields(project_id, subject, issue_fields)
    if policy_error is not None:
        return policy_error

    tracker_name: Optional[str] = None
    tracker_id = issue_fields.get("tracker_id")
    if tracker_id is not None:
        try:
            tracker_name = await resolve_tracker_name(project_id, tracker_id)
        except Exception:
            tracker_name = None

    template_error = validate_issue_template(description, tracker_name)
    if template_error is not None:
        return template_error

    issue_fields.pop("project_id", None)
    issue_fields.pop("subject", None)
    issue_fields.pop("description", None)
    issue_fields.pop("extra_fields", None)

    try:
        client = get_client()
        issue = await asyncio.to_thread(
            client.issue.create,
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
            client = get_client()
            issue = await asyncio.to_thread(
                client.issue.create,
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
    issue_to_dict: IssueToDictFn,
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
            statuses = await asyncio.to_thread(get_client().issue_status.all)
            matches = [
                status
                for status in statuses
                if getattr(status, "name", "").lower() == name
            ]
            if len(matches) == 1:
                update_fields["status_id"] = matches[0].id
            elif len(matches) > 1:
                return handle_error(
                    ValueError(
                        f"Ambiguous status name '{name}': "
                        f"multiple statuses match (IDs: "
                        f"{', '.join(str(s.id) for s in matches)})"
                    ),
                    f"updating issue {issue_id}",
                    {"resource_type": "issue", "resource_id": issue_id},
                )
        except Exception as e:
            logger.warning("Error resolving status name '%s': %s", name, e)

    try:
        update_fields = map_named_custom_fields_for_update(issue_id, update_fields)
        client = get_client()
        await asyncio.to_thread(client.issue.update, issue_id, **update_fields)
        updated_issue = await asyncio.to_thread(client.issue.get, issue_id)
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
            issue = await asyncio.to_thread(get_client().issue.get, issue_id)
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
            client = get_client()
            await asyncio.to_thread(client.issue.update, issue_id, **retry_fields)
            updated_issue = await asyncio.to_thread(client.issue.get, issue_id)
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


async def create_redmine_issue_with_subtasks_impl(
    project_id: int,
    parent_subject: str,
    parent_description: str = "",
    parent_fields: Optional[Union[Dict[str, Any], str]] = None,
    parent_extra_fields: Optional[Union[Dict[str, Any], str]] = None,
    subtasks: Optional[List[Dict[str, Any]]] = None,
    stop_on_subtask_error: bool = False,
    *,
    create_issue_fn: Callable[..., Any],
    wrap_content: Callable[[Any], Any],
) -> Dict[str, Any]:
    """Create a parent issue and a batch of subtasks under it."""
    if not str(parent_subject or "").strip():
        return {"error": "parent_subject is required."}

    subtask_items = [] if subtasks is None else subtasks
    if not isinstance(subtask_items, list):
        return {"error": "subtasks must be a list of objects."}
    subtask_batch_limit = _resolve_subtask_batch_limit()

    try:
        parent_payload = _coerce_optional_object_payload(parent_fields, "parent_fields")
        parent_payload.update(
            _coerce_optional_object_payload(parent_extra_fields, "parent_extra_fields")
        )
    except ValueError as exc:
        return {"error": str(exc)}

    parent_issue = await create_issue_fn(
        project_id=project_id,
        subject=parent_subject,
        description=parent_description,
        fields=parent_payload,
        extra_fields=None,
    )
    if not isinstance(parent_issue, dict) or "error" in parent_issue:
        return {
            "error": "Failed to create parent issue.",
            "project_id": project_id,
            "parent_issue": parent_issue,
            "created_subtasks": [],
            "failed_subtasks": [],
        }

    parent_issue_id = parent_issue.get("id")
    if parent_issue_id is None:
        return {
            "error": "Parent issue creation returned no issue id.",
            "project_id": project_id,
            "parent_issue": parent_issue,
            "created_subtasks": [],
            "failed_subtasks": [],
        }

    created_subtasks: List[Dict[str, Any]] = []
    failed_subtasks: List[Dict[str, Any]] = []

    stop_processing = False
    for batch_start in range(0, len(subtask_items), subtask_batch_limit):
        batch = subtask_items[batch_start : batch_start + subtask_batch_limit]
        for offset, subtask in enumerate(batch):
            index = batch_start + offset
            if not isinstance(subtask, dict):
                failed_subtasks.append(
                    {
                        "index": index,
                        "subject": None,
                        "error": "Each subtask must be an object.",
                    }
                )
                if stop_on_subtask_error:
                    stop_processing = True
                    break
                continue

            subtask_subject = str(subtask.get("subject", "")).strip()
            if not subtask_subject:
                failed_subtasks.append(
                    {
                        "index": index,
                        "subject": None,
                        "error": "subtask.subject is required.",
                    }
                )
                if stop_on_subtask_error:
                    stop_processing = True
                    break
                continue

            try:
                subtask_payload = _coerce_optional_object_payload(
                    subtask.get("fields"), "subtask.fields"
                )
                subtask_payload.update(
                    _coerce_optional_object_payload(
                        subtask.get("extra_fields"), "subtask.extra_fields"
                    )
                )
            except ValueError as exc:
                failed_subtasks.append(
                    {
                        "index": index,
                        "subject": wrap_content(subtask_subject),
                        "error": str(exc),
                    }
                )
                if stop_on_subtask_error:
                    stop_processing = True
                    break
                continue

            subtask_payload["parent_issue_id"] = parent_issue_id
            subtask_description = str(subtask.get("description", ""))

            subtask_issue = await create_issue_fn(
                project_id=project_id,
                subject=subtask_subject,
                description=subtask_description,
                fields=subtask_payload,
                extra_fields=None,
            )
            if not isinstance(subtask_issue, dict) or "error" in subtask_issue:
                failed_subtasks.append(
                    {
                        "index": index,
                        "subject": wrap_content(subtask_subject),
                        "error": (
                            subtask_issue.get("error", "Unknown subtask creation error")
                            if isinstance(subtask_issue, dict)
                            else "Unknown subtask creation error"
                        ),
                        "result": subtask_issue,
                    }
                )
                if stop_on_subtask_error:
                    stop_processing = True
                    break
                continue

            created_subtasks.append(subtask_issue)

        if stop_processing:
            break

    return {
        "project_id": project_id,
        "parent_issue": parent_issue,
        "created_subtasks": created_subtasks,
        "failed_subtasks": failed_subtasks,
        "summary": {
            "requested_subtasks": len(subtask_items),
            "created_subtasks": len(created_subtasks),
            "failed_subtasks": len(failed_subtasks),
            "stop_on_subtask_error": stop_on_subtask_error,
            "subtask_batch_size": subtask_batch_limit,
            "subtask_batch_count": (
                (len(subtask_items) + subtask_batch_limit - 1) // subtask_batch_limit
                if subtask_items
                else 0
            ),
            "stopped_early": stop_processing,
        },
    }
