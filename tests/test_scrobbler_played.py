import random

import pytest

from src.scrobbler.played import (
    CERTAIN,
    DEFAULT_RULES,
    END_MODELS,
    END_SLACK_SECONDS,
    END_UNKNOWN,
    ESTIMATED,
    LONG_WINDOW_SECONDS,
    OPEN,
    PAUSE_WINDOW_SECONDS,
    PLAY,
    SKIP,
    TIEBREAKS,
    TIMING_MODELS,
    TIMING_UNKNOWN,
    Evidence,
    Rules,
    Undecided,
    assess,
    certain_only_tiebreak,
    chain_starts,
    end_unknown,
    listening_bounds,
    midpoint_tiebreak,
    play_probability,
    shared_durations,
    shared_midpoint_tiebreak,
    spread_starts,
    threshold_seconds,
    timing_unknown,
)

pytestmark = pytest.mark.usefixtures("no_network")

T0 = 1_000_000.0


def later(duration=200, window=(T0 - 120, T0), next_window=(T0 + 120, T0 + 240), count=1, next_count=1):
    return Evidence(
        duration=duration,
        window_start=window[0],
        window_end=window[1],
        position=count - 1,
        count=count,
        next_window_start=next_window[0],
        next_window_end=next_window[1],
        next_count=next_count,
    )


def same_window(duration=200, window=(T0 - 300, T0), position=0, count=2, shared=()):
    return Evidence(
        duration=duration,
        window_start=window[0],
        window_end=window[1],
        position=position,
        count=count,
        next_window_start=window[0],
        next_window_end=window[1],
        next_count=count,
        shared_durations=shared,
    )


def test_threshold_is_half_the_track_up_to_four_minutes():
    assert threshold_seconds(200) == 100
    assert threshold_seconds(600) == 240


def test_open_play_lower_bound_grows_with_time_on_top():
    open_play = Evidence(duration=200, window_start=T0 - 120, window_end=T0)
    assert listening_bounds(open_play, T0 + 90) == (90, 200)
    assert listening_bounds(open_play, T0 + 900) == (200, 200)


def test_bounds_from_the_next_play_in_a_later_window():
    evidence = later(next_window=(T0 + 120, T0 + 240))
    assert listening_bounds(evidence, T0 + 999) == (120, 200)
    assert listening_bounds(later(duration=600), T0) == (120, 360)


def test_next_play_in_the_very_next_window_leaves_lo_at_zero():
    assert listening_bounds(later(duration=600, next_window=(T0, T0 + 120)), T0 + 999) == (0, 240)
    assert listening_bounds(later(next_window=(T0, T0 + 120)), T0 + 999) == (0, 200)


def test_play_ended_inside_its_own_window_is_bounded_by_the_window():
    assert listening_bounds(same_window(window=(T0 - 60, T0)), T0) == (0, 60)


def test_too_short_tracks_are_certain_skips():
    verdict = assess(Evidence(duration=30, window_start=T0 - 60, window_end=T0), T0 + 999)
    assert (verdict.outcome, verdict.certainty) == (SKIP, CERTAIN)


def test_hi_below_the_threshold_is_a_certain_skip():
    verdict = assess(same_window(duration=400, window=(T0 - 120, T0)), T0)
    assert (verdict.outcome, verdict.certainty) == (SKIP, CERTAIN)
    assert verdict.hi == 120 < verdict.threshold == 200


def test_lo_at_the_threshold_is_a_certain_play():
    verdict = assess(later(duration=200, next_window=(T0 + 100, T0 + 220)), T0 + 999)
    assert (verdict.outcome, verdict.certainty) == (PLAY, CERTAIN)
    assert verdict.lo == verdict.threshold == 100


def test_newest_play_stays_open_while_it_could_still_be_playing():
    open_play = Evidence(duration=200, window_start=T0 - 120, window_end=T0)
    assert assess(open_play, T0 + 100).outcome == OPEN
    assert assess(open_play, T0 + 200 + END_SLACK_SECONDS).outcome == OPEN


