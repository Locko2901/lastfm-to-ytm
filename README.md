[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with ytmusicapi](https://img.shields.io/badge/Built%20with-ytmusicapi-FF0000?logo=youtube&logoColor=white)](https://ytmusicapi.readthedocs.io/)
[![Uses Last.fm API](https://img.shields.io/badge/Uses-Last.fm%20API-D51007?logo=last.fm&logoColor=white)](https://www.last.fm/api)
[![MIT License](https://img.shields.io/github/license/Locko2901/lastfm-to-ytm)](LICENSE)

# Last.fm &rarr; YouTube Music Playlist Creator

Create and maintain a YouTube Music playlist from your Last.fm listening history. This tool fetches your recent scrobbles, intelligently finds matches on YouTube Music, and keeps a playlist updated. Optionally, it can snapshot your listening into weekly playlists.

There are two ways to run it:

**Docker (recommended)** - web dashboard + sync engine, built-in scheduler, configure everything from the UI. Get started with `./run-docker.sh`.

**CLI-only** - sync engine only, configure via `.env`, schedule with cron/systemd. Get started with `pip install . && python run.py`.

## Preview

![Dashboard Preview](docs/screenshots/dashboard.png)

## Table of Contents

- [Features](#features)
- [Quick Start with Docker (Web UI)](#quick-start-with-docker-web-ui)
  - [Docker CLI Options](#docker-cli-options)
  - [Docker Environment Variables](#docker-environment-variables)
  - [Common Docker Commands](#common-docker-commands)
  - [Updating](#updating)
- [Web Dashboard](#web-dashboard)
  - [Dashboard Features](#dashboard-features)
  - [Integrated Scheduler](#integrated-scheduler)
- [CLI-Only Setup](#cli-only-setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Running a Sync](#running-a-sync)
  - [Manual Scheduling (CLI)](#manual-scheduling-cli)
- [Authentication](#authentication)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
  - [Search and Matching](#search-and-matching)
  - [Recency Weighting](#recency-weighting)
  - [Weekly Playlists](#weekly-playlists)
- [Manual Search Overrides](#manual-search-overrides)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Credits](#credits)
- [License](#license)

## Features

- Creates/updates a YouTube Music playlist from your Last.fm scrobbles
- Optional recency-weighted selection to prioritize what you've listened to lately
- Intelligent search and matching on YouTube Music:
  - Prefers official Songs over user-uploaded Videos
  - Handles artist variations and collaborations
  - Avoids common mismatches (covers, remixes, live versions) where possible
  - Considers title, artist, and album similarity
- Weekly playlist snapshots (e.g., "Your Playlist week of 2026-03-09")
- **Web dashboard** (Docker) with real-time sync console, settings editor, cache browser, override/blacklist management, and built-in scheduler
- Configurable via environment variables, `.env` file, or the web UI
- Safe, incremental updates with batching and rate-limit-friendly delays

---

## Quick Start with Docker (Web UI)

The recommended way to run this tool. Docker gives you the web dashboard, built-in scheduler, and a self-contained environment.
```bash
# Clone and enter the repo
git clone https://github.com/Locko2901/lastfm-to-ytm.git
cd lastfm-to-ytm

# Make the launcher executable (first time only)
chmod +x run-docker.sh

# Start the container
./run-docker.sh
```

The web dashboard will be available at `http://localhost:2002` (or `http://<your-server-ip>:2002`).

On first launch, the dashboard walks you through initial setup - creating your `.env`, entering your Last.fm credentials, and authenticating with YouTube Music. No manual file editing required.

### Docker CLI Options

```bash
./run-docker.sh [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--rebuild` | `-r` | Force rebuild the Docker image |
| `--no-cache` | | Rebuild without Docker cache (implies `--rebuild`) |
| `--stop` | | Stop the running container |
| `--logs` | `-l` | Follow container logs |
| `--status` | | Show container status |
| `--prune` | | Remove dangling images and old project images |
| `--prune-all` | | Aggressive cleanup: also clear build cache and unused images |
| `--help` | `-h` | Show help message |

Options can be combined, e.g. `./run-docker.sh --no-cache --prune` to do a fresh rebuild and cleanup.

### Docker Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YTMT_PORT` | `2002` | Port to expose the web dashboard |
| `YTMT_HEALTH_TIMEOUT` | `30` | Seconds to wait for health check |

### Common Docker Commands

```bash
./run-docker.sh              # Start (default)
./run-docker.sh --logs       # Follow container logs
./run-docker.sh --stop       # Stop the container
./run-docker.sh --status     # Check if running
./run-docker.sh --no-cache   # Force rebuild with fresh dependencies
./run-docker.sh --rebuild --prune  # Rebuild and clean up old images
```

The Docker setup:
- Runs a Flask web dashboard with Gunicorn behind the scenes
- Persists cache and config data in local directories
- Auto-restarts unless manually stopped

### Updating

To update to the latest version:

```bash
git pull
./run-docker.sh --rebuild
```

Your cache, config, and `.env` are stored outside the container and persist across rebuilds.

---

## Web Dashboard

The web dashboard is always included with the Docker setup. It provides a full management interface - **everything** can be configured, inspected, and triggered from the UI without ever touching a config file, JSON, or terminal.

> **Don't want Docker?** You can run the web dashboard manually too:
> ```bash
> pip install ".[web]"
> lastfm-ytm-web
> ```
> This starts the same dashboard at `http://localhost:2002`. You'll still need to handle process management yourself (e.g., keep it running via systemd or screen).

### Dashboard Features

- **Playlist tab** - View every track in your synced playlist with its matched YouTube Music link, source (cache/search/override), and status badges. Filter by overrides, blacklisted, or pending retry.
- **Overrides tab** - Add, edit, or remove manual search overrides directly. Paste a YouTube Music URL or video ID and the dashboard extracts and validates it.
- **Blacklist tab** - Manage blacklisted tracks from the UI. Blacklisted tracks are excluded entirely from playlist generation.
- **Not Found tab** - See all tracks where the search couldn't find a match. One-click to add an override or blacklist entry for any of them.

<details>
<summary>Screenshot: Not Found tab</summary>

![Not Found](docs/screenshots/notfound.png)

</details>

- **Cache tab** - Browse all cached search results, see which video each track resolved to, and clear individual entries or the full cache.
- **Settings modal** - Edit all configuration (Last.fm credentials, playlist options, search tuning, weekly settings, etc.) without touching `.env`. Changes take effect on the next sync.

<details>
<summary>Screenshot: Settings modal</summary>

![Settings Modal](docs/screenshots/settings_modal.png)

</details>

- **Sync console** - Trigger a sync manually and watch real-time output in a resizable terminal drawer. Stop a running sync at any time.

<details>
<summary>Screenshot: Sync console</summary>

![Sync Console](docs/screenshots/sync_console.png)

</details>

- **Stats bar** - At-a-glance counts: playlist tracks, overrides, blacklisted, not found, cached searches, and last sync time.
- **YTM authentication** - Run `ytmusicapi browser` authentication interactively through the web UI - no terminal access needed.
- **First-time setup wizard** - Guides you through `.env` creation, Last.fm credentials, and YouTube Music auth on first launch.

<details>
<summary>Screenshot: Setup wizard</summary>

![Setup Wizard](docs/screenshots/setup_wizard.png)

</details>

### Integrated Scheduler

The web dashboard includes a built-in scheduler (powered by APScheduler) so you don't need cron or systemd:

- **Interval mode** - Run every N hours, optionally anchored to a start time (e.g., every 6 hours starting at midnight)
- **Cron mode** - Use a cron expression for full control (e.g., `0 */6 * * *`)
- Configure via the Settings modal in the UI, or via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SYNC_ENABLED` | `false` | Enable the built-in scheduler |
| `AUTO_SYNC_TYPE` | `interval` | `interval` or `cron` |
| `AUTO_SYNC_INTERVAL_HOURS` | `6` | Hours between syncs (interval mode) |
| `AUTO_SYNC_START_TIME` | | HH:MM anchor for interval start (e.g., `00:00`) |
| `AUTO_SYNC_CRON` | `0 */6 * * *` | Cron expression (cron mode) |

The dashboard header shows a "Scheduled" indicator and the next run time when the scheduler is active.

---

## CLI-Only Setup

If you prefer not to use Docker, you can run the sync engine directly. Without the `[web]` extras, you won't get the web dashboard - all configuration is done via `.env` and JSON files, and scheduling is your responsibility.

### Prerequisites

- Python 3.10+
- A Last.fm API key: https://www.last.fm/api
- YouTube Music authentication exported for ytmusicapi:
  - Setup guide: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html

> Keep your `browser.json` private. Do not commit it.

### Installation

```bash
# Clone the repo
git clone https://github.com/Locko2901/lastfm-to-ytm.git
cd lastfm-to-ytm

# Create & activate a virtual environment
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows

# Install
python -m pip install --upgrade pip
pip install .
```

### Running a Sync

```bash
python run.py # or just lastfm-ytm-sync
```

What happens:
- On the first run, creates a new YouTube Music playlist named by `PLAYLIST_NAME`. On subsequent runs, it finds and updates the existing playlist by name.
- If `WEEKLY_ENABLED=true`, also creates/updates the weekly playlist for the current week

> The tool manages only the playlist(s) it creates. Manual edits to those playlists are reverted on the next run to match the tool's logic.

### Manual Scheduling (CLI)

Without the web dashboard, you need to set up scheduling yourself. This tool is designed to run on a recurring schedule to keep playlists up to date.

**Cron** (Linux/macOS):

```bash
crontab -e

# Example: run every day at 00:05
5 0 * * * cd /path/to/repo && /usr/bin/python3 run.py >> playlist.log 2>&1
```

**systemd** (Linux):

```ini
# /etc/systemd/system/lastfm-ytm.service
[Unit]
Description=Last.fm to YouTube Music Playlist Updater
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/repo
ExecStart=/usr/bin/python3 /path/to/repo/run.py

# /etc/systemd/system/lastfm-ytm.timer
[Unit]
Description=Run Last.fm to YTM updater daily

[Timer]
OnCalendar=*-*-* 00:05:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Windows Task Scheduler**:

- Program/script: path to `python.exe`
- Add arguments: `C:\path\to\repo\run.py`
- Start in: `C:\path\to\repo`
- Trigger: Daily at a time you prefer

---

## Authentication

### Last.fm

- Get an API key at https://www.last.fm/api
- **Docker**: Enter credentials in the setup wizard or Settings modal
- **CLI**: Set `LASTFM_API_KEY` and `LASTFM_USER` in the `.env` file

### YouTube Music (ytmusicapi)

- This tool uses browser-based authentication only (no OAuth)
- **Docker**: Use the built-in auth flow in the web dashboard (no terminal access needed)
- **CLI**: Follow the ytmusicapi docs to export `browser.json`:
  - https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html

> Anonymous search is supported (`USE_ANON_SEARCH=true`) for finding tracks, but you still need valid YouTube Music auth to create or update playlists.

## Configuration

**Docker**: Use the Settings modal in the web dashboard. All settings are editable from the UI and saved to `.env` automatically.

**CLI**: Copy the included [`.env.example`](.env.example) and edit it:

1. Copy `.env.example` to `.env`
2. Fill in your Last.fm username and API key
3. Adjust other settings as needed (playlist name, visibility, limits, etc.)

> The `.env.example` file is fully documented with inline comments explaining each setting, including playlist options, search behavior, caching, retries, and more.

> **Privacy note**: When `USE_ANON_SEARCH=false` (the default), your YouTube Music searches will appear in your YouTube search history. Set `USE_ANON_SEARCH=true` if you prefer to keep searches private. Anonymous search may return slightly different results.

---

## How It Works

1. Fetch recent scrobbles from Last.fm
2. Process tracks:
   - If `USE_RECENCY_WEIGHTING=true`, score each track using exponential decay (see [Recency Weighting](#recency-weighting))
   - Otherwise, pick up to `LIMIT` most recent unique tracks
   - If `DEDUPLICATE=true`, ensure the final playlist does not include duplicates
3. Resolve each track to a YouTube Music video ID using a three-tier priority:
   1. **Manual overrides** - check `config/search_overrides.json` first (user-specified fixes)
   2. **Search cache** - check `cache/search_cache.json` (previously successful searches, 30-day TTL)
   3. **YouTube Music API** - only query the API if both above miss, then cache the result

   This cache-first approach minimizes API calls and ensures consistent results across runs.
4. Score and select the best match (see [Search and Matching](#search-and-matching))
5. Create or update YouTube Music playlist(s) with delays (`SLEEP_BETWEEN_SEARCHES`) to be rate-limit friendly

### Search and Matching

The matching algorithm aims to select the "right" track:

- Prefers official Song results over user-uploaded Videos
- Scores title, artist(s), and album similarity
- Handles common artist variations and multi-artist collaborations
- Avoids covers, remixes, and live versions unless they're the closest available match
- Can perform authenticated or anonymous search (`USE_ANON_SEARCH`), which may affect results

If a track cannot be matched reliably, it may be skipped or a best-effort match may be used.

### Recency Weighting

When enabled, this tool combines play count and recency to rank tracks:

- **Play score**: `plays / max_plays` (normalized to 0&ndash;1)
- **Recency score**: `0.5 ^ (age_hours / half_life_hours)` based on the most recent play
  - A track played exactly one half-life ago scores 0.5
  - More recent = higher score (up to 1.0)
- **Final score**: `play_weight &times; play_score + (1 &minus; play_weight) &times; recency_score`
  - Default: 70% play count, 30% recency (`RECENCY_PLAY_WEIGHT=0.7`)
- **Sorting priority**: Higher score &rarr; more recent play &rarr; higher play count

### Weekly Playlists

When `WEEKLY_ENABLED=true`, the tool creates/updates weekly playlists named:

- `{PLAYLIST_NAME} week of YYYY-MM-DD`, or
- `{WEEKLY_PLAYLIST_PREFIX} week of YYYY-MM-DD` if a prefix is set

The date corresponds to the start of the week. Over time, you'll build a library of weekly snapshots. Old weeks are automatically deleted based on `WEEKLY_KEEP_WEEKS` (default: 2).

---

## Manual Search Overrides

Sometimes the automatic search may fail to find a song or may find the wrong version. You can override specific searches or blacklist tracks entirely.

**Docker**: Use the web dashboard - the Overrides, Blacklist, and Not Found tabs let you manage these with a few clicks.

**CLI**: Edit `config/search_overrides.json` directly:

1. **Create the overrides file** (if it doesn't exist):
   ```bash
   cp config/search_overrides.json.example config/search_overrides.json
   ```

2. **Add your override** (find the video ID from a YouTube Music URL - it's the part after `v=`):
   ```json
   {
     "_overrides": {
       "rick astley|never gonna give you up": {
         "artist": "Rick Astley",
         "title": "Never Gonna Give You Up",
         "video_id": "dQw4w9WgXcQ",
         "reason": "Search found wrong version"
       }
     },
     "_blacklist": {
       "artist name|unwanted track": {
         "artist": "Artist Name",
         "title": "Unwanted Track",
         "reason": "Don't want this in playlist"
       }
     }
   }
   ```

**Key rules**:
- Keys must be `artist|title` in **lowercase**
- Overrides take priority over both the search cache and API searches
- Blacklisted tracks are skipped entirely during playlist generation
- Both persist until you manually remove them (no expiration)

---

## Troubleshooting
- **YouTube Music auth errors**:
  - Ensure `browser.json` is valid (re-export via ytmusicapi or the web dashboard)
- **Last.fm errors** (401/403/invalid key):
  - Confirm `LASTFM_API_KEY` and `LASTFM_USER`
  - Verify your key at https://www.last.fm/api/accounts
- **Playlist not updating**:
  - Confirm `PLAYLIST_NAME` matches exactly
  - Set `LOG_LEVEL=DEBUG` for verbose output
- **Missing or wrong matches**:
  - Toggle `USE_ANON_SEARCH`
  - Increase `EARLY_TERMINATION_SCORE` for more thorough searching (0.8&ndash;0.9)
  - Set `EARLY_TERMINATION_SCORE=1.0` to disable early termination entirely
  - Some tracks may be region-restricted or unavailable on YouTube Music
  - Use [manual overrides](#manual-search-overrides) to fix specific songs
- **Search performance issues**:
  - Decrease `EARLY_TERMINATION_SCORE` for faster searching (0.9&ndash;0.95)
  - Set `SLEEP_BETWEEN_SEARCHES=0` for maximum speed
- **Rate limiting or throttling**:
  - Increase `SLEEP_BETWEEN_SEARCHES`
  - Reduce `SEARCH_MAX_WORKERS`
- **Weekly date mismatches**:
  - Time zones and UTC timestamps from Last.fm can shift what falls into a given week

## Development

```bash
pip install -e ".[dev,web]"
```

### Translations (i18n)

The web dashboard uses [Flask-Babel](https://python-babel.github.io/flask-babel/) for translations. All user-facing strings in templates, Python routes, and JS modules are wrapped with `_()` / `gettext()`.

After pulling changes that modify `.po` files, compile the catalogs:

```bash
pybabel compile -d web/translations
```

See [`docs/i18n.md`](docs/i18n.md) for the full architecture - adding new languages, updating translations after code changes, the JS translation pipeline, and the custom extractor.

### Linting & Formatting

| Language | Tool | Check | Fix / Format |
|---|---|---|---|
| Python | [Ruff](https://docs.astral.sh/ruff/) | `ruff check .` | `ruff check . --fix` &middot; `ruff format .` |
| JS / CSS | [Biome](https://biomejs.dev/) | `npm run lint` | `npm run lint:fix` &middot; `npm run format` |
| HTML (Jinja) | [j2lint](https://github.com/aristanetworks/j2lint) | `j2lint web/templates --extensions html` | - (manual) |

See [docs/linting.md](docs/linting.md) for rule rationale, VS Code setup, and CI configuration.

## Credits

- [ytmusicapi](https://ytmusicapi.readthedocs.io/) - YouTube Music API wrapper
- Thanks to the Last.fm and YouTube Music communities.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
