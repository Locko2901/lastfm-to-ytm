"""API routes for data and settings."""

from __future__ import annotations

import json
import logging
import socket
import threading

import requests
from flask import Blueprint, Response, jsonify, render_template, request
from flask_babel import gettext as _
from requests.adapters import HTTPAdapter

from ..services import (
    ALL_SETTINGS,
    BOOL_SETTINGS,
    ENV_EXAMPLE_FILE,
    ENV_FILE,
    PRIVACY_SETTINGS,
    bulk_delete_search_cache,
    bulk_delete_tag_cache,
    clear_failure_log,
    clear_playlist_cache_all,
    clear_search_cache_all,
    clear_search_cache_notfound,
    clear_tag_cache_all,
    delete_custom_playlist_data,
    get_cache_stats,
    get_cached_tracks,
    get_custom_playlist_tracks,
    get_history_db,
    get_last_sync_time,
    get_not_found_tracks,
    get_overrides_data,
    get_playlist_cache_summary,
    get_playlist_cache_tracks,
    get_playlist_mappings,
    get_setup_status,
    get_tag_cache_tracks,
    get_tag_overrides_data,
    get_tag_stats,
    get_tag_suggestions,
    get_track_tag_overrides_map,
    get_track_tags_map,
    get_update_status,
    is_history_enabled,
    load_custom_playlists_config,
    load_failure_log,
    load_overrides,
    load_run_log,
    load_search_cache,
    parse_env_file,
    remove_playlist_from_cache,
    remove_track_from_playlist_cache,
    reset_history_db,
    save_custom_playlists_config,
    sync_lock,
    sync_state,
    update_env_file,
)
from ..services.scheduler import (
    get_scheduler_status,
    start_scheduler,
)
from ..services.teleporter import export_config, import_config, preview_config

api_bp = Blueprint("api", __name__, url_prefix="/api")

logger = logging.getLogger(__name__)


class IPv4Adapter(HTTPAdapter):
    """HTTP adapter that forces IPv4 connections."""

    def init_poolmanager(self, *args, **kwargs):
        """Initialize pool with IPv4-only options."""
        kwargs["socket_options"] = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]
        import urllib3.util.connection

        _orig_allowed = urllib3.util.connection.allowed_gai_family
        urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
        super().init_poolmanager(*args, **kwargs)
        urllib3.util.connection.allowed_gai_family = _orig_allowed


def get_ipv4_session():
    """Create IPv4-only session."""
    session = requests.Session()
    session.mount("http://", IPv4Adapter())
    session.mount("https://", IPv4Adapter())
    return session


_ipv4_session = None
_ipv4_session_lock = threading.Lock()


def ipv4_session():
    """Get shared IPv4-only session."""
    global _ipv4_session
    if _ipv4_session is None:
        with _ipv4_session_lock:
            if _ipv4_session is None:
                _ipv4_session = get_ipv4_session()
    return _ipv4_session


@api_bp.route("/status")
def status():
    """Get current sync status."""
    with sync_lock:
        return jsonify(
            {
                "running": sync_state["running"],
                "output": list(sync_state["output"])[-100:],
                "started_at": sync_state["started_at"],
                "finished_at": sync_state["finished_at"],
                "exit_code": sync_state["exit_code"],
            }
        )


@api_bp.route("/update-status")
def update_status():
    """Return how many commits the running build is behind ``origin/main``.

    Response keys: ``current`` (short SHA), ``behind_by``, ``compare_url``,
    ``update_available``. Network failures yield ``behind_by=None``.
    """
    return jsonify(get_update_status())


@api_bp.route("/setup/status")
def setup_status():
    """Check if first-time setup is needed."""
    setup = get_setup_status()
    return jsonify(
        {
            "needs_setup": setup["needs_setup"],
            "has_env": setup["has_env"],
            "has_browser_json": setup["has_browser_json"],
        }
    )


@api_bp.route("/setup/init", methods=["POST"])
def setup_init():
    """Initialize .env from .env.example."""
    env_exists = ENV_FILE.exists()
    env_empty = env_exists and ENV_FILE.stat().st_size == 0
    if env_exists and not env_empty:
        return jsonify({"error": _(".env already exists")}), 400

    if not ENV_EXAMPLE_FILE.exists():
        return jsonify({"error": _(".env.example not found")}), 500

    try:
        import shutil

        shutil.copy(ENV_EXAMPLE_FILE, ENV_FILE)
        return jsonify({"status": "created"})
    except OSError as e:
        logger.error(f"Failed to copy .env.example: {e}")
        return jsonify({"error": _("Failed to create configuration file")}), 500


