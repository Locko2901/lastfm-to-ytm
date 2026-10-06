"""Simulate listening sessions and score the history scrobbler's decisions against the truth.

Each session runs through the scrobbler's own ``Poller`` and adaptive pacing,
with fake history and Last.fm. Run it to print the tables, with ``--write`` to
update docs/scrobbler.md, or with ``--check`` to fail when they are stale.
"""

from __future__ import annotations

import argparse
import dataclasses
import functools
import os
import random
import sys
import tempfile
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import SCROBBLER_POLL_MINUTES_DEFAULT, Settings
from src.lastfm.client import LastfmClient, NowPlaying
from src.lastfm.scrobble import Scrobble
from src.scrobbler.detect import (
    BASELINE,
    PLAYS,
    RESET,
    Pending,
    SnapshotEntry,
    Step,
    confirm_step,
    detect_new_plays,
    snapshot_of,
)
from src.scrobbler.history import HistoryItem
from src.scrobbler.pacing import IDLE_INTERVAL_SECONDS, poll_due
from src.scrobbler.played import (
    CERTAIN,
    DEFAULT_RULES,
    END_MODELS,
    MIN_TRACK_SECONDS,
    PLAY,
    SKIP,
    TIEBREAKS,
    TIMING_MODELS,
    Rules,
    threshold_seconds,
)
from src.scrobbler.realtime import REALTIME_GAP_SECONDS
from src.scrobbler.service import REASON_DUPLICATE, REASON_REALTIME, Poller
from src.scrobbler.store import SKIPPED, WOULD_SCROBBLE, ScrobblerStore

DOCS = ROOT / "docs" / "scrobbler.md"
SECTION = "### Simulation results"

INTERVALS_MINUTES = (1, 2, 5, 10)
SESSIONS_PER_SCENARIO = 40
SEED = 20261006
BACKGROUND_ROWS = 80
FALSE_SCROBBLE_WEIGHT = 3
HISTORY_LIMIT = 200
IDLE_BEFORE_SECONDS = 3600
TAIL_SECONDS = 2 * 3600
FLICKER_SHARE = 0.15
STOPPED_SESSION_SHARE = 0.5
PHONE = "phone"
PC = "pc"
DEFER = "defer"
DUPLICATE = "duplicate"
SCRATCH_DIR = "/dev/shm" if Path("/dev/shm").is_dir() else None
WORKERS = os.cpu_count() or 1
GAP_VARIANTS_MINUTES = (2, 5, 10, 15)
IDLE_VARIANTS_MINUTES = (5, 10, 15)


@dataclass(frozen=True, slots=True)
class TruePlay:
    """One play as it really happened; ``appears`` is when its row reaches the history (its start unless synced late).

    A play on the ``PC`` device is seen by a real-time scrobbler there: shown
    as now playing while it plays, scrobbled (at its start time) once it
    reached Last.fm's threshold.
    """

    track: str
    duration: int
    start: float
    listened: float
    appears: float | None = None
    device: str = PHONE

    @property
    def shown(self) -> float:
        """When the play's row shows up in the history."""
        return self.start if self.appears is None else self.appears

    @property
    def scrobble(self) -> bool:
        """Last.fm's rule on the real listening time."""
        return self.duration > MIN_TRACK_SECONDS and self.listened >= threshold_seconds(self.duration)

    def playing_at(self, t: float) -> bool:
        """True while the play plays."""
        return self.start <= t < self.start + self.listened

    def scrobbled_by(self, t: float) -> bool:
        """True once a real-time scrobbler on its device has scrobbled it."""
        return self.device == PC and self.scrobble and self.start + threshold_seconds(self.duration) <= t


@dataclass
class Session:
    """A listening session and what goes wrong while it is read."""

    plays: list[TruePlay]
    outage: tuple[float, float] | None = None
    flicker: float = 0.0


