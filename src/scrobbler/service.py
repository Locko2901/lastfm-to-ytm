"""One poll of the history scrobbler: detect plays, decide each one, scrobble or dry run.

When a play is due and in which order it is decided (played rule, real-time
scrobbler, age, duplicates, send) is explained in docs/scrobbler.md.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from ..config import Settings
from ..lastfm.client import (
    LastfmAuthError,
    LastfmClient,
    LastfmError,
    LastfmTooManyScrobbles,
    LastfmUnavailable,
    NowPlaying,
    ScrobbleEntry,
    iter_batches,
)
from ..lastfm.scrobble import Scrobble
from ..observability.http_status import describe_sync_error, extract_http_status
from .dedup import Candidate, find_duplicate, window_seconds
from .detect import BASELINE, RESET, Pending, SnapshotEntry, Step, confirm_step
from .history import HistoryItem, HistorySignedOut
from .matching import MATCH, TrackKey, compare, track_key
from .played import (
    DEFAULT_RULES,
    END_SLACK_SECONDS,
    MIN_TRACK_SECONDS,
    OPEN,
    SKIP,
    Evidence,
    Rules,
    Verdict,
    assess,
    chain_starts,
    shared_durations,
    spread_starts,
    timing_unknown,
)
from .realtime import (
    CLOCK_SLACK_SECONDS,
    NOW_PLAYING_MEMORY_SECONDS,
    REALTIME_GAP_SECONDS,
    Period,
    active_during,
    active_periods,
    usable_sightings,
)
from .store import FAILED, PENDING, SCROBBLED, SENDING, SKIPPED, WOULD_SCROBBLE, NewPlay, PlayRow, ScrobblerStore

log = logging.getLogger(__name__)

MAX_SCROBBLE_AGE_SECONDS = 14 * 24 * 3600
AGE_SAFETY_SECONDS = 3600
SETTLE_SLACK_SECONDS = 60
RECENT_FETCH_MARGIN_SECONDS = 300
WIDE_WINDOW_SECONDS = 24 * 3600
MAX_RANGE_SECONDS = 24 * 3600
UNKNOWN_TIMING_DEDUP_SECONDS = 24 * 3600

REASON_DUPLICATE = "duplicate"
REASON_TOO_OLD = "too_old"
REASON_NOT_MUSIC = "not_music"
REASON_NO_ARTIST = "no_artist"
REASON_IGNORED = "ignored_by_lastfm"
REASON_ERROR = "error"
REASON_RECOVERED = "recovered"
REASON_TOO_MANY_SCROBBLES = "too_many_scrobbles"
REASON_TOO_SHORT = "too_short"
REASON_UNKNOWN_DURATION = "unknown_duration"
REASON_LISTENED_TOO_LITTLE = "listened_too_little"
REASON_UNKNOWN_ARTIST = "unknown_artist"
REASON_REALTIME = "realtime_active"

ERROR_HISTORY = "history"
ERROR_HISTORY_AUTH = "history_auth"
ERROR_LASTFM_UNAVAILABLE = "lastfm_unavailable"
ERROR_LASTFM_AUTH = "lastfm_auth"
ERROR_NOT_CONNECTED = "not_connected"
ERROR_ACCOUNT_MISMATCH = "account_mismatch"
ERROR_SCROBBLE_FAILED = "scrobble_failed"
ERROR_DAILY_LIMIT = "daily_limit"

DAILY_LIMIT_CODE = 5
SIGNED_OUT_MESSAGE = (
    "YouTube Music answered the history read as signed out, and retrying cannot fix that. Reconnect YouTube Music in "
    "Settings, General, copying the request headers from a private browser window so that normal browsing does not "
    "rotate the session; polling picks up again by itself."
)
_META_ERROR_KIND = "error_kind"

HistoryReader = Callable[[], tuple[list[HistoryItem], int]]
Detector = Callable[[Sequence[SnapshotEntry] | None, Pending | None, Sequence[HistoryItem], float], Step]


@dataclass
class PollOutcome:
    """Summary of one poll, also what the dashboard and notifications show."""

    status: str = "ok"
    dry_run: bool = True
    history_rows: int = 0
    history_repeats: int = 0
    history_failed: bool = False
    changed: bool = False
    new_plays: int = 0
    scrobbled: int = 0
    would_scrobble: int = 0
    skipped: int = 0
    pending: int = 0
    failed: int = 0
    error: str = ""
    error_kind: str = ""
    previous_error_kind: str = ""
    notify: bool = False
    messages: list[str] = field(default_factory=list)

    def fail(self, kind: str, message: str) -> None:
        """Record an error; the first one of a poll sets the kind."""
        if not self.error_kind:
            self.error_kind = kind
            self.error = message
        self.messages.append(message)


@dataclass(frozen=True, slots=True)
class NowPlayingRead:
    """Last.fm's now playing track as read once per poll (``playing`` is None when nothing plays)."""

    playing: NowPlaying | None


