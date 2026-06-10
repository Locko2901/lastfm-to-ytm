"""SQLite-based history database for tracking songs, syncs, and actions."""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 3

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    artist      TEXT    NOT NULL COLLATE NOCASE,
    title       TEXT    NOT NULL COLLATE NOCASE,
    video_id    TEXT,
    yt_title    TEXT,
    source      TEXT    NOT NULL DEFAULT 'search',
    first_seen  TEXT    NOT NULL,
    last_seen   TEXT    NOT NULL,
    times_found INTEGER NOT NULL DEFAULT 1,
    times_missed INTEGER NOT NULL DEFAULT 0,
    best_score  REAL,
    UNIQUE(artist, title)
);

CREATE INDEX IF NOT EXISTS idx_tracks_artist_title ON tracks(artist, title);
CREATE INDEX IF NOT EXISTS idx_tracks_video_id     ON tracks(video_id);
CREATE INDEX IF NOT EXISTS idx_tracks_last_seen    ON tracks(last_seen);

CREATE TABLE IF NOT EXISTS syncs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    duration_secs   REAL,
    sync_type       TEXT    NOT NULL DEFAULT 'main',
    trigger         TEXT    NOT NULL DEFAULT 'manual',
    status          TEXT    NOT NULL DEFAULT 'running',
    tracks_total    INTEGER DEFAULT 0,
    tracks_resolved INTEGER DEFAULT 0,
    tracks_missed   INTEGER DEFAULT 0,
    api_searches    INTEGER DEFAULT 0,
    api_playlist_ops INTEGER DEFAULT 0,
    cache_hits      INTEGER DEFAULT 0,
    cache_misses    INTEGER DEFAULT 0,
    override_hits   INTEGER DEFAULT 0,
    error_message   TEXT
);

CREATE INDEX IF NOT EXISTS idx_syncs_started_at ON syncs(started_at);
CREATE INDEX IF NOT EXISTS idx_syncs_status     ON syncs(status);

CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    action_type TEXT    NOT NULL,
    artist      TEXT,
    title       TEXT,
    video_id    TEXT,
    detail      TEXT,
    source      TEXT    NOT NULL DEFAULT 'web'
);

