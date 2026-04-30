# Configuration

!!! tip "Just getting started?"
    The defaults work well out of the box. You only **need** to set your Last.fm credentials and YouTube Music auth - everything else is optional. Docker users can skip this page entirely and configure via the web dashboard.

**Docker**: Use the Settings modal in the web dashboard. All settings are editable from the UI and saved to `.env` automatically.

**CLI**: Copy `.env.example` to `.env` and edit it. The example file has inline comments for every setting.

---

## Authentication

### Last.fm

- Get an API key at <https://www.last.fm/api>
- **Docker**: Enter credentials in the setup wizard or Settings modal
- **CLI**: Set `LASTFM_API_KEY` and `LASTFM_USER` in the `.env` file

### YouTube Music (ytmusicapi)

- This tool uses browser-based authentication only (no OAuth)
- **Docker**: Use the built-in auth flow in the web dashboard (no terminal access needed)
- **CLI**: Follow the ytmusicapi docs to export `browser.json`:
    - <https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html>

!!! info "Anonymous search"
    Anonymous search is supported (`USE_ANON_SEARCH=true`) for finding tracks, but you still need valid YouTube Music auth to create or update playlists.

---

## Settings Reference

All settings are configured via environment variables in `.env`. The tables below list every available setting.

### Credentials (Required)

