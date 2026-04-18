"""Shared resource helpers."""

from __future__ import annotations

from typing import Optional, Union


def parse_tracker_id(tracker_id: Optional[Union[str, int]]) -> Optional[int]:
    """Parse optional tracker id safely."""
    if tracker_id is None:
        return None
    return int(tracker_id)
