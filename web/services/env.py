"""Environment file parsing and updating."""

from __future__ import annotations

import contextlib
import datetime
import shutil
from pathlib import Path

from src.config import PROJECT_ROOT, RUNTIME_DIR

ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"
BROWSER_JSON_FILE = PROJECT_ROOT / "browser.json"

_PRESERVED_HEADER = "# ---- Custom / unrecognised settings (preserved) ----"

BOOL_SETTINGS = {
    "DEDUPLICATE",
    "USE_ANON_SEARCH",
    "USE_RECENCY_WEIGHTING",
    "RECENCY_SESSION_WEIGHTING",
    "WEEKLY_ENABLED",
    "LASTFM_FORCE_IPV4",
    "AUTO_SYNC_ENABLED",
    "AUTO_TAG_SYNC_ENABLED",
    "USE_24_HOUR_CLOCK",
    "NOW_PLAYING_ENABLED",
    "HISTORY_DB_ENABLED",
    "USE_LOCAL_LASTFM_DB",
    "DISPLAY_TIPS",
    "WEBHOOK_ALLOW_PRIVATE",
}

PRIVACY_SETTINGS = {
    "MAKE_PUBLIC",
    "WEEKLY_MAKE_PUBLIC",
    "CUSTOM_PLAYLISTS_PRIVACY",
}

ALL_SETTINGS = [
    "LASTFM_USER",
    "LASTFM_API_KEY",
    "PLAYLIST_NAME",
    "PLAYLIST_DESCRIPTION",
    "MAKE_PUBLIC",
    "LIMIT",
    "DEDUPLICATE",
    "USE_RECENCY_WEIGHTING",
    "RECENCY_HALF_LIFE_HOURS",
    "RECENCY_PLAY_WEIGHT",
    "RECENCY_MIN_PLAYS",
    "RECENCY_NORMALIZATION",
    "RECENCY_VELOCITY_WEIGHT",
    "RECENCY_SESSION_WEIGHTING",
    "RECENCY_SESSION_HOURS",
    "RECENCY_SESSION_TIMEZONE",
    "TIMEZONE",
    "WEEKLY_ENABLED",
    "WEEKLY_WEEK_START",
    "WEEKLY_TIMEZONE",
    "WEEKLY_KEEP_WEEKS",
    "WEEKLY_PLAYLIST_PREFIX",
    "WEEKLY_MAKE_PUBLIC",
    "USE_ANON_SEARCH",
    "EARLY_TERMINATION_SCORE",
    "SLEEP_BETWEEN_SEARCHES",
    "SEARCH_MAX_WORKERS",
    "MAX_RAW_SCROBBLES",
    "BACKFILL_PASSES",
    "CACHE_SEARCH_TTL_DAYS",
    "CACHE_NOTFOUND_TTL_DAYS",
    "API_MAX_RETRIES",
    "LASTFM_MAX_RETRIES",
    "LASTFM_MAX_CONSECUTIVE_EMPTY",
    "LASTFM_FORCE_IPV4",
    "LOG_LEVEL",
    "AUTO_SYNC_ENABLED",
    "AUTO_SYNC_TYPE",
    "AUTO_SYNC_INTERVAL_HOURS",
    "AUTO_SYNC_START_TIME",
    "AUTO_SYNC_CRON",
    "AUTO_TAG_SYNC_ENABLED",
    "AUTO_TAG_SYNC_FREQUENCY",
    "USE_24_HOUR_CLOCK",
    "DATE_FORMAT",
    "NOW_PLAYING_ENABLED",
    "NOW_PLAYING_INTERVAL",
    "DISPLAY_TIPS",
    "CUSTOM_PLAYLISTS_PRIVACY",
    "TAG_CACHE_TTL_DAYS",
    "TAG_MIN_COUNT",
    "TAG_SLEEP_BETWEEN",
    "HISTORY_DB_ENABLED",
    "HISTORY_MAX_SIZE_MB",
    "HISTORY_RETENTION_DAYS",
    "USE_LOCAL_LASTFM_DB",
    "WEBHOOK_URL",
    "WEBHOOK_EVENTS",
    "WEBHOOK_ALLOW_PRIVATE",
]


