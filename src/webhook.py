"""Webhook notifications for sync events."""

from __future__ import annotations

import ipaddress
import logging
import socket
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

_TIMEOUT = 10


def _is_discord(url: str) -> bool:
    return "discord.com/api/webhooks/" in url or "discordapp.com/api/webhooks/" in url


def _is_safe_webhook_url(url: str, *, allow_private: bool = False) -> bool:
    """SSRF guard: allow only http(s) URLs.

    By default the host must resolve to public addresses. Set ``allow_private``
    (self-hosted opt-in) to permit private/loopback targets such as a LAN ntfy
    or Gotify instance.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    if allow_private:
        return True
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


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
    allow_private: bool = False,
) -> bool:
    """Send a webhook notification. Returns True on success."""
    if not url:
        return False

    if not _is_safe_webhook_url(url, allow_private=allow_private):
        log.warning("Webhook URL rejected: must be http(s) and resolve to a public address")
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