| Variable | Default | Description |
|----------|---------|-------------|
| `LASTFM_USER` | | Your Last.fm username |
| `LASTFM_API_KEY` | | Last.fm API key ([get one here](https://www.last.fm/api/account/create)) |
| `YTM_AUTH_PATH` | `browser.json` | Path to ytmusicapi auth file |

### Main Playlist

| Variable | Default | Description |
|----------|---------|-------------|
| `PLAYLIST_NAME` | `Last.fm Recents (auto)` | Name for the synced playlist on YouTube Music |
| `PLAYLIST_DESCRIPTION` | *(auto-generated)* | Custom description (empty = auto-generated) |
| `MAKE_PUBLIC` | `PRIVATE` | Playlist visibility: `PRIVATE`, `UNLISTED`, or `PUBLIC` |
| `LIMIT` | `100` | Target number of tracks |
| `DEDUPLICATE` | `true` | Remove duplicate tracks |

### Track Ranking

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_RECENCY_WEIGHTING` | `true` | Rank by play count + recency (`false` = most recent first) |
| `RECENCY_HALF_LIFE_HOURS` | `24.0` | How fast recency decays (lower = favor newer tracks) |
| `RECENCY_PLAY_WEIGHT` | `0.7` | Balance: `0.0` = pure recency, `1.0` = pure play count |

### Weekly Playlists

| Variable | Default | Description |
|----------|---------|-------------|
| `WEEKLY_ENABLED` | `true` | Create weekly playlist snapshots |
| `WEEKLY_WEEK_START` | `MON` | Day the week starts (`MON`-`SUN`) |
| `WEEKLY_TIMEZONE` | `UTC` | Timezone for week boundary calculation |
| `WEEKLY_KEEP_WEEKS` | `2` | How many weeks to keep (`0` = keep all) |
| `WEEKLY_PLAYLIST_PREFIX` | *(from playlist name)* | Override name prefix (empty = derive from `PLAYLIST_NAME`) |
| `WEEKLY_MAKE_PUBLIC` | *(inherit)* | `PRIVATE`/`UNLISTED`/`PUBLIC` (empty = inherit `MAKE_PUBLIC`) |

### Search Behavior

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_ANON_SEARCH` | `true` | Use anonymous YTM client for searches (recommended) |
| `EARLY_TERMINATION_SCORE` | `0.9` | Stop search early if match score exceeds this (`0.0`-`1.0`) |
| `SLEEP_BETWEEN_SEARCHES` | `0.25` | Delay between searches in seconds |
| `SEARCH_MAX_WORKERS` | `2` | Parallel search threads (higher = faster but more API load) |

!!! note "Privacy"
    When `USE_ANON_SEARCH=false`, your YouTube Music searches appear in your YouTube search history. Set to `true` to keep searches private. Anonymous search may return slightly different results.

### Backfill

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_RAW_SCROBBLES` | `2000` | Max scrobbles to fetch (`0` = unlimited) |
| `BACKFILL_PASSES` | `3` | Additional fetch attempts if below `LIMIT` (`0` = disabled) |

### Caching

| Variable | Default | Description |
|----------|---------|-------------|
| `CACHE_PLAYLIST_FILE` | `cache/.playlist_cache.json` | Path to playlist cache |
| `CACHE_SEARCH_FILE` | `cache/.search_cache.json` | Path to search cache |
| `CACHE_OVERRIDES_FILE` | `config/search_overrides.json` | Path to search overrides |
| `CACHE_SEARCH_TTL_DAYS` | `30` | Days before cached searches expire (`0` = never) |
| `CACHE_NOTFOUND_TTL_DAYS` | `7` | Days before "not found" results are retried (`0` = don't cache) |

### Custom Tag Playlists

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_PLAYLISTS_FILE` | `config/custom_playlists.json` | Path to custom playlist config |
| `CUSTOM_PLAYLISTS_PRIVACY` | *(inherit)* | `PRIVATE`/`UNLISTED`/`PUBLIC` (empty = inherit `MAKE_PUBLIC`) |
| `TAG_CACHE_FILE` | `cache/.tag_cache.json` | Path to tag cache file |
| `TAG_CACHE_TTL_DAYS` | `90` | Days before cached tags expire |
| `TAG_MIN_COUNT` | `10` | Minimum Last.fm tag vote count to consider valid |
| `TAG_SLEEP_BETWEEN` | `0.25` | Delay between tag API calls in seconds |
| `TAG_OVERRIDES_FILE` | `config/tag_overrides.json` | Manual tag overrides file |

### History Database

| Variable | Default | Description |
|----------|---------|-------------|
| `HISTORY_DB_ENABLED` | `false` | Track all songs, syncs, and actions in a local SQLite DB |
| `HISTORY_DB_FILE` | `cache/history.db` | Path to the history database file |
| `HISTORY_MAX_SIZE_MB` | `0` | Auto-prune oldest records when exceeded (`0` = unlimited) |

### Reliability & Retries

| Variable | Default | Description |
|----------|---------|-------------|
| `API_MAX_RETRIES` | `3` | YTM API retry attempts (exponential backoff) |
| `LASTFM_MAX_RETRIES` | `5` | Last.fm API retry attempts |
| `LASTFM_MAX_CONSECUTIVE_EMPTY` | `3` | Stop after N pages with no new tracks |
| `LASTFM_FORCE_IPV4` | `true` | Force IPv4 (helps with flaky Last.fm IPv6) |

### Auto-Sync (Web Dashboard)

These settings only apply when running the web dashboard.

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SYNC_ENABLED` | `false` | Enable the built-in scheduler |
| `AUTO_SYNC_TYPE` | `interval` | `interval` or `cron` |
| `AUTO_SYNC_INTERVAL_HOURS` | `6` | Hours between syncs (interval mode) |
| `AUTO_SYNC_START_TIME` | | HH:MM anchor for interval start (e.g., `00:00`) |
| `AUTO_SYNC_CRON` | `0 */6 * * *` | Cron expression (cron mode) |
| `AUTO_TAG_SYNC_ENABLED` | `false` | Also sync custom tag playlists after each scheduled run |
| `AUTO_TAG_SYNC_FREQUENCY` | `1` | Run tag sync every N main syncs (`1` = every time) |
| `USE_24_HOUR_CLOCK` | `true` | Display times in 24-hour format |
| `DATE_FORMAT` | `auto` | Date display format: `auto` (browser locale), `DMY` (31/12), or `MDY` (12/31) |
| `NOW_PLAYING_ENABLED` | `true` | Show "Now Playing" from Last.fm in the header |
| `NOW_PLAYING_INTERVAL` | `15` | Seconds between Now Playing polls (`5`-`120`) |

### Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URL` | *(empty)* | Webhook endpoint URL (leave empty to disable) |
| `WEBHOOK_EVENTS` | `error` | When to send: `all` (every sync) or `error` (failures only) |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG` |

### Docker-Specific

These are set on the host, not in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `YTMT_PORT` | `2002` | Port to expose the web dashboard |
| `YTMT_HEALTH_TIMEOUT` | `30` | Seconds to wait for health check |
