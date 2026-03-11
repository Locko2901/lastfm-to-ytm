"""API routes for data and settings."""

from __future__ import annotations

import logging
import socket
import threading

import requests
from flask import Blueprint, jsonify, render_template, request
from requests.adapters import HTTPAdapter

from ..services import (
    ALL_SETTINGS,
    BOOL_SETTINGS,
    ENV_EXAMPLE_FILE,
    ENV_FILE,
    clear_failure_log,
    get_cache_stats,
    get_cached_tracks,
    get_last_sync_time,
    get_not_found_tracks,
    get_overrides_data,
    get_playlist_mappings,
    get_setup_status,
    load_failure_log,
    load_run_log,
    parse_env_file,
    sync_lock,
    sync_state,
    update_env_file,
)
from ..services.scheduler import (
    get_scheduler_status,
    start_scheduler,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")

logger = logging.getLogger(__name__)


class IPv4Adapter(HTTPAdapter):
    """HTTP adapter that forces IPv4 connections."""

    def init_poolmanager(self, *args, **kwargs):
        """Initialize pool manager with IPv4-only socket options."""
        kwargs["socket_options"] = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]
        import urllib3.util.connection

        _orig_allowed = urllib3.util.connection.allowed_gai_family
        urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
        super().init_poolmanager(*args, **kwargs)
        urllib3.util.connection.allowed_gai_family = _orig_allowed


def get_ipv4_session():
    """Create a requests session that only uses IPv4."""
    session = requests.Session()
    session.mount("http://", IPv4Adapter())
    session.mount("https://", IPv4Adapter())
    return session


_ipv4_session = None
_ipv4_session_lock = threading.Lock()


def ipv4_session():
    """Return the shared IPv4-only requests session, creating it if needed."""
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
        return jsonify({"error": ".env already exists"}), 400

    if not ENV_EXAMPLE_FILE.exists():
        return jsonify({"error": ".env.example not found"}), 500

    try:
        import shutil

        shutil.copy(ENV_EXAMPLE_FILE, ENV_FILE)
        return jsonify({"status": "created"})
    except OSError as e:
        logger.error(f"Failed to copy .env.example: {e}")
        return jsonify({"error": "Failed to create configuration file"}), 500


@api_bp.route("/setup/lastfm", methods=["POST"])
def setup_lastfm():
    """Save Last.fm credentials during setup."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get("username", "").strip()
    api_key = data.get("api_key", "").strip()

    if not username or not api_key:
        return jsonify({"error": "Username and API key are required"}), 400

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
        return jsonify({"error": "Failed to save credentials"}), 500


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
        else:
            result[key] = value
    return jsonify(result)


@api_bp.route("/settings", methods=["POST"])
def settings_update():
    """Update settings in .env file."""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        updates = {}
        for key, value in data.items():
            if key not in ALL_SETTINGS:
                continue
            if key in BOOL_SETTINGS:
                updates[key] = "true" if value else "false"
            else:
                updates[key] = str(value) if value is not None else ""

        update_env_file(updates)
        return jsonify({"status": "saved", "updated": list(updates.keys())})
    except OSError as e:
        logger.error(f"Failed to update settings: {e}")
        return jsonify({"error": "Failed to save settings"}), 500


@api_bp.route("/stats")
def stats():
    """Get all stats for updating the UI dynamically."""
    run_log = load_run_log()
    override_list, blacklist = get_overrides_data()
    cache_stats = get_cache_stats()
    not_found = get_not_found_tracks()
    last_sync = get_last_sync_time()

    resolved = run_log.get("resolved", 0)
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
        }
    )


@api_bp.route("/panel/<panel_name>")
def panel_html(panel_name):
    """Get rendered HTML for a specific panel."""
    if panel_name == "playlist":
        playlist_mappings, _ = get_playlist_mappings()
        return render_template("partials/_panel_playlist.html", mappings=playlist_mappings)
    if panel_name == "blacklist":
        _, blacklist = get_overrides_data()
        return render_template("partials/_panel_blacklist.html", blacklist=blacklist)
    if panel_name == "overrides":
        override_list, _ = get_overrides_data()
        return render_template("partials/_panel_overrides.html", overrides=override_list)
    if panel_name == "cache":
        cached_tracks = get_cached_tracks()
        return render_template("partials/_panel_cache.html", cached_tracks=cached_tracks)
    if panel_name == "notfound":
        not_found = get_not_found_tracks()
        return render_template("partials/_panel_notfound.html", not_found_tracks=not_found)
    return jsonify({"error": "Unknown panel"}), 404


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


@api_bp.route("/now-playing")
def now_playing():
    """Get currently playing track from Last.fm."""
    settings = parse_env_file()
    username = settings.get("LASTFM_USER", "").strip()
    api_key = settings.get("LASTFM_API_KEY", "").strip()

    if not username or not api_key:
        return jsonify({"playing": False, "error": "Last.fm credentials not configured"})

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
        return jsonify({"playing": False, "error": "Failed to fetch from Last.fm"})
    except Exception as e:
        logger.error(f"Error in now-playing endpoint: {e}")
        return jsonify({"playing": False, "error": "Internal error"})


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
            return jsonify({"error": "No data provided"}), 400

        enabled = data.get("enabled", False)
        schedule_type = data.get("schedule_type", "interval")
        interval_hours = float(data.get("interval_hours", 6))
        start_time = data.get("start_time", "")
        cron_expression = data.get("cron_expression", "0 */6 * * *")

        update_env_file(
            {
                "AUTO_SYNC_ENABLED": "true" if enabled else "false",
                "AUTO_SYNC_TYPE": schedule_type,
                "AUTO_SYNC_INTERVAL_HOURS": str(interval_hours),
                "AUTO_SYNC_START_TIME": start_time,
                "AUTO_SYNC_CRON": cron_expression,
            }
        )

        success = start_scheduler(
            enabled=enabled,
            schedule_type=schedule_type,
            interval_hours=interval_hours,
            start_time=start_time,
            cron_expression=cron_expression,
        )

        if success:
            return jsonify({"status": "configured", **get_scheduler_status()})
        return jsonify({"error": "Failed to configure scheduler. APScheduler may not be installed."}), 500

    except ValueError as e:
        return jsonify({"error": f"Invalid value: {e}"}), 400
    except Exception as e:
        logger.error(f"Failed to configure scheduler: {e}")
        return jsonify({"error": "Failed to configure scheduler"}), 500


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
