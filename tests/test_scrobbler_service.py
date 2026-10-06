import dataclasses

import pytest
from ytmusicapi.exceptions import YTMusicServerError

from src.config import Settings
from src.lastfm.client import (
    HttpResponse,
    LastfmAuthError,
    LastfmClient,
    LastfmError,
    LastfmTooManyScrobbles,
    LastfmUnavailable,
    NowPlaying,
    ScrobbleOutcome,
)
from src.lastfm.scrobble import Scrobble
from src.scrobbler.history import HistoryItem, HistorySignedOut, fetch_history, history_reader
from src.scrobbler.played import Rules
from src.scrobbler.service import (
    ERROR_ACCOUNT_MISMATCH,
    ERROR_DAILY_LIMIT,
    ERROR_HISTORY,
    ERROR_HISTORY_AUTH,
    ERROR_LASTFM_AUTH,
    ERROR_LASTFM_UNAVAILABLE,
    ERROR_NOT_CONNECTED,
    ERROR_SCROBBLE_FAILED,
    MAX_RANGE_SECONDS,
    MAX_SCROBBLE_AGE_SECONDS,
    SIGNED_OUT_MESSAGE,
    Poller,
    group_ranges,
    oldest_accepted_timestamp,
)
from src.scrobbler.store import FAILED, PENDING, SCROBBLED, SENDING, SKIPPED, WOULD_SCROBBLE, ScrobblerStore

pytestmark = pytest.mark.usefixtures("no_network")

T0 = 1_700_000_000
POLL = 300
CONFIRM = 10


class FakeLastfm:
    """Stands in for LastfmClient: serves recent scrobbles and records what would be sent."""

    def __init__(self):
        self.scrobbles = []
        self.playing = None
        self.read_error = None
        self.send_error = None
        self.ignore = {}
        self.batches = []
        self.reads = 0
        self.users = set()
        self.clock = None
        self.max_range = None
        self.ranges = []

    def recent_scrobbles(self, username, from_ts, to_ts=None):
        self.reads += 1
        self.users.add(username)
        if self.read_error:
            raise self.read_error
        end = self.clock() if to_ts is None else to_ts
        self.ranges.append((from_ts, end))
        if self.max_range is not None and end - from_ts > self.max_range:
            raise LastfmTooManyScrobbles("too many pages")
        return [s for s in sorted(self.scrobbles, key=lambda s: -s.ts) if from_ts <= s.ts <= end]

    def now_playing(self, username):
        self.users.add(username)
        if self.read_error:
            raise self.read_error
        return self.playing

    def scrobble_batch(self, entries):
        self.batches.append(list(entries))
        if self.send_error:
            raise self.send_error
        outcomes = []
        for entry in entries:
            code = self.ignore.get(entry.track, 0)
            if code == 0:
                self.scrobbles.append(Scrobble(entry.artist, entry.track, entry.album, entry.timestamp))
            outcomes.append(ScrobbleOutcome(code == 0, code, "ignored" if code else "", entry.artist, entry.track))
        return outcomes


class History:
    def __init__(self, *ids):
        self.rows = [song(v) for v in ids]
        self.error = None

    def set(self, *rows):
        self.rows = [r if isinstance(r, HistoryItem) else song(r) for r in rows]

    def __call__(self):
        if self.error:
            raise self.error
        return list(self.rows), 0


def song(video_id, duration=200, played="Today", **kwargs):
    defaults = {"title": f"Song {video_id}", "artists": ("Artist",)}
    defaults.update(kwargs)
    return HistoryItem(video_id=video_id, duration=duration, played=played, **defaults)


class Clock:
    def __init__(self, t=T0 - POLL):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, seconds=POLL):
        self.t += seconds


