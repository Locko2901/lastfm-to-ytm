"""Compare the running app version against the latest GitHub release."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

REPO = os.environ.get("YTMT_GITHUB_REPO", "Locko2901/lastfm-to-ytm")
CACHE_TTL_SECONDS = 6 * 60 * 60
HTTP_TIMEOUT = 5

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT_FILE = _PROJECT_ROOT / "pyproject.toml"
_CACHE_DIR = Path(os.environ.get("CACHE_DIR", str(_PROJECT_ROOT / "cache")))
_CACHE_FILE = _CACHE_DIR / ".update_check.json"

_VERSION_RE = re.compile(r"^\s*version\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def _read_local_version() -> str | None:
    """Return the project version from ``pyproject.toml``, or ``None``."""
    try:
        text = _PYPROJECT_FILE.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _VERSION_RE.search(text)
    if not match:
        return None
    return match.group(1).strip() or None


def _parse_version(value: str | None) -> tuple[int, ...] | None:
    """Parse a ``X.Y.Z`` (optionally ``vX.Y.Z``) string into a tuple of ints."""
    if not value:
        return None
    cleaned = value.strip().lstrip("vV")
    cleaned = re.split(r"[-+]", cleaned, maxsplit=1)[0]
    parts = cleaned.split(".")
    try:
        return tuple(int(p) for p in parts if p != "")
    except ValueError:
        return None


def _load_cache() -> dict[str, Any] | None:
    try:
        data = json.loads(_CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if time.time() - float(data.get("fetched_at", 0)) > CACHE_TTL_SECONDS:
        return None
    return data


def _save_cache(payload: dict[str, Any]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(_CACHE_FILE)
    except OSError as exc:
        logger.debug("Could not cache update info: %s", exc)


def _fetch_latest_release() -> dict[str, Any] | None:
    cached = _load_cache()
    if cached is not None:
        return cached

    url = f"https://api.github.com/repos/{REPO}/releases/latest"
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.RequestException as exc:
        logger.debug("GitHub release check failed: %s", exc)
        return None
    if response.status_code != 200:
        logger.debug("GitHub release check returned HTTP %s", response.status_code)
        return None
    try:
        data = response.json()
    except ValueError:
        return None

    tag = data.get("tag_name")
    if not tag:
        return None

    payload = {
        "tag": tag,
        "name": data.get("name") or tag,
        "url": data.get("html_url"),
        "fetched_at": time.time(),
    }
    _save_cache(payload)
    return payload


def get_update_status() -> dict[str, Any]:
    """Compare the running version against the latest GitHub release.

    Returns:
        ``{"current_version", "latest_version", "release_url",
        "release_name", "update_available"}``. ``latest_version`` /
        ``release_url`` are ``None`` if the GitHub check failed.
    """
    current = _read_local_version()
    result: dict[str, Any] = {
        "current_version": current,
        "latest_version": None,
        "release_url": None,
        "release_name": None,
        "update_available": False,
    }

    remote = _fetch_latest_release()
    if not remote:
        return result

    tag = str(remote.get("tag") or "")
    latest = tag.lstrip("vV") or None
    result["latest_version"] = latest
    result["release_url"] = remote.get("url")
    result["release_name"] = remote.get("name") or tag

    current_parsed = _parse_version(current)
    latest_parsed = _parse_version(latest)
    if current_parsed is not None and latest_parsed is not None:
        result["update_available"] = latest_parsed > current_parsed

    return result
