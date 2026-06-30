import time

from src.lastfm import Scrobble
from src.recency.weighting import collapse_recency_weighted, dedupe_keep_latest, weight_history_tracks


def _scrobble(artist, track, ts, album=""):
    return Scrobble(artist=artist, track=track, album=album, ts=ts)


def test_dedupe_keep_latest_keeps_most_recent():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Song", now - 100),
        _scrobble("A", "Song", now),
        _scrobble("B", "Other", now - 50),
    ]
    result = dedupe_keep_latest(scrobbles)
    assert len(result) == 2
    by_track = {s.track: s for s in result}
    assert by_track["Song"].ts == now


def test_dedupe_keep_latest_case_insensitive():
    now = int(time.time())
    scrobbles = [
        _scrobble("Artist", "Song", now - 10),
        _scrobble("artist", "song", now),
    ]
    result = dedupe_keep_latest(scrobbles)
    assert len(result) == 1
    assert result[0].ts == now


def test_dedupe_keep_latest_sorted_desc():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Old", now - 1000),
        _scrobble("B", "New", now),
    ]
    result = dedupe_keep_latest(scrobbles)
    assert [s.track for s in result] == ["New", "Old"]


def test_dedupe_keep_latest_empty():
    assert dedupe_keep_latest([]) == []


def test_collapse_aggregates_play_counts():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Song", now - 200),
        _scrobble("A", "Song", now - 100),
        _scrobble("A", "Song", now),
        _scrobble("B", "Other", now),
    ]
    result = collapse_recency_weighted(scrobbles)
    plays = {w.track: w.plays for w in result}
    assert plays["Song"] == 3
    assert plays["Other"] == 1


def test_collapse_ranks_by_play_count_when_play_weight_one():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Popular", now),
        _scrobble("A", "Popular", now),
        _scrobble("A", "Popular", now),
        _scrobble("B", "Rare", now),
    ]
    result = collapse_recency_weighted(scrobbles, play_weight=1.0)
    assert result[0].track == "Popular"
    assert result[0].score == 1.0


def test_collapse_ranks_by_recency_when_play_weight_zero():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Recent", now),
        _scrobble("B", "Stale", now - 3600 * 240),
    ]
    result = collapse_recency_weighted(scrobbles, play_weight=0.0, half_life_hours=24.0)
    assert result[0].track == "Recent"


def test_collapse_min_plays_filter():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Twice", now),
        _scrobble("A", "Twice", now - 10),
        _scrobble("B", "Once", now),
    ]
    result = collapse_recency_weighted(scrobbles, min_plays=2)
    tracks = {w.track for w in result}
    assert tracks == {"Twice"}


def test_collapse_keeps_latest_album():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "Song", now - 10, album="Old Album"),
        _scrobble("A", "Song", now, album="New Album"),
    ]
    result = collapse_recency_weighted(scrobbles)
    assert result[0].album == "New Album"


def test_collapse_empty():
    assert collapse_recency_weighted([]) == []


def _record(artist, track, plays, last_uts, album=""):
    return (artist, track, album, plays, last_uts)


def test_weight_history_ranks_by_lifetime_plays_when_play_weight_one():
    now = int(time.time())
    records = [
        _record("A", "Popular", 100, now),
        _record("B", "Rare", 1, now),
    ]
    result = weight_history_tracks(records, play_weight=1.0)
    assert result[0].track == "Popular"
    assert result[0].score == 1.0
    assert result[0].plays == 100


def test_weight_history_ranks_by_recency_when_play_weight_zero():
    now = int(time.time())
    records = [
        _record("A", "Recent", 5, now),
        _record("B", "Stale", 5, now - 3600 * 240),
    ]
    result = weight_history_tracks(records, play_weight=0.0, half_life_hours=24.0)
    assert result[0].track == "Recent"


def test_weight_history_min_plays_filter():
    now = int(time.time())
    records = [
        _record("A", "Kept", 3, now),
        _record("B", "Dropped", 1, now),
    ]
    result = weight_history_tracks(records, min_plays=2)
    assert {w.track for w in result} == {"Kept"}


def test_weight_history_zero_timestamp_treated_as_oldest():
    now = int(time.time())
    records = [
        _record("A", "HasTime", 5, now),
        _record("B", "NoTime", 5, 0),
    ]
    result = weight_history_tracks(records, play_weight=0.0, half_life_hours=24.0)
    assert result[0].track == "HasTime"
    assert result[-1].track == "NoTime"


def test_weight_history_empty():
    assert weight_history_tracks([]) == []
