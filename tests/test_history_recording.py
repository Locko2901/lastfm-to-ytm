"""Tests for ``record_tracks_to_history`` miss classification + cache lookups."""

from __future__ import annotations

import pytest

from src.cache.search import SearchCache
from src.history.db import HistoryDB
from src.observability.history_recording import record_tracks_to_history


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
