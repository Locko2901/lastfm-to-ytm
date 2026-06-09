from src.lastfm import Scrobble
from src.tags.filter import filter_tracks_by_tags


def _track(artist, title):
    return Scrobble(artist=artist, track=title, album="", ts=0)


def _tag_map(**entries):
    out = {}
    for key, tags in entries.items():
        artist, title = key.split("|")
        out[(artist.lower(), title.lower())] = [{"name": n, "count": c} for n, c in tags]
    return out


def test_filter_any_match():
    tracks = [_track("A", "Rock Song"), _track("B", "Pop Song")]
    tag_map = _tag_map(**{"A|Rock Song": [("rock", 100)], "B|Pop Song": [("pop", 100)]})
    result = filter_tracks_by_tags(tracks, tag_map, {"rock"}, match="any", min_count=10)
    assert [t.track for t in result] == ["Rock Song"]


def test_filter_all_match_requires_every_tag():
    tracks = [_track("A", "Both"), _track("B", "OnlyRock")]
    tag_map = _tag_map(**{"A|Both": [("rock", 100), ("electronic", 100)], "B|OnlyRock": [("rock", 100)]})
    result = filter_tracks_by_tags(tracks, tag_map, {"rock", "electronic"}, match="all", min_count=10)
    assert [t.track for t in result] == ["Both"]


def test_filter_respects_min_count():
    tracks = [_track("A", "Weak")]
    tag_map = _tag_map(**{"A|Weak": [("rock", 5)]})
    result = filter_tracks_by_tags(tracks, tag_map, {"rock"}, match="any", min_count=10)
    assert result == []


def test_filter_skips_blacklisted():
    tracks = [_track("A", "Rock Song")]
    tag_map = _tag_map(**{"A|Rock Song": [("rock", 100)]})
    result = filter_tracks_by_tags(tracks, tag_map, {"rock"}, match="any", min_count=10, blacklist=frozenset({"a|rock song"}))
    assert result == []


def test_filter_skips_tracks_without_tags():
    tracks = [_track("A", "Untagged")]
    result = filter_tracks_by_tags(tracks, {}, {"rock"}, match="any", min_count=10)
    assert result == []


def test_filter_case_insensitive_keys_and_tags():
    tracks = [_track("Artist", "Song")]
    tag_map = _tag_map(**{"Artist|Song": [("ROCK", 100)]})
    result = filter_tracks_by_tags(tracks, tag_map, {"rock"}, match="any", min_count=10)
    assert len(result) == 1


def test_filter_empty_tracks():
    assert filter_tracks_by_tags([], {}, {"rock"}) == []