@dataclass
class Score:
    """Decisions compared with the truth."""

    real: int = 0
    sent: int = 0
    false: int = 0
    missed: int = 0
    decisions: int = 0
    certain: int = 0
    phantom: int = 0
    polls: int = 0

    def add(self, other: Score) -> None:
        """Accumulate another score."""
        for name in ("real", "sent", "false", "missed", "decisions", "certain", "phantom", "polls"):
            setattr(self, name, getattr(self, name) + getattr(other, name))

    @property
    def false_share(self) -> float:
        """Share of sent scrobbles that should not exist."""
        return self.false / self.sent if self.sent else 0.0

    @property
    def missed_share(self) -> float:
        """Share of real scrobbles that were not sent."""
        return self.missed / self.real if self.real else 0.0

    @property
    def certain_share(self) -> float:
        """Share of decisions the bounds made on their own."""
        return self.certain / self.decisions if self.decisions else 0.0

    @property
    def cost(self) -> int:
        """Weighted errors: a false scrobble counts as much as several missed ones."""
        return FALSE_SCROBBLE_WEIGHT * self.false + self.missed


def normal_duration(rng: random.Random) -> int:
    """A typical track: about 3:45, between 2 and 7 minutes."""
    return int(min(420, max(120, rng.gauss(225, 60))))


def skip_time(rng: random.Random, duration: int) -> float:
    """When a skipped track was skipped: half within its first 30 s, half anywhere in it."""
    if rng.random() < 0.5:
        return rng.uniform(1, min(30, duration))
    return rng.uniform(1, duration)


@dataclass
class Library:
    """Tracks to pick from, with fixed lengths."""

    rng: random.Random
    short_share: float = 0.0
    long_share: float = 0.0
    durations: dict[str, int] = field(default_factory=dict)

    def track(self, track_id: str) -> tuple[str, int]:
        """Return a track and its length, creating it on first use."""
        if track_id not in self.durations:
            roll = self.rng.random()
            if roll < self.short_share:
                self.durations[track_id] = self.rng.randint(15, 45)
            elif roll < self.short_share + self.long_share:
                self.durations[track_id] = self.rng.randint(600, 1200)
            else:
                self.durations[track_id] = normal_duration(self.rng)
        return track_id, self.durations[track_id]

    def random(self, size: int = 400) -> tuple[str, int]:
        """A random track of the library."""
        return self.track(f"t{self.rng.randrange(size)}")


def gap(rng: random.Random) -> float:
    """Time between one track ending and the next starting."""
    return rng.uniform(0, 2)


def end_session(plays: list[TruePlay], rng: random.Random) -> list[TruePlay]:
    """End a session: half the time the last song plays out, half the time listening stops at a random point of it."""
    if plays and rng.random() < STOPPED_SESSION_SHARE:
        last = plays[-1]
        plays[-1] = dataclasses.replace(last, listened=rng.uniform(1, last.duration))
    elif plays:
        plays[-1] = dataclasses.replace(plays[-1], listened=float(plays[-1].duration))
    return plays


def shuffle_plays(rng: random.Random, skip_share: float, *, short: float = 0.0, long: float = 0.0, pauses: bool = False) -> list[TruePlay]:
    """Random tracks; each one is skipped with ``skip_share``, otherwise played to the end, with optional pauses."""
    library = Library(rng, short, long)
    plays: list[TruePlay] = []
    t = 0.0
    for _ in range(rng.randint(15, 30)):
        track, duration = library.random()
        listened = skip_time(rng, duration) if rng.random() < skip_share else float(duration)
        elapsed = listened
        if pauses and rng.random() < 0.2:
            elapsed += rng.uniform(60, 1200)
        plays.append(TruePlay(track, duration, t, listened))
        t += elapsed + gap(rng)
    return plays


def shuffle_session(skip_share: float, *, short: float = 0.0, long: float = 0.0, pauses: bool = False) -> Callable[[random.Random], Session]:
    """Shuffle with ``skip_share`` skips, ended by ``end_session``."""

    def make(rng: random.Random) -> Session:
        return Session(end_session(shuffle_plays(rng, skip_share, short=short, long=long, pauses=pauses), rng))

    return make


def album_session(rng: random.Random) -> Session:
    """An album played through, every track to the end, which ends the session."""
    library = Library(rng)
    album = rng.randrange(1000)
    plays: list[TruePlay] = []
    t = 0.0
    for number in range(rng.randint(8, 14)):
        track, duration = library.track(f"a{album}-{number}")
        plays.append(TruePlay(track, duration, t, float(duration)))
        t += duration + gap(rng)
    return Session(plays)


