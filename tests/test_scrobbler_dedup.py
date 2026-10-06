import pytest

from src.scrobbler.dedup import DEFAULT_DURATION_SECONDS, Candidate, find_duplicate, window_seconds
from src.scrobbler.matching import ARTIST_DIFFERS, VERSION_DIFFERS, track_key

pytestmark = pytest.mark.usefixtures("no_network")

T = 1_700_000_000
KEY = track_key(["Queen"], "Bohemian Rhapsody")


def scrobble(ts, artist="Queen", track="Bohemian Rhapsody", album="A Night at the Opera", now_playing=False):
    return Candidate(artist, track, album, ts, now_playing)


def test_window_is_duration_plus_poll_gap():
    assert window_seconds(355, 300) == 655
    assert window_seconds(None, 300) == DEFAULT_DURATION_SECONDS + 300
    assert window_seconds(200, -5) == 200


def test_scrobble_exactly_at_the_window_edge_is_a_duplicate():
    window = window_seconds(355, 300)
    for ts in (T + window, T - window):
        result = find_duplicate(KEY, T, window, [scrobble(ts)], set())
        assert result.duplicate == 0


def test_scrobble_one_second_outside_the_window_is_not_a_duplicate():
    window = window_seconds(355, 300)
    for ts in (T + window + 1, T - window - 1):
        result = find_duplicate(KEY, T, window, [scrobble(ts)], set())
        assert result.duplicate is None


def test_the_closest_matching_scrobble_wins():
    candidates = [scrobble(T - 400), scrobble(T + 100), scrobble(T - 50)]
    assert find_duplicate(KEY, T, 600, candidates, set()).duplicate == 2


def test_a_scrobble_covers_only_one_play():
    candidates = [scrobble(T)]
    used = {0}
    assert find_duplicate(KEY, T, 600, candidates, used).duplicate is None


def test_now_playing_covers_the_play():
    result = find_duplicate(KEY, T, 600, [scrobble(T + 120, now_playing=True)], set())
    assert result.duplicate == 0


def test_another_album_is_still_a_duplicate():
    result = find_duplicate(KEY, T, 600, [scrobble(T, album="Greatest Hits")], set())
    assert result.duplicate == 0


def test_remaster_and_feat_scrobbles_are_duplicates():
    feat_key = track_key(["Daft Punk", "Pharrell Williams"], "Get Lucky")
    candidates = [Candidate("Daft Punk feat. Pharrell Williams", "Get Lucky - Radio Edit", "", T + 30)]
    assert find_duplicate(feat_key, T, 600, candidates, set()).duplicate == 0
    remaster = [scrobble(T + 10, track="Bohemian Rhapsody - Remastered 2011")]
    assert find_duplicate(KEY, T, 600, remaster, set()).duplicate == 0


def test_live_version_in_the_window_is_a_near_miss_only():
    result = find_duplicate(KEY, T, 600, [scrobble(T + 5, track="Bohemian Rhapsody (Live at Wembley)")], set())
    assert result.duplicate is None
    assert result.near_miss == 0
    assert result.near_miss_reason == VERSION_DIFFERS


def test_same_title_by_another_artist_is_a_near_miss_only():
    result = find_duplicate(KEY, T, 600, [scrobble(T, artist="Panic! at the Disco")], set())
    assert result.duplicate is None
    assert result.near_miss_reason == ARTIST_DIFFERS


def test_near_miss_outside_the_window_is_not_reported():
    result = find_duplicate(KEY, T, 600, [scrobble(T + 601, track="Bohemian Rhapsody (Live)")], set())
    assert result.near_miss is None


def test_match_wins_over_a_closer_near_miss():
    candidates = [scrobble(T + 1, track="Bohemian Rhapsody (Live)"), scrobble(T + 300)]
    result = find_duplicate(KEY, T, 600, candidates, set())
    assert result.duplicate == 1
    assert result.near_miss == 0
