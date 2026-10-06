"""Tests for the played-rule simulation in ``scripts/scrobbler_simulation.py``.

The full run behind the tables in docs/scrobbler.md takes about ten minutes
(``python scripts/scrobbler_simulation.py --check``); these tests run a
reduced one and check that every simulated poll is a run of the real poller.
"""

import importlib.util
import itertools
import random
import sys
from pathlib import Path

import pytest

from src.scrobbler.played import DEFAULT_RULES

pytestmark = pytest.mark.usefixtures("no_network")

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scrobbler_simulation.py"


@pytest.fixture(scope="module")
def sim():
    spec = importlib.util.spec_from_file_location("scrobbler_simulation", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["scrobbler_simulation"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("scrobbler_simulation", None)


@pytest.fixture(scope="module")
def reduced(sim):
    return sim.simulate(DEFAULT_RULES, sessions=4, intervals=(1, 5))


def test_confirmation_keeps_flickers_from_inventing_plays(sim, reduced):
    trusting = sim.simulate(DEFAULT_RULES, sessions=4, intervals=(1,), confirm=False)
    assert trusting["flicker"][1].phantom > 0
    for scenario in ("album", "shuffle_0", "shuffle_20", "pauses", "flicker"):
        assert reduced[scenario][1].phantom == 0
    assert reduced["flicker"][1].false < trusting["flicker"][1].false


def test_full_listening_without_pauses_is_never_a_false_scrobble(reduced):
    for scenario in ("album", "shuffle_0"):
        for score in reduced[scenario].values():
            assert score.false == 0
            assert score.real > 0


def test_a_shorter_interval_costs_less(sim, reduced):
    combined = sim.totals(reduced)
    assert combined[1].cost < combined[5].cost
    assert combined[1].certain_share > combined[5].certain_share


def test_adaptive_pacing_polls_less_than_the_fastest_interval_would(sim):
    rng = random.Random(3)
    session = sim.album_session(rng)
    run = sim.track_session(session, 60.0, DEFAULT_RULES, rng=rng)
    span = run.polls[-1] - run.polls[0]
    assert len(run.polls) < span / 60 / 2
    gaps = [b - a for a, b in zip(run.polls, run.polls[1:], strict=False)]
    assert min(gaps) == pytest.approx(60)
    assert max(gaps) == pytest.approx(600)


def test_session_generators_cover_the_listed_behaviours(sim):
    rng = random.Random(1)
    assert set(sim.SCENARIOS) >= {
        "album",
        "shuffle_0",
        "shuffle_20",
        "shuffle_50",
        "fast_skip",
        "repeats",
        "pauses",
        "short",
        "long",
        "offline",
        "offline_mid",
        "outage",
        "flicker",
    }
    album = sim.album_session(rng).plays
    assert all(p.listened == p.duration for p in album)
    fast = sim.fast_skip_session(rng).plays
    assert sum(p.listened < 20 for p in fast) > len(fast) / 3
    offline = sim.offline_session(rng).plays
    assert len({p.shown for p in offline}) == 1
    assert all(p.shown > p.start for p in offline)
    middle = sim.offline_mid_session(rng).plays
    late = [p for p in middle if p.shown > p.start]
    assert 6 <= len(late) < len(middle)
    assert sim.outage_session(rng).outage is not None
    assert sim.flicker_session(rng).flicker > 0


def test_a_flicker_is_one_of_the_three_kinds(sim):
    rows = sim.background_rows()[:30]
    seen = set()
    rng = random.Random(5)
    for _ in range(60):
        fetched = sim.flicker(rows, rows[1:], rng)
        if fetched == rows[1:]:
            seen.add("stale")
        elif len(fetched) == len(rows) - 1:
            seen.add("missing")
        elif fetched != rows:
            seen.add("up")
    assert seen == {"stale", "missing", "up"}


def test_hidden_repeats_count_once(sim):
    plays = [sim.TruePlay("a", 200, 0, 10), sim.TruePlay("a", 200, 12, 200), sim.TruePlay("b", 200, 214, 200)]
    assert sim.hidden_under(plays, plays[0]) == plays[:2]


def test_a_record_found_late_still_stands_for_its_real_play(sim):
    plays = [sim.TruePlay("a", 200, 0, 200), sim.TruePlay("b", 200, 202, 200)]
    assert sim.true_play(plays, [], "b", 500) is plays[1]
    assert sim.true_play(plays, [], "c", 500) is None
    first = sim.Record("b", 260, plays[1], sim.PLAY)
    assert sim.true_play(plays, [first], "b", 900) is None


@pytest.mark.parametrize("scenario", ["shuffle_20", "outage", "flicker", "mixed"])
def test_each_poll_of_a_session_is_a_run_of_the_real_poller(sim, scenario, monkeypatch):
    runs = []
    original = sim.Poller.run

    def counting(self):
        runs.append(self)
        return original(self)

    monkeypatch.setattr(sim.Poller, "run", counting)
    rng = random.Random(f"poller-{scenario}")
    session = sim.SCENARIOS[scenario][1](rng)
    result = sim.track_session(session, 60.0, DEFAULT_RULES, rng=rng)
    assert len(runs) == len(result.polls)
    assert len({id(p) for p in runs}) == 1
    assert any(r.outcome for r in result.records)
    assert {r.outcome for r in result.records} <= {sim.PLAY, sim.SKIP, sim.DEFER, sim.DUPLICATE, ""}


def test_the_decision_log_becomes_the_outcomes_the_score_reads(sim):
    assert sim.outcome_of({"status": "would_scrobble", "reason": ""}) == sim.PLAY
    assert sim.outcome_of({"status": "skipped", "reason": "listened_too_little"}) == sim.SKIP
    assert sim.outcome_of({"status": "skipped", "reason": "realtime_active"}) == sim.DEFER
    assert sim.outcome_of({"status": "skipped", "reason": "duplicate"}) == sim.DUPLICATE
    assert sim.outcome_of({"status": "pending", "reason": ""}) == ""


def test_the_computer_s_scrobbler_shows_its_plays_and_scrobbles_them_once_they_count(sim):
    plays = [sim.TruePlay("pc", 200, 100, 200, device=sim.PC), sim.TruePlay("phone", 200, 300, 200)]
    clock = {"t": 150.0}
    lastfm = sim.SessionLastfm(plays, lambda: clock["t"], now_playing_shown=True)
    assert lastfm.now_playing("u").track == "pc"
    assert lastfm.recent_scrobbles("u", 0) == []
    clock["t"] = 250.0
    assert [s.track for s in lastfm.recent_scrobbles("u", 0)] == ["pc"]
    clock["t"] = 350.0
    assert lastfm.now_playing("u") is None
    assert sim.SessionLastfm(plays, lambda: 150.0, now_playing_shown=False).now_playing("u") is None


def test_parallel_and_serial_runs_score_the_same(sim):
    serial = sim.simulate(DEFAULT_RULES, sessions=2, intervals=(2,), scenarios=("album", "mixed"))
    parallel = sim.simulate(DEFAULT_RULES, sessions=2, intervals=(2,), scenarios=("album", "mixed"), workers=2)
    assert serial == parallel


def test_mixed_sessions_take_turns_between_the_devices(sim):
    rng = random.Random(4)
    for _ in range(5):
        plays = sim.mixed_session(rng).plays
        devices = [p.device for p in plays]
        changes = sum(1 for a, b in itertools.pairwise(devices) if a != b)
        assert 1 <= changes <= 3
        assert {sim.PHONE, sim.PC} == set(devices)


def test_deferring_to_the_real_time_scrobbler_drops_its_skips_without_missing_phone_plays(sim):
    on = sim.simulate(DEFAULT_RULES, sessions=6, intervals=(2,), scenarios=("mixed",))["mixed"][2]
    off = sim.simulate(DEFAULT_RULES, sessions=6, intervals=(2,), scenarios=("mixed",), realtime_gap=None)["mixed"][2]
    assert on.false < off.false
    assert on.missed <= off.missed + 1


def test_a_longer_idle_interval_polls_less(sim):
    rng = random.Random(6)
    session = sim.album_session(rng)
    polls = {m: len(sim.track_session(session, 120.0, DEFAULT_RULES, rng=random.Random(1), idle=m * 60.0).polls) for m in (5, 10, 15)}
    assert polls[5] > polls[10] > polls[15]


def test_the_generated_tables_replace_the_body_of_their_section(sim):
    text = f"# Page\n\nIntro.\n\n{sim.SECTION}\n\nold table\n\n### Next\n\nKept.\n"
    updated = sim.replace_section(text, "new table")
    assert updated == f"# Page\n\nIntro.\n\n{sim.SECTION}\n\nnew table\n\n### Next\n\nKept.\n"
    assert sim.replace_section(updated, "new table") == updated
    assert sim.replace_section("# Page\n\nNo tables here.\n", "x") is None
