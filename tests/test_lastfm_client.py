import hashlib

import pytest
import requests

from src.lastfm.client import (
    MIN_CALL_INTERVAL_SECONDS,
    SCROBBLE_BATCH_SIZE,
    HttpResponse,
    LastfmAuthError,
    LastfmClient,
    LastfmError,
    LastfmTokenPending,
    LastfmTooManyScrobbles,
    LastfmUnavailable,
    ScrobbleEntry,
    api_signature,
    iter_batches,
    parse_scrobble_response,
)

pytestmark = pytest.mark.usefixtures("no_network")


class FakeTransport:
    """Replays canned responses and records every request; never touches the network."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, http_method, params):
        self.calls.append((http_method, dict(params)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def ok(payload):
    return HttpResponse(200, payload)


def client(transport, clock=None, **kwargs):
    clock = clock or Clock()
    kwargs.setdefault("max_retries", 3)
    return LastfmClient("KEY", "SECRET", "SK", transport=transport, sleep=clock.sleep, clock=clock.now, **kwargs)


def accepted(artist, track, ts):
    return {
        "artist": {"corrected": "0", "#text": artist},
        "track": {"corrected": "0", "#text": track},
        "album": {"corrected": "0", "#text": ""},
        "timestamp": str(ts),
        "ignoredMessage": {"code": "0", "#text": ""},
    }


def test_signature_sorts_params_and_skips_format():
    params = {"token": "t", "method": "auth.getSession", "api_key": "k", "format": "json"}
    expected = hashlib.md5(b"api_keykmethodauth.getSessiontokents", usedforsecurity=False).hexdigest()
    assert api_signature(params, "s") == expected


def test_signature_encodes_utf8_and_sorts_array_params_by_ascii():
    params = {"track[1]": "B", "track[0]": "Déjà Vu", "artist[0]": "A"}
    raw = "artist[0]Atrack[0]Déjà Vutrack[1]Bsecret".encode()
    assert api_signature(params, "secret") == hashlib.md5(raw, usedforsecurity=False).hexdigest()


def test_get_token_is_signed_and_auth_url_carries_it():
    transport = FakeTransport(ok({"token": "TOKEN123"}))
    c = client(transport)
    assert c.get_token() == "TOKEN123"
    method, params = transport.calls[0]
    assert method == "GET"
    assert params["method"] == "auth.getToken"
    assert params["api_sig"] == api_signature({k: v for k, v in params.items() if k != "api_sig"}, "SECRET")
    assert c.auth_url("TOKEN123") == "https://www.last.fm/api/auth/?api_key=KEY&token=TOKEN123"


def test_get_session_returns_key_and_name():
    transport = FakeTransport(ok({"session": {"name": "someone", "key": "SESSION", "subscriber": 0}}))
    assert client(transport).get_session("TOKEN") == ("SESSION", "someone")
    assert transport.calls[0][1]["token"] == "TOKEN"


def test_unapproved_token_raises_pending_without_retrying():
    transport = FakeTransport(HttpResponse(403, {"error": 14, "message": "This token has not been authorized"}))
    with pytest.raises(LastfmTokenPending):
        client(transport).get_session("TOKEN")
    assert len(transport.calls) == 1


def test_expired_token_is_a_plain_error():
    transport = FakeTransport(HttpResponse(403, {"error": 15, "message": "This token has expired"}))
    with pytest.raises(LastfmError) as info:
        client(transport).get_session("TOKEN")
    assert info.value.code == 15
    assert not isinstance(info.value, LastfmTokenPending)


def test_signed_call_without_secret_is_refused_before_any_request():
    transport = FakeTransport()
    c = LastfmClient("KEY", "", transport=transport)
    with pytest.raises(LastfmError):
        c.get_token()
    assert transport.calls == []


def test_scrobble_batch_uses_array_notation_and_post():
    results = [accepted("A", "One", 1), accepted("B", "Two", 2)]
    transport = FakeTransport(ok({"scrobbles": {"@attr": {"accepted": 2, "ignored": 0}, "scrobble": results}}))
    entries = [ScrobbleEntry("A", "One", 1, "Album", 200), ScrobbleEntry("B", "Two", 2)]
    outcomes = client(transport).scrobble_batch(entries)
    method, params = transport.calls[0]
    assert method == "POST"
    assert params["method"] == "track.scrobble"
    assert params["sk"] == "SK"
    assert (params["artist[0]"], params["track[0]"], params["timestamp[0]"], params["album[0]"], params["duration[0]"]) == (
        "A",
        "One",
        "1",
        "Album",
        "200",
    )
    assert "album[1]" not in params
    assert "duration[1]" not in params
    assert [o.accepted for o in outcomes] == [True, True]


def test_scrobble_batch_rejects_more_than_fifty():
    entries = [ScrobbleEntry("A", f"T{i}", i) for i in range(SCROBBLE_BATCH_SIZE + 1)]
    with pytest.raises(ValueError):
        client(FakeTransport()).scrobble_batch(entries)


def test_scrobble_without_session_key_is_an_auth_error():
    c = LastfmClient("KEY", "SECRET", "", transport=FakeTransport())
    with pytest.raises(LastfmAuthError):
        c.scrobble_batch([ScrobbleEntry("A", "T", 1)])


def test_iter_batches_splits_into_fifties():
    assert [len(b) for b in iter_batches(list(range(120)))] == [50, 50, 20]
    assert iter_batches([]) == []


def test_single_scrobble_response_is_a_dict_not_a_list():
    payload = {"scrobbles": {"@attr": {"accepted": 1, "ignored": 0}, "scrobble": accepted("A", "One", 1)}}
    (outcome,) = parse_scrobble_response(payload, 1)
    assert outcome.accepted


def test_ignored_scrobbles_report_code_and_message():
    item = accepted("A", "One", 1)
    item["ignoredMessage"] = {"code": "3", "#text": "Timestamp too old"}
    (outcome,) = parse_scrobble_response({"scrobbles": {"scrobble": [item]}}, 1)
    assert not outcome.accepted
    assert (outcome.ignored_code, outcome.ignored_message) == (3, "Timestamp too old")


def test_response_with_the_wrong_number_of_results_is_an_error():
    with pytest.raises(LastfmError):
        parse_scrobble_response({"scrobbles": {"scrobble": []}}, 1)


def test_server_errors_are_retried_with_backoff():
    clock = Clock()
    transport = FakeTransport(HttpResponse(503, None), HttpResponse(502, None), ok({"token": "T"}))
    assert client(transport, clock).get_token() == "T"
    assert len(transport.calls) == 3
    backoffs = [s for s in clock.sleeps if s >= 1]
    assert backoffs == [1.0, 2.0]


@pytest.mark.parametrize("code", [8, 11, 16, 29])
def test_temporary_lastfm_error_codes_are_retried(code):
    transport = FakeTransport(HttpResponse(200, {"error": code, "message": "try later"}), ok({"token": "T"}))
    assert client(transport).get_token() == "T"
    assert len(transport.calls) == 2


def test_rate_limit_honours_retry_after():
    clock = Clock()
    transport = FakeTransport(HttpResponse(429, {"error": 29, "message": "Rate limit exceeded"}, retry_after=7), ok({"token": "T"}))
    client(transport, clock).get_token()
    assert 7 in clock.sleeps


def test_network_errors_are_retried_then_reported_unavailable():
    transport = FakeTransport(requests.ConnectionError("down"), requests.Timeout("slow"), requests.ConnectionError("down"))
    with pytest.raises(LastfmUnavailable):
        client(transport).get_token()
    assert len(transport.calls) == 3


def test_invalid_session_is_not_retried():
    transport = FakeTransport(HttpResponse(403, {"error": 9, "message": "Invalid session key"}))
    with pytest.raises(LastfmAuthError):
        client(transport).scrobble_batch([ScrobbleEntry("A", "T", 1)])
    assert len(transport.calls) == 1


def test_bad_request_errors_are_not_retried():
    transport = FakeTransport(HttpResponse(400, {"error": 6, "message": "Invalid parameters"}))
    with pytest.raises(LastfmError) as info:
        client(transport).scrobble_batch([ScrobbleEntry("A", "T", 1)])
    assert info.value.code == 6
    assert not isinstance(info.value, LastfmUnavailable)
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "failure",
    [requests.ReadTimeout("no answer"), requests.ConnectionError("reset"), HttpResponse(502, None), HttpResponse(200, None)],
)
def test_scrobble_is_never_resent_after_an_ambiguous_failure(failure):
    transport = FakeTransport(failure, ok({"scrobbles": {"scrobble": accepted("A", "T", 1)}}))
    with pytest.raises(LastfmUnavailable):
        client(transport).scrobble_batch([ScrobbleEntry("A", "T", 1)])
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectTimeout("no connection"),
        HttpResponse(429, {"error": 29, "message": "Rate limit exceeded"}),
        HttpResponse(503, {"error": 16, "message": "Temporarily unavailable"}),
        HttpResponse(200, {"error": 11, "message": "Service offline"}),
    ],
)
def test_scrobble_is_retried_when_lastfm_did_not_process_it(failure):
    transport = FakeTransport(failure, ok({"scrobbles": {"scrobble": accepted("A", "T", 1)}}))
    (outcome,) = client(transport).scrobble_batch([ScrobbleEntry("A", "T", 1)])
    assert outcome.accepted
    assert len(transport.calls) == 2


def test_calls_are_paced_to_stay_under_the_rate_limit():
    clock = Clock()
    transport = FakeTransport(ok({"token": "A"}), ok({"token": "B"}))
    c = client(transport, clock)
    c.get_token()
    c.get_token()
    assert clock.sleeps == [MIN_CALL_INTERVAL_SECONDS]


def recent_page(tracks, page, total_pages):
    return ok({"recenttracks": {"track": tracks, "@attr": {"page": str(page), "totalPages": str(total_pages)}}})


def track(artist, name, uts=None, nowplaying=False):
    t = {"artist": {"#text": artist}, "name": name, "album": {"#text": "Album"}}
    if uts is not None:
        t["date"] = {"uts": str(uts)}
    if nowplaying:
        t["@attr"] = {"nowplaying": "true"}
    return t


def test_recent_scrobbles_follow_pages_and_skip_now_playing():
    transport = FakeTransport(
        recent_page([track("A", "Now", nowplaying=True), track("A", "One", 300)], 1, 2),
        recent_page([track("B", "Two", 200)], 2, 2),
    )
    scrobbles = client(transport).recent_scrobbles("user", 100)
    assert [(s.artist, s.track, s.ts) for s in scrobbles] == [("A", "One", 300), ("B", "Two", 200)]
    assert transport.calls[0][1]["from"] == "100"
    assert transport.calls[1][1]["page"] == "2"


def test_recent_scrobbles_can_end_at_a_timestamp():
    transport = FakeTransport(recent_page([track("A", "One", 300)], 1, 1))
    client(transport).recent_scrobbles("user", 100, 400)
    params = transport.calls[0][1]
    assert (params["from"], params["to"]) == ("100", "400")
    transport = FakeTransport(recent_page([track("A", "One", 300)], 1, 1))
    client(transport).recent_scrobbles("user", 100)
    assert "to" not in transport.calls[0][1]


def test_recent_scrobbles_give_up_beyond_the_page_cap():
    transport = FakeTransport(recent_page([track("A", "One", 300)], 1, 9), recent_page([track("A", "Two", 200)], 2, 9))
    with pytest.raises(LastfmTooManyScrobbles):
        client(transport).recent_scrobbles("user", 0, max_pages=2)


def test_now_playing_is_read_from_the_first_track():
    transport = FakeTransport(recent_page([track("A", "Playing", nowplaying=True), track("A", "Done", 100)], 1, 1))
    playing = client(transport).now_playing("user")
    assert (playing.artist, playing.track, playing.album) == ("A", "Playing", "Album")


def test_no_now_playing_when_nothing_plays():
    transport = FakeTransport(recent_page(track("A", "Done", 100), 1, 1))
    assert client(transport).now_playing("user") is None


class FakeResponse:
    status_code = 200

    def __init__(self):
        self.headers = {}

    def json(self):
        return {"ok": True}


def test_the_plain_requests_transport_sends_through_the_requests_module(monkeypatch):
    from src.lastfm.client import requests_transport

    sent = []

    def fake(method):
        def call(url, **kwargs):
            sent.append((method, url.endswith("/2.0/"), kwargs.get("params") or kwargs.get("data")))
            return FakeResponse()

        return call

    monkeypatch.setattr(requests, "get", fake("GET"))
    monkeypatch.setattr(requests, "post", fake("POST"))
    assert requests_transport("GET", {"method": "user.getRecentTracks"}).payload == {"ok": True}
    requests_transport("POST", {"method": "track.scrobble"})
    assert sent == [("GET", True, {"method": "user.getRecentTracks"}), ("POST", True, {"method": "track.scrobble"})]


def test_shared_field_helpers_read_text_and_lists():
    from src.lastfm.fetch import as_list, field_text, parse_tracks

    assert (field_text({"#text": "Artist"}), field_text("Artist"), field_text(None), field_text({})) == ("Artist", "Artist", "", "")
    assert (as_list({"a": 1}), as_list([1, 2]), as_list(None), as_list("x")) == ([{"a": 1}], [1, 2], [], [])
    rows = [
        {"artist": {"#text": " Artist "}, "name": " Song ", "album": "Album", "date": {"uts": "5"}},
        {"artist": "A", "name": "Now", "@attr": {"nowplaying": "true"}},
        {"artist": {"#text": "B"}, "name": "No date"},
    ]
    assert [(s.artist, s.track, s.album, s.ts) for s in parse_tracks(rows)] == [("Artist", "Song", "Album", 5)]
