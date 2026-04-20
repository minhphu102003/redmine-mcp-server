"""Issue template resource helpers."""

from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ISSUE_TEMPLATE_RESOURCE_URI = "redmine://issue-template/default"

_ISSUE_TEMPLATE_SECTION_RE = re.compile(r"^\s{0,3}#{2,6}\s+(.+?)\s*$", re.MULTILINE)
_TRACKER_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _resource_templates_dir() -> Path:
    """Resolve resource-template directory from env override or package default."""
    env_dir = os.getenv("REDMINE_RESOURCE_TEMPLATE_DIR", "").strip()
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return (Path(__file__).parent / "templates").resolve()


def _default_issue_template_path() -> Path:
    """Path to packaged default issue template markdown."""
    return _resource_templates_dir() / "issue_description.md"


def _normalize_tracker_key(tracker_name: Optional[str]) -> str:
    """Normalize tracker label into a filesystem/env-safe key."""
    raw = str(tracker_name or "").strip().lower()
    if not raw:
        return ""
    return _TRACKER_SLUG_RE.sub("_", raw).strip("_")


def _tracker_template_path(tracker_name: Optional[str]) -> Optional[Path]:
    """Resolve tracker-specific template path if it exists."""
    tracker_key = _normalize_tracker_key(tracker_name)
    if not tracker_key:
        return None
    return _resource_templates_dir() / f"issue_description_{tracker_key}.md"


def load_issue_description_template(tracker_name: Optional[str] = None) -> str:
    """Load issue description template from env override or template file."""
    tracker_key = _normalize_tracker_key(tracker_name)

    by_tracker_inline_raw = os.getenv(
        "REDMINE_ISSUE_DESCRIPTION_TEMPLATE_BY_TRACKER", ""
    ).strip()
    if by_tracker_inline_raw and tracker_key:
        try:
            by_tracker_inline = json.loads(by_tracker_inline_raw)
            if isinstance(by_tracker_inline, dict):
                inline_tracker_template = str(
                    by_tracker_inline.get(tracker_key, "")
                ).strip()
                if inline_tracker_template:
                    return inline_tracker_template
        except json.JSONDecodeError:
            pass

    inline = os.getenv("REDMINE_ISSUE_DESCRIPTION_TEMPLATE", "").strip()
    if inline:
        return inline

    tracker_specific = _tracker_template_path(tracker_name)
    if tracker_specific is not None and tracker_specific.exists():
        try:
            return tracker_specific.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    custom_file = os.getenv("REDMINE_ISSUE_DESCRIPTION_TEMPLATE_FILE", "").strip()
    if custom_file:
        template_path = Path(custom_file).expanduser().resolve()
    else:
        template_path = _default_issue_template_path()

    try:
        return template_path.read_text(encoding="utf-8").strip()
    except OSError:
        return (
            "## Mục tiêu\n"
            "- Nêu mục tiêu/ngữ cảnh nghiệp vụ.\n\n"
            "## Hiện trạng\n"
            "- Mô tả hành vi hiện tại hoặc vấn đề đang gặp.\n\n"
            "## Kỳ vọng\n"
            "- Mô tả kết quả mong muốn.\n\n"
            "## Tiêu chí chấp nhận\n"
            "- [ ] Điều kiện chấp nhận 1\n"
            "- [ ] Điều kiện chấp nhận 2\n"
        )


def is_issue_template_enforced() -> bool:
    """Return whether issue description template validation is enabled."""
    return os.getenv("REDMINE_ENFORCE_ISSUE_TEMPLATE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def extract_template_sections(template: str) -> List[str]:
    """Extract markdown heading names from a template body."""
    sections: List[str] = []
    for match in _ISSUE_TEMPLATE_SECTION_RE.findall(template or ""):
        cleaned = match.strip()
        if cleaned:
            sections.append(cleaned)
    return sections


def required_issue_template_sections(tracker_name: Optional[str] = None) -> List[str]:
    """Return required sections from env override or template headings."""
    tracker_key = _normalize_tracker_key(tracker_name)
    by_tracker_raw = os.getenv(
        "REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS_BY_TRACKER", ""
    ).strip()
    if by_tracker_raw and tracker_key:
        try:
            by_tracker_sections = json.loads(by_tracker_raw)
            if isinstance(by_tracker_sections, dict):
                sections = by_tracker_sections.get(tracker_key)
                if isinstance(sections, str):
                    return [
                        section.strip()
                        for section in sections.split(",")
                        if section.strip()
                    ]
                if isinstance(sections, list):
                    return [
                        str(section).strip()
                        for section in sections
                        if str(section).strip()
                    ]
        except json.JSONDecodeError:
            pass

    raw = os.getenv("REDMINE_ISSUE_TEMPLATE_REQUIRED_SECTIONS", "").strip()
    if raw:
        return [section.strip() for section in raw.split(",") if section.strip()]
    return extract_template_sections(load_issue_description_template(tracker_name))


def missing_template_sections(
    description: str, required_sections: List[str]
) -> List[str]:
    """Detect required sections missing from issue description markdown."""
    if not required_sections:
        return []

    detected_sections = {
        heading.strip().lower()
        for heading in _ISSUE_TEMPLATE_SECTION_RE.findall(description or "")
        if heading.strip()
    }
    return [
        section
        for section in required_sections
        if section.strip().lower() not in detected_sections
    ]


def validate_issue_description_template(
    description: str,
    tracker_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Validate issue description against required template sections."""
    if not is_issue_template_enforced():
        return None

    required_sections = required_issue_template_sections(tracker_name)
    missing_sections = missing_template_sections(description, required_sections)
    if not missing_sections:
        return None

    return {
        "error": (
            "Issue description does not match required template sections. "
            "Please follow the issue template resource before creating issue."
        ),
        "template_resource_uri": ISSUE_TEMPLATE_RESOURCE_URI,
        "tracker": tracker_name,
        "missing_sections": missing_sections,
    }


def build_issue_template_payload() -> Dict[str, Any]:
    """Build issue template resource payload for agent guidance."""
    template_markdown = load_issue_description_template()
    variants: Dict[str, str] = {}
    for tracker in ("bug", "feature"):
        path = _tracker_template_path(tracker)
        if path is not None and path.exists():
            variants[tracker] = load_issue_description_template(tracker)
    return {
        "resource": "issue_creation_template",
        "enforced": is_issue_template_enforced(),
        "required_sections": required_issue_template_sections(),
        "template_markdown": template_markdown,
        "template_variants_by_tracker": variants,
        "usage_note": (
            "When REDMINE_ENFORCE_ISSUE_TEMPLATE=true, create_redmine_issue "
            "rejects descriptions missing required sections."
        ),
    }
