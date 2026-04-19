# Architecture

The sync engine has three layers:

1. **Data Layer** (`src/lastfm/`) - Fetch scrobbles from Last.fm API with pagination and diversity targeting
2. **Processing Layer** (`src/recency/`, `src/search/`) - Weight tracks by recency/plays, search and score YouTube Music matches
3. **Sync Layer** (`src/playlist/`, `src/ytm/`) - Maintain playlists with minimal API calls using diff-based sync

## Cache-First Design

All track resolution follows a three-tier priority:

1. **Manual overrides** (`config/search_overrides.json`) - user-specified fixes, checked first
2. **Search cache** (`cache/.search_cache.json`) - previously successful searches (30-day TTL)
3. **YouTube Music API** - only queried if both above miss; result is cached

This minimizes API calls and ensures consistent results across runs.

## Key Patterns

- **Atomic writes** - all cache saves use temp file + rename
- **File locking** - `fcntl.flock()` prevents concurrent cache corruption
- **Negative caching** - stores `null` results to avoid repeated failed searches
- **Template-based sync** - `PlaylistCache` stores desired state; skips sync if unchanged
- **Rate limit handling** - sleep between searches, retry with exponential backoff

## RuntimeContext

`RuntimeContext` (`src/context.py`) is a dependency-injection dataclass created once per run in `_build_context()`. It holds all shared state:

| Field | Type | Description |
|---|---|---|
| `settings` | `Settings` | Parsed configuration |
| `ytm` | `YTMusic` | Authenticated client (playlist operations) |
| `ytm_search` | `YTMusic` | Search client (anonymous if `USE_ANON_SEARCH=true`, otherwise same as `ytm`) |
| `search_cache` | `SearchCache` | Track &rarr; video ID cache |
| `search_overrides` | `SearchOverrides` | Manual overrides + blacklist |
| `playlist_cache` | `PlaylistCache` | Desired playlist state |
| `tag_cache` | `TagCache` | Last.fm tag cache |
| `tag_overrides` | `TagOverrides` | Manual tag fixes |

The **dual YTM client** pattern keeps search queries out of the user's YouTube search history when anonymous search is enabled, while still using authenticated credentials for playlist operations.

## Metrics

Both search and playlist operations track API usage for end-of-run logging:

**Search metrics** (`src/search/metrics.py`): total queries, songs searched, early terminations, session duration, early termination rate, queries per song, search rate (songs/sec)

**Playlist metrics** (`src/playlist/metrics.py`): per-operation counts (`get_playlist`, `add_playlist_items`, `remove_playlist_items`, `get_song`), total queries, session duration, query rate

## Failure & Run Logs

**Failure log** (`cache/.last_failure.json`): Written by `_save_failure_log()` when a sync fails. Contains timestamp, error message, traceback, sync type, and an auto-generated **hint** (e.g., "Authentication expired" for 401 errors, "Rate limited" for 403). The web dashboard reads this to show failure banners with actionable advice.

**Run log** (`cache/.last_run_log.json`): Written by `_save_run_log()` after every successful sync. Stores minimal per-track data (artist, title, source) - the web dashboard enriches this at display time by pulling video IDs and metadata from the search cache. Source values: `override`, `cache`, `search`, `blacklisted`, `not_found`.

---

## Main Sync Flow

`run()` (`src/main.py`) orchestrates the full workflow:

1. **Build context** - authenticate YTM, initialize caches and overrides via `_build_context()`
2. **Fetch scrobbles** - call `fetch_recent_with_diversity()` for diversity-targeted pagination
3. **Weight & dedupe** - `collapse_recency_weighted()` (if enabled) or `dedupe_keep_latest()`
4. **Resolve to video IDs** - `resolve_tracks_to_video_ids()` with three-tier priority
5. **Backfill** - if fewer tracks than `LIMIT`, fetch more scrobbles and resolve (up to `BACKFILL_PASSES`)
6. **Reorder** - if backfill happened with recency weighting, recalculate scores over the full scrobble set and reorder
7. **Sync main playlist** - `sync_playlist()` (existing) or `create_playlist_with_items()` (new), skipped if template unchanged
8. **Sync weekly playlist** - `update_weekly_playlist()` creates/updates a weekly snapshot
9. **Finalize** - clear failure log, save run log, log metrics, fire webhook

