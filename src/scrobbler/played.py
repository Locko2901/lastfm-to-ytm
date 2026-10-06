"""Whether a play counts: listening-time bounds from the polls against Last.fm's threshold.

``lo`` and ``hi`` bound the listening time; ``hi < T`` is a certain skip and
``lo >= T`` a certain play, otherwise a tie-break decides. Plays whose end or
timing the history does not show are decided by explicit models. The rule and
the simulation behind ``DEFAULT_RULES`` are explained in docs/scrobbler.md.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

MIN_TRACK_SECONDS = 30
MAX_THRESHOLD_SECONDS = 240
INTEGRATION_STEPS = 400
END_SLACK_SECONDS = 30
LONG_WINDOW_SECONDS = 30 * 60
PAUSE_WINDOW_SECONDS = 30 * 60

PLAY = "play"
SKIP = "skip"
OPEN = "open"
CERTAIN = "certain"
ESTIMATED = "estimated"
BOUNDS = "bounds"
END_UNKNOWN = "end_unknown"
TIMING_UNKNOWN = "timing_unknown"


def threshold_seconds(duration: int) -> float:
    """Listening time Last.fm requires: half the track or 4 minutes, whichever is less."""
    return min(duration / 2, MAX_THRESHOLD_SECONDS)


@dataclass(frozen=True, slots=True)
class Evidence:
    """What the polls show about one play.

    ``window_start``/``window_end`` are the polls around its start, ``position``
    and ``count`` its place among the new rows of that poll (0 = oldest). The
    ``next_*`` fields describe the start of the play that followed it, once
    there is one. ``shared_durations`` lists the track lengths of every play
    that started and ended inside this play's window, this one included.
    """

    duration: int
    window_start: float
    window_end: float
    position: int = 0
    count: int = 1
    next_window_start: float | None = None
    next_window_end: float | None = None
    next_count: int = 1
    shared_durations: tuple[int, ...] = ()

    @property
    def superseded(self) -> bool:
        """True once a later play started."""
        return self.next_window_start is not None and self.next_window_end is not None

    @property
    def window(self) -> float:
        """Length of the window its start lies in."""
        return max(0.0, self.window_end - self.window_start)

    @property
    def next_window(self) -> float:
        """Length of the window the next play started in (0 while there is none)."""
        if self.next_window_start is None or self.next_window_end is None:
            return 0.0
        return max(0.0, self.next_window_end - self.next_window_start)


@dataclass(frozen=True, slots=True)
class Verdict:
    """The played-rule decision for one play, with the evidence behind it."""

    outcome: str
    certainty: str
    lo: float
    hi: float
    threshold: float
    estimate: float | None = None
    basis: str = BOUNDS


def listening_bounds(evidence: Evidence, now: float) -> tuple[float, float]:
    """Return ``(lo, hi)``: the least and most listening time the polls allow, in seconds."""
    duration = float(evidence.duration)
    if evidence.next_window_start is None or evidence.next_window_end is None:
        lo = now - evidence.window_end
        hi = duration
    else:
        lo = evidence.next_window_start - evidence.window_end
        hi = evidence.next_window_end - evidence.window_start
    return min(duration, max(0.0, lo)), min(duration, max(0.0, hi))


@dataclass(frozen=True, slots=True)
class Undecided:
    """A play whose bounds straddle the threshold: what a tie-break gets to decide on."""

    evidence: Evidence
    lo: float
    hi: float
    threshold: float


TieBreak = Callable[[Undecided], tuple[bool, float]]


def midpoint_tiebreak(case: Undecided) -> tuple[bool, float]:
    """Count the play when the middle of ``lo`` and ``hi`` reaches the threshold."""
    middle = (case.lo + case.hi) / 2
    return middle >= case.threshold, middle


def shared_midpoint_tiebreak(case: Undecided) -> tuple[bool, float]:
    """Midpoint, with the midpoints of plays that shared one window capped to its length together."""
    evidence = case.evidence
    middle = (case.lo + case.hi) / 2
    shared = evidence.shared_durations
    if evidence.superseded and evidence.position < evidence.count - 1 and len(shared) > 1:
        middles = [min(float(d), evidence.window) / 2 for d in shared]
        total = sum(middles)
        if total > evidence.window > 0:
            middle *= evidence.window / total
    return middle >= case.threshold, middle


def play_probability(evidence: Evidence, threshold: float) -> float:
    """Chance that the play reached ``threshold`` if every start is anywhere in its window, equally likely.

    Plays sharing a window are spread over it in their known order: the gap
    between two of ``n`` such starts exceeds ``x`` with probability
    ``(1 - x / window) ** n``.
    """
    if not evidence.superseded:
        return 0.0
    assert evidence.next_window_start is not None and evidence.next_window_end is not None
    window = evidence.window
    if evidence.position < evidence.count - 1:
        if window <= 0:
            return 1.0 if threshold <= 0 else 0.0
        return max(0.0, 1 - threshold / window) ** evidence.count

    next_window = max(0.0, evidence.next_window_end - evidence.next_window_start)
    offset = evidence.next_window_start - evidence.window_start

    def next_start_at_least(y: float) -> float:
        if y <= 0:
            return 1.0
        if y >= next_window:
            return 0.0
        return (1 - y / next_window) ** evidence.next_count

    if window <= 0:
        return next_start_at_least(threshold - offset)
    total = 0.0
    step = window / INTEGRATION_STEPS
    for i in range(INTEGRATION_STEPS):
        x = (i + 0.5) * step
        density = evidence.count * (x ** (evidence.count - 1)) / (window**evidence.count)
        total += density * next_start_at_least(threshold - offset + x) * step
    return min(1.0, max(0.0, total))


def probability_tiebreak(cutoff: float) -> TieBreak:
    """Count the play when ``play_probability`` reaches ``cutoff``."""

    def decide(case: Undecided) -> tuple[bool, float]:
        chance = play_probability(case.evidence, case.threshold)
        return chance >= cutoff, chance

    return decide


def certain_only_tiebreak(case: Undecided) -> tuple[bool, float]:
    """Never count a play the bounds leave open."""
    return False, (case.lo + case.hi) / 2


TIEBREAKS: dict[str, TieBreak] = {
    "midpoint": midpoint_tiebreak,
    "shared_midpoint": shared_midpoint_tiebreak,
    "probability_50": probability_tiebreak(0.5),
    "probability_75": probability_tiebreak(0.75),
    "certain_only": certain_only_tiebreak,
}


@dataclass(frozen=True, slots=True)
class EndUnknown:
    """A play whose end the history does not show: what an end model gets to decide on."""

    evidence: Evidence
    now: float
    next_timing_unknown: bool


EndModel = Callable[[EndUnknown], str]
TimingModel = Callable[[Evidence], str]


def count_end(case: EndUnknown) -> str:
    """Count every play whose end is unknown."""
    del case
    return PLAY


def skip_end(case: EndUnknown) -> str:
    """Count no play whose end is unknown."""
    del case
    return SKIP


def pause_window_end(case: EndUnknown) -> str:
    """Count it when the next play started within 30 minutes of when this one could have ended (a pause), else not (a stop).

    Without a next play, it waits until those 30 minutes are over.
    """
    evidence = case.evidence
    could_end = evidence.window_end + evidence.duration
    if evidence.next_window_start is not None:
        if case.next_timing_unknown:
            return SKIP
        return PLAY if evidence.next_window_start - could_end <= PAUSE_WINDOW_SECONDS else SKIP
    return SKIP if case.now - could_end > PAUSE_WINDOW_SECONDS else OPEN


END_MODELS: dict[str, EndModel] = {"count": count_end, "skip": skip_end, "pause_window": pause_window_end}


def count_timing(evidence: Evidence) -> str:
    """Count every play whose timing is unknown."""
    del evidence
    return PLAY


def skip_timing(evidence: Evidence) -> str:
    """Count no play whose timing is unknown."""
    del evidence
    return SKIP


TIMING_MODELS: dict[str, TimingModel] = {"count": count_timing, "skip": skip_timing}


@dataclass(frozen=True, slots=True)
class Rules:
    """The choices behind the played rule; the simulation compares variants of each."""

    tiebreak: str = "probability_50"
    end_unknown: str = "count"
    timing_unknown: str = "count"
    burst_seconds: float = 5.0


DEFAULT_RULES = Rules()
DEFAULT_TIEBREAK = DEFAULT_RULES.tiebreak


def timing_unknown(count: int, window: float, rules: Rules = DEFAULT_RULES) -> bool:
    """True for a window too long to bound anything, or with more new plays than could start in it at a few seconds each."""
    return window > LONG_WINDOW_SECONDS or count > max(1.0, window / rules.burst_seconds)


def end_unknown(evidence: Evidence, now: float, next_timing_unknown: bool) -> bool:
    """True when listening stopped or paused at a time the history does not show.

    The next play started later than this one could have lasted (its earliest
    start minus this one's latest start exceeds the track length plus a small
    slack), its timing is unknown, or nothing followed and the play has been
    on top longer than that.
    """
    longest = evidence.duration + END_SLACK_SECONDS
    if evidence.next_window_start is not None:
        return next_timing_unknown or evidence.next_window_start - evidence.window_end > longest
    return now - evidence.window_end > longest


def assess(evidence: Evidence, now: float, rules: Rules = DEFAULT_RULES, tiebreak: TieBreak | None = None) -> Verdict:
    """Decide the play now: ``play`` or ``skip``, certain or estimated, or ``open`` while undecidable."""
    duration = float(evidence.duration)
    threshold = threshold_seconds(evidence.duration)
    if evidence.duration <= MIN_TRACK_SECONDS:
        return Verdict(SKIP, CERTAIN, 0.0, duration, threshold)
    if timing_unknown(evidence.count, evidence.window, rules):
        outcome = TIMING_MODELS[rules.timing_unknown](evidence)
        return Verdict(outcome, ESTIMATED, 0.0, duration, threshold, basis=TIMING_UNKNOWN)
    next_unknown = evidence.superseded and timing_unknown(evidence.next_count, evidence.next_window, rules)
    if end_unknown(evidence, now, next_unknown):
        outcome = END_MODELS[rules.end_unknown](EndUnknown(evidence, now, next_unknown))
        certainty = "" if outcome == OPEN else ESTIMATED
        return Verdict(outcome, certainty, 0.0, duration, threshold, basis=END_UNKNOWN)
    if not evidence.superseded:
        return Verdict(OPEN, "", 0.0, duration, threshold)
    lo, hi = listening_bounds(evidence, now)
    if hi < threshold:
        return Verdict(SKIP, CERTAIN, lo, hi, threshold)
    if lo >= threshold:
        return Verdict(PLAY, CERTAIN, lo, hi, threshold)
    counts, value = (tiebreak or TIEBREAKS[rules.tiebreak])(Undecided(evidence, lo, hi, threshold))
    return Verdict(PLAY if counts else SKIP, ESTIMATED, lo, hi, threshold, value)


def chain_starts(durations: Sequence[int], end: float) -> list[float]:
    """Starts of plays laid back to back at full length, the newest ending at ``end``; oldest first."""
    starts: list[float] = []
    position = end
    for duration in reversed(durations):
        position -= duration
        starts.append(position)
    return list(reversed(starts))


def spread_starts(count: int, window_start: float, window_end: float) -> list[float]:
    """Estimated starts of ``count`` plays found in one window, oldest first: evenly spread over it."""
    span = max(0.0, window_end - window_start)
    return [window_start + span * (i + 1) / (count + 1) for i in range(count)]


def shared_durations(durations: Sequence[int]) -> tuple[int, ...]:
    """Durations of the plays of one window that also ended in it: all but the newest."""
    return tuple(durations[:-1]) if len(durations) > 1 else ()
