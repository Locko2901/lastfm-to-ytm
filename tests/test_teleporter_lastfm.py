"""Teleporter round-trip coverage for the local Last.fm scrobble database.

Keeps the test hermetic by emptying the config/cache file lists (so no real
``.env``/cache files are touched) and stubbing ``Settings.from_env`` with a
namespace that points the local DB at ``tmp_path``.
"""

from __future__ import annotations

import time
import types

import pytest

pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from src.lastfm import LocalScrobbleDB, Scrobble
from web.services import teleporter

_PASSWORD = "correct horse battery"


def _fake_settings(tmp_path, db_file):
    return types.SimpleNamespace(
        history_db_enabled=False,
        history_db_file=str(tmp_path / "history.db"),
        use_local_lastfm_db=True,
        lastfm_local_db_file=str(db_file),
    )


def test_teleporter_roundtrips_lastfm_db(tmp_path, monkeypatch):
    monkeypatch.setattr(teleporter, "_CONFIG_FILES", [])
    monkeypatch.setattr(teleporter, "_CACHE_FILES", {})

    src_db = tmp_path / "lastfm_history.db"
    src = LocalScrobbleDB(src_db)
    now = int(time.time())
    src.ingest_scrobbles([Scrobble("A", "Hit", "", now), Scrobble("A", "Hit", "", now), Scrobble("B", "Deep", "", now)])
    src.close()

    fake = _fake_settings(tmp_path, src_db)
    monkeypatch.setattr("src.config.Settings.from_env", lambda: fake)

    blob = teleporter.export_config(_PASSWORD, cache_keys=["lastfm_db"])

    preview = teleporter.preview_config(blob, _PASSWORD)
    assert "lastfm_history.db" in preview["files"]

    restored_db = tmp_path / "restored.db"
    fake.lastfm_local_db_file = str(restored_db)
    result = teleporter.import_config(blob, _PASSWORD)
    assert "lastfm_db" in result["restored"]

    dst = LocalScrobbleDB(restored_db)
    assert dst.get_track_count() == 2
    assert dst.get_total_plays() == 3


def test_teleporter_skips_lastfm_db_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(teleporter, "_CONFIG_FILES", [])
    monkeypatch.setattr(teleporter, "_CACHE_FILES", {})

    src_db = tmp_path / "lastfm_history.db"
    src = LocalScrobbleDB(src_db)
    src.ingest_scrobbles([Scrobble("A", "Hit", "", int(time.time()))])
    src.close()

    fake = _fake_settings(tmp_path, src_db)
    monkeypatch.setattr("src.config.Settings.from_env", lambda: fake)
    blob = teleporter.export_config(_PASSWORD, cache_keys=["lastfm_db"])

    fake.use_local_lastfm_db = False
    fake.lastfm_local_db_file = str(tmp_path / "restored.db")
    result = teleporter.import_config(blob, _PASSWORD)
    assert "lastfm_db" in result["skipped"]
    assert not (tmp_path / "restored.db").exists()
