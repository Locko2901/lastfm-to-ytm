import time
from datetime import UTC, datetime

import pytest

from src.lastfm import Scrobble
from src.recency.weighting import (
    _compute_play_scores,
    _in_session,
    collapse_recency_weighted,
    dedupe_keep_latest,
    weight_history_tracks,
)


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


def _record(artist, track, plays, last_uts, album="", first_uts=None):
    if first_uts is None:
        first_uts = last_uts
    return (artist, track, album, plays, first_uts, last_uts)


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


def test_compute_play_scores_linear():
    assert _compute_play_scores([1.0, 2.0, 4.0], "linear") == [0.25, 0.5, 1.0]


def test_compute_play_scores_linear_default_for_unknown():
    assert _compute_play_scores([1.0, 4.0], "bogus") == [0.25, 1.0]


def test_compute_play_scores_log_compresses_outlier():
    linear = _compute_play_scores([1.0, 10.0, 500.0], "linear")
    logscores = _compute_play_scores([1.0, 10.0, 500.0], "log")
    assert logscores[1] > linear[1]
    assert linear[2] == 1.0
    assert logscores[2] == 1.0


def test_compute_play_scores_rank_ignores_magnitude():
    a = _compute_play_scores([1.0, 2.0, 3.0], "rank")
    b = _compute_play_scores([1.0, 50.0, 5000.0], "rank")
    assert a == b
    assert a == [1 / 3, 2 / 3, 3 / 3]


def test_compute_play_scores_rank_averages_ties():
    scores = _compute_play_scores([5.0, 5.0, 9.0], "rank")
    assert scores[0] == scores[1] == 1.5 / 3
    assert scores[2] == 1.0


def test_compute_play_scores_empty():
    assert _compute_play_scores([], "linear") == []


def test_collapse_log_normalization_tames_outlier():
    now = int(time.time())
    scrobbles = [_scrobble("Big", "Hit", now) for _ in range(50)]
    scrobbles += [_scrobble("Mid", "Song", now)] * 5
    scrobbles += [_scrobble("Low", "Track", now)]
    linear = collapse_recency_weighted(scrobbles, play_weight=1.0, normalization="linear")
    logged = collapse_recency_weighted(scrobbles, play_weight=1.0, normalization="log")
    mid_lin = next(w.score for w in linear if w.track == "Song")
    mid_log = next(w.score for w in logged if w.track == "Song")
    assert mid_log > mid_lin


def test_weight_history_rank_normalization():
    now = int(time.time())
    records = [
        _record("A", "Top", 5000, now),
        _record("B", "Mid", 50, now),
        _record("C", "Low", 5, now),
    ]
    result = weight_history_tracks(records, play_weight=1.0, normalization="rank")
    scores = {w.track: w.score for w in result}
    assert scores["Top"] == 1.0
    assert scores["Mid"] == 2 / 3
    assert scores["Low"] == 1 / 3


def test_collapse_velocity_favors_bursty_track():
    now = int(time.time())
    day = 86400
    scrobbles = [_scrobble("A", "Burst", now - i * 3600) for i in range(10)]
    scrobbles += [_scrobble("B", "Spread", now - i * 6 * day) for i in range(10)]
    baseline = collapse_recency_weighted(scrobbles, play_weight=1.0, velocity_weight=0.0)
    trending = collapse_recency_weighted(scrobbles, play_weight=1.0, velocity_weight=0.8)
    assert {w.track: w.plays for w in baseline} == {"Burst": 10, "Spread": 10}
    assert trending[0].track == "Burst"


def test_collapse_velocity_weight_zero_is_noop():
    now = int(time.time())
    scrobbles = [
        _scrobble("A", "One", now),
        _scrobble("A", "One", now - 100),
        _scrobble("B", "Two", now - 50),
    ]
    a = collapse_recency_weighted(scrobbles, velocity_weight=0.0)
    b = collapse_recency_weighted(scrobbles)
    assert [w.track for w in a] == [w.track for w in b]
    for wa, wb in zip(a, b, strict=True):
        assert wa.score == pytest.approx(wb.score, abs=1e-6)


def test_weight_history_velocity_uses_span():
    now = int(time.time())
    day = 86400
    records = [
        _record("A", "Fast", 20, now, first_uts=now - 2 * day),
        _record("B", "Slow", 20, now, first_uts=now - 200 * day),
    ]
    result = weight_history_tracks(records, play_weight=1.0, velocity_weight=0.9)
    assert result[0].track == "Fast"


def _ts_at_hour(hour: int) -> int:
    """Return a recent UTC timestamp landing on the given hour of day."""
    base = datetime(2026, 6, 1, hour, 30, tzinfo=UTC)
    return int(base.timestamp())


def test_session_weighting_boosts_in_window_plays():
    evening = [_scrobble("A", "Evening", _ts_at_hour(20) - i) for i in range(3)]
    night = [_scrobble("B", "Night", _ts_at_hour(3) - i) for i in range(3)]
    scrobbles = evening + night
    off = collapse_recency_weighted(scrobbles, play_weight=1.0, half_life_hours=0.0, session_weighting=False)
    on = collapse_recency_weighted(
        scrobbles,
        play_weight=1.0,
        half_life_hours=0.0,
        session_weighting=True,
        session_start=18,
        session_end=23,
        session_timezone="UTC",
    )
    assert {w.track: w.score for w in off}["Evening"] == {w.track: w.score for w in off}["Night"]
    assert on[0].track == "Evening"


def test_session_weighting_wraps_past_midnight():
    late = [_scrobble("A", "Late", _ts_at_hour(2) - i) for i in range(3)]
    day = [_scrobble("B", "Day", _ts_at_hour(13) - i) for i in range(3)]
    result = collapse_recency_weighted(
        late + day,
        play_weight=1.0,
        half_life_hours=0.0,
        session_weighting=True,
        session_start=22,
        session_end=4,
        session_timezone="UTC",
    )
    assert result[0].track == "Late"


def test_in_session_helper():
    assert _in_session(10, 9, 23) is True
    assert _in_session(23, 9, 23) is False
    assert _in_session(3, 22, 4) is True
    assert _in_session(12, 22, 4) is False
    assert _in_session(5, 8, 8) is True  # start == end covers whole day
