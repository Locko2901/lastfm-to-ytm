"""Notification dispatch: Apprise (preferred) + legacy webhook (deprecated)."""

import logging
from typing import Any

from ..config import Settings
from ..notify import send_apprise
from ..webhook import send_webhook

log = logging.getLogger(__name__)

_legacy_warned = False


def _fire_legacy_webhook(settings: Settings, *, status: str, sync_type: str, **kwargs: Any) -> None:
    """Send the DEPRECATED generic webhook if configured and the event matches."""
    global _legacy_warned
    if not settings.webhook_url:
        return
    if not _legacy_warned:
        log.warning("WEBHOOK_URL is deprecated; migrate to APPRISE_URLS (Apprise notifications)")
        _legacy_warned = True
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


def _fire_apprise(settings: Settings, *, status: str, sync_type: str, **kwargs: Any) -> None:
    """Send Apprise notifications if configured and the event matches."""
    if not settings.apprise_urls:
        return
    if status == "success" and settings.apprise_events == "error":
        return
    try:
        send_apprise(settings.apprise_urls, status=status, sync_type=sync_type, **kwargs)
    except Exception as e:
        log.debug("Apprise dispatch failed: %s", e)


def fire_webhook(settings: Settings, *, status: str, sync_type: str = "main", **kwargs: Any) -> None:
    """Dispatch sync notifications via Apprise and the legacy webhook."""
    _fire_apprise(settings, status=status, sync_type=sync_type, **kwargs)
    _fire_legacy_webhook(settings, status=status, sync_type=sync_type, **kwargs)
