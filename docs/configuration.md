# Configuration

!!! tip "Just getting started?"
    The defaults work well out of the box. You only **need** to set your Last.fm credentials and YouTube Music auth - everything else is optional. Docker users can skip this page entirely and configure via the web dashboard.

**Docker**: Use the Settings modal in the web dashboard. All settings are editable from the UI and saved to `.env` automatically.

**CLI**: Copy `.env.example` to `.env` and edit it. The example file has inline comments for every setting.

---

## Required: Credentials

These two are the only settings you *have* to configure. Everything else has sensible defaults.

### Last.fm

- Get an API key at <https://www.last.fm/api/account/create>
- **Docker**: Enter credentials in the setup wizard or Settings modal
- **CLI**: Set `LASTFM_API_KEY` and `LASTFM_USER` in `.env`

### YouTube Music (ytmusicapi)

- This tool uses browser-based authentication only (no OAuth)
- **Docker**: Use the built-in auth flow in the web dashboard - no terminal access needed
- **CLI**: Follow the [ytmusicapi browser setup guide](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html) to export `browser.json`

| Variable | Default | Description |
|----------|---------|-------------|
| `LASTFM_USER` | | Your Last.fm username |
| `LASTFM_API_KEY` | | Last.fm API key |
| `YTM_AUTH_PATH` | `browser.json` | Path to ytmusicapi auth file |

!!! info "Anonymous search"
    Anonymous search is supported (`USE_ANON_SEARCH=true`, the default) for finding tracks, but you still need valid YouTube Music auth to create or update playlists.

---

## Common settings

### Main Playlist

| Variable | Default | Description |
|----------|---------|-------------|
| `PLAYLIST_NAME` | `Last.fm Recents (auto)` | Name for the synced playlist on YouTube Music |
| `PLAYLIST_DESCRIPTION` | *(auto-generated)* | Custom description (empty = auto-generated) |
| `PLAYLIST_PRIVACY` | `PRIVATE` | Playlist visibility. One of `PRIVATE`, `UNLISTED`, or `PUBLIC`. Preferred over `MAKE_PUBLIC`. |
| `MAKE_PUBLIC` | *(unset)* | Deprecated alias for `PLAYLIST_PRIVACY`. Still honoured when `PLAYLIST_PRIVACY` is unset. |
| `LIMIT` | `100` | Target number of tracks |
| `DEDUPLICATE` | `true` | Remove duplicate tracks |

!!! note "Naming heads-up: `MAKE_PUBLIC` is deprecated"
    Prefer `PLAYLIST_PRIVACY` (`PRIVATE` / `UNLISTED` / `PUBLIC`). The older `MAKE_PUBLIC` variable is still honoured when `PLAYLIST_PRIVACY` is unset, and accepts the same privacy strings. Legacy boolean values (`true` &rarr; `PUBLIC`, `false` &rarr; `PRIVATE`) continue to work for backward compatibility but log a deprecation warning - switch to `PLAYLIST_PRIVACY` to silence it.

### Track Ranking

