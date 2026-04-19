# History Database

An optional local SQLite database that tracks all synced songs, actions, and sync runs for audit and visibility.

## What It Tracks

The database stores three types of records:

- **Tracks** - every song the sync engine encounters, including artist, title, matched video ID, match score, resolution source (cache/search/override), and how many times it was found or missed
- **Syncs** - a record of every sync run with timestamps, duration, track counts, API usage stats (searches, playlist operations, cache hits/misses, override hits), and final status
- **Actions** - user-initiated actions like adding overrides, blacklisting, or clearing cache entries (logged by the web dashboard)

When `HISTORY_MAX_SIZE_MB` is set to a non-zero value, the database auto-prunes the oldest records when the file exceeds the specified size.

## Configuration

**Docker**: Toggle via **Settings &rarr; History Database**.

**CLI**: Add to your `.env`:

```bash
HISTORY_DB_ENABLED=false               # Enable/disable the history database
HISTORY_DB_FILE=cache/history.db       # Path to the database file
HISTORY_MAX_SIZE_MB=0                  # Auto-prune oldest records when exceeded (0 = unlimited)
```

| Variable | Default | Description |
|----------|---------|-------------|
| `HISTORY_DB_ENABLED` | `false` | Track all songs, syncs, and actions in a local SQLite DB |
| `HISTORY_DB_FILE` | `cache/history.db` | Path to the history database file |
| `HISTORY_MAX_SIZE_MB` | `0` | Auto-prune oldest records when exceeded (`0` = unlimited) |
