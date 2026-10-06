"""Optional Last.fm scrobbler fed by the YouTube Music listening history."""

from .detect import Detection, SnapshotEntry, detect_new_plays, snapshot_of
from .history import HistoryItem, fetch_history, history_reader, parse_history
from .service import Poller, PollOutcome
from .store import ScrobblerStore

__all__ = [
    "Detection",
    "HistoryItem",
    "PollOutcome",
    "Poller",
    "ScrobblerStore",
    "SnapshotEntry",
    "detect_new_plays",
    "fetch_history",
    "history_reader",
    "parse_history",
    "snapshot_of",
]