@api_bp.route("/setup/lastfm", methods=["POST"])
def setup_lastfm():
    """Save Last.fm credentials during setup."""
    data = request.get_json()
    if not data:
        return jsonify({"error": _("No data provided")}), 400

    username = data.get("username", "").strip()
    api_key = data.get("api_key", "").strip()

    if not username or not api_key:
        return jsonify({"error": _("Username and API key are required")}), 400

    try:
        update_env_file(
            {
                "LASTFM_USER": username,
                "LASTFM_API_KEY": api_key,
            }
        )
        return jsonify({"status": "saved"})
    except OSError as e:
        logger.error(f"Failed to save Last.fm credentials: {e}")
        return jsonify({"error": _("Failed to save credentials")}), 500


@api_bp.route("/mappings")
def mappings():
    """JSON API for mappings."""
    run_log = load_run_log()
    return jsonify(run_log)


@api_bp.route("/overrides")
def overrides():
    """JSON API for overrides and blacklist."""
    override_list, blacklist = get_overrides_data()
    return jsonify({"overrides": override_list, "blacklist": blacklist})


@api_bp.route("/cache-stats")
def cache_stats():
    """JSON API for cache statistics."""
    return jsonify(get_cache_stats())


@api_bp.route("/settings")
def settings_get():
    """Get current settings from .env file."""
    settings = parse_env_file()
    result = {}
    for key in ALL_SETTINGS:
        value = settings.get(key, "")
        if key in BOOL_SETTINGS:
            result[key] = value.lower() in ("true", "1", "yes", "on", "t", "y")
        elif key in PRIVACY_SETTINGS:
            upper = value.upper()
            if upper in ("PUBLIC", "UNLISTED", "PRIVATE"):
                result[key] = upper
            elif value.lower() in ("true", "1", "yes", "on", "t", "y"):
                result[key] = "PUBLIC"
            elif value.lower() in ("false", "0", "no", "off", "f", "n"):
                result[key] = "PRIVATE"
            else:
                result[key] = value
        else:
            result[key] = value
    return jsonify(result)


