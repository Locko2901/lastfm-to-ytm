"""Generic server-side event bus with SSE fan-out.

A single in-process pub/sub used by the dashboard to push state changes
to the browser without polling. Producers call ``publish(type, data)``
from anywhere; subscribers (the ``/api/events`` SSE endpoint) get the
event delivered on their own queue.
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
from typing import Any

logger = logging.getLogger(__name__)

_subscribers: list[queue.Queue[Any]] = []
_lock = threading.Lock()


def publish(event_type: str, data: Any = None) -> None:
    """Broadcast an event to every active subscriber."""
    payload = {"type": event_type, "data": data}
    with _lock:
        subs = list(_subscribers)
    for q in subs:
        with contextlib.suppress(queue.Full):
            q.put_nowait(payload)


def subscribe() -> queue.Queue[Any]:
    """Register a subscriber queue. Caller must call ``unsubscribe`` on exit."""
    q: queue.Queue[Any] = queue.Queue(maxsize=256)
    with _lock:
        _subscribers.append(q)
    return q


def unsubscribe(q: queue.Queue[Any]) -> None:
    """Remove a previously-registered subscriber queue."""
    with _lock, contextlib.suppress(ValueError):
        _subscribers.remove(q)
