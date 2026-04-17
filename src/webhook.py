"""Webhook notifications for sync events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import requests

log = logging.getLogger(__name__)

_TIMEOUT = 10


def _is_discord(url: str) -> bool:
    return "discord.com/api/webhooks/" in url or "discordapp.com/api/webhooks/" in url


def _build_discord_payload(
    *,
    status: str,
    sync_type: str,
    tracks_resolved: int,
    tracks_missed: int,
    duration_secs: float | None,
    error: str | None,
    playlist_url: str | None,
    cache_hits: int | None = None,
    cache_misses: int | None = None,
    api_searches: int | None = None,
    tracks_total: int | None = None,
) -> dict:
    """Format webhook data as a Discord embed."""
    color = 0x57F287 if status == "success" else 0xED4245 if status == "error" else 0x5865F2
    title = {
        "success": f"\u2705 Sync complete ({sync_type})",
        "error": f"\u274c Sync failed ({sync_type})",
        "test": "\U0001f514 Webhook test",
    }.get(status, f"Sync {status} ({sync_type})")

    fields = []
    if status != "test":
        fields.append({"name": "Resolved", "value": str(tracks_resolved), "inline": True})
        fields.append({"name": "Missed", "value": str(tracks_missed), "inline": True})
        if tracks_total is not None:
            fields.append({"name": "Total", "value": str(tracks_total), "inline": True})
    if duration_secs is not None:
        fields.append({"name": "Duration", "value": f"{duration_secs:.1f}s", "inline": True})
    if api_searches is not None:
        fields.append({"name": "API Searches", "value": str(api_searches), "inline": True})
    if cache_hits is not None:
        rate = ""
        if cache_hits + (cache_misses or 0) > 0:
            rate = f" ({100 * cache_hits // (cache_hits + (cache_misses or 0))}%)"
        fields.append({"name": "Cache Hits", "value": f"{cache_hits}{rate}", "inline": True})
    if error:
        fields.append({"name": "Error", "value": f"```\n{error[:1000]}\n```"})
    if playlist_url:
        fields.append({"name": "Playlist", "value": f"[Open in YouTube Music]({playlist_url})"})

    return {
        "embeds": [
            {
                "title": title,
                "color": color,
                "fields": fields,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ],
    }


def _build_generic_payload(
    *,
    status: str,
    sync_type: str,
    tracks_resolved: int,
    tracks_missed: int,
    duration_secs: float | None,
    error: str | None,
    playlist_url: str | None,
    cache_hits: int | None = None,
    cache_misses: int | None = None,
    api_searches: int | None = None,
    tracks_total: int | None = None,
) -> dict:
    """Build a plain JSON payload for generic HTTP endpoints."""
    payload = {
        "status": status,
        "sync_type": sync_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "tracks_resolved": tracks_resolved,
        "tracks_missed": tracks_missed,
    }
    if tracks_total is not None:
        payload["tracks_total"] = tracks_total
    if duration_secs is not None:
        payload["duration_secs"] = round(duration_secs, 1)
    if cache_hits is not None:
        payload["cache_hits"] = cache_hits
    if cache_misses is not None:
        payload["cache_misses"] = cache_misses
    if api_searches is not None:
        payload["api_searches"] = api_searches
    if playlist_url:
        payload["playlist_url"] = playlist_url
    if error:
        payload["error"] = error[:500]
    return payload


def send_webhook(
    url: str,
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
    """Send a webhook notification. Returns True on success."""
    if not url:
        return False

    kwargs = {
        "status": status,
        "sync_type": sync_type,
        "tracks_resolved": tracks_resolved,
        "tracks_missed": tracks_missed,
        "duration_secs": duration_secs,
        "error": error,
        "playlist_url": playlist_url,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "api_searches": api_searches,
        "tracks_total": tracks_total,
    }

    payload = _build_discord_payload(**kwargs) if _is_discord(url) else _build_generic_payload(**kwargs)

    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT)
        resp.raise_for_status()
        log.info("Webhook sent (%s %s) -> %d", status, sync_type, resp.status_code)
        return True
    except Exception as e:
        log.warning("Webhook failed: %s", e)
        return False