def fast_skip_session(rng: random.Random) -> Session:
    """Skipping through a playlist: most tracks get 2 to 15 seconds, some are played out."""
    library = Library(rng)
    plays: list[TruePlay] = []
    t = 0.0
    for _ in range(rng.randint(20, 40)):
        track, duration = library.random()
        listened = rng.uniform(2, 15) if rng.random() < 0.7 else float(duration)
        plays.append(TruePlay(track, duration, t, listened))
        t += listened + gap(rng)
    return Session(end_session(plays, rng))


def repeat_session(rng: random.Random) -> Session:
    """Repeats: the same track again right away, or one of the last few again."""
    library = Library(rng)
    plays: list[TruePlay] = []
    t = 0.0
    for _ in range(rng.randint(15, 30)):
        roll = rng.random()
        if plays and roll < 0.25:
            track, duration = plays[-1].track, plays[-1].duration
        elif len(plays) > 2 and roll < 0.4:
            pick = rng.choice(plays[-5:])
            track, duration = pick.track, pick.duration
        else:
            track, duration = library.random()
        listened = skip_time(rng, duration) if rng.random() < 0.2 else float(duration)
        plays.append(TruePlay(track, duration, t, listened))
        t += listened + gap(rng)
    return Session(end_session(plays, rng))


def offline_session(rng: random.Random) -> Session:
    """Shuffle with 20% skips played offline; every row reaches the history when the phone reconnects, 5 to 60 minutes later."""
    plays = end_session(shuffle_plays(rng, 0.2), rng)
    sync = max(p.start + p.listened for p in plays) + rng.uniform(300, 3600)
    return Session([dataclasses.replace(p, appears=sync) for p in plays])


def offline_mid_session(rng: random.Random) -> Session:
    """Shuffle with 20% skips, with a stretch of 6 to 12 plays offline; those rows reach the history when the next online play starts."""
    plays = end_session(shuffle_plays(rng, 0.2), rng)
    first = rng.randint(2, 4)
    last = min(len(plays) - 2, first + rng.randint(6, 12))
    sync = plays[last].start
    return Session([dataclasses.replace(p, appears=sync) if first <= i < last else p for i, p in enumerate(plays)])


def outage_session(rng: random.Random) -> Session:
    """Shuffle with 20% skips while the scrobbler cannot read the history for two hours from some point of the session."""
    plays = end_session(shuffle_plays(rng, 0.2), rng)
    start = rng.uniform(0, max(p.start for p in plays))
    return Session(plays, outage=(start, start + 2 * 3600))


def flicker_session(rng: random.Random) -> Session:
    """Shuffle with 20% skips, while some fetches return an inconsistent list (a row moved up, a row missing, a stale list)."""
    return Session(end_session(shuffle_plays(rng, 0.2), rng), flicker=FLICKER_SHARE)


def mixed_session(rng: random.Random) -> Session:
    """Shuffle with 20% skips in two to four parts, alternating between the phone and a computer whose real-time scrobbler is on.

    At each change of device, half the time the last song is cut short, and
    half the time a pause of 1 to 10 minutes comes before the next part.
    """
    library = Library(rng)
    plays: list[TruePlay] = []
    t = 0.0
    device = rng.choice((PHONE, PC))
    for part in range(rng.randint(2, 4)):
        if part:
            device = PC if device == PHONE else PHONE
            last = plays[-1]
            if rng.random() < 0.5:
                plays[-1] = dataclasses.replace(last, listened=rng.uniform(1, last.duration))
                t = last.start + plays[-1].listened + gap(rng)
            if rng.random() < 0.5:
                t += rng.uniform(60, 600)
        for _ in range(rng.randint(4, 10)):
            track, duration = library.random()
            listened = skip_time(rng, duration) if rng.random() < 0.2 else float(duration)
            plays.append(TruePlay(track, duration, t, listened, device=device))
            t += listened + gap(rng)
    return Session(end_session(plays, rng))


