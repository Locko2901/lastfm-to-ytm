# How It Works

## Overview

1. Fetch recent scrobbles from Last.fm (up to `MAX_RAW_SCROBBLES`, default 2000)
2. Process tracks:
    - If `USE_RECENCY_WEIGHTING=true`, score each track using exponential decay (see [Recency Weighting](#recency-weighting))
    - Otherwise, pick up to `LIMIT` most recent unique tracks
    - If `DEDUPLICATE=true`, ensure the final playlist does not include duplicates
3. Resolve each track to a YouTube Music video ID using a three-tier priority:
    1. **Blacklist check** - skip tracks listed in the `_blacklist` section of `config/search_overrides.json`
    2. **Manual overrides** - check the `_overrides` section of `config/search_overrides.json` (user-specified fixes)
    3. **Search cache** - check `cache/.search_cache.json` (previously successful searches, 30-day TTL)
    4. **YouTube Music API** - only query the API if all of the above miss, then cache the result

    This cache-first approach minimizes API calls and ensures consistent results across runs.

4. **Backfill** - if fewer tracks were resolved than `LIMIT`, fetch additional scrobbles and repeat resolution (up to `BACKFILL_PASSES` iterations, default 3)
5. Score and select the best match (see [Search and Matching](#search-and-matching))
6. Create or update YouTube Music playlist(s) with rate-limit-friendly delays (`SLEEP_BETWEEN_SEARCHES`)
7. If `WEEKLY_ENABLED=true`, update the weekly playlist snapshot (see [Weekly Playlists](#weekly-playlists))

---

## Search and Matching

For each track, the engine builds multiple search queries (exact match, artist + title, title only) and runs them against the YouTube Music API using up to `SEARCH_MAX_WORKERS` parallel threads. Results are scored and the best match is selected.

The matching algorithm aims to select the "right" track:

- Prefers official **Song** results over user-uploaded **Videos**
- Scores title, artist(s), uploader, and album similarity
- Handles common artist variations and multi-artist collaborations
- Avoids covers, remixes, and live versions unless they are the closest available match
- Can perform authenticated or anonymous search (`USE_ANON_SEARCH`), which may affect results
- Supports **early termination**: if a match scores above `EARLY_TERMINATION_SCORE` (default 0.9), searching stops immediately to save API calls

If a track cannot be matched reliably, it is cached as "not found" (retried after `CACHE_NOTFOUND_TTL_DAYS`, default 7) and skipped for the current run.

### Scoring Breakdown

The base match score is calculated as:

| Component | Weight |
|-----------|--------|
| Title similarity | 56% |
| Artist similarity | 32% |
| Uploader match | 7% |
| Album bonus | 5% |

Additional adjustments:

- **Hard rejects**: "nightcore", "daycore", "sped", "slowed", "8d", "chipmunk", "reverb", "pitch", "bassboosted" in video results (non-Topic channels) &rarr; rejected outright
- **Soft penalties**: "live", "acoustic", "remix", "cover", "karaoke", "instrumental", etc. &rarr; -8% per term (capped at 25%). Hard negative terms that slip through (e.g., in song results) get -35% per term (capped at 60%).
- **Result type**: Songs get +6%, Videos get -3%, "Topic" channels with good uploader match get +2%
- **Style mismatch**: If you actually *want* a nightcore/sped-up version but the candidate lacks it, an additional -12% to -18% penalty is applied
- **Minimum thresholds**: Artist similarity must be &ge; 0.30, title similarity must be &ge; 0.25, or the candidate is discarded
- **Acceptance thresholds**: Base threshold of 0.66 (0.68 when album data is available), with an additional +0.05 for video results

---

## Recency Weighting

When enabled, the tool combines play count and recency to rank tracks:

- **Play score**: `plays / max_plays` (normalized to 0-1)
- **Recency score**: `0.5 ^ (age_hours / half_life_hours)` based on the most recent play
    - A track played exactly one half-life ago scores 0.5
    - More recent = higher score (up to 1.0)
    - Default half-life: **24 hours** (`RECENCY_HALF_LIFE_HOURS=24.0`)
- **Final score**: `play_weight &times; play_score + (1 - play_weight) &times; recency_score`
    - Default: 70% play count, 30% recency (`RECENCY_PLAY_WEIGHT=0.7`)
- **Sorting priority**: Higher score &rarr; more recent play &rarr; higher play count

When `USE_RECENCY_WEIGHTING=false`, the tool simply takes the most recent unique tracks in chronological order (most recent first), up to `LIMIT`.

---

## Weekly Playlists

When `WEEKLY_ENABLED=true`, the tool creates/updates weekly playlists named:

- `{PLAYLIST_NAME} week of YYYY-MM-DD`, or
- `{WEEKLY_PLAYLIST_PREFIX} week of YYYY-MM-DD` if a prefix is set

If the main playlist name ends with `(auto)`, the prefix strips it automatically (e.g., `Last.fm Recents (auto)` &rarr; `Last.fm Recents week of 2026-04-13`).

The date corresponds to the start of the week (determined by `WEEKLY_WEEK_START` and `WEEKLY_TIMEZONE`). Over time, you build a library of weekly snapshots. Old weeks are automatically pruned based on `WEEKLY_KEEP_WEEKS` (default: 2). Set to `0` to keep all weekly playlists indefinitely.

Weekly playlists inherit the main playlist's privacy setting unless overridden with `WEEKLY_MAKE_PUBLIC`.
