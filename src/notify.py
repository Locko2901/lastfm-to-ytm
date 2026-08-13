"""Apprise-based sync notifications with multi-target support.

Apprise (https://github.com/caronc/apprise) turns a service URL such as
``discord://...``, ``ntfy://...`` or ``tgram://...`` into a delivered
notification, so a single list of URLs can fan a sync result out to many
services at once. This supersedes the legacy generic webhook in
``src/webhook.py``.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

log = logging.getLogger(__name__)

_SPLIT_RE = re.compile(r"[\s,]+")


def parse_apprise_entries(raw: str | None) -> list[tuple[str, bool]]:
    """Parse ``APPRISE_URLS`` into ``(url, enabled)`` pairs.

    Entries are separated by newlines, commas or whitespace. A leading ``!``
    marks a disabled entry that is kept in configuration but skipped when
    dispatching. Blank entries are dropped and duplicates removed (first wins).
    """
    if not raw:
        return []
    seen: dict[str, bool] = {}
    for part in _SPLIT_RE.split(raw.strip()):
        token = part.strip()
        if not token:
            continue
        enabled = True
        if token.startswith("!"):
            enabled = False
            token = token[1:].strip()
        if token and token not in seen:
            seen[token] = enabled
    return list(seen.items())


def parse_apprise_urls(raw: str | None) -> list[str]:
    """Return only the enabled Apprise URLs, used for dispatch."""
    return [url for url, enabled in parse_apprise_entries(raw) if enabled]


def _build_message(
    *,
    status: str,
    sync_type: str,
    tracks_resolved: int,
    tracks_missed: int,
    duration_secs: float | None,
    error: str | None,
    playlist_url: str | None,
    cache_hits: int | None,
    cache_misses: int | None,
    api_searches: int | None,
    tracks_total: int | None,
) -> tuple[str, str]:
    """Build a ``(title, body)`` pair for an Apprise notification."""
    title = {
        "success": f"\u2705 Sync complete ({sync_type})",
        "error": f"\u274c Sync failed ({sync_type})",
        "test": "\U0001f514 Notification test",
    }.get(status, f"Sync {status} ({sync_type})")

    lines: list[str] = []
    if status != "test":
        lines.append(f"Resolved: {tracks_resolved}")
        lines.append(f"Missed: {tracks_missed}")
        if tracks_total is not None:
            lines.append(f"Total: {tracks_total}")
    if duration_secs is not None:
        lines.append(f"Duration: {duration_secs:.1f}s")
    if api_searches is not None:
        lines.append(f"API searches: {api_searches}")
    if cache_hits is not None:
        total = cache_hits + (cache_misses or 0)
        rate = f" ({100 * cache_hits // total}%)" if total > 0 else ""
        lines.append(f"Cache hits: {cache_hits}{rate}")
    if playlist_url:
        lines.append(f"Playlist: {playlist_url}")
    if error:
        lines.append(f"Error: {error[:1000]}")
    if not lines:
        lines.append(datetime.now(UTC).isoformat())

    return title, "\n".join(lines)


def send_apprise(
    urls: list[str],
    *,
    status: str,
    sync_type: str = "main",
    tracks_resolved: int = 0,
    tracks_missed: int = 0,
    duration_secs: float | None = None,
    error: str | None = None,
    playlist_url: str | None = None,
    cache_hits: int | None = None,
    cache_misses: int | None = None,
    api_searches: int | None = None,
    tracks_total: int | None = None,
) -> bool:
    """Dispatch a notification to every Apprise URL. Returns True on success.

    Apprise URLs are operator-configured (via ``.env``/the authenticated
    settings UI) and intentionally include self-hosted LAN services such as
    ntfy or Gotify, so no public-address SSRF guard is applied here.
    """
    if not urls:
        return False

    try:
        import apprise
    except ImportError:
        log.warning("Apprise is not installed; cannot send notifications (pip install apprise)")
        return False

    apobj = apprise.Apprise()
    added = 0
    for url in urls:
        if apobj.add(url):
            added += 1
        else:
            log.warning("Ignoring invalid Apprise URL")
    if not added:
        log.warning("No valid Apprise URLs configured")
        return False

    title, body = _build_message(
        status=status,
        sync_type=sync_type,
        tracks_resolved=tracks_resolved,
        tracks_missed=tracks_missed,
        duration_secs=duration_secs,
        error=error,
        playlist_url=playlist_url,
        cache_hits=cache_hits,
        cache_misses=cache_misses,
        api_searches=api_searches,
        tracks_total=tracks_total,
    )
    notify_type = {
        "success": apprise.NotifyType.SUCCESS,
        "error": apprise.NotifyType.FAILURE,
    }.get(status, apprise.NotifyType.INFO)

    try:
        ok = apobj.notify(title=title, body=body, notify_type=notify_type)
    except Exception as e:
        log.warning("Apprise notification failed: %s", e)
        return False
    if ok:
        log.info("Apprise notified (%s %s) -> %d target(s)", status, sync_type, added)
    else:
        log.warning("Apprise reported delivery failure (%s %s)", status, sync_type)
    return bool(ok)
