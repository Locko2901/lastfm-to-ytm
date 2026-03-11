"""Flask web dashboard for Last.fm → YouTube Music sync."""

from __future__ import annotations

import logging
import os
import secrets as _secrets
import sys
from pathlib import Path

from flask import Flask, g, render_template

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import CACHE_DIR, CONFIG_DIR, PROJECT_ROOT

from .routes import actions_bp, api_bp, auth_bp, sync_bp
from .services import (
    get_cache_stats,
    get_cached_tracks,
    get_last_sync_time,
    get_not_found_tracks,
    get_overrides_data,
    get_playlist_links,
    load_overrides,
    load_run_log,
    sync_state,
)
from .services.scheduler import init_scheduler_from_env

ENV_FILE = PROJECT_ROOT / ".env"
BROWSER_JSON_FILE = PROJECT_ROOT / "browser.json"
RUN_LOG_FILE = CACHE_DIR / ".last_run_log.json"
OVERRIDES_FILE = CONFIG_DIR / "search_overrides.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _ensure_secret_key(env_path: Path) -> str:
    """Return FLASK_SECRET_KEY, generating and persisting it to .env if absent."""
    key = os.environ.get("FLASK_SECRET_KEY", "").strip()
    if key:
        return key

    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("FLASK_SECRET_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    os.environ["FLASK_SECRET_KEY"] = key
                    return key

    key = _secrets.token_hex(32)
    os.environ["FLASK_SECRET_KEY"] = key

    _auto_section = (
        "\n\n"
        "# ============================================================================\n"
        "# AUTO-GENERATED (managed by the app - do not edit manually)\n"
        "# ============================================================================\n"
        f"FLASK_SECRET_KEY={key}\n"
    )

    if env_path.exists():
        content = env_path.read_text()
        if "# AUTO-GENERATED" in content:
            env_path.write_text(content.rstrip("\n") + f"\nFLASK_SECRET_KEY={key}\n")
        else:
            env_path.write_text(content.rstrip("\n") + _auto_section)

    logger.info("Generated and persisted new FLASK_SECRET_KEY to .env")
    return key


app = Flask(__name__, static_folder="static")


app.secret_key = _ensure_secret_key(ENV_FILE)

_dist = Path(__file__).parent / "static" / "dist"
app.jinja_env.globals["use_minified"] = (_dist / "app.min.js").exists() and (_dist / "bundle.min.css").exists()


@app.context_processor
def inject_csp_nonce():
    """Make the CSP nonce available in all templates."""
    return {"csp_nonce": getattr(g, "csp_nonce", "")}


@app.before_request
def generate_csp_nonce():
    """Generate a unique nonce for inline scripts on each request."""
    g.csp_nonce = _secrets.token_urlsafe(16)


@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    nonce = getattr(g, "csp_nonce", "")
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        f"connect-src 'self'; font-src 'self'"
    )
    return response


app.register_blueprint(api_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(sync_bp)
app.register_blueprint(actions_bp)


@app.route("/")
def index():
    """Main dashboard page."""
    run_log = load_run_log()
    all_mappings = run_log["mappings"]
    limit = run_log["limit"]
    overrides = load_overrides()

    playlist_mappings = []
    for m in all_mappings:
        if (m.get("video_id") or m.get("pending_retry")) and len(playlist_mappings) < limit:
            key = f"{m['artist'].lower()}|{m['title'].lower()}"
            m["is_blacklisted"] = key in overrides._cache.get("_blacklist", {})
            m["is_overridden"] = key in overrides._cache.get("_overrides", {})
            if m.get("video_id"):
                m["ytm_url"] = f"https://music.youtube.com/watch?v={m['video_id']}"
            else:
                m["ytm_url"] = None
            playlist_mappings.append(m)

    override_list, blacklist = get_overrides_data()
    cache_stats = get_cache_stats()
    cached_tracks = get_cached_tracks()
    last_sync = get_last_sync_time()
    playlist_links = get_playlist_links()

    env_exists = ENV_FILE.exists()
    env_empty = env_exists and ENV_FILE.stat().st_size == 0
    needs_setup = not env_exists or env_empty

    browser_exists = BROWSER_JSON_FILE.exists()
    browser_valid = browser_exists and BROWSER_JSON_FILE.stat().st_size > 3
    needs_auth = env_exists and not env_empty and not browser_valid

    return render_template(
        "dashboard.html",
        mappings=playlist_mappings,
        limit=limit,
        timestamp=run_log["timestamp"],
        total=run_log["total"],
        resolved=len(playlist_mappings),
        overrides=override_list,
        blacklist=blacklist,
        cache_stats=cache_stats,
        cached_tracks=cached_tracks,
        not_found_tracks=get_not_found_tracks(),
        sync_running=sync_state["running"],
        last_sync=last_sync,
        playlist_links=playlist_links,
        needs_setup=needs_setup,
        needs_auth=needs_auth,
    )


def main():
    """Run the Flask development server."""
    logger.info("Starting web dashboard at http://127.0.0.1:2002")
    logger.info("Run log: %s", RUN_LOG_FILE)
    logger.info("Overrides: %s", OVERRIDES_FILE)
    try:
        init_scheduler_from_env()
    except Exception as e:
        logger.warning(f"Could not initialize scheduler: {e}")
    app.run(debug=True, port=2002, threaded=True)


if __name__ == "__main__":
    main()
