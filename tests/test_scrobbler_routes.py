"""Route tests for the history scrobbler (``web.routes.scrobbler``).

Settings are read from the hermetic ``.env`` in ``tmp_path`` and the Last.fm
client is a fake, so nothing reaches Last.fm or YouTube Music.
"""

from __future__ import annotations

import dataclasses
import os
import re
import time

import pytest

pytest.importorskip("flask")

from dotenv import dotenv_values

from src.config import Settings
from src.lastfm.client import LastfmError, LastfmTokenPending
from src.scrobbler.detect import SnapshotEntry
from src.scrobbler.service import ERROR_HISTORY, ERROR_HISTORY_AUTH, ERROR_LASTFM_UNAVAILABLE, PollOutcome
from src.scrobbler.store import PENDING, SKIPPED, WOULD_SCROBBLE, NewPlay, ScrobblerStore

pytestmark = pytest.mark.usefixtures("no_network")


class FakeAuthClient:
    def __init__(self):
        self.pending = False
        self.error = None
        self.session = ("SESSIONKEY", "me")

    def get_token(self):
        if self.error:
            raise self.error
        return "TOKEN"

    def auth_url(self, token):
        return f"https://www.last.fm/api/auth/?api_key=KEY&token={token}"

    def get_session(self, token):
        assert token == "TOKEN"
        if self.pending:
            raise LastfmTokenPending("not yet", 14)
        if self.error:
            raise self.error
        return self.session

    def now_playing(self, _username):
        return None

    def recent_scrobbles(self, _username, _from_ts, _to_ts=None):
        return []


@pytest.fixture
def scrobbler(client, web_paths, monkeypatch, tmp_path):
    from web.routes import api
    from web.routes import scrobbler as routes
    from web.services import scrobbler as service

    env_file = web_paths["ENV_FILE"]
    env_file.write_text("LASTFM_USER=me\nLASTFM_API_KEY=KEY\nSCROBBLER_ENABLED=true\n", encoding="utf-8")
    db = tmp_path / "scrobbler.db"

    def load_settings(**_kwargs):
        values = {k: v or "" for k, v in dotenv_values(env_file).items()}
        return Settings(
            lastfm_user=values.get("LASTFM_USER", ""),
            lastfm_api_key=values.get("LASTFM_API_KEY", ""),
            lastfm_api_secret=values.get("LASTFM_API_SECRET", ""),
            lastfm_session_key=values.get("LASTFM_SESSION_KEY", ""),
            lastfm_session_user=values.get("LASTFM_SESSION_USER", ""),
            scrobbler_enabled=values.get("SCROBBLER_ENABLED") == "true",
            scrobbler_dry_run=values.get("SCROBBLER_DRY_RUN", "true") == "true",
            scrobbler_idle_minutes=int(values.get("SCROBBLER_IDLE_MINUTES") or 10),
            scrobbler_db_file=str(db),
            ytm_auth_path=str(tmp_path / "browser.json"),
        )

    fake = FakeAuthClient()
    service.reset_store()
    monkeypatch.setattr(service, "load_settings", load_settings)
    monkeypatch.setattr(routes, "load_settings", load_settings)
    monkeypatch.setattr(service, "build_client", lambda _settings: fake)
    monkeypatch.setattr(routes, "scrobbler_next_poll", lambda: None)
    configured = []
    monkeypatch.setattr(api, "configure_scrobbler_job", lambda: configured.append(True))

    class Env:
        pass

    e = Env()
    e.client, e.env_file, e.db, e.fake, e.load_settings, e.configured, e.service = client, env_file, db, fake, load_settings, configured, service
    e.routes = routes
    yield e
    service.reset_store()


def env_values(path):
    return dotenv_values(path)


def add_play(store, video_id, status, reason="", ts=1_700_000_000):
    play = NewPlay(video_id, "Artist", f"Song {video_id}", ("Artist",), "", 200, "Today", False, ts, ts - 150, ts + 150, status, reason)
    store.record_detection([SnapshotEntry(video_id, "Today")], ts + 150, ts - 150, [play], poll_id=None, dry_run=True)


def test_status_reports_settings_and_connection(scrobbler):
    body = scrobbler.client.get("/api/scrobbler/status").get_json()
    assert body["enabled"] is True
    assert body["dry_run"] is True
    assert body["connected"] is False
    assert body["has_secret"] is False
    assert body["lastfm_user"] == "me"
    assert "session_key" not in body
    assert body["counts"]["pending"] == 0