@api_bp.route("/settings", methods=["POST"])
def settings_update():
    """Update settings in .env file."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": _("No data provided")}), 400

        updates = {}
        for key, value in data.items():
            if key not in ALL_SETTINGS:
                continue
            if key in BOOL_SETTINGS:
                updates[key] = "true" if value else "false"
            elif key in PRIVACY_SETTINGS:
                upper = str(value).upper() if value else ""
                if upper in ("PUBLIC", "UNLISTED", "PRIVATE"):
                    updates[key] = upper
                else:
                    updates[key] = ""
            else:
                updates[key] = str(value) if value is not None else ""

        cron_val = updates.get("AUTO_SYNC_CRON") or data.get("AUTO_SYNC_CRON", "")
        sync_type = updates.get("AUTO_SYNC_TYPE") or data.get("AUTO_SYNC_TYPE", "")
        sync_enabled = updates.get("AUTO_SYNC_ENABLED", "false").lower() in ("true", "1")
        if sync_enabled and sync_type == "cron" and cron_val:
            try:
                from apscheduler.triggers.cron import CronTrigger

                CronTrigger.from_crontab(cron_val)
            except (ValueError, TypeError) as e:
                return jsonify({"error": _("Invalid cron expression: %(error)s", error=str(e))}), 400
            except ImportError:
                pass

        start_time_val = updates.get("AUTO_SYNC_START_TIME", "")
        if start_time_val:
            try:
                hour, minute = map(int, start_time_val.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    return jsonify({"error": _("Invalid start time: hour must be 0-23, minute 0-59")}), 400
            except (ValueError, AttributeError):
                pass  # Non-strict: empty or partial values are allowed in general settings

        update_env_file(updates)

        if "HISTORY_DB_ENABLED" in updates or "HISTORY_DB_FILE" in updates:
            reset_history_db()

        return jsonify({"status": "saved", "updated": list(updates.keys())})
    except OSError as e:
        logger.error(f"Failed to update settings: {e}")
        return jsonify({"error": _("Failed to save settings")}), 500


@api_bp.route("/webhook/test", methods=["POST"])
def webhook_test():
    """Send a test webhook to verify the URL works."""
    data = request.get_json() or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": _("No webhook URL provided")}), 400

    from src.webhook import send_webhook

    ok = send_webhook(
        url,
        status="test",
        sync_type="test",
        tracks_resolved=42,
        tracks_missed=3,
    )
    if ok:
        return jsonify({"status": "ok"})
    return jsonify({"error": _("Webhook request failed. Check the URL and try again.")}), 502


@api_bp.route("/stats")
def stats():
    """Get all stats for updating the UI dynamically."""
    run_log = load_run_log()
    override_list, blacklist = get_overrides_data()
    cache_stats = get_cache_stats()
    not_found = get_not_found_tracks()
    last_sync = get_last_sync_time()
    tag_stats = get_tag_stats()
    custom_playlists = load_custom_playlists_config()

    resolved = run_log.get("in_playlist", run_log.get("resolved", 0))
    limit = run_log.get("limit", 100)
    playlist_count = min(resolved, limit)

    return jsonify(
        {
            "resolved": playlist_count,
            "overrides": len(override_list),
            "blacklist": len(blacklist),
            "not_found": len(not_found),
            "cached": cache_stats.get("found", 0),
            "last_sync": last_sync,
            "tag_cached": tag_stats.get("total", 0),
            "custom_playlists": len(custom_playlists),
        }
    )


@api_bp.route("/panel/<panel_name>")
def panel_html(panel_name):
    """Get rendered HTML for a specific panel."""
    if panel_name == "playlist":
        playlist_mappings, _ = get_playlist_mappings()
        return render_template(
            "partials/_panel_playlist.html",
            mappings=playlist_mappings,
            track_tags_map=get_track_tags_map(),
            tag_overrides_map=get_track_tag_overrides_map(),
        )
    if panel_name == "blacklist":
        _, blacklist = get_overrides_data()
        return render_template("partials/_panel_blacklist.html", blacklist=blacklist)
    if panel_name == "overrides":
        override_list, _ = get_overrides_data()
        return render_template(
            "partials/_panel_overrides.html",
            overrides=override_list,
            track_tags_map=get_track_tags_map(),
            tag_overrides_map=get_track_tag_overrides_map(),
        )
    if panel_name == "cache":
        cached_tracks = get_cached_tracks()
        return render_template(
            "partials/_panel_cache.html",
            cached_tracks=cached_tracks,
            track_tags_map=get_track_tags_map(),
            tag_overrides_map=get_track_tag_overrides_map(),
        )
    if panel_name == "notfound":
        not_found = get_not_found_tracks()
        return render_template("partials/_panel_notfound.html", not_found_tracks=not_found, track_tags_map=get_track_tags_map())
    if panel_name == "tags":
        tag_cache_tracks = get_tag_cache_tracks()
        tag_overrides_data = get_tag_overrides_data()
        return render_template(
            "partials/_panel_tags.html",
            tag_cache_tracks=tag_cache_tracks,
            tag_overrides=tag_overrides_data,
        )
    if panel_name == "custompl":
        custom_playlists = load_custom_playlists_config()
        return render_template("partials/_panel_custompl.html", custom_playlists=custom_playlists)
    if panel_name == "history":
        return render_template("partials/_panel_history.html", history_enabled=is_history_enabled())
    return jsonify({"error": _("Unknown panel")}), 404


@api_bp.route("/custom-playlists")
def custom_playlists_get():
    """Get custom playlist configurations."""
    return jsonify({"playlists": load_custom_playlists_config()})


@api_bp.route("/custom-playlists", methods=["POST"])
def custom_playlists_save():
    """Save custom playlist configurations."""
    data = request.get_json()
    if not data or "playlists" not in data:
        return jsonify({"error": _("Invalid data: 'playlists' array required")}), 400

    playlists = data["playlists"]
    if not isinstance(playlists, list):
        return jsonify({"error": _("'playlists' must be an array")}), 400

    cleaned = []
    for entry in playlists:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "").strip()
        tags = entry.get("tags", [])
        if not name or not tags:
            continue
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            continue
        match = entry.get("match", "any")
        if match not in ("any", "all"):
            match = "any"
        limit = entry.get("limit", 50)
        if not isinstance(limit, int) or limit < 0:
            limit = 50
        blacklist = entry.get("blacklist", [])
        if not isinstance(blacklist, list):
            blacklist = []
        blacklist = [b for b in blacklist if isinstance(b, str)]
        backfill = entry.get("backfill", True)
        if not isinstance(backfill, bool):
            backfill = True
        auto_sync = entry.get("auto_sync", True)
        if not isinstance(auto_sync, bool):
            auto_sync = True
        description = entry.get("description", "")
        if not isinstance(description, str):
            description = ""
        cleaned.append(
            {
                "name": name,
                "description": description.strip(),
                "tags": [t.lower().strip() for t in tags if t.strip()],
                "match": match,
                "limit": limit,
                "blacklist": [b.lower().strip() for b in blacklist if b.strip()],
                "backfill": backfill,
                "auto_sync": auto_sync,
            }
        )

    try:
        save_custom_playlists_config(cleaned)
        return jsonify({"status": "saved", "count": len(cleaned)})
    except OSError as e:
        logger.error(f"Failed to save custom playlists: {e}")
        return jsonify({"error": _("Failed to save custom playlists")}), 500


@api_bp.route("/tag-overrides")
def tag_overrides_get():
    """Get tag overrides list."""
    return jsonify({"overrides": get_tag_overrides_data()})


@api_bp.route("/tags/suggestions")
def tag_suggestions():
    """Get unique tag names from the tag cache for autocomplete."""
    return jsonify({"tags": get_tag_suggestions()})


@api_bp.route("/custom-playlists/<int:index>", methods=["DELETE"])
def custom_playlist_delete(index: int):
    """Delete a custom playlist, its cache entry, and optionally from YTM."""
    data = request.get_json(silent=True) or {}
    delete_from_ytm = data.get("delete_from_ytm", False)
    result = delete_custom_playlist_data(index, delete_from_ytm=delete_from_ytm)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route("/custom-playlists/<int:index>/tracks")
def custom_playlist_tracks(index: int):
    """Get tracks matching a custom playlist's tag filter, rendered as HTML."""
    tracks = get_custom_playlist_tracks(index)
    return render_template("partials/_custompl_tracks.html", tracks=tracks, pl_index=index, tag_overrides_map=get_track_tag_overrides_map())


