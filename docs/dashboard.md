# Web Dashboard

The web dashboard is always included with the Docker setup. It provides a full management interface - **everything** can be configured, inspected, and triggered from the UI without ever touching a config file, JSON, or terminal.

!!! tip "Running without Docker?"
    You can run the web dashboard manually too:
    ```bash
    pip install ".[web]"
    lastfm-ytm-web
    ```
    This starts the same dashboard at `http://localhost:2002`. You'll still need to handle process management yourself (e.g., keep it running via systemd or screen).

## Dashboard Features

- **Playlist tab** - View every track in your synced playlist with its matched YouTube Music link, source (cache/search/override), and status badges. Filter by overrides, blacklisted, or pending retry.
- **Overrides tab** - Add, edit, or remove manual search overrides directly. Paste a YouTube Music URL or video ID and the dashboard extracts and validates it.
- **Blacklist tab** - Manage blacklisted tracks from the UI. Blacklisted tracks are excluded entirely from playlist generation.
- **Not Found tab** - See all tracks where the search couldn't find a match. One-click to add an override or blacklist entry for any of them.

??? example "Screenshot: Not Found tab"
    ![Not Found](screenshots/notfound.png)

- **Cache tab** - Browse all cached search results, see which video each track resolved to, and clear individual entries or the full cache.
- **Settings modal** - Edit all configuration (Last.fm credentials, playlist options, search tuning, weekly settings, etc.) without touching `.env`. Changes take effect on the next sync.

??? example "Screenshot: Settings modal"
    ![Settings Modal](screenshots/settings_modal.png)

- **Sync console** - Trigger a sync manually and watch real-time output in a resizable terminal drawer. Stop a running sync at any time.

??? example "Screenshot: Sync console"
    ![Sync Console](screenshots/sync_console.png)

- **Stats bar** - At-a-glance counts: playlist tracks, overrides, blacklisted, not found, cached searches, and last sync time.
- **YTM authentication** - Run `ytmusicapi browser` authentication interactively through the web UI - no terminal access needed.
- **First-time setup wizard** - Guides you through `.env` creation, Last.fm credentials, and YouTube Music auth on first launch.

??? example "Screenshot: Setup wizard"
    ![Setup Wizard](screenshots/setup_wizard.png)

## Integrated Scheduler

The web dashboard includes a built-in scheduler (powered by APScheduler) so you don't need cron or systemd:

- **Interval mode** - Run every N hours, optionally anchored to a start time (e.g., every 6 hours starting at midnight)
- **Cron mode** - Use a cron expression for full control (e.g., `0 */6 * * *`)
- **Tag sync** - Optionally run tag playlist sync after each scheduled main sync via `AUTO_TAG_SYNC_ENABLED`. Use `AUTO_TAG_SYNC_FREQUENCY` to run it every N main syncs (e.g., `2` = every other sync).
- Configure via the Settings modal in the UI, or via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SYNC_ENABLED` | `false` | Enable the built-in scheduler |
| `AUTO_SYNC_TYPE` | `interval` | `interval` or `cron` |
| `AUTO_SYNC_INTERVAL_HOURS` | `6` | Hours between syncs (interval mode) |
| `AUTO_SYNC_START_TIME` | | HH:MM anchor for interval start (e.g., `00:00`) |
| `AUTO_SYNC_CRON` | `0 */6 * * *` | Cron expression (cron mode) |
| `AUTO_TAG_SYNC_ENABLED` | `false` | Also sync custom tag playlists after each scheduled run |
| `AUTO_TAG_SYNC_FREQUENCY` | `1` | Run tag sync every N main syncs (`1` = every time) |

The dashboard header shows a "Scheduled" indicator and the next run time when the scheduler is active.

## PWA Support

The dashboard is installable as a Progressive Web App. In supported browsers, you can add it to your home screen or install it as a standalone app for quick access.

## Data Export &amp; Import

The dashboard supports two ways to back up your data:

- **Plain export** - Export overrides, blacklist, and/or tag overrides as plain JSON files. Useful for quick backups or sharing configuration between instances. Available under **Settings &rarr; Data Management**.
- **Encrypted export (Teleporter)** - Export your full configuration (including `.env`, `browser.json`, caches) as a password-encrypted binary file. See [Teleporter](teleporter.md).
