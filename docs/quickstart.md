# Quick Start

!!! info "Stable vs. dev channel"
    The dashboard's version pill tells you which **update channel** you're on
    and lights up when there's something new:

    - **stable** - you're running a tagged release (`vX.Y.Z`). The pill
      lights up when a newer release is published. Recommended for most
      people.
    - **dev** - you're running the latest in-progress code from the
      `main` branch. The pill lights up whenever a new commit lands.

    You don't have to configure this - the launcher figures it out for you
    every time you start the app, based on what you actually asked for:

    | How you start the app | You get **stable** when&hellip; | You get **dev** when&hellip; |
    |---|---|---|
    | Prebuilt Docker (`./run-docker.sh --pull[=TAG]`) | `--pull`, `--pull=latest`, or `--pull=vX.Y.Z` | `--pull=dev` or `--pull=main` |
    | Local Docker build (`./run-docker.sh` after `git clone`) | You ran `git checkout vX.Y.Z` (a specific release) | Anything else - including a fresh `git clone` that lands on `main` |
    | Standalone Python (`python run.py`) | You ran `git checkout vX.Y.Z` | Anything else |

    For the two Docker paths, `run-docker.sh` writes the answer to a tiny
    `.channel` file in the project root (right next to `COMMIT_SHA`) and the
    dashboard reads it. For standalone, the dashboard asks `git` directly.

    !!! warning "Why `git clone` is always **dev**, even right after a release"
        A fresh `git clone` (or `git checkout main`) leaves you on the `main`
        *branch*, even if the latest commit on `main` happens to be a
        release commit. That's intentional - the next commit will be a
        dev commit. To be on **stable**, you have to explicitly check out a release
        tag (e.g. `git checkout v1.2.3`).

    **Want to switch?** Just run the install path for the other channel
    (see [Switching channels](#switching-channels) below). There's nothing
    to remember - no flag, no config file, no env var.

    **Note**: set `YTMT_CHANNEL=stable` (or `dev`) in your
    environment to force a channel, or pass `--channel=stable|dev` to
    `run-docker.sh` for a one-shot override.

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

Use this if you want to build the image locally, pin a tag, or contribute. **Stable requires explicitly checking out a
release tag** - a plain `git clone` always lands on `main` and stays
on the dev channel (see the warning in the callout at the top).

=== "Stable channel"

    ```bash
    git clone https://github.com/Locko2901/lastfm-to-ytm.git
    cd lastfm-to-ytm
    git checkout "$(git tag --sort=-v:refname | head -1)"   # latest release tag
    chmod +x run-docker.sh
    ./run-docker.sh    # builds locally; channel auto-detected as stable
    ```

=== "Dev channel"

    ```bash
    git clone https://github.com/Locko2901/lastfm-to-ytm.git
    cd lastfm-to-ytm
    chmod +x run-docker.sh
    ./run-docker.sh    # builds locally from main; channel auto-detected as dev
    ```

See all available tags on the
[releases page](https://github.com/Locko2901/lastfm-to-ytm/releases) or with
`git tag --list 'v*' | sort -V`. To pin a specific release instead of the
latest tag, replace the `git checkout` line above with
`git checkout v1.2.0`.

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
| `--channel=CH` | | One-shot override of the auto-detected channel (`stable` or `dev`) for this run only. Normally not needed - channel is inferred from `--pull` / git state and written to `.channel` in the project root |
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

The version pill in the dashboard header lights up when a newer build is
available. What "newer" means depends on your channel:

- **stable** - a newer release tag has been published (e.g. `v1.0.2`
  when you're on `v1.0.1`).
- **dev** - a newer commit has landed on `main` than the one you
  built / pulled.

Click the pill to open the GitHub release for the changelog before
upgrading. The commands to actually pull the update depend on how you
installed:

=== "Prebuilt Docker (stable)"

    ```bash
    ./run-docker.sh --pull            # picks up the new :latest release
    # or pin a specific version:
    ./run-docker.sh --pull=v1.2.0
    ```

=== "Prebuilt Docker (dev)"

    ```bash
    ./run-docker.sh --pull=dev        # fetches the newest :dev image
    ```

=== "Local Docker (stable)"

    ```bash
    git fetch --tags
    git checkout "$(git tag --sort=-v:refname | head -1)"
    ./run-docker.sh --rebuild
    # add --no-cache for a fully fresh image, --prune to drop the old one
    ```

=== "Local Docker (dev)"

    ```bash
    git checkout main
    git pull
    ./run-docker.sh --rebuild
    ```

=== "Standalone CLI (stable)"

    ```bash
    git fetch --tags
    git checkout "$(git tag --sort=-v:refname | head -1)"
    source .venv/bin/activate
    pip install --upgrade ".[web]"        # drop [web] if installed without it
    pybabel compile -d web/translations   # only needed for the web dashboard
    ```

=== "Standalone CLI (dev)"

    ```bash
    git checkout main
    git pull
    source .venv/bin/activate
    pip install --upgrade ".[web]"
    pybabel compile -d web/translations
    ```

For CLI installs, restart whatever runs the sync (cron, systemd,
`lastfm-ytm-web`, etc.) after upgrading. The `pybabel compile` step is
required because the compiled `.mo` catalogs are gitignored and
Flask-Babel silently falls back to source strings without them.

Docker bind mounts (`cache/`, `config/`, `.env`, `browser.json`) persist
across rebuilds and image swaps, so your data and credentials survive any
upgrade path.

### Switching channels

The channel is just a function of what you're running, so "switching" means
running the install path for the other channel. There's no persistent flag.

=== "Docker (prebuilt)"

    ```bash
    # Move to dev
    ./run-docker.sh --pull=dev

    # Back to stable
    ./run-docker.sh --pull            # or --pull=vX.Y.Z to pin
    ```

=== "Docker (local build)"

    ```bash
    # Move to dev
    git checkout main && ./run-docker.sh --rebuild

    # Move to stable
    git fetch --tags
    git checkout "$(git tag --sort=-v:refname | head -1)"
    ./run-docker.sh --rebuild
    ```

=== "Standalone CLI"

    Either change your checkout (`git checkout <tag-or-main>`) or force the
    channel via env var - it overrides git-state detection:

    ```bash
    export YTMT_CHANNEL=dev      # or stable
    ```

    Persist it by adding the line to your shell profile, `.env`, or the
    systemd unit's `Environment=` directive.

For Docker, the one-shot `--channel=stable|dev` flag is available too if
you want to override detection for a single invocation without changing
the actual build.

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

Like the local Docker build, **stable requires explicitly checking out a
release tag** - a plain `git clone` stays on the dev channel (see the
warning in the callout at the top). You can also force the channel at
runtime with `YTMT_CHANNEL=stable|dev`.

=== "Stable channel"

    ```bash
    git clone https://github.com/Locko2901/lastfm-to-ytm.git
    cd lastfm-to-ytm
    git checkout "$(git tag --sort=-v:refname | head -1)"   # latest release tag

    python -m venv .venv
    source .venv/bin/activate      # macOS/Linux
    # .venv\Scripts\activate       # Windows

    python -m pip install --upgrade pip
    pip install .
    ```

=== "Dev channel"

    ```bash
    git clone https://github.com/Locko2901/lastfm-to-ytm.git
    cd lastfm-to-ytm

    python -m venv .venv
    source .venv/bin/activate      # macOS/Linux
    # .venv\Scripts\activate       # Windows

    python -m pip install --upgrade pip
    pip install .
    ```

The web dashboard asks `git` whether your HEAD is **detached on a release
tag** (`git checkout v1.2.3`). If yes &rarr; stable, otherwise &rarr; dev.
A plain `git clone` or `git checkout main` is always dev, even if `main`'s
latest commit happens to be a release commit. To force a value (e.g.
unpacked tarball with no git, or tracking dev while sitting on a tagged
commit), set `YTMT_CHANNEL=stable` or `YTMT_CHANNEL=dev` in your
environment - the env var always wins.

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