@api_bp.route("/failure_log")
def failure_log():
    """Get the last failure log if one exists."""
    log = load_failure_log()
    if log:
        return jsonify({"has_failure": True, **log})
    return jsonify({"has_failure": False})


@api_bp.route("/failure_log", methods=["DELETE"])
def clear_failure():
    """Clear/dismiss the failure log."""
    if clear_failure_log():
        return jsonify({"status": "cleared"})
    return jsonify({"status": "no_log"})


@api_bp.route("/restart", methods=["POST"])
def restart_server():
    """Restart the web server gracefully.

    In production (Gunicorn): Sends HUP to master process for graceful worker reload.
    In development (Flask): Sends SIGTERM to trigger dev server restart.
    In Docker: Container will auto-restart due to restart: unless-stopped policy.
    """
    import os
    import signal
    import threading

    def delayed_restart():
        import time

        time.sleep(0.5)

        gunicorn_master_pid = os.getenv("GUNICORN_PID") or _get_gunicorn_master_pid()

        if gunicorn_master_pid:
            logger.info(f"Sending HUP to Gunicorn master (PID {gunicorn_master_pid})")
            os.kill(gunicorn_master_pid, signal.SIGHUP)
        else:
            logger.info("Sending SIGTERM to current process")
            os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=delayed_restart, daemon=True).start()
    return jsonify({"status": "restarting"})


@api_bp.route("/scheduler/status")
def scheduler_status():
    """Get current scheduler status."""
    return jsonify(get_scheduler_status())


def _get_run_log_source(artist: str, title: str) -> str | None:
    """Read raw run log to find the original source for a track."""
    from ..services.data import RUN_LOG_FILE

    try:
        if not RUN_LOG_FILE.exists():
            return None
        with RUN_LOG_FILE.open() as f:
            data = json.load(f)
        a_lower, t_lower = artist.lower(), title.lower()
        for m in data.get("mappings", []):
            if m.get("artist", "").lower() == a_lower and m.get("title", "").lower() == t_lower:
                return m.get("source")
    except Exception:
        pass
    return None


