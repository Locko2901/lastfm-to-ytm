"""History scrobbler glue for the dashboard: scheduled polls, failure notifications, status."""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import Settings
from src.lastfm.client import LastfmClient, Transport, requests_transport, session_transport
from src.observability.webhooks import fire_webhook
from src.scrobbler import Poller, PollOutcome, ScrobblerStore, history_reader
from src.scrobbler.pacing import next_poll_at, pace, poll_due
from src.scrobbler.service import ERROR_HISTORY_AUTH, last_error_kind, oldest_accepted_timestamp

from . import events as bus
from . import notifications
from .data import load_settings
from .http import ipv4_session

logger = logging.getLogger(__name__)

_store: ScrobblerStore | None = None
_store_lock = threading.Lock()
_poll_lock = threading.Lock()

STATS_WINDOW_SECONDS = 24 * 3600


def get_store(settings: Settings) -> ScrobblerStore:
    """Return the shared store for ``SCROBBLER_DB_FILE``, reopening it when the path changes."""
    global _store
    with _store_lock:
        path = Path(settings.scrobbler_db_file)
        if _store is None or _store.path != path:
            if _store is not None:
                _store.close()
            _store = ScrobblerStore(path)
        return _store


def reset_store() -> None:
    """Drop the shared store (tests, or after the database file changed)."""
    global _store
    with _store_lock:
        if _store is not None:
            _store.close()
        _store = None


def _transport(settings: Settings) -> Transport:
    if not settings.lastfm_force_ipv4:
        return requests_transport
    return session_transport(ipv4_session())


def build_client(settings: Settings) -> LastfmClient:
    """Last.fm client with the configured key, secret, session and retries."""
    return LastfmClient(
        settings.lastfm_api_key,
        settings.lastfm_api_secret,
        settings.lastfm_session_key,
        max_retries=settings.lastfm_max_retries,
        transport=_transport(settings),
    )


def poll_now(settings: Settings | None = None) -> PollOutcome | None:
    """Run one poll when the scrobbler is enabled and no other poll is running.

    Returns None when it is disabled or busy.
    """
    settings = settings or load_settings()
    if settings is None or not settings.scrobbler_enabled:
        return None
    if not _poll_lock.acquire(blocking=False):
        return None
    try:
        outcome = Poller(settings, get_store(settings), history_reader(settings), build_client(settings)).run()
    finally:
        _poll_lock.release()
    if outcome.status == "busy":
        return None
    if outcome.notify:
        notify_failure(settings, outcome)
    publish_session_state(outcome)
    bus.publish("scrobbler_changed", {"status": outcome.status})
    return outcome


def publish_session_state(outcome: PollOutcome) -> None:
    """Tell the dashboard when a poll finds the YouTube Music session expired, and when a read works again after that."""
    if outcome.error_kind == ERROR_HISTORY_AUTH:
        bus.publish("auth_status", {"valid": False, "expired": True})
    elif outcome.previous_error_kind == ERROR_HISTORY_AUTH and not outcome.history_failed:
        bus.publish("auth_status", {"valid": True})


def youtube_session_expired(settings: Settings | None) -> bool:
    """Whether the last poll found the YouTube Music session expired and the auth file has not been replaced since."""
    if settings is None or not Path(settings.scrobbler_db_file).exists():
        return False
    store = get_store(settings)
    last = store.last_poll()
    if last is None or last_error_kind(store) != ERROR_HISTORY_AUTH:
        return False
    auth = Path(settings.ytm_auth_path)
    return not auth.exists() or auth.stat().st_mtime <= last["finished_at"]


def poll_if_due(settings: Settings | None = None) -> PollOutcome | None:
    """One scheduler tick: poll only when adaptive pacing says a poll is due (see ``scrobbler.pacing``)."""
    settings = settings or load_settings()
    if settings is None or not settings.scrobbler_enabled:
        return None
    last_attempt, last_change, errors = get_store(settings).pacing_state()
    fastest, idle = settings.scrobbler_poll_minutes * 60, settings.scrobbler_idle_minutes * 60
    if not poll_due(fastest, time.time(), last_attempt, last_change, errors, idle=idle):
        return None
    return poll_now(settings)


