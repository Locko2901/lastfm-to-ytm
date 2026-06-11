"""Data loading and manipulation functions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from flask import g, has_request_context

from src.cache.playlist import PlaylistCache
from src.cache.search import SearchCache, SearchOverrides
from src.cache.tags import TagCache, TagOverrides
from src.config import CACHE_DIR, CONFIG_DIR, Settings, load_custom_playlists
from src.history import HistoryDB
from src.playlist.weekly import _derive_weekly_prefix

from .env import BROWSER_JSON_FILE, ENV_FILE

RUN_LOG_FILE = CACHE_DIR / ".last_run_log.json"
OVERRIDES_FILE = CONFIG_DIR / "search_overrides.json"
SEARCH_CACHE_FILE = CACHE_DIR / ".search_cache.json"
PLAYLIST_CACHE_FILE = CACHE_DIR / ".playlist_cache.json"
TAG_CACHE_FILE = CACHE_DIR / ".tag_cache.json"
TAG_OVERRIDES_FILE = CONFIG_DIR / "tag_overrides.json"
CUSTOM_PLAYLISTS_FILE = CONFIG_DIR / "custom_playlists.json"


def _track_key(artist: str, title: str) -> str:
    """Build artist|title lookup key."""
    return f"{artist.lower()}|{title.lower()}"


def _parse_artist_title_from_key(key: str) -> tuple[str, str]:
    """Extract artist/title from key."""
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
    return cast("Settings | None", g._settings)


def load_run_log() -> dict[str, Any]:
    """Load the last run log and enrich with data from cache/overrides.

    The run log only stores minimal data (artist, title, source).
    We pull video_id and yt_title from the search cache/overrides.
    """
    if not RUN_LOG_FILE.exists():
        return {"mappings": [], "limit": 100, "timestamp": None, "total": 0, "resolved": 0, "in_playlist": 0}
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
        in_playlist = 0

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
                in_playlist += 1
            elif pending_retry:
                in_playlist += 1

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
            "in_playlist": in_playlist,
        }
    except Exception:
        return {"mappings": [], "limit": 100, "timestamp": None, "total": 0, "resolved": 0, "in_playlist": 0}


def load_overrides() -> SearchOverrides:
    """Load search overrides."""
    if "_overrides" not in g:
        g._overrides = SearchOverrides(str(OVERRIDES_FILE))
    return cast("SearchOverrides", g._overrides)


def load_search_cache() -> SearchCache:
    """Load search cache."""
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
    return cast("SearchCache", g._search_cache)


def get_cache_stats() -> dict[str, Any]:
    """Get cache statistics."""
    stats = load_search_cache().stats()
    return {"total": stats["total"], "found": stats["found"], "not_found": stats["notfound"]}


def get_not_found_tracks() -> list[dict[str, Any]]:
    """Get tracks with null video_id."""
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


def get_cached_tracks() -> list[dict[str, Any]]:
    """Get found tracks from the search cache."""
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


def _get_playlist_context() -> dict[str, Any]:
    """Resolve playlist cache file, name, and weekly settings from config.

    Returns dict[str, Any] with keys: cache_file, name, weekly_enabled, weekly_prefix.
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


def load_playlist_cache() -> PlaylistCache:
    """Load playlist cache (lazy, per-request)."""
    if "_playlist_cache" not in g:
        ctx = _get_playlist_context()
        g._playlist_cache = PlaylistCache(str(ctx["cache_file"]))
    return cast("PlaylistCache", g._playlist_cache)


def get_playlist_cache_summary() -> list[dict[str, Any]]:
    """List cached playlists with id, video_count, last_updated."""
    return load_playlist_cache().summary()


def get_playlist_cache_tracks(playlist_name: str) -> list[dict[str, Any]]:
    """Resolve a playlist cache template's video IDs to artist/title via search cache."""
    pc = load_playlist_cache()
    video_ids = pc.get_video_ids(playlist_name)
    if not video_ids:
        return []

    sc = load_search_cache()
    overrides = load_overrides()

    vid_to_info: dict[str, dict[str, Any]] = {}
    for sc_entry in sc.values():
        vid = sc_entry.get("video_id")
        if vid and vid not in vid_to_info:
            vid_to_info[vid] = {
                "artist": sc_entry.get("artist", ""),
                "title": sc_entry.get("title", ""),
                "yt_title": sc_entry.get("yt_title"),
                "source": "cache",
            }
    for _key, ov_entry in overrides.override_items():
        vid = ov_entry.get("video_id")
        if vid and vid not in vid_to_info:
            vid_to_info[vid] = {
                "artist": ov_entry.get("artist", ""),
                "title": ov_entry.get("title", ""),
                "yt_title": None,
                "source": "override",
            }

    return [
        {
            "video_id": vid,
            **vid_to_info.get(vid, {"artist": "", "title": "", "yt_title": None, "source": "unknown"}),
        }
        for vid in video_ids
    ]


