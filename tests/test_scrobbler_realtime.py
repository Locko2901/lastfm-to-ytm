import pytest

from src.scrobbler.realtime import CLOCK_SLACK_SECONDS, REALTIME_GAP_SECONDS, Period, active_during, active_periods, usable_sightings

pytestmark = pytest.mark.usefixtures("no_network")

T0 = 1_700_000_000.0


def playing(*times):
    return [(t, True) for t in times]


def test_sightings_and_scrobbles_within_the_gap_form_one_period():
    periods = active_periods(playing(T0 + 60, T0 + 180), [T0, T0 + 240])
    assert periods == [Period(T0 - CLOCK_SLACK_SECONDS, T0 + 240 + CLOCK_SLACK_SECONDS, 4)]


def test_a_longer_silence_than_the_gap_ends_the_period():
    at_gap = active_periods(playing(T0, T0 + REALTIME_GAP_SECONDS), [])
    assert at_gap == [Period(T0, T0 + REALTIME_GAP_SECONDS, 2)]
    beyond = active_periods(playing(T0, T0 + REALTIME_GAP_SECONDS + 1), [])
    assert beyond == [Period(T0, T0, 1), Period(T0 + REALTIME_GAP_SECONDS + 1, T0 + REALTIME_GAP_SECONDS + 1, 1)]


def test_a_poll_that_saw_the_real_time_scrobbler_idle_splits_the_period():
    sightings = [(T0, True), (T0 + 120, False), (T0 + 240, True)]
    assert active_periods(sightings, []) == [Period(T0, T0, 1), Period(T0 + 240, T0 + 240, 1)]
    assert active_periods([(T0 + 120, False)], []) == []


def test_a_scrobble_reaches_half_a_minute_either_way_for_another_clock():
    (period,) = active_periods([], [T0])
    assert (period.start, period.end) == (T0 - CLOCK_SLACK_SECONDS, T0 + CLOCK_SLACK_SECONDS)


def test_the_gap_is_a_parameter():
    assert len(active_periods(playing(T0, T0 + 400), [], gap=300)) == 2
    assert len(active_periods(playing(T0, T0 + 400), [], gap=600)) == 1


def test_a_play_is_inside_when_its_start_window_overlaps_a_period():
    periods = [Period(T0, T0 + 300, 3)]
    assert active_during(periods, T0 - 60, T0) == periods[0]
    assert active_during(periods, T0 + 300 - 1, T0 + 360) == periods[0]
    assert active_during(periods, T0 + 300, T0 + 360) is None
    assert active_during(periods, T0 - 120, T0 - 1) is None
    assert active_during([], T0, T0 + 60) is None


def test_idle_polls_count_only_once_the_real_time_scrobbler_was_seen_playing():
    sightings = [(T0, False), (T0 + 120, False)]
    assert usable_sightings(sightings, reports_now_playing=True) == sightings
    assert usable_sightings(sightings, reports_now_playing=False) == []
    chained = active_periods(usable_sightings(sightings, False), [T0 - 60, T0 + 200])
    assert len(chained) == 1
