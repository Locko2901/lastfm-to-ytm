"""History DB recording helpers."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from ..config import Settings
from ..history import HistoryDB

if TYPE_CHECKING:
    from ..cache.search import SearchCache

log = logging.getLogger(__name__)

_MISS_SOURCES = ("not_found", "not_found_cached", "blacklisted")


def get_history_db(settings: Settings) -> HistoryDB | None:
    """Return HistoryDB instance if enabled, else None."""
    if not settings.history_db_enabled:
        return None
    try:
        return HistoryDB(settings.history_db_file)
    except Exception as e:
        log.warning("Failed to open history DB: %s", e)
        return None


def record_tracks_to_history(db: HistoryDB, run_log_mappings: list[dict[str, Any]], search_cache: SearchCache) -> None:
    """Record all resolved tracks into the history database."""
    for m in run_log_mappings:
        artist = m.get("artist", "")
        title = m.get("title", "")
        source = m.get("source", "search")
        if not artist or not title:
            continue

        is_miss = source in ("not_found", "not_found_cached", "blacklisted")
        video_id = None
        yt_title = None
        if not is_miss:
            entry = search_cache.get_entry(artist, title)
            if entry:
                video_id = entry.get("video_id")
                yt_title = entry.get("yt_title")

        db.record_track(artist, title, video_id, yt_title, source, missed=is_miss)


def record_near_misses_to_history(
    db: HistoryDB,
    run_log_mappings: list[dict[str, Any]],
    search_cache: SearchCache,
    limit: int,
    sync_id: int | None = None,
) -> int:
    """Persist tracks that resolved to a video but ranked just past ``limit``.

    The playlist keeps only the top ``limit`` resolved tracks; the remainder
    are "near-misses" — recently scrobbled songs that scored just below the
    cutoff. Surfacing them helps tune ``LIMIT``/``RECENCY_*`` settings. The
    ranked resolved order is recovered from ``run_log_mappings`` (miss entries
    are interleaved but skipped here). Returns the number of rows stored.
    """
    if limit <= 0:
        return 0
    resolved = [m for m in run_log_mappings if m.get("source") not in _MISS_SOURCES]
    dropped = resolved[limit:]
    if not dropped:
        db.record_near_misses(sync_id, [], limit)
        return 0

    rows: list[dict[str, Any]] = []
    for m in dropped:
        artist = m.get("artist", "")
        title = m.get("title", "")
        if not artist or not title:
            continue
        video_id = None
        yt_title = None
        entry = search_cache.get_entry(artist, title)
        if entry:
            video_id = entry.get("video_id")
            yt_title = entry.get("yt_title")
        rows.append(
            {
                "artist": artist,
                "title": title,
                "video_id": video_id,
                "yt_title": yt_title,
                "score": m.get("score"),
                "plays": m.get("plays"),
            }
        )

    return db.record_near_misses(sync_id, rows, limit)


def record_sync_error(settings: Settings, error: Exception) -> None:
    """Record a sync error as a history action (best-effort)."""
    try:
        db = get_history_db(settings)
        if not db:
            return
        source = os.environ.get("SYNC_TRIGGER", "cli")
        error_str = str(error)
        if len(error_str) > 200:
            error_str = error_str[:200] + "…"
        db.record_action("sync_error", detail=error_str, source=source)

        sync_id_str = os.environ.get("HISTORY_SYNC_ID")
        if sync_id_str:
            db.finish_sync(int(sync_id_str), status="error", error_message=error_str)
    except Exception:
        pass