def test_newest_play_on_top_longer_than_it_lasts_has_an_unknown_end():
    open_play = Evidence(duration=200, window_start=T0 - 120, window_end=T0)
    for name in ("count", "skip"):
        verdict = assess(open_play, T0 + 200 + END_SLACK_SECONDS + 1, Rules(end_unknown=name))
        assert (verdict.outcome, verdict.certainty, verdict.basis) == (PLAY if name == "count" else SKIP, ESTIMATED, END_UNKNOWN)


def test_next_play_starting_after_this_one_could_have_ended_means_an_unknown_end():
    longest = 200 + END_SLACK_SECONDS
    in_time = later(next_window=(T0 + longest, T0 + longest + 120))
    assert not end_unknown(in_time, T0 + 9999, False)
    gap = later(next_window=(T0 + longest + 1, T0 + longest + 121))
    assert end_unknown(gap, T0 + 9999, False)
    verdict = assess(gap, T0 + 9999, Rules(end_unknown="skip"))
    assert (verdict.outcome, verdict.certainty, verdict.basis) == (SKIP, ESTIMATED, END_UNKNOWN)
    assert assess(gap, T0 + 9999, Rules(end_unknown="count")).outcome == PLAY


def test_a_gap_is_never_a_certain_play_even_with_lo_far_above_the_threshold():
    gap = later(next_window=(T0 + 3600, T0 + 3720))
    assert listening_bounds(gap, T0)[0] >= threshold_seconds(200)
    assert assess(gap, T0 + 9999, Rules(end_unknown="count")).certainty == ESTIMATED


def test_pause_window_counts_a_pause_and_skips_a_stop():
    could_end = T0 + 200
    paused = later(next_window=(could_end + PAUSE_WINDOW_SECONDS, could_end + PAUSE_WINDOW_SECONDS + 120))
    assert assess(paused, T0 + 9999, Rules(end_unknown="pause_window")).outcome == PLAY
    stopped = later(next_window=(could_end + PAUSE_WINDOW_SECONDS + 1, could_end + PAUSE_WINDOW_SECONDS + 121))
    assert assess(stopped, T0 + 9999, Rules(end_unknown="pause_window")).outcome == SKIP
    open_play = Evidence(duration=200, window_start=T0 - 120, window_end=T0)
    waiting = assess(open_play, could_end + PAUSE_WINDOW_SECONDS, Rules(end_unknown="pause_window"))
    assert (waiting.outcome, waiting.certainty, waiting.basis) == (OPEN, "", END_UNKNOWN)
    assert assess(open_play, could_end + PAUSE_WINDOW_SECONDS + 1, Rules(end_unknown="pause_window")).outcome == SKIP


def test_more_plays_than_fit_in_the_window_is_a_burst_with_unknown_timing():
    rules = Rules(burst_seconds=10)
    assert not timing_unknown(6, 60, rules)
    assert timing_unknown(7, 60, rules)
    assert not timing_unknown(1, 5, rules)
    assert timing_unknown(1, LONG_WINDOW_SECONDS + 1, rules)
    burst = same_window(window=(T0 - 60, T0), count=8)
    for name in ("count", "skip"):
        verdict = assess(burst, T0 + 9999, Rules(timing_unknown=name, burst_seconds=10))
        assert (verdict.outcome, verdict.certainty, verdict.basis) == (PLAY if name == "count" else SKIP, ESTIMATED, TIMING_UNKNOWN)


def test_play_before_a_burst_has_an_unknown_end():
    before = later(next_window=(T0 + 60, T0 + 120), next_count=20)
    verdict = assess(before, T0 + 9999, Rules(end_unknown="skip", burst_seconds=10))
    assert (verdict.outcome, verdict.basis) == (SKIP, END_UNKNOWN)
    assert assess(before, T0 + 9999, Rules(end_unknown="pause_window", burst_seconds=10)).outcome == SKIP


def test_plays_after_a_long_outage_have_unknown_timing():
    after_outage = Evidence(duration=200, window_start=T0 - 2 * 3600, window_end=T0)
    verdict = assess(after_outage, T0 + 60, Rules(timing_unknown="count"))
    assert (verdict.outcome, verdict.basis) == (PLAY, TIMING_UNKNOWN)