CREATE INDEX IF NOT EXISTS idx_actions_timestamp   ON actions(timestamp);
CREATE INDEX IF NOT EXISTS idx_actions_action_type ON actions(action_type);
"""


class HistoryDB:
    """Thread-safe SQLite history database."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_schema(self) -> None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.executescript(_SCHEMA_SQL)

        cur.execute("SELECT COUNT(*) FROM schema_version")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
            conn.commit()
        else:
            cur.execute("SELECT version FROM schema_version LIMIT 1")
            current = cur.fetchone()[0]
            if current < _SCHEMA_VERSION:
                if current < 2:
                    self._migrate_v1_to_v2(conn)
                if current < 3:
                    self._migrate_v2_to_v3(conn)
                conn.commit()
        log.debug("History DB initialized at %s (schema v%d)", self._db_path, _SCHEMA_VERSION)

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        """Migrate schema v1 → v2: add COLLATE NOCASE to tracks."""
        cur = conn.cursor()
        cur.executescript("""
            ALTER TABLE tracks RENAME TO _tracks_old;

            CREATE TABLE tracks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                artist      TEXT    NOT NULL COLLATE NOCASE,
                title       TEXT    NOT NULL COLLATE NOCASE,
                video_id    TEXT,
                yt_title    TEXT,
                source      TEXT    NOT NULL DEFAULT 'search',
                first_seen  TEXT    NOT NULL,
                last_seen   TEXT    NOT NULL,
                times_found INTEGER NOT NULL DEFAULT 1,
                best_score  REAL,
                UNIQUE(artist, title)
            );

            INSERT OR IGNORE INTO tracks
                (id, artist, title, video_id, yt_title, source, first_seen, last_seen, times_found, best_score)
            SELECT id, artist, title, video_id, yt_title, source, first_seen, last_seen, times_found, best_score
            FROM _tracks_old;

            DROP TABLE _tracks_old;

            CREATE INDEX IF NOT EXISTS idx_tracks_artist_title ON tracks(artist, title);
            CREATE INDEX IF NOT EXISTS idx_tracks_video_id     ON tracks(video_id);
            CREATE INDEX IF NOT EXISTS idx_tracks_last_seen    ON tracks(last_seen);

            UPDATE schema_version SET version = 2;
        """)
        log.info("Migrated history DB schema v1 → v2 (COLLATE NOCASE on tracks)")

    def _migrate_v2_to_v3(self, conn: sqlite3.Connection) -> None:
        """Migrate schema v2 → v3: add times_missed column."""
        cur = conn.cursor()
        cur.execute("ALTER TABLE tracks ADD COLUMN times_missed INTEGER NOT NULL DEFAULT 0")
        cur.execute("UPDATE schema_version SET version = 3")
        log.info("Migrated history DB schema v2 → v3 (added times_missed)")

    def close(self) -> None:
        """Close the thread-local database connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def record_track(
        self,
        artist: str,
        title: str,
        video_id: str | None = None,
        yt_title: str | None = None,
        source: str = "search",
        score: float | None = None,
        missed: bool = False,
    ) -> None:
        """Upsert a track, incrementing times_found or times_missed on conflict."""
        now = datetime.now(UTC).isoformat()
        found_inc = 0 if missed else 1
        missed_inc = 1 if missed else 0
        with self._cursor() as cur:
            cur.execute(
                """INSERT INTO tracks (artist, title, video_id, yt_title, source, first_seen, last_seen, times_found, times_missed, best_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(artist, title) DO UPDATE SET
                       video_id     = COALESCE(excluded.video_id, video_id),
                       yt_title     = COALESCE(excluded.yt_title, yt_title),
                       source       = excluded.source,
                       last_seen    = excluded.last_seen,
                       times_found  = times_found + excluded.times_found,
                       times_missed = times_missed + excluded.times_missed,
                       best_score   = MAX(COALESCE(best_score, 0), COALESCE(excluded.best_score, 0))""",
                (artist, title, video_id, yt_title, source, now, now, found_inc, missed_inc, score),
            )

    def get_tracks(
        self,
        limit: int = 200,
        offset: int = 0,
        sort: str = "last_seen",
        order: str = "desc",
        search: str | None = None,
        source_filter: str | None = None,
        found_filter: str | None = None,
    ) -> list[dict]:
        """Return paginated tracks with optional search, source, and found filters."""
        sort_columns = {
            "last_seen": "last_seen",
            "first_seen": "first_seen",
            "times_found": "times_found",
            "times_missed": "times_missed",
            "artist": "artist",
            "title": "title",
        }
        sort_col = sort_columns.get(sort, "last_seen")
        order_sql = "ASC" if order.lower() == "asc" else "DESC"

        conditions: list[str] = []
        params: list[Any] = []

        if search:
            conditions.append("(artist LIKE ? OR title LIKE ? OR yt_title LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if source_filter:
            conditions.append("source = ?")
            params.append(source_filter)
        if found_filter == "found":
            conditions.append("video_id IS NOT NULL")
        elif found_filter == "not_found":
            conditions.append("video_id IS NULL")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        query = f"SELECT * FROM tracks {where} ORDER BY {sort_col} {order_sql} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._cursor() as cur:
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]

    def get_track_count(self, search: str | None = None, source_filter: str | None = None, found_filter: str | None = None) -> int:
        """Count tracks matching the given filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if search:
            conditions.append("(artist LIKE ? OR title LIKE ? OR yt_title LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like, like])
        if source_filter:
            conditions.append("source = ?")
            params.append(source_filter)
        if found_filter == "found":
            conditions.append("video_id IS NOT NULL")
        elif found_filter == "not_found":
            conditions.append("video_id IS NULL")

        where = ""
        if conditions:
            where = "WHERE " + " AND ".join(conditions)

        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM tracks {where}", params)
            return cur.fetchone()[0]

    def get_track_history(self, artist: str, title: str) -> dict | None:
        """Return history summary for a specific track, if available."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT artist, title, video_id, yt_title, source, first_seen, last_seen, times_found, times_missed, best_score
                   FROM tracks WHERE artist = ? AND title = ?""",
                (artist, title),
            )
            row = cur.fetchone()
            if row is None:
                return None

            result = dict(row)
            cur.execute(
                """SELECT COUNT(*) FROM actions
                   WHERE artist IS NOT NULL AND title IS NOT NULL
                     AND artist = ? COLLATE NOCASE AND title = ? COLLATE NOCASE""",
                (artist, title),
            )
            result["action_count"] = cur.fetchone()[0]
            return result

    def start_sync(self, sync_type: str = "main", trigger: str = "manual") -> int:
        """Record sync start and return its row ID.

        If a non-finished sync of the same type was started within the last 5 seconds,
        return its ID instead of inserting a duplicate (handles scheduler + manual
        race conditions firing in the same second).
        """
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        recent_cutoff = (now_dt - timedelta(seconds=5)).isoformat()
        with self._cursor() as cur:
            cur.execute(
                """SELECT id FROM syncs
                   WHERE sync_type = ? AND status = 'running' AND started_at >= ?
                   ORDER BY started_at DESC LIMIT 1""",
                (sync_type, recent_cutoff),
            )
            row = cur.fetchone()
            if row is not None:
                return row["id"]
            cur.execute(
                "INSERT INTO syncs (started_at, sync_type, trigger, status) VALUES (?, ?, ?, 'running')",
                (now, sync_type, trigger),
            )
            return cur.lastrowid

    def finish_sync(
        self,
        sync_id: int,
        *,
        status: str = "success",
        tracks_total: int = 0,
        tracks_resolved: int = 0,
        tracks_missed: int = 0,
        api_searches: int = 0,
        api_playlist_ops: int = 0,
        cache_hits: int = 0,
        cache_misses: int = 0,
        override_hits: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Finalise a sync record with duration and metrics."""
        now = datetime.now(UTC).isoformat()
        with self._cursor() as cur:
            cur.execute("SELECT started_at FROM syncs WHERE id = ?", (sync_id,))
            row = cur.fetchone()
            duration = None
            if row:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                    duration = (datetime.now(UTC) - started).total_seconds()
                except Exception:
                    pass

            cur.execute(
                """UPDATE syncs SET
                       finished_at = ?, duration_secs = ?, status = ?,
                       tracks_total = ?, tracks_resolved = ?, tracks_missed = ?,
                       api_searches = ?, api_playlist_ops = ?,
                       cache_hits = ?, cache_misses = ?, override_hits = ?,
                       error_message = ?
                   WHERE id = ?""",
                (
                    now,
                    duration,
                    status,
                    tracks_total,
                    tracks_resolved,
                    tracks_missed,
                    api_searches,
                    api_playlist_ops,
                    cache_hits,
                    cache_misses,
                    override_hits,
                    error_message,
                    sync_id,
                ),
            )

    def get_syncs(
        self,
        limit: int = 50,
        offset: int = 0,
        date_from: str | None = None,
        date_to: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Return paginated sync records, newest first, with optional date range and status."""
        conditions: list[str] = []
        params: list[Any] = []
        if date_from:
            conditions.append("started_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("started_at <= ?")
            params.append(date_to)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        with self._cursor() as cur:
            cur.execute(f"SELECT * FROM syncs {where} ORDER BY started_at DESC LIMIT ? OFFSET ?", params)
            return [dict(row) for row in cur.fetchall()]

    def get_sync(self, sync_id: int) -> dict | None:
        """Return a single sync record by ID."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM syncs WHERE id = ?", (sync_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_sync_count(self, date_from: str | None = None, date_to: str | None = None, status: str | None = None) -> int:
        """Return total number of sync records, with optional date range and status."""
        conditions: list[str] = []
        params: list[Any] = []
        if date_from:
            conditions.append("started_at >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("started_at <= ?")
            params.append(date_to)
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM syncs {where}", params)
            return cur.fetchone()[0]

    def record_action(
        self,
        action_type: str,
        artist: str | None = None,
        title: str | None = None,
        video_id: str | None = None,
        detail: str | None = None,
        source: str = "web",
    ) -> None:
        """Record a user or system action.

        Deduplicates against an identical action recorded in the last 5 seconds
        (same action_type, artist, title, video_id, detail, source). Protects
        against webhook double-fire, SSE reconnect re-emit, and scheduler +
        manual trigger races.
        """
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        recent_cutoff = (now_dt - timedelta(seconds=5)).isoformat()
        with self._cursor() as cur:
            cur.execute(
                """SELECT 1 FROM actions
                   WHERE timestamp >= ?
                     AND action_type = ?
                     AND IFNULL(artist, '')   = IFNULL(?, '')
                     AND IFNULL(title, '')    = IFNULL(?, '')
                     AND IFNULL(video_id, '') = IFNULL(?, '')
                     AND IFNULL(detail, '')   = IFNULL(?, '')
                     AND source = ?
                   LIMIT 1""",
                (recent_cutoff, action_type, artist, title, video_id, detail, source),
            )
            if cur.fetchone() is not None:
                return
            cur.execute(
                "INSERT INTO actions (timestamp, action_type, artist, title, video_id, detail, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (now, action_type, artist, title, video_id, detail, source),
            )

    def get_actions(
        self,
        limit: int = 100,
        offset: int = 0,
        action_type: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """Return paginated actions, optionally filtered by type and date range."""
        conditions: list[str] = []
        params: list[Any] = []
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        with self._cursor() as cur:
            cur.execute(f"SELECT * FROM actions {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?", params)
            return [dict(row) for row in cur.fetchall()]

    def get_action_count(self, action_type: str | None = None, date_from: str | None = None, date_to: str | None = None) -> int:
        """Count actions, optionally filtered by type and date range."""
        conditions: list[str] = []
        params: list[Any] = []
        if action_type:
            conditions.append("action_type = ?")
            params.append(action_type)
        if date_from:
            conditions.append("timestamp >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("timestamp <= ?")
            params.append(date_to)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM actions {where}", params)
            return cur.fetchone()[0]

    def get_overview_stats(self) -> dict:
        """Return aggregate statistics across tracks, syncs, and actions."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tracks")
            total_tracks = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM tracks WHERE video_id IS NOT NULL")
            found_tracks = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM tracks WHERE video_id IS NULL")
            not_found_tracks = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM syncs")
            total_syncs = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM syncs WHERE status = 'success'")
            successful_syncs = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM syncs WHERE status = 'error'")
            failed_syncs = cur.fetchone()[0]

            cur.execute("SELECT AVG(duration_secs) FROM syncs WHERE duration_secs IS NOT NULL")
            row = cur.fetchone()
            avg_duration = round(row[0], 1) if row[0] else 0

            cur.execute("SELECT SUM(api_searches) FROM syncs")
            row = cur.fetchone()
            total_api_searches = row[0] or 0

            cur.execute("SELECT SUM(api_playlist_ops) FROM syncs")
            row = cur.fetchone()
            total_api_playlist_ops = row[0] or 0

            cur.execute("SELECT SUM(cache_hits), SUM(cache_misses) FROM syncs")
            row = cur.fetchone()
            total_cache_hits = row[0] or 0
            total_cache_misses = row[1] or 0

            cur.execute("SELECT COUNT(*) FROM actions")
            total_actions = cur.fetchone()[0]

            cur.execute("SELECT SUM(times_found) FROM tracks")
            row = cur.fetchone()
            total_lookups = row[0] or 0

            cache_total = total_cache_hits + total_cache_misses
            cache_hit_rate = round(total_cache_hits / cache_total * 100, 1) if cache_total > 0 else 0

            return {
                "total_tracks": total_tracks,
                "found_tracks": found_tracks,
                "not_found_tracks": not_found_tracks,
                "total_syncs": total_syncs,
                "successful_syncs": successful_syncs,
                "failed_syncs": failed_syncs,
                "avg_duration": avg_duration,
                "total_api_searches": total_api_searches,
                "total_api_playlist_ops": total_api_playlist_ops,
                "total_cache_hits": total_cache_hits,
                "total_cache_misses": total_cache_misses,
                "cache_hit_rate": cache_hit_rate,
                "total_actions": total_actions,
                "total_lookups": total_lookups,
            }

    def get_top_tracks(self, limit: int = 20) -> list[dict]:
        """Return tracks ordered by times_found descending."""
        with self._cursor() as cur:
            cur.execute(
                "SELECT artist, title, video_id, yt_title, times_found, first_seen, last_seen FROM tracks ORDER BY times_found DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_recent_actions(self, limit: int = 20) -> list[dict]:
        """Return most recent actions."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM actions ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]

    def get_action_type_counts(self) -> dict[str, int]:
        """Return action counts grouped by type."""
        with self._cursor() as cur:
            cur.execute("SELECT action_type, COUNT(*) as cnt FROM actions GROUP BY action_type ORDER BY cnt DESC")
            return {row["action_type"]: row["cnt"] for row in cur.fetchall()}

    def get_source_counts(self) -> dict[str, int]:
        """Return track counts grouped by source."""
        with self._cursor() as cur:
            cur.execute("SELECT source, COUNT(*) as cnt FROM tracks GROUP BY source ORDER BY cnt DESC")
            return {row["source"]: row["cnt"] for row in cur.fetchall()}

    def backfill_from_search_cache(self, cache_data: dict) -> int:
        """Import tracks from search cache data into the history DB."""
        count = 0
        now = datetime.now(UTC).isoformat()
        with self._cursor() as cur:
            for key, entry in cache_data.items():
                parts = key.split("|", 1)
                if len(parts) != 2:
                    continue
                artist, title = parts
                video_id = entry.get("video_id")
                yt_title = entry.get("yt_title")
                timestamp = entry.get("timestamp", now)

                cur.execute(
                    """INSERT INTO tracks (artist, title, video_id, yt_title, source, first_seen, last_seen, times_found)
                       VALUES (?, ?, ?, ?, 'cache_backfill', ?, ?, 1)
                       ON CONFLICT(artist, title) DO UPDATE SET
                           video_id  = COALESCE(video_id, excluded.video_id),
                           yt_title  = COALESCE(yt_title, excluded.yt_title)""",
                    (artist, title, video_id, yt_title, timestamp, timestamp),
                )
                count += 1

        self.record_action("backfill_from_cache", detail=f"Imported {count} entries from search cache", source="web")
        log.info("Backfilled %d entries from search cache into history DB", count)
        return count

    def backfill_from_overrides(self, overrides_data: dict) -> int:
        """Import tracks from override data into the history DB."""
        count = 0
        now = datetime.now(UTC).isoformat()
        with self._cursor() as cur:
            for key, entry in overrides_data.items():
                parts = key.split("|", 1)
                if len(parts) != 2:
                    continue
                artist, title = parts
                video_id = entry.get("video_id")

                cur.execute(
                    """INSERT INTO tracks (artist, title, video_id, source, first_seen, last_seen, times_found)
                       VALUES (?, ?, ?, 'override_backfill', ?, ?, 1)
                       ON CONFLICT(artist, title) DO UPDATE SET
                           video_id = COALESCE(video_id, excluded.video_id)""",
                    (artist, title, video_id, now, now),
                )
                count += 1

        self.record_action("backfill_from_overrides", detail=f"Imported {count} entries from overrides", source="web")
        log.info("Backfilled %d entries from overrides into history DB", count)
        return count

    def get_db_size_bytes(self) -> int:
        """Return the database file size in bytes."""
        try:
            return self._db_path.stat().st_size
        except OSError:
            return 0

    def prune_if_oversized(self, max_size_mb: float) -> int:
        """Delete oldest actions and syncs if DB exceeds *max_size_mb*.

        Prunes in batches of 100 oldest actions, then 50 oldest syncs,
        repeating until under the limit (or tables are empty).
        Returns total rows deleted.
        """
        if max_size_mb <= 0:
            return 0
        max_bytes = int(max_size_mb * 1024 * 1024)
        if self.get_db_size_bytes() <= max_bytes:
            return 0

        deleted = 0
        with self._cursor() as cur:
            while self.get_db_size_bytes() > max_bytes:
                cur.execute("DELETE FROM actions WHERE id IN (SELECT id FROM actions ORDER BY timestamp ASC LIMIT 100)")
                batch = cur.rowcount
                cur.execute("DELETE FROM syncs WHERE id IN (SELECT id FROM syncs ORDER BY started_at ASC LIMIT 50)")
                batch += cur.rowcount
                deleted += batch
                if batch == 0:
                    break
        if deleted:
            self.vacuum()
            log.info("Pruned %d rows to stay under %s MB limit", deleted, max_size_mb)
        return deleted

    def vacuum(self) -> None:
        """Reclaim free space in the database file."""
        conn = self._get_conn()
        conn.execute("VACUUM")

    def prune_by_age(self, retention_days: int) -> dict[str, int]:
        """Delete actions and syncs older than *retention_days* days.

        Tracks are kept (they are cumulative lookup state, not history).
        Runs VACUUM if anything was deleted. Returns counts of deleted rows.
        """
        if retention_days <= 0:
            return {"actions": 0, "syncs": 0}
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        with self._cursor() as cur:
            cur.execute("DELETE FROM actions WHERE timestamp < ?", (cutoff,))
            actions_deleted = cur.rowcount
            cur.execute("DELETE FROM syncs WHERE started_at < ?", (cutoff,))
            syncs_deleted = cur.rowcount
        total = actions_deleted + syncs_deleted
        if total:
            self.vacuum()
            log.info(
                "Pruned %d actions and %d syncs older than %d days",
                actions_deleted,
                syncs_deleted,
                retention_days,
            )
        return {"actions": actions_deleted, "syncs": syncs_deleted}

    def export_to_dict(self) -> dict[str, Any]:
        """Export all rows as a JSON-serialisable dict.

        Format: {"schema_version": N, "exported_at": iso, "tables": {name: [rows]}}.
        """
        tables = ("tracks", "syncs", "actions")
        out: dict[str, list[dict]] = {}
        with self._cursor() as cur:
            for table in tables:
                cur.execute(f"SELECT * FROM {table}")
                out[table] = [dict(row) for row in cur.fetchall()]
        return {
            "schema_version": _SCHEMA_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "tables": out,
        }

    def import_from_dict(self, data: dict[str, Any], *, mode: str = "merge") -> dict[str, int]:
        """Import rows from an export dict.

        mode='merge' upserts tracks (summing counts) and appends new syncs/actions.
        mode='replace' wipes existing data first, then inserts everything as-is.
        Returns counts of imported rows per table.
        """
        if mode not in {"merge", "replace"}:
            raise ValueError(f"Unsupported import mode: {mode}")
        version = data.get("schema_version", 0)
        if version > _SCHEMA_VERSION:
            raise ValueError(f"Unsupported export schema version {version}")
        tables = data.get("tables", {})
        if not isinstance(tables, dict):
            raise ValueError("Malformed export: missing 'tables'")

        counts = {"tracks": 0, "syncs": 0, "actions": 0}
        with self._cursor() as cur:
            if mode == "replace":
                cur.execute("DELETE FROM actions")
                cur.execute("DELETE FROM syncs")
                cur.execute("DELETE FROM tracks")

            for row in tables.get("tracks", []):
                cur.execute(
                    """INSERT INTO tracks (artist, title, video_id, yt_title, source,
                                           first_seen, last_seen, times_found, times_missed, best_score)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(artist, title) DO UPDATE SET
                           video_id     = COALESCE(video_id, excluded.video_id),
                           yt_title     = COALESCE(yt_title, excluded.yt_title),
                           source       = source,
                           first_seen   = MIN(first_seen, excluded.first_seen),
                           last_seen    = MAX(last_seen, excluded.last_seen),
                           times_found  = MAX(times_found, excluded.times_found),
                           times_missed = MAX(times_missed, excluded.times_missed),
                           best_score   = MAX(COALESCE(best_score, 0), COALESCE(excluded.best_score, 0))""",
                    (
                        row.get("artist"),
                        row.get("title"),
                        row.get("video_id"),
                        row.get("yt_title"),
                        row.get("source") or "search",
                        row.get("first_seen"),
                        row.get("last_seen"),
                        row.get("times_found") or 0,
                        row.get("times_missed") or 0,
                        row.get("best_score"),
                    ),
                )
                counts["tracks"] += 1

            for row in tables.get("syncs", []):
                cur.execute(
                    """INSERT INTO syncs (started_at, finished_at, duration_secs, sync_type, trigger,
                                          status, tracks_total, tracks_resolved, tracks_missed,
                                          api_searches, api_playlist_ops, cache_hits, cache_misses,
                                          override_hits, error_message)
                       SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                       WHERE NOT EXISTS (
                           SELECT 1 FROM syncs WHERE started_at = ? AND sync_type = ?
                       )""",
                    (
                        row.get("started_at"),
                        row.get("finished_at"),
                        row.get("duration_secs"),
                        row.get("sync_type") or "main",
                        row.get("trigger") or "manual",
                        row.get("status") or "success",
                        row.get("tracks_total") or 0,
                        row.get("tracks_resolved") or 0,
                        row.get("tracks_missed") or 0,
                        row.get("api_searches") or 0,
                        row.get("api_playlist_ops") or 0,
                        row.get("cache_hits") or 0,
                        row.get("cache_misses") or 0,
                        row.get("override_hits") or 0,
                        row.get("error_message"),
                        row.get("started_at"),
                        row.get("sync_type") or "main",
                    ),
                )
                counts["syncs"] += cur.rowcount

            for row in tables.get("actions", []):
                cur.execute(
                    """INSERT INTO actions (timestamp, action_type, artist, title, video_id, detail, source)
                       SELECT ?, ?, ?, ?, ?, ?, ?
                       WHERE NOT EXISTS (
                           SELECT 1 FROM actions
                           WHERE timestamp   = ?
                             AND action_type = ?
                             AND IFNULL(artist, '')   = IFNULL(?, '')
                             AND IFNULL(title, '')    = IFNULL(?, '')
                             AND IFNULL(video_id, '') = IFNULL(?, '')
                             AND IFNULL(detail, '')   = IFNULL(?, '')
                       )""",
                    (
                        row.get("timestamp"),
                        row.get("action_type"),
                        row.get("artist"),
                        row.get("title"),
                        row.get("video_id"),
                        row.get("detail"),
                        row.get("source") or "import",
                        row.get("timestamp"),
                        row.get("action_type"),
                        row.get("artist"),
                        row.get("title"),
                        row.get("video_id"),
                        row.get("detail"),
                    ),
                )
                counts["actions"] += cur.rowcount

        log.info(
            "Imported history (%s): tracks=%d syncs=%d actions=%d",
            mode,
            counts["tracks"],
            counts["syncs"],
            counts["actions"],
        )
        return counts

    def clear_all(self) -> None:
        """Delete all data from tracks, syncs, and actions."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM actions")
            cur.execute("DELETE FROM syncs")
            cur.execute("DELETE FROM tracks")
        self.vacuum()
        log.info("Cleared all history data")

    def get_sync_trend(self, days: int = 30) -> list[dict]:
        """Return daily sync stats for the last *days* days.

        Each entry: {date, total, success, error, avg_duration,
                     avg_resolved, avg_missed, avg_cache_rate}.
        """
        cutoff = (datetime.now(UTC) - __import__("datetime").timedelta(days=days)).isoformat()
        with self._cursor() as cur:
            cur.execute(
                """SELECT
                       DATE(started_at) AS date,
                       COUNT(*)         AS total,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                       SUM(CASE WHEN status = 'error'   THEN 1 ELSE 0 END) AS error,
                       ROUND(AVG(duration_secs), 1) AS avg_duration,
                       ROUND(AVG(tracks_resolved), 1) AS avg_resolved,
                       ROUND(AVG(tracks_missed), 1)   AS avg_missed,
                       ROUND(
                           AVG(CASE WHEN (cache_hits + cache_misses) > 0
                                    THEN cache_hits * 100.0 / (cache_hits + cache_misses)
                                    ELSE NULL END), 1
                       ) AS avg_cache_rate
                   FROM syncs
                   WHERE started_at >= ?
                   GROUP BY DATE(started_at)
                   ORDER BY date ASC""",
                (cutoff,),
            )
            return [dict(row) for row in cur.fetchall()]
