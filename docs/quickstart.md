# Quick Start

## Docker (Recommended)

Docker gives you the web dashboard, built-in scheduler, and a self-contained environment.

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

## CLI-Only Setup

If you prefer not to use Docker, you can run the sync engine directly. Without the `[web]` extras, you won't get the web dashboard - all configuration is done via `.env` and JSON files, and scheduling is your responsibility.

### Prerequisites

- Python 3.10+
- A Last.fm API key: <https://www.last.fm/api>
- YouTube Music authentication exported for ytmusicapi:
    - Setup guide: <https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html>

!!! warning
    Keep your `browser.json` private. Do not commit it.

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
python run.py  # or just: lastfm-ytm-sync
```

What happens:

- On the first run, creates a new YouTube Music playlist named by `PLAYLIST_NAME`. On subsequent runs, it finds and updates the existing playlist by name.
- If `WEEKLY_ENABLED=true`, also creates/updates the weekly playlist for the current week.

!!! note
    The tool manages only the playlist(s) it creates. Manual edits to those playlists are reverted on the next run to match the tool's logic.

### Manual Scheduling (CLI)

Without the web dashboard, you need to set up scheduling yourself.

=== "Cron (Linux/macOS)"

    ```bash
    crontab -e

    # Example: run every day at 00:05
    5 0 * * * cd /path/to/repo && /usr/bin/python3 run.py >> playlist.log 2>&1
    ```

=== "systemd (Linux)"

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

=== "Windows Task Scheduler"

    - **Program/script**: path to `python.exe`
    - **Add arguments**: `C:\path\to\repo\run.py`
    - **Start in**: `C:\path\to\repo`
    - **Trigger**: Daily at a time you prefer

---

## What's Next?

After your first successful sync:

- **Fix mismatches** - check the playlist for wrong matches and add [manual overrides](overrides.md) to fix them. The web dashboard's **Not Found** and **Playlist** tabs make this easy.
- **Tune the settings** - adjust `RECENCY_PLAY_WEIGHT`, `RECENCY_HALF_LIFE_HOURS`, or `LIMIT` to get the playlist feel you want. See [Configuration](configuration.md) for all options.
- **Set up tag playlists** - auto-generate genre-based playlists from your Last.fm tags. See [Custom Tag Playlists](tag-playlists.md).
- **Enable scheduling** - Docker users can enable the built-in scheduler from the Settings modal. CLI users can set up [cron or systemd](#manual-scheduling-cli).
- **Get notified** - set up [webhooks](webhooks.md) to get Discord (or other) notifications on sync results.
