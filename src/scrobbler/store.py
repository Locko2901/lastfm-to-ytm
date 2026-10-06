"""SQLite state of the history scrobbler: snapshot, polls, and every detected play.

The ``plays`` table is both the decision log shown on the dashboard and the
ledger of the scrobbler's own scrobbles: a play moves from ``pending`` to a
final status once, and only ``pending`` plays are ever sent.
"""

from __future__ import annotations

import fcntl
import json
import logging
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..db import SQLiteStore
from .detect import Pending, SnapshotEntry

log = logging.getLogger(__name__)

_SCHEMA_VERSION = 2

_COLUMNS_ADDED_IN_V2 = {
    "position": "INTEGER NOT NULL DEFAULT 0",
    "window_count": "INTEGER NOT NULL DEFAULT 1",
    "shared": "TEXT NOT NULL DEFAULT '[]'",
    "next_window_start": "REAL",
    "next_window_end": "REAL",
    "next_window_count": "INTEGER NOT NULL DEFAULT 1",
    "listen_lo": "REAL",
    "listen_hi": "REAL",
    "listen_threshold": "REAL",
    "certainty": "TEXT NOT NULL DEFAULT ''",
    "dry_run_choice": "TEXT NOT NULL DEFAULT ''",
    "dry_run_choice_at": "REAL",
    "basis": "TEXT NOT NULL DEFAULT ''",
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS polls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      REAL    NOT NULL,
    finished_at     REAL,
    status          TEXT    NOT NULL DEFAULT 'running',
    dry_run         INTEGER NOT NULL DEFAULT 1,
    history_rows    INTEGER NOT NULL DEFAULT 0,
    history_repeats INTEGER NOT NULL DEFAULT 0,
    new_plays       INTEGER NOT NULL DEFAULT 0,
    scrobbled       INTEGER NOT NULL DEFAULT 0,
    would_scrobble  INTEGER NOT NULL DEFAULT 0,
    skipped         INTEGER NOT NULL DEFAULT 0,
    pending         INTEGER NOT NULL DEFAULT 0,
    failed          INTEGER NOT NULL DEFAULT 0,
    error           TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plays (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    poll_id       INTEGER,
    video_id      TEXT    NOT NULL,
    artist        TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    artists       TEXT    NOT NULL DEFAULT '[]',
    album         TEXT    NOT NULL DEFAULT '',
    duration      INTEGER,
    played        TEXT    NOT NULL DEFAULT '',
    replay        INTEGER NOT NULL DEFAULT 0,
    detected_at   REAL    NOT NULL,
    window_start  REAL    NOT NULL,
    timestamp     INTEGER NOT NULL,
    earliest      INTEGER NOT NULL,
    latest        INTEGER NOT NULL,
    status        TEXT    NOT NULL,
    reason        TEXT    NOT NULL DEFAULT '',
    detail        TEXT    NOT NULL DEFAULT '{}',
    dry_run       INTEGER NOT NULL DEFAULT 1,
    attempts      INTEGER NOT NULL DEFAULT 0,
    decided_at    REAL,
    lastfm_artist TEXT    NOT NULL DEFAULT '',
    lastfm_title  TEXT    NOT NULL DEFAULT '',
    position          INTEGER NOT NULL DEFAULT 0,
    window_count      INTEGER NOT NULL DEFAULT 1,
    shared            TEXT    NOT NULL DEFAULT '[]',
    next_window_start REAL,
    next_window_end   REAL,
    next_window_count INTEGER NOT NULL DEFAULT 1,
    listen_lo         REAL,
    listen_hi         REAL,
    listen_threshold  REAL,
    certainty         TEXT    NOT NULL DEFAULT '',
    dry_run_choice    TEXT    NOT NULL DEFAULT '',
    dry_run_choice_at REAL,
    basis             TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS now_playing_seen (
    seen_at REAL PRIMARY KEY,
    playing INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_plays_status   ON plays(status);
CREATE INDEX IF NOT EXISTS idx_plays_detected ON plays(detected_at);
CREATE INDEX IF NOT EXISTS idx_plays_ts       ON plays(timestamp);
"""

PENDING = "pending"
SENDING = "sending"
SCROBBLED = "scrobbled"
WOULD_SCROBBLE = "would_scrobble"
SKIPPED = "skipped"
FAILED = "failed"
OPEN_STATUSES = (PENDING, SENDING)

CHOICE_SEND = "send"
CHOICE_KEEP = "keep"
CHOICE_TOO_OLD = "too_old"
ALL_STATUSES = (PENDING, SENDING, SCROBBLED, WOULD_SCROBBLE, SKIPPED, FAILED)

_META_SNAPSHOT = "snapshot"
_META_LAST_POLL = "last_poll_at"
_META_LAST_CHANGE = "last_change_at"
_META_PENDING = "pending"
_META_HISTORY_ERRORS = "history_errors"

PLAYS_RETENTION_SECONDS = 90 * 24 * 3600
POLLS_RETENTION_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True, slots=True)
class NewPlay:
    """A detected play about to be recorded."""

    video_id: str
    artist: str
    title: str
    artists: tuple[str, ...]
    album: str
    duration: int | None
    played: str
    replay: bool
    timestamp: int
    earliest: int
    latest: int
    status: str
    reason: str = ""
    position: int = 0
    count: int = 1
    shared: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class PlayRow:
    """A recorded play."""

    id: int
    video_id: str
    artist: str
    title: str
    artists: tuple[str, ...]
    album: str
    duration: int | None
    detected_at: float
    window_start: float
    timestamp: int
    earliest: int
    latest: int
    status: str
    reason: str
    attempts: int
    lastfm_artist: str
    lastfm_title: str
    position: int = 0
    window_count: int = 1
    shared: tuple[int, ...] = ()
    next_window_start: float | None = None
    next_window_end: float | None = None
    next_window_count: int = 1

    @property
    def gap(self) -> float:
        """Time between the two polls that found this play."""
        return max(0.0, self.detected_at - self.window_start)


def _row_to_play(row: sqlite3.Row) -> PlayRow:
    try:
        artists = tuple(str(a) for a in json.loads(row["artists"] or "[]"))
    except (TypeError, ValueError):
        artists = ()
    return PlayRow(
        id=row["id"],
        video_id=row["video_id"],
        artist=row["artist"],
        title=row["title"],
        artists=artists or (row["artist"],),
        album=row["album"],
        duration=row["duration"],
        detected_at=row["detected_at"],
        window_start=row["window_start"],
        timestamp=row["timestamp"],
        earliest=row["earliest"],
        latest=row["latest"],
        status=row["status"],
        reason=row["reason"],
        attempts=row["attempts"],
        lastfm_artist=row["lastfm_artist"],
        lastfm_title=row["lastfm_title"],
        position=row["position"],
        window_count=row["window_count"],
        shared=_int_tuple(row["shared"]),
        next_window_start=row["next_window_start"],
        next_window_end=row["next_window_end"],
        next_window_count=row["next_window_count"],
    )


def _int_tuple(raw: str | None) -> tuple[int, ...]:
    try:
        return tuple(int(v) for v in json.loads(raw or "[]"))
    except (TypeError, ValueError):
        return ()


def _play_dict(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in ("detail", "artists"):
        try:
            out[key] = json.loads(out.get(key) or ("{}" if key == "detail" else "[]"))
        except (TypeError, ValueError):
            out[key] = {} if key == "detail" else []
    out["dry_run"] = bool(out.get("dry_run"))
    out["replay"] = bool(out.get("replay"))
    return out


class ScrobblerStore(SQLiteStore):
    """Thread-safe SQLite store for the history scrobbler."""

    def __init__(self, db_path: str | Path):
        super().__init__(db_path)
        self._init_schema()

    @property
    def path(self) -> Path:
        """Location of the database file."""
        return self._db_path

    def _init_schema(self) -> None:
        conn = self._get_conn()
        cur = conn.cursor()
        cur.executescript(_SCHEMA_SQL)
        cur.execute("SELECT version FROM schema_version LIMIT 1")
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO schema_version (version) VALUES (?)", (_SCHEMA_VERSION,))
        elif row[0] < 2:
            self._migrate_v1_to_v2(conn)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_plays_open ON plays(next_window_end)")
        conn.commit()
        log.debug("Scrobbler DB initialized at %s (schema v%d)", self._db_path, _SCHEMA_VERSION)

    def _migrate_v1_to_v2(self, conn: sqlite3.Connection) -> None:
        """Migrate schema v1 to v2: the poll evidence, listening bounds, certainty, dry-run choice and basis of each play."""
        cur = conn.cursor()
        for name, definition in _COLUMNS_ADDED_IN_V2.items():
            cur.execute(f"ALTER TABLE plays ADD COLUMN {name} {definition}")
        cur.execute("UPDATE schema_version SET version = 2")
        log.info("Migrated scrobbler DB schema v1 to v2 (play evidence and decisions)")

    def load_snapshot(self) -> tuple[list[SnapshotEntry] | None, float | None]:
        """Return the last saved snapshot and when it was taken, or ``(None, None)``."""
        raw = self.get_meta(_META_SNAPSHOT)
        last = self.get_meta(_META_LAST_POLL)
        if raw is None:
            return None, None
        try:
            entries = [SnapshotEntry(str(e[0]), str(e[1])) for e in json.loads(raw)]
        except (TypeError, ValueError, IndexError):
            log.warning("Scrobbler snapshot is unreadable; starting from a new baseline")
            return None, None
        try:
            taken = float(last) if last is not None else None
        except ValueError:
            taken = None
        return entries, taken

    def _write_snapshot(self, cur: sqlite3.Cursor, snapshot: Sequence[SnapshotEntry], taken_at: float) -> None:
        payload = json.dumps([[e.video_id, e.played] for e in snapshot])
        for key, value in ((_META_SNAPSHOT, payload), (_META_LAST_POLL, repr(taken_at))):
            self._write_meta(cur, key, value)

    def _write_pending(self, cur: sqlite3.Cursor, pending: Pending | None) -> None:
        payload = (
            "null"
            if pending is None
            else json.dumps(
                {
                    "snapshot": [[e.video_id, e.played] for e in pending.snapshot],
                    "new_ids": list(pending.new_ids),
                    "seen_at": pending.seen_at,
                    "kind": pending.kind,
                }
            )
        )
        self._write_meta(cur, _META_PENDING, payload)

    def load_pending(self) -> Pending | None:
        """The change seen once and waiting for the next poll to confirm it, if any."""
        raw = self.get_meta(_META_PENDING)
        try:
            data = json.loads(raw) if raw else None
            if not isinstance(data, dict):
                return None
            return Pending(
                snapshot=tuple(SnapshotEntry(str(e[0]), str(e[1])) for e in data["snapshot"]),
                new_ids=tuple(str(v) for v in data["new_ids"]),
                seen_at=float(data["seen_at"]),
                kind=str(data.get("kind") or "plays"),
            )
        except (TypeError, ValueError, KeyError, IndexError):
            return None

    def save_pending(self, pending: Pending | None) -> None:
        """Replace the pending change without touching the confirmed snapshot."""
        with self._cursor() as cur:
            self._write_pending(cur, pending)

    def save_snapshot(self, snapshot: Sequence[SnapshotEntry], observed_at: float, pending: Pending | None = None) -> None:
        """Replace the confirmed snapshot without recording plays (a confirmed first list)."""
        with self._cursor() as cur:
            self._write_snapshot(cur, snapshot, observed_at)
            self._write_pending(cur, pending)

    def save_observed(self, observed_at: float | None, pending: Pending | None, snapshot: Sequence[SnapshotEntry] | None = None) -> None:
        """Record a poll that confirmed no play: move the observed time forward (if given) and replace the pending change.

        ``snapshot`` is the confirmed snapshot with refreshed shelves, when given.
        """
        with self._cursor() as cur:
            if snapshot is not None:
                self._write_meta(cur, _META_SNAPSHOT, json.dumps([[e.video_id, e.played] for e in snapshot]))
            if observed_at is not None:
                self._write_meta(cur, _META_LAST_POLL, repr(observed_at))
            self._write_pending(cur, pending)

    def record_detection(
        self,
        snapshot: Sequence[SnapshotEntry],
        taken_at: float,
        window_start: float,
        plays: Sequence[NewPlay],
        *,
        poll_id: int | None,
        dry_run: bool,
        pending: Pending | None = None,
        observed_at: float | None = None,
    ) -> list[int]:
        """Store new plays (oldest first) and the new snapshot in one transaction.

        Either both are saved or neither is, so a crash can neither lose the
        plays (the next poll finds them again) nor record them twice. Each play
        becomes the successor of the one before it: the last play recorded
        earlier, then each other in order.
        """
        ids: list[int] = []
        with self._cursor() as cur:
            if plays:
                self._close_latest(cur, window_start, taken_at, len(plays))
            for play in plays:
                final = play.status not in OPEN_STATUSES
                cur.execute(
                    """INSERT INTO plays (poll_id, video_id, artist, title, artists, album, duration, played, replay,
                           detected_at, window_start, timestamp, earliest, latest, status, reason, dry_run, decided_at,
                           position, window_count, shared)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        poll_id,
                        play.video_id,
                        play.artist,
                        play.title,
                        json.dumps(list(play.artists)),
                        play.album,
                        play.duration,
                        play.played,
                        int(play.replay),
                        taken_at,
                        window_start,
                        play.timestamp,
                        play.earliest,
                        play.latest,
                        play.status,
                        play.reason,
                        int(dry_run),
                        taken_at if final else None,
                        play.position,
                        play.count,
                        json.dumps(list(play.shared)),
                    ),
                )
                ids.append(int(cur.lastrowid or 0))
            for earlier in ids[:-1]:
                cur.execute(
                    "UPDATE plays SET next_window_start = ?, next_window_end = ?, next_window_count = ? WHERE id = ?",
                    (window_start, taken_at, len(plays), earlier),
                )
            self._write_snapshot(cur, snapshot, taken_at if observed_at is None else observed_at)
            self._write_pending(cur, pending)
        return ids

    def _close_latest(self, cur: sqlite3.Cursor, window_start: float, window_end: float, count: int) -> None:
        """Mark the latest play as followed by a play that started in ``(window_start, window_end]``."""
        cur.execute("SELECT id FROM plays WHERE next_window_end IS NULL ORDER BY detected_at DESC, position DESC, id DESC LIMIT 1")
        row = cur.fetchone()
        if row is not None:
            cur.execute(
                "UPDATE plays SET next_window_start = ?, next_window_end = ?, next_window_count = ? WHERE id = ?",
                (window_start, window_end, count, row["id"]),
            )

    def save_reset(
        self,
        snapshot: Sequence[SnapshotEntry],
        window_start: float,
        taken_at: float,
        pending: Pending | None = None,
        observed_at: float | None = None,
    ) -> None:
        """Replace the snapshot after the history changed beyond recognition.

        The latest play was certainly followed by others within the window, so
        it is closed there.
        """
        with self._cursor() as cur:
            self._close_latest(cur, window_start, taken_at, 1)
            self._write_snapshot(cur, snapshot, taken_at if observed_at is None else observed_at)
            self._write_pending(cur, pending)

    def open_plays(self) -> list[PlayRow]:
        """Plays not decided yet (``pending``) or sent without a recorded answer (``sending``)."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM plays WHERE status IN (?, ?) ORDER BY timestamp, id", OPEN_STATUSES)
            return [_row_to_play(r) for r in cur.fetchall()]

    @contextmanager
    def exclusive(self) -> Iterator[bool]:
        """Try to hold the poll lock (a lock file next to the database), across processes.

        Yields False when another poll holds it.
        """
        lock_path = self._db_path.with_name(self._db_path.name + ".lock")
        with lock_path.open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def duplicates_decided_since(self, since: float) -> list[tuple[PlayRow, dict[str, Any]]]:
        """Plays skipped as duplicates since ``since``, with the scrobble each was matched to."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM plays WHERE reason = 'duplicate' AND decided_at >= ? ORDER BY timestamp", (since,))
            rows = cur.fetchall()
        result: list[tuple[PlayRow, dict[str, Any]]] = []
        for row in rows:
            try:
                detail = json.loads(row["detail"] or "{}")
            except (TypeError, ValueError):
                detail = {}
            result.append((_row_to_play(row), detail if isinstance(detail, dict) else {}))
        return result

    def own_scrobbles_since(self, since_ts: int) -> list[PlayRow]:
        """The ledger: plays this scrobbler sent and Last.fm accepted, from ``since_ts`` on."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM plays WHERE status = ? AND timestamp >= ? ORDER BY timestamp", (SCROBBLED, since_ts))
            return [_row_to_play(r) for r in cur.fetchall()]

    def decide(
        self,
        play_id: int,
        status: str,
        *,
        reason: str = "",
        detail: dict[str, Any] | None = None,
        decided_at: float,
        dry_run: bool,
        lastfm_artist: str = "",
        lastfm_title: str = "",
        listening: tuple[float, float, float, str, str] | None = None,
    ) -> None:
        """Record a play's decision (or put it back to ``pending``).

        ``listening`` is ``(lo, hi, threshold, certainty, basis)`` from the played
        rule; when omitted, the stored values are kept.
        """
        final = status not in OPEN_STATUSES
        with self._cursor() as cur:
            cur.execute(
                """UPDATE plays SET status = ?, reason = ?, detail = ?, decided_at = ?, dry_run = ?,
                       lastfm_artist = ?, lastfm_title = ?
                   WHERE id = ?""",
                (status, reason, json.dumps(detail or {}), decided_at if final else None, int(dry_run), lastfm_artist, lastfm_title, play_id),
            )
            if listening is not None:
                lo, hi, threshold, certainty, basis = listening
                cur.execute(
                    "UPDATE plays SET listen_lo = ?, listen_hi = ?, listen_threshold = ?, certainty = ?, basis = ? WHERE id = ?",
                    (lo, hi, threshold, certainty, basis, play_id),
                )

    def mark_sending(self, play_ids: Sequence[int]) -> None:
        """Mark plays as handed to Last.fm, before the request goes out."""
        if not play_ids:
            return
        with self._cursor() as cur:
            cur.executemany(
                "UPDATE plays SET status = ?, attempts = attempts + 1 WHERE id = ? AND status = ?",
                [(SENDING, i, PENDING) for i in play_ids],
            )

    def dry_run_offer(self, oldest_timestamp: int) -> tuple[int, int]:
        """Count the dry run's "would scrobble" plays not offered yet: ``(still accepted by age, too old)``."""
        with self._cursor() as cur:
            cur.execute(
                """SELECT SUM(timestamp >= ?) AS fresh, SUM(timestamp < ?) AS old
                   FROM plays WHERE status = ? AND dry_run_choice = ''""",
                (oldest_timestamp, oldest_timestamp, WOULD_SCROBBLE),
            )
            row = cur.fetchone()
            return int(row["fresh"] or 0), int(row["old"] or 0)

    def record_dry_run_choice(self, send: bool, oldest_timestamp: int, at: float) -> tuple[int, int]:
        """Record the answer to the offer for every "would scrobble" play not offered yet.

        Sending puts the plays Last.fm still accepts back to pending, so the
        next poll checks and sends them like any other play; older ones are
        marked too old. Keeping marks them all. Returns ``(queued or kept, too old)``.
        """
        with self._cursor() as cur:
            if not send:
                cur.execute(
                    "UPDATE plays SET dry_run_choice = ?, dry_run_choice_at = ? WHERE status = ? AND dry_run_choice = ''",
                    (CHOICE_KEEP, at, WOULD_SCROBBLE),
                )
                return cur.rowcount, 0
            cur.execute(
                """UPDATE plays SET dry_run_choice = ?, dry_run_choice_at = ?
                   WHERE status = ? AND dry_run_choice = '' AND timestamp < ?""",
                (CHOICE_TOO_OLD, at, WOULD_SCROBBLE, oldest_timestamp),
            )
            too_old = cur.rowcount
            cur.execute(
                """UPDATE plays SET dry_run_choice = ?, dry_run_choice_at = ?, status = ?, decided_at = NULL, dry_run = 0
                   WHERE status = ? AND dry_run_choice = '' AND timestamp >= ?""",
                (CHOICE_SEND, at, PENDING, WOULD_SCROBBLE, oldest_timestamp),
            )
            return cur.rowcount, too_old

    def pacing_state(self) -> tuple[float | None, float | None, int]:
        """``(last poll attempt, last change seen, history read failures in a row)`` for adaptive polling."""
        with self._cursor() as cur:
            cur.execute("SELECT MAX(started_at) AS last FROM polls")
            row = cur.fetchone()
        last_attempt = row["last"] if row and row["last"] is not None else None
        raw_change = self.get_meta(_META_LAST_CHANGE)
        raw_errors = self.get_meta(_META_HISTORY_ERRORS)
        try:
            last_change = float(raw_change) if raw_change else None
        except ValueError:
            last_change = None
        try:
            errors = int(raw_errors) if raw_errors else 0
        except ValueError:
            errors = 0
        return last_attempt, last_change, errors

    def record_pacing(self, *, changed_at: float | None, history_failed: bool) -> None:
        """Remember a change of the history and count history read failures in a row."""
        if changed_at is not None:
            self.set_meta(_META_LAST_CHANGE, repr(changed_at))
        _last, _change, errors = self.pacing_state()
        self.set_meta(_META_HISTORY_ERRORS, str(errors + 1 if history_failed else 0))

    def start_poll(self, started_at: float, dry_run: bool) -> int:
        """Open a poll record and return its id."""
        with self._cursor() as cur:
            cur.execute("INSERT INTO polls (started_at, dry_run) VALUES (?, ?)", (started_at, int(dry_run)))
            return int(cur.lastrowid or 0)

    def finish_poll(self, poll_id: int, finished_at: float, status: str, **counts: Any) -> None:
        """Close a poll record with its outcome."""
        allowed = ("history_rows", "history_repeats", "new_plays", "scrobbled", "would_scrobble", "skipped", "pending", "failed", "error")
        fields = {k: v for k, v in counts.items() if k in allowed}
        assignments = ", ".join(f"{k} = ?" for k in fields)
        sql = "UPDATE polls SET finished_at = ?, status = ?" + (f", {assignments}" if assignments else "") + " WHERE id = ?"
        with self._cursor() as cur:
            cur.execute(sql, (finished_at, status, *fields.values(), poll_id))

    def last_poll(self) -> dict[str, Any] | None:
        """The most recent finished poll."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM polls WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            return dict(row) if row else None

    def recent_polls(self, limit: int = 20) -> list[dict[str, Any]]:
        """The latest finished polls, newest first."""
        with self._cursor() as cur:
            cur.execute("SELECT * FROM polls WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT ?", (max(1, limit),))
            return [dict(r) for r in cur.fetchall()]

    def list_plays(self, *, statuses: Sequence[str] | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """Decision log, newest first, optionally filtered by status."""
        where = ""
        params: list[Any] = []
        if statuses:
            where = f"WHERE status IN ({', '.join('?' for _ in statuses)})"
            params.extend(statuses)
        with self._cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM plays {where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(f"SELECT * FROM plays {where} ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?", [*params, max(1, limit), max(0, offset)])
            return [_play_dict(r) for r in cur.fetchall()], total

    def status_counts(self, since: float) -> dict[str, int]:
        """Number of plays per status detected since ``since`` (open plays are always counted)."""
        counts = dict.fromkeys(ALL_STATUSES, 0)
        with self._cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) AS n FROM plays WHERE detected_at >= ? OR status IN (?, ?) GROUP BY status",
                (since, *OPEN_STATUSES),
            )
            for row in cur.fetchall():
                counts[row["status"]] = int(row["n"])
        return counts

    def record_now_playing(self, seen_at: float, playing: bool) -> None:
        """Remember whether a real-time scrobbler showed the song on top of the history as now playing at ``seen_at``."""
        with self._cursor() as cur:
            cur.execute("INSERT OR REPLACE INTO now_playing_seen (seen_at, playing) VALUES (?, ?)", (seen_at, int(playing)))

    def saw_now_playing_since(self, since: float) -> bool:
        """True when a real-time scrobbler showed the song on top of the history as now playing at a poll since ``since``."""
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM now_playing_seen WHERE playing = 1 AND seen_at >= ? LIMIT 1", (since,))
            return cur.fetchone() is not None

    def now_playing_between(self, start: float, end: float) -> list[tuple[float, bool]]:
        """The now playing sightings in ``[start, end]``, oldest first: ``(poll time, playing the song on top)``."""
        with self._cursor() as cur:
            cur.execute("SELECT seen_at, playing FROM now_playing_seen WHERE seen_at BETWEEN ? AND ? ORDER BY seen_at", (start, end))
            return [(float(row["seen_at"]), bool(row["playing"])) for row in cur.fetchall()]

    def prune(self, now: float) -> None:
        """Drop decided plays older than 90 days, and polls and now playing sightings older than 30 days."""
        with self._cursor() as cur:
            cur.execute(
                "DELETE FROM plays WHERE detected_at < ? AND status NOT IN (?, ?)",
                (now - PLAYS_RETENTION_SECONDS, *OPEN_STATUSES),
            )
            cur.execute("DELETE FROM polls WHERE started_at < ?", (now - POLLS_RETENTION_SECONDS,))
            cur.execute("DELETE FROM now_playing_seen WHERE seen_at < ?", (now - POLLS_RETENTION_SECONDS,))

    def clear(self) -> None:
        """Forget everything: snapshot, polls, plays and now playing sightings (the next poll starts a new baseline)."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM plays")
            cur.execute("DELETE FROM polls")
            cur.execute("DELETE FROM now_playing_seen")
            cur.execute("DELETE FROM meta")