def error_text(error: BaseException) -> str:
    """The error's message, or its type when the message is empty or ``None``."""
    text = str(error).strip()
    return text if text and text != "None" else type(error).__name__


def last_error_kind(store: ScrobblerStore) -> str:
    """The error kind of the last poll, empty after a poll without errors."""
    return store.get_meta(_META_ERROR_KIND) or ""


def oldest_accepted_timestamp(now: float) -> int:
    """Oldest play timestamp still sent: Last.fm refuses scrobbles older than 14 days (an hour of margin)."""
    return round(now - MAX_SCROBBLE_AGE_SECONDS + AGE_SAFETY_SECONDS)


def play_range(play: PlayRow, window: int) -> tuple[int, int]:
    """Time range whose scrobbles can cover ``play``: its window, plus a margin."""
    return play.timestamp - window - RECENT_FETCH_MARGIN_SECONDS, play.timestamp + window + RECENT_FETCH_MARGIN_SECONDS


def group_ranges(items: list[tuple[tuple[int, int], PlayRow]], max_span: int | None) -> list[tuple[tuple[int, int], list[PlayRow]]]:
    """Merge overlapping ranges (each with its play), keeping every merged range within ``max_span``."""
    groups: list[tuple[tuple[int, int], list[PlayRow]]] = []
    for (start, end), play in sorted(items, key=lambda item: item[0]):
        if groups:
            (g_start, g_end), plays = groups[-1]
            merged_end = max(g_end, end)
            if start <= g_end and (max_span is None or merged_end - g_start <= max_span):
                groups[-1] = ((g_start, merged_end), [*plays, play])
                continue
        groups.append(((start, end), [play]))
    return groups


def evidence_of(play: PlayRow) -> Evidence:
    """The poll evidence of a recorded play, for the played rule."""
    return Evidence(
        duration=play.duration or 0,
        window_start=play.window_start,
        window_end=play.detected_at,
        position=play.position,
        count=play.window_count,
        next_window_start=play.next_window_start,
        next_window_end=play.next_window_end,
        next_count=play.next_window_count,
        shared_durations=play.shared,
    )


def play_timing_unknown(play: PlayRow, rules: Rules = DEFAULT_RULES) -> bool:
    """True for a play found in a burst or after a long gap between polls."""
    return timing_unknown(play.window_count, play.gap, rules)


def dedup_window(play: PlayRow, rules: Rules = DEFAULT_RULES) -> int:
    """Duplicate window of a play; a play of unknown timing is compared with a whole day of scrobbles."""
    window = window_seconds(play.duration, play.gap)
    return max(window, UNKNOWN_TIMING_DEDUP_SECONDS) if play_timing_unknown(play, rules) else window


def is_due(play: PlayRow, now: float, rules: Rules = DEFAULT_RULES) -> bool:
    """True once the played rule can decide and a real-time scrobbler had a minute to act.

    That is after the poll that showed the next play, right after the poll that
    found a play of unknown timing, or, while nothing followed, once the play
    has been on top longer than it could have lasted.
    """
    if play.status == SENDING:
        return True
    if play_timing_unknown(play, rules):
        return now >= play.detected_at + SETTLE_SLACK_SECONDS
    if play.next_window_end is not None:
        return now >= play.next_window_end + SETTLE_SLACK_SECONDS
    return now >= play.detected_at + (play.duration or 0) + END_SLACK_SECONDS + SETTLE_SLACK_SECONDS


