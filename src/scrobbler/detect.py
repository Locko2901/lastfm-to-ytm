"""Detect new plays by comparing snapshots of the YouTube Music history.

The fewest top rows that explain the current list are the new plays, and a row
moving into "Today" was played again. New rows count once the next poll
confirms them (``confirm_step``). docs/scrobbler.md has examples.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .history import TODAY_LABEL, HistoryItem

SNAPSHOT_LIMIT = 250


@dataclass(frozen=True, slots=True)
class SnapshotEntry:
    """One persisted history row: enough to compare order and shelf."""

    video_id: str
    played: str = ""


@dataclass(frozen=True, slots=True)
class Detection:
    """Result of comparing the current history with the previous snapshot."""

    new_items: list[HistoryItem] = field(default_factory=list)
    baseline: bool = False
    reset: bool = False
    empty: bool = False
    replays: int = 0
    shelf_moves: int = 0


@dataclass(frozen=True, slots=True)
class Pending:
    """New rows seen once, waiting for the next poll to confirm them."""

    snapshot: tuple[SnapshotEntry, ...]
    new_ids: tuple[str, ...]
    seen_at: float
    kind: str = "plays"


BASELINE = "baseline"
RESET = "reset"
PLAYS = "plays"


@dataclass(frozen=True, slots=True)
class Step:
    """What one poll does once confirmation is applied.

    ``accepted`` are the confirmed plays (newest first), first seen at
    ``seen_at``; ``snapshot`` replaces the confirmed one unless None;
    ``pending`` waits for the next poll; ``observed_at`` is the time up to which
    nothing unconfirmed started.
    """

    accepted: list[HistoryItem] = field(default_factory=list)
    snapshot: list[SnapshotEntry] | None = None
    seen_at: float | None = None
    pending: Pending | None = None
    observed_at: float | None = None
    kind: str = ""
    flicker: bool = False
    changed: bool = False
    replays: int = 0


def snapshot_of(items: Sequence[HistoryItem]) -> list[SnapshotEntry]:
    """Return the snapshot to persist for ``items`` (top ``SNAPSHOT_LIMIT`` rows)."""
    return [SnapshotEntry(item.video_id, item.played) for item in items[:SNAPSHOT_LIMIT]]


def _explains(current_ids: Sequence[str], k: int, previous_pos: dict[str, int]) -> bool:
    """True when rows ``k`` and below are the previous snapshot's rows, in their old order.

    Rows after the last previously known one are ignored (older songs coming
    into view at the bottom). At least one known row is required, so a list
    that shares nothing with the snapshot is never "explained".
    """
    tail = current_ids[k:]
    last_known = max((i for i, vid in enumerate(tail) if vid in previous_pos), default=-1)
    if last_known < 0:
        return False
    position = -1
    for vid in tail[: last_known + 1]:
        old = previous_pos.get(vid)
        if old is None or old <= position:
            return False
        position = old
    return True


def detect_new_plays(previous: Sequence[SnapshotEntry] | None, current: Sequence[HistoryItem]) -> Detection:
    """Return the plays that happened between ``previous`` and ``current``, newest first.

    Without a previous snapshot the current list only becomes the baseline. When
    the lists share nothing (history cleared, more plays than the history holds,
    another account) the snapshot is reset and nothing is reported, since there
    is no way to tell old rows from new ones.
    """
    if not current:
        return Detection(empty=True)
    if not previous:
        return Detection(baseline=True)

    previous_pos: dict[str, int] = {}
    for i, entry in enumerate(previous):
        previous_pos.setdefault(entry.video_id, i)
    previous_played = {entry.video_id: entry.played for entry in previous}
    current_ids = [item.video_id for item in current]

    k = next((k for k in range(len(current_ids)) if _explains(current_ids, k, previous_pos)), None)
    if k is None:
        return Detection(reset=True)

    order_k = k
    for j in range(order_k, len(current)):
        item = current[j]
        before = previous_played.get(item.video_id, "").strip().lower()
        if item.is_today and before and before != TODAY_LABEL and all(above.is_today for above in current[:j]):
            k = j + 1

    new_items = list(current[:k])
    replays = sum(1 for item in new_items if item.video_id in previous_pos)
    return Detection(new_items=new_items, replays=replays, shelf_moves=k - order_k)


def _same_rows(previous: Sequence[SnapshotEntry], current: Sequence[HistoryItem]) -> bool:
    """True when ``current`` lists the same rows as ``previous``, in the same order."""
    return [e.video_id for e in previous] == [e.video_id for e in snapshot_of(current)]


def _relabelled(snapshot: Sequence[SnapshotEntry], current: Sequence[HistoryItem]) -> list[SnapshotEntry]:
    """``snapshot`` with each row's shelf taken from ``current`` where it is listed (shelves move at midnight)."""
    shelves = {item.video_id: item.played for item in current}
    return [SnapshotEntry(e.video_id, shelves.get(e.video_id, e.played)) for e in snapshot]


