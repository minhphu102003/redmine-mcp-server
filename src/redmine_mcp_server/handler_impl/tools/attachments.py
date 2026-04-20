"""Undecorated attachment tool implementations extracted from redmine_handler."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Optional
from urllib.parse import urlparse

from ...attachment_manager import AttachmentFileManager

logger = logging.getLogger(__name__)

HandleErrorFn = Callable[
    [Exception, str, Optional[dict[str, Any]]],
    dict[str, Any],
]


def _sanitize_attachment_filename(raw_name: Any, fallback_name: str) -> str:
    """Normalize untrusted attachment filename to a safe basename."""
    candidate = str(raw_name or "").strip().replace("\\", "/")
    candidate = Path(candidate).name
    candidate = "".join(ch for ch in candidate if ch.isprintable() and ch not in "\r\n")
    if candidate in {"", ".", ".."}:
        return fallback_name
    # Keep file names short for filesystem and header safety.
    return candidate[:255]


def _build_download_url(file_id: str) -> str:
    """Build public download URL using a trusted base URL when configured."""
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if public_base_url:
        parsed = urlparse(public_base_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{public_base_url}/files/{file_id}"

    public_host = os.getenv("PUBLIC_HOST", os.getenv("SERVER_HOST", "localhost"))
    public_port = os.getenv("PUBLIC_PORT", os.getenv("SERVER_PORT", "8000"))
    public_scheme = os.getenv("PUBLIC_SCHEME", "https").strip().lower()
    if public_scheme not in {"http", "https"}:
        public_scheme = "https"

    if public_host == "0.0.0.0":
        public_host = "localhost"

    return f"{public_scheme}://{public_host}:{public_port}/files/{file_id}"


async def get_redmine_attachment_download_url_impl(
    attachment_id: int,
    *,
    ensure_cleanup_started: Callable[[], Awaitable[Any]],
    get_client: Callable[[], Any],
    handle_error: HandleErrorFn,
) -> Dict[str, Any]:
    """Download an attachment and build a time-limited local download URL."""
    await ensure_cleanup_started()

    try:
        attachment = get_client().attachment.get(attachment_id)

        attachments_dir = Path(os.getenv("ATTACHMENTS_DIR", "./attachments"))
        expires_minutes = float(os.getenv("ATTACHMENT_EXPIRES_MINUTES", "60"))
        attachments_dir.mkdir(parents=True, exist_ok=True)

        file_id = str(uuid.uuid4())
        downloaded_path = attachment.download(savepath=str(attachments_dir))
        original_filename = getattr(
            attachment,
            "filename",
            f"attachment_{attachment_id}",
        )
        safe_filename = _sanitize_attachment_filename(
            original_filename, f"attachment_{attachment_id}"
        )

        uuid_dir = attachments_dir / file_id
        uuid_dir.mkdir(exist_ok=True)
        final_path = uuid_dir / safe_filename
        temp_path = uuid_dir / f"{safe_filename}.tmp"

        try:
            os.rename(downloaded_path, temp_path)
            os.rename(temp_path, final_path)
        except (OSError, IOError) as e:
            try:
                if temp_path.exists():
                    temp_path.unlink()
                if Path(downloaded_path).exists():
                    Path(downloaded_path).unlink()
            except OSError:
                pass
            return {"error": f"Failed to store attachment: {str(e)}"}

        expires_hours = expires_minutes / 60.0
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        metadata = {
            "file_id": file_id,
            "attachment_id": attachment_id,
            "original_filename": safe_filename,
            "file_path": str(final_path),
            "content_type": getattr(
                attachment,
                "content_type",
                "application/octet-stream",
            ),
            "size": final_path.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        metadata_file = uuid_dir / "metadata.json"
        temp_metadata = uuid_dir / "metadata.json.tmp"

        try:
            with open(temp_metadata, "w", encoding="utf-8") as metadata_stream:
                json.dump(metadata, metadata_stream, indent=2)
            os.rename(temp_metadata, metadata_file)
        except (OSError, IOError, ValueError) as e:
            try:
                if temp_metadata.exists():
                    temp_metadata.unlink()
                if final_path.exists():
                    final_path.unlink()
            except OSError:
                pass
            return {"error": f"Failed to save metadata: {str(e)}"}

        download_url = _build_download_url(file_id)
        return {
            "download_url": download_url,
            "filename": safe_filename,
            "content_type": metadata["content_type"],
            "size": metadata["size"],
            "expires_at": metadata["expires_at"],
            "attachment_id": attachment_id,
        }
    except Exception as e:
        return handle_error(
            e,
            f"downloading attachment {attachment_id}",
            {"resource_type": "attachment", "resource_id": attachment_id},
        )


async def cleanup_attachment_files_impl(
    *,
    attachment_manager_factory: Callable[[str], AttachmentFileManager] = (
        AttachmentFileManager
    ),
    log: Optional[logging.Logger] = None,
) -> Dict[str, Any]:
    """Clean up expired attachment files and return storage statistics."""
    try:
        attachments_dir = os.getenv("ATTACHMENTS_DIR", "./attachments")
        manager = attachment_manager_factory(attachments_dir)
        cleanup_stats = manager.cleanup_expired_files()
        storage_stats = manager.get_storage_stats()
        return {"cleanup": cleanup_stats, "current_storage": storage_stats}
    except Exception as e:
        selected_logger = log or logger
        selected_logger.error(f"Error during attachment cleanup: {e}")
        return {"error": f"An error occurred during cleanup: {str(e)}"}
