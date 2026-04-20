"""Undecorated HTTP-route helper implementations for Redmine MCP."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from starlette.responses import FileResponse

from ..attachment_manager import AttachmentFileManager

logger = logging.getLogger(__name__)


class CleanupTaskManager:
    """Manages the background cleanup task lifecycle."""

    def __init__(self):
        self.task: Optional[asyncio.Task] = None
        self.manager: Optional[AttachmentFileManager] = None
        self.enabled = False
        self.interval_seconds = 600  # 10 minutes default

    async def start(self):
        """Start the cleanup task if enabled."""
        self.enabled = os.getenv("AUTO_CLEANUP_ENABLED", "false").lower() == "true"

        if not self.enabled:
            logger.info("Automatic cleanup is disabled (AUTO_CLEANUP_ENABLED=false)")
            return

        interval_minutes = float(os.getenv("CLEANUP_INTERVAL_MINUTES", "10"))
        self.interval_seconds = interval_minutes * 60
        attachments_dir = os.getenv("ATTACHMENTS_DIR", "./attachments")

        self.manager = AttachmentFileManager(attachments_dir)

        logger.info(
            "Starting automatic cleanup task "
            f"(interval: {interval_minutes} minutes, directory: {attachments_dir})"
        )

        self.task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        """The main cleanup loop."""
        # Initial delay to let server fully start.
        await asyncio.sleep(10)

        while True:
            try:
                if self.manager is None:
                    await asyncio.sleep(self.interval_seconds)
                    continue

                stats = self.manager.cleanup_expired_files()
                if stats["cleaned_files"] > 0:
                    logger.info(
                        "Automatic cleanup completed: "
                        f"removed {stats['cleaned_files']} files, "
                        f"freed {stats['cleaned_mb']}MB"
                    )
                else:
                    logger.debug("Automatic cleanup: no expired files found")

                await asyncio.sleep(self.interval_seconds)

            except asyncio.CancelledError:
                logger.info("Cleanup task cancelled, shutting down")
                raise
            except Exception as exc:  # pragma: no cover - defensive runtime path
                logger.error(f"Error in cleanup task: {exc}", exc_info=True)
                await asyncio.sleep(min(self.interval_seconds, 300))

    async def stop(self):
        """Stop the cleanup task gracefully."""
        if self.task and not self.task.done():
            logger.info("Stopping cleanup task...")
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
            logger.info("Cleanup task stopped")

    def get_status(self) -> dict[str, Any]:
        """Get current status of cleanup task."""
        return {
            "enabled": self.enabled,
            "running": self.task and not self.task.done() if self.task else False,
            "interval_seconds": self.interval_seconds,
            "storage_stats": self.manager.get_storage_stats() if self.manager else None,
        }


def make_cleanup_manager() -> CleanupTaskManager:
    """Create a new cleanup task manager instance."""
    return CleanupTaskManager()


async def ensure_cleanup_started(
    cleanup_manager: CleanupTaskManager, cleanup_initialized: bool
) -> tuple[bool, str]:
    """Ensure cleanup task is started once, using lazy initialization."""
    if cleanup_initialized:
        return True, "Cleanup already initialized"

    cleanup_enabled = os.getenv("AUTO_CLEANUP_ENABLED", "false").lower() == "true"
    if cleanup_enabled:
        await cleanup_manager.start()
        logger.info("Cleanup task initialized via helper call")
        return True, "Cleanup task initialized"

    logger.info("Cleanup disabled (AUTO_CLEANUP_ENABLED=false)")
    return True, "Cleanup disabled"


def health_payload(auth_mode: str) -> dict[str, str]:
    """Build health endpoint payload."""
    return {
        "status": "ok",
        "service": "redmine_mcp_tools",
        "auth_mode": auth_mode,
    }


def serve_attachment_by_id(
    file_id: str,
    attachments_dir_env: str = "ATTACHMENTS_DIR",
) -> FileResponse | dict[str, Any]:
    """Serve attachment file response or return a structured error sentinel."""
    try:
        uuid.UUID(file_id)
    except ValueError:
        return {"status_code": 400, "detail": "Invalid file ID"}

    attachments_dir = Path(os.getenv(attachments_dir_env, "./attachments"))
    uuid_dir = attachments_dir / file_id
    metadata_file = uuid_dir / "metadata.json"

    if not metadata_file.exists():
        return {"status_code": 404, "detail": "File not found or expired"}

    try:
        with open(metadata_file, "r", encoding="utf-8") as file:
            metadata = json.load(file)

        expires_at_str = metadata.get("expires_at", "")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > expires_at:
                try:
                    file_path_for_cleanup = Path(metadata["file_path"])
                    if file_path_for_cleanup.exists():
                        file_path_for_cleanup.unlink()
                    metadata_file.unlink()
                    if uuid_dir.exists() and not any(uuid_dir.iterdir()):
                        uuid_dir.rmdir()
                except OSError:
                    pass
                return {"status_code": 404, "detail": "File expired"}

        file_path = Path(metadata["file_path"]).resolve()
        uuid_dir_resolved = uuid_dir.resolve()
        try:
            file_path.relative_to(uuid_dir_resolved)
        except ValueError:
            return {"status_code": 403, "detail": "Access denied"}

        if not file_path.exists():
            return {"status_code": 404, "detail": "File not found"}

        header_filename = Path(str(metadata.get("original_filename", ""))).name
        header_filename = (
            "".join(
                ch for ch in header_filename if ch.isprintable() and ch not in "\r\n"
            ).strip()
            or "attachment.bin"
        )

        return FileResponse(
            path=str(file_path),
            filename=header_filename,
            media_type=metadata.get("content_type", "application/octet-stream"),
        )

    except json.JSONDecodeError:
        return {"status_code": 500, "detail": "Corrupted metadata"}
    except ValueError:
        return {"status_code": 500, "detail": "Invalid metadata format"}


def cleanup_status_payload(cleanup_manager: CleanupTaskManager) -> dict[str, Any]:
    """Build cleanup status payload."""
    return cleanup_manager.get_status()