@api_bp.route("/track-detail")
def track_detail():
    """Get full details for a specific track from all data sources."""
    artist = request.args.get("artist", "").strip()
    title = request.args.get("title", "").strip()

    if not artist or not title:
        return jsonify({"error": _("Artist and title are required")}), 400

    cache = load_search_cache()
    overrides_obj = load_overrides()
    tags_map = get_track_tags_map()
    tag_overrides_map = get_track_tag_overrides_map()

    key = f"{artist.lower()}|{title.lower()}"

    result = {
        "artist": artist,
        "title": title,
        "video_id": None,
        "yt_title": None,
        "source": None,
        "tags": tags_map.get(key, []),
        "has_tag_override": key in tag_overrides_map,
        "is_overridden": False,
        "is_blacklisted": False,
        "cache_timestamp": None,
        "history_times_found": None,
        "history_first_seen": None,
        "history_last_seen": None,
        "history_action_count": None,
    }

    override_vid = overrides_obj.get(artist, title)
    if override_vid:
        result["video_id"] = override_vid
        result["source"] = "override"
        result["is_overridden"] = True

    override_keys = overrides_obj.override_keys()
    blacklist_keys = overrides_obj.blacklist_keys()
    result["is_overridden"] = key in override_keys
    result["is_blacklisted"] = key in blacklist_keys

    entry = cache.get_entry(artist, title)
    if entry:
        result["cache_timestamp"] = entry.get("timestamp")
        if not result["video_id"]:
            result["video_id"] = entry.get("video_id")
            result["yt_title"] = entry.get("yt_title")
            result["source"] = "cache" if entry.get("video_id") else "not_found"

    if result["source"] in ("cache", None):
        result["source"] = _get_run_log_source(artist, title) or result["source"]

    if result["is_blacklisted"] and result["source"] not in ("blacklisted",):
        result["source"] = "blacklisted"

    history_db = get_history_db()
    if history_db:
        history_entry = history_db.get_track_history(artist, title)
        if history_entry:
            result["history_times_found"] = history_entry.get("times_found")
            result["history_first_seen"] = history_entry.get("first_seen")
            result["history_last_seen"] = history_entry.get("last_seen")
            result["history_action_count"] = history_entry.get("action_count")

            if not result["video_id"]:
                result["video_id"] = history_entry.get("video_id")
            if not result["yt_title"]:
                result["yt_title"] = history_entry.get("yt_title")
            if not result["source"]:
                result["source"] = history_entry.get("source")

    return jsonify(result)


@api_bp.route("/now-playing")
def now_playing():
    """Get currently playing track from Last.fm."""
    settings = parse_env_file()
    username = settings.get("LASTFM_USER", "").strip()
    api_key = settings.get("LASTFM_API_KEY", "").strip()

    if not username or not api_key:
        return jsonify({"playing": False, "error": _("Last.fm credentials not configured")})

    try:
        resp = ipv4_session().get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "user.getrecenttracks",
                "user": username,
                "api_key": api_key,
                "format": "json",
                "limit": 1,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        tracks = data.get("recenttracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]

        if not tracks:
            return jsonify({"playing": False})

        track = tracks[0]
        is_playing = track.get("@attr", {}).get("nowplaying") == "true"

        if not is_playing:
            return jsonify({"playing": False})

        artist = ""
        a = track.get("artist")
        if isinstance(a, dict):
            artist = a.get("#text") or ""
        elif isinstance(a, str):
            artist = a or ""

        album = ""
        alb = track.get("album")
        if isinstance(alb, dict):
            album = alb.get("#text") or ""
        elif isinstance(alb, str):
            album = alb

        image_url = ""
        images = track.get("image", [])
        for preferred_size in ["large", "extralarge", "medium", "small"]:
            for img in images:
                if isinstance(img, dict) and img.get("size") == preferred_size:
                    url = img.get("#text", "")
                    if url and not url.endswith("2a96cbd8b46e442fc41c2b86b821562f.png"):
                        image_url = url
                        break
            if image_url:
                break

        return jsonify(
            {
                "playing": True,
                "track": track.get("name", ""),
                "artist": artist.strip(),
                "album": album.strip(),
                "image": image_url,
            }
        )

    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch now playing: {e}")
        return jsonify({"playing": False, "error": _("Failed to fetch from Last.fm")})
    except Exception as e:
        logger.error(f"Error in now-playing endpoint: {e}")
        return jsonify({"playing": False, "error": _("Internal error")})


_image_cache = {}
_image_cache_lock = threading.Lock()
_IMAGE_CACHE_MAX_SIZE = 50
_IMAGE_CACHE_TTL = 3600


@api_bp.route("/image-proxy")
def image_proxy():
    """Proxy external images to enable CORS for canvas color extraction."""
    import time

    from flask import Response

    url = request.args.get("url", "")

    if not url:
        return Response("Missing url parameter", status=400)

    allowed_domains = ["lastfm.freetls.fastly.net", "lastfm-img2.akamaized.net", "i.scdn.co"]
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        if parsed.hostname not in allowed_domains:
            return Response("Domain not allowed", status=403)
    except Exception:
        return Response("Invalid URL", status=400)

    now = time.time()
    with _image_cache_lock:
        if url in _image_cache:
            cached = _image_cache[url]
            if now - cached["time"] < _IMAGE_CACHE_TTL:
                return Response(
                    cached["data"],
                    content_type=cached["content_type"],
                    headers={
                        "Cache-Control": "public, max-age=86400",
                        "Access-Control-Allow-Origin": "*",
                        "X-Cache": "HIT",
                    },
                )
            del _image_cache[url]

    try:
        resp = ipv4_session().get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (compatible; LastFM-YTM-Sync/1.0)"})
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "image/jpeg")
        data = resp.content

        with _image_cache_lock:
            if len(_image_cache) >= _IMAGE_CACHE_MAX_SIZE:
                oldest_key = min(_image_cache.keys(), key=lambda k: _image_cache[k]["time"])
                del _image_cache[oldest_key]

            _image_cache[url] = {
                "data": data,
                "content_type": content_type,
                "time": now,
            }

        return Response(
            data,
            content_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*",
                "X-Cache": "MISS",
            },
        )
    except requests.exceptions.RequestException as e:
        logger.warning(f"Image proxy failed for {url}: {e}")
        return Response("Failed to fetch image", status=502)
    except Exception as e:
        logger.error(f"Image proxy error: {e}")
        return Response("Internal error", status=500)


