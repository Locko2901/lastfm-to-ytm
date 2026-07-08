import pytest

from src.history.db import HistoryDB


@pytest.fixture
def db(tmp_path):
    database = HistoryDB(str(tmp_path / "history.db"))
    yield database
    database.close()


def test_record_track_creates_row(db):
    db.record_track("Daft Punk", "One More Time", video_id="abc12345678", source="search")
    hist = db.get_track_history("Daft Punk", "One More Time")
    assert hist is not None
    assert hist["video_id"] == "abc12345678"
    assert hist["times_found"] == 1
    assert hist["times_missed"] == 0


def test_record_track_upsert_increments_found(db):
    db.record_track("A", "B", video_id="vid00000001")
    db.record_track("A", "B", video_id="vid00000001")
    hist = db.get_track_history("A", "B")
    assert hist["times_found"] == 2


def test_record_track_missed_increments_missed(db):
    db.record_track("A", "B", missed=True)
    hist = db.get_track_history("A", "B")
    assert hist["times_found"] == 0
    assert hist["times_missed"] == 1


def test_record_track_is_case_insensitive_unique(db):
    db.record_track("Artist", "Title", video_id="vid00000001")
    db.record_track("artist", "title", video_id="vid00000001")
    assert db.get_track_count() == 1


def test_get_track_history_missing_returns_none(db):
    assert db.get_track_history("Nope", "Nope") is None


def test_get_tracks_search_filter(db):
    db.record_track("Daft Punk", "One More Time", video_id="v1100000000")
    db.record_track("Queen", "Bohemian Rhapsody", video_id="v2200000000")
    results = db.get_tracks(search="queen")
    assert len(results) == 1
    assert results[0]["artist"] == "Queen"


def test_get_tracks_found_filter(db):
    db.record_track("A", "Found", video_id="vid00000001")
    db.record_track("B", "Missing", missed=True)
    found = db.get_tracks(found_filter="found")
    not_found = db.get_tracks(found_filter="not_found")
    assert {t["title"] for t in found} == {"Found"}
    assert {t["title"] for t in not_found} == {"Missing"}


def test_get_tracks_invalid_sort_falls_back(db):
    db.record_track("A", "B", video_id="vid00000001")
    assert db.get_tracks(sort="; DROP TABLE tracks") != []


def test_get_tracks_valid_sort_and_order(db):
    db.record_track("Aaa", "First", video_id="vid00000001")
    db.record_track("Zzz", "Second", video_id="vid00000002")
    asc = db.get_tracks(sort="artist", order="asc")
    desc = db.get_tracks(sort="artist", order="desc")
    assert [t["artist"] for t in asc] == ["Aaa", "Zzz"]
    assert [t["artist"] for t in desc] == ["Zzz", "Aaa"]


def test_get_track_count_with_source_filter(db):
    db.record_track("A", "B", source="search", video_id="v1")
    db.record_track("C", "D", source="override", video_id="v2")
    assert db.get_track_count(source_filter="override") == 1


def test_start_and_finish_sync(db):
    sync_id = db.start_sync(sync_type="main", trigger="manual")
    db.finish_sync(sync_id, status="success", tracks_total=10, tracks_resolved=8)
    rec = db.get_sync(sync_id)
    assert rec["status"] == "success"
    assert rec["tracks_total"] == 10
    assert rec["tracks_resolved"] == 8
    assert rec["finished_at"] is not None
    assert rec["duration_secs"] is not None


def test_start_sync_dedupes_recent_running(db):
    first = db.start_sync(sync_type="main")
    second = db.start_sync(sync_type="main")
    assert first == second
    assert db.get_sync_count() == 1


def test_get_syncs_newest_first(db):
    a = db.start_sync(sync_type="main")
    db.finish_sync(a)
    b = db.start_sync(sync_type="tags")
    db.finish_sync(b)
    syncs = db.get_syncs()
    assert syncs[0]["id"] == b


