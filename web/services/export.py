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
import re
from typing import Any

EXPORT_FORMATS: dict[str, tuple[str, str]] = {
    "m3u": ("audio/x-mpegurl", "m3u8"),
    "csv": ("text/csv", "csv"),
    "json": ("application/json", "json"),
    "custom": ("text/plain; charset=utf-8", "txt"),
}

CUSTOM_EXPORT_FIELDS: dict[str, str] = {
    "index": "1-based position of the track in the playlist",
    "artist": "Artist name",
    "title": "Track title",
    "yt_title": "YouTube Music title (falls back to the track title)",
    "video_id": "YouTube Music video ID",
    "url": "YouTube Music watch URL",
    "source": "Where the match came from (cache, override, ...)",
    "tags": "Comma-separated tags (custom/tag playlists only)",
    "playlist": "Playlist name",
    "count": "Total number of tracks in the playlist",
}

DEFAULT_CUSTOM_TEMPLATE = "{artist} - {title}"
DEFAULT_CUSTOM_EXTENSION = "txt"
DEFAULT_CUSTOM_SEPARATOR = "\n"

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_EXTENSION_RE = re.compile(r"[^A-Za-z0-9]")

_YTM_WATCH_URL = "https://music.youtube.com/watch?v="


def sanitize_extension(ext: str | None) -> str:
    """Normalise a user-supplied file extension to a short alphanumeric token."""
    cleaned = _EXTENSION_RE.sub("", (ext or "").lstrip(".")).lower()[:8]
    return cleaned or DEFAULT_CUSTOM_EXTENSION


EXPORT_FORMATS_SEED_VERSION = 2
DEFAULT_EXPORT_FORMATS: list[dict[str, str]] = [
    {"name": "Artist - Title", "template": "{artist} - {title}", "extension": "txt"},
    {"name": "Markdown links", "template": "- [{artist} - {title}]({url})", "extension": "md"},
    {"name": "Numbered list", "template": "{index}. {artist} - {title}", "extension": "txt"},
    {"name": "JSON lines", "template": '{"artist": "{artist}", "title": "{title}"}', "extension": "jsonl"},
    {
        "name": "JSON array",
        "template": '  {"artist": "{artist}", "title": "{title}"}',
        "header": "[\n",
        "separator": ",\n",
        "footer": "\n]",
        "extension": "json",
    },
]


def sanitize_export_format(entry: Any) -> dict[str, str] | None:
    """Validate/normalise one saved export format; return ``None`` if unusable."""
    if not isinstance(entry, dict):
        return None
    name = str(entry.get("name", "")).strip()[:80]
    if not name:
        return None
    template = str(entry.get("template", "") or DEFAULT_CUSTOM_TEMPLATE)[:2000]
    result: dict[str, str] = {
        "name": name,
        "template": template,
        "extension": sanitize_extension(entry.get("extension")),
    }
    header = str(entry.get("header", "") or "")[:1000]
    footer = str(entry.get("footer", "") or "")[:1000]
    separator = entry.get("separator")
    separator = DEFAULT_CUSTOM_SEPARATOR if separator is None else str(separator)[:100]
    if header:
        result["header"] = header
    if footer:
        result["footer"] = footer
    if separator != DEFAULT_CUSTOM_SEPARATOR:
        result["separator"] = separator
    return result


def sanitize_export_formats(entries: Any) -> list[dict[str, str]]:
    """Validate a list of saved formats, dropping invalid ones and de-duping by name."""
    if not isinstance(entries, list):
        return []
    seen: set[str] = set()
    result: list[dict[str, str]] = []
    for entry in entries:
        fmt = sanitize_export_format(entry)
        if fmt is None:
            continue
        key = fmt["name"].lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(fmt)
    return result


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
                "source": t.get("source", ""),
                "tags": list(t.get("tags", []) or []),
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


def _custom_field_values(playlist_name: str, track: dict[str, Any], index: int, total: int) -> dict[str, str]:
    """Build the string values for every supported custom-template placeholder."""
    vid = track.get("video_id", "") or ""
    title = track.get("title", "") or ""
    tags = track.get("tags") or []
    return {
        "index": str(index),
        "artist": track.get("artist", "") or "",
        "title": title,
        "yt_title": (track.get("yt_title") or title),
        "video_id": vid,
        "url": track_url(vid),
        "source": track.get("source", "") or "",
        "tags": ", ".join(str(t) for t in tags),
        "playlist": playlist_name,
        "count": str(total),
    }


def apply_custom_template(template: str, values: dict[str, str]) -> str:
    """Substitute ``{field}`` tokens using ``values``; unknown tokens are left untouched."""
    return _PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), template)


def tracks_to_custom(
    playlist_name: str,
    tracks: list[dict[str, Any]],
    template: str,
    header: str = "",
    footer: str = "",
    separator: str = DEFAULT_CUSTOM_SEPARATOR,
) -> str:
    """Render each track from ``template``, joined by ``separator`` and wrapped in ``header``/``footer``.

    The wrapper fields make structured output possible (e.g. a JSON array via
    ``header="["``, ``separator=","``, ``footer="]"``).
    """
    template = template or DEFAULT_CUSTOM_TEMPLATE
    total = len(tracks)
    items = [apply_custom_template(template, _custom_field_values(playlist_name, t, i, total)) for i, t in enumerate(tracks, start=1)]
    body = f"{header}{separator.join(items)}{footer}"
    if not body.endswith("\n"):
        body += "\n"
    return body


def custom_output_error(body: str, ext: str) -> str | None:
    """Return the mismatched extension when ``body`` isn't valid for it, else ``None``.

    The custom exporter emits one line per track, so a structured extension like
    ``json`` produces a malformed file. This guards against that mismatch.
    """
    ext = sanitize_extension(ext)
    if ext == "json":
        try:
            json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return "json"
    return None


def render_export(
    playlist_name: str,
    tracks: list[dict[str, Any]],
    fmt: str,
    template: str | None = None,
    extension: str | None = None,
    header: str = "",
    footer: str = "",
    separator: str = DEFAULT_CUSTOM_SEPARATOR,
) -> tuple[str, str, str] | None:
    """Render tracks in the requested format.

    ``template``/``extension``/``header``/``footer``/``separator`` are only used
    for the ``custom`` format (a ``{placeholder}`` string, a chosen file
    extension, and optional wrapper text to build structured output).
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
    elif fmt == "custom":
        body = tracks_to_custom(playlist_name, tracks, template or DEFAULT_CUSTOM_TEMPLATE, header, footer, separator)
        ext = sanitize_extension(extension)
    else:
        body = tracks_to_m3u(playlist_name, tracks)
    return body, mimetype, ext