SCENARIOS: dict[str, tuple[str, Callable[[random.Random], Session]]] = {
    "album": ("Album played through", album_session),
    "shuffle_0": ("Shuffle, no skips", shuffle_session(0.0)),
    "shuffle_20": ("Shuffle, 20% skipped", shuffle_session(0.2)),
    "shuffle_50": ("Shuffle, 50% skipped", shuffle_session(0.5)),
    "fast_skip": ("Fast skipping through a playlist", fast_skip_session),
    "repeats": ("Repeats (same track again, or one of the last five)", repeat_session),
    "pauses": ("Pauses of 1 to 20 min", shuffle_session(0.2, pauses=True)),
    "short": ("Many very short tracks (15 to 45 s)", shuffle_session(0.2, short=0.3)),
    "long": ("Many very long tracks (10 to 20 min)", shuffle_session(0.2, long=0.3)),
    "offline": ("Played offline, synced when the phone reconnects", offline_session),
    "offline_mid": ("Offline stretch in a session, synced at the next online play", offline_mid_session),
    "outage": ("History unreadable for two hours", outage_session),
    "flicker": ("Inconsistent lists on 15% of the fetches", flicker_session),
    "mixed": ("Phone and a computer with a real-time scrobbler, taking turns", mixed_session),
}


@dataclass
class Record:
    """A play in the scrobbler's decision log, with the real play it stands for and how it was decided."""

    video_id: str
    detected_at: float
    truth: TruePlay | None
    outcome: str = ""
    certainty: str = ""


def history_at(plays: list[TruePlay], background: list[HistoryItem], t: float) -> list[HistoryItem]:
    """The history at time ``t``: songs by their latest appearance, newest first, one row each."""
    latest: dict[str, TruePlay] = {}
    for play in sorted(plays, key=lambda p: (p.shown, p.start)):
        if play.shown <= t:
            latest[play.track] = play
    rows = [HistoryItem(video_id=p.track, title=p.track, artists=("Artist",), duration=p.duration, played="Today") for p in latest.values()]
    rows.sort(key=lambda item: (latest[item.video_id].shown, latest[item.video_id].start), reverse=True)
    seen = {r.video_id for r in rows}
    return (rows + [b for b in background if b.video_id not in seen])[:HISTORY_LIMIT]


def background_rows() -> list[HistoryItem]:
    """Older history below the session's plays."""
    return [HistoryItem(video_id=f"old{i}", title="old", artists=("Artist",), duration=200, played="Today") for i in range(BACKGROUND_ROWS)]


def flicker(items: list[HistoryItem], previous: list[HistoryItem], rng: random.Random) -> list[HistoryItem]:
    """One inconsistent fetch: an older row listed higher, a row missing, or the previous list again."""
    kind = rng.choice(("up", "missing", "stale"))
    if kind == "stale" and previous:
        return list(previous)
    if len(items) < 4:
        return items
    flickered = list(items)
    index = rng.randrange(2, min(20, len(items)))
    row = flickered.pop(index)
    if kind == "up":
        flickered.insert(rng.randrange(0, index), row)
    return flickered


def trust_every_fetch(snapshot: Sequence[SnapshotEntry] | None, _pending: Pending | None, items: Sequence[HistoryItem], now: float) -> Step:
    """Detection without confirmation, trusting every fetch (only for the comparison)."""
    detection = detect_new_plays(snapshot, items)
    if detection.empty:
        return Step()
    if detection.baseline:
        return Step(snapshot=snapshot_of(items), seen_at=now, kind=BASELINE)
    if detection.reset:
        return Step(snapshot=snapshot_of(items), seen_at=now, kind=RESET, changed=True)
    if not detection.new_items:
        return Step(observed_at=now)
    return Step(accepted=detection.new_items, snapshot=snapshot_of(items), seen_at=now, kind=PLAYS, changed=True, observed_at=now)


class SessionLastfm:
    """Last.fm as a session leaves it: the computer's plays shown as now playing and scrobbled by the real-time scrobbler there."""

    def __init__(self, plays: list[TruePlay], clock: Callable[[], float], now_playing_shown: bool):
        self.plays, self.clock, self.now_playing_shown = plays, clock, now_playing_shown

    def recent_scrobbles(self, _username: str, from_ts: int, to_ts: int | None = None) -> list[Scrobble]:
        """The real-time scrobbler's scrobbles between ``from_ts`` and ``to_ts``, newest first."""
        now = self.clock()
        end = now if to_ts is None else to_ts
        found = [Scrobble("Artist", p.track, "", round(p.start)) for p in self.plays if p.scrobbled_by(now) and from_ts <= round(p.start) <= end]
        return sorted(found, key=lambda s: -s.ts)

    def now_playing(self, _username: str) -> NowPlaying | None:
        """The computer's play playing now, when its scrobbler shows now playing."""
        playing = next((p for p in self.plays if p.device == PC and p.playing_at(self.clock())), None)
        return NowPlaying("Artist", playing.track, "") if playing is not None and self.now_playing_shown else None


