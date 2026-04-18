"""Workflow contract resource helpers."""

from __future__ import annotations

import os
from typing import Any, Dict, List

_DEFAULT_WORKFLOW_CONTRACT_SAMPLE_LIMIT = 25
_MAX_WORKFLOW_CONTRACT_SAMPLE_LIMIT = 100


def resolve_workflow_contract_sample_limit() -> int:
    """Resolve workflow contract sample size from env, clamped to safe bounds."""
    raw = os.getenv(
        "REDMINE_WORKFLOW_CONTRACT_SAMPLE_LIMIT",
        str(_DEFAULT_WORKFLOW_CONTRACT_SAMPLE_LIMIT),
    ).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_WORKFLOW_CONTRACT_SAMPLE_LIMIT
    if parsed <= 0:
        return 1
    return min(parsed, _MAX_WORKFLOW_CONTRACT_SAMPLE_LIMIT)


def build_transition_matrix(workflow_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize workflow snapshot data into compact transition maps."""
    transition_rows = workflow_data.get("workflow_by_current_status", [])
    by_from_status_id: Dict[str, Any] = {}
    by_from_status_name: Dict[str, Any] = {}

    for row in transition_rows:
        current = row.get("current_status") or {}
        current_id = current.get("id")
        current_name = current.get("name")
        allowed_statuses: List[Dict[str, Any]] = row.get("allowed_statuses", [])

        allowed_ids = [status.get("id") for status in allowed_statuses]
        allowed_names = [status.get("name") for status in allowed_statuses]

        key_id = str(current_id) if current_id is not None else "unknown"
        by_from_status_id[key_id] = {
            "current_status": current,
            "allowed_status_ids": allowed_ids,
            "allowed_status_names": allowed_names,
            "allowed_statuses": allowed_statuses,
        }

        if current_name:
            by_from_status_name[str(current_name)] = allowed_names

    return {
        "by_from_status_id": by_from_status_id,
        "by_from_status_name": by_from_status_name,
    }
