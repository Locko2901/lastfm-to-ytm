# CLI Install

Run the sync engine (and optionally the web dashboard) without Docker. You manage `.env`, credentials, and scheduling yourself.

!!! tip "Most users want Docker"
    The [Docker quickstart](quickstart.md) is faster, handles scheduling, and bundles the same dashboard. Use this CLI path if you don't want Docker - you can still run the web UI manually by installing the `[web]` extras (see below).

## Prerequisites

- Python 3.10+
- A Last.fm API key - [create one here](https://www.last.fm/api/account/create)
- YouTube Music auth exported for `ytmusicapi` - see the [browser setup guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html)

!!! warning
    Keep `browser.json` private. Never commit it.

---

## 1. Install

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

    !!! note "About `git checkout <tag>`"
        Checking out a tag leaves you in **detached HEAD** state. That's expected - you're pinning to a specific release. To update later, re-run the `git fetch --tags` + `git checkout` lines from the [Updating](#updating) section below.

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

See [Release Channels](channels.md) if you're unsure which to pick.

!!! tip "Want the web dashboard too?"
    Replace `pip install .` with `pip install ".[web]"`, then run `pybabel compile -d web/translations` before starting the dashboard. Start it with `lastfm-ytm-web` (binds to `http://localhost:2002`).

    The `pybabel compile` step is required because the compiled `.mo` translation files are gitignored - skip it and the language dropdown won't switch locales.

## 2. Create your `.env`

Copy the template and edit it with your credentials:

```bash
cp .env.example .env
$EDITOR .env   # set LASTFM_API_KEY and LASTFM_USER at minimum
```

The minimum required keys:

```ini
LASTFM_API_KEY=<your key>
LASTFM_USER=<your last.fm username>
PLAYLIST_NAME=Last.fm Recents (auto)   # whatever you want the playlist called
```

Everything else has sensible defaults. See the [full Configuration reference](configuration.md) for all available settings (search tuning, recency weighting, weekly playlists, webhooks, history database, etc.).

## 3. Export YouTube Music auth

Follow the [ytmusicapi browser setup guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html) once - it walks you through copying request headers from your browser's DevTools.

```bash
ytmusicapi browser   # interactive setup, writes browser.json
```

!!! warning
    Keep `browser.json` private. It contains your YouTube Music session.

## 4. Run a sync

```bash
python run.py     # or just: lastfm-ytm-sync
```

To sync your [custom tag playlists](tag-playlists.md) instead, run:

```bash
python run_tags.py    # or just: lastfm-ytm-tags
```

For what actually happens during a sync, see [How It Works](how-it-works.md).

---

## Manual Scheduling

Without the web dashboard, set up scheduling yourself.

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

## Updating

```bash
git fetch --tags
git checkout "$(git tag --sort=-v:refname | head -1)"   # stable; or `git checkout main` for dev
source .venv/bin/activate
pip install --upgrade ".[web]"        # drop [web] if installed without it
```

!!! warning "Web dashboard users: compile translations"
    If you installed with `[web]`, also run `pybabel compile -d web/translations` after upgrading. The compiled `.mo` catalogs are gitignored and Flask-Babel silently falls back to source strings without them - the language dropdown won't switch locales.

Restart whatever runs the sync (cron, systemd, `lastfm-ytm-web`, etc.) after upgrading.

See [Release Channels](channels.md) for stable vs. dev and how to pin a specific release.
