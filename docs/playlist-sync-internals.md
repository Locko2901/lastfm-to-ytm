# Playlist Sync Internals

## Sync Strategy (`src/playlist/sync.py`)

`sync_playlist()` uses a **replace-then-verify** approach rather than incremental diffing:

1. **Replace content** - `_replace_playlist_content()` removes all tracks, then adds the desired list
2. **Verify** - re-fetch the playlist and compare against desired state
3. **Detect substitutions** - if mismatches exist, check whether YouTube replaced videos with equivalent ones
4. **Retry** - up to `verify_attempts` (default 2) if verification fails

### Precondition Retry

YouTube's API returns 400 (Precondition) or 409 (Conflict) when the playlist state changed between read and write. `_replace_playlist_content()` retries these with increasing delays (`3s`, `6s`) by re-fetching the playlist state before each attempt.

---

## YouTube Substitution Detection

`_are_same_song()` detects when YouTube silently replaces a requested video ID with a different upload of the same song.

**Comparison logic:**

1. Fetch metadata for both video IDs via `get_song()`
2. Normalize titles by stripping artist prefixes (`"artist - "`) and suffixes: `(audio)`, `(official audio)`, `(official video)`, `(lyric video)`, `(lyrics)`, `[official audio]`, `[audio]`, `- audio`, `- official audio`
3. Check for exact title match **and** at least one shared artist &rarr; substitution
4. Check for substring containment (min length 3) with artist match &rarr; substitution

Detected substitutions are:

- Logged as info messages
- Recorded in the history DB as `"substitution"` actions
- Accepted silently - the adjusted desired list is used for further verification

---

## Retry & Backoff

`_retry_with_backoff()` wraps all YTM API calls with exponential backoff:

| Parameter | Value |
|---|---|
| Max retries | 3 |
| Initial delay | 1s |
| Backoff factor | 2&times; (1s &rarr; 2s &rarr; 4s) |
| Retryable errors | `403`, `Forbidden`, `Expecting value` (invalid JSON) |
| Non-retryable | `400` + `Precondition` (handled by precondition retry), `409` Conflict |

---

## Invalid Video ID Handling

When a bulk `add_playlist_items` call fails with 400/409:

1. Each video ID is validated individually via `get_song()`
2. Invalid IDs are collected into an `InvalidVideoIDsError`
3. The caller (`run()`) evicts bad IDs from the search cache via `_evict_from_cache()`
4. The full track list is re-resolved with fresh API searches for evicted tracks
5. Sync is retried with corrected video IDs

`_evict_from_cache()` scans all cache entries, matches video IDs against the bad set, and deletes the corresponding `(artist, title)` entries.

---

## Video ID Validation

Video IDs must be exactly 11 characters (alphanumeric + underscore/hyphen). Invalid IDs are filtered out during playlist retrieval by `_get_playlist_video_ids()`.

---

## Weekly Playlist Snapshots (`src/playlist/weekly.py`)

Creates a rolling weekly copy of the main playlist.

### Naming Convention

`"{prefix} week of YYYY-MM-DD"` where:

- **Prefix** is either `WEEKLY_PLAYLIST_PREFIX` or auto-derived from the main playlist name (strips trailing `(auto)`)
- **Date** is the start of the current week

### Week Calculation

- Timezone-aware via `ZoneInfo` (falls back to UTC)
- Week start day configurable (`MON`-`SUN`)
- `_start_of_week()` computes the most recent occurrence of the configured start day at `00:00:00`

### Pruning

`_prune_old_weeklies()` keeps only the N most recent weekly playlists:

1. Lists all library playlists matching `"{prefix} week of "` pattern
2. Parses ISO dates from titles
3. Sorts by date descending
4. Deletes everything beyond `WEEKLY_KEEP_WEEKS` (default 2)

### Template Caching

Weekly playlists use the same `PlaylistCache` template system - sync is skipped if the video ID list hasn't changed since last run.

---

## `upsert_playlist()` Helper

A convenience function that combines create-or-update with template checking:

1. Look up existing playlist by name
2. If exists and template changed &rarr; `sync_playlist()`
3. If exists and template unchanged &rarr; skip
4. If not found &rarr; `create_playlist_with_items()`

Used by tag-based custom playlists to avoid duplicating the create/update logic.
