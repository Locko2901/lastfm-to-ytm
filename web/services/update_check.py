"""Compare the running app version against the latest GitHub release."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, cast

import requests

logger = logging.getLogger(__name__)

REPO = os.environ.get("YTMT_GITHUB_REPO", "Locko2901/lastfm-to-ytm")
CACHE_TTL_SECONDS = 6 * 60 * 60
HTTP_TIMEOUT = 5

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT_FILE = _PROJECT_ROOT / "pyproject.toml"
_COMMIT_SHA_FILE = _PROJECT_ROOT / "COMMIT_SHA"
_CHANNEL_FILE = _PROJECT_ROOT / ".channel"
_CACHE_DIR = Path(os.environ.get("RUNTIME_DIR") or os.environ.get("CACHE_DIR") or str(_PROJECT_ROOT / "runtime"))
_CACHE_FILE = _CACHE_DIR / ".update_check.json"
_DEFAULT_BRANCH = os.environ.get("YTMT_GITHUB_BRANCH", "main")

_VERSION_RE = re.compile(r"^\s*version\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_VALID_CHANNELS = {"stable", "dev"}


def _detect_channel_from_git() -> str | None:
    """Return ``"stable"`` only when HEAD is detached on a release tag.

    A plain ``git clone`` (or ``git checkout main``) leaves HEAD attached to
    the branch even if its tip commit happens to be tagged, so we require
    detached HEAD *and* an exact tag match before declaring stable.

    Returns ``None`` when git or a repository is unavailable (e.g. tarball
    installs, prebuilt Docker images without a checkout).
    """
    try:
        head_check = subprocess.run(
            ["git", "-C", str(_PROJECT_ROOT), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if head_check.returncode != 0:
        return None
    try:
        symref = subprocess.run(
            ["git", "-C", str(_PROJECT_ROOT), "symbolic-ref", "-q", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if symref.returncode == 0:
        return "dev"
    try:
        describe = subprocess.run(
            [
                "git",
                "-C",
                str(_PROJECT_ROOT),
                "describe",
                "--tags",
                "--exact-match",
                "HEAD",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if describe.returncode == 0 and describe.stdout.strip().lstrip("vV"):
        return "stable"
    return "dev"


def _read_channel() -> str | None:
    """Return the declared update channel (``"stable"`` or ``"dev"``), or ``None``.

    Precedence:

    1. ``YTMT_CHANNEL`` environment variable (manual override).
    2. ``.channel`` pointer file in the project root, written by
       ``run-docker.sh`` on every launch (same pattern as ``COMMIT_SHA``).
    3. Git tag detection: HEAD on a release tag &rarr; ``"stable"``, else
       ``"dev"``. Only applies to standalone checkouts.

    Returns ``None`` when no signal is available.
    """
    env = os.environ.get("YTMT_CHANNEL", "").strip().lower()
    if env in _VALID_CHANNELS:
        return env
    try:
        file_value = _CHANNEL_FILE.read_text(encoding="utf-8").strip().lower()
    except OSError:
        file_value = ""
    if file_value in _VALID_CHANNELS:
        return file_value
    return _detect_channel_from_git()


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


def _read_commit_sha() -> str | None:
    """Return the full commit SHA the running build was built from, or ``None``.

    Reads from the ``COMMIT_SHA`` file copied into the image at build time
    (populated by CI or ``run-docker.sh``). Falls back to ``git rev-parse
    HEAD`` for standalone installs running directly from a checkout. Returns
    ``None`` for the placeholder value ``unknown`` or any unparseable content.
    """
    try:
        text = _COMMIT_SHA_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    if text and text.lower() != "unknown" and _SHA_RE.match(text):
        return text.lower()
    try:
        result = subprocess.run(
            ["git", "-C", str(_PROJECT_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip().lower()
    if not _SHA_RE.match(sha):
        return None
    return sha


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


def _github_get(path: str) -> dict[str, Any] | list[Any] | None:
    """GET a JSON path from the GitHub REST API for the configured repo."""
    url = f"https://api.github.com/repos/{REPO}{path}"
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.RequestException as exc:
        logger.debug("GitHub request %s failed: %s", path, exc)
        return None
    if response.status_code != 200:
        logger.debug("GitHub request %s returned HTTP %s", path, response.status_code)
        return None
    try:
        return cast("dict[str, Any] | list[Any] | None", response.json())
    except ValueError:
        return None


def _github_sha_exists(sha: str) -> bool | None:
    """Return True if ``sha`` is reachable on the remote, False if not, None on error."""
    url = f"https://api.github.com/repos/{REPO}/commits/{sha}"
    try:
        response = requests.get(
            url,
            timeout=HTTP_TIMEOUT,
            headers={"Accept": "application/vnd.github+json"},
        )
    except requests.RequestException as exc:
        logger.debug("GitHub sha existence check for %s failed: %s", sha, exc)
        return None
    if response.status_code == 200:
        return True
    if response.status_code in (404, 422):
        return False
    logger.debug("GitHub sha existence check for %s returned HTTP %s", sha, response.status_code)
    return None


def _fetch_remote_info(version: str | None, current_sha: str | None) -> dict[str, Any] | None:
    """Fetch latest release, branch HEAD sha, and the sha of the current version's tag.

    Cached in a single JSON blob. The cache key includes the running build's
    SHA so pulling a new commit (which changes ``current_sha`` but not
    ``version``) immediately invalidates a stale dev-channel cache instead
    of waiting for the TTL to expire.
    """
    cached = _load_cache()
    if cached is not None and cached.get("version_at_fetch") == version and cached.get("sha_at_fetch") == current_sha:
        return cached

    release = _github_get("/releases/latest")
    if not isinstance(release, dict):
        return None
    tag = release.get("tag_name")
    if not tag:
        return None

    branch_head_sha: str | None = None
    head = _github_get(f"/commits/{_DEFAULT_BRANCH}")
    if isinstance(head, dict):
        sha = head.get("sha")
        if isinstance(sha, str):
            branch_head_sha = sha.lower()

    current_tag_sha: str | None = None
    if version:
        ref = _github_get(f"/git/ref/tags/v{version}")
        if isinstance(ref, dict):
            obj = ref.get("object") or {}
            sha = obj.get("sha")
            if isinstance(sha, str):
                current_tag_sha = sha.lower()

    current_sha_on_remote: bool | None = None
    if current_sha:
        current_sha_on_remote = _github_sha_exists(current_sha)

    payload = {
        "tag": tag,
        "name": release.get("name") or tag,
        "url": release.get("html_url"),
        "branch_head_sha": branch_head_sha,
        "current_tag_sha": current_tag_sha,
        "current_sha_on_remote": current_sha_on_remote,
        "version_at_fetch": version,
        "sha_at_fetch": current_sha,
        "fetched_at": time.time(),
    }
    _save_cache(payload)
    return payload


def get_update_status() -> dict[str, Any]:
    """Compare the running build against the latest release and branch HEAD.

    Returns a dict with keys:

    - ``current_version``: version from ``pyproject.toml``
    - ``current_sha`` / ``current_sha_short``: full / 7-char build SHA, or
      ``None`` for non-image installs without a populated ``COMMIT SHA``
    - ``build_type``: ``"local"`` (unpushed SHA - overrides everything else),
      ``"stable"`` / ``"dev"`` from ``YTMT_CHANNEL`` or ``.channel``, or
      inferred from the SHA (tag match → ``"stable"``, otherwise ``"dev"``;
      ``"unknown"`` if no SHA).
    - ``latest_version`` / ``release_url`` / ``release_name``: latest released
      tag (``None`` on fetch failure)
    - ``latest_branch_sha`` / ``latest_branch_sha_short``: HEAD of the default
      branch (used for dev-build update detection)
    - ``update_available``: stable builds compare semver; dev builds compare
      ``current_sha`` to ``latest_branch_sha``
    - ``commits_url``: GitHub URL pointing at the new commits since the
      running build (compare view when ``current_sha`` is known, otherwise
      the default branch commit log). Always populated.
    """
    current = _read_local_version()
    current_sha = _read_commit_sha()
    declared_channel = _read_channel()
    result: dict[str, Any] = {
        "current_version": current,
        "current_sha": current_sha,
        "current_sha_short": current_sha[:7] if current_sha else None,
        "build_type": declared_channel or "unknown",
        "latest_version": None,
        "release_url": None,
        "release_name": None,
        "latest_branch_sha": None,
        "latest_branch_sha_short": None,
        "update_available": False,
        "commits_url": f"https://github.com/{REPO}/commits/{_DEFAULT_BRANCH}",
    }

    remote = _fetch_remote_info(current, current_sha)
    if not remote:
        return result

    tag = str(remote.get("tag") or "")
    latest = tag.lstrip("vV") or None
    result["latest_version"] = latest
    result["release_url"] = remote.get("url")
    result["release_name"] = remote.get("name") or tag

    branch_head = remote.get("branch_head_sha")
    if isinstance(branch_head, str):
        result["latest_branch_sha"] = branch_head
        result["latest_branch_sha_short"] = branch_head[:7]
        if current_sha and current_sha != branch_head:
            result["commits_url"] = f"https://github.com/{REPO}/compare/{current_sha}...{branch_head}"

    current_tag_sha = remote.get("current_tag_sha")
    sha_on_remote = remote.get("current_sha_on_remote")
    if declared_channel is None and current_sha:
        if isinstance(current_tag_sha, str) and current_sha == current_tag_sha:
            result["build_type"] = "stable"
        elif sha_on_remote is False:
            result["build_type"] = "local"
        else:
            result["build_type"] = "dev"

    if sha_on_remote is False:
        result["build_type"] = "local"
        result["commits_url"] = f"https://github.com/{REPO}/commits/{_DEFAULT_BRANCH}"
        result["update_available"] = False
        return result

    if result["build_type"] == "dev":
        if branch_head and current_sha and branch_head != current_sha:
            result["update_available"] = True
    else:
        current_parsed = _parse_version(current)
        latest_parsed = _parse_version(latest)
        if current_parsed is not None and latest_parsed is not None:
            result["update_available"] = latest_parsed > current_parsed

    return result
