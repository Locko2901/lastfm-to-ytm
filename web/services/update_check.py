from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

REPO = os.environ.get("YTMT_GITHUB_REPO", "Locko2901/lastfm-to-ytm")
DEFAULT_BRANCH = os.environ.get("YTMT_GITHUB_BRANCH", "main")
CACHE_TTL_SECONDS = 24 * 60 * 60
HTTP_TIMEOUT = 5

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_COMMIT_FILE = _PROJECT_ROOT / "COMMIT_SHA"
_CACHE_DIR = Path(os.environ.get("CACHE_DIR", str(_PROJECT_ROOT / "cache")))
_CACHE_FILE = _CACHE_DIR / ".update_check.json"


def _git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None


def _git_branch() -> str | None:
    """Current branch name, or None on detached HEAD / no git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    if not out or out == "HEAD":
        return None
    return out


def _read_commit_file() -> str | None:
    try:
        text = _COMMIT_FILE.read_text().strip()
    except OSError:
        return None
    if not text or text == "unknown":
        return None
    return text


def get_local_commit() -> str | None:
    """Return the commit SHA the running build was produced from, or None."""
    return _git_head() or _read_commit_file()


def _load_cache(local_sha: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("local") != local_sha:
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


def _fetch_compare(local_sha: str) -> dict[str, Any] | None:
    cached = _load_cache(local_sha)
    if cached is not None:
        return cached

    url = f"https://api.github.com/repos/{REPO}/compare/{local_sha}...{DEFAULT_BRANCH}"
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.RequestException as exc:
        logger.debug("GitHub compare check failed: %s", exc)
        return None
    if response.status_code != 200:
        logger.debug("GitHub compare returned HTTP %s", response.status_code)
        return None
    try:
        data = response.json()
    except ValueError:
        return None

    payload = {
        "local": local_sha,
        "behind_by": int(data.get("ahead_by") or 0),
        "compare_url": data.get("html_url"),
        "fetched_at": time.time(),
    }
    _save_cache(payload)
    return payload


def get_update_status() -> dict[str, Any]:
    """Compare the running build against ``origin/main``.

    Returns:
        ``{"current", "branch", "on_main", "behind_by", "compare_url",
        "update_available"}``. ``branch``/``on_main`` are ``None`` when the
        branch can't be detected (e.g. running from a baked Docker image).
        ``behind_by``/``compare_url`` are ``None`` if the GitHub check failed.
    """
    local_sha = get_local_commit()
    branch = _git_branch()
    result: dict[str, Any] = {
        "current": local_sha[:7] if local_sha else None,
        "branch": branch,
        "on_main": branch == DEFAULT_BRANCH if branch else None,
        "behind_by": None,
        "compare_url": None,
        "update_available": False,
    }

    if not local_sha:
        return result

    remote = _fetch_compare(local_sha)
    if not remote:
        return result

    behind = remote.get("behind_by") or 0
    result["behind_by"] = behind
    result["compare_url"] = remote.get("compare_url")
    result["update_available"] = behind > 0
    return result
