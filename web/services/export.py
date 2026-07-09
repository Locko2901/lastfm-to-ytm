"""Playlist export formatters (M3U, CSV, JSON).

Pure functions that turn a list of resolved playlist track dicts
(``{"artist", "title", "video_id", "yt_title", ...}``) into a downloadable
text body. Kept dependency-free so they're trivially unit-testable and reusable
by any route that already has a track list.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    "m3u": ("audio/x-mpegurl", "m3u8"),
    "csv": ("text/csv", "csv"),
    "json": ("application/json", "json"),
}

_YTM_WATCH_URL = "https://music.youtube.com/watch?v="


def track_url(video_id: str) -> str:
    """Return the YouTube Music watch URL for a video ID (empty string if none)."""
    return f"{_YTM_WATCH_URL}{video_id}" if video_id else ""


def tracks_to_json(playlist_name: str, tracks: list[dict[str, Any]]) -> str:
    """Serialise tracks to a pretty-printed JSON document."""
    payload = {
        "playlist": playlist_name,
        "track_count": len(tracks),
        "tracks": [
            {
                "artist": t.get("artist", ""),
                "title": t.get("title", ""),
                "video_id": t.get("video_id", ""),
                "yt_title": t.get("yt_title"),
                "url": track_url(t.get("video_id", "")),
            }
            for t in tracks
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def tracks_to_csv(tracks: list[dict[str, Any]]) -> str:
    """Serialise tracks to CSV with a header row."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["artist", "title", "video_id", "yt_title", "url"])
    for t in tracks:
        vid = t.get("video_id", "")
        writer.writerow([t.get("artist", ""), t.get("title", ""), vid, t.get("yt_title") or "", track_url(vid)])
    return buf.getvalue()


def tracks_to_m3u(playlist_name: str, tracks: list[dict[str, Any]]) -> str:
    """Serialise tracks to an extended M3U playlist pointing at YouTube Music URLs."""
    lines = ["#EXTM3U", f"#PLAYLIST:{playlist_name}"]
    for t in tracks:
        artist = t.get("artist", "")
        title = t.get("title", "")
        label = f"{artist} - {title}" if artist and title else title or artist or t.get("video_id", "")
        lines.append(f"#EXTINF:-1,{label}")
        lines.append(track_url(t.get("video_id", "")))
    return "\n".join(lines) + "\n"


def render_export(playlist_name: str, tracks: list[dict[str, Any]], fmt: str) -> tuple[str, str, str] | None:
    """Render tracks in the requested format.

    Returns ``(body, mimetype, extension)`` or ``None`` if ``fmt`` is unsupported.
    """
    fmt = (fmt or "").lower()
    if fmt not in EXPORT_FORMATS:
        return None
    mimetype, ext = EXPORT_FORMATS[fmt]
    if fmt == "json":
        body = tracks_to_json(playlist_name, tracks)
    elif fmt == "csv":
        body = tracks_to_csv(tracks)
    else:
        body = tracks_to_m3u(playlist_name, tracks)
    return body, mimetype, ext