def test_get_sync_missing_returns_none(db):
    assert db.get_sync(9999) is None


def test_record_and_get_action(db):
    db.record_action("add_override", artist="A", title="B", video_id="v1", detail="manual fix")
    actions = db.get_actions()
    assert len(actions) == 1
    assert actions[0]["action_type"] == "add_override"


def test_record_action_dedupes_identical_recent(db):
    db.record_action("delete_cache", artist="A", title="B")
    db.record_action("delete_cache", artist="A", title="B")
    assert db.get_action_count() == 1


def test_get_actions_type_filter(db):
    db.record_action("add_override", artist="A", title="B")
    db.record_action("delete_cache", artist="C", title="D")
    assert db.get_action_count(action_type="add_override") == 1


def test_action_type_counts(db):
    db.record_action("x", artist="A", title="1")
    db.record_action("x", artist="B", title="2")
    db.record_action("y", artist="C", title="3")
    counts = db.get_action_type_counts()
    assert counts["x"] == 2
    assert counts["y"] == 1


def test_overview_stats(db):
    db.record_track("A", "Found", video_id="v1")
    db.record_track("B", "Missing", missed=True)
    sync_id = db.start_sync()
    db.finish_sync(sync_id, status="success", api_searches=5, cache_hits=3, cache_misses=1)
    stats = db.get_overview_stats()
    assert stats["total_tracks"] == 2
    assert stats["found_tracks"] == 1
    assert stats["not_found_tracks"] == 1
    assert stats["successful_syncs"] == 1
    assert stats["total_api_searches"] == 5
    assert stats["cache_hit_rate"] == 75.0


def test_get_top_tracks_ordered(db):
    db.record_track("A", "Popular", video_id="v1")
    db.record_track("A", "Popular", video_id="v1")
    db.record_track("B", "Rare", video_id="v2")
    top = db.get_top_tracks(limit=5)
    assert top[0]["title"] == "Popular"


def test_source_counts(db):
    db.record_track("A", "1", source="search", video_id="v1")
    db.record_track("B", "2", source="search", video_id="v2")
    db.record_track("C", "3", source="override", video_id="v3")
    assert db.get_source_counts() == {"search": 2, "override": 1}


def test_backfill_from_search_cache(db):
    cache_data = {
        "daft punk|one more time": {"video_id": "v1", "yt_title": "yt1", "timestamp": "2024-01-01T00:00:00+00:00"},
        "queen|bohemian rhapsody": {"video_id": "v2"},
        "malformed_key_no_pipe": {"video_id": "v3"},
    }
    count = db.backfill_from_search_cache(cache_data)
    assert count == 2
    assert db.get_track_count() == 2


def test_backfill_from_overrides(db):
    overrides = {"artist|title": {"video_id": "v1"}}
    assert db.backfill_from_overrides(overrides) == 1
    assert db.get_track_history("artist", "title")["video_id"] == "v1"


def test_prune_by_age_removes_old(db):
    sync_id = db.start_sync()
    db.finish_sync(sync_id)
    db.record_action("x", artist="A", title="B")
    with db._cursor() as cur:
        cur.execute("UPDATE syncs SET started_at = '2000-01-01T00:00:00+00:00'")
        cur.execute("UPDATE actions SET timestamp = '2000-01-01T00:00:00+00:00'")
    result = db.prune_by_age(retention_days=30)
    assert result == {"actions": 1, "syncs": 1}
    assert db.get_sync_count() == 0
    assert db.get_action_count() == 0


def test_prune_by_age_keeps_tracks(db):
    db.record_track("A", "B", video_id="v1")
    db.prune_by_age(retention_days=30)
    assert db.get_track_count() == 1


def test_prune_by_age_zero_is_noop(db):
    assert db.prune_by_age(retention_days=0) == {"actions": 0, "syncs": 0}