def remove_playlist_from_cache(playlist_name: str) -> bool:
    """Remove a single playlist entry from the playlist cache (cache-only)."""
    pc = load_playlist_cache()
    if playlist_name in pc._cache:
        pc.remove(playlist_name)
        return True
    return False


def remove_track_from_playlist_cache(playlist_name: str, video_id: str) -> bool:
    """Remove a video ID from a playlist's cached template."""
    return load_playlist_cache().remove_video_id(playlist_name, video_id)


def clear_playlist_cache_all() -> int:
    """Clear all playlist cache entries. Returns count removed."""
    pc = load_playlist_cache()
    n = len(pc._cache)
    pc.clear()
    return n


def clear_search_cache_all() -> int:
    """Clear all search cache entries. Returns count removed."""
    sc = load_search_cache()
    n = len(sc._cache)
    sc.clear()
    return n


def clear_search_cache_notfound() -> int:
    """Clear all not-found entries from search cache. Returns count removed."""
    return load_search_cache().clear_notfound()


def clear_tag_cache_all() -> int:
    """Clear all tag cache entries. Returns count removed."""
    tc = load_tag_cache()
    n = len(tc._cache)
    tc.clear()
    return n


def bulk_delete_search_cache(keys: list[str]) -> int:
    """Delete multiple search cache entries by raw key. Returns count deleted."""
    return load_search_cache().delete_keys(keys)


def bulk_delete_tag_cache(keys: list[str]) -> int:
    """Delete multiple tag cache entries by raw key. Returns count deleted."""
    return load_tag_cache().delete_keys(keys)


def get_last_sync_time() -> str | None:
    """Get last sync time from playlist cache."""
    ctx = _get_playlist_context()

    if not ctx["cache_file"].exists():
        return None
    try:
        with ctx["cache_file"].open() as f:
            data = json.load(f)

        playlist_entry = data.get(ctx["name"], {})
        return cast("str | None", playlist_entry.get("last_updated"))
    except Exception:
        return None


def get_overrides_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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


def load_failure_log() -> dict[str, Any] | None:
    """Load the last failure log if it exists.

    Returns None if no failure log exists (sync was successful).
    """
    if not FAILURE_LOG_FILE.exists():
        return None
    try:
        with FAILURE_LOG_FILE.open() as f:
            return cast("dict[str, Any] | None", json.load(f))
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


def get_playlist_links() -> dict[str, Any]:
    """Get URLs to the main playlist and latest weekly playlist (if exists).

    Returns dict[str, Any] with:
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


def get_playlist_mappings() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build the playlist mappings list with override/blacklist annotations.

    Returns:
        Tuple of (playlist_mappings list, run_log dict[str, Any]).
    """
    run_log = load_run_log()
    overrides = load_overrides()
    override_keys = overrides.override_keys()
    blacklist_keys = overrides.blacklist_keys()

    playlist_mappings: list[dict[str, Any]] = []
    for m in run_log["mappings"]:
        if (m.get("video_id") or m.get("pending_retry")) and len(playlist_mappings) < run_log["limit"]:
            key = _track_key(m["artist"], m["title"])
            m["is_blacklisted"] = key in blacklist_keys
            m["is_overridden"] = key in override_keys
            m["ytm_url"] = f"https://music.youtube.com/watch?v={m['video_id']}" if m.get("video_id") else None
            playlist_mappings.append(m)

    return playlist_mappings, run_log


def _env_has_user_config(path: Path) -> bool:
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


def get_setup_status() -> dict[str, Any]:
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


def load_tag_cache() -> TagCache:
    """Load tag cache."""
    if "_tag_cache" not in g:
        settings = _get_settings()
        if settings:
            g._tag_cache = TagCache(settings.tag_cache_file, ttl_days=settings.tag_cache_ttl_days)
        else:
            g._tag_cache = TagCache(str(TAG_CACHE_FILE))
    return cast("TagCache", g._tag_cache)


