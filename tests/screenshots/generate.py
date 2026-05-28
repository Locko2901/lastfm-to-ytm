"""Generate dashboard screenshots from a fixture dataset via Playwright.

Run from the project root with the venv active:

    python tests/screenshots/generate.py

Outputs PNGs to ``docs/screenshots/`` (overwriting the existing files).
Use ``--out`` to write somewhere else, ``--keep-server`` to leave the demo
server running, and ``--only NAME`` (repeatable) to capture a subset.

Architecture
------------
- A subprocess starts ``web.app:app`` with every fixture path (``CACHE_DIR``,
  ``CONFIG_DIR``, plus the per-file ``CACHE_*_FILE`` / ``TAG_*_FILE`` /
  ``CUSTOM_PLAYLISTS_FILE`` / ``HISTORY_DB_FILE`` overrides) pointed at
  ``tests/screenshots/fixtures/``. The per-file overrides are required because
  the project ``.env`` may set them with relative paths that would otherwise
  shadow the directory-level vars.
- Playwright intercepts the volatile endpoints (``/api/now-playing``,
  ``/api/scheduler/status``, ``/api/update-status``, ``/api/failure_log``,
  ``/api/auth/status``, ``/api/auth/validate``, ``/api/setup/status``,
  ``/api/settings``) so the captures are byte-stable and never leak real
  credentials.
- ``Date.now()`` is frozen via an init script so relative time labels
  ("3 days ago") don't drift between regenerations.
- Tab and modal views are triggered through the dashboard's own ``window.*``
  entrypoints (``switchTab``, ``showSettingsModal``, ``openSyncDrawer``,
  ``showSetupWizard``, ``showTeleporterModal``) - no application code is
  modified.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIXTURES = HERE / "fixtures"
DEFAULT_OUT = ROOT / "docs" / "screenshots"
HISTORY_DB_PATH = FIXTURES / "cache" / "history-demo.db"

FROZEN_NOW_ISO = "2026-05-28T10:00:00Z"

VIEWPORT = {"width": 1440, "height": 900}
DEVICE_SCALE = 2

ROUTE_STUBS: dict[str, dict] = {
    "**/api/now-playing": {
        "playing": True,
        "artist": "Aurora Lights",
        "title": "Glass Mountain",
        "album": "Hollow Sky EP",
        "image_url": "",
        "url": "https://music.youtube.com/watch?v=demo_aL_gm_001",
    },
    "**/api/scheduler/status": {
        "enabled": False,
        "next_run": None,
        "cron": "",
        "timezone": "UTC",
    },
    "**/api/update-status": {
        "current_version": "1.4.0",
        "latest_version": "1.4.0",
        "release_url": "",
        "release_name": "",
        "update_available": False,
        "commits_url": "",
    },
    "**/api/failure_log": {"has_failure": False},
    "**/api/auth/status": {
        "browser_json_exists": True,
        "valid": True,
    },
    "**/api/auth/validate": {"success": True, "valid": True},
    "**/api/setup/status": {
        "needs_setup": False,
        "has_env": True,
        "has_browser_json": True,
        "needs_auth": False,
    },
    "**/api/settings": {
        "LASTFM_USER": "demo_user",
        "LASTFM_API_KEY": "demo_api_key_00000000000000000000",
        "PLAYLIST_NAME": "Last.fm Recents (auto)",
        "PLAYLIST_DESCRIPTION": "Auto-synced from my Last.fm scrobbles",
        "LIMIT": "100",
        "MAKE_PUBLIC": "PRIVATE",
        "DEDUPLICATE": True,
        "USE_ANON_SEARCH": True,
        "USE_RECENCY_WEIGHTING": True,
        "RECENCY_HALF_LIFE_HOURS": "48",
        "RECENCY_PLAY_WEIGHT": "0.7",
        "WEEKLY_ENABLED": True,
        "WEEKLY_WEEK_START": "MON",
        "WEEKLY_KEEP_WEEKS": "2",
        "WEEKLY_TIMEZONE": "UTC",
        "WEEKLY_MAKE_PUBLIC": "PRIVATE",
        "HISTORY_DB_ENABLED": True,
        "DISPLAY_TIPS": True,
        "WEBHOOK_URL": "https://ntfy.sh/demo-syncs",
        "WEBHOOK_EVENTS": "all",
        "LOG_LEVEL": "INFO",
    },
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _seed_history_db(db_path: Path) -> None:
    """(Re)create a small history SQLite database with frozen timestamps.

    We bootstrap the schema via the real ``HistoryDB`` class (so any future
    migrations stay in sync), then wipe the seeded tables and insert
    hand-crafted rows so the History tab and its sub-tabs render consistent
    counts, charts, and lists.
    """
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(ROOT))
    from src.history.db import HistoryDB

    HistoryDB(db_path)

    tracks = [
        (
            "Aurora Lights",
            "Glass Mountain",
            "demo_aL_gm_001",
            "Aurora Lights - Glass Mountain",
            "search",
            "2026-04-12T08:11:00+00:00",
            "2026-05-28T09:14:56+00:00",
            38,
            0,
            0.94,
        ),
        (
            "Aurora Lights",
            "Paper Boats",
            "demo_aL_pb_002",
            "Aurora Lights - Paper Boats (Official Audio)",
            "search",
            "2026-04-15T17:42:00+00:00",
            "2026-05-27T22:01:00+00:00",
            22,
            0,
            0.91,
        ),
        (
            "Halcyon Drift",
            "Coral Static",
            "demo_hd_cs_003",
            "Halcyon Drift - Coral Static",
            "search",
            "2026-03-30T11:05:00+00:00",
            "2026-05-28T07:48:00+00:00",
            31,
            1,
            0.88,
        ),
        (
            "Halcyon Drift",
            "Slow Tide",
            "demo_hd_st_004",
            "Halcyon Drift - Slow Tide (Official Video)",
            "override",
            "2026-04-02T19:20:00+00:00",
            "2026-05-27T15:33:00+00:00",
            14,
            0,
            0.99,
        ),
        (
            "Midnight Cartographer",
            "North Star Index",
            "demo_mc_ns_005",
            "Midnight Cartographer - North Star Index",
            "search",
            "2026-04-19T22:12:00+00:00",
            "2026-05-28T06:02:00+00:00",
            18,
            0,
            0.86,
        ),
        (
            "Midnight Cartographer",
            "Map of the Quiet",
            "demo_mc_mq_006",
            "Midnight Cartographer - Map of the Quiet",
            "search",
            "2026-05-02T09:48:00+00:00",
            "2026-05-26T18:55:00+00:00",
            9,
            0,
            0.83,
        ),
        (
            "Saturn Hours",
            "Ring Theory",
            "demo_sh_rt_007",
            "Saturn Hours - Ring Theory",
            "search",
            "2026-04-08T13:31:00+00:00",
            "2026-05-28T05:47:00+00:00",
            26,
            0,
            0.90,
        ),
        (
            "Saturn Hours",
            "Equinox",
            "demo_sh_eq_008",
            "Saturn Hours - Equinox (Live at Echo Hall)",
            "search",
            "2026-04-25T20:05:00+00:00",
            "2026-05-25T11:14:00+00:00",
            6,
            2,
            0.71,
        ),
        (
            "Paper Kites Demo",
            "Soft Echo",
            "demo_pk_se_009",
            "Paper Kites Demo - Soft Echo",
            "search",
            "2026-05-04T07:33:00+00:00",
            "2026-05-27T19:22:00+00:00",
            11,
            0,
            0.85,
        ),
        (
            "The Quiet Channel",
            "Test Pattern",
            "demo_qc_tp_012",
            "The Quiet Channel - Test Pattern (Remastered)",
            "override",
            "2026-04-29T16:18:00+00:00",
            "2026-05-28T08:55:00+00:00",
            7,
            0,
            0.97,
        ),
        ("Field Recordings Pro", "Cassette Hiss vol. 2", None, None, "search", "2026-05-06T12:01:00+00:00", "2026-05-23T14:45:00+00:00", 0, 4, None),
        ("Obscure B-Side", "Untitled Sketch 4", None, None, "search", "2026-05-11T22:38:00+00:00", "2026-05-28T09:14:58+00:00", 0, 3, None),
        ("Tape Hiss Collective", "Hum & Wow", None, None, "search", "2026-05-18T08:24:00+00:00", "2026-05-27T20:11:00+00:00", 0, 2, None),
    ]
    syncs = [
        ("2026-05-21T08:00:00+00:00", "2026-05-21T08:00:08+00:00", 8.2, "main", "schedule", "success", 84, 82, 2, 5, 4, 79, 5, 2, None),
        ("2026-05-22T08:00:00+00:00", "2026-05-22T08:00:06+00:00", 6.5, "main", "schedule", "success", 86, 84, 2, 3, 2, 83, 3, 2, None),
        ("2026-05-23T08:00:00+00:00", "2026-05-23T08:00:09+00:00", 9.1, "main", "schedule", "success", 88, 85, 3, 6, 5, 82, 6, 2, None),
        ("2026-05-24T08:00:00+00:00", "2026-05-24T08:00:07+00:00", 7.4, "main", "schedule", "success", 85, 83, 2, 4, 3, 81, 4, 2, None),
        ("2026-05-25T08:00:00+00:00", "2026-05-25T08:00:11+00:00", 11.3, "weekly", "schedule", "success", 90, 87, 3, 8, 12, 82, 8, 2, None),
        ("2026-05-26T08:00:00+00:00", "2026-05-26T08:00:05+00:00", 5.8, "main", "schedule", "success", 85, 83, 2, 2, 1, 83, 2, 2, None),
        (
            "2026-05-27T08:00:00+00:00",
            "2026-05-27T08:00:21+00:00",
            21.4,
            "main",
            "schedule",
            "error",
            87,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            "YTM 403: please re-auth",
        ),
        ("2026-05-28T09:14:53+00:00", "2026-05-28T09:15:00+00:00", 7.2, "main", "manual", "success", 87, 85, 2, 4, 6, 81, 4, 2, None),
    ]
    actions = [
        ("2026-05-15T11:24:00+00:00", "override_add", "Halcyon Drift", "Slow Tide", "demo_hd_st_004", "Search found wrong version", "web"),
        ("2026-05-17T19:08:00+00:00", "blacklist_add", "Lowercase Drums", "Blank Canvas", None, "Silent track", "web"),
        ("2026-05-19T07:51:00+00:00", "cache_clear", "Saturn Hours", "Equinox", None, None, "web"),
        ("2026-05-20T14:33:00+00:00", "tag_override_add", "Halcyon Drift", "Slow Tide", None, "mode=replace, tags=ambient,downtempo", "web"),
        ("2026-05-22T09:18:00+00:00", "override_add", "The Quiet Channel", "Test Pattern", "demo_qc_tp_012", "Picked remastered cut", "web"),
        ("2026-05-23T16:02:00+00:00", "blacklist_add", "Ad Jingles Inc", "Brand Anthem", None, "Ad / jingle", "web"),
        ("2026-05-25T08:14:00+00:00", "sync_completed", None, None, None, "weekly sync 90 tracks", "system"),
        ("2026-05-26T21:47:00+00:00", "cache_clear", "Midnight Cartographer", "Map of the Quiet", None, None, "web"),
        ("2026-05-27T08:00:21+00:00", "sync_failed", None, None, None, "YTM 403 - token expired", "system"),
        ("2026-05-28T09:15:00+00:00", "sync_completed", None, None, None, "manual sync 87 tracks", "system"),
    ]

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany(
            """INSERT INTO tracks (artist, title, video_id, yt_title, source, first_seen, last_seen, times_found, times_missed, best_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tracks,
        )
        conn.executemany(
            """INSERT INTO syncs (started_at, finished_at, duration_secs, sync_type, trigger, status,
                                  tracks_total, tracks_resolved, tracks_missed,
                                  api_searches, api_playlist_ops, cache_hits, cache_misses, override_hits, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            syncs,
        )
        conn.executemany(
            "INSERT INTO actions (timestamp, action_type, artist, title, video_id, detail, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            actions,
        )
        conn.commit()
    finally:
        conn.close()


def _wait_for_server(port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"Demo server on port {port} did not start within {timeout}s")


def start_server(port: int) -> subprocess.Popen:
    """Spawn the demo Flask app pointing at the fixture dirs.

    Each per-file CACHE_* / *_FILE env var is set explicitly because the
    project `.env` may already define them with relative paths that would
    otherwise shadow `CACHE_DIR` / `CONFIG_DIR`.
    """
    _seed_history_db(HISTORY_DB_PATH)
    cache_dir = FIXTURES / "cache"
    config_dir = FIXTURES / "config"
    env = os.environ.copy()
    env.update(
        {
            "CACHE_DIR": str(cache_dir),
            "CONFIG_DIR": str(config_dir),
            "CACHE_SEARCH_FILE": str(cache_dir / ".search_cache.json"),
            "CACHE_PLAYLIST_FILE": str(cache_dir / ".playlist_cache.json"),
            "CACHE_OVERRIDES_FILE": str(config_dir / "search_overrides.json"),
            "TAG_CACHE_FILE": str(cache_dir / ".tag_cache.json"),
            "TAG_OVERRIDES_FILE": str(config_dir / "tag_overrides.json"),
            "CUSTOM_PLAYLISTS_FILE": str(config_dir / "custom_playlists.json"),
            "HISTORY_DB_FILE": str(cache_dir / "history-demo.db"),
            "LASTFM_USER": "demo_user",
            "LASTFM_API_KEY": "demo_api_key_00000000000000000000",
            "PLAYLIST_NAME": "Last.fm Recents (auto)",
            "WEEKLY_ENABLED": "true",
            "HISTORY_DB_ENABLED": "true",
            "DEMO_PORT": str(port),
            "FLASK_ENV": "production",
            "PYTHONUNBUFFERED": "1",
        },
    )
    cmd = [sys.executable, str(HERE / "_serve.py")]
    proc = subprocess.Popen(
        cmd,
        env=env,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_server(port)
    except Exception:
        proc.terminate()
        try:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
        except Exception:
            out = ""
        sys.stderr.write(out)
        raise
    return proc


_DATE_FREEZE_SCRIPT = f"""
(() => {{
  const FROZEN = new Date('{FROZEN_NOW_ISO}').getTime();
  const RealDate = Date;
  class FrozenDate extends RealDate {{
    constructor(...args) {{
      if (args.length === 0) {{ super(FROZEN); return; }}
      super(...args);
    }}
    static now() {{ return FROZEN; }}
    static parse(...a) {{ return RealDate.parse(...a); }}
    static UTC(...a) {{ return RealDate.UTC(...a); }}
  }}
  globalThis.Date = FrozenDate;
}})();
"""

_FAKE_SYNC_OUTPUT = """INFO: Authenticating with YTMusic...
INFO: Fetching scrobbles for 'demo_user'...
INFO: Aggregated to 19 unique tracks (half-life=48.0h). Resolving on YTM...
INFO: Resolving 19 unique tracks on YTM...
INFO: 1/19 Glass Mountain (plays=8, score=0.912) [cache]
INFO: 2/19 Hollow Sky (plays=7, score=0.864) [cache]
INFO: 3/19 Coral Static (plays=6, score=0.811) [cache]
INFO: 4/19 Slow Tide (plays=6, score=0.793) [override]
INFO: 5/19 Compass Rose (plays=5, score=0.732) [cache]
INFO: 6/19 Northbound (plays=5, score=0.708) [cache]
INFO: 7/19 Ring Theory (plays=5, score=0.689) [cache]
INFO: 8/19 Halo Effect (plays=4, score=0.621) [cache]
INFO: 9/19 Featherweight (plays=4, score=0.583) [cache]
INFO: 10/19 Origami Sun (plays=4, score=0.547) [cache]
INFO: 11/19 Standby Mode (plays=3, score=0.471) [cache]
INFO: 12/19 Test Pattern (plays=3, score=0.452) [override]
INFO: 13/19 soft margin (plays=3, score=0.418) [cache]
INFO: Blacklisted track skipped: Lowercase Drums - blank canvas (reason: Skipped \u2014 duplicates 'soft margin' on the EP)
INFO: 14/19 Rainwater on Tin (plays=2, score=0.341) [cache]
INFO: Blacklisted track skipped: Ad Jingles Inc - Brand Anthem (reason: Accidentally scrobbled from a TV ad)
INFO: 15/19 Untitled Sketch 4 (plays=1, score=0.218) [cache]
INFO: 16/19 Drone for Empty Room (plays=1, score=0.184) [cache]
INFO: 17/19 Misattributed Track (plays=1, score=0.151) [cache]
INFO: Found 14 unique tracks
INFO: Template changed for 'Last.fm Recents (auto)': 14 videos -> 14 videos
INFO: Updating playlist 'Last.fm Recents (auto)'...
INFO: Syncing playlist...
INFO: Starting playlist sync for PLdemoMainPlaylist000000000001 (current query count: 0)
INFO: \u2713 Playlist sync successful (exact match)
INFO: Completed using 4 API queries (total: 4)
INFO: Caching template: 'Last.fm Recents (auto)' -> PLdemoMainPlaylist000000000001 (14 videos)
INFO: Found existing weekly playlist 'Last.fm Recents (auto) week of 2026-05-25' (PLdemoWeekly2026052500000001)
INFO: Weekly unchanged (matches main), skipping sync
INFO: Caching template: 'Last.fm Recents (auto) week of 2026-05-25' -> PLdemoWeekly2026052500000001 (14 videos)
INFO: Done: https://music.youtube.com/playlist?list=PLdemoMainPlaylist000000000001
INFO: Weekly: https://music.youtube.com/playlist?list=PLdemoWeekly2026052500000001
INFO: 3 tracks not found
INFO: Saved run log with 19 mappings to /app/cache/.last_run_log.json
INFO: === Search Session Statistics ===
INFO: Total songs searched: 2
INFO: Total API queries: 5
INFO: Average queries per song: 2.50
INFO: Early terminations: 0
INFO: Early termination rate: 0.0%
INFO: Session duration: 6.3 seconds
INFO: Search rate: 0.32 songs/second
INFO: Query rate: 0.79 queries/second
INFO: ==================================
INFO: === Playlist Session Statistics ===
INFO: Total playlist API queries: 4
INFO: Session duration: 6.3 seconds
INFO: Query rate: 0.63 queries/second
INFO: Operation breakdown:
INFO:   get_playlist: 2 (50.0%)
INFO:   add_playlist_items: 1 (25.0%)
INFO:   remove_playlist_items: 1 (25.0%)
INFO: ==================================
INFO: Search cache stats - Hits: 17, Misses: 2, Hit rate: 89.5%, Writes: 2
INFO: Playlist cache stats - Hits: 4, Misses: 0, Hit rate: 100.0%, Writes: 2
INFO: Overrides: 2, Blacklisted: 2
INFO: Webhook sent (success main) -> 17
"""


def _stub_routes(context) -> None:
    """Mock volatile API endpoints in the browser context."""
    import json

    def _make_handler(payload: dict):
        body = json.dumps(payload)

        def _handler(route, _request):
            route.fulfill(status=200, content_type="application/json", body=body)

        return _handler

    for pattern, payload in ROUTE_STUBS.items():
        context.route(pattern, _make_handler(payload))


def _new_page(context):
    context.add_init_script(_DATE_FREEZE_SCRIPT)
    page = context.new_page()
    page.set_default_timeout(8_000)
    return page


def _open_dashboard(context, base_url: str):
    """Open the dashboard, wait for it to render, return the page."""
    page = _new_page(context)
    page.goto(base_url)
    page.wait_for_selector(".tabs .tab.active", state="visible")
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=4_000)
    return page


def _shoot(page, out: Path, name: str) -> None:
    page.screenshot(path=str(out / f"{name}.png"), full_page=False)
    page.close()


_TAB_CAPTURES: tuple[tuple[str, str], ...] = (
    ("notfound", "notfound"),
    ("overrides", "overrides"),
    ("custom_playlists", "custompl"),
)


_MODAL_CAPTURES: tuple[tuple[str, str, str], ...] = (
    ("settings_modal", "window.showSettingsModal && window.showSettingsModal()", "#settingsModal.active"),
    ("setup_wizard", "window.showSetupWizard && window.showSetupWizard()", "#setupModal"),
    ("teleporter", "window.showTeleporterModal && window.showTeleporterModal()", "#teleporterModal.active"),
)


def capture_dashboard(context, base_url: str, out: Path) -> None:
    page = _open_dashboard(context, base_url)
    _shoot(page, out, "dashboard")


def _make_tab_capture(tab_id: str):
    def _capture(context, base_url: str, out: Path, *, name: str) -> None:
        page = _open_dashboard(context, base_url)
        page.evaluate(f"window.switchTab && window.switchTab({tab_id!r})")
        page.wait_for_selector(f'[data-tab="{tab_id}"].active', state="visible")
        page.wait_for_timeout(150)
        _shoot(page, out, name)

    return _capture


def _make_modal_capture(open_js: str, visible_selector: str):
    def _capture(context, base_url: str, out: Path, *, name: str) -> None:
        page = _open_dashboard(context, base_url)
        page.evaluate(open_js)
        page.wait_for_selector(visible_selector, state="visible", timeout=3_000)
        page.wait_for_timeout(200)
        _shoot(page, out, name)

    return _capture


def capture_sync_console(context, base_url: str, out: Path) -> None:
    page = _open_dashboard(context, base_url)
    page.evaluate("window.openSyncDrawer && window.openSyncDrawer()")
    page.evaluate(
        """(text) => {
            const el = document.getElementById('syncOutput');
            if (el) {
                el.innerText = text;
                el.scrollTop = el.scrollHeight;
            }
            const status = document.getElementById('syncStatusText');
            if (status) status.textContent = 'Completed';
        }""",
        _FAKE_SYNC_OUTPUT,
    )
    page.wait_for_timeout(200)
    _shoot(page, out, "sync_console")


def capture_history(context, base_url: str, out: Path) -> None:
    page = _open_dashboard(context, base_url)
    page.evaluate("window.switchTab && window.switchTab('history')")
    page.wait_for_selector('[data-tab="history"].active', state="visible")
    with contextlib.suppress(Exception):
        page.wait_for_function(
            "() => { const el = document.getElementById('histStatTracks');"
            " return el && el.textContent.trim() && el.textContent.trim() !== '\u2013'; }",
            timeout=4_000,
        )
    page.wait_for_timeout(300)
    _shoot(page, out, "history")


CAPTURES: dict[str, callable] = {"dashboard": capture_dashboard}
for _name, _tab in _TAB_CAPTURES:
    _tab_capture = _make_tab_capture(_tab)
    CAPTURES[_name] = lambda c, b, o, _cap=_tab_capture, _n=_name: _cap(c, b, o, name=_n)
for _name, _open, _sel in _MODAL_CAPTURES:
    _modal_capture = _make_modal_capture(_open, _sel)
    CAPTURES[_name] = lambda c, b, o, _cap=_modal_capture, _n=_name: _cap(c, b, o, name=_n)
CAPTURES["sync_console"] = capture_sync_console
CAPTURES["history"] = capture_history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory (default: docs/screenshots)")
    parser.add_argument(
        "--only",
        action="append",
        choices=sorted(CAPTURES),
        help="Capture only the named screenshot(s). Repeatable.",
    )
    parser.add_argument("--port", type=int, default=0, help="Port for the demo server (default: random free port).")
    parser.add_argument("--keep-server", action="store_true", help="Leave the demo server running after capture.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium with a visible window (debug).")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.stderr.write(
            "playwright is not installed in this environment.\nInstall with:  pip install playwright  &&  python -m playwright install chromium\n",
        )
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    port = args.port or _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    targets = args.only or list(CAPTURES)

    print(f"[demo] starting server on {base_url}")
    server = start_server(port)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            context = browser.new_context(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE)
            _stub_routes(context)

            for name in targets:
                print(f"[demo] capturing {name}")
                try:
                    CAPTURES[name](context, base_url, args.out)
                except Exception as exc:
                    print(f"[demo]   ! {name}: {exc}", file=sys.stderr)

            context.close()
            browser.close()
    finally:
        if args.keep_server:
            print(f"[demo] server still running on {base_url} (PID {server.pid}) - kill manually when done")
        else:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            print("[demo] server stopped")

    print(f"[demo] screenshots written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