@api_bp.route("/scheduler/configure", methods=["POST"])
def scheduler_configure():
    """Configure and start/stop the scheduler.

    Also saves the settings to .env for persistence across restarts.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": _("No data provided")}), 400

        enabled = data.get("enabled", False)
        schedule_type = data.get("schedule_type", "interval")
        interval_hours = float(data.get("interval_hours", 6))
        start_time = data.get("start_time", "")
        cron_expression = data.get("cron_expression", "0 */6 * * *")
        tag_sync_enabled = data.get("tag_sync_enabled", False)
        tag_sync_frequency = max(1, int(data.get("tag_sync_frequency", 1)))

        if schedule_type == "cron" and enabled:
            try:
                from apscheduler.triggers.cron import CronTrigger

                CronTrigger.from_crontab(cron_expression)
            except (ValueError, TypeError) as e:
                return jsonify({"error": _("Invalid cron expression: %(error)s", error=str(e))}), 400
            except ImportError:
                pass

        if start_time:
            try:
                hour, minute = map(int, start_time.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    return jsonify({"error": _("Invalid start time: hour must be 0-23, minute 0-59")}), 400
            except (ValueError, AttributeError):
                return jsonify({"error": _("Invalid start time format. Use HH:MM.")}), 400

        update_env_file(
            {
                "AUTO_SYNC_ENABLED": "true" if enabled else "false",
                "AUTO_SYNC_TYPE": schedule_type,
                "AUTO_SYNC_INTERVAL_HOURS": str(interval_hours),
                "AUTO_SYNC_START_TIME": start_time,
                "AUTO_SYNC_CRON": cron_expression,
                "AUTO_TAG_SYNC_ENABLED": "true" if tag_sync_enabled else "false",
                "AUTO_TAG_SYNC_FREQUENCY": str(tag_sync_frequency),
            }
        )

        success = start_scheduler(
            enabled=enabled,
            schedule_type=schedule_type,
            interval_hours=interval_hours,
            start_time=start_time,
            cron_expression=cron_expression,
            tag_sync_enabled=tag_sync_enabled,
        )

        if success:
            return jsonify({"status": "configured", **get_scheduler_status()})
        return jsonify({"error": _("Failed to configure scheduler. APScheduler may not be installed.")}), 500

    except ValueError as e:
        return jsonify({"error": _("Invalid value: %(error)s", error=str(e))}), 400
    except Exception as e:
        logger.error(f"Failed to configure scheduler: {e}")
        return jsonify({"error": _("Failed to configure scheduler")}), 500


@api_bp.route("/teleporter/export", methods=["POST"])
def teleporter_export():
    """Export all config as an encrypted binary file."""
    data = request.get_json()
    if not data or not data.get("password"):
        return jsonify({"error": _("Password is required")}), 400

    password = data["password"]
    if len(password) < 4:
        return jsonify({"error": _("Password must be at least 4 characters")}), 400

    cache_keys = data.get("cache_keys") or []
    if not isinstance(cache_keys, list):
        cache_keys = []

    try:
        encrypted = export_config(password, cache_keys=cache_keys)
        return Response(
            encrypted,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=teleporter-backup.bin"},
        )
    except Exception as e:
        logger.error(f"Teleporter export failed: {e}")
        return jsonify({"error": _("Export failed")}), 500


@api_bp.route("/teleporter/preview", methods=["POST"])
def teleporter_preview():
    """Decrypt and preview contents of a teleporter file without applying."""
    password = request.form.get("password", "")
    file = request.files.get("file")

    if not password:
        return jsonify({"error": _("Password is required")}), 400
    if not file:
        return jsonify({"error": _("No file provided")}), 400

    try:
        file_data = file.read()
        summary = preview_config(file_data, password)
        return jsonify(summary)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Teleporter preview failed: {e}")
        return jsonify({"error": _("Preview failed")}), 500


@api_bp.route("/teleporter/import", methods=["POST"])
def teleporter_import():
    """Decrypt and restore config from a teleporter file."""
    password = request.form.get("password", "")
    file = request.files.get("file")

    if not password:
        return jsonify({"error": _("Password is required")}), 400
    if not file:
        return jsonify({"error": _("No file provided")}), 400

    try:
        file_data = file.read()
        result = import_config(file_data, password)
        return jsonify({"status": "ok", **result})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Teleporter import failed: {e}")
        return jsonify({"error": _("Import failed")}), 500


@api_bp.route("/history/status")
def history_status():
    """Check if history DB is enabled and get overview stats."""
    if not is_history_enabled():
        return jsonify({"enabled": False})
    db = get_history_db()
    if not db:
        return jsonify({"enabled": False})
    stats = db.get_overview_stats()
    stats["enabled"] = True
    stats["db_size_bytes"] = db.get_db_size_bytes()
    return jsonify(stats)


@api_bp.route("/history/tracks")
def history_tracks():
    """Get paginated tracks from history DB."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 50, 0
    sort = request.args.get("sort", "last_seen")
    order = request.args.get("order", "desc")
    search = request.args.get("search", "").strip() or None
    source_filter = request.args.get("source", "").strip() or None
    found_filter = request.args.get("found", "").strip() or None

    tracks = db.get_tracks(limit, offset, sort, order, search, source_filter, found_filter)
    total = db.get_track_count(search, source_filter, found_filter)
    return jsonify({"tracks": tracks, "total": total, "limit": limit, "offset": offset})