def test_status_counts_the_last_day_and_every_open_play(scrobbler):
    store = ScrobblerStore(scrobbler.db)
    recent = int(time.time()) - 600
    add_play(store, "a", WOULD_SCROBBLE, ts=recent)
    add_play(store, "b", SKIPPED, "duplicate", ts=recent)
    add_play(store, "old", SKIPPED, "duplicate", ts=recent - 3 * 86400)
    add_play(store, "c", PENDING, ts=recent - 3 * 86400)
    counts = scrobbler.client.get("/api/scrobbler/status").get_json()["counts"]
    assert (counts["would_scrobble"], counts["skipped"], counts["pending"]) == (1, 1, 1)


def test_plays_are_listed_and_filtered_by_group(scrobbler):
    store = ScrobblerStore(scrobbler.db)
    add_play(store, "a", WOULD_SCROBBLE, ts=1_700_000_000)
    add_play(store, "b", SKIPPED, "duplicate", ts=1_700_000_100)
    add_play(store, "c", PENDING, ts=1_700_000_200)

    everything = scrobbler.client.get("/api/scrobbler/plays").get_json()
    assert everything["total"] == 3
    assert [p["video_id"] for p in everything["plays"]] == ["c", "b", "a"]

    skipped = scrobbler.client.get("/api/scrobbler/plays?status=skipped").get_json()
    assert [p["reason"] for p in skipped["plays"]] == ["duplicate"]
    done = scrobbler.client.get("/api/scrobbler/plays?status=done").get_json()
    assert [p["video_id"] for p in done["plays"]] == ["a"]
    waiting = scrobbler.client.get("/api/scrobbler/plays?status=open&limit=1").get_json()
    assert waiting["total"] == 1


def test_plays_reject_bad_paging(scrobbler):
    assert scrobbler.client.get("/api/scrobbler/plays?limit=x").status_code == 400


def test_poll_now_refuses_when_disabled(scrobbler):
    scrobbler.env_file.write_text("LASTFM_USER=me\nLASTFM_API_KEY=KEY\nSCROBBLER_ENABLED=false\n", encoding="utf-8")
    assert scrobbler.client.post("/api/scrobbler/poll").status_code == 400


def test_poll_now_returns_the_outcome(scrobbler, monkeypatch):
    monkeypatch.setattr(scrobbler.service, "poll_now", lambda _settings: PollOutcome(status="ok", new_plays=2, would_scrobble=1))
    body = scrobbler.client.post("/api/scrobbler/poll").get_json()
    assert body["new_plays"] == 2
    assert body["would_scrobble"] == 1


def test_reset_clears_snapshot_and_decisions(scrobbler):
    store = ScrobblerStore(scrobbler.db)
    add_play(store, "a", WOULD_SCROBBLE)
    assert scrobbler.client.post("/api/scrobbler/reset").get_json()["status"] == "cleared"
    assert store.list_plays()[1] == 0
    assert store.load_snapshot() == (None, None)


def test_reset_waits_for_a_running_poll(scrobbler):
    store = ScrobblerStore(scrobbler.db)
    add_play(store, "a", WOULD_SCROBBLE)
    with ScrobblerStore(scrobbler.db).exclusive() as owned:
        assert owned
        assert scrobbler.client.post("/api/scrobbler/reset").status_code == 409
    assert store.list_plays()[1] == 1


def test_setup_saves_the_optional_api_secret_next_to_the_key(scrobbler):
    body = {"username": "me", "api_key": "KEY2", "api_secret": "SHH"}
    assert scrobbler.client.post("/api/setup/lastfm", json=body).status_code == 200
    values = env_values(scrobbler.env_file)
    assert (values["LASTFM_API_KEY"], values["LASTFM_API_SECRET"]) == ("KEY2", "SHH")
    scrobbler.client.post("/api/setup/lastfm", json={"username": "me", "api_key": "KEY3"})
    assert env_values(scrobbler.env_file)["LASTFM_API_SECRET"] == "SHH"