def load_tag_overrides() -> TagOverrides:
    """Load tag overrides."""
    if "_tag_overrides" not in g:
        settings = _get_settings()
        if settings:
            g._tag_overrides = TagOverrides(settings.tag_overrides_file)
        else:
            g._tag_overrides = TagOverrides(str(TAG_OVERRIDES_FILE))
    return cast("TagOverrides", g._tag_overrides)


def get_tag_stats() -> dict[str, Any]:
    """Get tag cache statistics."""
    return load_tag_cache().stats()


def get_tag_cache_tracks() -> list[dict[str, Any]]:
    """Get tag cache tracks with override annotations."""
    cache = load_tag_cache()
    overrides = load_tag_overrides()
    tracks = []
    seen_keys: set[str] = set()

    for key, entry in cache.items():
        seen_keys.add(key)
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        artist = entry.get("artist", fb_artist)
        title = entry.get("title", fb_title)
        raw_tags = entry.get("tags", [])
        final_tags = overrides.apply(artist, title, raw_tags)
        override_result = overrides.get(artist, title)
        has_override = override_result is not None
        override_mode = override_result[1] if override_result else None
        override_tags = [t["name"] for t in override_result[0]] if override_result else []
        lastfm_tags = [t["name"] for t in raw_tags if isinstance(t, dict)]
        tracks.append(
            {
                "key": key,
                "artist": artist,
                "title": title,
                "tags": final_tags,
                "lastfm_tags": lastfm_tags,
                "has_override": has_override,
                "override_mode": override_mode,
                "override_tags": override_tags,
                "timestamp": entry.get("timestamp"),
            }
        )

    for key, data in overrides.items():
        if key in seen_keys:
            continue
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        artist = data.get("artist", fb_artist)
        title = data.get("title", fb_title)
        override_result = overrides.get(artist, title)
        if not override_result:
            continue
        override_tag_objs, mode = override_result
        override_tags = [t["name"] for t in override_tag_objs]
        tracks.append(
            {
                "key": key,
                "artist": artist,
                "title": title,
                "tags": override_tag_objs,
                "lastfm_tags": [],
                "has_override": True,
                "override_mode": mode,
                "override_tags": override_tags,
                "timestamp": data.get("timestamp"),
            }
        )

    tracks.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return tracks


def get_tag_overrides_data() -> list[dict[str, Any]]:
    """Get all tag override entries."""
    overrides = load_tag_overrides()
    result = []
    for key, data in overrides.items():
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        result.append(
            {
                "key": key,
                "artist": data.get("artist", fb_artist),
                "title": data.get("title", fb_title),
                "tags": data.get("tags", []),
                "mode": data.get("mode", "add"),
                "reason": data.get("reason", ""),
            }
        )
    return result


def get_track_tags_map() -> dict[str, list[str]]:
    """Build artist|title → tag names map."""
    cache = load_tag_cache()
    overrides = load_tag_overrides()
    settings = _get_settings()
    min_count = settings.tag_min_count if settings else 10
    tag_map: dict[str, list[str]] = {}
    for key, entry in cache.items():
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        artist = entry.get("artist", fb_artist)
        title = entry.get("title", fb_title)
        raw_tags = entry.get("tags", [])
        final_tags = overrides.apply(artist, title, raw_tags)
        tag_names = [t["name"] for t in final_tags if isinstance(t, dict) and t.get("count", 0) >= min_count]
        if tag_names:
            tag_map[key] = tag_names
    for key, data in overrides.items():
        if key in tag_map:
            continue
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        result = overrides.get(data.get("artist", fb_artist), data.get("title", fb_title))
        if result:
            tag_names = [t["name"] for t in result[0]]
            if tag_names:
                tag_map[key] = tag_names
    return tag_map


def get_track_tag_overrides_map() -> dict[str, dict[str, Any]]:
    """Build artist|title → tag overrides map."""
    overrides = load_tag_overrides()
    result: dict[str, dict[str, Any]] = {}
    for key, data in overrides.items():
        fb_artist, fb_title = _parse_artist_title_from_key(key)
        artist = data.get("artist", fb_artist)
        title = data.get("title", fb_title)
        override_result = overrides.get(artist, title)
        if override_result:
            tag_names = [t["name"] for t in override_result[0]]
            result[key] = {"tags": ", ".join(tag_names)}
    return result