def run_scheduled_poll() -> None:
    """Scheduler entry point: one tick, never raising."""
    try:
        poll_if_due()
    except Exception:
        logger.exception("Scheduled scrobbler poll failed")


def notify_failure(settings: Settings, outcome: PollOutcome) -> None:
    """Send a failure through the dashboard notifications, Apprise and the legacy webhook."""
    message = f"History scrobbler: {outcome.error}"
    try:
        notifications.add(message, "error", source="scrobbler")
    except Exception:
        logger.exception("Could not store the scrobbler notification")
    fire_webhook(
        settings,
        status="error",
        sync_type="scrobbler",
        error=outcome.error,
        tracks_resolved=outcome.scrobbled,
        tracks_missed=outcome.failed,
    )


def clear_store(settings: Settings) -> bool:
    """Forget the snapshot and every decision, unless a poll is running (then return False)."""
    if not _poll_lock.acquire(blocking=False):
        return False
    try:
        store = get_store(settings)
        with store.exclusive() as owned:
            if owned:
                store.clear()
            return owned
    finally:
        _poll_lock.release()


def dry_run_offer(settings: Settings) -> dict[str, int]:
    """How many "would scrobble" plays of the dry run were never offered: still accepted by age, and too old."""
    eligible, too_old = get_store(settings).dry_run_offer(oldest_accepted_timestamp(time.time()))
    return {"eligible": eligible, "too_old": too_old}


def record_dry_run_choice(settings: Settings, send: bool) -> dict[str, int] | None:
    """Record the answer to the dry-run offer; None while a poll is running.

    Sending queues the plays Last.fm still accepts for the next poll, which
    checks each one for duplicates and sends it like any other play.
    """
    if not _poll_lock.acquire(blocking=False):
        return None
    try:
        store = get_store(settings)
        with store.exclusive() as owned:
            if not owned:
                return None
            now = time.time()
            count, too_old = store.record_dry_run_choice(send, oldest_accepted_timestamp(now), now)
    finally:
        _poll_lock.release()
    bus.publish("scrobbler_changed", {"status": "dry_run_choice"})
    return {"queued": count, "too_old": too_old} if send else {"kept": count}


def is_polling() -> bool:
    """True while a poll runs."""
    return _poll_lock.locked()


def get_status(settings: Settings | None, next_poll: str | None = None) -> dict[str, Any]:
    """Everything the dashboard shows about the scrobbler."""
    if settings is None:
        return {"configured": False, "enabled": False}
    status: dict[str, Any] = {
        "configured": True,
        "enabled": settings.scrobbler_enabled,
        "dry_run": settings.scrobbler_dry_run,
        "poll_minutes": settings.scrobbler_poll_minutes,
        "has_secret": bool(settings.lastfm_api_secret),
        "connected": bool(settings.lastfm_session_key),
        "session_user": settings.lastfm_session_user,
        "lastfm_user": settings.lastfm_user,
        "account_mismatch": bool(settings.lastfm_session_user) and settings.lastfm_session_user.casefold() != settings.lastfm_user.casefold(),
        "polling": is_polling(),
        "next_poll": next_poll if settings.scrobbler_enabled else None,
        "idle_minutes": settings.scrobbler_idle_minutes,
        "pace": None,
        "pace_seconds": None,
        "last_poll": None,
        "counts": {},
    }
    if settings.scrobbler_enabled or Path(settings.scrobbler_db_file).exists():
        store = get_store(settings)
        now = time.time()
        status["last_poll"] = store.last_poll()
        status["counts"] = store.status_counts(now - STATS_WINDOW_SECONDS)
        status["youtube_session_expired"] = youtube_session_expired(settings)
        if settings.scrobbler_enabled:
            fastest, idle = settings.scrobbler_poll_minutes * 60, settings.scrobbler_idle_minutes * 60
            last_attempt, last_change, errors = store.pacing_state()
            status["pace"], status["pace_seconds"] = pace(fastest, now, last_change, errors, idle=idle)
            if next_poll:
                tick = datetime.fromisoformat(next_poll).timestamp()
                due = next_poll_at(tick, fastest, last_attempt, last_change, errors, idle=idle)
                status["next_poll"] = datetime.fromtimestamp(due, UTC).isoformat()
    return status
