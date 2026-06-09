import pytest

from src.search.scoring import (
    HARD_PENALTY_PER_HIT,
    SOFT_PENALTY_PER_HIT,
    STYLE_MISMATCH_SONG_PENALTY,
    STYLE_MISMATCH_VIDEO_PENALTY,
    album_name_from_result,
    hard_negative_hits,
    negative_penalty,
    score_candidate,
    style_mismatch_penalty,
)


def test_album_name_from_dict():
    assert album_name_from_result({"album": {"name": "Discovery"}}) == "Discovery"


def test_album_name_from_string():
    assert album_name_from_result({"album": "Discovery"}) == "Discovery"


def test_album_name_missing():
    assert album_name_from_result({}) is None
    assert album_name_from_result({"album": None}) is None


def test_hard_negative_hits_detected():
    assert hard_negative_hits("Halo Nightcore", "Halo") == {"nightcore"}


def test_hard_negative_hits_suppressed_when_user_wants_it():
    assert hard_negative_hits("Halo Nightcore", "Halo Nightcore") == set()


def test_negative_penalty_none():
    assert negative_penalty("Halo", "Halo") == 0.0


def test_negative_penalty_soft_term():
    assert negative_penalty("Halo (Live)", "Halo") == pytest.approx(SOFT_PENALTY_PER_HIT)


def test_negative_penalty_hard_term():
    assert negative_penalty("Halo Nightcore", "Halo") == pytest.approx(HARD_PENALTY_PER_HIT)


def test_style_mismatch_no_user_style():
    assert style_mismatch_penalty("Halo", "Halo", "video") == 0.0


def test_style_mismatch_video_penalty():
    assert style_mismatch_penalty("Halo Nightcore", "Halo", "video") == pytest.approx(STYLE_MISMATCH_VIDEO_PENALTY)


def test_style_mismatch_song_penalty():
    assert style_mismatch_penalty("Halo Nightcore", "Halo", "song") == pytest.approx(STYLE_MISMATCH_SONG_PENALTY)


def test_style_mismatch_satisfied():
    assert style_mismatch_penalty("Halo Nightcore", "Halo Nightcore", "video") == 0.0


def test_score_candidate_strong_song_match():
    r = {
        "resultType": "song",
        "title": "Halo",
        "artists": [{"name": "Beyoncé"}],
        "album": {"name": "I Am... Sasha Fierce"},
    }
    score = score_candidate(r, "Beyoncé", "Halo", "I Am... Sasha Fierce")
    assert score > 0.7


def test_score_candidate_hard_reject_nightcore_video():
    r = {
        "resultType": "video",
        "title": "Halo (Nightcore)",
        "artists": [{"name": "Beyoncé"}],
        "author": "Some User",
    }
    assert score_candidate(r, "Beyoncé", "Halo", None) == 0.0


def test_score_candidate_rejects_unrelated_artist():
    r = {
        "resultType": "song",
        "title": "Halo",
        "artists": [{"name": "Completely Different Band"}],
        "author": "Completely Different Band",
    }
    assert score_candidate(r, "Beyoncé", "Halo", None) == 0.0


def test_score_candidate_song_beats_video():
    song = {"resultType": "song", "title": "Halo", "artists": [{"name": "Beyoncé"}]}
    video = {"resultType": "video", "title": "Halo", "artists": [{"name": "Beyoncé"}], "author": "Beyoncé"}
    assert score_candidate(song, "Beyoncé", "Halo", None) > score_candidate(video, "Beyoncé", "Halo", None)


def test_score_candidate_bounded():
    r = {"resultType": "song", "title": "Halo", "artists": [{"name": "Beyoncé"}]}
    assert 0.0 <= score_candidate(r, "Beyoncé", "Halo", None) <= 1.0


def test_score_candidate_unknown_result_type_rejected():
    r = {"resultType": "playlist", "title": "Halo", "artists": [{"name": "Beyoncé"}]}
    assert score_candidate(r, "Beyoncé", "Halo", None) == 0.0


def test_score_candidate_empty_result_type_allowed():
    r = {"resultType": "", "title": "Halo", "artists": [{"name": "Beyoncé"}]}
    assert score_candidate(r, "Beyoncé", "Halo", None) > 0.0


def test_score_candidate_live_version_penalized():
    studio = {"resultType": "song", "title": "Halo", "artists": [{"name": "Beyoncé"}]}
    live = {"resultType": "song", "title": "Halo (Live)", "artists": [{"name": "Beyoncé"}]}
    assert score_candidate(studio, "Beyoncé", "Halo", None) > score_candidate(live, "Beyoncé", "Halo", None)


def test_negative_penalty_multiple_soft_terms_capped():
    penalty = negative_penalty("Halo Live Acoustic Remix Cover Karaoke", "Halo")
    assert penalty <= 0.25 + 1e-9