def get_tag_suggestions() -> list[str]:
    """Get sorted unique tag names."""
    cache = load_tag_cache()
    overrides = load_tag_overrides()
    settings = _get_settings()
    min_count = settings.tag_min_count if settings else 10
    counts: dict[str, int] = {}
    for _key, entry in cache.items():
        fb_artist, fb_title = _parse_artist_title_from_key(_key)
        artist = entry.get("artist", fb_artist)
        title = entry.get("title", fb_title)
        final_tags = overrides.apply(artist, title, entry.get("tags", []))
        for t in final_tags:
            if isinstance(t, dict) and t.get("count", 0) >= min_count:
                name = t["name"].lower()
                counts[name] = counts.get(name, 0) + 1
    for _key, data in overrides.items():
        for tag_name in data.get("tags", []):
            name = tag_name.lower() if isinstance(tag_name, str) else ""
            if name and name not in counts:
                counts[name] = 1
    return sorted(counts, key=lambda n: counts[n], reverse=True)


def load_custom_playlists_config() -> list[dict[str, Any]]:
    """Load custom playlist configs for the web UI."""
    settings = _get_settings()
    path = settings.custom_playlists_file if settings else str(CUSTOM_PLAYLISTS_FILE)
    configs = load_custom_playlists(path)

    cache_file = Path(settings.cache_playlist_file) if settings else PLAYLIST_CACHE_FILE
    cache_data: dict[str, Any] = {}
    if cache_file.exists():
        try:
            with cache_file.open() as f:
                cache_data = json.load(f)
        except Exception:
            pass

    return [
        {
            "name": c.name,
            "description": c.description,
            "tags": list(c.tags),
            "match": c.match,
            "limit": c.limit,
            "blacklist": sorted(c.blacklist),
            "backfill": c.backfill,
            "auto_sync": c.auto_sync,
            "track_count": len(cache_data.get(c.name, {}).get("video_ids", [])),
            "playlist_id": cache_data.get(c.name, {}).get("id"),
        }
        for c in configs
    ]


def save_custom_playlists_config(playlists: list[dict[str, Any]]) -> None:
    """Save custom playlist configs atomically."""
    settings = _get_settings()
    path = Path(settings.custom_playlists_file if settings else str(CUSTOM_PLAYLISTS_FILE))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(".tmp")
    with temp_file.open("w") as f:
        json.dump({"playlists": playlists}, f, indent=2)
    temp_file.replace(path)


def delete_custom_playlist_data(index: int, delete_from_ytm: bool = False) -> dict[str, Any]:
    """Delete a custom playlist: config, cache entry, and optionally from YTM.

    Returns a result dict[str, Any] with status info and any warnings.
    """
    import logging

    log = logging.getLogger(__name__)
    playlists = load_custom_playlists_config()
    if index < 0 or index >= len(playlists):
        return {"error": "Invalid playlist index"}

    pl = playlists[index]
    name = pl["name"]
    warnings: list[str] = []

    settings = _get_settings()
    cache_file = Path(settings.cache_playlist_file) if settings else PLAYLIST_CACHE_FILE
    ytm_playlist_id = None
    if cache_file.exists():
        try:
            with cache_file.open() as f:
                cache_data = json.load(f)
            ytm_playlist_id = cache_data.get(name, {}).get("id")
            if name in cache_data:
                del cache_data[name]
                temp_file = cache_file.with_suffix(".tmp")
                with temp_file.open("w") as f:
                    json.dump(cache_data, f, indent=2)
                temp_file.replace(cache_file)
        except Exception as e:
            log.warning("Failed to remove '%s' from playlist cache: %s", name, e)
            warnings.append("Failed to remove from playlist cache")

    if delete_from_ytm and ytm_playlist_id:
        try:
            from ytmusicapi import YTMusic

            yt = YTMusic(str(BROWSER_JSON_FILE))
            yt.delete_playlist(ytm_playlist_id)
        except Exception as e:
            log.warning("Failed to delete playlist '%s' from YTM: %s", name, e)
            warnings.append("Failed to delete from YouTube Music")

    updated = [p for i, p in enumerate(playlists) if i != index]
    save_custom_playlists_config(updated)

    return {"status": "deleted", "name": name, "warnings": warnings}


