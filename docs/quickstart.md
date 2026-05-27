# Quick Start

## Docker (Recommended)

Docker gives you the web dashboard, built-in scheduler, and a self-contained environment.

### One-line install (prebuilt image)

The fastest path - downloads just the launcher script, the compose file,
and `.env.example`, then pulls the prebuilt multi-arch image from GHCR.
No `git` required.

By default the installer resolves the **latest release tag** via the
GitHub API and pins everything to it (it falls back to `main` only if no
release exists or the API is unreachable).

```bash
curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash
cd lastfm-to-ytm
./run-docker.sh --pull   # the installer prints the exact --pull=vX.Y.Z line to copy
```

Want a different target directory? Pass it as an argument:

```bash
curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash -s -- my-ytmt
```

Pin to a specific release explicitly (or track the dev channel) via
`YTMT_REF`:

```bash
# Pin to a specific tag
curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh \
    | YTMT_REF=v1.2.0 bash
cd lastfm-to-ytm
./run-docker.sh --pull=v1.2.0

# Track the bleeding edge instead
curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh \
    | YTMT_REF=main bash
cd lastfm-to-ytm
./run-docker.sh --pull=dev
```

!!! tip "Curl-pipe-bash safety"
    If you'd rather inspect the installer before running it, download it
    first: `curl -fsSL .../install.sh -o install.sh && less install.sh && bash install.sh`.

### Manual install (clone the repo)

Use this if you want to build the image locally, pin a tag, hack on the
source, or contribute back.

```bash
# Latest main
git clone https://github.com/Locko2901/lastfm-to-ytm.git
cd lastfm-to-ytm

# Make the launcher executable (first time only)
chmod +x run-docker.sh

# Start the container (builds the image locally)
./run-docker.sh
```

#### Pinning a specific version

To run a tagged release instead of the latest `main`:

```bash
# Shallow-clone just that tag
git clone --depth 1 --branch v1.2.0 https://github.com/Locko2901/lastfm-to-ytm.git
cd lastfm-to-ytm
./run-docker.sh --pull=v1.2.0   # use the matching prebuilt image (fast)
# or: ./run-docker.sh           # build that exact source locally
```

To switch an existing checkout to a tag:

```bash
cd lastfm-to-ytm
git fetch --tags
git checkout v1.2.0
./run-docker.sh --pull=v1.2.0
```

You can see all available versions on the
[releases page](https://github.com/Locko2901/lastfm-to-ytm/releases) or
with `git tag --list 'v*' | sort -V`.

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
| `--pull` | `-p` | Use the prebuilt image from GHCR instead of building locally (`--pull=TAG` to pin a tag) |
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
| `YTMT_IMAGE` | `lastfm-to-ytm-web:local` | Full image reference compose uses (override to pin a prebuilt tag) |

### Using the Prebuilt Image

Multi-arch images (`linux/amd64`, `linux/arm64`) are published to GitHub
Container Registry on every push to `main` and on every tagged release.

```bash
./run-docker.sh --pull              # pulls ghcr.io/locko2901/lastfm-to-ytm:latest
./run-docker.sh --pull=v1.2.0       # pin a specific version
./run-docker.sh --pull=main         # always-fresh main branch build
```

Available tags:

| Tag | Tracks | Channel |
|---|---|---|
| `latest` | The most recent tagged release | stable |
| `vX.Y.Z`, `X.Y`, `X` | A specific release (semver) | stable |
| `dev` | Latest untagged commit on `main` | development |
| `sha-<short>` | A specific `main` commit | development |

!!! note
    `latest` only moves when a new release tag is published - it never
    points at an untagged `main` commit. Use `dev` if you want the
    bleeding edge.

You can also bypass the launcher entirely - pulling and running the
image with plain `docker` works fine, as long as you mount `cache/`,
`config/`, `.env`, and `browser.json` the same way
[`devops/docker-compose.yml`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/devops/docker-compose.yml) does.

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

The dashboard shows a version pill (e.g. `v1.0.1`) in the header. When a
newer release is published on GitHub, the pill highlights and shows the
available version (e.g. `↑ v1.0.2`); clicking it opens the corresponding
[GitHub release](https://github.com/Locko2901/lastfm-to-ytm/releases) so
you can review the changelog before updating.

**Docker (recommended):**

```bash
git pull
./run-docker.sh --rebuild
```

Add `--no-cache` if a dependency was bumped and you want a fully fresh
image, and `--prune` to remove the previous image afterwards:

```bash
./run-docker.sh --no-cache --prune
```

If you are running the prebuilt image instead, just pull the new tag:

```bash
./run-docker.sh --pull           # latest release
./run-docker.sh --pull=v1.2.0    # pin a specific version
```

Your cache, config, and `.env` are stored outside the container and
persist across rebuilds.

**CLI / manual install:**

```bash
git pull
source .venv/bin/activate
pip install --upgrade ".[web]"        # drop [web] if you installed without it
pybabel compile -d web/translations   # only needed for the web dashboard
```

Then restart whatever is running the sync (cron, systemd, `lastfm-ytm-web`,
etc.). The `pip install --upgrade` picks up any new dependencies; the
`pybabel compile` step is required because the compiled `.mo` catalogs are
gitignored and Flask-Babel silently falls back to source strings without
them.

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
