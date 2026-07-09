"""Persistent failure / run-log files consumed by the web dashboard."""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from ..config import CACHE_DIR
from .http_status import extract_http_status

log = logging.getLogger(__name__)


def save_run_log(mappings: list[dict[str, Any]]) -> None:
    """Save the run log for the web dashboard."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CACHE_DIR / ".last_run_log.json"
    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total": len(mappings),
        "mappings": mappings,
    }
    with log_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved run log with %d mappings to %s", len(mappings), log_file)


def save_failure_log(error_message: str, traceback_str: str | None = None, *, sync_type: str = "main") -> None:
    """Save a failure log."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CACHE_DIR / ".last_failure.json"

    hint = None
    status = extract_http_status(error_message)
    error_lower = error_message.lower()
    if status == 401 or "unauthorized" in error_lower:
        hint = "Authentication expired. Try regenerating YouTube Music auth or check your Last.fm API key."
    elif status == 429 or "rate limit" in error_lower:
        hint = "Rate limited by YouTube Music. Wait a few minutes before trying again."
    elif status == 403 or "forbidden" in error_lower:
        hint = "Access denied. You may need to regenerate YouTube Music auth, or you've been rate-limited."

    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "error": error_message,
        "traceback": traceback_str,
        "hint": hint,
        "sync_type": sync_type,
    }
    with log_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved failure log to %s", log_file)


def clear_failure_log() -> None:
    """Clear the failure log."""
    log_file = CACHE_DIR / ".last_failure.json"
    if log_file.exists():
        log_file.unlink()
        log.debug("Cleared failure log")


def save_dry_run_preview(playlists: list[dict[str, Any]], *, kind: str = "main") -> None:
    """Save the latest dry-run sync preview for the web dashboard.

    Args:
        playlists: One preview dict per playlist (see ``build_sync_preview``).
        kind: The sync kind that produced the preview (``"main"`` or ``"custom"``).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    preview_file = CACHE_DIR / ".dry_run_preview.json"
    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "kind": kind,
        "playlists": playlists,
    }
    with preview_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved dry-run preview (%s) with %d playlist(s) to %s", kind, len(playlists), preview_file)
