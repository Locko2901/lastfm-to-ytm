# Playlist Sync Internals

## Sync Strategy (`src/playlist/sync.py`)

`sync_playlist()` uses a **pre-check, then replace-or-reorder, then verify** approach:

1. **Pre-check current state** - fetch the playlist and compare against the desired list:
    - Exact match &rarr; return immediately (no writes).
    - Same content, different order &rarr; call `_reorder_playlist()` to align order in place via `edit_playlist(moveItem=...)` and return.
2. **Replace content** - otherwise `_replace_playlist_content()` removes all tracks, then adds the desired list.
3. **Verify** - re-fetch the playlist and compare against desired state.
4. **Reorder after replace** - if the result has the right content but wrong order (YouTube does not always preserve add order for bulk inserts), `_reorder_playlist()` fixes it.
5. **Detect substitutions** - if mismatches remain, check whether YouTube replaced videos with equivalent ones.
6. **Retry** - up to `verify_attempts` (default 2) if verification fails.

### In-place Reorder (`_reorder_playlist`)

Walks the desired list and, for each mismatched position, issues `ytm.edit_playlist(playlist_id, moveItem=(setVideoId, successor_setVideoId))` to move the right track into place. Uses `setVideoId` values from `get_playlist()` and updates its local mirror after every move. Worst case is O(n) moves; typical case after a same-content replace is a handful.

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

When `WEEKLY_KEEP_WEEKS > 0`, only the N most recent weekly playlists survive on YTM **and** in the cache (3 entries when `=3`, etc.); older weeks are deleted from both. When `WEEKLY_KEEP_WEEKS = 0`, every weekly playlist is kept forever on YTM and cached. In all cases, `PlaylistCache.clear_old_weekly_songs()` keeps the song template (`video_ids`) only for the current week - older surviving weeks retain just their ID with no songs.

### Discovery & Manual Management

The dashboard **Playlists** tab manages autogenerated playlists outside the normal sync loop (`src/playlist/discover.py`):

- `classify_playlist()` tags a playlist as `main`, `weekly`, `custom`, or `unknown` by exact-name match first, then fuzzy weekly title (`week of YYYY-MM-DD`) and description markers (so renamed playlists are still recognised).
- `discover_playlists()` scans the live library and returns autogenerated candidates with a `tracked` flag. A candidate is tracked when its ID **or its title** matches a cached entry. Title matching is essential because `create_playlist()` and `get_library_playlists()` return **different ID forms** for the same playlist, so a freshly-created playlist's cached ID would never match the library ID and would wrongly appear untracked.
- During **Discover**, cached entries are also **healed**: when a library playlist's title matches a cache entry whose stored ID differs, the cache is updated to the canonical library ID via `PlaylistCache.track_id()`. This keeps every stored ID authoritative so later operations can reference playlists directly by ID.
- The tab loads tracked playlists offline from the cache (no YTM call) and only hits the API on **Discover**. Tracking writes IDs via `PlaylistCache.track_id()` without disturbing existing templates.

### Template Caching

Weekly playlists use the same `PlaylistCache` template system. The change check compares against the **weekly's own** cached template (not the main playlist's), so a per-week snapshot is detected as stale on its first run of the week even when the main playlist hasn't changed. When the weekly already exists, `sync_playlist()` is always invoked - its pre-check makes this a cheap no-op when the playlist is already in order, and a `moveItem`-based reorder when it isn't (e.g. when YTM's bulk add at creation time didn't preserve order).

---

## `upsert_playlist()` Helper

A convenience function that combines create-or-update with template checking:

1. Resolve the existing playlist ID via `get_or_rename_playlist()` (name lookup, with role-based rename fallback)
2. If exists and template changed &rarr; `sync_playlist()`
3. If exists and template unchanged &rarr; skip
4. If not found &rarr; `create_playlist_with_items()`

Used by tag-based custom playlists to avoid duplicating the create/update logic.

---

## Rename Detection (`role` markers)

A managed playlist is looked up **by name** on every run. When a user changes the
playlist's name (e.g. edits `PLAYLIST_NAME`), the name lookup misses and a naive
sync would create a **duplicate** playlist and orphan the old one. To avoid this,
each cached entry carries a stable **`role`** marker that survives renames.

### Cache support (`src/cache/playlist.py`)

- `set_template(name, id, video_ids, *, role=None)` stores the `role` alongside the
  ID and template. When `role` is omitted, any existing role on the entry is preserved.
- `find_by_role(role)` returns `(name, id)` **only when exactly one** entry carries
  that role and has an ID. It returns `None` on no match **or** an ambiguous match
  (multiple entries share the role), so a rename can never target the wrong playlist.
- `rename(old_name, new_name)` migrates the cache key in place, preserving the ID,
  template (`video_ids`), and role, and refreshes `last_updated`.

### Resolver (`get_or_rename_playlist()` in `src/ytm/operations.py`)

1. Try the normal `get_existing_playlist_by_name()` lookup - return the ID on a hit.
2. On a miss, if a `role` is supplied, call `cache.find_by_role(role)`.
3. If a match is found under a **different** name, verify the old playlist still
   exists on YTM via `get_playlist(prev_id, limit=0)`. If it 404s / returns
   `Unable to find 'contents'`, the stale entry is dropped from the cache and the
   caller creates a fresh playlist.
4. Otherwise retitle it in place with `edit_playlist(prev_id, title=name)` and call
   `cache.rename(prev_name, name)`, returning the existing ID - no duplicate created.

### Roles per playlist type

| Playlist | Role | Source |
|---|---|---|
| Main | `"main"` | `src/workflows/main_sync.py` |
| Weekly | `"weekly:<ISO-date>"` (current week's start date) | `src/playlist/weekly.py` |
| Custom / tag | `"custom:<sha1[:16]>"` hashed from the playlist **definition** (kind, tags, artists, match mode, discovery seeds) | `src/tags/sync.py::_custom_playlist_role()` |

Custom playlists have no stable ID in `config/custom_playlists.json` (entries are
keyed by name), so their role is derived from the definition's content. Two custom
playlists with identical definitions produce the same role - `find_by_role()`'s
ambiguity guard then declines to rename either, which is the safe outcome.

Dry-run / preview paths deliberately keep using the read-only
`get_existing_playlist_by_name()` so a preview never mutates playlist titles.

### ID reconciliation (reference by ID)

Because `create_playlist()` returns a different ID form than
`get_library_playlists()`, a cached entry can hold a stale ID for a playlist that
still exists. IDs are kept canonical in three places:

- **At creation time:** `create_playlist_with_items()` immediately calls
  `get_playlist()` (wrapped in the standard `_retry_with_backoff` exponential
  backoff, since the API is flaky) to read back the playlist's **canonical `id`**
  and caches that instead of the compact create-time ID. A transient failure
  falls back to the create-time ID so a sync is never blocked.
- **On a library scan:** whenever `get_existing_playlist_by_name()` falls back to
  a library scan (cache miss, or the cached ID failed to verify), it heals the
  cache in place via `PlaylistCache.track_id()` - updating the stored ID to the
  canonical library ID while preserving the entry's template and role.
- **On Discover:** the Playlists tab's healing pass reconciles every cached entry
  whose title matches a library playlist with a differing ID.

Together these keep every stored ID authoritative so all subsequent edit/sync/
delete operations reference playlists directly by ID rather than re-resolving
them by name.