@dataclass
class Run:
    """The decision log and the polls of one simulated session."""

    records: list[Record]
    polls: list[float]


def outcome_of(row: dict[str, Any]) -> str:
    """The simulation's outcome for one row of the decision log."""
    if row["status"] == WOULD_SCROBBLE:
        return PLAY
    if row["status"] == SKIPPED:
        return {REASON_REALTIME: DEFER, REASON_DUPLICATE: DUPLICATE}.get(row["reason"], SKIP)
    return ""


def track_session(
    session: Session,
    fastest: float,
    rules: Rules,
    *,
    rng: random.Random,
    confirm: bool = True,
    realtime_gap: float | None = REALTIME_GAP_SECONDS,
    now_playing_shown: bool = True,
    idle: float = IDLE_INTERVAL_SECONDS,
) -> Run:
    """Run one session through the scrobbler's own ``Poller``, on the scheduler's ticks and adaptive pacing.

    The poller runs in dry run with a temporary store, a fake history reader
    (the session's history, its flickers and outages) and a fake Last.fm (the
    real-time scrobbler of the computer). ``realtime_gap`` None turns the
    deferral to real-time scrobblers off; ``now_playing_shown`` False stands
    for a real-time scrobbler that only scrobbles.
    """
    plays = session.plays
    background = background_rows()
    end = max(p.shown + p.listened for p in plays) + TAIL_SECONDS
    clock = {"t": 0.0}
    previous: list[list[HistoryItem]] = [[]]

    def read_history() -> tuple[list[HistoryItem], int]:
        t = clock["t"]
        if session.outage and session.outage[0] <= t <= session.outage[1]:
            raise RuntimeError("Server returned HTTP 503: Service Unavailable")
        items = history_at(plays, background, t)
        fetched = flicker(items, previous[0], rng) if session.flicker and rng.random() < session.flicker else items
        previous[0] = items
        return fetched, 0

    settings = Settings(
        lastfm_user="simulation",
        lastfm_api_key="simulation",
        scrobbler_enabled=True,
        scrobbler_dry_run=True,
        scrobbler_defer_to_realtime=realtime_gap is not None,
    )
    polls: list[float] = []
    with tempfile.TemporaryDirectory(dir=SCRATCH_DIR) as scratch:
        store = ScrobblerStore(Path(scratch) / "scrobbler.db")
        lastfm = SessionLastfm(plays, lambda: clock["t"], now_playing_shown)
        poller = Poller(
            settings,
            store,
            read_history,
            cast("LastfmClient", lastfm),
            now=lambda: clock["t"],
            rules=rules,
            realtime_gap=realtime_gap if realtime_gap is not None else REALTIME_GAP_SECONDS,
            detect=confirm_step if confirm else trust_every_fetch,
        )
        tick = -IDLE_BEFORE_SECONDS + rng.uniform(0, fastest)
        while tick <= end:
            t = tick
            tick += fastest
            if not poll_due(fastest, t, *store.pacing_state(), idle=idle):
                continue
            clock["t"] = t
            polls.append(t)
            poller.run()
        rows = sorted(store.list_plays(limit=100_000)[0], key=lambda r: r["id"])
        store.close()
    records: list[Record] = []
    for row in rows:
        truth = true_play(plays, records, row["video_id"], row["detected_at"])
        records.append(Record(row["video_id"], row["detected_at"], truth, outcome_of(row), row["certainty"]))
    return Run(records, polls)


