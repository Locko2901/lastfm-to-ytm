"""Data loading and manipulation functions."""

from __future__ import annotations

import json
from pathlib import Path

from src.cache.search import SearchCache, SearchOverrides
from src.config import CACHE_DIR, CONFIG_DIR, Settings
from src.playlist.weekly import _derive_weekly_prefix

RUN_LOG_FILE = CACHE_DIR / ".last_run_log.json"
OVERRIDES_FILE = CONFIG_DIR / "search_overrides.json"
SEARCH_CACHE_FILE = CACHE_DIR / ".search_cache.json"
PLAYLIST_CACHE_FILE = CACHE_DIR / ".playlist_cache.json"


def load_run_log() -> dict:
    """Load the last run log and enrich with data from cache/overrides.

    The run log only stores minimal data (artist, title, source).
    We pull video_id and yt_title from the search cache/overrides.
    """
    if not RUN_LOG_FILE.exists():
        return {"mappings": [], "limit": 100, "timestamp": None, "total": 0, "resolved": 0}
    try:
        with RUN_LOG_FILE.open() as f:
            data = json.load(f)

        try:
            settings = Settings.from_env()
            limit = settings.limit
        except Exception:
            limit = 100

        raw_mappings = data.get("mappings", [])
        cache = load_search_cache()
        overrides = load_overrides()
        enriched_mappings = []
        resolved = 0

        for m in raw_mappings:
            artist = m.get("artist", "")
            title = m.get("title", "")
            source = m.get("source", "")

            video_id = None
            yt_title = None
            pending_retry = False

            if source == "override":
                video_id = overrides.get(artist, title)
            elif source in ("cache", "search"):
                entry = cache.get_entry(artist, title)
                if entry:
                    video_id = entry.get("video_id")
                    yt_title = entry.get("yt_title")
                else:
                    pending_retry = True

            if video_id:
                resolved += 1

            enriched_mappings.append(
                {
                    "artist": artist,
                    "title": title,
                    "video_id": video_id,
                    "yt_title": yt_title,
                    "source": source,
                    "pending_retry": pending_retry,
                }
            )

        return {
            "mappings": enriched_mappings,
            "limit": limit,
            "timestamp": data.get("timestamp"),
            "total": data.get("total", 0),
            "resolved": resolved,
        }
    except Exception:
        return {"mappings": [], "limit": 100, "timestamp": None, "total": 0, "resolved": 0}


def load_overrides() -> SearchOverrides:
    """Load search overrides."""
    return SearchOverrides(str(OVERRIDES_FILE))


def load_search_cache() -> SearchCache:
    """Load search cache."""
    try:
        settings = Settings.from_env()
        return SearchCache(
            settings.cache_search_file,
            ttl_days=settings.cache_search_ttl_days,
            notfound_ttl_days=settings.cache_notfound_ttl_days,
        )
    except Exception:
        return SearchCache(str(SEARCH_CACHE_FILE))


def get_cache_stats() -> dict:
    """Get cache statistics."""
    cache = load_search_cache()
    total = len(cache._cache)
    found = sum(1 for e in cache._cache.values() if e.get("video_id"))
    not_found = total - found
    return {"total": total, "found": found, "not_found": not_found}


def get_not_found_tracks() -> list[dict]:
    """Get all tracks from the search cache that have null video_id."""
    cache = load_search_cache()
    not_found = []
    for key, entry in cache._cache.items():
        if not entry.get("video_id"):
            not_found.append(
                {
                    "key": key,
                    "artist": entry.get("artist", key.split("|")[0] if "|" in key else key),
                    "title": entry.get("title", key.split("|")[1] if "|" in key else ""),
                    "timestamp": entry.get("timestamp"),
                }
            )
    not_found.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return not_found


def get_cached_tracks() -> list[dict]:
    """Get all tracks from the search cache that have a video_id (found tracks)."""
    cache = load_search_cache()
    overrides = load_overrides()
    cached = []
    for key, entry in cache._cache.items():
        video_id = entry.get("video_id")
        if video_id:
            override_key = f"{entry.get('artist', '').lower()}|{entry.get('title', '').lower()}"
            has_override = override_key in overrides._cache.get("_overrides", {})
            is_blacklisted = override_key in overrides._cache.get("_blacklist", {})
            cached.append(
                {
                    "key": key,
                    "artist": entry.get("artist", key.split("|")[0] if "|" in key else key),
                    "title": entry.get("title", key.split("|")[1] if "|" in key else ""),
                    "video_id": video_id,
                    "yt_title": entry.get("yt_title"),
                    "timestamp": entry.get("timestamp"),
                    "has_override": has_override,
                    "is_blacklisted": is_blacklisted,
                }
            )
    cached.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return cached


