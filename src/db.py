"""Shared SQLite plumbing for the project's stores: one connection per thread, WAL, ``Row`` access, commit or rollback per block."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

CONNECT_TIMEOUT_SECONDS = 10


class SQLiteStore:
    """A SQLite database file opened once per thread, with ``sqlite3.Row`` rows and WAL journaling.

    Subclasses create their schema. ``get_meta`` and ``set_meta`` need a
    ``meta (key, value)`` table in it.
    """

    def __init__(self, db_path: str | Path, *, foreign_keys: bool = False):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._foreign_keys = foreign_keys
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), timeout=CONNECT_TIMEOUT_SECONDS)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            if self._foreign_keys:
                conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        """A cursor whose block commits when it ends and rolls back on an exception."""
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

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
            self._write_meta(cur, key, value)

    @staticmethod
    def _write_meta(cur: sqlite3.Cursor, key: str, value: str) -> None:
        """Upsert a meta key/value within the transaction of ``cur``."""
        cur.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
