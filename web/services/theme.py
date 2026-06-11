"""Persistent storage for the user's custom theme overrides.

Schema (JSON):
    {
        "enabled": bool,
        "parents": {
            "dark":  { "--accent": "#ff0000", ... },
            "light": { "--accent": "#aa0000", ... }
        }
    }

Stored at ``cache/.theme_overrides.json`` so it travels with the other
cache files (and the teleporter) but is never auto-evicted.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.config import CACHE_DIR

logger = logging.getLogger(__name__)

THEME_OVERRIDES_FILE: Path = CACHE_DIR / ".theme_overrides.json"

_VALID_PARENTS = {"dark", "light"}
# Light validation: hex (#abc / #aabbcc / #aabbccdd) or short rgb()/rgba() forms.
_HEX_RE = __import__("re").compile(r"^#[0-9a-fA-F]{3,8}$")


def _empty() -> dict[str, Any]:
    return {"enabled": False, "parents": {"dark": {}, "light": {}}}


def load_theme_overrides() -> dict[str, Any]:
    """Read the theme overrides file. Returns the empty shape if absent or invalid."""
    if not THEME_OVERRIDES_FILE.exists():
        return _empty()
    try:
        raw = THEME_OVERRIDES_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Failed to read %s: %s", THEME_OVERRIDES_FILE, e)
        return _empty()
    return _sanitise(data)


def save_theme_overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Validate, persist, and return the canonical sanitised payload."""
    clean = _sanitise(data)
    THEME_OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = THEME_OVERRIDES_FILE.with_suffix(THEME_OVERRIDES_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    tmp.replace(THEME_OVERRIDES_FILE)
    return clean


def _sanitise(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _empty()
    parents_raw = data.get("parents")
    parents_in: dict[Any, Any] = parents_raw if isinstance(parents_raw, dict) else {}
    parents_out: dict[str, dict[str, str]] = {"dark": {}, "light": {}}
    for parent in _VALID_PARENTS:
        bucket_raw = parents_in.get(parent)
        bucket: dict[Any, Any] = bucket_raw if isinstance(bucket_raw, dict) else {}
        for key, value in bucket.items():
            if not isinstance(key, str) or not key.startswith("--"):
                continue
            if not isinstance(value, str):
                continue
            v = value.strip()
            if not _HEX_RE.match(v):
                continue
            parents_out[parent][key] = v
    return {"enabled": bool(data.get("enabled")), "parents": parents_out}