def test_dry_run_offer_counts_plays_and_records_sending(scrobbler):
    store = ScrobblerStore(scrobbler.db)
    recent = int(time.time()) - 600
    add_play(store, "a", WOULD_SCROBBLE, ts=recent)
    add_play(store, "old", WOULD_SCROBBLE, ts=recent - 20 * 86400)
    assert scrobbler.client.get("/api/scrobbler/dry-run-plays").get_json() == {"eligible": 1, "too_old": 1}
    assert scrobbler.client.post("/api/scrobbler/dry-run-plays", json={"send": True}).status_code == 400
    scrobbler.env_file.write_text("LASTFM_USER=me\nLASTFM_API_KEY=KEY\nSCROBBLER_ENABLED=true\nSCROBBLER_DRY_RUN=false\n", encoding="utf-8")
    assert scrobbler.client.post("/api/scrobbler/dry-run-plays", json={"send": True}).get_json() == {"queued": 1, "too_old": 1}
    rows = {r["video_id"]: r for r in store.list_plays()[0]}
    assert (rows["a"]["status"], rows["a"]["dry_run_choice"]) == (PENDING, "send")
    assert (rows["old"]["status"], rows["old"]["dry_run_choice"]) == (WOULD_SCROBBLE, "too_old")
    assert scrobbler.client.get("/api/scrobbler/dry-run-plays").get_json() == {"eligible": 0, "too_old": 0}


def test_dry_run_offer_can_be_declined(scrobbler):
    store = ScrobblerStore(scrobbler.db)
    add_play(store, "a", WOULD_SCROBBLE, ts=int(time.time()) - 600)
    assert scrobbler.client.post("/api/scrobbler/dry-run-plays", json={"send": False}).get_json() == {"kept": 1}
    row = store.list_plays()[0][0]
    assert (row["status"], row["dry_run_choice"]) == (WOULD_SCROBBLE, "keep")
    assert scrobbler.client.get("/api/scrobbler/dry-run-plays").get_json() == {"eligible": 0, "too_old": 0}


def test_dry_run_choice_waits_for_a_running_poll(scrobbler):
    with ScrobblerStore(scrobbler.db).exclusive() as owned:
        assert owned
        assert scrobbler.client.post("/api/scrobbler/dry-run-plays", json={"send": False}).status_code == 409


def test_connect_requires_the_api_secret(scrobbler):
    resp = scrobbler.client.post("/api/scrobbler/auth/start", json={})
    assert resp.status_code == 400


def test_connect_saves_the_secret_and_returns_the_approval_url(scrobbler):
    resp = scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["token"] == "TOKEN"
    assert body["auth_url"].startswith("https://www.last.fm/api/auth/")
    assert env_values(scrobbler.env_file)["LASTFM_API_SECRET"] == "SHH"


def test_connect_reports_lastfm_errors(scrobbler):
    scrobbler.fake.error = LastfmError("Invalid API key", 10)
    resp = scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})
    assert resp.status_code == 502


def test_finish_waits_while_the_token_is_not_approved(scrobbler):
    scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})
    scrobbler.fake.pending = True
    resp = scrobbler.client.post("/api/scrobbler/auth/finish", json={"token": "TOKEN"})
    assert resp.status_code == 202
    assert "LASTFM_SESSION_KEY" not in env_values(scrobbler.env_file)


def test_finish_stores_the_session_key_in_env(scrobbler):
    scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})
    resp = scrobbler.client.post("/api/scrobbler/auth/finish", json={"token": "TOKEN"})
    assert resp.get_json() == {"status": "connected", "user": "me"}
    values = env_values(scrobbler.env_file)
    assert values["LASTFM_SESSION_KEY"] == "SESSIONKEY"
    assert values["LASTFM_SESSION_USER"] == "me"
    assert scrobbler.env_file.stat().st_mode & 0o777 == 0o600
    status = scrobbler.client.get("/api/scrobbler/status").get_json()
    assert status["connected"] is True
    assert "SESSIONKEY" not in str(status)


def test_finish_refuses_another_lastfm_account(scrobbler):
    scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})
    scrobbler.fake.session = ("OTHERKEY", "someone-else")
    resp = scrobbler.client.post("/api/scrobbler/auth/finish", json={"token": "TOKEN"})
    assert resp.status_code == 400
    assert "LASTFM_SESSION_KEY" not in env_values(scrobbler.env_file)


def test_finish_needs_a_token(scrobbler):
    assert scrobbler.client.post("/api/scrobbler/auth/finish", json={}).status_code == 400


def test_disconnect_clears_the_session(scrobbler):
    scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})
    scrobbler.client.post("/api/scrobbler/auth/finish", json={"token": "TOKEN"})
    scrobbler.client.post("/api/scrobbler/auth/disconnect")
    values = env_values(scrobbler.env_file)
    assert values["LASTFM_SESSION_KEY"] == ""
    assert values["LASTFM_API_SECRET"] == "SHH"