@api_bp.route("/history/syncs")
def history_syncs():
    """Get paginated sync history."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 50, 0
    date_from = request.args.get("from", "").strip() or None
    date_to = request.args.get("to", "").strip() or None
    syncs = db.get_syncs(limit, offset, date_from, date_to)
    total = db.get_sync_count(date_from, date_to)
    return jsonify({"syncs": syncs, "total": total, "limit": limit, "offset": offset})


@api_bp.route("/history/syncs/<int:sync_id>")
def history_sync(sync_id: int):
    """Get a single sync record."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    sync_record = db.get_sync(sync_id)
    if not sync_record:
        return jsonify({"error": _("Sync record not found")}), 404

    return jsonify(sync_record)


@api_bp.route("/history/actions")
def history_actions():
    """Get paginated action history."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    try:
        limit = min(int(request.args.get("limit", 100)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 100, 0
    action_type = request.args.get("type", "").strip() or None
    date_from = request.args.get("from", "").strip() or None
    date_to = request.args.get("to", "").strip() or None
    actions = db.get_actions(limit, offset, action_type, date_from, date_to)
    total = db.get_action_count(action_type, date_from, date_to)
    return jsonify({"actions": actions, "total": total, "limit": limit, "offset": offset})


@api_bp.route("/history/top-tracks")
def history_top_tracks():
    """Get most frequently found tracks."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except (ValueError, TypeError):
        limit = 20
    return jsonify({"tracks": db.get_top_tracks(limit)})


@api_bp.route("/history/backfill", methods=["POST"])
def history_backfill():
    """Backfill history DB from existing cache data."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    cache = load_search_cache()
    cache_count = db.backfill_from_search_cache(dict(cache.items()))

    overrides = load_overrides()
    override_items = dict(overrides.override_items())
    override_count = db.backfill_from_overrides(override_items)

    return jsonify(
        {
            "status": "ok",
            "cache_entries": cache_count,
            "override_entries": override_count,
        }
    )


@api_bp.route("/history/clear", methods=["POST"])
def history_clear():
    """Delete all history data (tracks, syncs, actions)."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400
    db.clear_all()
    return jsonify({"status": "cleared"})


@api_bp.route("/history/trend")
def history_trend():
    """Get daily sync trend data for charting."""
    db = get_history_db()
    if not db:
        return jsonify({"error": _("History database is not enabled")}), 400

    try:
        days = min(int(request.args.get("days", 30)), 365)
    except (ValueError, TypeError):
        days = 30
    return jsonify({"trend": db.get_sync_trend(days)})


def _get_gunicorn_master_pid() -> int | None:
    """Find Gunicorn master process PID if running under Gunicorn.

    Returns the master PID, or None if not running under Gunicorn.
    """
    import os
    from pathlib import Path

    try:
        ppid = os.getppid()
        with Path(f"/proc/{ppid}/comm").open() as f:
            parent_name = f.read().strip()
        if parent_name == "gunicorn":
            return ppid
    except OSError:
        pass

    try:
        with Path(f"/proc/{os.getpid()}/cmdline").open() as f:
            cmdline = f.read()
        if "gunicorn" in cmdline:
            ppid = os.getppid()
            if ppid == 1:
                return os.getpid()
            return ppid
    except OSError:
        pass

    return None


