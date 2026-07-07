# How It Works

This tool has two sync flows: the **main playlist** (covered below) and, optionally, **custom playlists** (tag- and artist-based). The Docker dashboard exposes both as separate buttons; on the CLI they are `python run.py` and `python run_tags.py`. The rest of this page describes the main flow - custom playlists are documented in [Custom Playlists](tag-playlists.md).

## Overview

1. Fetch recent scrobbles from Last.fm (up to `MAX_RAW_SCROBBLES`, default 2000)
2. Process tracks:
    - If `USE_RECENCY_WEIGHTING=true`, score each track using exponential decay (see [Recency Weighting](#recency-weighting))
    - Otherwise, pick up to `LIMIT` most recent unique tracks
    - If `DEDUPLICATE=true`, ensure the final playlist does not include duplicates
3. Resolve each track to a YouTube Music video ID. Tracks listed in the `_blacklist` section of `config/search_overrides.json` are filtered out first. Surviving tracks are resolved using a three-tier priority:
    1. **Manual overrides** - check the `_overrides` section of `config/search_overrides.json` (user-specified fixes)
    2. **Search cache** - check `cache/.search_cache.json` (previously successful searches, 30-day TTL)
    3. **YouTube Music API** - only query the API if both of the above miss, then cache the result

    This cache-first approach minimizes API calls and ensures consistent results across runs.

4. **Backfill** - if fewer tracks were resolved than `LIMIT`, fetch additional scrobbles and repeat resolution (up to `BACKFILL_PASSES` iterations, default 3)
5. Score and select the best match (see [Search and Matching](#search-and-matching))
6. Create or update YouTube Music playlist(s) with rate-limit-friendly delays (`SLEEP_BETWEEN_SEARCHES`)
7. If `WEEKLY_ENABLED=true`, update the weekly playlist snapshot (see [Weekly Playlists](#weekly-playlists))

!!! note "Playlist lifecycle"
    On the **first** run, the tool creates a new YouTube Music playlist named by `PLAYLIST_NAME`. On every subsequent run it finds the existing playlist by name and updates it in place. The tool manages only the playlist(s) it creates - manual edits to those playlists are reverted on the next run to match the tool's logic. Other playlists in your library are never touched.

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

!!! info "Deeper dive"
    For the full normalization, similarity, and query-building details (with code references), see [Search Internals](search-internals.md).

??? example "Scoring breakdown (advanced)"

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

- **Play score**: raw play counts normalized to 0-1 (see [Play-count normalization](#play-count-normalization) for the strategies)
- **Recency score**: `0.5 ^ (age_hours / half_life_hours)` based on the most recent play
    - A track played exactly one half-life ago scores 0.5
    - More recent = higher score (up to 1.0)
    - Default half-life: **48 hours** (`RECENCY_HALF_LIFE_HOURS=48.0`)
- **Final score**: `play_weight &times; play_score + (1 - play_weight) &times; recency_score`
    - Default: 70% play count, 30% recency (`RECENCY_PLAY_WEIGHT=0.7`)
    - This is a **linear blend**, so `RECENCY_PLAY_WEIGHT` is literally the fraction of the score controlled by play count. `0.9` &rarr; play count dominates; `0.3` &rarr; recency dominates.
- **Minimum play gate**: tracks with fewer than `RECENCY_MIN_PLAYS` scrobbles inside the fetched window are dropped before scoring (default `1` = no gate). Useful for surfacing only songs you've revisited. Note that the gate counts plays inside the fetched recency window only - raise `MAX_RAW_SCROBBLES` if you need a larger window.
- **Sorting priority**: Higher score &rarr; more recent play &rarr; higher play count

When `USE_RECENCY_WEIGHTING=false`, the tool simply takes the most recent unique tracks in chronological order (most recent first), up to `LIMIT`.

### Play-count normalization

`RECENCY_NORMALIZATION` controls how raw play counts become the 0-1 `play_score`:

| Strategy | Formula | Effect |
|----------|---------|--------|
| `linear` (default) | `plays / max_plays` | A single high-play outlier (e.g. one track at 500 plays) flattens everything below it toward zero. |
| `log` | `log1p(plays) / log1p(max_plays)` | Compresses outliers so heavy hitters don't dominate; mid-tier tracks keep meaningful scores. |
| `rank` | tie-averaged percentile position | Ignores absolute magnitude entirely - only the *order* of play counts matters. The most balanced spread. |

All three produce scores in `[0, 1]`, so they plug into the same final-score blend without changing the meaning of `RECENCY_PLAY_WEIGHT`.

### Velocity (trending) weight

`RECENCY_VELOCITY_WEIGHT` (default `0.0` = off) blends a **trending** signal into the final score:

```text
velocity_raw   = plays / days_between_first_and_last_play   (span floored at 1 day)
velocity_score = velocity_raw / max(velocity_raw)           (normalized to 0-1)
final          = (1 - vw) * base_score + vw * velocity_score
```

Because the blend is **linear**, the weight *is* the maximum fraction of the final score velocity can swing - and doubling it roughly doubles the effect (there is no threshold or diminishing-returns curve):

| `RECENCY_VELOCITY_WEIGHT` | Behaviour |
|---------------------------|-----------|
| `0.0` | Off - no effect (default). |
| `0.15`-`0.3` | Surfaces recent binges without letting one-off plays dominate. Recommended range if you want the signal. |
| `0.5` | Half the ranking is pure trending; the playlist becomes noticeably volatile. |
| `1.0` | Ranking is *entirely* plays-per-day; play count and recency are ignored. |

Key nuances:

- It rewards **bursts**: 5 plays in one day scores `5.0/day`, whereas 5 plays spread over 5 days scores `1.0/day`.
- It uses the **raw** play count, *not* the session-weighted count, so it is independent of session weighting.
- A single-play track scores `1/1 = 1.0`, so at high weights one-off plays can rank surprisingly high - another reason the default is off and low values are recommended.

### Session weighting

`RECENCY_SESSION_WEIGHTING` (default `false`) boosts scrobbles that happened during your preferred listening hours before scoring:

- Plays whose local-time hour falls inside the half-open window `RECENCY_SESSION_HOURS` (`[start, end)`, e.g. `9-23`) count as 1.5&times; a play; plays outside count as 1&times;. Windows may wrap past midnight (e.g. `22-4`).
- The local hour is computed in `RECENCY_SESSION_TIMEZONE` (blank inherits the general `TIMEZONE`, then `UTC`).
- The boosted count feeds the play-count normalization above, so it interacts with `RECENCY_NORMALIZATION` but **not** velocity (which uses raw counts).
- It requires per-scrobble timestamps, so it is a **no-op** when `USE_LOCAL_LASTFM_DB=true` (the local history DB keeps only aggregated counts).

---

## Weekly Playlists

When `WEEKLY_ENABLED=true`, the tool creates/updates weekly playlists named:

- `{PLAYLIST_NAME} week of YYYY-MM-DD`, or
- `{WEEKLY_PLAYLIST_PREFIX} week of YYYY-MM-DD` if a prefix is set

If the main playlist name ends with `(auto)`, the prefix strips it automatically (e.g., `Last.fm Recents (auto)` &rarr; `Last.fm Recents week of 2026-04-13`).

The date corresponds to the start of the week (determined by `WEEKLY_WEEK_START` and `WEEKLY_TIMEZONE`). Over time, you build a library of weekly snapshots. Old weeks are automatically pruned based on `WEEKLY_KEEP_WEEKS` (default: 2). Set to `0` to keep all weekly playlists indefinitely.

Weekly playlists inherit the main playlist's privacy setting unless overridden with `WEEKLY_PLAYLIST_PRIVACY` (or the deprecated `WEEKLY_MAKE_PUBLIC` alias).