def _played_on_top(confirmed: Sequence[SnapshotEntry], played_ids: Sequence[str], current: Sequence[HistoryItem]) -> list[SnapshotEntry]:
    """The confirmed snapshot after ``played_ids`` (newest first) moved to its top, shelves from ``current``."""
    played = set(played_ids)
    rows = [SnapshotEntry(vid, "") for vid in played_ids] + [e for e in confirmed if e.video_id not in played]
    return _relabelled(rows, current)[:SNAPSHOT_LIMIT]


def _pending_after(snapshot: Sequence[SnapshotEntry], current: Sequence[HistoryItem], now: float) -> Pending | None:
    """The rows of ``current`` above ``snapshot``, waiting for confirmation, if any."""
    detection = detect_new_plays(snapshot, current)
    if detection.reset:
        return Pending(tuple(snapshot_of(current)), (), now, RESET)
    if not detection.new_items:
        return None
    return Pending(tuple(snapshot_of(current)), tuple(i.video_id for i in detection.new_items), now)


def confirm_step(confirmed: Sequence[SnapshotEntry] | None, pending: Pending | None, current: Sequence[HistoryItem], now: float) -> Step:
    """Apply one poll: accept the pending rows if ``current`` confirms them, else start or replace a pending change.

    A first list or a reset becomes the snapshot once the next fetch lists the
    same rows. An empty list confirms and refutes nothing.
    """
    if not current:
        return Step(pending=pending)
    if not confirmed:
        if pending is not None and pending.kind == BASELINE and _same_rows(pending.snapshot, current):
            return Step(snapshot=snapshot_of(current), seen_at=pending.seen_at, kind=BASELINE, observed_at=now)
        return Step(pending=Pending(tuple(snapshot_of(current)), (), now, BASELINE))

    detection = detect_new_plays(confirmed, current)
    if detection.reset:
        if pending is not None and pending.kind == RESET and _same_rows(pending.snapshot, current):
            return Step(snapshot=snapshot_of(current), seen_at=pending.seen_at, kind=RESET, changed=True, observed_at=now)
        return Step(pending=Pending(tuple(snapshot_of(current)), (), now, RESET), flicker=pending is not None, changed=True)

    new_ids = tuple(item.video_id for item in detection.new_items)
    if not new_ids:
        if pending is not None:
            return Step(flicker=True)
        return Step(snapshot=_relabelled(confirmed, current), observed_at=now)
    if pending is not None and pending.kind == PLAYS and new_ids[len(new_ids) - len(pending.new_ids) :] == pending.new_ids:
        by_id = {item.video_id: item for item in current}
        accepted = [by_id[vid] for vid in pending.new_ids]
        previous_ids = {entry.video_id for entry in confirmed}
        snapshot = _played_on_top(confirmed, pending.new_ids, current)
        after = _pending_after(snapshot, current, now)
        return Step(
            accepted=accepted,
            snapshot=snapshot,
            seen_at=pending.seen_at,
            pending=after,
            kind=PLAYS,
            changed=True,
            replays=sum(1 for vid in pending.new_ids if vid in previous_ids),
            observed_at=pending.seen_at if after else now,
        )
    return Step(pending=Pending(tuple(snapshot_of(current)), new_ids, now), flicker=pending is not None, changed=True)
