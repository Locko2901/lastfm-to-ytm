"""Lightweight SQLite store for the user's full Last.fm scrobble history.

This is a standalone database (separate from the analytics ``history.db``) that
aggregates every unique ``(artist, track)`` the user has ever scrobbled, tracking
a lifetime play count and the first/last time it was played. It powers the
"use local Last.fm database" mode, where playlist recency/ranking is computed
from lifetime plays + recency instead of a single recent-tracks fetch.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .scrobble import Scrobble

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS scrobbles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    artist           TEXT    NOT NULL COLLATE NOCASE,
    track            TEXT    NOT NULL COLLATE NOCASE,
    album            TEXT,
    plays            INTEGER NOT NULL DEFAULT 0,
    first_played_uts INTEGER,
    last_played_uts  INTEGER,
    UNIQUE(artist, track)
);

CREATE INDEX IF NOT EXISTS idx_scrobbles_plays       ON scrobbles(plays);
CREATE INDEX IF NOT EXISTS idx_scrobbles_last_played ON scrobbles(last_played_uts);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_META_LAST_UTS = "last_scrobble_uts"
_META_LAST_FULL_SYNC = "last_full_sync_at"
_META_LAST_SYNC = "last_sync_at"


class LocalScrobbleDB:
    """Thread-safe SQLite store of aggregated Last.fm scrobble history."""

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
            self._local.conn = conn
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
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
        log.debug("Local Last.fm DB initialised at %s (schema v%d)", self._db_path, _SCHEMA_VERSION)

    def close(self) -> None:
        """Close the thread-local database connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    def get_meta(self, key: str) -> str | None:
        """Return a meta value, or None if unset."""
        with self._cursor() as cur:
            cur.execute("SELECT value FROM meta WHERE key = ?", (key,))
            row = cur.fetchone()
            return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """Upsert a meta key/value."""
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_last_scrobble_uts(self) -> int | None:
        """Return the highest scrobble timestamp ingested so far, or None."""
        val = self.get_meta(_META_LAST_UTS)
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    def is_empty(self) -> bool:
        """Return True if no scrobbles have been ingested yet."""
        return self.get_last_scrobble_uts() is None

    def ingest_scrobbles(self, scrobbles: Sequence[Scrobble]) -> int:
        """Upsert a batch of scrobbles, incrementing play counts.

        Returns the number of scrobbles processed. Updates the stored
        ``last_scrobble_uts`` watermark to the highest timestamp seen.
        """
        if not scrobbles:
            return 0

        max_uts = 0
        with self._cursor() as cur:
            for s in scrobbles:
                cur.execute(
                    """INSERT INTO scrobbles (artist, track, album, plays, first_played_uts, last_played_uts)
                       VALUES (?, ?, ?, 1, ?, ?)
                       ON CONFLICT(artist, track) DO UPDATE SET
                           plays            = plays + 1,
                           album            = COALESCE(NULLIF(excluded.album, ''), album),
                           first_played_uts = MIN(first_played_uts, excluded.first_played_uts),
                           last_played_uts  = MAX(last_played_uts, excluded.last_played_uts)""",
                    (s.artist, s.track, s.album, s.ts, s.ts),
                )
                max_uts = max(max_uts, s.ts)

            if max_uts > 0:
                prev = self.get_last_scrobble_uts() or 0
                if max_uts > prev:
                    cur.execute(
                        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (_META_LAST_UTS, str(max_uts)),
                    )

        return len(scrobbles)

    def mark_synced(self, *, full: bool) -> None:
        """Record sync completion timestamps."""
        now = datetime.now(UTC).isoformat()
        self.set_meta(_META_LAST_SYNC, now)
        if full:
            self.set_meta(_META_LAST_FULL_SYNC, now)

    def get_scoring_rows(self, min_plays: int = 1) -> list[tuple[str, str, str, int, int]]:
        """Return ``(artist, track, album, plays, last_played_uts)`` rows for scoring.

        Filters out tracks below ``min_plays``. Rows with a NULL timestamp
        fall back to 0 (treated as very old by the recency decay).
        """
        with self._cursor() as cur:
            cur.execute(
                """SELECT artist, track, COALESCE(album, '') AS album, plays,
                          COALESCE(last_played_uts, 0) AS last_played_uts
                   FROM scrobbles
                   WHERE plays >= ?
                   ORDER BY plays DESC""",
                (max(min_plays, 1),),
            )
            return [(r["artist"], r["track"], r["album"], int(r["plays"]), int(r["last_played_uts"])) for r in cur.fetchall()]

    def get_top_tracks(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return tracks ordered by lifetime play count descending."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT artist, track, album, plays, first_played_uts, last_played_uts
                   FROM scrobbles ORDER BY plays DESC, last_played_uts DESC LIMIT ?""",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_track_count(self) -> int:
        """Return the number of unique tracks stored."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM scrobbles")
            return int(cur.fetchone()[0])

    def get_total_plays(self) -> int:
        """Return the sum of all play counts."""
        with self._cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(plays), 0) FROM scrobbles")
            return int(cur.fetchone()[0])

    def get_db_size_bytes(self) -> int:
        """Return the database file size in bytes."""
        try:
            return self._db_path.stat().st_size
        except OSError:
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Return overview statistics for the local scrobble history."""
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*), COALESCE(SUM(plays), 0), MIN(first_played_uts), MAX(last_played_uts) FROM scrobbles")
            total_tracks, total_plays, first_uts, last_uts = cur.fetchone()
        return {
            "total_tracks": int(total_tracks or 0),
            "total_plays": int(total_plays or 0),
            "first_played_uts": int(first_uts) if first_uts else None,
            "last_played_uts": int(last_uts) if last_uts else None,
            "last_sync_at": self.get_meta(_META_LAST_SYNC),
            "last_full_sync_at": self.get_meta(_META_LAST_FULL_SYNC),
            "db_size_bytes": self.get_db_size_bytes(),
        }

    def clear(self) -> None:
        """Delete all scrobbles and reset sync watermarks.

        The next sync will perform a fresh full history crawl.
        """
        with self._cursor() as cur:
            cur.execute("DELETE FROM scrobbles")
            cur.execute("DELETE FROM meta")
        log.info("Local Last.fm DB cleared at %s", self._db_path)

    def vacuum(self) -> None:
        """Reclaim unused space by running VACUUM."""
        conn = self._get_conn()
        conn.execute("VACUUM")
        conn.commit()

    def export_to_dict(self) -> dict[str, Any]:
        """Return a serialisable dump of the entire scrobble history."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT artist, track, album, plays, first_played_uts, last_played_uts
                   FROM scrobbles ORDER BY plays DESC, last_played_uts DESC"""
            )
            scrobbles = [dict(row) for row in cur.fetchall()]
            cur.execute("SELECT key, value FROM meta")
            meta = {row["key"]: row["value"] for row in cur.fetchall()}
        return {
            "version": _SCHEMA_VERSION,
            "exported_at": datetime.now(UTC).isoformat(),
            "meta": meta,
            "scrobbles": scrobbles,
        }

    def import_from_dict(self, payload: dict[str, Any], *, mode: str = "merge") -> dict[str, int]:
        """Import a previously exported dump.

        ``mode="replace"`` wipes the database first; ``mode="merge"`` upserts
        idempotently - play counts take the MAX of existing/incoming (so
        re-importing the same dump is a no-op) and the first/last-played range
        widens. Returns the number of imported and skipped scrobble rows.
        """
        if mode not in {"merge", "replace"}:
            raise ValueError(f"invalid import mode: {mode!r}")

        scrobbles = payload.get("scrobbles")
        if not isinstance(scrobbles, list):
            raise ValueError("payload missing 'scrobbles' list")

        if mode == "replace":
            self.clear()

        imported = 0
        skipped = 0
        with self._cursor() as cur:
            for row in scrobbles:
                if not isinstance(row, dict):
                    skipped += 1
                    continue
                artist = row.get("artist")
                track = row.get("track")
                if not artist or not track:
                    skipped += 1
                    continue
                plays = int(row.get("plays") or 0)
                cur.execute(
                    """INSERT INTO scrobbles (artist, track, album, plays, first_played_uts, last_played_uts)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(artist, track) DO UPDATE SET
                           plays            = MAX(plays, excluded.plays),
                           album            = COALESCE(NULLIF(excluded.album, ''), album),
                           first_played_uts = MIN(COALESCE(first_played_uts, excluded.first_played_uts), excluded.first_played_uts),
                           last_played_uts  = MAX(COALESCE(last_played_uts, excluded.last_played_uts), excluded.last_played_uts)""",
                    (
                        artist,
                        track,
                        row.get("album") or "",
                        plays,
                        row.get("first_played_uts"),
                        row.get("last_played_uts"),
                    ),
                )
                imported += 1

            cur.execute("SELECT COALESCE(MAX(last_played_uts), 0) FROM scrobbles")
            max_uts = int(cur.fetchone()[0] or 0)
            if max_uts > 0:
                cur.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (_META_LAST_UTS, str(max_uts)),
                )

        return {"imported": imported, "skipped": skipped}