def settings(**overrides):
    base = {
        "lastfm_user": "me",
        "lastfm_api_key": "KEY",
        "lastfm_api_secret": "SECRET",
        "lastfm_session_key": "SK",
        "lastfm_session_user": "me",
        "scrobbler_enabled": True,
        "scrobbler_dry_run": True,
        "scrobbler_defer_to_realtime": False,
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def env(tmp_path):
    """A store, a history and a fake Last.fm; the clock starts one poll before T0.

    The rules are pinned: a play whose end is unknown counts, so the newest
    play of a test is decided once it has been on top longer than it lasts.
    Deferring to real-time scrobblers is off unless a test turns it on, so the
    duplicate check sees the real-time scrobbles.
    """
    store = ScrobblerStore(tmp_path / "scrobbler.db")
    history = History("a", "b", "c")
    lastfm = FakeLastfm()
    clock = Clock()

    class Env:
        pass

    e = Env()
    e.store, e.history, e.lastfm, e.clock, e.path = store, history, lastfm, clock, tmp_path / "scrobbler.db"
    lastfm.clock = clock
    e.rules = Rules(end_unknown="count", timing_unknown="count")

    def poll(**overrides):
        return Poller(settings(**overrides), e.store, e.history, e.lastfm, now=e.clock, rules=e.rules).run()

    e.poll = poll
    return e


def plays(store, *statuses):
    rows, _ = store.list_plays(statuses=list(statuses) or None, limit=500)
    return rows


def start(env, **overrides):
    """Two polls of the same list; the second one, at T0, confirms it as the baseline."""
    env.poll(**overrides)
    env.clock.advance()
    return env.poll(**overrides)


def show(env, *top, **overrides):
    """Put ``top`` above the baseline rows and poll once: the new rows wait for confirmation."""
    env.history.set(*top, "a", "b", "c")
    return env.poll(**overrides)


def baseline_then(env, *top, settle=True, **overrides):
    """Baseline at T0 and ``top`` seen at T0 + POLL, then the confirming poll.

    With ``settle`` it comes a poll later, when the newest play has been on
    top longer than it lasts and is decided; without, right away, so the plays
    are recorded but not yet due.
    """
    start(env, **overrides)
    env.clock.advance()
    show(env, *top, **overrides)
    env.clock.advance(POLL if settle else CONFIRM)
    return env.poll(**overrides)


def test_first_list_becomes_the_baseline_once_a_second_poll_confirms_it(env):
    first = env.poll()
    assert first.status == "baseline"
    assert env.store.load_snapshot() == (None, None)
    env.clock.advance()
    second = env.poll()
    assert (second.status, second.new_plays) == ("baseline", 0)
    snapshot, observed = env.store.load_snapshot()
    assert [e.video_id for e in snapshot] == ["a", "b", "c"]
    assert observed == T0
    assert plays(env.store) == []
    assert env.lastfm.reads == 0


def test_new_play_is_recorded_once_confirmed_and_waits_before_a_decision(env):
    start(env)
    env.clock.advance()
    seen = show(env, "x")
    assert seen.new_plays == 0
    assert plays(env.store) == []
    env.clock.advance(CONFIRM)
    confirmed = env.poll()
    assert (confirmed.new_plays, confirmed.pending) == (1, 1)
    assert env.lastfm.reads == 0
    (row,) = plays(env.store)
    assert row["status"] == PENDING
    assert (row["window_start"], row["detected_at"], row["timestamp"]) == (T0, T0 + POLL, T0 + POLL // 2)


def test_a_row_moved_up_for_one_poll_is_a_flicker_and_records_nothing(env):
    start(env)
    env.clock.advance()
    env.history.set("c", "a", "b")
    env.poll()
    env.clock.advance()
    env.history.set("a", "b", "c")
    outcome = env.poll()
    assert outcome.status == "flicker"
    assert plays(env.store) == []
    env.clock.advance()
    env.poll()
    assert plays(env.store) == []


def test_dry_run_records_would_scrobble_without_sending(env):
    outcome = baseline_then(env, "x")
    assert outcome.would_scrobble == 1
    assert env.lastfm.batches == []
    assert env.lastfm.users == {"me"}
    (row,) = plays(env.store)
    assert row["status"] == WOULD_SCROBBLE
    assert row["dry_run"]
    assert row["detail"]["window"] == 200 + POLL
    assert row["detail"]["uncertainty"] == POLL // 2
    assert (row["certainty"], row["detail"]["played"]["basis"]) == ("estimated", "end_unknown")


def test_play_already_scrobbled_in_real_time_is_skipped_as_duplicate(env):
    env.lastfm.scrobbles.append(Scrobble("Artist", "Song x", "Other Album", T0 + 100))
    outcome = baseline_then(env, "x")
    assert outcome.skipped == 1
    (row,) = plays(env.store)
    assert row["status"] == SKIPPED
    assert row["reason"] == "duplicate"
    assert row["detail"]["duplicate_of"]["timestamp"] == T0 + 100
    assert row["detail"]["duplicate_of"]["distance"] == 50


def test_now_playing_track_counts_as_a_duplicate(env):
    start(env)
    env.clock.advance()
    show(env, song("x", duration=900))
    env.clock.advance(CONFIRM)
    env.poll()
    env.clock.advance(900 + 30 + 60)
    env.lastfm.playing = NowPlaying("Artist", "Song x", "")
    env.poll()
    (row,) = plays(env.store)
    assert row["reason"] == "duplicate"
    assert row["detail"]["duplicate_of"]["now_playing"] is True


def test_near_miss_is_recorded_but_the_play_is_still_scrobbled(env):
    env.lastfm.scrobbles.append(Scrobble("Artist", "Song x (Live)", "", T0 + 150))
    baseline_then(env, "x")
    (row,) = plays(env.store)
    assert row["status"] == WOULD_SCROBBLE
    assert row["detail"]["near_miss"]["reason"] == "version_differs"


def test_lastfm_unreachable_keeps_plays_pending_and_notifies_once(env):
    env.lastfm.read_error = LastfmUnavailable("down")
    outcome = baseline_then(env, "x")
    assert outcome.error_kind == ERROR_LASTFM_UNAVAILABLE
    assert outcome.notify
    assert outcome.pending == 1
    assert env.lastfm.batches == []
    env.clock.advance()
    again = env.poll()
    assert again.error_kind == ERROR_LASTFM_UNAVAILABLE
    assert not again.notify
    env.lastfm.read_error = None
    env.clock.advance()
    recovered = env.poll()
    assert recovered.error_kind == ""
    assert recovered.would_scrobble == 1


def test_lastfm_unreachable_in_live_mode_sends_nothing(env):
    env.lastfm.read_error = LastfmUnavailable("down")
    baseline_then(env, "x", scrobbler_dry_run=False)
    assert env.lastfm.batches == []
    assert plays(env.store)[0]["status"] == PENDING


def test_live_mode_scrobbles_and_keeps_a_ledger(env):
    start(env, scrobbler_dry_run=False)
    env.clock.advance()
    show(env, "y", scrobbler_dry_run=False)
    env.clock.advance()
    first = show(env, "x", "y", scrobbler_dry_run=False)
    env.clock.advance()
    second = env.poll(scrobbler_dry_run=False)
    assert first.scrobbled + second.scrobbled == 2
    sent = [e for batch in env.lastfm.batches for e in batch]
    assert [e.track for e in sent] == ["Song y", "Song x"]
    assert sent[0].timestamp < sent[1].timestamp
    rows = plays(env.store, SCROBBLED)
    assert {r["lastfm_title"] for r in rows} == {"Song x", "Song y"}
    assert [p.title for p in env.store.own_scrobbles_since(0)] == ["Song y", "Song x"]


def test_two_plays_in_one_window_get_an_estimated_decision(env):
    baseline_then(env, "x", "y")
    rows = {r["video_id"]: r for r in plays(env.store)}
    older = rows["y"]
    assert older["certainty"] == "estimated"
    assert (older["listen_lo"], older["listen_hi"], older["listen_threshold"]) == (0, 200, 100)
    assert older["status"] == SKIPPED
    assert older["reason"] == "listened_too_little"
    assert older["detail"]["played"]["estimate"] < 0.5
    newest = rows["x"]
    assert (newest["status"], newest["certainty"], newest["basis"]) == (WOULD_SCROBBLE, "estimated", "end_unknown")


def test_newest_play_waits_while_it_could_still_be_playing(env):
    start(env)
    env.clock.advance(120)
    show(env, song("long", duration=600))
    env.clock.advance(CONFIRM)
    env.poll()
    env.clock.advance(670)
    env.poll()
    assert plays(env.store)[0]["status"] == PENDING
    env.clock.advance(20)
    env.poll()
    row = plays(env.store)[0]
    assert (row["status"], row["certainty"], row["basis"]) == (WOULD_SCROBBLE, "estimated", "end_unknown")


def test_play_followed_by_the_next_one_in_time_is_a_certain_play(env):
    start(env)
    env.clock.advance(60)
    show(env, "x")
    env.clock.advance(60)
    env.poll()
    env.clock.advance(60)
    env.poll()
    env.clock.advance(60)
    env.history.set("y", "x", "a", "b", "c")
    env.poll()
    env.clock.advance(60)
    env.poll()
    row = next(r for r in plays(env.store) if r["video_id"] == "x")
    assert (row["status"], row["certainty"], row["basis"]) == (WOULD_SCROBBLE, "certain", "bounds")
    assert (row["listen_lo"], row["listen_hi"]) == (120, 200)


def test_next_play_after_a_long_gap_leaves_the_end_unknown(env):
    start(env)
    env.clock.advance(60)
    show(env, "x")
    env.clock.advance(60)
    env.poll()
    env.clock.advance(1200)
    env.poll()
    env.clock.advance(60)
    env.history.set("y", "x", "a", "b", "c")
    env.poll()
    row = next(r for r in plays(env.store) if r["video_id"] == "x")
    assert (row["certainty"], row["basis"]) == ("estimated", "end_unknown")


def test_plays_found_after_a_long_gap_are_laid_back_to_back_and_checked_against_a_day(env):
    env.lastfm.scrobbles.append(Scrobble("Artist", "Song x", "", T0 - 12 * 3600))
    start(env)
    env.clock.advance(2 * 3600)
    show(env, "x", "y")
    env.clock.advance(CONFIRM)
    env.poll()
    env.clock.advance(60)
    env.poll()
    rows = {r["video_id"]: r for r in plays(env.store)}
    seen = T0 + 2 * 3600
    assert (rows["y"]["timestamp"], rows["x"]["timestamp"]) == (seen - 400, seen - 200)
    assert rows["x"]["basis"] == rows["y"]["basis"] == "timing_unknown"
    assert rows["y"]["status"] == WOULD_SCROBBLE
    assert (rows["x"]["status"], rows["x"]["reason"]) == (SKIPPED, "duplicate")
    assert rows["x"]["detail"]["window"] >= 24 * 3600


def test_play_replaced_within_a_short_window_is_a_certain_skip(env):
    start(env)
    env.clock.advance(60)
    env.history.set(song("x", duration=400), "a", "b", "c")
    env.poll()
    env.clock.advance(60)
    env.history.set("y", song("x", duration=400), "a", "b", "c")
    env.poll()
    env.clock.advance(60)
    env.poll()
    row = next(r for r in plays(env.store) if r["video_id"] == "x")
    assert (row["status"], row["reason"], row["certainty"]) == (SKIPPED, "listened_too_little", "certain")
    assert row["listen_hi"] == 120
    assert env.lastfm.reads == 0


def test_a_detected_play_is_never_scrobbled_twice(env):
    baseline_then(env, "x", scrobbler_dry_run=False)
    for _ in range(3):
        env.clock.advance()
        env.poll(scrobbler_dry_run=False)
    assert sum(len(b) for b in env.lastfm.batches) == 1


def test_own_earlier_scrobble_does_not_hide_a_real_replay(env):
    baseline_then(env, "x", scrobbler_dry_run=False)
    env.clock.advance()
    env.history.set("y", "x", "a", "b", "c")
    env.poll(scrobbler_dry_run=False)
    env.clock.advance()
    env.history.set("x", "y", "a", "b", "c")
    env.poll(scrobbler_dry_run=False)
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    sent = [e.track for batch in env.lastfm.batches for e in batch]
    assert sent == ["Song x", "Song y", "Song x"]


def test_restart_between_polls_neither_loses_nor_repeats_plays(env):
    start(env, scrobbler_dry_run=False)
    env.clock.advance()
    show(env, "x", scrobbler_dry_run=False)
    env.store.close()

    def restart_and_poll():
        store = ScrobblerStore(env.path)
        outcome = Poller(settings(scrobbler_dry_run=False), store, env.history, env.lastfm, now=env.clock, rules=env.rules).run()
        rows = plays(store)
        store.close()
        return outcome, rows

    env.clock.advance(CONFIRM)
    confirmed, rows = restart_and_poll()
    assert confirmed.new_plays == 1
    ((row),) = rows
    assert (row["window_start"], row["timestamp"], row["status"]) == (T0, T0 + POLL // 2, PENDING)

    env.clock.advance()
    decided, _rows = restart_and_poll()
    assert (decided.new_plays, decided.scrobbled) == (0, 1)
    env.clock.advance()
    later, _rows = restart_and_poll()
    assert (later.new_plays, later.scrobbled) == (0, 0)
    assert sum(len(b) for b in env.lastfm.batches) == 1


def test_scrobbles_go_out_in_batches_of_fifty(env):
    env.history.set("a")
    start(env, scrobbler_dry_run=False)
    env.clock.advance(12 * 3600)
    env.history.set(*[f"n{i}" for i in range(120)], "a")
    first = env.poll(scrobbler_dry_run=False)
    assert first.new_plays == 0
    env.clock.advance()
    second = env.poll(scrobbler_dry_run=False)
    assert (second.new_plays, second.scrobbled) == (120, 120)
    assert [len(b) for b in env.lastfm.batches] == [50, 50, 20]
    assert len(plays(env.store, SCROBBLED)) == 120


def test_unanswered_batch_is_checked_before_it_is_sent_again(env):
    baseline_then(env, "x", settle=False, scrobbler_dry_run=False)
    env.lastfm.send_error = LastfmUnavailable("timeout")
    env.clock.advance()
    outcome = env.poll(scrobbler_dry_run=False)
    assert outcome.error_kind == ERROR_LASTFM_UNAVAILABLE
    assert plays(env.store)[0]["status"] == SENDING

    env.lastfm.send_error = None
    row = plays(env.store)[0]
    env.lastfm.scrobbles.append(Scrobble("Artist", "Song x", "", row["timestamp"]))
    env.clock.advance()
    recovered = env.poll(scrobbler_dry_run=False)
    assert recovered.scrobbled == 1
    assert plays(env.store)[0]["reason"] == "recovered"
    assert len(env.lastfm.batches) == 1


def test_unanswered_batch_that_never_landed_is_sent_again(env):
    baseline_then(env, "x", settle=False, scrobbler_dry_run=False)
    env.lastfm.send_error = LastfmUnavailable("timeout")
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    env.lastfm.send_error = None
    env.clock.advance()
    outcome = env.poll(scrobbler_dry_run=False)
    assert outcome.scrobbled == 1
    assert len(env.lastfm.batches) == 2
    assert plays(env.store)[0]["status"] == SCROBBLED


def test_revoked_session_puts_plays_back_and_reports_auth(env):
    env.lastfm.send_error = LastfmAuthError("Invalid session key", 9)
    outcome = baseline_then(env, "x", scrobbler_dry_run=False)
    assert outcome.error_kind == ERROR_LASTFM_AUTH
    assert plays(env.store)[0]["status"] == PENDING


def test_rejected_batch_is_marked_failed(env):
    env.lastfm.send_error = LastfmError("Invalid parameters", 6)
    outcome = baseline_then(env, "x", scrobbler_dry_run=False)
    assert outcome.error_kind == ERROR_SCROBBLE_FAILED
    assert outcome.failed == 1
    row = plays(env.store)[0]
    assert row["status"] == FAILED
    assert "Invalid parameters" in row["detail"]["error"]


def test_lastfm_ignored_scrobble_is_skipped_with_its_code(env):
    env.lastfm.ignore["Song x"] = 2
    baseline_then(env, "x", scrobbler_dry_run=False)
    row = plays(env.store)[0]
    assert (row["status"], row["reason"]) == (SKIPPED, "ignored_by_lastfm")
    assert row["detail"]["ignored"]["code"] == 2


def test_daily_limit_keeps_the_play_for_later(env):
    env.lastfm.ignore["Song x"] = 5
    outcome = baseline_then(env, "x", scrobbler_dry_run=False)
    assert outcome.error_kind == ERROR_DAILY_LIMIT
    assert plays(env.store)[0]["status"] == PENDING


def test_live_mode_without_session_waits_and_says_why(env):
    outcome = baseline_then(env, "x", scrobbler_dry_run=False, lastfm_session_key="")
    assert outcome.error_kind == ERROR_NOT_CONNECTED
    assert plays(env.store)[0]["status"] == PENDING
    assert env.lastfm.reads == 0


def test_live_mode_refuses_a_session_of_another_account(env):
    outcome = baseline_then(env, "x", scrobbler_dry_run=False, lastfm_session_user="someone-else")
    assert outcome.error_kind == ERROR_ACCOUNT_MISMATCH
    assert env.lastfm.batches == []


def test_dry_run_needs_no_session(env):
    outcome = baseline_then(env, "x", lastfm_session_key="", lastfm_api_secret="")
    assert outcome.would_scrobble == 1


def test_plays_older_than_lastfm_accepts_are_skipped(env):
    env.lastfm.read_error = LastfmUnavailable("down")
    baseline_then(env, "x")
    env.clock.advance(MAX_SCROBBLE_AGE_SECONDS)
    outcome = env.poll()
    row = plays(env.store)[0]
    assert (row["status"], row["reason"]) == (SKIPPED, "too_old")
    assert outcome.skipped == 1


def test_short_tracks_and_podcasts_are_skipped_at_detection(env):
    start(env)
    env.clock.advance()
    show(env, song("s", duration=25), song("p", video_type="MUSIC_VIDEO_TYPE_PODCAST_EPISODE"))
    env.clock.advance(CONFIRM)
    outcome = env.poll()
    reasons = {r["video_id"]: r["reason"] for r in plays(env.store)}
    assert reasons == {"s": "too_short", "p": "not_music"}
    assert outcome.skipped == 2


def test_history_failure_is_reported_and_keeps_the_snapshot(env):
    start(env)
    env.history.error = RuntimeError("cookie expired")
    env.clock.advance()
    outcome = env.poll()
    assert outcome.error_kind == ERROR_HISTORY
    assert outcome.notify
    snapshot, taken = env.store.load_snapshot()
    assert [e.video_id for e in snapshot] == ["a", "b", "c"]
    assert taken == T0


def test_history_with_nothing_in_common_resets_without_plays(env):
    start(env)
    env.clock.advance()
    env.history.set("p", "q")
    assert env.poll().status == "reset"
    assert [e.video_id for e in env.store.load_snapshot()[0]] == ["a", "b", "c"]
    env.clock.advance()
    outcome = env.poll()
    assert outcome.status == "reset"
    assert [e.video_id for e in env.store.load_snapshot()[0]] == ["p", "q"]
    assert plays(env.store) == []


def test_poll_is_recorded_for_the_dashboard(env):
    baseline_then(env, "x")
    last = env.store.last_poll()
    assert last["status"] == "ok"
    assert last["would_scrobble"] == 1
    assert last["history_rows"] == 4


def test_real_client_end_to_end_with_a_fake_transport(env):
    sent = []

    def transport(http_method, params):
        if params["method"] == "user.getRecentTracks":
            return HttpResponse(200, {"recenttracks": {"track": [], "@attr": {"totalPages": "0"}}})
        sent.append((http_method, dict(params)))
        item = {
            "artist": {"#text": params["artist[0]"]},
            "track": {"#text": params["track[0]"]},
            "ignoredMessage": {"code": "0", "#text": ""},
        }
        return HttpResponse(200, {"scrobbles": {"scrobble": item}})

    real = LastfmClient("KEY", "SECRET", "SK", transport=transport, sleep=lambda _s: None)
    env.lastfm = real
    outcome = baseline_then(env, "x", scrobbler_dry_run=False)
    assert outcome.scrobbled == 1
    (call,) = sent
    assert call[0] == "POST"
    assert call[1]["method"] == "track.scrobble"
    assert call[1]["artist[0]"] == "Artist"
    assert "api_sig" in call[1]


def test_settings_repr_hides_secrets():
    text = repr(dataclasses.replace(settings(), lastfm_api_secret="TOPSECRET", lastfm_session_key="SESSIONKEY"))
    assert "TOPSECRET" not in text
    assert "SESSIONKEY" not in text


def _replay_after_a_desktop_play(env, *, via_now_playing):
    start(env)
    env.clock.advance()
    if via_now_playing:
        env.lastfm.playing = NowPlaying("Artist", "Song s", "")
    else:
        env.lastfm.scrobbles.append(Scrobble("Artist", "Song s", "", T0 + 290))
    show(env, "s")
    env.clock.advance(CONFIRM)
    env.poll()
    env.clock.advance()
    env.poll()
    first = plays(env.store)[0]
    assert first["reason"] == "duplicate"
    if via_now_playing:
        env.lastfm.playing = None
        env.lastfm.scrobbles.append(Scrobble("Artist", "Song s", "", T0 + 290))
    env.clock.advance(2 * POLL)
    show(env, "s", "y")
    env.clock.advance()
    env.poll()
    return {(r["video_id"], r["id"]): r for r in plays(env.store)}


def test_a_real_time_scrobble_covers_one_play_only_across_polls(env):
    rows = _replay_after_a_desktop_play(env, via_now_playing=False)
    replay = max((r for (vid, _), r in rows.items() if vid == "s"), key=lambda r: r["id"])
    assert replay["status"] == WOULD_SCROBBLE
    assert "duplicate_of" not in replay["detail"]


def test_a_now_playing_match_claims_the_scrobble_it_became(env):
    rows = _replay_after_a_desktop_play(env, via_now_playing=True)
    replay = max((r for (vid, _), r in rows.items() if vid == "s"), key=lambda r: r["id"])
    assert replay["status"] == WOULD_SCROBBLE


def test_a_play_with_a_huge_window_does_not_hold_up_the_others(env):
    env.lastfm.max_range = 2 * 24 * 3600
    start(env)
    env.clock.advance(3 * 24 * 3600)
    show(env, "w")
    env.clock.advance(CONFIRM)
    env.poll()
    env.clock.advance(60)
    show(env, "n", "w")
    env.clock.advance(POLL)
    outcome = env.poll()
    decisions = {r["video_id"]: (r["status"], r["reason"]) for r in plays(env.store)}
    assert decisions == {"w": (SKIPPED, "too_many_scrobbles"), "n": (WOULD_SCROBBLE, "")}
    assert outcome.error_kind == ""


def test_only_one_poll_runs_at_a_time_across_processes(env):
    start(env)
    other = ScrobblerStore(env.path)
    with other.exclusive() as owned:
        assert owned
        env.clock.advance()
        env.history.set("x", "a", "b", "c")
        outcome = env.poll()
    assert outcome.status == "busy"
    assert plays(env.store) == []
    assert env.store.last_poll()["finished_at"] == T0
    other.close()


def test_unanswered_play_is_recovered_when_lastfm_corrected_its_title(env):
    baseline_then(env, "x", settle=False, scrobbler_dry_run=False)
    env.lastfm.send_error = LastfmUnavailable("timeout")
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    env.lastfm.send_error = None
    row = plays(env.store)[0]
    env.lastfm.scrobbles.append(Scrobble("Artist", "Song Ex", "", row["timestamp"]))
    env.clock.advance()
    outcome = env.poll(scrobbler_dry_run=False)
    assert outcome.scrobbled == 1
    assert plays(env.store)[0]["reason"] == "recovered"
    assert len(env.lastfm.batches) == 1


def test_store_adds_new_columns_to_an_older_database(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """CREATE TABLE schema_version (version INTEGER NOT NULL);
        INSERT INTO schema_version VALUES (1);
        CREATE TABLE plays (id INTEGER PRIMARY KEY AUTOINCREMENT, poll_id INTEGER, video_id TEXT NOT NULL, artist TEXT NOT NULL,
            title TEXT NOT NULL, artists TEXT NOT NULL DEFAULT '[]', album TEXT NOT NULL DEFAULT '', duration INTEGER,
            played TEXT NOT NULL DEFAULT '', replay INTEGER NOT NULL DEFAULT 0, detected_at REAL NOT NULL, window_start REAL NOT NULL,
            timestamp INTEGER NOT NULL, earliest INTEGER NOT NULL, latest INTEGER NOT NULL, status TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '{}', dry_run INTEGER NOT NULL DEFAULT 1,
            attempts INTEGER NOT NULL DEFAULT 0, decided_at REAL, lastfm_artist TEXT NOT NULL DEFAULT '', lastfm_title TEXT NOT NULL DEFAULT '');"""
    )
    conn.close()
    store = ScrobblerStore(path)
    columns = {row[1] for row in sqlite3.connect(path).execute("PRAGMA table_info(plays)")}
    assert {"listen_lo", "listen_hi", "certainty", "next_window_end", "window_count"} <= columns
    assert store.open_plays() == []


def record_dry_run_plays(env, *ids):
    """Baseline, then one new play per poll in dry run, and one more poll to decide the last one."""
    rows = ["a", "b", "c"]
    start(env)
    for video_id in ids:
        env.clock.advance()
        rows = [video_id, *[r for r in rows if r != video_id]]
        env.history.set(*rows)
        env.poll()
    env.clock.advance()
    env.poll()
    return rows


def offer(env):
    return env.store.dry_run_offer(oldest_accepted_timestamp(env.clock()))


def choose(env, send):
    return env.store.record_dry_run_choice(send, oldest_accepted_timestamp(env.clock()), env.clock())


def test_dry_run_plays_are_sent_once_the_user_chooses_to(env):
    record_dry_run_plays(env, "x", "y")
    assert {r["status"] for r in plays(env.store)} == {WOULD_SCROBBLE}
    assert offer(env) == (2, 0)
    assert choose(env, True) == (2, 0)
    assert {r["status"] for r in plays(env.store)} == {PENDING}
    env.clock.advance()
    outcome = env.poll(scrobbler_dry_run=False)
    assert outcome.scrobbled == 2
    assert [e.track for batch in env.lastfm.batches for e in batch] == ["Song x", "Song y"]
    assert {(r["status"], r["dry_run_choice"]) for r in plays(env.store)} == {(SCROBBLED, "send")}
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    assert sum(len(batch) for batch in env.lastfm.batches) == 2
    assert offer(env) == (0, 0)


def test_dry_run_plays_are_checked_for_duplicates_again_at_send_time(env):
    record_dry_run_plays(env, "x", "y")
    x = next(r for r in plays(env.store) if r["video_id"] == "x")
    env.lastfm.scrobbles.append(Scrobble("Artist", "Song x", "", x["timestamp"] + 30))
    choose(env, True)
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    rows = {r["video_id"]: r for r in plays(env.store)}
    assert (rows["x"]["status"], rows["x"]["reason"], rows["x"]["dry_run_choice"]) == (SKIPPED, "duplicate", "send")
    assert rows["y"]["status"] == SCROBBLED
    assert [e.track for batch in env.lastfm.batches for e in batch] == ["Song y"]


def test_only_plays_lastfm_still_accepts_are_queued(env):
    rows = record_dry_run_plays(env, "x")
    env.clock.advance(MAX_SCROBBLE_AGE_SECONDS)
    env.history.set("z", *rows)
    env.poll()
    env.clock.advance()
    env.poll()
    assert offer(env) == (1, 1)
    assert choose(env, True) == (1, 1)
    rows = {r["video_id"]: r for r in plays(env.store)}
    assert (rows["x"]["status"], rows["x"]["dry_run_choice"]) == (WOULD_SCROBBLE, "too_old")
    assert (rows["z"]["status"], rows["z"]["dry_run_choice"]) == (PENDING, "send")
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    assert [e.track for batch in env.lastfm.batches for e in batch] == ["Song z"]


def test_keeping_the_dry_run_plays_sends_nothing_and_is_asked_once(env):
    record_dry_run_plays(env, "x")
    assert choose(env, False) == (1, 0)
    env.clock.advance()
    env.poll(scrobbler_dry_run=False)
    assert env.lastfm.batches == []
    assert plays(env.store)[0]["dry_run_choice"] == "keep"
    assert plays(env.store)[0]["status"] == WOULD_SCROBBLE
    assert offer(env) == (0, 0)


def test_queued_dry_run_plays_go_out_in_batches(env):
    env.history.set("a")
    start(env)
    env.clock.advance(12 * 3600)
    env.history.set(*[f"n{i}" for i in range(60)], "a")
    env.poll()
    env.clock.advance()
    env.poll()
    assert offer(env) == (60, 0)
    choose(env, True)
    env.clock.advance()
    outcome = env.poll(scrobbler_dry_run=False)
    assert outcome.scrobbled == 60
    assert [len(batch) for batch in env.lastfm.batches] == [50, 10]


def test_plays_spread_over_days_are_checked_in_short_ranges(env):
    rows = ["a", "b", "c"]
    start(env)
    for day in range(10):
        env.clock.advance(24 * 3600)
        env.poll()
        env.clock.advance(POLL)
        rows = [f"d{day}", *rows]
        env.history.set(*rows)
        env.poll()
        env.clock.advance(POLL)
        env.poll()
    assert offer(env) == (10, 0)
    choose(env, True)
    env.lastfm.ranges.clear()
    env.clock.advance()
    outcome = env.poll(scrobbler_dry_run=False)
    assert outcome.scrobbled == 10
    assert len(env.lastfm.ranges) > 1
    assert all(end - start <= MAX_RANGE_SECONDS for start, end in env.lastfm.ranges)


def test_group_ranges_merges_overlaps_within_the_span():
    a, b, c, d = object(), object(), object(), object()
    groups = group_ranges([((0, 100), a), ((50, 150), b), ((400, 500), c), ((450, 2000), d)], 1000)
    assert groups == [((0, 150), [a, b]), ((400, 500), [c]), ((450, 2000), [d])]
    assert group_ranges([((400, 500), c), ((450, 2000), d)], None) == [((400, 2000), [c, d])]


def test_uploads_use_the_artist_from_their_title_or_are_skipped(env):
    start(env)
    env.clock.advance()
    good = song("u1", title="Real Artist - Song (Lyrics)", artists=("Lyrics Channel",), video_type="MUSIC_VIDEO_TYPE_UGC")
    bad = song("u2", title="Song (Lyrics)", artists=("Lyrics Channel",), video_type="MUSIC_VIDEO_TYPE_UGC")
    show(env, bad, good)
    env.clock.advance(CONFIRM)
    env.poll()
    rows = {r["video_id"]: r for r in plays(env.store)}
    assert (rows["u2"]["status"], rows["u2"]["reason"]) == (SKIPPED, "unknown_artist")
    assert (rows["u1"]["artist"], rows["u1"]["title"], rows["u1"]["artists"]) == ("Real Artist", "Song", ["Real Artist"])


REALTIME = {"scrobbler_defer_to_realtime": True}


class Timeline:
    """Polls every minute from T0 on, with a real-time scrobbler on another device that may show now playing and scrobble."""

    def __init__(self, env, **overrides):
        self.env = env
        self.overrides = {**REALTIME, **overrides}
        self.rows = [song("a"), song("b"), song("c")]
        start(env, **self.overrides)

    def play(self, video_id, *, on_pc=False, duration=200):
        self.rows = [song(video_id, duration), *[r for r in self.rows if r.video_id != video_id]]
        self.env.history.set(*self.rows)
        self.env.lastfm.playing = NowPlaying("Artist", f"Song {video_id}", "") if on_pc else None

    def stop(self):
        self.env.lastfm.playing = None

    def scrobbled_on_pc(self, video_id, started):
        self.env.lastfm.scrobbles.append(Scrobble("Artist", f"Song {video_id}", "", T0 + started))

    def poll_until(self, seconds):
        while self.env.clock() < T0 + seconds:
            self.env.clock.advance(60)
            self.env.poll(**self.overrides)

    def decisions(self):
        return {r["video_id"]: (r["status"], r["reason"]) for r in plays(self.env.store)}


LEFT = (SKIPPED, "realtime_active")


def test_a_pc_session_with_skips_is_left_to_the_real_time_scrobbler(env):
    t = Timeline(env)
    t.play("p1", on_pc=True)
    t.poll_until(120)
    t.scrobbled_on_pc("p1", 30)
    t.poll_until(180)
    t.play("p2", on_pc=True)
    t.play("p3", on_pc=True)
    t.poll_until(360)
    t.scrobbled_on_pc("p3", 240)
    t.poll_until(600)
    t.stop()
    t.poll_until(900)
    assert t.decisions() == {"p1": LEFT, "p2": LEFT, "p3": LEFT}
    p2 = next(r for r in plays(env.store) if r["video_id"] == "p2")
    assert p2["certainty"] == "certain"
    assert p2["detail"]["realtime"]["from"] <= T0 + 30
    assert p2["detail"]["played"]["hi"] < p2["detail"]["played"]["threshold"]


def test_a_phone_session_after_the_pc_stopped_is_scrobbled_normally(env):
    t = Timeline(env)
    t.play("p1", on_pc=True)
    t.poll_until(120)
    t.scrobbled_on_pc("p1", 30)
    t.poll_until(180)
    t.stop()
    t.poll_until(240)
    t.play("q1")
    t.poll_until(420)
    t.play("q2")
    t.poll_until(900)
    assert t.decisions() == {"p1": LEFT, "q1": (WOULD_SCROBBLE, ""), "q2": (WOULD_SCROBBLE, "")}


def test_switching_devices_mid_session_leaves_only_the_pc_plays(env):
    t = Timeline(env)
    t.play("p1", on_pc=True)
    t.poll_until(120)
    t.scrobbled_on_pc("p1", 30)
    t.poll_until(180)
    t.stop()
    t.poll_until(240)
    t.play("q1")
    t.poll_until(420)
    t.play("p2", on_pc=True)
    t.scrobbled_on_pc("p2", 450)
    t.poll_until(600)
    t.stop()
    t.poll_until(1200)
    assert t.decisions() == {"p1": LEFT, "q1": (WOULD_SCROBBLE, ""), "p2": LEFT}


def test_an_idle_real_time_scrobbler_leaves_every_play_to_the_history(env):
    t = Timeline(env)
    t.scrobbled_on_pc("old", -3600)
    t.play("x")
    t.poll_until(180)
    t.play("y")
    env.lastfm.playing = NowPlaying("Someone Else", "Another Song", "")
    t.poll_until(900)
    assert t.decisions() == {"x": (WOULD_SCROBBLE, ""), "y": (WOULD_SCROBBLE, "")}


def test_with_the_setting_off_the_played_rule_and_duplicates_decide(env):
    t = Timeline(env, scrobbler_defer_to_realtime=False)
    t.play("p1", on_pc=True)
    t.poll_until(120)
    t.scrobbled_on_pc("p1", 30)
    t.poll_until(180)
    t.play("p2", on_pc=True)
    t.play("p3", on_pc=True)
    t.poll_until(900)
    decisions = t.decisions()
    assert decisions["p1"] == (SKIPPED, "duplicate")
    assert decisions["p2"] == (SKIPPED, "listened_too_little")


def test_the_scrobblers_own_scrobbles_are_no_real_time_activity(env):
    t = Timeline(env, scrobbler_dry_run=False)
    t.play("x")
    t.poll_until(420)
    assert t.decisions()["x"] == (SCROBBLED, "")
    t.play("y")
    t.poll_until(900)
    assert t.decisions()["y"] == (SCROBBLED, "")


def test_without_last_fm_plays_that_count_wait_and_the_others_are_skipped(env):
    t = Timeline(env)
    t.play("p1")
    t.poll_until(180)
    t.play("p2")
    t.play("p3")
    env.lastfm.read_error = LastfmUnavailable("down")
    t.poll_until(300)
    decisions = t.decisions()
    assert decisions["p1"] == (PENDING, "")
    assert decisions["p2"] == (SKIPPED, "listened_too_little")


def test_a_real_time_scrobbler_without_now_playing_is_followed_by_its_scrobbles(env):
    t = Timeline(env)
    t.play("p1")
    t.poll_until(120)
    t.scrobbled_on_pc("p1", 30)
    t.poll_until(180)
    t.play("p2", duration=600)
    t.poll_until(360)
    t.play("p3")
    t.scrobbled_on_pc("p3", 390)
    t.poll_until(900)
    assert t.decisions() == {"p1": LEFT, "p2": LEFT, "p3": LEFT}
    assert not env.store.saw_now_playing_since(0)
    assert env.store.now_playing_between(T0, T0 + 900)


RAW_ROWS = [{"videoId": v, "title": f"Song {v}", "artists": [{"name": "Artist"}], "duration_seconds": 200, "played": "Today"} for v in "abc"]


class FlakyYTM:
    """A YTMusic stand-in whose get_history fails with the given messages before it answers."""

    def __init__(self, *failures):
        self.failures = list(failures)
        self.calls = 0

    def get_history(self):
        self.calls += 1
        if self.failures:
            raise RuntimeError(self.failures.pop(0))
        return RAW_ROWS


@pytest.fixture
def sleeps(monkeypatch):
    waited = []
    monkeypatch.setattr("src.ytm.retry.time.sleep", waited.append)
    return waited


@pytest.mark.parametrize("status", ["403: Forbidden", "429: Too Many Requests", "500: Internal Server Error", "503: Service Unavailable"])
def test_a_history_read_is_retried_with_backoff_like_the_sync(sleeps, status):
    ytm = FlakyYTM(f"Server returned HTTP {status}", f"Server returned HTTP {status}")
    items, repeats = fetch_history(ytm, max_retries=3)
    assert [i.video_id for i in items] == ["a", "b", "c"]
    assert (ytm.calls, sleeps, repeats) == (3, [1.0, 2.0], 0)


@pytest.mark.parametrize("status", ["400: Bad Request", "409: Conflict", "401: Unauthorized"])
def test_a_history_read_that_a_retry_cannot_fix_fails_at_once(sleeps, status):
    ytm = FlakyYTM(f"Server returned HTTP {status}")
    with pytest.raises(RuntimeError):
        fetch_history(ytm, max_retries=3)
    assert (ytm.calls, sleeps) == (1, [])


def test_the_history_reader_uses_the_sync_client_and_tries_up_to_api_max_retries(sleeps, monkeypatch, tmp_path):
    ytm = FlakyYTM(*["Server returned HTTP 503: Service Unavailable"] * 5)
    opened = []
    monkeypatch.setattr("src.scrobbler.history.build_oauth_client", lambda path: opened.append(path) or ytm)
    auth = str(tmp_path / "browser.json")
    read = history_reader(settings(api_max_retries=2, ytm_auth_path=auth))
    with pytest.raises(RuntimeError):
        read()
    assert (ytm.calls, sleeps, opened) == (2, [1.0], [auth])


def test_retried_reads_feed_the_poll_and_failures_are_summarised(env, sleeps):
    ytm = FlakyYTM("Server returned HTTP 429: Too Many Requests\nA long upstream body")
    env.history = lambda: fetch_history(ytm, max_retries=3)
    assert env.poll().status == "baseline"
    assert (ytm.calls, sleeps) == (2, [1.0])
    ytm.failures = ["Server returned HTTP 503: Service Unavailable\nA long upstream body"] * 3
    env.clock.advance()
    outcome = env.poll()
    assert outcome.error_kind == ERROR_HISTORY
    assert outcome.error == "Could not read the YouTube Music history: HTTP 503"
    assert sleeps == [1.0, 1.0, 2.0]
    assert env.store.pacing_state()[2] == 1


def test_an_expired_authentication_is_its_own_failure_notified_once(env, sleeps):
    ytm = FlakyYTM(*["Server returned HTTP 401: Unauthorized"] * 2)
    env.history = lambda: fetch_history(ytm, max_retries=3)
    first = env.poll()
    assert first.error_kind == ERROR_HISTORY_AUTH
    assert "retrying cannot fix that" in first.error
    assert "Reconnect YouTube Music" in first.error
    assert first.notify
    env.clock.advance()
    second = env.poll()
    assert (second.error_kind, second.notify) == (ERROR_HISTORY_AUTH, False)
    assert ytm.calls == 2
    assert sleeps == []
    ytm.failures = ["Server returned HTTP 403: Forbidden"] * 3
    env.clock.advance()
    third = env.poll()
    assert (third.error_kind, third.notify) == (ERROR_HISTORY, True)
    assert third.error.endswith("HTTP 403 - rate limit or auth expired")


def history_page(*sections):
    """A FEmusic_history browse answer, reduced to the shape YouTube Music sends (no real data)."""
    tab = {"tabRenderer": {"content": {"sectionListRenderer": {"contents": list(sections)}}}}
    return {"contents": {"singleColumnBrowseResultsRenderer": {"tabs": [tab]}}}


SIGN_IN_MESSAGE = {"messageRenderer": {"text": {"runs": [{"text": "Sign in to view your history"}]}}}
SIGNED_OUT_PAGE = history_page({"itemSectionRenderer": {"contents": [SIGN_IN_MESSAGE]}})
PAUSED_PAGE = history_page({"musicNotifierShelfRenderer": {"title": {"runs": [{"text": "History is paused"}]}}})


@pytest.fixture
def recorded_ytm(monkeypatch):
    """ytmusicapi's own get_history over a recorded browse answer, keeping the requests it sends."""
    from ytmusicapi import YTMusic

    def answering(page):
        ytm = YTMusic()
        ytm.requests = []
        monkeypatch.setattr(ytm, "_check_auth", lambda: None)
        monkeypatch.setattr(ytm, "_send_request", lambda endpoint, _body: ytm.requests.append(endpoint) or page)
        return ytm

    return answering


def test_ytmusicapi_turns_the_signed_out_page_into_an_error_without_a_message(recorded_ytm):
    with pytest.raises(YTMusicServerError) as raised:
        recorded_ytm(SIGNED_OUT_PAGE).get_history()
    assert raised.value.args == (None,)
    with pytest.raises(HistorySignedOut):
        fetch_history(recorded_ytm(SIGNED_OUT_PAGE))


def test_a_signed_out_history_is_an_expired_session_not_retried_and_notified_once(env, sleeps, recorded_ytm):
    ytm = recorded_ytm(SIGNED_OUT_PAGE)
    env.history = lambda: fetch_history(ytm, max_retries=3)
    first = env.poll()
    assert (first.error_kind, first.notify, first.error) == (ERROR_HISTORY_AUTH, True, SIGNED_OUT_MESSAGE)
    assert "private browser window" in first.error
    env.clock.advance()
    second = env.poll()
    assert (second.error_kind, second.previous_error_kind, second.notify) == (ERROR_HISTORY_AUTH, ERROR_HISTORY_AUTH, False)
    assert (ytm.requests, sleeps) == (["browse", "browse"], [])


def test_a_notice_shelf_instead_of_the_history_is_shown_as_given(env, sleeps, recorded_ytm):
    env.history = lambda: fetch_history(recorded_ytm(PAUSED_PAGE), max_retries=3)
    outcome = env.poll()
    assert (outcome.error_kind, outcome.error) == (ERROR_HISTORY, "Could not read the YouTube Music history: History is paused")
    assert sleeps == []


@pytest.mark.parametrize("error", [RuntimeError(), RuntimeError(None), OSError("  ")])
def test_a_history_error_without_a_message_names_its_type(env, error):
    def fail():
        raise error

    env.history = fail
    outcome = env.poll()
    assert outcome.error == f"Could not read the YouTube Music history: {type(error).__name__}"