def _strip_inline_comment(value: str) -> str:
    """Remove a trailing ``# ...`` inline comment from an .env value."""
    for marker in (" #", "\t#"):
        idx = value.find(marker)
        if idx != -1:
            return value[:idx]
    return value


def _inline_comment(value: str) -> str:
    """Return the trailing ``# ...`` inline comment (with leading space), or ``""``."""
    for marker in (" #", "\t#"):
        idx = value.find(marker)
        if idx != -1:
            return value[idx:]
    return ""


def _parse_env_path(path: Path) -> dict[str, str]:
    """Parse an env-style file at ``path`` into key-value pairs."""
    settings: dict[str, str] = {}
    if not path.exists():
        return settings

    with path.open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                settings[key.strip()] = _strip_inline_comment(value).strip()

    return settings


def parse_env_file() -> dict[str, str]:
    """Parse .env file into key-value pairs."""
    return _parse_env_path(ENV_FILE)


def parse_env_example() -> dict[str, str]:
    """Parse .env.example into key-value pairs (insertion order = template order)."""
    return _parse_env_path(ENV_EXAMPLE_FILE)


def update_env_file(updates: dict[str, str]) -> None:
    """Update the .env file with new values, preserving comments and structure."""
    if not ENV_FILE.exists():
        lines = []
    else:
        with ENV_FILE.open() as f:
            lines = f.readlines()

    updated_keys = set()
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, old_value = stripped.partition("=")
            key = key.strip()
            if key in updates:
                inline_comment = ""
                for marker in (" #", "\t#"):
                    idx = old_value.find(marker)
                    if idx != -1:
                        inline_comment = old_value[idx:]
                        break

                new_value = updates[key]
                new_lines.append(f"{key}={new_value}{inline_comment}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with ENV_FILE.open("w") as f:
        f.writelines(new_lines)

    # Restrict permissions: the .env may hold secrets (API keys, passwords).
    with contextlib.suppress(OSError):
        ENV_FILE.chmod(0o600)


def check_env_completeness() -> dict[str, object]:
    """Report which ``.env.example`` keys are missing from the current ``.env``.

    Returns a dict with ``env_present``, ``example_present``, the ordered list
    of ``missing_keys`` (present in the example but not in ``.env``) and its
    ``missing_count``. Returns an empty missing list when either file is absent
    (a missing ``.env`` means first-time setup, handled separately; a missing
    ``.env.example`` is surfaced via ``example_present`` so callers can prompt
    the user to re-download it).
    """
    env_present = ENV_FILE.exists()
    example_present = ENV_EXAMPLE_FILE.exists()
    result: dict[str, object] = {
        "env_present": env_present,
        "example_present": example_present,
        "missing_keys": [],
        "missing_count": 0,
    }
    if not env_present or not example_present:
        return result

    current = set(parse_env_file())
    missing = [key for key in parse_env_example() if key not in current]
    result["missing_keys"] = missing
    result["missing_count"] = len(missing)
    return result


def reconcile_env_file() -> dict[str, object]:
    """Regenerate ``.env`` from the ``.env.example`` template, backing up first.

    The rewritten file follows the example's ordering and inline comments while
    keeping every existing user value. Missing keys are inserted in their
    correct position using the example's default value. Keys present in ``.env``
    but not in the example (custom/deprecated) are preserved at the end under a
    dedicated header - nothing is ever deleted. A timestamped backup of the
    existing ``.env`` is always created before writing.

    Returns a dict with ``imported`` (keys added from the example),
    ``preserved_unknown`` (custom keys kept) and ``backup`` (backup filename or
    ``None`` when there was no pre-existing ``.env``).

    Raises ``FileNotFoundError`` when ``.env.example`` is missing.
    """
    if not ENV_EXAMPLE_FILE.exists():
        raise FileNotFoundError(str(ENV_EXAMPLE_FILE))

    current_values = parse_env_file()
    example_keys: set[str] = set()
    imported: list[str] = []
    out_lines: list[str] = []

    for raw in ENV_EXAMPLE_FILE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out_lines.append(raw)
            continue
        key, _, example_value = stripped.partition("=")
        key = key.strip()
        example_keys.add(key)
        comment = _inline_comment(example_value)
        if key in current_values:
            value = current_values[key]
        else:
            value = _strip_inline_comment(example_value).strip()
            imported.append(key)
        out_lines.append(f"{key}={value}{comment}")

    preserved = [key for key in current_values if key not in example_keys]
    if preserved:
        out_lines.append("")
        out_lines.append(_PRESERVED_HEADER)
        out_lines.extend(f"{key}={current_values[key]}" for key in preserved)

    new_content = "\n".join(out_lines).rstrip("\n") + "\n"

    backup_name = _backup_env_file()

    with ENV_FILE.open("w", encoding="utf-8") as f:
        f.write(new_content)
    with contextlib.suppress(OSError):
        ENV_FILE.chmod(0o600)

    return {
        "imported": imported,
        "preserved_unknown": preserved,
        "backup": backup_name,
    }


def _backup_env_file() -> str | None:
    """Copy the current ``.env`` to a timestamped backup, returning its path.

    Backups live in ``runtime/backups/`` - a writable location that works both
    for standalone installs and Docker (where ``/app`` is read-only but the
    ``runtime`` volume is mounted read-write). Falls back to a backup alongside
    ``.env`` if the runtime directory is not writable. Returns a path relative
    to the project root when possible, or ``None`` when there is no ``.env`` to
    back up.
    """
    if not ENV_FILE.exists():
        return None
    filename = f".env.bak-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    for dest in (RUNTIME_DIR / "backups" / filename, ENV_FILE.with_name(filename)):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ENV_FILE, dest)
        except OSError:
            continue
        with contextlib.suppress(OSError):
            dest.chmod(0o600)
        try:
            return str(dest.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(dest)
    return None


def _resolve_example_ref() -> str:
    """Resolve the GitHub ref to fetch ``.env.example`` from for this build.

    Stable channel &rarr; the release tag (``vX.Y.Z``); otherwise the exact
    build commit SHA when known, falling back to the default branch.
    """
    from . import update_check as uc

    if uc._read_channel() == "stable":
        version = uc._read_local_version()
        if version:
            return "v" + version.strip().lstrip("vV")
    sha = uc._read_commit_sha()
    if sha:
        return sha
    return uc._DEFAULT_BRANCH


def example_download_info() -> dict[str, str]:
    """Return GitHub URLs to (re)download ``.env.example`` for this build."""
    from . import update_check as uc

    ref = _resolve_example_ref()
    return {
        "ref": ref,
        "raw_url": f"https://raw.githubusercontent.com/{uc.REPO}/{ref}/.env.example",
        "blob_url": f"https://github.com/{uc.REPO}/blob/{ref}/.env.example",
    }


def download_example_from_github() -> dict[str, object]:
    """Download ``.env.example`` from GitHub for this build's ref and save it.

    Tries the version/commit-pinned ref first, then the default branch. Only
    writes content that looks like a valid dotenv template (size-capped and
    containing a known key) to avoid persisting an error page.
    """
    import requests

    from . import update_check as uc

    info = example_download_info()
    urls = [info["raw_url"]]
    fallback = f"https://raw.githubusercontent.com/{uc.REPO}/{uc._DEFAULT_BRANCH}/.env.example"
    if fallback not in urls:
        urls.append(fallback)

    last_error = ""
    for url in urls:
        try:
            resp = requests.get(url, timeout=uc.HTTP_TIMEOUT)
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
        if resp.status_code != 200:
            last_error = f"HTTP {resp.status_code}"
            continue
        text = resp.text
        if len(text) > 262_144 or "LASTFM_USER" not in text:
            last_error = "unexpected content"
            continue
        try:
            ENV_EXAMPLE_FILE.write_text(text, encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": str(exc), "url": url}
        return {"ok": True, "url": url, "ref": info["ref"]}

    return {"ok": False, "error": last_error or "download failed", "url": info["raw_url"]}
