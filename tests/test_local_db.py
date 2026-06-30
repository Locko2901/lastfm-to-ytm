import time

from src.lastfm import LocalScrobbleDB, Scrobble


def _sc(artist, track, ts, album=""):
    return Scrobble(artist=artist, track=track, album=album, ts=ts)


def test_empty_db_state(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    assert db.is_empty() is True
    assert db.get_last_scrobble_uts() is None
    assert db.get_track_count() == 0
    assert db.get_total_plays() == 0


def test_ingest_increments_plays_and_dedupes(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles(
        [
            _sc("A", "Song", now - 100),
            _sc("a", "song", now - 50),
            _sc("B", "Other", now - 10),
        ]
    )
    assert db.get_track_count() == 2
    assert db.get_total_plays() == 3
    rows = {(r["artist"].lower(), r["track"].lower()): r for r in db.get_top_tracks(10)}
    assert rows[("a", "song")]["plays"] == 2
    assert rows[("b", "other")]["plays"] == 1


def test_watermark_tracks_max_uts(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "S", now - 100), _sc("A", "S", now)])
    assert db.get_last_scrobble_uts() == now
    assert db.is_empty() is False
    db.ingest_scrobbles([_sc("B", "T", now - 500)])
    assert db.get_last_scrobble_uts() == now


def test_first_and_last_played_tracked(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "S", now)])
    db.ingest_scrobbles([_sc("A", "S", now - 1000)])
    db.ingest_scrobbles([_sc("A", "S", now + 1000)])
    row = db.get_top_tracks(1)[0]
    assert row["first_played_uts"] == now - 1000
    assert row["last_played_uts"] == now + 1000
    assert row["plays"] == 3


def test_get_scoring_rows_respects_min_plays(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "Twice", now), _sc("A", "Twice", now), _sc("B", "Once", now)])
    rows = db.get_scoring_rows(min_plays=2)
    assert len(rows) == 1
    artist, track, _album, plays, _last = rows[0]
    assert (artist.lower(), track.lower()) == ("a", "twice")
    assert plays == 2


def test_top_tracks_ordered_by_plays(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "Low", now)])
    db.ingest_scrobbles([_sc("B", "High", now), _sc("B", "High", now), _sc("B", "High", now)])
    top = db.get_top_tracks(10)
    assert top[0]["track"].lower() == "high"
    assert top[0]["plays"] == 3


def test_album_filled_when_available(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "S", now, album="")])
    db.ingest_scrobbles([_sc("A", "S", now + 1, album="Greatest Hits")])
    row = db.get_top_tracks(1)[0]
    assert row["album"] == "Greatest Hits"


def test_stats_and_mark_synced(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "S", now), _sc("A", "S", now)])
    db.mark_synced(full=True)
    stats = db.get_stats()
    assert stats["total_tracks"] == 1
    assert stats["total_plays"] == 2
    assert stats["last_played_uts"] == now
    assert stats["last_sync_at"] is not None
    assert stats["last_full_sync_at"] is not None
    assert stats["db_size_bytes"] > 0


def test_persistence_across_instances(tmp_path):
    path = tmp_path / "lfm.db"
    db = LocalScrobbleDB(path)
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "S", now)])
    db.close()

    db2 = LocalScrobbleDB(path)
    assert db2.get_track_count() == 1
    assert db2.get_last_scrobble_uts() == now


def test_clear_resets_db_and_watermark(tmp_path):
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    now = int(time.time())
    db.ingest_scrobbles([_sc("A", "S", now), _sc("B", "T", now)])
    assert db.get_track_count() == 2

    db.clear()
    assert db.get_track_count() == 0
    assert db.get_total_plays() == 0
    assert db.get_last_scrobble_uts() is None
    assert db.is_empty() is True


def test_export_import_roundtrip(tmp_path):
    src = LocalScrobbleDB(tmp_path / "src.db")
    now = int(time.time())
    src.ingest_scrobbles([_sc("A", "Song", now - 100), _sc("A", "Song", now), _sc("B", "Other", now)])
    payload = src.export_to_dict()
    assert len(payload["scrobbles"]) == 2

    dst = LocalScrobbleDB(tmp_path / "dst.db")
    counts = dst.import_from_dict(payload, mode="merge")
    assert counts["imported"] == 2
    assert dst.get_track_count() == 2
    assert dst.get_total_plays() == 3
    assert dst.get_last_scrobble_uts() == now


def test_import_merge_is_idempotent(tmp_path):
    src = LocalScrobbleDB(tmp_path / "src.db")
    now = int(time.time())
    src.ingest_scrobbles([_sc("A", "Song", now), _sc("A", "Song", now - 50)])
    payload = src.export_to_dict()

    dst = LocalScrobbleDB(tmp_path / "dst.db")
    dst.import_from_dict(payload, mode="merge")
    dst.import_from_dict(payload, mode="merge")
    assert dst.get_track_count() == 1
    assert dst.get_total_plays() == 2


def test_import_replace_wipes_first(tmp_path):
    dst = LocalScrobbleDB(tmp_path / "dst.db")
    now = int(time.time())
    dst.ingest_scrobbles([_sc("Old", "Track", now)])

    payload = {"scrobbles": [{"artist": "New", "track": "Song", "plays": 5, "last_played_uts": now}]}
    counts = dst.import_from_dict(payload, mode="replace")
    assert counts["imported"] == 1
    assert dst.get_track_count() == 1
    rows = dst.get_top_tracks(10)
    assert rows[0]["artist"] == "New"
    assert rows[0]["plays"] == 5


def test_import_skips_invalid_rows(tmp_path):
    dst = LocalScrobbleDB(tmp_path / "dst.db")
    payload = {"scrobbles": [{"artist": "A", "track": "B", "plays": 1}, {"artist": "", "track": "X"}, "garbage"]}
    counts = dst.import_from_dict(payload, mode="merge")
    assert counts["imported"] == 1
    assert counts["skipped"] == 2


def test_import_invalid_payload_raises(tmp_path):
    import pytest

    dst = LocalScrobbleDB(tmp_path / "dst.db")
    with pytest.raises(ValueError):
        dst.import_from_dict({"nope": []}, mode="merge")
    with pytest.raises(ValueError):
        dst.import_from_dict({"scrobbles": []}, mode="invalid")
