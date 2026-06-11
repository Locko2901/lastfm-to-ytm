"""Unified Server-Sent Events stream for dashboard state changes."""

from __future__ import annotations

import json
import logging
import queue
import time
from collections.abc import Iterator
from typing import Any

from flask import Blueprint, Response, stream_with_context
from flask.typing import ResponseReturnValue

from ..services import events as bus
from ..services import notifications as notif_store
from ..services import sync_lock, sync_state
from ..services.scheduler import get_scheduler_status

events_bp = Blueprint("events", __name__, url_prefix="/api/events")

logger = logging.getLogger(__name__)

_KEEPALIVE_SECONDS = 15


def _snapshot() -> dict[str, Any]:
    """Capture current values that subscribers want on initial connect."""
    with sync_lock:
        sync_snap = {
            "running": sync_state["running"],
            "started_at": sync_state["started_at"],
            "finished_at": sync_state["finished_at"],
            "exit_code": sync_state["exit_code"],
        }
    try:
        scheduler_snap = get_scheduler_status()
    except Exception:
        logger.exception("Failed to read scheduler status for snapshot")
        scheduler_snap = None
    try:
        notifications_snap = notif_store.list_all()
    except Exception:
        logger.exception("Failed to read notifications for snapshot")
        notifications_snap = {"notifications": [], "last_seen_at": None}
    return {
        "sync_state": sync_snap,
        "scheduler": scheduler_snap,
        "notifications": notifications_snap,
    }


@events_bp.route("")
def stream() -> ResponseReturnValue:
    """SSE stream emitting typed events: ``sync_state``, ``stats_changed``, etc."""

    def gen() -> Iterator[str]:
        q = bus.subscribe()
        try:
            yield f"event: snapshot\ndata: {json.dumps(_snapshot())}\n\n"

            last_ping = time.time()
            while True:
                try:
                    event = q.get(timeout=_KEEPALIVE_SECONDS)
                except queue.Empty:
                    event = None

                if event is not None:
                    yield f"data: {json.dumps(event)}\n\n"

                now = time.time()
                if now - last_ping >= _KEEPALIVE_SECONDS:
                    yield ": ping\n\n"
                    last_ping = now
        except GeneratorExit:
            pass
        finally:
            bus.unsubscribe(q)

    return Response(
        stream_with_context(gen()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
