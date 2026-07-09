"""Compute a read-only preview ("dry run") of what a playlist sync would change."""

from __future__ import annotations

from typing import Any


def current_tracks_from_playlist(playlist: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract ``video_id``/``title``/``artist`` rows from a YTM playlist dict."""
    tracks: list[dict[str, Any]] = []
    for track in playlist.get("tracks", []):
        vid = track.get("videoId")
        if not vid:
            continue
        artists = track.get("artists") or []
        artist = ", ".join(a.get("name", "") for a in artists if a.get("name"))
        tracks.append({"video_id": vid, "title": track.get("title", ""), "artist": artist})
    return tracks


def build_sync_preview(
    *,
    playlist_name: str,
    playlist_id: str | None,
    current_tracks: list[dict[str, Any]],
    desired_video_ids: list[str],
    resolved_details: dict[str, dict[str, Any]],
    misses: int = 0,
) -> dict[str, Any]:
    """Diff the current playlist against the desired track list without mutating anything.

    Args:
        playlist_name: Name of the target playlist.
        playlist_id: Existing playlist ID, or ``None`` if the playlist would be created.
        current_tracks: Current playlist tracks as dicts with ``video_id``/``title``/``artist``.
        desired_video_ids: Ordered list of video IDs the sync would produce.
        resolved_details: Map of video ID -> resolved track metadata
            (``artist``/``title``/``score``/``plays``/``source``).
        misses: Number of tracks that could not be resolved to a video ID.

    Returns:
        A JSON-serialisable preview dict with a summary and added/removed lists.
    """
    current_ids = [t["video_id"] for t in current_tracks if t.get("video_id")]
    current_set = set(current_ids)
    desired_set = set(desired_video_ids)
    current_detail_map = {t["video_id"]: t for t in current_tracks if t.get("video_id")}

    added: list[dict[str, Any]] = []
    for vid in desired_video_ids:
        if vid not in current_set:
            d = resolved_details.get(vid, {})
            added.append(
                {
                    "video_id": vid,
                    "artist": d.get("artist", ""),
                    "title": d.get("title", ""),
                    "score": d.get("score"),
                    "plays": d.get("plays"),
                    "source": d.get("source", ""),
                }
            )

    removed: list[dict[str, Any]] = []
    for vid in current_ids:
        if vid not in desired_set:
            t = current_detail_map.get(vid, {})
            removed.append(
                {
                    "video_id": vid,
                    "artist": t.get("artist", ""),
                    "title": t.get("title", ""),
                }
            )

    kept_ids = [vid for vid in desired_video_ids if vid in current_set]

    current_kept = [vid for vid in current_ids if vid in desired_set]
    desired_kept = [vid for vid in desired_video_ids if vid in current_set]
    reordered = current_kept != desired_kept

    return {
        "playlist_name": playlist_name,
        "playlist_id": playlist_id,
        "exists": playlist_id is not None,
        "summary": {
            "current_count": len(current_ids),
            "desired_count": len(desired_video_ids),
            "added": len(added),
            "removed": len(removed),
            "unchanged": len(kept_ids),
            "reordered": reordered,
        },
        "added": added,
        "removed": removed,
        "misses": misses,
    }