def test_export_import_roundtrip(db, tmp_path):
    db.record_track("A", "B", video_id="v1")
    sync_id = db.start_sync()
    db.finish_sync(sync_id)
    db.record_action("x", artist="A", title="B")
    export = db.export_to_dict()

    other = HistoryDB(str(tmp_path / "other.db"))
    try:
        counts = other.import_from_dict(export, mode="replace")
        assert counts["tracks"] == 1
        assert other.get_track_history("A", "B")["video_id"] == "v1"
    finally:
        other.close()


def test_import_invalid_mode_raises(db):
    with pytest.raises(ValueError):
        db.import_from_dict({"tables": {}}, mode="bogus")


def test_import_future_schema_raises(db):
    with pytest.raises(ValueError):
        db.import_from_dict({"schema_version": 999, "tables": {}})


def test_record_near_misses_stores_ranked_rows(db):
    rows = [
        {"artist": "A", "title": "Close", "video_id": "v1", "score": 0.42, "plays": 3},
        {"artist": "B", "title": "Closer", "video_id": "v2", "score": 0.40, "plays": 2},
    ]
    stored = db.record_near_misses(sync_id=7, rows=rows, cutoff=100)
    assert stored == 2
    got = db.get_near_misses()
    assert [r["rank"] for r in got] == [101, 102]
    assert got[0]["title"] == "Close"
    assert got[0]["cutoff"] == 100
    assert got[0]["sync_id"] == 7
    assert db.get_near_miss_count() == 2


def test_record_near_misses_replaces_previous(db):
    db.record_near_misses(1, [{"artist": "A", "title": "Old", "video_id": "v1"}], cutoff=50)
    db.record_near_misses(2, [{"artist": "B", "title": "New", "video_id": "v2"}], cutoff=50)
    got = db.get_near_misses()
    assert len(got) == 1
    assert got[0]["title"] == "New"


def test_record_near_misses_empty_clears(db):
    db.record_near_misses(1, [{"artist": "A", "title": "Old", "video_id": "v1"}], cutoff=50)
    assert db.record_near_misses(2, [], cutoff=50) == 0
    assert db.get_near_miss_count() == 0


def test_record_near_misses_caps_rows(db):
    rows = [{"artist": "A", "title": f"T{i}", "video_id": f"v{i}"} for i in range(150)]
    stored = db.record_near_misses(1, rows, cutoff=10)
    assert stored == 100
    assert db.get_near_miss_count() == 100


def test_record_near_misses_skips_blank_artist_title(db):
    rows = [
        {"artist": "", "title": "Blank", "video_id": "v1"},
        {"artist": "A", "title": "Good", "video_id": "v2"},
    ]
    db.record_near_misses(1, rows, cutoff=5)
    got = db.get_near_misses()
    assert len(got) == 1
    assert got[0]["title"] == "Good"


def test_near_misses_pagination(db):
    rows = [{"artist": "A", "title": f"T{i}", "video_id": f"v{i}"} for i in range(5)]
    db.record_near_misses(1, rows, cutoff=0)
    page1 = db.get_near_misses(limit=2, offset=0)
    page2 = db.get_near_misses(limit=2, offset=2)
    assert [r["rank"] for r in page1] == [1, 2]
    assert [r["rank"] for r in page2] == [3, 4]


def test_clear_all_wipes_near_misses(db):
    db.record_near_misses(1, [{"artist": "A", "title": "T", "video_id": "v1"}], cutoff=10)
    db.clear_all()
    assert db.get_near_miss_count() == 0


def test_near_misses_export_import_roundtrip(db, tmp_path):
    db.record_near_misses(3, [{"artist": "A", "title": "T", "video_id": "v1", "score": 0.5, "plays": 4}], cutoff=20)
    export = db.export_to_dict()
    assert "near_misses" in export["tables"]

    other = HistoryDB(str(tmp_path / "other.db"))
    try:
        counts = other.import_from_dict(export, mode="replace")
        assert counts["near_misses"] == 1
        got = other.get_near_misses()
        assert got[0]["title"] == "T"
        assert got[0]["rank"] == 21
    finally:
        other.close()