### Backfill Algorithm

When the initial resolve yields fewer video IDs than `LIMIT`, backfill kicks in:

```
while len(video_ids) < target_count and current_pass <= BACKFILL_PASSES:
    shortage = target_count - len(video_ids)
    additional_limit = len(recents) + shortage * 2
    # Fetch deeper into history, dedupe against seen_track_keys
    # Resolve new tracks, append unique video IDs
```

- **Multi-pass**: up to `BACKFILL_PASSES` (default 3) attempts
- **Fetch expansion**: requests `shortage * 2` extra scrobbles to account for duplicates and misses
- **Deduplication**: `seen_track_keys` set prevents re-resolving tracks across passes
- **Post-backfill reorder**: when recency weighting is enabled, the entire scrobble set is re-scored and the playlist reordered by final composite scores

### Invalid Video ID Recovery

When the YTM API rejects video IDs during sync (400/409 errors):

1. `InvalidVideoIDsError` is raised with the bad IDs
2. `_evict_from_cache()` removes them from the search cache
3. The full track list is re-resolved (evicted tracks get fresh searches)
4. Sync is retried with the corrected video IDs

### Track Resolution Pipeline

`resolve_tracks_to_video_ids()` (`src/search/resolver.py`) implements the three-tier priority in a single pass over all tracks:

1. **Blacklist check** - `search_overrides.is_blacklisted()` &rarr; skip with reason logged
2. **Override lookup** - `search_overrides.get()` &rarr; use fixed video ID
3. **Cache lookup** - `search_cache.get()` &rarr; use cached result (including negative `NOT_FOUND` sentinel)
4. **API search** - `find_on_ytm()` &rarr; cache result, sleep `SLEEP_BETWEEN_SEARCHES`

Returns `(video_ids, misses, track_to_vid, run_log_mappings)` for downstream use.

---

## Diversity-Targeted Fetching

`fetch_recent_with_diversity()` (`src/lastfm/fetch.py`) targets **unique tracks**, not raw scrobble count:

- Fetches pages of 200 scrobbles at a time
- Counts unique `(artist.lower(), track.lower())` pairs after each page
- Stops when any of: unique tracks &ge; `target_unique`, total scrobbles &ge; `max_raw_limit`, or `max_consecutive_empty` pages with no new unique tracks
- "Now playing" tracks (no timestamp) are filtered out during parsing

**Tag fetching** uses a separate `fetch_track_tags()` function that tries `track.getTopTags` first, falling back to `artist.getTopTags` if no track-level tags meet the minimum count threshold.

---

## Recency Weighting

`collapse_recency_weighted()` (`src/recency/weighting.py`) aggregates scrobbles into unique `WeightedTrack` objects:

**Per-track aggregation:**

- Groups by `(artist.lower(), track.lower())`
- Tracks play count and most recent timestamp per track

**Scoring formula:**

$$\text{score} = w_{\text{play}} \times \frac{\text{plays}}{\text{max\_plays}} + (1 - w_{\text{play}}) \times 0.5^{\text{age\_hours} / \text{half\_life}}$$

- `play_weight` ($w_{\text{play}}$): default `0.7` (70% plays, 30% recency)
- `half_life_hours`: default `24.0` - a track's recency score halves every 24 hours
- Sorting priority: `(-score, -ts, -plays)` for stable ordering

**Debug output**: logs top 50 tracks with per-track breakdown (play count, normalized score, age, recency score, final composite).