def played_detail(verdict: Verdict) -> dict[str, Any]:
    """The played rule's numbers, for the decision log."""
    return {
        "lo": round(verdict.lo),
        "hi": round(verdict.hi),
        "threshold": round(verdict.threshold),
        "certainty": verdict.certainty,
        "estimate": None if verdict.estimate is None else round(verdict.estimate, 3),
        "basis": verdict.basis,
    }


def _listening(verdict: Verdict | None) -> tuple[float, float, float, str, str] | None:
    return None if verdict is None else (verdict.lo, verdict.hi, verdict.threshold, verdict.certainty, verdict.basis)


def _detection_status(item: HistoryItem) -> tuple[str, str]:
    """Plays decided as soon as they are found: not music, no artist, no length, too short."""
    if not item.is_music:
        return SKIPPED, REASON_NOT_MUSIC
    if item.is_upload and not item.scrobble_artist:
        return SKIPPED, REASON_UNKNOWN_ARTIST
    if not item.scrobble_artist or not item.scrobble_title:
        return SKIPPED, REASON_NO_ARTIST
    if item.duration is None:
        return SKIPPED, REASON_UNKNOWN_DURATION
    if item.duration <= MIN_TRACK_SECONDS:
        return SKIPPED, REASON_TOO_SHORT
    return PENDING, ""