def test_every_model_is_registered_and_the_defaults_exist():
    assert set(END_MODELS) == {"count", "skip", "pause_window"}
    assert set(TIMING_MODELS) == {"count", "skip"}
    assert DEFAULT_RULES.tiebreak in TIEBREAKS
    assert DEFAULT_RULES.end_unknown in END_MODELS
    assert DEFAULT_RULES.timing_unknown in TIMING_MODELS


def test_burst_starts_are_laid_back_to_back_up_to_the_poll():
    assert chain_starts([100, 200, 300], 1000) == [400, 500, 700]


def test_bounds_around_the_threshold_go_to_the_tiebreak():
    calls = []

    def tiebreak(case):
        calls.append(case)
        return True, 0.9

    verdict = assess(later(next_window=(T0, T0 + 120)), T0 + 999, tiebreak=tiebreak)
    assert (verdict.outcome, verdict.certainty, verdict.estimate) == (PLAY, ESTIMATED, 0.9)
    (case,) = calls
    assert (case.lo, case.hi, case.threshold) == (0, 200, 100)


def test_default_tiebreak_is_even_chance():
    verdict = assess(later(next_window=(T0, T0 + 120)), T0 + 999)
    assert verdict.certainty == ESTIMATED
    assert verdict.outcome == (PLAY if verdict.estimate >= 0.5 else SKIP)


def test_same_window_probability_follows_the_spacing_formula():
    evidence = same_window(window=(T0 - 300, T0), count=2)
    assert play_probability(evidence, 100) == pytest.approx((1 - 100 / 300) ** 2)
    assert play_probability(same_window(window=(T0, T0), count=2), 100) == 0.0


def monte_carlo(evidence, threshold, runs=200_000):
    rng = random.Random(7)
    hits = 0
    for _ in range(runs):
        own = max(rng.uniform(evidence.window_start, evidence.window_end) for _ in range(evidence.count))
        nxt = min(rng.uniform(evidence.next_window_start, evidence.next_window_end) for _ in range(evidence.next_count))
        hits += nxt - own >= threshold
    return hits / runs


@pytest.mark.parametrize(
    ("evidence", "threshold"),
    [
        (later(window=(T0 - 120, T0), next_window=(T0, T0 + 120)), 100),
        (later(window=(T0 - 300, T0), next_window=(T0, T0 + 300), count=2, next_count=3), 112),
        (later(window=(T0 - 120, T0), next_window=(T0 + 240, T0 + 360)), 300),
    ],
)
def test_later_window_probability_matches_a_monte_carlo_estimate(evidence, threshold):
    assert play_probability(evidence, threshold) == pytest.approx(monte_carlo(evidence, threshold), abs=0.01)


def test_probability_is_zero_while_the_play_is_open():
    assert play_probability(Evidence(duration=200, window_start=T0 - 60, window_end=T0), 100) == 0.0


def test_midpoint_and_shared_midpoint():
    case = Undecided(same_window(window=(T0 - 300, T0), count=4, shared=(200, 200, 200)), 0, 200, 100)
    assert midpoint_tiebreak(case) == (True, 100)
    counts, value = shared_midpoint_tiebreak(case)
    assert value == pytest.approx(100 * 300 / 300)
    four = Undecided(same_window(window=(T0 - 300, T0), count=5, shared=(200, 200, 200, 200)), 0, 200, 100)
    counts, value = shared_midpoint_tiebreak(four)
    assert value == pytest.approx(75)
    assert counts is False


def test_certain_only_never_counts_an_open_case():
    assert certain_only_tiebreak(Undecided(later(), 0, 200, 100))[0] is False


def test_every_tiebreak_is_registered():
    assert set(TIEBREAKS) == {"midpoint", "shared_midpoint", "probability_50", "probability_75", "certain_only"}


def test_starts_are_spread_evenly_over_the_window():
    assert spread_starts(1, 0, 300) == [150]
    assert spread_starts(3, 0, 400) == [100, 200, 300]


def test_shared_durations_are_all_but_the_newest():
    assert shared_durations([180, 200, 220]) == (180, 200)
    assert shared_durations([180]) == ()