def test_settings_never_return_the_session_key(scrobbler):
    scrobbler.env_file.write_text("LASTFM_USER=me\nLASTFM_SESSION_KEY=SESSIONKEY\nLASTFM_API_SECRET=SHH\n", encoding="utf-8")
    body = scrobbler.client.get("/api/settings").get_json()
    assert "LASTFM_SESSION_KEY" not in body
    assert body["LASTFM_API_SECRET"] == "SHH"
    assert body["SCROBBLER_ENABLED"] is False


def test_missing_dry_run_setting_reads_as_on(scrobbler):
    scrobbler.env_file.write_text("LASTFM_USER=me\nSCROBBLER_ENABLED=true\n", encoding="utf-8")
    assert scrobbler.client.get("/api/settings").get_json()["SCROBBLER_DRY_RUN"] is True
    scrobbler.env_file.write_text("LASTFM_USER=me\nSCROBBLER_DRY_RUN=false\n", encoding="utf-8")
    assert scrobbler.client.get("/api/settings").get_json()["SCROBBLER_DRY_RUN"] is False


@pytest.mark.parametrize(
    ("submitted", "accepted"),
    [
        ({"SCROBBLER_POLL_MINUTES": "2", "SCROBBLER_IDLE_MINUTES": "15"}, True),
        ({"SCROBBLER_POLL_MINUTES": "2", "SCROBBLER_IDLE_MINUTES": "5"}, True),
        ({"SCROBBLER_POLL_MINUTES": "5", "SCROBBLER_IDLE_MINUTES": "5"}, True),
        ({"SCROBBLER_POLL_MINUTES": "5", "SCROBBLER_IDLE_MINUTES": "3"}, False),
        ({"SCROBBLER_IDLE_MINUTES": "61"}, False),
        ({"SCROBBLER_IDLE_MINUTES": "7.5"}, False),
        ({"SCROBBLER_POLL_MINUTES": "0"}, False),
        ({"SCROBBLER_POLL_MINUTES": "", "SCROBBLER_IDLE_MINUTES": ""}, True),
    ],
)
def test_poll_intervals_are_validated_when_saved(scrobbler, submitted, accepted):
    response = scrobbler.client.post("/api/settings", json=submitted)
    assert (response.status_code == 200) is accepted
    stored = env_values(scrobbler.env_file)
    if accepted:
        assert all(stored.get(key) == value for key, value in submitted.items())
    else:
        assert "minutes" in response.get_json()["error"]
        assert not set(submitted) & set(stored)


def test_raising_the_fastest_interval_above_the_saved_idle_one_is_refused(scrobbler):
    scrobbler.env_file.write_text("LASTFM_USER=me\nSCROBBLER_IDLE_MINUTES=5\n", encoding="utf-8")
    response = scrobbler.client.post("/api/settings", json={"SCROBBLER_POLL_MINUTES": "10"})
    assert response.status_code == 400
    assert "(10)" in response.get_json()["error"]


def test_missing_deferral_setting_reads_as_on_and_saving_it_reschedules(scrobbler):
    scrobbler.env_file.write_text("LASTFM_USER=me\nSCROBBLER_ENABLED=true\n", encoding="utf-8")
    assert scrobbler.client.get("/api/settings").get_json()["SCROBBLER_DEFER_TO_REALTIME"] is True
    scrobbler.client.post("/api/settings", json={"SCROBBLER_DEFER_TO_REALTIME": False})
    assert env_values(scrobbler.env_file)["SCROBBLER_DEFER_TO_REALTIME"] == "false"
    assert scrobbler.client.get("/api/settings").get_json()["SCROBBLER_DEFER_TO_REALTIME"] is False
    assert scrobbler.configured == [True]


def test_saving_scrobbler_settings_reschedules_the_poll(scrobbler):
    scrobbler.client.post("/api/settings", json={"SCROBBLER_POLL_MINUTES": "10"})
    assert scrobbler.configured == [True]
    scrobbler.client.post("/api/settings", json={"LIMIT": "50"})
    assert scrobbler.configured == [True]


def scrobbler_tab(page):
    return re.search(r"<button[^>]*id=\"scrobblerTab\"[^>]*>", page).group(0)


