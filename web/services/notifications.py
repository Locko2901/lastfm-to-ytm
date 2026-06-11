"""Server-side notification store with SSE fan-out.

Notifications are persisted to ``cache/.notifications.json`` so they survive
restarts and are shared across browser tabs / devices. Live updates are
broadcast to connected clients through per-subscriber queues consumed by the
SSE endpoint in ``web.routes.notifications``.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from . import events as bus

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = Path(os.environ.get("CACHE_DIR", str(_PROJECT_ROOT / "cache")))
_STORE_FILE = _CACHE_DIR / ".notifications.json"

_VALID_TYPES = {"success", "error", "info", "warning"}
MAX_NOTIFICATIONS = 100
TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days

_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _load() -> dict[str, Any]:
    try:
        with _STORE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"notifications": [], "last_seen_at": None}
    if not isinstance(data, dict):
        return {"notifications": [], "last_seen_at": None}
    data.setdefault("notifications", [])
    data.setdefault("last_seen_at", None)
    if not isinstance(data["notifications"], list):
        data["notifications"] = []
    return data


def _save(data: dict[str, Any]) -> None:
    try:
        _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _STORE_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(_STORE_FILE)
    except OSError as exc:
        logger.warning("Could not persist notifications: %s", exc)


def _prune(notifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop expired entries and trim to MAX_NOTIFICATIONS (newest first)."""
    cutoff = time.time() - TTL_SECONDS
    fresh = []
    for n in notifications:
        try:
            ts = datetime.fromisoformat(n["created_at"]).timestamp()
        except (KeyError, ValueError, TypeError):
            continue
        if ts >= cutoff:
            fresh.append(n)
    fresh.sort(key=lambda n: n["created_at"], reverse=True)
    return fresh[:MAX_NOTIFICATIONS]


def _broadcast(event: dict[str, Any]) -> None:
    bus.publish("notification", event)


def list_all() -> dict[str, Any]:
    """Return ``{notifications: [...], last_seen_at}`` (pruned)."""
    with _lock:
        data = _load()
        pruned = _prune(data["notifications"])
        if len(pruned) != len(data["notifications"]):
            data["notifications"] = pruned
            _save(data)
        return {
            "notifications": pruned,
            "last_seen_at": data.get("last_seen_at"),
        }


def add(message: str, type_: str = "info", source: str | None = None) -> dict[str, Any]:
    """Create a notification, persist, and broadcast it."""
    if type_ not in _VALID_TYPES:
        type_ = "info"
    message = (message or "").strip()
    if not message:
        raise ValueError("message is required")
    entry = {
        "id": secrets.token_hex(8),
        "message": message[:500],
        "type": type_,
        "created_at": _now_iso(),
        "source": source,
    }
    with _lock:
        data = _load()
        if data["notifications"]:
            prev = data["notifications"][0]
            if prev.get("message") == entry["message"] and prev.get("type") == entry["type"] and prev.get("source") == entry["source"]:
                try:
                    prev_ts = datetime.fromisoformat(prev["created_at"]).timestamp()
                    if time.time() - prev_ts < 5:
                        return cast("dict[str, Any]", prev)
                except (KeyError, ValueError, TypeError):
                    pass
        data["notifications"].insert(0, entry)
        data["notifications"] = _prune(data["notifications"])
        _save(data)
    _broadcast({"event": "add", "notification": entry})
    return entry


def delete(notification_id: str) -> bool:
    """Remove a notification by id. Returns ``True`` if it existed."""
    with _lock:
        data = _load()
        before = len(data["notifications"])
        data["notifications"] = [n for n in data["notifications"] if n.get("id") != notification_id]
        if len(data["notifications"]) == before:
            return False
        _save(data)
    _broadcast({"event": "delete", "id": notification_id})
    return True


def clear() -> None:
    """Drop every stored notification and broadcast a clear event."""
    with _lock:
        data = _load()
        data["notifications"] = []
        _save(data)
    _broadcast({"event": "clear"})


def mark_read() -> str:
    """Mark all current notifications as read. Returns the new ``last_seen_at``."""
    seen = _now_iso()
    with _lock:
        data = _load()
        data["last_seen_at"] = seen
        _save(data)
    _broadcast({"event": "read", "last_seen_at": seen})
    return seen
