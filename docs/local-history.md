# Local Last.fm History Database

By default, the tool builds your main playlist from a **recent** slice of your
Last.fm scrobbles. The **local Last.fm history database** changes this: it
crawls your *entire* listening history into a small local SQLite database and
ranks the playlist by **lifetime play count + recency** instead.

!!! warning "Playlist behaviour changes"
    Enabling this changes how the main playlist is built. Instead of "what you
    played recently", the playlist becomes "your most-played tracks, weighted
    toward ones you've returned to lately". The resulting playlist can look
    noticeably different. This is expected.

## How it works

1. **First sync (full crawl).** When the local database is empty, the next sync
   pages through your *complete* Last.fm history and stores, for every unique
   `(artist, track)`:
    - a lifetime **play count** (how often it was scrobbled),
    - the **first** and **last** time it was played.

    This can take a while on the first run, depending on how many scrobbles you
    have. Progress is logged as it ingests.

2. **Follow-up syncs (incremental).** Later syncs only fetch scrobbles newer
   than the last one ingested. Existing tracks get their play counts bumped and
   their "last played" timestamp updated; brand-new tracks are added.

3. **Ranking.** Tracks are scored with the same recency formula used elsewhere,
   but the play-count component uses your **lifetime** plays and recency decays
   from the **last time you played** each track:

    $$\text{score} = w_p \cdot \frac{\text{plays}}{\text{max plays}} + (1 - w_p) \cdot 0.5^{\,(\text{hours since last play}) / \text{half life}}$$

    where $w_p$ is `RECENCY_PLAY_WEIGHT` and the half-life is
    `RECENCY_HALF_LIFE_HOURS`.

The top-scoring tracks (up to your `LIMIT`) are resolved on YouTube Music and
synced to the playlist.

## Enabling it

=== "Dashboard"

    Open **Settings &rarr; Local Last.fm History** and tick **Use local Last.fm
    database**, then save. The status line shows how many unique tracks and
    plays have been ingested once the first sync completes.

=== ".env"

    ```bash
    USE_LOCAL_LASTFM_DB=true
    # Optional:
    LASTFM_LOCAL_DB_FILE=cache/lastfm_history.db   # where to store the DB
    LASTFM_LOCAL_DB_MAX_SCROBBLES=0                # safety cap per crawl (0 = unlimited)
    ```

Run a sync afterwards to trigger the first full crawl.

## Settings reference

| Setting | Default | Description |
| --- | --- | --- |
| `USE_LOCAL_LASTFM_DB` | `false` | Build the main playlist from your full local scrobble history. |
| `LASTFM_LOCAL_DB_FILE` | `cache/lastfm_history.db` | Path to the local history database file. |
| `LASTFM_LOCAL_DB_MAX_SCROBBLES` | `0` | Safety cap on scrobbles ingested per crawl (0 = unlimited). Useful to bound the very first crawl. |

The same `RECENCY_HALF_LIFE_HOURS`, `RECENCY_PLAY_WEIGHT`, and
`RECENCY_MIN_PLAYS` settings tune the ranking.

## Relationship to the History Database

This is a **separate** database from the [History Database](history.md), which
tracks YouTube Music lookups, sync runs, and actions for analytics.

When **both** are enabled, the History tab's **Total Tracks** stat and the
**Top Tracks** subtab are sourced from the local Last.fm database - so they
reflect your *full listening library* and *lifetime plays* rather than YouTube
Music lookup frequency. Disable the local database and those views revert to the
History Database's own data.

## Managing the database

The local Last.fm database lives alongside the
[History Database](history.md) under **Settings &rarr; Local Databases**. When the
setting is enabled, that subsection gains a **Clear Last.fm History** button, and
a matching entry appears under **Settings &rarr; Data Management**:

- **Clear Last.fm History** - deletes every stored scrobble and resets the sync
  watermark. The next sync re-crawls your full Last.fm history.
- **Export** - downloads the entire database as a plaintext JSON dump.
- **Import** - restores a previously exported dump. **Merge** is idempotent
  (re-importing the same file changes nothing, since play counts take the
  maximum rather than summing); **Replace** wipes the database first.

It can also be bundled into an encrypted [Teleporter](teleporter.md) backup -
tick **Local Last.fm database** under *Include cache files* when exporting. On
import it is merged idempotently into the target instance (when the local
database setting is enabled there).

## Notes

- The database is lightweight: one aggregated row per unique track, no per-play
  rows. Even very large libraries stay small.
- It lives under `cache/` and is excluded from version control like the other
  caches. Back it up via the [Teleporter](teleporter.md) or the Export button
  above if desired.
- Switching the setting off leaves the database in place; switching it back on
  resumes incrementally from where it left off.