def test_dashboard_shows_the_tab_only_when_enabled(scrobbler, monkeypatch):
    from web.services import data

    monkeypatch.setattr(data, "_get_settings", scrobbler.load_settings)
    assert "hidden" not in scrobbler_tab(scrobbler.client.get("/").get_data(as_text=True))
    scrobbler.env_file.write_text("LASTFM_USER=me\nSCROBBLER_ENABLED=false\n", encoding="utf-8")
    assert "hidden" in scrobbler_tab(scrobbler.client.get("/").get_data(as_text=True))


def test_poll_failure_is_notified_once_through_dashboard_and_webhooks(scrobbler, monkeypatch):
    from web.services import notifications

    sent = []
    monkeypatch.setattr(scrobbler.service, "fire_webhook", lambda _settings, **kwargs: sent.append(kwargs))

    def broken_history():
        raise RuntimeError("cookie expired")

    monkeypatch.setattr(scrobbler.service, "history_reader", lambda _settings: broken_history)
    settings = scrobbler.load_settings()
    first = scrobbler.service.poll_now(settings)
    second = scrobbler.service.poll_now(settings)
    assert first.error_kind == "history"
    assert first.notify
    assert not second.notify
    stored = notifications.list_all()["notifications"]
    assert len(stored) == 1
    assert stored[0]["source"] == "scrobbler"
    assert "cookie expired" in stored[0]["message"]
    assert len(sent) == 1
    assert (sent[0]["status"], sent[0]["sync_type"]) == ("error", "scrobbler")


def test_poll_now_does_nothing_when_disabled_or_busy(scrobbler):
    settings = scrobbler.load_settings()
    assert scrobbler.service.poll_now(dataclasses.replace(settings, scrobbler_enabled=False)) is None
    with scrobbler.service._poll_lock:
        assert scrobbler.service.poll_now(settings) is None
        assert scrobbler.client.post("/api/scrobbler/poll").status_code == 409


def test_status_creates_no_database_while_disabled(scrobbler):
    scrobbler.env_file.write_text("LASTFM_USER=me\nLASTFM_API_KEY=KEY\n", encoding="utf-8")
    body = scrobbler.client.get("/api/scrobbler/status").get_json()
    assert body["enabled"] is False
    assert not scrobbler.db.exists()


def test_scrobbler_job_follows_the_settings(monkeypatch):
    pytest.importorskip("apscheduler")
    from web.services import data, scheduler

    current = {"value": Settings(lastfm_user="me", lastfm_api_key="KEY", scrobbler_enabled=True, scrobbler_poll_minutes=7)}
    asked = []
    monkeypatch.setattr(data, "load_settings", lambda **kwargs: asked.append(kwargs) or current["value"])
    try:
        assert scheduler.configure_scrobbler_job()
        job = scheduler.get_scheduler().get_job(scheduler.SCROBBLER_JOB_ID)
        assert job.trigger.interval.total_seconds() == 7 * 60
        assert scheduler.scrobbler_next_poll() is not None
        assert asked == [{"fresh": True}]
        current["value"] = None
        assert scheduler.configure_scrobbler_job()
        assert scheduler.get_scheduler().get_job(scheduler.SCROBBLER_JOB_ID) is None
        assert scheduler.scrobbler_next_poll() is None
    finally:
        scheduler.stop_scheduler()


def test_scheduled_ticks_poll_only_when_pacing_says_so(scrobbler, monkeypatch):
    from src.scrobbler.history import HistoryItem

    rows = [HistoryItem(video_id="a", title="Song", artists=("Artist",), duration=200, played="Today")]
    monkeypatch.setattr(scrobbler.service, "history_reader", lambda _settings: lambda: (list(rows), 0))
    settings = scrobbler.load_settings()
    assert scrobbler.service.poll_if_due(settings) is not None
    assert scrobbler.service.poll_if_due(settings) is None
    assert scrobbler.service.poll_now(settings) is not None
    assert scrobbler.service.poll_if_due(dataclasses.replace(settings, scrobbler_enabled=False)) is None