def get_custom_playlist_tracks(index: int) -> list[dict[str, Any]]:
    """Return tracks that are actually in a custom playlist (from playlist cache).

    Mirrors the main playlist approach: reads the synced video IDs from the
    playlist cache, then reverse-resolves to artist/title via the search cache.
    """
    playlists = load_custom_playlists_config()
    if index < 0 or index >= len(playlists):
        return []
    pl = playlists[index]
    playlist_name = pl["name"]
    blacklist_set = {b.lower() for b in pl.get("blacklist", [])}

    settings = _get_settings()
    cache_file = Path(settings.cache_playlist_file) if settings else PLAYLIST_CACHE_FILE
    if not cache_file.exists():
        return []

    try:
        with cache_file.open() as f:
            cache_data = json.load(f)
    except Exception:
        return []

    entry = cache_data.get(playlist_name, {})
    video_ids = entry.get("video_ids", [])
    if not video_ids:
        return []

    search_cache = load_search_cache()
    overrides = load_overrides()
    override_keys = overrides.override_keys()
    blacklist_keys = overrides.blacklist_keys()

    vid_to_info: dict[str, dict[str, Any]] = {}
    for _key, sc_entry in search_cache.items():
        vid = sc_entry.get("video_id")
        if vid and vid not in vid_to_info:
            fb_artist, fb_title = _parse_artist_title_from_key(_key)
            vid_to_info[vid] = {
                "artist": sc_entry.get("artist", fb_artist),
                "title": sc_entry.get("title", fb_title),
                "yt_title": sc_entry.get("yt_title"),
                "source": "cache",
            }
    for _key, ov_entry in overrides.override_items():
        vid = ov_entry.get("video_id")
        if vid and vid not in vid_to_info:
            fb_artist, fb_title = _parse_artist_title_from_key(_key)
            vid_to_info[vid] = {
                "artist": ov_entry.get("artist", fb_artist),
                "title": ov_entry.get("title", fb_title),
                "yt_title": None,
                "source": "override",
            }

    tag_cache = load_tag_cache()
    tag_overrides = load_tag_overrides()
    min_count = settings.tag_min_count if settings else 10

    results = []
    for vid in video_ids:
        info = vid_to_info.get(vid)
        if not info:
            continue

        artist = info["artist"]
        title = info["title"]

        raw_tags = tag_cache.get(artist, title) or []
        final_tags = tag_overrides.apply(artist, title, raw_tags)
        display_tags = [t["name"] for t in final_tags if isinstance(t, dict) and t.get("count", 0) >= min_count]

        override_key = _track_key(artist, title)
        is_overridden = override_key in override_keys
        is_blacklisted = override_key in blacklist_keys

        bl_key = f"{artist.lower()}|{title.lower()}"
        is_pl_blacklisted = bl_key in blacklist_set

        results.append(
            {
                "artist": artist,
                "title": title,
                "tags": display_tags,
                "video_id": vid,
                "yt_title": info.get("yt_title"),
                "ytm_url": f"https://music.youtube.com/watch?v={vid}",
                "source": info.get("source", "cache"),
                "is_overridden": is_overridden,
                "is_blacklisted": is_blacklisted,
                "is_playlist_blacklisted": is_pl_blacklisted,
            }
        )

    return results


_history_db: HistoryDB | None = None


def get_history_db() -> HistoryDB | None:
    """Return the shared HistoryDB instance, or None if disabled.

    Works both inside Flask request context and from background threads
    (e.g. scheduler).
    """
    global _history_db
    if _history_db is not None:
        return _history_db

    if has_request_context():
        settings = _get_settings()
    else:
        try:
            settings = Settings.from_env()
        except Exception:
            return None

    if not settings or not settings.history_db_enabled:
        return None

    _history_db = HistoryDB(settings.history_db_file)
    return _history_db


def reset_history_db() -> None:
    """Reset the cached HistoryDB instance (e.g. after settings change)."""
    global _history_db
    if _history_db is not None:
        _history_db.close()
    _history_db = None


def is_history_enabled() -> bool:
    """Check if history DB is enabled in settings."""
    settings = _get_settings()
    return bool(settings and settings.history_db_enabled)


def history_record_action(
    action_type: str,
    artist: str | None = None,
    title: str | None = None,
    video_id: str | None = None,
    detail: str | None = None,
    source: str = "web",
) -> None:
    """Record an action in the history DB if enabled."""
    db = get_history_db()
    if db:
        db.record_action(action_type, artist, title, video_id, detail, source)
