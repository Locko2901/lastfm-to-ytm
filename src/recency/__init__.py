"""Recency weighting algorithm."""

from .weighting import (
    WeightedTrack,
    collapse_recency_weighted,
    dedupe_keep_latest,
    weight_history_tracks,
)

__all__ = [
    "WeightedTrack",
    "collapse_recency_weighted",
    "dedupe_keep_latest",
    "weight_history_tracks",
]