def test_status_shows_the_pace_and_the_next_due_poll(scrobbler, monkeypatch):
    from datetime import UTC, datetime

    from src.scrobbler.history import HistoryItem

    rows = [HistoryItem(video_id="a", title="Song", artists=("Artist",), duration=200, played="Today")]
    monkeypatch.setattr(scrobbler.service, "history_reader", lambda _settings: lambda: (list(rows), 0))
    scrobbler.service.poll_now(scrobbler.load_settings())
    last = scrobbler.service.get_store(scrobbler.load_settings()).pacing_state()[0]
    tick = datetime.fromtimestamp(last + 30, UTC).isoformat()
    monkeypatch.setattr(scrobbler.routes, "scrobbler_next_poll", lambda: tick)
    body = scrobbler.client.get("/api/scrobbler/status").get_json()
    assert (body["pace"], body["pace_seconds"], body["idle_minutes"]) == ("idle", 600, 10)
    assert datetime.fromisoformat(body["next_poll"]).timestamp() == pytest.approx(last + 30 + 5 * 120)
    scrobbler.env_file.write_text("LASTFM_USER=me\nLASTFM_API_KEY=KEY\nSCROBBLER_ENABLED=true\nSCROBBLER_IDLE_MINUTES=15\n", encoding="utf-8")
    body = scrobbler.client.get("/api/scrobbler/status").get_json()
    assert (body["pace"], body["pace_seconds"], body["idle_minutes"]) == ("idle", 900, 15)
    assert datetime.fromisoformat(body["next_poll"]).timestamp() == pytest.approx(last + 30 + 8 * 120)


def test_auth_routes_report_an_env_file_that_cannot_be_written(scrobbler, monkeypatch):
    scrobbler.client.post("/api/scrobbler/auth/start", json={"api_secret": "SHH"})

    def read_only(_updates):
        raise OSError("read-only file system")

    monkeypatch.setattr(scrobbler.routes, "update_env_file", read_only)
    for path, body in (("start", {"api_secret": "NEW"}), ("finish", {"token": "TOKEN"}), ("disconnect", {})):
        resp = scrobbler.client.post(f"/api/scrobbler/auth/{path}", json=body)
        assert resp.status_code == 500
        assert resp.get_json()["error"]


@pytest.mark.parametrize(
    ("kind", "previous", "history_failed", "published"),
    [
        (ERROR_HISTORY_AUTH, "", True, [{"valid": False, "expired": True}]),
        (ERROR_HISTORY_AUTH, ERROR_HISTORY_AUTH, True, [{"valid": False, "expired": True}]),
        ("", ERROR_HISTORY_AUTH, False, [{"valid": True}]),
        (ERROR_LASTFM_UNAVAILABLE, ERROR_HISTORY_AUTH, False, [{"valid": True}]),
        (ERROR_HISTORY, ERROR_HISTORY_AUTH, True, []),
        ("", "", False, []),
    ],
)
def test_polls_publish_the_youtube_music_session_state(scrobbler, monkeypatch, kind, previous, history_failed, published):
    from src.scrobbler.service import Poller

    outcome = PollOutcome(error_kind=kind, previous_error_kind=previous, history_failed=history_failed)
    monkeypatch.setattr(Poller, "run", lambda _self: outcome)
    events = []
    monkeypatch.setattr(scrobbler.service.bus, "publish", lambda event, data=None: events.append((event, data)))
    monkeypatch.setattr(scrobbler.service, "notify_failure", lambda *_args: None)
    assert scrobbler.service.poll_now(scrobbler.load_settings()) is outcome
    assert [data for event, data in events if event == "auth_status"] == published


def test_an_expired_session_found_by_a_poll_lasts_until_the_auth_file_is_replaced(scrobbler, monkeypatch, tmp_path):
    from src.scrobbler.history import HistorySignedOut
    from src.scrobbler.service import Poller
    from web.routes import events

    def signed_out():
        raise HistorySignedOut

    settings = scrobbler.load_settings()
    auth = tmp_path / "browser.json"
    auth.write_text('{"cookie": "SAPISID=x"}', encoding="utf-8")
    os.utime(auth, (1_000, 1_000))
    Poller(settings, scrobbler.service.get_store(settings), signed_out, scrobbler.fake, now=lambda: 2_000.0).run()
    monkeypatch.setattr(events, "load_settings", scrobbler.load_settings)

    assert scrobbler.service.youtube_session_expired(settings)
    assert scrobbler.client.get("/api/scrobbler/status").get_json()["youtube_session_expired"] is True
    assert events._snapshot()["auth_status"] == {"valid": False, "expired": True}

    os.utime(auth, (3_000, 3_000))
    assert not scrobbler.service.youtube_session_expired(settings)
    assert scrobbler.client.get("/api/scrobbler/status").get_json()["youtube_session_expired"] is False
    assert "auth_status" not in events._snapshot()