class Poller:
    """Runs polls against a store, a history reader and a Last.fm client; ``detect`` turns each read into a ``detect.Step``."""

    def __init__(
        self,
        settings: Settings,
        store: ScrobblerStore,
        read_history: HistoryReader,
        client: LastfmClient,
        *,
        now: Callable[[], float] = time.time,
        rules: Rules = DEFAULT_RULES,
        realtime_gap: float = REALTIME_GAP_SECONDS,
        detect: Detector = confirm_step,
    ):
        self.settings = settings
        self.store = store
        self.read_history = read_history
        self.client = client
        self.now = now
        self.rules = rules
        self.realtime_gap = realtime_gap
        self.detect = detect

    def run(self) -> PollOutcome:
        """Run one poll and return its summary (never raises for expected failures).

        Returns a ``busy`` outcome, without touching anything, when another poll
        (in this process or another one) holds the store's lock.
        """
        with self.store.exclusive() as owned:
            if not owned:
                return PollOutcome(status="busy", dry_run=self.settings.scrobbler_dry_run)
            return self._run()

    def _run(self) -> PollOutcome:
        started = self.now()
        dry_run = self.settings.scrobbler_dry_run
        outcome = PollOutcome(dry_run=dry_run)
        poll_id = self.store.start_poll(started, dry_run)
        try:
            items = self._detect(poll_id, started, outcome)
            read = self._watch_realtime(started, items)
            self.store.record_pacing(changed_at=started if outcome.changed else None, history_failed=outcome.history_failed)
            self._decide(started, outcome, read)
        except Exception as e:
            log.exception("Scrobbler poll failed")
            outcome.fail(REASON_ERROR, f"Unexpected error: {error_text(e)}")
            outcome.status = "error"
        if outcome.error_kind and outcome.status == "ok":
            outcome.status = "error"
        self.store.finish_poll(
            poll_id,
            self.now(),
            outcome.status,
            history_rows=outcome.history_rows,
            history_repeats=outcome.history_repeats,
            new_plays=outcome.new_plays,
            scrobbled=outcome.scrobbled,
            would_scrobble=outcome.would_scrobble,
            skipped=outcome.skipped,
            pending=outcome.pending,
            failed=outcome.failed,
            error=outcome.error,
        )
        outcome.previous_error_kind = last_error_kind(self.store)
        outcome.notify = bool(outcome.error_kind) and outcome.error_kind != outcome.previous_error_kind
        self.store.set_meta(_META_ERROR_KIND, outcome.error_kind)
        self.store.prune(started)
        return outcome

    def _detect(self, poll_id: int, now: float, outcome: PollOutcome) -> list[HistoryItem] | None:
        """Read the history and record the plays this poll confirms (see ``detect.confirm_step``); return what was read."""
        try:
            items, repeats = self.read_history()
        except HistorySignedOut:
            outcome.history_failed = True
            outcome.fail(ERROR_HISTORY_AUTH, SIGNED_OUT_MESSAGE)
            return None
        except Exception as e:
            outcome.history_failed = True
            message = error_text(e)
            if extract_http_status(message) == 401:
                outcome.fail(
                    ERROR_HISTORY_AUTH,
                    "YouTube Music refused to read the history (HTTP 401): the browser authentication has expired, and retrying "
                    "cannot fix that. Reconnect YouTube Music in the dashboard; polling picks up again by itself.",
                )
            else:
                outcome.fail(ERROR_HISTORY, f"Could not read the YouTube Music history: {describe_sync_error(message)}")
            return None
        outcome.history_rows = len(items)
        outcome.history_repeats = repeats
        previous, last_poll_at = self.store.load_snapshot()
        step = self.detect(previous, self.store.load_pending(), items, now)
        outcome.changed = step.changed
        if not items:
            outcome.status = "empty"
            return items
        if step.flicker:
            outcome.status = "flicker"
        if step.snapshot is None or step.seen_at is None:
            if step.pending is not None and step.pending.kind in (BASELINE, RESET):
                outcome.status = step.pending.kind
            self.store.save_observed(step.observed_at, step.pending, step.snapshot)
            return items
        observed = step.observed_at if step.observed_at is not None else step.seen_at
        if step.kind == BASELINE:
            outcome.status = "baseline"
            self.store.save_snapshot(step.snapshot, observed, step.pending)
            return items
        window_start = last_poll_at if last_poll_at is not None and last_poll_at <= step.seen_at else step.seen_at
        if step.kind == RESET:
            outcome.status = "reset"
            self.store.save_reset(step.snapshot, window_start, step.seen_at, step.pending, observed)
            return items
        self._record(poll_id, step, window_start, previous or [], outcome)
        return items

    def _watch_realtime(self, now: float, items: Sequence[HistoryItem] | None) -> NowPlayingRead | None:
        """Read Last.fm's now playing track once and remember whether it is the song on top of the history.

        Returns None when deferring to real-time scrobblers is off or the read
        failed (the decisions then read it themselves and report a failure).
        Nothing is remembered without a history to compare with.
        """
        if not self.settings.scrobbler_defer_to_realtime:
            return None
        try:
            playing = self.client.now_playing(self.settings.lastfm_user)
        except LastfmError as e:
            log.info("Could not read the now playing track: %s", e)
            return None
        if items:
            top = track_key(items[0].match_artists, items[0].scrobble_title)
            self.store.record_now_playing(now, playing is not None and compare(top, track_key(playing.artist, playing.track)) == MATCH)
        return NowPlayingRead(playing)

    def _record(self, poll_id: int, step: Step, window_start: float, previous: Sequence[SnapshotEntry], outcome: PollOutcome) -> None:
        """Store the plays a poll confirmed, with the window they started in."""
        assert step.snapshot is not None and step.seen_at is not None
        seen_at = step.seen_at
        new = list(reversed(step.accepted))
        if timing_unknown(len(new), seen_at - window_start, self.rules):
            starts = chain_starts([item.duration or 0 for item in new], seen_at)
        else:
            starts = spread_starts(len(new), window_start, seen_at)
        shared = shared_durations([item.duration or 0 for item in new])
        previous_ids = {entry.video_id for entry in previous}
        plays: list[NewPlay] = []
        for position, (item, start) in enumerate(zip(new, starts, strict=True)):
            status, reason = _detection_status(item)
            plays.append(
                NewPlay(
                    video_id=item.video_id,
                    artist=item.scrobble_artist,
                    title=item.scrobble_title,
                    artists=item.match_artists,
                    album=item.album,
                    duration=item.duration,
                    played=item.played,
                    replay=item.video_id in previous_ids,
                    timestamp=round(start),
                    earliest=round(window_start),
                    latest=round(seen_at),
                    status=status,
                    reason=reason,
                    position=position,
                    count=len(new),
                    shared=shared if position < len(new) - 1 else (),
                )
            )
        observed = step.observed_at if step.observed_at is not None else seen_at
        self.store.record_detection(
            step.snapshot,
            seen_at,
            window_start,
            plays,
            poll_id=poll_id,
            dry_run=self.settings.scrobbler_dry_run,
            pending=step.pending,
            observed_at=observed,
        )
        outcome.new_plays = len(plays)
        outcome.skipped += sum(1 for p in plays if p.status == SKIPPED)

    def _decide(self, now: float, outcome: PollOutcome, read: NowPlayingRead | None = None) -> None:
        """Decide every due play: too old, left to a real-time scrobbler, duplicate, scrobble or would scrobble."""
        dry_run = self.settings.scrobbler_dry_run
        due: list[PlayRow] = []
        for play in self.store.open_plays():
            if play.status == PENDING and play.timestamp < oldest_accepted_timestamp(now):
                self.store.decide(play.id, SKIPPED, reason=REASON_TOO_OLD, decided_at=now, dry_run=dry_run)
                outcome.skipped += 1
            elif is_due(play, now, self.rules):
                due.append(play)
        try:
            if due:
                _snapshot, observed = self.store.load_snapshot()
                self._decide_due(due, now, dry_run, outcome, now if observed is None else min(now, observed), read)
        finally:
            outcome.pending = len(self.store.open_plays())

    def _decide_due(self, due: list[PlayRow], now: float, dry_run: bool, outcome: PollOutcome, observed: float, read: NowPlayingRead | None) -> None:
        """Apply the played rule, leave plays to an active real-time scrobbler, then check the rest against Last.fm and scrobble them.

        Open plays are judged as of ``observed``, the last poll that confirmed
        nothing else had started: a newer row may still wait for confirmation.
        Plays that count wait while scrobbling cannot run (not connected, or
        Last.fm unreachable); plays that do not count are then skipped by the
        played rule alone.
        """
        defer = self.settings.scrobbler_defer_to_realtime
        verdicts: dict[int, Verdict] = {}
        counted: list[PlayRow] = []
        unplayed: list[PlayRow] = []
        for play in due:
            if play.status == SENDING:
                counted.append(play)
                continue
            verdict = assess(evidence_of(play), observed, self.rules)
            if verdict.outcome == OPEN:
                continue
            verdicts[play.id] = verdict
            (unplayed if verdict.outcome == SKIP else counted).append(play)
        if not defer:
            self._skip_all_as_too_little(unplayed, verdicts, now, dry_run, outcome)
            unplayed = []
        if counted and not dry_run:
            problem = self._live_problem()
            if problem:
                outcome.fail(*problem)
                counted = []
        if not counted and not unplayed:
            return

        windows = {play.id: dedup_window(play, self.rules) for play in counted + unplayed}
        try:
            recent, checked, unchecked = self._recent_scrobbles(counted + unplayed, windows)
            playing = read.playing if read is not None else self.client.now_playing(self.settings.lastfm_user)
        except LastfmError as e:
            outcome.fail(ERROR_LASTFM_UNAVAILABLE, f"Could not read recent scrobbles from Last.fm, plays wait for the next poll: {e}")
            self._skip_all_as_too_little(unplayed, verdicts, now, dry_run, outcome)
            return
        unplayed_ids = {play.id for play in unplayed}
        self._skip_all_as_too_little([p for p, _error in unchecked if p.id in unplayed_ids], verdicts, now, dry_run, outcome)
        for play, error in unchecked:
            if play.id not in unplayed_ids and play.status == PENDING:
                too_many = {"window": windows[play.id], "error": error}
                self.store.decide(play.id, SKIPPED, reason=REASON_TOO_MANY_SCROBBLES, detail=too_many, decided_at=now, dry_run=dry_run)
                outcome.skipped += 1
        if not checked:
            return

        candidates = [Candidate(s.artist, s.track, s.album, s.ts) for s in recent]
        if playing is not None:
            candidates.append(Candidate(playing.artist, playing.track, playing.album, round(now), now_playing=True))
        used: set[int] = set()

        to_decide = [p for p in checked if p.status == PENDING]
        to_decide += self._recover_sending([p for p in checked if p.status == SENDING], candidates, used, now, dry_run, outcome)
        self._exclude_own(candidates, used)
        own = set(used)
        self._exclude_covered(candidates, used, now)
        periods = self._active_periods(candidates, own, to_decide, now) if defer and to_decide else []

        to_send: list[tuple[PlayRow, dict[str, Any]]] = []
        for play in sorted(to_decide, key=lambda p: (p.timestamp, p.id)):
            verdict = verdicts.get(play.id) or assess(evidence_of(play), observed, self.rules)
            verdicts[play.id] = verdict
            period = active_during(periods, play.window_start, play.detected_at)
            if period is not None:
                self._leave_to_realtime(play, verdict, period, now, dry_run)
                outcome.skipped += 1
                continue
            if verdict.outcome == SKIP:
                self._skip_as_too_little(play, verdict, now, dry_run)
                outcome.skipped += 1
                continue
            window = windows[play.id]
            result = find_duplicate(track_key(play.artists, play.title), play.timestamp, window, candidates, used)
            detail: dict[str, Any] = {
                "window": window,
                "uncertainty": max(play.timestamp - play.earliest, play.latest - play.timestamp),
                "played": played_detail(verdict),
            }
            if result.near_miss is not None:
                detail["near_miss"] = {**candidates[result.near_miss].to_dict(), "reason": result.near_miss_reason}
            if result.duplicate is not None:
                used.add(result.duplicate)
                match = candidates[result.duplicate]
                detail["duplicate_of"] = {**match.to_dict(), "distance": abs(match.timestamp - play.timestamp)}
                self.store.decide(
                    play.id, SKIPPED, reason=REASON_DUPLICATE, detail=detail, decided_at=now, dry_run=dry_run, listening=_listening(verdict)
                )
                outcome.skipped += 1
            elif dry_run:
                self.store.decide(play.id, WOULD_SCROBBLE, detail=detail, decided_at=now, dry_run=True, listening=_listening(verdict))
                outcome.would_scrobble += 1
            else:
                to_send.append((play, detail))

        if to_send:
            self._send(to_send, verdicts, now, outcome)

    def _active_periods(self, candidates: list[Candidate], own: set[int], plays: list[PlayRow], now: float) -> list[Period]:
        """Real-time scrobbler activity around ``plays``: now playing sightings and the scrobbles that are not the scrobbler's own."""
        reach = self.realtime_gap + CLOCK_SLACK_SECONDS
        start = min(p.window_start for p in plays) - reach
        end = max(p.detected_at for p in plays) + reach
        reports = self.store.saw_now_playing_since(now - NOW_PLAYING_MEMORY_SECONDS)
        sightings = usable_sightings(self.store.now_playing_between(start, end), reports)
        scrobbles = [c.timestamp for i, c in enumerate(candidates) if not c.now_playing and i not in own]
        return active_periods(sightings, scrobbles, self.realtime_gap)

    def _leave_to_realtime(self, play: PlayRow, verdict: Verdict, period: Period, now: float, dry_run: bool) -> None:
        """Record a play left to the real-time scrobbler that was active around it."""
        detail = {
            "realtime": {"from": round(period.start), "to": round(period.end), "points": period.points},
            "played": played_detail(verdict),
        }
        self.store.decide(play.id, SKIPPED, reason=REASON_REALTIME, detail=detail, decided_at=now, dry_run=dry_run, listening=_listening(verdict))

    def _skip_all_as_too_little(
        self, plays: Sequence[PlayRow], verdicts: dict[int, Verdict], now: float, dry_run: bool, outcome: PollOutcome
    ) -> None:
        """Skip plays the played rule did not count, without looking for real-time activity."""
        for play in plays:
            self._skip_as_too_little(play, verdicts[play.id], now, dry_run)
            outcome.skipped += 1

    def _skip_as_too_little(self, play: PlayRow, verdict: Verdict, now: float, dry_run: bool) -> None:
        """Record a play the played rule did not count."""
        self.store.decide(
            play.id,
            SKIPPED,
            reason=REASON_LISTENED_TOO_LITTLE,
            detail={"played": played_detail(verdict)},
            decided_at=now,
            dry_run=dry_run,
            listening=_listening(verdict),
        )

    def _scrobble_range(self, play: PlayRow, window: int) -> tuple[int, int]:
        """Time range whose scrobbles matter for ``play``: its duplicate window, and with deferring on the reach of real-time activity."""
        start, end = play_range(play, window)
        if self.settings.scrobbler_defer_to_realtime:
            reach = self.realtime_gap + CLOCK_SLACK_SECONDS
            start = min(start, math.floor(play.window_start - reach))
            end = max(end, math.ceil(play.detected_at + reach))
        return start, end

    def _recent_scrobbles(self, due: list[PlayRow], windows: dict[int, int]) -> tuple[list[Scrobble], list[PlayRow], list[tuple[PlayRow, str]]]:
        """Read the scrobbles around every due play: the scrobbles, the plays they cover, and the plays that could not be checked.

        Nearby windows are read together, up to a day per request; a play whose
        own window is over a day is read alone and returned as unchecked (with
        the error) when its range holds too many scrobbles.
        """
        user = self.settings.lastfm_user
        found: dict[tuple[int, str, str], Scrobble] = {}
        checked: list[PlayRow] = []
        unchecked: list[tuple[PlayRow, str]] = []
        normal = [p for p in due if windows[p.id] <= WIDE_WINDOW_SECONDS]
        wide = [p for p in due if windows[p.id] > WIDE_WINDOW_SECONDS]
        for (start, end), plays in group_ranges([(self._scrobble_range(p, windows[p.id]), p) for p in normal], MAX_RANGE_SECONDS):
            found.update({(s.ts, s.artist, s.track): s for s in self.client.recent_scrobbles(user, start, end)})
            checked += plays
        for (start, end), plays in group_ranges([(self._scrobble_range(p, windows[p.id]), p) for p in wide], None):
            try:
                scrobbles = self.client.recent_scrobbles(user, start, end)
            except LastfmTooManyScrobbles as e:
                unchecked += [(play, str(e)) for play in plays]
                continue
            found.update({(s.ts, s.artist, s.track): s for s in scrobbles})
            checked += plays
        return sorted(found.values(), key=lambda s: -s.ts), checked, unchecked

    def _live_problem(self) -> tuple[str, str] | None:
        """Why live scrobbling cannot run right now, if it cannot."""
        s = self.settings
        if not s.lastfm_api_secret or not s.lastfm_session_key:
            return ERROR_NOT_CONNECTED, "Not connected to Last.fm: add the API secret and run the Connect Last.fm step"
        if s.lastfm_session_user and s.lastfm_session_user.casefold() != s.lastfm_user.casefold():
            return (
                ERROR_ACCOUNT_MISMATCH,
                f"The Last.fm session belongs to {s.lastfm_session_user}, but LASTFM_USER is {s.lastfm_user}; reconnect with the right account",
            )
        return None

    def _recover_sending(
        self, sending: list[PlayRow], candidates: list[Candidate], used: set[int], now: float, dry_run: bool, outcome: PollOutcome
    ) -> list[PlayRow]:
        """Resolve plays sent without an answer: scrobbled when Last.fm has them, else pending again.

        A scrobble at exactly the play's timestamp with the same title or artist
        is taken as this play (Last.fm may have corrected one of them). Returns
        the plays that went back to pending, to be decided like the others.
        """
        retry: list[PlayRow] = []
        for play in sending:
            keys = [track_key(play.artists, play.title)]
            found = _same_timestamp(play.timestamp, keys, candidates, used)
            if found is None:
                self.store.decide(play.id, PENDING, decided_at=now, dry_run=dry_run)
                retry.append(replace(play, status=PENDING))
                continue
            used.add(found)
            match = candidates[found]
            self.store.decide(
                play.id, SCROBBLED, reason=REASON_RECOVERED, decided_at=now, dry_run=False, lastfm_artist=match.artist, lastfm_title=match.track
            )
            outcome.scrobbled += 1
        return retry

    def _exclude_own(self, candidates: list[Candidate], used: set[int]) -> None:
        """Take the scrobbler's own earlier scrobbles out of the candidates: they cover other plays.

        One of them is recognised by its exact timestamp and title or artist, as
        recorded in the ledger.
        """
        since = min((c.timestamp for c in candidates if not c.now_playing), default=None)
        if since is None:
            return
        for own in self.store.own_scrobbles_since(since):
            keys = [track_key(own.artists, own.title)]
            if own.lastfm_artist and own.lastfm_title:
                keys.append(track_key(own.lastfm_artist, own.lastfm_title))
            found = _same_timestamp(own.timestamp, keys, candidates, used)
            if found is not None:
                used.add(found)

    def _exclude_covered(self, candidates: list[Candidate], used: set[int], now: float) -> None:
        """Take out the scrobbles that earlier polls matched as duplicates: each covers one play only.

        A play matched to the now playing track claims the real scrobble that
        track later became: the closest same-track scrobble within its window.
        """
        for play, detail in self.store.duplicates_decided_since(now - MAX_SCROBBLE_AGE_SECONDS - WIDE_WINDOW_SECONDS):
            matched = detail.get("duplicate_of")
            if not isinstance(matched, dict):
                continue
            if matched.get("now_playing"):
                key = track_key(play.artists, play.title)
                window = int(detail.get("window") or window_seconds(play.duration, play.gap))
                closest = [
                    (abs(c.timestamp - play.timestamp), i)
                    for i, c in enumerate(candidates)
                    if i not in used and not c.now_playing and abs(c.timestamp - play.timestamp) <= window and compare(key, c.key) == MATCH
                ]
                if closest:
                    used.add(min(closest)[1])
                continue
            for i, c in enumerate(candidates):
                if (
                    i not in used
                    and not c.now_playing
                    and c.timestamp == matched.get("timestamp")
                    and c.artist == matched.get("artist")
                    and c.track == matched.get("track")
                ):
                    used.add(i)
                    break

    def _send(self, to_send: list[tuple[PlayRow, dict[str, Any]]], verdicts: dict[int, Verdict], now: float, outcome: PollOutcome) -> None:
        """Scrobble in batches of 50.

        A batch Last.fm did not answer stays ``sending``: the next poll looks for
        it among the recent scrobbles before sending it again.
        """
        for batch in iter_batches(to_send):
            ids = [play.id for play, _ in batch]
            self.store.mark_sending(ids)
            entries = [ScrobbleEntry(p.artist, p.title, p.timestamp, p.album, p.duration) for p, _ in batch]
            try:
                results = self.client.scrobble_batch(entries)
            except LastfmAuthError as e:
                self._back_to_pending(ids, now)
                outcome.fail(ERROR_LASTFM_AUTH, f"Last.fm rejected the session key ({e}); reconnect in Settings")
                return
            except LastfmUnavailable as e:
                outcome.fail(ERROR_LASTFM_UNAVAILABLE, f"Last.fm did not answer; the next poll checks whether these scrobbles landed: {e}")
                return
            except LastfmError as e:
                for play, detail in batch:
                    self.store.decide(play.id, FAILED, reason=REASON_ERROR, detail={**detail, "error": str(e)}, decided_at=now, dry_run=False)
                outcome.failed += len(batch)
                outcome.fail(ERROR_SCROBBLE_FAILED, f"Last.fm refused {len(batch)} scrobble(s): {e}")
                continue
            for (play, detail), result in zip(batch, results, strict=True):
                if result.accepted:
                    self.store.decide(
                        play.id,
                        SCROBBLED,
                        detail=detail,
                        decided_at=now,
                        dry_run=False,
                        lastfm_artist=result.artist,
                        lastfm_title=result.track,
                        listening=_listening(verdicts.get(play.id)),
                    )
                    outcome.scrobbled += 1
                elif result.ignored_code == DAILY_LIMIT_CODE:
                    self.store.decide(play.id, PENDING, decided_at=now, dry_run=False)
                    outcome.fail(ERROR_DAILY_LIMIT, "Last.fm's daily scrobble limit is reached; plays will be retried")
                else:
                    ignored = {"code": result.ignored_code, "message": result.ignored_message}
                    self.store.decide(play.id, SKIPPED, reason=REASON_IGNORED, detail={**detail, "ignored": ignored}, decided_at=now, dry_run=False)
                    outcome.skipped += 1

    def _back_to_pending(self, ids: list[int], now: float) -> None:
        for play_id in ids:
            self.store.decide(play_id, PENDING, decided_at=now, dry_run=False)


def _same_timestamp(timestamp: int, keys: list[TrackKey], candidates: list[Candidate], used: set[int]) -> int | None:
    """Index of an unused scrobble at exactly ``timestamp`` sharing a title or an artist with one of ``keys``."""
    for i, c in enumerate(candidates):
        if i in used or c.now_playing or c.timestamp != timestamp:
            continue
        other = c.key
        if any(k.title == other.title or k.artists & other.artists for k in keys):
            return i
    return None