def true_play(plays: list[TruePlay], records: list[Record], track: str, seen_at: float) -> TruePlay | None:
    """The real play a new record of ``track`` stands for, or None for a phantom.

    It is the latest play of the track shown by ``seen_at`` and after the play
    the track's previous record stands for, taken back to the first of its
    immediate repeats. A window that misses the real start (after a stale
    list) still finds it, so the score shows what the wrong window cost.
    """
    earlier = [r.truth for r in records if r.truth is not None and r.truth.track == track]
    after = max((t.shown for t in earlier), default=float("-inf"))
    order = [i for i, p in enumerate(plays) if p.track == track and after < p.shown <= seen_at]
    if not order:
        return None
    index = max(order, key=lambda i: (plays[i].shown, plays[i].start))
    while index > 0 and plays[index - 1].track == track and plays[index - 1].shown > after:
        index -= 1
    return plays[index]


def hidden_under(plays: list[TruePlay], truth: TruePlay) -> list[TruePlay]:
    """The plays one history row stands for: ``truth`` and its immediate repeats.

    Playing the track on top again changes nothing in the history, so the
    repeats until another track starts are only visible as this one row.
    """
    later = [p for p in plays if p.start >= truth.start]
    run: list[TruePlay] = []
    for play in later:
        if play.track != truth.track:
            break
        run.append(play)
    return run or [truth]


def score(plays: list[TruePlay], run: Run) -> Score:
    """Compare the decisions with Last.fm's rule on the real listening times.

    A play sent from the phone is right when one of the plays its history row
    stands for was a real scrobble, which it then covers; uncovered real
    scrobbles are missed. Plays on the computer belong to its real-time
    scrobbler: sending one is always a false scrobble.
    """
    result = Score(real=sum(1 for p in plays if p.scrobble and p.device == PHONE), polls=len(run.polls))
    covered: set[int] = set()
    for record in run.records:
        if record.truth is None:
            result.phantom += 1
            if record.outcome == PLAY:
                result.sent += 1
                result.false += 1
            continue
        if not record.outcome:
            continue
        result.decisions += 1
        result.certain += record.certainty == CERTAIN
        if record.outcome != PLAY:
            continue
        result.sent += 1
        if record.truth.device == PC:
            result.false += 1
            continue
        real = next((p for p in hidden_under(plays, record.truth) if p.scrobble and id(p) not in covered), None)
        if real is None:
            result.false += 1
        else:
            covered.add(id(real))
    result.missed = sum(1 for p in plays if p.scrobble and p.device == PHONE and id(p) not in covered)
    return result


def score_scenario(key: str, minutes: int, sessions: int, options: dict[str, Any]) -> Score:
    """Score ``sessions`` sessions of one scenario at one fastest interval, from that pair's own seeded random generator."""
    make = SCENARIOS[key][1]
    rng = random.Random(f"{SEED}-{key}-{minutes}")
    total = Score()
    for _ in range(sessions):
        session = make(rng)
        total.add(score(session.plays, track_session(session, minutes * 60.0, rng=rng, **options)))
    return total


def simulate(
    rules: Rules = DEFAULT_RULES,
    *,
    sessions: int = SESSIONS_PER_SCENARIO,
    intervals: tuple[int, ...] = INTERVALS_MINUTES,
    confirm: bool = True,
    realtime_gap: float | None = REALTIME_GAP_SECONDS,
    now_playing_shown: bool = True,
    idle: float = IDLE_INTERVAL_SECONDS,
    scenarios: tuple[str, ...] | None = None,
    workers: int = 1,
) -> dict[str, dict[int, Score]]:
    """Score every scenario (or the ones named) at every fastest interval with one set of rules, in ``workers`` processes."""
    pairs = [(key, minutes) for key in SCENARIOS if scenarios is None or key in scenarios for minutes in intervals]
    options = {"rules": rules, "confirm": confirm, "realtime_gap": realtime_gap, "now_playing_shown": now_playing_shown, "idle": idle}
    keys, minutes_list = [k for k, _m in pairs], [m for _k, m in pairs]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            scores = list(pool.map(score_scenario, keys, minutes_list, [sessions] * len(pairs), [options] * len(pairs)))
    else:
        scores = [score_scenario(key, minutes, sessions, options) for key, minutes in pairs]
    results: dict[str, dict[int, Score]] = {}
    for (key, minutes), result in zip(pairs, scores, strict=True):
        results.setdefault(key, {})[minutes] = result
    return results


