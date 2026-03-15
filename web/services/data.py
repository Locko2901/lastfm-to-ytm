"""Data loading and manipulation functions."""

from __future__ import annotations

import json
from pathlib import Path

from flask import g

from src.cache.search import SearchCache, SearchOverrides
from src.config import CACHE_DIR, CONFIG_DIR, Settings
from src.playlist.weekly import _derive_weekly_prefix

from .env import BROWSER_JSON_FILE, ENV_FILE

RUN_LOG_FILE = CACHE_DIR / ".last_run_log.json"
OVERRIDES_FILE = CONFIG_DIR / "search_overrides.json"
SEARCH_CACHE_FILE = CACHE_DIR / ".search_cache.json"
PLAYLIST_CACHE_FILE = CACHE_DIR / ".playlist_cache.json"


def _track_key(artist: str, title: str) -> str:
    """Build a normalised `artist|title` lookup key."""
    return f"{artist.lower()}|{title.lower()}"


def _parse_artist_title_from_key(key: str) -> tuple[str, str]:
    """Extract (artist, title) fallback from a pipe-delimited cache key."""
    parts = key.split("|", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def _get_settings() -> Settings | None:
    """Return Settings cached on the current request (Flask `g`).

    Returns None when the .env file is missing or unparseable.
    """
    if "_settings" not in g:
        try:
            g._settings = Settings.from_env()
        except Exception:
            g._settings = None
    return g._settings


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

        settings = _get_settings()
        limit = settings.limit if settings else 100

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
    """Load search overrides (cached per request)."""
    if "_overrides" not in g:
        g._overrides = SearchOverrides(str(OVERRIDES_FILE))
    return g._overrides


def load_search_cache() -> SearchCache:
    """Load search cache (cached per request)."""
    if "_search_cache" not in g:
        settings = _get_settings()
        if settings:
            g._search_cache = SearchCache(
                settings.cache_search_file,
                ttl_days=settings.cache_search_ttl_days,
                notfound_ttl_days=settings.cache_notfound_ttl_days,
            )
        else:
            g._search_cache = SearchCache(str(SEARCH_CACHE_FILE))
    return g._search_cache


def get_cache_stats() -> dict:
    """Get cache statistics."""
    stats = load_search_cache().stats()
    return {"total": stats["total"], "found": stats["found"], "not_found": stats["notfound"]}


def get_not_found_tracks() -> list[dict]:
    """Get all tracks from the search cache that have null video_id."""
    cache = load_search_cache()
    not_found = []
    for key, entry in cache.items():
        if not entry.get("video_id"):
            fb_artist, fb_title = _parse_artist_title_from_key(key)
            not_found.append(
                {
                    "key": key,
                    "artist": entry.get("artist", fb_artist),
                    "title": entry.get("title", fb_title),
                    "timestamp": entry.get("timestamp"),
                }
            )
    not_found.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return not_found


def get_cached_tracks() -> list[dict]:
    """Get all tracks from the search cache that have a video_id (found tracks)."""
    cache = load_search_cache()
    overrides = load_overrides()
    override_keys = overrides.override_keys()
    blacklist_keys = overrides.blacklist_keys()
    cached = []
    for key, entry in cache.items():
        video_id = entry.get("video_id")
        if video_id:
            fb_artist, fb_title = _parse_artist_title_from_key(key)
            override_key = _track_key(entry.get("artist", ""), entry.get("title", ""))
            cached.append(
                {
                    "key": key,
                    "artist": entry.get("artist", fb_artist),
                    "title": entry.get("title", fb_title),
                    "video_id": video_id,
                    "yt_title": entry.get("yt_title"),
                    "timestamp": entry.get("timestamp"),
                    "has_override": override_key in override_keys,
                    "is_blacklisted": override_key in blacklist_keys,
                }
            )
    cached.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return cached


def _get_playlist_context() -> dict:
    """Resolve playlist cache file, name, and weekly settings from config.

    Returns dict with keys: cache_file, name, weekly_enabled, weekly_prefix.
    """
    settings = _get_settings()
    if settings:
        name = settings.playlist_name
        return {
            "cache_file": Path(settings.cache_playlist_file),
            "name": name,
            "weekly_enabled": settings.weekly_enabled,
            "weekly_prefix": getattr(settings, "weekly_playlist_prefix", None) or _derive_weekly_prefix(name),
        }
    name = "Last.fm Recents (auto)"
    return {
        "cache_file": PLAYLIST_CACHE_FILE,
        "name": name,
        "weekly_enabled": True,
        "weekly_prefix": _derive_weekly_prefix(name),
    }


def get_last_sync_time() -> str | None:
    """Get the last sync time from the playlist cache."""
    ctx = _get_playlist_context()

    if not ctx["cache_file"].exists():
        return None
    try:
        with ctx["cache_file"].open() as f:
            data = json.load(f)

        playlist_entry = data.get(ctx["name"], {})
        return playlist_entry.get("last_updated")
    except Exception:
        return None


def get_overrides_data() -> tuple[list[dict], list[dict]]:
    """Get all overrides and blacklist entries."""
    overrides = load_overrides()

    override_list = []
    for key, data in overrides.override_items():
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        override_list.append(
            {
                "key": key,
                "artist": data.get("artist", fb_artist),
                "title": data.get("title", fb_title),
                "video_id": data.get("video_id"),
                "reason": data.get("reason", ""),
                "timestamp": data.get("timestamp"),
            }
        )

    blacklist = []
    for key, data in overrides.blacklist_items():
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        blacklist.append(
            {
                "key": key,
                "artist": data.get("artist", fb_artist),
                "title": data.get("title", fb_title),
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
    ctx = _get_playlist_context()
    playlist_cache_file = ctx["cache_file"]
    playlist_name = ctx["name"]
    weekly_enabled = ctx["weekly_enabled"]
    weekly_prefix_base = ctx["weekly_prefix"]

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


def get_playlist_mappings() -> tuple[list[dict], dict]:
    """Build the playlist mappings list with override/blacklist annotations.

    Returns:
        Tuple of (playlist_mappings list, run_log dict).
    """
    run_log = load_run_log()
    overrides = load_overrides()
    override_keys = overrides.override_keys()
    blacklist_keys = overrides.blacklist_keys()

    playlist_mappings = []
    for m in run_log["mappings"]:
        if (m.get("video_id") or m.get("pending_retry")) and len(playlist_mappings) < run_log["limit"]:
            key = _track_key(m["artist"], m["title"])
            m["is_blacklisted"] = key in blacklist_keys
            m["is_overridden"] = key in override_keys
            m["ytm_url"] = f"https://music.youtube.com/watch?v={m['video_id']}" if m.get("video_id") else None
            playlist_mappings.append(m)

    return playlist_mappings, run_log


def _env_has_user_config(path) -> bool:
    """Return True if .env contains user-supplied config (not just auto-generated keys)."""
    auto_keys = {"FLASK_SECRET_KEY"}
    try:
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            key = stripped.split("=", 1)[0].strip()
            if key not in auto_keys:
                return True
    except OSError:
        return False
    return False


def get_setup_status() -> dict:
    """Check if first-time setup is needed.

    Returns:
        Dict with keys: needs_setup, has_env, has_browser_json, needs_auth.
    """
    env_exists = ENV_FILE.exists()
    env_empty = not _env_has_user_config(ENV_FILE)
    needs_setup = not env_exists or env_empty

    browser_exists = BROWSER_JSON_FILE.exists()
    browser_valid = browser_exists and BROWSER_JSON_FILE.stat().st_size > 3  # {} is 2-3 bytes

    return {
        "needs_setup": needs_setup,
        "has_env": env_exists and not env_empty,
        "has_browser_json": browser_valid,
        "needs_auth": env_exists and not env_empty and not browser_valid,
    }
