"""Run log utilities for saving last run's mappings.

Stores only minimal data (artist, title, source) - full details like
video_id and yt_title are pulled from the search cache when needed.
"""

import json
from datetime import UTC, datetime
from pathlib import Path


def save_run_log(
    cache_dir: Path,
    mappings: list[dict[str, str]],
) -> None:
    """Save the run log with track mappings.

    Args:
        cache_dir: Directory to save the log file
        mappings: List of mapping dicts with keys:
            - artist: str
            - title: str
            - source: str ('override', 'cache', 'search', 'blacklisted', 'not_found')
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    log_file = cache_dir / ".last_run_log.json"

    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total": len(mappings),
        "mappings": mappings,
    }

    with log_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def create_mapping_entry(
    artist: str,
    title: str,
    source: str,
) -> dict[str, str]:
    """Create a mapping entry."""
    return {
        "artist": artist,
        "title": title,
        "source": source,
    }