def totals(results: dict[str, dict[int, Score]]) -> dict[int, Score]:
    """All scenarios together, per interval."""
    combined: dict[int, Score] = {}
    for per_interval in results.values():
        for minutes, value in per_interval.items():
            combined.setdefault(minutes, Score()).add(value)
    return combined


def pct(value: float) -> str:
    """Percentage with one decimal."""
    return f"{100 * value:.1f}%"


def interval_table(results: dict[str, dict[int, Score]]) -> str:
    """Markdown table: each scenario at each interval, false / missed / certain."""
    intervals = sorted(next(iter(results.values())))
    header = "| Scenario | " + " | ".join(f"Fastest {m} min" for m in intervals) + " |"
    lines = [header, "|---|" + "---|" * len(intervals)]
    for key, (label, _make) in SCENARIOS.items():
        cells = [f"{pct(s.false_share)} / {pct(s.missed_share)} / {pct(s.certain_share)}" for s in (results[key][m] for m in intervals)]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    combined = totals(results)
    cells = [f"**{pct(s.false_share)} / {pct(s.missed_share)} / {pct(s.certain_share)}**" for s in (combined[m] for m in intervals)]
    lines.append("| **All scenarios** | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def comparison_table(title: str, variants: dict[str, dict[int, Score]], chosen: str) -> str:
    """Markdown table: variants over all scenarios, per interval, with the weighted error."""
    intervals = sorted(next(iter(variants.values())))
    lines = [f"| {title} | " + " | ".join(f"Fastest {m} min" for m in intervals) + " |", "|---|" + "---|" * len(intervals)]
    for name, combined in variants.items():
        label = f"`{name}` (chosen)" if name == chosen else f"`{name}`"
        cells = [f"{pct(s.false_share)} / {pct(s.missed_share)} (cost {s.cost})" for s in (combined[m] for m in intervals)]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def polls_line(results: dict[str, dict[int, Score]], sessions: int) -> str:
    """How many history requests adaptive pacing made per simulated session."""
    parts = []
    for minutes, combined in sorted(totals(results).items()):
        parts.append(f"fastest {minutes} min: {combined.polls / (sessions * len(results)):.0f}")
    intro = "Polls per simulated session with adaptive pacing (each session runs from an idle hour before it to two hours after it): "
    return intro + "; ".join(parts) + "."


def idle_table(variants: dict[int, Score], sessions: int) -> str:
    """Markdown table: each idle interval at the default fastest interval, over all scenarios."""
    fastest = SCROBBLER_POLL_MINUTES_DEFAULT
    lines = [
        f"| Idle interval (fastest {fastest} min) | False / missed / certain | Polls per session |",
        "|---|---|---|",
    ]
    for minutes, s in variants.items():
        label = f"{minutes} min (default)" if minutes * 60 == IDLE_INTERVAL_SECONDS else f"{minutes} min"
        polls = s.polls / (sessions * len(SCENARIOS))
        lines.append(f"| {label} | {pct(s.false_share)} / {pct(s.missed_share)} / {pct(s.certain_share)} | {polls:.0f} |")
    return "\n".join(lines)


def render(sessions: int) -> list[str]:
    """Every table of the docs block, chosen rules first; the scenarios run in parallel processes."""
    run = functools.partial(simulate, sessions=sessions, workers=WORKERS)
    chosen = run(DEFAULT_RULES)
    base = totals(chosen)

    def variant(**changes: object) -> dict[int, Score]:
        rules = dataclasses.replace(DEFAULT_RULES, **changes)
        return base if rules == DEFAULT_RULES else totals(run(rules))

    tiebreaks = {name: variant(tiebreak=name) for name in TIEBREAKS}
    ends = {name: variant(end_unknown=name) for name in END_MODELS}
    timings = {name: variant(timing_unknown=name) for name in TIMING_MODELS}
    bursts = {f"{seconds:g} s": variant(burst_seconds=seconds) for seconds in (3.0, 5.0, 10.0, 20.0)}
    confirmation = {"confirmed by the next poll": base, "every fetch trusted": totals(run(DEFAULT_RULES, confirm=False))}

    def mixed(gap: float | None, shown: bool = True) -> dict[int, Score]:
        if gap == REALTIME_GAP_SECONDS and shown:
            return chosen["mixed"]
        return run(DEFAULT_RULES, realtime_gap=gap, now_playing_shown=shown, scenarios=("mixed",))["mixed"]

    deferral = {
        "off": mixed(None),
        **{f"gap {m} min": mixed(m * 60.0) for m in GAP_VARIANTS_MINUTES},
        **{f"gap {m} min, no now playing": mixed(m * 60.0, shown=False) for m in GAP_VARIANTS_MINUTES},
    }

    def idle(minutes: int) -> Score:
        if minutes * 60 == IDLE_INTERVAL_SECONDS:
            return base[SCROBBLER_POLL_MINUTES_DEFAULT]
        return totals(run(DEFAULT_RULES, intervals=(SCROBBLER_POLL_MINUTES_DEFAULT,), idle=minutes * 60.0))[SCROBBLER_POLL_MINUTES_DEFAULT]

    idles = {minutes: idle(minutes) for minutes in IDLE_VARIANTS_MINUTES}
    return [
        interval_table(chosen),
        polls_line(chosen, sessions),
        comparison_table("Tie-break", tiebreaks, DEFAULT_RULES.tiebreak),
        comparison_table("End unknown", ends, DEFAULT_RULES.end_unknown),
        comparison_table("Timing unknown", timings, DEFAULT_RULES.timing_unknown),
        comparison_table("Burst: seconds per play", bursts, f"{DEFAULT_RULES.burst_seconds:g} s"),
        comparison_table("New rows", confirmation, "confirmed by the next poll"),
        comparison_table("Real-time deferral (mixed devices)", deferral, f"gap {REALTIME_GAP_SECONDS // 60:g} min"),
        idle_table(idles, sessions),
    ]


def docs_block(sessions: int) -> str:
    """The generated block for docs/scrobbler.md."""
    main, polls, tiebreaks, ends, timings, bursts, confirmation, deferral, idles = render(sessions)
    weight = FALSE_SCROBBLE_WEIGHT
    return "\n".join(
        [
            "Each cell: **false scrobbles** (share of sent scrobbles that should not exist) / **missed scrobbles** "
            "(share of real ones not sent) / **certain** (share of decisions the bounds made without a model or tie-break).",
            "",
            main,
            "",
            polls,
            "",
            f"Variants compared over all scenarios (false / missed, and the cost: {weight} per false scrobble, 1 per missed one). "
            "Each table changes one choice and keeps the others; the last one only concerns the mixed-device scenario:",
            "",
            tiebreaks,
            "",
            ends,
            "",
            timings,
            "",
            bursts,
            "",
            confirmation,
            "",
            deferral,
            "",
            "The idle interval (all scenarios, at the default fastest interval; the polls include an idle hour before "
            "and two hours after each session):",
            "",
            idles,
        ]
    )


def replace_section(text: str, block: str) -> str | None:
    """``text`` with the body of the ``SECTION`` heading (up to the next heading) replaced by ``block``, or None without it."""
    heading = text.find(f"\n{SECTION}\n")
    if heading < 0:
        return None
    body = heading + len(SECTION) + 2
    following = text.find("\n#", body)
    if following < 0:
        return None
    return text[:body] + "\n" + block + "\n" + text[following:]


def main() -> int:
    """Print the tables, or update or check docs/scrobbler.md."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="update the table in docs/scrobbler.md")
    parser.add_argument("--check", action="store_true", help="fail when docs/scrobbler.md is out of date")
    parser.add_argument("--sessions", type=int, default=SESSIONS_PER_SCENARIO)
    args = parser.parse_args()
    block = docs_block(args.sessions)
    if not args.write and not args.check:
        print(block)
        return 0
    text = DOCS.read_text(encoding="utf-8")
    updated = replace_section(text, block)
    if updated is None:
        print(f"No '{SECTION}' section followed by another heading in {DOCS}", file=sys.stderr)
        return 1
    if args.check:
        if updated != text:
            print("docs/scrobbler.md simulation table is out of date; run with --write", file=sys.stderr)
            return 1
        return 0
    DOCS.write_text(updated, encoding="utf-8")
    print(f"Updated {DOCS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