def get_last_sync_time() -> str | None:
    """Get the last sync time from the playlist cache."""
    try:
        settings = Settings.from_env()
        playlist_cache_file = Path(settings.cache_playlist_file)
        playlist_name = settings.playlist_name
    except Exception:
        playlist_cache_file = PLAYLIST_CACHE_FILE
        playlist_name = "Last.fm Recents (auto)"

    if not playlist_cache_file.exists():
        return None
    try:
        with playlist_cache_file.open() as f:
            data = json.load(f)

        playlist_entry = data.get(playlist_name, {})
        return playlist_entry.get("last_updated")
    except Exception:
        return None


def get_overrides_data() -> tuple[list[dict], list[dict]]:
    """Get all overrides and blacklist entries."""
    overrides = load_overrides()

    override_list = []
    for key, data in overrides._cache.get("_overrides", {}).items():
        override_list.append(
            {
                "key": key,
                "artist": data.get("artist", key.split("|")[0]),
                "title": data.get("title", key.split("|")[1] if "|" in key else ""),
                "video_id": data.get("video_id"),
                "reason": data.get("reason", ""),
                "timestamp": data.get("timestamp"),
            }
        )

    blacklist = []
    for key, data in overrides._cache.get("_blacklist", {}).items():
        blacklist.append(
            {
                "key": key,
                "artist": data.get("artist", key.split("|")[0]),
                "title": data.get("title", key.split("|")[1] if "|" in key else ""),
                "reason": data.get("reason", ""),
                "timestamp": data.get("timestamp"),
            }
        )

    return override_list, blacklist


FAILURE_LOG_FILE = CACHE_DIR / ".last_failure.json"


def load_failure_log() -> dict | None:
    """Load the last failure log if it exists.

    Returns None if no failure log exists (sync was successful).
    """
    if not FAILURE_LOG_FILE.exists():
        return None
    try:
        with FAILURE_LOG_FILE.open() as f:
            return json.load(f)
    except Exception:
        return None


def clear_failure_log() -> bool:
    """Clear the failure log.

    Returns True if the file was deleted, False otherwise.
    """
    if FAILURE_LOG_FILE.exists():
        try:
            FAILURE_LOG_FILE.unlink()
            return True
        except Exception:
            return False
    return False


def get_playlist_links() -> dict:
    """Get URLs to the main playlist and latest weekly playlist (if exists).

    Returns dict with:
        - main_url: URL to main playlist (or None)
        - main_name: Name of main playlist
        - weekly_url: URL to latest weekly playlist (or None)
        - weekly_name: Name of latest weekly playlist
        - weekly_enabled: Whether weekly playlists are enabled
    """
    try:
        settings = Settings.from_env()
        playlist_cache_file = Path(settings.cache_playlist_file)
        playlist_name = settings.playlist_name
        weekly_enabled = settings.weekly_enabled
        weekly_prefix_base = getattr(settings, "weekly_playlist_prefix", None) or _derive_weekly_prefix(playlist_name)
    except Exception:
        playlist_cache_file = PLAYLIST_CACHE_FILE
        playlist_name = "Last.fm Recents (auto)"
        weekly_enabled = True
        weekly_prefix_base = _derive_weekly_prefix(playlist_name)

    result = {
        "main_url": None,
        "main_name": playlist_name,
        "weekly_url": None,
        "weekly_name": None,
        "weekly_enabled": weekly_enabled,
    }

    if not playlist_cache_file.exists():
        return result

    try:
        with playlist_cache_file.open() as f:
            data = json.load(f)

        main_entry = data.get(playlist_name, {})
        main_id = main_entry.get("id")
        if main_id:
            result["main_url"] = f"https://music.youtube.com/playlist?list={main_id}"

        if weekly_enabled:
            weekly_prefix = f"{weekly_prefix_base} week of "
            weekly_entries = [(name, entry) for name, entry in data.items() if name.startswith(weekly_prefix) and entry.get("id")]
            if weekly_entries:
                weekly_entries.sort(key=lambda x: x[0], reverse=True)
                latest_name, latest_entry = weekly_entries[0]
                result["weekly_url"] = f"https://music.youtube.com/playlist?list={latest_entry['id']}"
                result["weekly_name"] = latest_name

        return result
    except Exception:
        return result
