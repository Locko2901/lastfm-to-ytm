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


HEADERS = "cookie: SAPISID=fake; SID=fake\nx-goog-authuser: 0\nuser-agent: test"


@pytest.fixture
def submit(client, monkeypatch, tmp_path):
    """POST pasted headers to /api/auth/submit against a fake YouTube Music; returns the answer, the file and the events."""
    import ytmusicapi

    from web.routes import auth
    from web.services import events

    browser_json = tmp_path / "browser.json"
    monkeypatch.setattr(auth, "BROWSER_JSON_FILE", browser_json)
    published = []
    monkeypatch.setattr(events, "publish", lambda event, data=None: published.append((event, data)))

    def post(outcome):
        class LiveCheck:
            def __init__(self, auth_json):
                assert '"cookie"' in auth_json

            def get_liked_songs(self, **_kwargs):
                if isinstance(outcome, BaseException):
                    raise outcome
                return outcome

        monkeypatch.setattr(ytmusicapi, "YTMusic", LiveCheck)
        response = client.post("/api/auth/submit", json={"headers_raw": HEADERS})
        return response.status_code, response.get_json(), published

    post.browser_json = browser_json
    return post


def test_headers_that_pass_the_live_check_are_saved_and_announced(submit):
    liked = {"tracks": [{"title": "Song", "artists": [{"name": "Artist"}]}]}
    status, body, published = submit(liked)
    assert (status, body) == (200, {"success": True, "verified": True, "lastLiked": "Song by Artist"})
    assert "SAPISID=fake" in submit.browser_json.read_text(encoding="utf-8")
    assert published == [("auth_status", {"valid": True})]


@pytest.mark.parametrize(
    ("outcome", "status", "reason"),
    [
        (YTMusicServerError(None), 400, "signed out"),
        (KeyError("singleColumnBrowseResultsRenderer"), 400, "signed out"),
        (OSError("Max retries exceeded with url: /youtubei/v1/browse"), 502, "Could not check the headers"),
    ],
)
def test_headers_that_fail_the_live_check_leave_browser_json_and_the_banner(submit, outcome, status, reason):
    submit.browser_json.write_text('{"cookie": "SAPISID=previous"}', encoding="utf-8")
    before = submit.browser_json.stat().st_mtime_ns
    answer, body, published = submit(outcome)
    assert (answer, body["success"]) == (status, False)
    assert reason in body["error"]
    assert submit.browser_json.read_text(encoding="utf-8") == '{"cookie": "SAPISID=previous"}'
    assert submit.browser_json.stat().st_mtime_ns == before
    assert published == []


def test_a_failed_first_connection_creates_no_browser_json(submit):
    answer, body, published = submit(OSError("Name or service not known"))
    assert (answer, body["success"], published) == (502, False, [])
    assert not submit.browser_json.exists()
