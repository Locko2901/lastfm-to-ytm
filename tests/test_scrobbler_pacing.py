import pytest

from src.scrobbler.pacing import (
    BACKOFF,
    FAST,
    IDLE,
    IDLE_AFTER_SECONDS,
    IDLE_INTERVAL_SECONDS,
    MAX_ERROR_INTERVAL_SECONDS,
    next_poll_at,
    pace,
    poll_due,
)
from src.scrobbler.store import ScrobblerStore

pytestmark = pytest.mark.usefixtures("no_network")

T0 = 1_700_000_000.0
FASTEST = 120.0


def test_polls_at_the_fastest_interval_while_the_history_changes():
    assert pace(FASTEST, T0, T0 - 600, 0) == (FAST, FASTEST)
    assert pace(FASTEST, T0, T0 - IDLE_AFTER_SECONDS, 0) == (FAST, FASTEST)


def test_slows_down_to_the_idle_interval_after_half_an_hour_without_a_change():
    assert pace(FASTEST, T0, T0 - IDLE_AFTER_SECONDS - 1, 0) == (IDLE, IDLE_INTERVAL_SECONDS)
    assert pace(FASTEST, T0, None, 0) == (IDLE, IDLE_INTERVAL_SECONDS)
    assert pace(FASTEST, T0, None, 0, idle=900) == (IDLE, 900)
    assert pace(FASTEST, T0, None, 0, idle=300) == (IDLE, 300)
    assert pace(1200.0, T0, None, 0) == (IDLE, 1200.0)
    assert pace(FASTEST, T0, T0, 0, idle=900) == (FAST, FASTEST)


def test_backs_off_after_failed_reads_up_to_half_an_hour():
    assert pace(FASTEST, T0, T0, 1) == (BACKOFF, 240)
    assert pace(FASTEST, T0, T0, 3) == (BACKOFF, 960)
    assert pace(FASTEST, T0, T0, 10) == (BACKOFF, MAX_ERROR_INTERVAL_SECONDS)


def test_a_tick_polls_once_the_interval_has_passed():
    assert poll_due(FASTEST, T0, None, None, 0)
    assert poll_due(FASTEST, T0, T0 - FASTEST, T0 - 60, 0)
    assert poll_due(FASTEST, T0, T0 - FASTEST + 3, T0 - 60, 0)
    assert not poll_due(FASTEST, T0, T0 - 60, T0 - 60, 0)
    assert not poll_due(FASTEST, T0, T0 - 300, None, 0)
    assert poll_due(FASTEST, T0, T0 - IDLE_INTERVAL_SECONDS, None, 0)


def test_the_first_change_after_idle_brings_the_fast_pace_back():
    quiet = T0 - 2 * IDLE_AFTER_SECONDS
    assert not poll_due(FASTEST, T0, T0 - FASTEST, quiet, 0)
    assert poll_due(FASTEST, T0, T0 - FASTEST, T0 - FASTEST, 0)


def test_next_poll_is_the_first_due_tick():
    assert next_poll_at(T0 + 30, FASTEST, T0, None, 0) == T0 + 30 + 5 * FASTEST
    assert next_poll_at(T0 + 30, FASTEST, T0, T0, 0) == T0 + 30 + FASTEST
    assert next_poll_at(T0 + 30, FASTEST, None, None, 0) == T0 + 30
    assert next_poll_at(T0 + 30, FASTEST, T0, None, 0, idle=3600) == T0 + 30 + 30 * FASTEST


def test_the_idle_interval_decides_when_a_quiet_history_is_read_again():
    quiet = T0 - 2 * IDLE_AFTER_SECONDS
    assert not poll_due(FASTEST, T0, T0 - 840, quiet, 0, idle=900)
    assert poll_due(FASTEST, T0, T0 - 900, quiet, 0, idle=900)
    assert poll_due(FASTEST, T0, T0 - 300, quiet, 0, idle=300)


def test_store_remembers_changes_and_failures_in_a_row(tmp_path):
    store = ScrobblerStore(tmp_path / "scrobbler.db")
    assert store.pacing_state() == (None, None, 0)
    store.start_poll(T0, True)
    store.record_pacing(changed_at=T0, history_failed=False)
    assert store.pacing_state() == (T0, T0, 0)
    store.start_poll(T0 + 120, True)
    store.record_pacing(changed_at=None, history_failed=True)
    store.record_pacing(changed_at=None, history_failed=True)
    assert store.pacing_state() == (T0 + 120, T0, 2)
    store.record_pacing(changed_at=None, history_failed=False)
    assert store.pacing_state()[2] == 0
