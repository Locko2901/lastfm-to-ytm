"""Tests for ``record_tracks_to_history`` miss classification + cache lookups."""

from __future__ import annotations

import pytest

from src.cache.search import SearchCache
from src.history.db import HistoryDB
from src.observability.history_recording import record_near_misses_to_history, record_tracks_to_history


@pytest.fixture
def db(tmp_path):
    database = HistoryDB(str(tmp_path / "history.db"))
    yield database
    database.close()


@pytest.fixture
def cache(tmp_path):
    return SearchCache(str(tmp_path / ".search_cache.json"))


def test_records_found_track_with_cache_metadata(db, cache):
    cache.set("Daft Punk", "One More Time", "vid00000001", yt_title="Daft Punk - One More Time")
    mappings = [{"artist": "Daft Punk", "title": "One More Time", "source": "search"}]

    record_tracks_to_history(db, mappings, cache)

    hist = db.get_track_history("Daft Punk", "One More Time")
    assert hist["video_id"] == "vid00000001"
    assert hist["yt_title"] == "Daft Punk - One More Time"
    assert hist["times_found"] == 1
    assert hist["times_missed"] == 0


@pytest.mark.parametrize("source", ["not_found", "not_found_cached", "blacklisted"])
def test_miss_sources_increment_missed(db, cache, source):
    mappings = [{"artist": "A", "title": "B", "source": source}]

    record_tracks_to_history(db, mappings, cache)

    hist = db.get_track_history("A", "B")
    assert hist["times_missed"] == 1
    assert hist["times_found"] == 0
    assert hist["video_id"] is None


def test_skips_entries_missing_artist_or_title(db, cache):
    mappings = [
        {"artist": "", "title": "B", "source": "search"},
        {"artist": "A", "title": "", "source": "search"},
    ]

    record_tracks_to_history(db, mappings, cache)

    assert db.get_track_count() == 0


def test_found_track_without_cache_entry_records_no_video(db, cache):
    mappings = [{"artist": "A", "title": "B", "source": "search"}]

    record_tracks_to_history(db, mappings, cache)

    hist = db.get_track_history("A", "B")
    assert hist["times_found"] == 1
    assert hist["video_id"] is None


def test_near_misses_records_tracks_past_limit(db, cache):
    cache.set("A", "Third", "vid00000003", yt_title="A - Third")
    mappings = [
        {"artist": "A", "title": "First", "source": "search", "score": 0.9, "plays": 5},
        {"artist": "A", "title": "Second", "source": "search", "score": 0.8, "plays": 4},
        {"artist": "A", "title": "Third", "source": "search", "score": 0.7, "plays": 3},
    ]

    stored = record_near_misses_to_history(db, mappings, cache, limit=2)

    assert stored == 1
    got = db.get_near_misses()
    assert len(got) == 1
    assert got[0]["title"] == "Third"
    assert got[0]["rank"] == 3
    assert got[0]["cutoff"] == 2
    assert got[0]["video_id"] == "vid00000003"
    assert got[0]["score"] == 0.7
    assert got[0]["plays"] == 3


def test_near_misses_skips_miss_sources_when_ranking(db, cache):
    mappings = [
        {"artist": "A", "title": "First", "source": "search", "score": 0.9},
        {"artist": "X", "title": "Missing", "source": "not_found"},
        {"artist": "A", "title": "Second", "source": "cache", "score": 0.8},
        {"artist": "A", "title": "Third", "source": "search", "score": 0.7},
    ]

    stored = record_near_misses_to_history(db, mappings, cache, limit=2)

    assert stored == 1
    assert db.get_near_misses()[0]["title"] == "Third"


def test_near_misses_none_when_all_fit(db, cache):
    mappings = [{"artist": "A", "title": "Only", "source": "search", "score": 0.9}]
    assert record_near_misses_to_history(db, mappings, cache, limit=5) == 0
    assert db.get_near_miss_count() == 0


def test_near_misses_clears_stale_rows_when_none(db, cache):
    db.record_near_misses(1, [{"artist": "A", "title": "Old", "video_id": "v1"}], cutoff=2)
    mappings = [{"artist": "A", "title": "Only", "source": "search"}]
    record_near_misses_to_history(db, mappings, cache, limit=5)
    assert db.get_near_miss_count() == 0


def test_near_misses_noop_when_limit_zero(db, cache):
    mappings = [{"artist": "A", "title": "T", "source": "search"}]
    assert record_near_misses_to_history(db, mappings, cache, limit=0) == 0
