import threading

import pytest

from src.db import SQLiteStore


class MetaStore(SQLiteStore):
    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        with self._cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")


def test_meta_values_are_upserted(tmp_path):
    store = MetaStore(tmp_path / "nested" / "store.db")
    assert store.get_meta("k") is None
    store.set_meta("k", "1")
    store.set_meta("k", "2")
    assert store.get_meta("k") == "2"


def test_a_failing_block_is_rolled_back(tmp_path):
    store = MetaStore(tmp_path / "store.db")
    with pytest.raises(RuntimeError), store._cursor() as cur:
        SQLiteStore._write_meta(cur, "k", "lost")
        raise RuntimeError("boom")
    assert store.get_meta("k") is None


def test_each_thread_gets_its_own_connection_with_wal_and_rows(tmp_path):
    store = MetaStore(tmp_path / "store.db", foreign_keys=True)
    main = store._get_conn()
    other = []
    thread = threading.Thread(target=lambda: other.append(store._get_conn()))
    thread.start()
    thread.join()
    assert other[0] is not main
    assert main.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert main.execute("PRAGMA foreign_keys").fetchone()["foreign_keys"] == 1
    assert MetaStore(tmp_path / "plain.db")._get_conn().execute("PRAGMA foreign_keys").fetchone()[0] == 0


def test_close_drops_the_thread_connection(tmp_path):
    store = MetaStore(tmp_path / "store.db")
    first = store._get_conn()
    store.close()
    store.close()
    assert store._get_conn() is not first
