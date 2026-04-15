"""Serializer helpers split from serialization module."""

from typing import Any, Dict

from .content import wrap_insecure_content


def _wiki_page_to_dict(
    wiki_page: Any, include_attachments: bool = True
) -> Dict[str, Any]:
    """Convert a wiki page object to a dictionary.

    Args:
        wiki_page: Redmine wiki page object
        include_attachments: Whether to include attachment metadata

    Returns:
        Dictionary with wiki page data
    """
    result: Dict[str, Any] = {
        "title": wiki_page.title,
        "text": wrap_insecure_content(wiki_page.text),
        "version": wiki_page.version,
    }

    # Add optional timestamp fields
    if hasattr(wiki_page, "created_on"):
        result["created_on"] = (
            str(wiki_page.created_on) if wiki_page.created_on else None
        )
    else:
        result["created_on"] = None

    if hasattr(wiki_page, "updated_on"):
        result["updated_on"] = (
            str(wiki_page.updated_on) if wiki_page.updated_on else None
        )
    else:
        result["updated_on"] = None

    # Add author info
    if hasattr(wiki_page, "author"):
        result["author"] = {
            "id": wiki_page.author.id,
            "name": wiki_page.author.name,
        }

    # Add project info
    if hasattr(wiki_page, "project"):
        result["project"] = {
            "id": wiki_page.project.id,
            "name": wiki_page.project.name,
        }

    # Process attachments if requested
    if include_attachments and hasattr(wiki_page, "attachments"):
        result["attachments"] = []
        for attachment in wiki_page.attachments:
            att_dict = {
                "id": attachment.id,
                "filename": attachment.filename,
                "filesize": attachment.filesize,
                "content_type": attachment.content_type,
                "description": getattr(attachment, "description", ""),
                "created_on": (
                    str(attachment.created_on)
                    if hasattr(attachment, "created_on") and attachment.created_on
                    else None
                ),
            }
            result["attachments"].append(att_dict)

    return result
