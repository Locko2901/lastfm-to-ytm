import pytest
from ytmusicapi.exceptions import YTMusicServerError

from src.ytm import is_signed_out

SIGNED_OUT = [
    YTMusicServerError(None),
    YTMusicServerError(),
    YTMusicServerError(""),
    KeyError("singleColumnBrowseResultsRenderer"),
    Exception("Sign in to confirm your account"),
]
OTHER = [
    YTMusicServerError("Server returned HTTP 503: Service Unavailable"),
    YTMusicServerError({"text": "History is paused"}),
    RuntimeError("Read timed out"),
]


@pytest.mark.parametrize("error", SIGNED_OUT)
def test_signed_out_answers_are_recognised(error):
    assert is_signed_out(error)


@pytest.mark.parametrize("error", OTHER)
def test_other_failures_are_not_signed_out(error):
    assert not is_signed_out(error)


@pytest.mark.parametrize(("error", "expired"), [*((e, True) for e in SIGNED_OUT), *((e, False) for e in OTHER)])
def test_auth_test_route_reports_a_signed_out_session_as_expired(client, monkeypatch, tmp_path, error, expired):
    import ytmusicapi

    from web.routes import auth

    browser_json = tmp_path / "browser.json"
    browser_json.write_text('{"cookie": "SAPISID=x"}', encoding="utf-8")
    monkeypatch.setattr(auth, "BROWSER_JSON_FILE", browser_json)

    class SignedOutYTMusic:
        def __init__(self, _path):
            pass

        def get_liked_songs(self, **_kwargs):
            raise error

    monkeypatch.setattr(ytmusicapi, "YTMusic", SignedOutYTMusic)
    body = client.get("/api/auth/test").get_json()
    assert body["valid"] is False
    assert body.get("expired", False) is expired
