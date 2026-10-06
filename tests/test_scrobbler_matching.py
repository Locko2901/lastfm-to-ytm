import pytest

from src.scrobbler.matching import (
    ARTIST_DIFFERS,
    MATCH,
    TITLE_DIFFERS,
    VERSION_DIFFERS,
    artist_keys,
    clean_video_title,
    compare,
    split_title,
    track_key,
)

pytestmark = pytest.mark.usefixtures("no_network")


def verdict(a_artist, a_title, b_artist, b_title):
    return compare(track_key(a_artist, a_title), track_key(b_artist, b_title))


@pytest.mark.parametrize(
    ("ytm_title", "lastfm_title"),
    [
        ("Bohemian Rhapsody", "Bohemian Rhapsody - Remastered 2011"),
        ("Bohemian Rhapsody (Remastered 2011)", "Bohemian Rhapsody"),
        ("Bohemian Rhapsody - 2011 Remaster", "Bohemian Rhapsody [Remastered]"),
        ("Bohemian Rhapsody", "Bohemian Rhapsody - Single Version"),
        ("Bohemian Rhapsody", "Bohemian Rhapsody - Radio Edit"),
    ],
)
def test_remasters_and_edits_are_the_same_track(ytm_title, lastfm_title):
    assert verdict("Queen", ytm_title, "Queen", lastfm_title) == MATCH


@pytest.mark.parametrize(
    ("ytm_artists", "ytm_title", "lastfm_artist", "lastfm_title"),
    [
        (["Daft Punk", "Pharrell Williams"], "Get Lucky", "Daft Punk", "Get Lucky (feat. Pharrell Williams)"),
        (["Daft Punk"], "Get Lucky (feat. Pharrell Williams)", "Daft Punk feat. Pharrell Williams", "Get Lucky"),
        (["Daft Punk", "Pharrell Williams", "Nile Rodgers"], "Get Lucky", "Daft Punk & Pharrell Williams", "Get Lucky"),
        (["Daft Punk"], "Get Lucky ft. Pharrell Williams", "Daft Punk", "Get Lucky"),
        (["Pharrell Williams"], "Get Lucky", "Daft Punk feat. Pharrell Williams", "Get Lucky"),
    ],
)
def test_featured_artists_do_not_break_a_match(ytm_artists, ytm_title, lastfm_artist, lastfm_title):
    assert compare(track_key(ytm_artists, ytm_title), track_key(lastfm_artist, lastfm_title)) == MATCH


def test_live_version_is_a_near_miss_not_a_match():
    assert verdict("Oasis", "Wonderwall (Live)", "Oasis", "Wonderwall") == VERSION_DIFFERS
    assert verdict("Oasis", "Wonderwall - Live at Knebworth", "Oasis", "Wonderwall") == VERSION_DIFFERS


def test_two_live_versions_match_each_other():
    assert verdict("Oasis", "Wonderwall - Live at Knebworth", "Oasis", "Wonderwall (Live)") == MATCH


def test_song_with_live_in_its_name_is_not_a_version():
    assert verdict("Oasis", "Live Forever", "Oasis", "Live Forever - Remastered") == MATCH
    assert verdict("Oasis", "Live Forever (Live)", "Oasis", "Live Forever") == VERSION_DIFFERS


@pytest.mark.parametrize("version", ["Remix", "Acoustic", "Instrumental", "Sped Up", "Demo"])
def test_other_versions_differ_from_the_original(version):
    assert verdict("Artist", f"Song ({version})", "Artist", "Song") == VERSION_DIFFERS


def test_same_title_by_another_artist_is_a_near_miss():
    assert verdict("Johnny Cash", "Hurt", "Nine Inch Nails", "Hurt") == ARTIST_DIFFERS


def test_another_song_by_the_same_artist_differs():
    assert verdict("Queen", "Bohemian Rhapsody", "Queen", "Somebody to Love") == TITLE_DIFFERS


def test_case_accents_and_punctuation_are_ignored():
    assert verdict("Beyoncé", "Déjà Vu", "BEYONCE", "deja vu") == MATCH
    assert verdict("Guns N' Roses", "Sweet Child O' Mine", "Guns N Roses", "Sweet Child O Mine") == MATCH
    assert verdict("Artist", "Don't Stop", "Artist", "Dont Stop") == MATCH


def test_leading_the_is_ignored_in_artists():
    assert verdict("The Beatles", "Let It Be", "Beatles", "Let It Be") == MATCH


def test_music_video_title_with_artist_prefix_matches_the_song():
    ytm = track_key(["Rick Astley"], "Rick Astley - Never Gonna Give You Up (Official Music Video)")
    assert compare(ytm, track_key("Rick Astley", "Never Gonna Give You Up")) == MATCH


def test_topic_channel_artist_matches():
    assert verdict(["Some Band - Topic"], "Song", "Some Band", "Song") == MATCH


def test_artist_split_does_not_cut_words_containing_x():
    keys = artist_keys("Alex Turner")
    assert "alexturner" in keys
    assert "ale" not in keys
    assert artist_keys("Calvin Harris x Dua Lipa") >= {"calvinharris", "dualipa"}


def test_artist_split_takes_plus_and_vs_between_names():
    assert artist_keys("Armin van Buuren vs. Vini Vici") >= {"arminvanbuuren", "vinivici"}
    assert artist_keys("Florence + the Machine") >= {"florencethemachine", "florence", "machine"}
    assert verdict(["Florence + the Machine"], "Dog Days Are Over", "Florence + the Machine", "Dog Days Are Over") == MATCH
    assert artist_keys("C+C Music Factory") == {"ccmusicfactory"}


def test_split_title_separates_core_and_qualifiers():
    core, qualifiers = split_title("Song - Live at Wembley")
    assert core == "song"
    assert "live" in qualifiers
    core, _ = split_title("Part One - The Beginning")
    assert core == "part one - the beginning"


def test_clean_video_title_keeps_meaningful_brackets():
    assert clean_video_title("Artist - Song (Official Video) [4K]", "Artist") == "Song"
    assert clean_video_title("Song (Live)", "Artist") == "Song (Live)"
    assert clean_video_title("Other - Song", "Artist") == "Other - Song"