!!! tip "Just tuning?"
    Leave these at defaults. The two knobs worth adjusting:

    - `RECENCY_PLAY_WEIGHT`: lower (e.g. `0.3`) to favor what you've heard *lately*, higher (e.g. `0.9`) to favor what you play *most*.
    - `RECENCY_HALF_LIFE_HOURS`: lower (e.g. `24`) to make the playlist react faster to new listens, higher (e.g. `168`) for a slower-moving feel.

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_RECENCY_WEIGHTING` | `true` | Rank by play count + recency (`false` = most recent first) |
| `RECENCY_HALF_LIFE_HOURS` | `48.0` | How fast recency decays (lower = favor newer tracks) |
| `RECENCY_PLAY_WEIGHT` | `0.7` | Balance: `0.0` = pure recency, `1.0` = pure play count |
| `RECENCY_MIN_PLAYS` | `1` | Minimum scrobbles within fetched window for a track to qualify (`1` = no gate) |

### Weekly Playlists

| Variable | Default | Description |
|----------|---------|-------------|
| `WEEKLY_ENABLED` | `true` | Create weekly playlist snapshots |
| `WEEKLY_WEEK_START` | `MON` | Day the week starts (`MON`-`SUN`) |
| `WEEKLY_TIMEZONE` | `UTC` | Timezone for week boundary calculation |
| `WEEKLY_KEEP_WEEKS` | `2` | How many weeks to keep (`0` = keep all) |
| `WEEKLY_PLAYLIST_PREFIX` | *(from playlist name)* | Override name prefix (empty = derive from `PLAYLIST_NAME`) |
| `WEEKLY_PLAYLIST_PRIVACY` | *(inherit)* | `PRIVATE`/`UNLISTED`/`PUBLIC` (empty = inherit `PLAYLIST_PRIVACY`). Preferred over `WEEKLY_MAKE_PUBLIC`. |
| `WEEKLY_MAKE_PUBLIC` | *(inherit)* | Deprecated alias for `WEEKLY_PLAYLIST_PRIVACY`. Still honoured when the preferred var is unset. |

### Auto-Sync (Web Dashboard)

These settings only apply when running the web dashboard.

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTO_SYNC_ENABLED` | `false` | Enable the built-in scheduler |
| `AUTO_SYNC_TYPE` | `interval` | `interval` or `cron` |
| `AUTO_SYNC_INTERVAL_HOURS` | `6` | Hours between syncs (interval mode) |
| `AUTO_SYNC_START_TIME` | | HH:MM anchor for interval start (e.g., `00:00`) |
| `AUTO_SYNC_CRON` | `0 */6 * * *` | Cron expression (cron mode) |
| `AUTO_TAG_SYNC_ENABLED` | `false` | Also sync custom playlists (tags & artists) after each scheduled run |
| `AUTO_TAG_SYNC_FREQUENCY` | `1` | Run tag sync every N main syncs (`1` = every time) |
| `USE_24_HOUR_CLOCK` | `true` | Display times in 24-hour format |
| `DATE_FORMAT` | `auto` | Date display format: `auto` (browser locale), `DMY` (31/12), or `MDY` (12/31) |
| `NOW_PLAYING_ENABLED` | `true` | Show "Now Playing" from Last.fm in the header |
| `NOW_PLAYING_INTERVAL` | `15` | Seconds between Now Playing polls (`5`-`120`) |
| `DISPLAY_TIPS` | `true` | Show the helper info banners at the top of each dashboard tab |