@api_bp.route("/cache/summary")
def cache_summary():
    """Aggregate cache stats and the playlist cache contents for the admin modal."""
    return jsonify(
        {
            "search": get_cache_stats(),
            "tags": get_tag_stats(),
            "playlists": get_playlist_cache_summary(),
        }
    )


@api_bp.route("/cache/playlist-tracks")
def cache_playlist_tracks():
    """Resolve a playlist cache template's video IDs to artist/title."""
    name = request.args.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    return jsonify({"name": name, "tracks": get_playlist_cache_tracks(name)})


@api_bp.route("/cache/search/all", methods=["DELETE"])
def cache_clear_search_all():
    """Clear ALL entries from the search cache."""
    deleted = clear_search_cache_all()
    from ..services import history_record_action

    history_record_action("cache_clear_search_all", "", "", detail=f"deleted={deleted}")
    return jsonify({"deleted": deleted})


@api_bp.route("/cache/search/notfound", methods=["DELETE"])
def cache_clear_search_notfound():
    """Clear all not-found entries from the search cache."""
    deleted = clear_search_cache_notfound()
    from ..services import history_record_action

    history_record_action("cache_clear_search_notfound", "", "", detail=f"deleted={deleted}")
    return jsonify({"deleted": deleted})


@api_bp.route("/cache/search/bulk", methods=["DELETE"])
def cache_bulk_delete_search():
    """Bulk-delete search cache entries by raw key list (JSON: {keys: [...]})."""
    payload = request.get_json(silent=True) or {}
    keys = payload.get("keys") or []
    if not isinstance(keys, list):
        return jsonify({"error": "keys must be a list"}), 400
    deleted = bulk_delete_search_cache([str(k) for k in keys])
    from ..services import history_record_action

    history_record_action("cache_clear_search_bulk", "", "", detail=f"deleted={deleted}")
    return jsonify({"deleted": deleted})


@api_bp.route("/cache/tags/all", methods=["DELETE"])
def cache_clear_tags_all():
    """Clear ALL entries from the tag cache."""
    deleted = clear_tag_cache_all()
    from ..services import history_record_action

    history_record_action("cache_clear_tags_all", "", "", detail=f"deleted={deleted}")
    return jsonify({"deleted": deleted})


@api_bp.route("/cache/tags/bulk", methods=["DELETE"])
def cache_bulk_delete_tags():
    """Bulk-delete tag cache entries by raw key list (JSON: {keys: [...]})."""
    payload = request.get_json(silent=True) or {}
    keys = payload.get("keys") or []
    if not isinstance(keys, list):
        return jsonify({"error": "keys must be a list"}), 400
    deleted = bulk_delete_tag_cache([str(k) for k in keys])
    from ..services import history_record_action

    history_record_action("cache_clear_tags_bulk", "", "", detail=f"deleted={deleted}")
    return jsonify({"deleted": deleted})


@api_bp.route("/cache/playlist/all", methods=["DELETE"])
def cache_clear_playlist_all():
    """Clear ENTIRE playlist cache (cache-only, leaves YTM playlists intact)."""
    deleted = clear_playlist_cache_all()
    from ..services import history_record_action

    history_record_action("cache_clear_playlist_all", "", "", detail=f"deleted={deleted}")
    return jsonify({"deleted": deleted})


@api_bp.route("/cache/playlist/entry", methods=["DELETE"])
def cache_clear_playlist_entry():
    """Remove a single playlist from the playlist cache (cache-only)."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    removed = remove_playlist_from_cache(name)
    if not removed:
        return jsonify({"error": "playlist not found in cache"}), 404
    from ..services import history_record_action

    history_record_action("cache_clear_playlist_entry", "", "", detail=name)
    return jsonify({"removed": True, "name": name})


@api_bp.route("/cache/playlist/track", methods=["DELETE"])
def cache_clear_playlist_track():
    """Remove a single video ID from a playlist's cached template."""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    video_id = (payload.get("video_id") or "").strip()
    if not name or not video_id:
        return jsonify({"error": "name and video_id are required"}), 400
    removed = remove_track_from_playlist_cache(name, video_id)
    if not removed:
        return jsonify({"error": "playlist or video_id not found"}), 404
    from ..services import history_record_action

    history_record_action("cache_clear_playlist_track", "", "", detail=f"{name} :: {video_id}")
    return jsonify({"removed": True, "name": name, "video_id": video_id})
