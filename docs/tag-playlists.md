# Custom Playlists

Create automatic YouTube Music playlists that fill themselves with matching tracks from your scrobble history. Each custom playlist is one of two **types**:

- **Tag playlists** - include tracks by Last.fm tags/genres. For example, a "Breakcore Mix" playlist that only includes tracks tagged `breakcore` or `drill and bass`, or a "Chill Electronic" playlist that requires both `electronic` and `ambient`.
- **Artist playlists** - include every found track by one or more specific artists. For example, a "Radiohead & Aphex Twin" playlist that gathers all of those artists' tracks from your history.

??? example "Screenshot: Custom Playlists editor"
    ![Custom Playlists](screenshots/custom_playlists.png)

!!! tip "Related"
    Custom playlists honor the same `_overrides`, `_blacklist`, and `_blacklist_artists` you set up in [Search Overrides](overrides.md), plus **per-playlist** `blacklist`/`blacklist_artists` fields (see [Configuration](#configuration) below). Use tag overrides when Last.fm's tags are wrong; use search overrides when the *matched video* is wrong.

## How Tags Are Resolved

Tag playlists use a cache-first approach to find each track's Last.fm tags (artist playlists skip this step entirely, since they match on artist name alone):

1. **Tag overrides** - check `config/tag_overrides.json` (user manual fixes). If the override mode is `"replace"`, the override tags are used directly and steps 2-3 are skipped.
2. **Tag cache** - check `runtime/.tag_cache.json` (90-day TTL, configurable via `TAG_CACHE_TTL_DAYS`)
3. **Last.fm API** - fetch via `track.getTopTags`, falling back to `artist.getTopTags` if track-level tags are unavailable

After fetching, `"add"` mode tag overrides are merged into the result (this allows supplementing Last.fm's tags without replacing them entirely).

Tags with fewer votes than `TAG_MIN_COUNT` (default: 10) are filtered out to avoid noise.

!!! info "How `TAG_MIN_COUNT` shapes the playlist"
    This threshold decides how many tags each track is allowed to carry, which in turn decides how many tracks qualify:

    - **Raise it** (e.g. `50`) &rarr; only strong, widely-agreed tags survive, so fewer tracks match your `tags` and the playlist gets **smaller and more precise** (and may struggle to reach `limit`, leaning harder on backfill).
    - **Lower it** (e.g. `1`) &rarr; niche and noisy tags count too, so **more tracks match** and the playlist grows, at the cost of the occasional off-genre song.

If backfilling is enabled and a playlist has not reached its target track count after filtering, the tool automatically fetches more scrobbles and repeats until the limit is met or no more data is available.

---

## Configuration

**Docker**: Use the web dashboard to create and manage custom playlists. Pick the **Playlist Type** (genre tags or artists) in the editor. Sync can be triggered manually from the UI, or automatically after each scheduled main sync via `AUTO_TAG_SYNC_ENABLED` and `AUTO_TAG_SYNC_FREQUENCY` (see [Configuration](configuration.md)).

**CLI**: Edit `config/custom_playlists.json` directly:

### 1. Create the config file

```bash
cp config/custom_playlists.json.example config/custom_playlists.json
```

### 2. Define your playlists

```json
{
  "playlists": [
    {
      "name": "Breakcore Mix (auto)",
      "tags": ["breakcore", "drill and bass"],
      "match": "any",
      "limit": 50,
      "backfill": true,
      "blacklist": []
    },
    {
      "name": "Ambient Electronic (auto)",
      "tags": ["ambient", "electronic"],
      "match": "all",
      "limit": 30,
      "backfill": true,
      "privacy": "PUBLIC",
      "blacklist": ["artist name|unwanted track"],
      "blacklist_artists": ["unwanted artist"]
    },
    {
      "name": "My Favorite Artists (auto)",
      "kind": "artists",
      "artists": ["radiohead", "aphex twin"],
      "limit": 50,
      "backfill": true
    }
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Playlist name on YouTube Music |
| `kind` | no | `"tags"` (default) or `"artists"` |
| `description` | no | Optional playlist description (empty = auto-generated) |
| `tags` | tag playlists | Last.fm tags to match against (required when `kind` is `"tags"`) |
| `artists` | artist playlists | Lowercase artist names to include (required when `kind` is `"artists"`) |
| `match` | no | `"any"` (track has at least one tag, default) or `"all"` (track has every tag). Tag playlists only. `"any"` casts a wide net &rarr; **bigger** playlist; `"all"` is strict AND logic &rarr; **smaller, tightly-filtered** playlist (e.g. `["ambient", "electronic"]` with `"all"` keeps only tracks tagged *both*) |
| `limit` | no | Target number of tracks (default: `50`) |
| `backfill` | no | Fetch more scrobbles if filtering doesn't reach the limit (default: `true`) |
| `privacy` | no | Per-playlist visibility: `"PUBLIC"`, `"UNLISTED"`, or `"PRIVATE"` (omit/empty to inherit the global `CUSTOM_PLAYLISTS_PRIVACY` setting) |
| `blacklist` | no | Per-playlist exclusions as `"artist\|title"` (lowercase) |
| `blacklist_artists` | no | Per-playlist artist exclusions (lowercase artist names) |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CUSTOM_PLAYLISTS_FILE` | `config/custom_playlists.json` | Path to playlist definitions |
| `TAG_CACHE_TTL_DAYS` | `90` | Days before cached tags expire |
| `TAG_MIN_COUNT` | `10` | Minimum Last.fm tag count threshold |
| `TAG_SLEEP_BETWEEN` | `0.25` | Seconds between tag API calls |
| `CUSTOM_PLAYLISTS_PRIVACY` | *(main setting)* | Default privacy for custom playlists (`PUBLIC` / `UNLISTED` / `PRIVATE`). Overridable per playlist with the `privacy` field above |
| `BACKFILL_PASSES` | `3` | Maximum backfill iterations |

---

## Tag Overrides

When Last.fm's tag data is wrong or incomplete, you can manually fix it.

**Docker**: Use the web dashboard's tag management interface.

**CLI**: Edit `config/tag_overrides.json` directly:

### 1. Create the overrides file

```bash
cp config/tag_overrides.json.example config/tag_overrides.json
```

### 2. Add your override

```json
{
  "_overrides": {
    "artist name|song title": {
      "artist": "Artist Name",
      "title": "Song Title",
      "tags": ["breakcore", "electronic"],
      "mode": "add",
      "reason": "Last.fm only has 'electronic', adding 'breakcore'"
    }
  }
}
```

| Field | Description |
|-------|-------------|
| Key | `artist\|title` in **lowercase** |
| `tags` | List of tag names to apply |
| `mode` | `"add"` merges with existing Last.fm tags, `"replace"` overwrites them entirely |
| `reason` | Optional note for your reference |

---

## Running Custom Sync

Custom playlists (both tag- and artist-based) are synced separately from the main playlist. Use the dedicated entry point:

```bash
python run_tags.py  # or: lastfm-ytm-tags
```

!!! warning
    `python run.py` only runs the main playlist sync. Custom playlists must be triggered separately via `run_tags.py` or from the web dashboard (**Custom Playlist Sync** in the run menu).

### Syncing specific playlists

The run menu's **Custom Playlist Sync** rebuilds *every* configured custom
playlist. To refresh just one (or a handful) without touching the rest, use the
**Custom Playlists** tab instead:

- Each playlist card has its own **Sync** button that rebuilds only that
  playlist.
- The **Sync Multiple…** button in the toolbar opens a dialog where you tick one
  or more playlists (or none, to sync all) and rebuild exactly those in a single
  run.

Both routes reuse the same engine as a full custom sync - they simply restrict
it to the chosen playlist names - so backfill, blacklists, and limits all behave
identically. Auto-sync exclusions are ignored for these manual runs: a playlist
marked **No Auto-sync** is still rebuilt when you sync it explicitly.