### Webhooks

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URL` | *(empty)* | Webhook endpoint URL (leave empty to disable) |
| `WEBHOOK_EVENTS` | `error` | When to send: `all` (every sync) or `error` (failures only) |
| `WEBHOOK_ALLOW_PRIVATE` | `false` | Allow webhook URLs that resolve to private/LAN/localhost addresses (enable only for self-hosted receivers) |

---

## Advanced settings

These are rarely changed. Most users can ignore everything below.

??? note "Search behavior"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `USE_ANON_SEARCH` | `true` | Use anonymous YTM client for searches (recommended) |
    | `EARLY_TERMINATION_SCORE` | `0.9` | Stop search early if match score exceeds this (`0.0`-`1.0`) |
    | `SLEEP_BETWEEN_SEARCHES` | `0.25` | Delay between searches in seconds |
    | `SEARCH_MAX_WORKERS` | `2` | Parallel search threads (higher = faster but more API load) |

    **Privacy:** When `USE_ANON_SEARCH=false`, your YouTube Music searches appear in your YouTube search history. Set to `true` to keep searches private. Anonymous search may return slightly different results.

??? note "Backfill"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `MAX_RAW_SCROBBLES` | `2000` | Max scrobbles to fetch (`0` = unlimited) |
    | `BACKFILL_PASSES` | `3` | Additional fetch attempts if below `LIMIT` (`0` = disabled) |

??? note "Caching"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `CACHE_PLAYLIST_FILE` | `cache/.playlist_cache.json` | Path to playlist cache |
    | `CACHE_SEARCH_FILE` | `cache/.search_cache.json` | Path to search cache |
    | `CACHE_OVERRIDES_FILE` | `config/search_overrides.json` | Path to search overrides |
    | `CACHE_SEARCH_TTL_DAYS` | `30` | Days before cached searches expire (`0` = never) |
    | `CACHE_NOTFOUND_TTL_DAYS` | `7` | Days before "not found" results are retried (`0` = don't cache) |

??? note "Custom playlists"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `CUSTOM_PLAYLISTS_FILE` | `config/custom_playlists.json` | Path to custom playlist config |
    | `CUSTOM_PLAYLISTS_PRIVACY` | *(inherit)* | Default privacy for custom playlists: `PRIVATE`/`UNLISTED`/`PUBLIC` (empty = inherit `PLAYLIST_PRIVACY`). Overridable per playlist via the config's `privacy` field |
    | `TAG_CACHE_FILE` | `cache/.tag_cache.json` | Path to tag cache file |
    | `TAG_CACHE_TTL_DAYS` | `90` | Days before cached tags expire |
    | `TAG_MIN_COUNT` | `10` | Minimum Last.fm tag vote count to consider valid |
    | `TAG_SLEEP_BETWEEN` | `0.25` | Delay between tag API calls in seconds |
    | `TAG_OVERRIDES_FILE` | `config/tag_overrides.json` | Manual tag overrides file |

    See [Custom Playlists](tag-playlists.md) for the JSON schema and examples.

??? note "History database"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `HISTORY_DB_ENABLED` | `false` | Track all songs, syncs, and actions in a local SQLite DB |
    | `HISTORY_DB_FILE` | `cache/history.db` | Path to the history database file |
    | `HISTORY_MAX_SIZE_MB` | `0` | Auto-prune oldest records when exceeded (`0` = unlimited) |
    | `HISTORY_RETENTION_DAYS` | `0` | After each sync, delete `syncs` &amp; `actions` rows older than N days (`0` = keep forever). `tracks` are always retained. |

    See [History Database](history.md) for what's tracked and the dashboard view.

??? note "Local Last.fm history database"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `USE_LOCAL_LASTFM_DB` | `false` | Build the main playlist from your full local scrobble history (lifetime plays + recency) instead of recent tracks. **Changes playlist behaviour.** |
    | `LASTFM_LOCAL_DB_FILE` | `cache/lastfm_history.db` | Path to the local Last.fm history database file |
    | `LASTFM_LOCAL_DB_MAX_SCROBBLES` | `0` | Safety cap on scrobbles ingested per crawl (`0` = unlimited) |

    See [Local Last.fm History](local-history.md) for how the full crawl and incremental updates work.

??? note "Reliability & retries"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `API_MAX_RETRIES` | `3` | YTM API retry attempts (exponential backoff) |
    | `LASTFM_MAX_RETRIES` | `5` | Last.fm API retry attempts |
    | `LASTFM_MAX_CONSECUTIVE_EMPTY` | `3` | Stop after N pages with no new tracks |
    | `LASTFM_FORCE_IPV4` | `true` | Force IPv4 (helps with flaky Last.fm IPv6) |

??? note "Logging"

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `LOG_LEVEL` | `INFO` | `CRITICAL`, `ERROR`, `WARNING`, `INFO`, or `DEBUG` |

??? note "Docker-specific (host-side)"

    These are set on the host, not in `.env`:

    | Variable | Default | Description |
    |----------|---------|-------------|
    | `YTMT_PORT` | `2002` | Port to expose the web dashboard |
    | `YTMT_HEALTH_TIMEOUT` | `30` | Seconds to wait for health check |
