import pytest

from src.search.normalization import tokens
from src.search.queries import build_queries, candidate_artists, clean_title_for_match, split_artist_aliases


def test_split_artist_aliases_single_artist():
    assert split_artist_aliases("Daft Punk") == ["daft punk"]


def test_split_artist_aliases_splits_on_ampersand():
    result = split_artist_aliases("Simon & Garfunkel")
    assert "simon" in result
    assert "garfunkel" in result
    assert "simon and garfunkel" in result


def test_split_artist_aliases_strips_feat():
    result = split_artist_aliases("Drake feat. Rihanna")
    assert "drake" in result
    assert all("rihanna" not in alias for alias in result)


def test_split_artist_aliases_empty_returns_blank():
    assert split_artist_aliases("") == [""]


def test_clean_title_for_match_removes_bracketed():
    assert clean_title_for_match("Halo (Live)", set()) == "halo"


def test_clean_title_for_match_drops_leading_artist():
    artist_tokens = tokens("Artist")
    assert clean_title_for_match("Artist - Song", artist_tokens) == "song"


def test_candidate_artists_from_artists_list():
    r = {"artists": [{"name": "Beyoncé"}, {"name": "Jay-Z"}]}
    assert candidate_artists(r) == ["Beyoncé", "Jay-Z"]


def test_candidate_artists_includes_cleaned_author():
    r = {"artists": [], "author": "Adele - Topic"}
    assert candidate_artists(r) == ["adele"]


def test_build_queries_returns_strings():
    queries = build_queries("Daft Punk", "One More Time", None)
    assert queries
    assert all(isinstance(q, str) for q in queries)
    assert "daft punk - one more time" in queries


def test_build_queries_respects_already_tried():
    skip = {"daft punk - one more time"}
    queries = build_queries("Daft Punk", "One More Time", None, already_tried=skip)
    assert "daft punk - one more time" not in queries


def test_build_queries_includes_album_variant():
    queries = build_queries("Daft Punk", "One More Time", "Discovery")
    assert any("discovery" in q.lower() for q in queries)


def test_build_queries_no_duplicates():
    queries = build_queries("Daft Punk", "One More Time", None)
    assert len(queries) == len(set(queries))


def test_clean_title_for_match_falls_back_when_empty():
    assert clean_title_for_match("(Live)", set()) != ""


def test_split_artist_aliases_dedupes():
    aliases = split_artist_aliases("Daft Punk & Daft Punk")
    assert len(aliases) == len(set(aliases))


@pytest.mark.parametrize(
    "artist",
    ["Max Richter", "Rex Orange County", "Alex Turner", "Lil Nas X", "xxxtentacion", "C+C Music Factory", "Vsevolod Zaderatsky"],
)
def test_split_artist_aliases_keeps_single_names_whole(artist):
    assert split_artist_aliases(artist) == [artist.lower()]


@pytest.mark.parametrize(
    ("credit", "parts"),
    [
        ("DJ Snake x Lil Jon", ["dj snake", "lil jon"]),
        ("Calvin Harris X Dua Lipa", ["calvin harris", "dua lipa"]),
        ("Rosalía × The Weeknd", ["rosalía", "the weeknd"]),
        ("Artist A + Artist B", ["artist a", "artist b"]),
        ("Artist A vs Artist B", ["artist a", "artist b"]),
        ("Artist A vs. Artist B", ["artist a", "artist b"]),
    ],
)
def test_split_artist_aliases_splits_between_artists(credit, parts):
    assert split_artist_aliases(credit) == [*parts, credit.lower()]


@pytest.mark.parametrize(
    ("band", "parts", "full"),
    [
        ("Mumford & Sons", ["mumford", "sons"], "mumford and sons"),
        ("Florence + the Machine", ["florence", "the machine"], "florence + the machine"),
    ],
)
def test_split_artist_aliases_keeps_a_band_name_as_an_alias(band, parts, full):
    assert split_artist_aliases(band) == [*parts, full]
