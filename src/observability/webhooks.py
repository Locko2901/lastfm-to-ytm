"""Webhook dispatch wrapper that respects settings filter."""

import logging
from typing import Any

from ..config import Settings
from ..webhook import send_webhook

log = logging.getLogger(__name__)


def fire_webhook(settings: Settings, *, status: str, sync_type: str = "main", **kwargs: Any) -> None:
    """Send webhook if configured and event matches filter."""
    if not settings.webhook_url:
        return
    if status == "success" and settings.webhook_events == "error":
        return
    try:
        send_webhook(
            settings.webhook_url,
            status=status,
            sync_type=sync_type,
            allow_private=settings.webhook_allow_private,
            **kwargs,
        )
    except Exception as e:
        log.debug("Webhook dispatch failed: %s", e)
