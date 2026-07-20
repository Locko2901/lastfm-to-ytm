"""Settings from environment variables."""

import contextlib
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")

_LEGACY_CACHE_DIR = PROJECT_ROOT / "cache"


def _resolve_runtime_dir() -> Path:
    """Resolve the runtime state directory, migrating legacy cache/ if needed.

    Resolution order:
    1. RUNTIME_DIR env var (new, explicit) - used as-is.
    2. CACHE_DIR env var (legacy, explicit) - used as-is for backwards compat.
    3. Default runtime/ - if it is missing but a legacy cache/ directory exists,
       the contents are moved over automatically so existing installs keep their
       history databases and caches.
    """
    explicit = os.getenv("RUNTIME_DIR") or os.getenv("CACHE_DIR")
    if explicit:
        return Path(explicit)

    target = PROJECT_ROOT / "runtime"
    if not target.exists() and _LEGACY_CACHE_DIR.is_dir():
        try:
            shutil.move(str(_LEGACY_CACHE_DIR), str(target))
            logging.getLogger(__name__).info("Migrated legacy cache/ directory to runtime/")
        except Exception as exc:  # pragma: no cover - defensive, keep data reachable
            logging.getLogger(__name__).warning("Could not migrate cache/ to runtime/: %s", exc)
            return _LEGACY_CACHE_DIR
    return target


RUNTIME_DIR = _resolve_runtime_dir()

CACHE_DIR = RUNTIME_DIR

CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(PROJECT_ROOT / "config")))


def _remap_legacy_path(value: str) -> str:
    """Rewrite a path pointing inside the old cache/ directory to RUNTIME_DIR.

    Keeps `.env` files copied from older releases (which reference cache/...)
    working after the runtime/ migration. Paths that are pinned to the legacy
    location on purpose (RUNTIME_DIR == cache/) or that live elsewhere are
    returned unchanged.
    """
    if RUNTIME_DIR == _LEGACY_CACHE_DIR:
        return value
    p = Path(value)
    try:
        if p.is_absolute():
            rel = p.relative_to(_LEGACY_CACHE_DIR)
        elif p.parts and p.parts[0] == "cache":
            rel = Path(*p.parts[1:])
        else:
            return value
    except ValueError:
        return value
    return str(RUNTIME_DIR / rel)


def _runtime_file(env_name: str, filename: str) -> str:
    """Resolve a runtime file path from an env var, remapping legacy cache/ paths."""
    return _remap_legacy_path(os.getenv(env_name, str(RUNTIME_DIR / filename)))


_RUNTIME_PATH_ENV_KEYS = (
    "CACHE_PLAYLIST_FILE",
    "CACHE_SEARCH_FILE",
    "TAG_CACHE_FILE",
    "HISTORY_DB_FILE",
    "LASTFM_LOCAL_DB_FILE",
)


def _legacy_cache_value_to_runtime(value: str) -> str | None:
    """Return the runtime/ equivalent of a legacy cache/ path, else None.

    Returns None for values that are not under the legacy cache/ directory
    (custom locations or paths already pointing at runtime/), so callers can
    leave those untouched. Relative inputs stay relative (``cache/x`` ->
    ``runtime/x``); absolute inputs under the legacy dir are rebased onto
    ``PROJECT_ROOT/runtime``.
    """
    v = value.strip()
    if not v:
        return None
    p = Path(v)
    if p.is_absolute():
        try:
            rel = p.relative_to(_LEGACY_CACHE_DIR)
        except ValueError:
            return None
        return str(PROJECT_ROOT / "runtime" / rel)
    parts = p.parts
    if not parts or parts[0] != "cache":
        return None
    return "runtime" if len(parts) == 1 else "runtime/" + "/".join(parts[1:])


def migrate_env_to_runtime() -> bool:
    """Rewrite legacy cache/ paths in the on-disk .env to runtime/ (one-time).

    Idempotent and safe to call on every start:
    - Keys pointing under the old cache/ directory are rewritten to runtime/.
    - Keys pointing at a custom location are left untouched.
    - Keys already pointing at runtime/ are left untouched.

    Skipped entirely when RUNTIME_DIR or the legacy CACHE_DIR env var pins a
    custom runtime location - that is an explicit user choice we don't override.
    Returns True if the file was modified. Call this from process entry points
    (CLI / web server start), never at import time, so tests and library imports
    don't mutate a real .env.
    """
    if os.getenv("RUNTIME_DIR") or os.getenv("CACHE_DIR"):
        return False
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return False
    try:
        original = env_file.read_text(encoding="utf-8")
    except OSError:
        return False

    changed = False
    out_lines: list[str] = []
    for line in original.splitlines(keepends=True):
        newline = "\n" if line.endswith("\n") else ""
        body = line[: len(line) - len(newline)] if newline else line
        stripped = body.strip()
        if stripped and not stripped.startswith("#") and "=" in body:
            key, sep, rest = body.partition("=")
            if key.strip() in _RUNTIME_PATH_ENV_KEYS:
                value, comment = rest, ""
                for marker in (" #", "\t#"):
                    idx = value.find(marker)
                    if idx != -1:
                        value, comment = value[:idx], value[idx:]
                        break
                new_value = _legacy_cache_value_to_runtime(value)
                if new_value is not None and new_value != value.strip():
                    body = f"{key}{sep}{new_value}{comment}"
                    changed = True
        out_lines.append(body + newline)

    if not changed:
        return False

    tmp_file = env_file.with_name(env_file.name + ".tmp")
    tmp_file.write_text("".join(out_lines), encoding="utf-8")
    tmp_file.replace(env_file)
    with contextlib.suppress(OSError):
        env_file.chmod(0o600)
    logging.getLogger(__name__).info("Migrated legacy cache/ paths in .env to runtime/")
    return True


def _dotenv_keys(path: Path) -> list[str]:
    """Return the ordered KEY names defined in an env-style file (best effort)."""
    keys: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return keys
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.append(line.partition("=")[0].strip())
    return keys


def warn_env_incomplete() -> None:
    """Log a one-line warning when .env is missing keys added in newer versions.

    Compares the on-disk ``.env`` against ``.env.example`` and lists any keys
    present only in the template. Purely informational and never raises - safe
    to call from any process entry point right after ``migrate_env_to_runtime``.
    No-op when either file is absent (a missing ``.env`` is first-time setup).
    """
    env_file = PROJECT_ROOT / ".env"
    example_file = PROJECT_ROOT / ".env.example"
    if not env_file.exists() or not example_file.exists():
        return
    current = set(_dotenv_keys(env_file))
    missing = [key for key in _dotenv_keys(example_file) if key not in current]
    if not missing:
        return
    logging.getLogger(__name__).warning(
        "Your .env is missing %d setting(s) added in a newer version: %s. Open the dashboard Settings tab to import optimized defaults.",
        len(missing),
        ", ".join(missing),
    )


def _strip_inline_comment(val: str | None) -> str | None:
    if val is None:
        return None
    if val.startswith("#"):
        return None
    for marker in (" #", "\t#"):
        idx = val.find(marker)
        if idx != -1:
            val = val[:idx]
    return val.strip() or None


def _str_to_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    val = _strip_inline_comment(val) or ""
    return val.lower() in {"1", "true", "t", "yes", "y", "on"}


def _str_to_float(val: str | None, default: float) -> float:
    try:
        val = _strip_inline_comment(val)
        return float(val) if val is not None else default
    except Exception:
        return default


def _str_to_int(val: str | None, default: int) -> int:
    try:
        val = _strip_inline_comment(val)
        return int(val) if val is not None else default
    except Exception:
        return default


_VALID_NORMALIZATIONS = {"linear", "log", "rank"}


def _parse_session_hours(val: str | None, default: tuple[int, int] = (9, 23)) -> tuple[int, int]:
    """Parse a ``"START-END"`` hour window into a ``(start, end)`` pair.

    Both bounds must be integers in ``0..23``; otherwise ``default`` is
    returned. The window is interpreted as half-open ``[start, end)`` and may
    wrap around midnight (e.g. ``"22-4"``).
    """
    val = _strip_inline_comment(val)
    if not val:
        return default
    parts = val.split("-")
    if len(parts) != 2:
        return default
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError:
        return default
    if not (0 <= start <= 23 and 0 <= end <= 23):
        return default
    return start, end


_VALID_PRIVACY = {"PUBLIC", "UNLISTED", "PRIVATE"}
_BOOLEAN_PRIVACY_TOKENS = {"1", "true", "t", "yes", "y", "on", "0", "false", "f", "no", "n", "off"}


def _parse_privacy(val: str | None, default: str = "PRIVATE") -> str:
    """Parse a privacy value, with backward compat for true/false booleans."""
    if val is None:
        return default
    val = _strip_inline_comment(val) or ""
    upper = val.upper()
    if upper in _VALID_PRIVACY:
        return upper
    # Backward compatibility: treat boolean-truthy as PUBLIC
    if val.lower() in {"1", "true", "t", "yes", "y", "on"}:
        return "PUBLIC"
    if val.lower() in {"0", "false", "f", "no", "n", "off"}:
        return "PRIVATE"
    return default


def _resolve_privacy_setting(
    preferred_var: str,
    legacy_var: str,
    *,
    default: str = "PRIVATE",
    inherit: bool = False,
) -> str | None:
    """Resolve a privacy setting from a preferred and a legacy env var.

    ``preferred_var`` wins when set. ``legacy_var`` is still honoured for
    backward compatibility, but its legacy boolean form (``true``/``false``)
    is deprecated and emits a warning. When ``inherit`` is True and neither
    var is set, returns ``None`` so the caller can fall back to another value.
    """
    preferred = _strip_inline_comment(os.getenv(preferred_var))
    if preferred is not None:
        return _parse_privacy(preferred, default)

    legacy_raw = os.getenv(legacy_var)
    legacy = _strip_inline_comment(legacy_raw)
    if legacy is None:
        return None if inherit else default
    if legacy.lower() in _BOOLEAN_PRIVACY_TOKENS:
        logging.getLogger(__name__).warning(
            "%s is set to a boolean value (%r); this form is deprecated. Use %s=PRIVATE|UNLISTED|PUBLIC instead.",
            legacy_var,
            legacy,
            preferred_var,
        )
    return _parse_privacy(legacy_raw, default)


def _resolve_main_privacy() -> str:
    """Resolve the main playlist privacy (PLAYLIST_PRIVACY, legacy MAKE_PUBLIC)."""
    resolved = _resolve_privacy_setting("PLAYLIST_PRIVACY", "MAKE_PUBLIC", default="PRIVATE")
    assert resolved is not None  # inherit=False guarantees a concrete value
    return resolved


@dataclass(frozen=True)
class Settings:
    """Application configuration loaded from environment variables."""

    lastfm_user: str
    lastfm_api_key: str = field(repr=False)  # Exclude from repr
    ytm_auth_path: str = str(PROJECT_ROOT / "browser.json")
    playlist_name: str = "Last.fm Recents (auto)"
    playlist_description: str = ""
    privacy: str = "PRIVATE"
    limit: int = 100
    deduplicate: bool = True
    sleep_between_searches: float = 0.25
    use_anon_search: bool = True
    early_termination_score: float = 0.9
    use_recency_weighting: bool = True
    recency_half_life_hours: float = 48.0
    recency_play_weight: float = 0.7
    recency_min_plays: int = 1
    recency_normalization: str = "linear"
    recency_velocity_weight: float = 0.0
    recency_session_weighting: bool = False
    recency_session_start: int = 9
    recency_session_end: int = 23
    recency_session_timezone: str = "UTC"
    max_raw_scrobbles: int = 2000
    log_level: str = "INFO"
    timezone: str = "UTC"
    weekly_enabled: bool = True
    weekly_playlist_prefix: str | None = None
    weekly_privacy_status: str | None = None
    weekly_week_start: str = "MON"
    weekly_timezone: str = "UTC"
    weekly_keep_weeks: int = 2
    api_max_retries: int = 3
    search_max_workers: int = 2
    backfill_passes: int = 3
    lastfm_max_retries: int = 5
    lastfm_max_consecutive_empty: int = 3
    lastfm_force_ipv4: bool = True
    cache_playlist_file: str = str(RUNTIME_DIR / ".playlist_cache.json")
    cache_search_file: str = str(RUNTIME_DIR / ".search_cache.json")
    cache_overrides_file: str = str(CONFIG_DIR / "search_overrides.json")
    cache_search_ttl_days: int = 30
    cache_notfound_ttl_days: int = 7
    custom_playlists_file: str = str(CONFIG_DIR / "custom_playlists.json")
    custom_playlists_privacy_status: str | None = None
    tag_cache_file: str = str(RUNTIME_DIR / ".tag_cache.json")
    tag_cache_ttl_days: int = 90
    tag_min_count: int = 10
    tag_sleep_between: float = 0.25
    tag_overrides_file: str = str(CONFIG_DIR / "tag_overrides.json")
    history_db_enabled: bool = False
    history_db_file: str = str(RUNTIME_DIR / "history.db")
    history_max_size_mb: float = 0
    history_retention_days: int = 0
    use_local_lastfm_db: bool = False
    lastfm_local_db_file: str = str(RUNTIME_DIR / "lastfm_history.db")
    lastfm_local_db_max_scrobbles: int = 0
    discovery_rediscover_days: int = 0
    webhook_url: str = ""
    webhook_events: str = "error"
    webhook_allow_private: bool = False

    @property
    def privacy_status(self) -> str:
        """Return YouTube privacy status string."""
        return self.privacy

    @staticmethod
    def from_env() -> "Settings":
        """Load settings from environment variables.

        Re-reads .env with override=True so edits made via the web UI take
        effect without restarting the server (long-running processes like
        gunicorn keep os.environ from their initial load otherwise).
        """
        load_dotenv(PROJECT_ROOT / ".env", override=True)
        lastfm_user = os.getenv("LASTFM_USER", "").strip()
        lastfm_api_key = os.getenv("LASTFM_API_KEY", "").strip()
        if not lastfm_user or not lastfm_api_key:
            raise RuntimeError("LASTFM_USER and LASTFM_API_KEY must be set in environment or .env")

        ytm_auth_path = os.getenv("YTM_AUTH_PATH", str(PROJECT_ROOT / "browser.json"))
        playlist_name = os.getenv("PLAYLIST_NAME", "Last.fm Recents (auto)")
        playlist_description = (_strip_inline_comment(os.getenv("PLAYLIST_DESCRIPTION")) or "").strip()
        privacy = _resolve_main_privacy()

        limit = _str_to_int(os.getenv("LIMIT"), 100)
        deduplicate = _str_to_bool(os.getenv("DEDUPLICATE"), True)
        sleep_between_searches = _str_to_float(os.getenv("SLEEP_BETWEEN_SEARCHES"), 0.25)
        use_anon_search = _str_to_bool(os.getenv("USE_ANON_SEARCH"), True)
        early_termination_score = _str_to_float(os.getenv("EARLY_TERMINATION_SCORE"), 0.9)

        use_recency_weighting = _str_to_bool(os.getenv("USE_RECENCY_WEIGHTING"), True)
        recency_half_life_hours = _str_to_float(os.getenv("RECENCY_HALF_LIFE_HOURS"), 48.0)
        recency_play_weight = _str_to_float(os.getenv("RECENCY_PLAY_WEIGHT"), 0.7)
        if not 0.0 <= recency_play_weight <= 1.0:
            recency_play_weight = 0.7
        recency_min_plays = _str_to_int(os.getenv("RECENCY_MIN_PLAYS"), 1)
        recency_min_plays = max(recency_min_plays, 1)

        recency_normalization = (_strip_inline_comment(os.getenv("RECENCY_NORMALIZATION")) or "linear").strip().lower()
        if recency_normalization not in _VALID_NORMALIZATIONS:
            recency_normalization = "linear"
        recency_velocity_weight = _str_to_float(os.getenv("RECENCY_VELOCITY_WEIGHT"), 0.0)
        if not 0.0 <= recency_velocity_weight <= 1.0:
            recency_velocity_weight = 0.0
        recency_session_weighting = _str_to_bool(os.getenv("RECENCY_SESSION_WEIGHTING"), False)
        recency_session_start, recency_session_end = _parse_session_hours(os.getenv("RECENCY_SESSION_HOURS"))
        timezone = (_strip_inline_comment(os.getenv("TIMEZONE")) or "UTC").strip()
        recency_session_timezone = (
            _strip_inline_comment(os.getenv("RECENCY_SESSION_TIMEZONE")) or _strip_inline_comment(os.getenv("WEEKLY_TIMEZONE")) or timezone
        ).strip()

        max_raw_scrobbles = _str_to_int(os.getenv("MAX_RAW_SCROBBLES"), 2000)
        if max_raw_scrobbles == 0:
            max_raw_scrobbles = 999999  # Effectively unlimited

        log_level = (_strip_inline_comment(os.getenv("LOG_LEVEL")) or "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

        weekly_enabled = _str_to_bool(os.getenv("WEEKLY_ENABLED"), True)

        weekly_playlist_prefix = _strip_inline_comment(os.getenv("WEEKLY_PLAYLIST_PREFIX"))

        weekly_privacy_status = _resolve_privacy_setting("WEEKLY_PLAYLIST_PRIVACY", "WEEKLY_MAKE_PUBLIC", default="PRIVATE", inherit=True)

        weekly_week_start = _strip_inline_comment(os.getenv("WEEKLY_WEEK_START")) or "MON"
        weekly_timezone = _strip_inline_comment(os.getenv("WEEKLY_TIMEZONE")) or timezone
        weekly_keep_weeks = _str_to_int(os.getenv("WEEKLY_KEEP_WEEKS"), 2)
        api_max_retries = _str_to_int(os.getenv("API_MAX_RETRIES"), 3)
        search_max_workers = _str_to_int(os.getenv("SEARCH_MAX_WORKERS"), 2)
        backfill_passes = _str_to_int(os.getenv("BACKFILL_PASSES"), 3)
        lastfm_max_retries = _str_to_int(os.getenv("LASTFM_MAX_RETRIES"), 5)
        lastfm_max_consecutive_empty = _str_to_int(os.getenv("LASTFM_MAX_CONSECUTIVE_EMPTY"), 3)
        lastfm_force_ipv4 = _str_to_bool(os.getenv("LASTFM_FORCE_IPV4"), True)

        cache_playlist_file = _runtime_file("CACHE_PLAYLIST_FILE", ".playlist_cache.json")
        cache_search_file = _runtime_file("CACHE_SEARCH_FILE", ".search_cache.json")
        cache_overrides_file = os.getenv("CACHE_OVERRIDES_FILE", str(CONFIG_DIR / "search_overrides.json"))
        cache_search_ttl_days = _str_to_int(os.getenv("CACHE_SEARCH_TTL_DAYS"), 30)
        cache_notfound_ttl_days = _str_to_int(os.getenv("CACHE_NOTFOUND_TTL_DAYS"), 7)

        custom_playlists_file = os.getenv("CUSTOM_PLAYLISTS_FILE", str(CONFIG_DIR / "custom_playlists.json"))
        custom_playlists_privacy_env = _strip_inline_comment(os.getenv("CUSTOM_PLAYLISTS_PRIVACY"))
        custom_playlists_privacy_status: str | None = None
        if custom_playlists_privacy_env is not None:
            custom_playlists_privacy_status = _parse_privacy(custom_playlists_privacy_env, "PRIVATE")
        tag_cache_file = _runtime_file("TAG_CACHE_FILE", ".tag_cache.json")
        tag_cache_ttl_days = _str_to_int(os.getenv("TAG_CACHE_TTL_DAYS"), 90)
        tag_min_count = _str_to_int(os.getenv("TAG_MIN_COUNT"), 10)
        tag_sleep_between = _str_to_float(os.getenv("TAG_SLEEP_BETWEEN"), 0.25)
        tag_overrides_file = os.getenv("TAG_OVERRIDES_FILE", str(CONFIG_DIR / "tag_overrides.json"))
        history_db_enabled = _str_to_bool(os.getenv("HISTORY_DB_ENABLED"), False)
        history_db_file = _runtime_file("HISTORY_DB_FILE", "history.db")
        history_max_size_mb = _str_to_float(os.getenv("HISTORY_MAX_SIZE_MB"), 0)
        history_retention_days = _str_to_int(os.getenv("HISTORY_RETENTION_DAYS"), 0)
        use_local_lastfm_db = _str_to_bool(os.getenv("USE_LOCAL_LASTFM_DB"), False)
        lastfm_local_db_file = _runtime_file("LASTFM_LOCAL_DB_FILE", "lastfm_history.db")
        lastfm_local_db_max_scrobbles = _str_to_int(os.getenv("LASTFM_LOCAL_DB_MAX_SCROBBLES"), 0)
        discovery_rediscover_days = max(_str_to_int(os.getenv("DISCOVERY_REDISCOVER_DAYS"), 0), 0)
        webhook_url = (_strip_inline_comment(os.getenv("WEBHOOK_URL")) or "").strip()
        webhook_events = (_strip_inline_comment(os.getenv("WEBHOOK_EVENTS")) or "error").strip().lower()
        if webhook_events not in {"all", "error"}:
            webhook_events = "error"
        webhook_allow_private = _str_to_bool(os.getenv("WEBHOOK_ALLOW_PRIVATE"), False)

        return Settings(
            lastfm_user=lastfm_user,
            lastfm_api_key=lastfm_api_key,
            ytm_auth_path=ytm_auth_path,
            playlist_name=playlist_name,
            playlist_description=playlist_description,
            privacy=privacy,
            limit=limit,
            deduplicate=deduplicate,
            sleep_between_searches=sleep_between_searches,
            use_anon_search=use_anon_search,
            early_termination_score=early_termination_score,
            use_recency_weighting=use_recency_weighting,
            recency_half_life_hours=recency_half_life_hours,
            recency_play_weight=recency_play_weight,
            recency_min_plays=recency_min_plays,
            recency_normalization=recency_normalization,
            recency_velocity_weight=recency_velocity_weight,
            recency_session_weighting=recency_session_weighting,
            recency_session_start=recency_session_start,
            recency_session_end=recency_session_end,
            recency_session_timezone=recency_session_timezone,
            timezone=timezone,
            max_raw_scrobbles=max_raw_scrobbles,
            log_level=log_level,
            weekly_enabled=weekly_enabled,
            weekly_playlist_prefix=weekly_playlist_prefix,
            weekly_privacy_status=weekly_privacy_status,
            weekly_week_start=weekly_week_start,
            weekly_timezone=weekly_timezone,
            weekly_keep_weeks=weekly_keep_weeks,
            api_max_retries=api_max_retries,
            search_max_workers=search_max_workers,
            backfill_passes=backfill_passes,
            lastfm_max_retries=lastfm_max_retries,
            lastfm_max_consecutive_empty=lastfm_max_consecutive_empty,
            lastfm_force_ipv4=lastfm_force_ipv4,
            cache_playlist_file=cache_playlist_file,
            cache_search_file=cache_search_file,
            cache_overrides_file=cache_overrides_file,
            cache_search_ttl_days=cache_search_ttl_days,
            cache_notfound_ttl_days=cache_notfound_ttl_days,
            custom_playlists_file=custom_playlists_file,
            custom_playlists_privacy_status=custom_playlists_privacy_status,
            tag_cache_file=tag_cache_file,
            tag_cache_ttl_days=tag_cache_ttl_days,
            tag_min_count=tag_min_count,
            tag_sleep_between=tag_sleep_between,
            tag_overrides_file=tag_overrides_file,
            history_db_enabled=history_db_enabled,
            history_db_file=history_db_file,
            history_max_size_mb=history_max_size_mb,
            history_retention_days=history_retention_days,
            use_local_lastfm_db=use_local_lastfm_db,
            lastfm_local_db_file=lastfm_local_db_file,
            lastfm_local_db_max_scrobbles=lastfm_local_db_max_scrobbles,
            discovery_rediscover_days=discovery_rediscover_days,
            webhook_url=webhook_url,
            webhook_events=webhook_events,
            webhook_allow_private=webhook_allow_private,
        )


_VALID_FILTER_SORTS = ("plays", "recent", "stale", "first_seen", "random")

_VALID_FILTER_TEMPLATES = (
    "custom",
    "top_tracks_7d",
    "top_tracks_30d",
    "top_tracks_90d",
    "forgotten_favorites",
    "not_played_6mo",
    "active_artists",
    "rediscovered_artists",
    "new_to_me",
    "seasonal",
)


@dataclass(frozen=True)
class PlaylistFilterSpec:
    """Composable, reusable filter primitives for template ("filter") playlists.

    Every field is optional and independently combinable; a value of ``0`` (or an
    empty tuple) means "ignore this dimension". Templates are just pre-filled
    instances of this spec, so new playlist ideas rarely need new code — only a
    new preset. All ``*_days`` windows are measured against "now" at sync time.
    """

    min_plays: int = 0
    max_plays: int = 0
    played_within_days: int = 0
    not_played_within_days: int = 0
    first_played_within_days: int = 0
    first_played_before_days: int = 0
    months: tuple[int, ...] = ()
    per_artist_limit: int = 0
    sort: str = "plays"


def _parse_filter_spec(raw: object) -> PlaylistFilterSpec:
    """Parse a raw ``filters`` mapping into a validated ``PlaylistFilterSpec``."""
    if not isinstance(raw, dict):
        return PlaylistFilterSpec()

    def _int(key: str) -> int:
        value = raw.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 0
        return value

    raw_months = raw.get("months", [])
    months = tuple(sorted({m for m in raw_months if isinstance(m, int) and 1 <= m <= 12})) if isinstance(raw_months, list) else ()

    sort = raw.get("sort", "plays")
    if sort not in _VALID_FILTER_SORTS:
        sort = "plays"

    return PlaylistFilterSpec(
        min_plays=_int("min_plays"),
        max_plays=_int("max_plays"),
        played_within_days=_int("played_within_days"),
        not_played_within_days=_int("not_played_within_days"),
        first_played_within_days=_int("first_played_within_days"),
        first_played_before_days=_int("first_played_before_days"),
        months=months,
        per_artist_limit=_int("per_artist_limit"),
        sort=sort,
    )


@dataclass(frozen=True)
class CustomPlaylistConfig:
    """Configuration for a single custom playlist (tag-, artist-, discovery- or filter-based)."""

    name: str
    tags: tuple[str, ...] = ()
    artists: tuple[str, ...] = ()
    kind: str = "tags"
    match: str = "any"
    limit: int = 50
    blacklist: frozenset[str] = frozenset()
    blacklist_artists: frozenset[str] = frozenset()
    backfill: bool = True
    auto_sync: bool = True
    description: str = ""
    privacy: str | None = None
    discovery_seed: str = "artists"
    discovery_seed_auto: bool = True
    discovery_seed_artists: tuple[str, ...] = ()
    discovery_seed_tracks: tuple[tuple[str, str], ...] = ()
    discovery_exclude_scrobbled: bool = True
    filter_template: str = "custom"
    filters: PlaylistFilterSpec = PlaylistFilterSpec()


def load_custom_playlists(path: str) -> list[CustomPlaylistConfig]:
    """Load custom playlist configurations."""
    config_path = Path(path)
    if not config_path.exists():
        return []

    try:
        with config_path.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log = logging.getLogger(__name__)
        log.warning("Failed to load custom playlists from %s: %s", path, e)
        return []

    playlists = data.get("playlists", [])
    configs: list[CustomPlaylistConfig] = []

    for entry in playlists:
        name = entry.get("name")
        kind = entry.get("kind", "tags")
        if kind not in ("tags", "artists", "discovery", "filter"):
            kind = "tags"

        raw_artists = entry.get("artists", [])
        artists = tuple(a.lower() for a in raw_artists if isinstance(a, str) and a.strip())

        tags = entry.get("tags")
        if not name or (kind == "tags" and not tags) or (kind == "artists" and not artists):
            continue

        match = entry.get("match", "any")
        if match not in ("any", "all"):
            match = "any"

        raw_blacklist = entry.get("blacklist", [])
        blacklist = frozenset(k.lower() for k in raw_blacklist if isinstance(k, str))

        raw_blacklist_artists = entry.get("blacklist_artists", [])
        blacklist_artists = frozenset(k.lower() for k in raw_blacklist_artists if isinstance(k, str))

        backfill = entry.get("backfill", True)
        if not isinstance(backfill, bool):
            backfill = True

        auto_sync = entry.get("auto_sync", True)
        if not isinstance(auto_sync, bool):
            auto_sync = True

        description = entry.get("description", "")
        if not isinstance(description, str):
            description = ""

        raw_privacy = entry.get("privacy")
        privacy: str | None = None
        if isinstance(raw_privacy, str) and raw_privacy.strip().upper() in _VALID_PRIVACY:
            privacy = raw_privacy.strip().upper()

        discovery_seed = entry.get("discovery_seed", "artists")
        if discovery_seed not in ("artists", "tracks"):
            discovery_seed = "artists"

        discovery_seed_auto = entry.get("discovery_seed_auto", True)
        if not isinstance(discovery_seed_auto, bool):
            discovery_seed_auto = True

        raw_seed_artists = entry.get("discovery_seed_artists", [])
        discovery_seed_artists = tuple(a.strip() for a in raw_seed_artists if isinstance(a, str) and a.strip())

        raw_seed_tracks = entry.get("discovery_seed_tracks", [])
        seed_tracks: list[tuple[str, str]] = []
        for item in raw_seed_tracks:
            if isinstance(item, dict):
                artist = str(item.get("artist", "")).strip()
                track = str(item.get("track", "")).strip()
                if artist and track:
                    seed_tracks.append((artist, track))
        discovery_seed_tracks = tuple(seed_tracks)

        discovery_exclude_scrobbled = entry.get("discovery_exclude_scrobbled", True)
        if not isinstance(discovery_exclude_scrobbled, bool):
            discovery_exclude_scrobbled = True

        filter_template = entry.get("filter_template", "custom")
        if filter_template not in _VALID_FILTER_TEMPLATES:
            filter_template = "custom"

        filters = _parse_filter_spec(entry.get("filters"))

        configs.append(
            CustomPlaylistConfig(
                name=name,
                tags=tuple(t.lower() for t in tags) if tags else (),
                artists=artists,
                kind=kind,
                match=match,
                limit=entry.get("limit", 50),
                blacklist=blacklist,
                blacklist_artists=blacklist_artists,
                backfill=backfill,
                auto_sync=auto_sync,
                description=description,
                privacy=privacy,
                discovery_seed=discovery_seed,
                discovery_seed_auto=discovery_seed_auto,
                discovery_seed_artists=discovery_seed_artists,
                discovery_seed_tracks=discovery_seed_tracks,
                discovery_exclude_scrobbled=discovery_exclude_scrobbled,
                filter_template=filter_template,
                filters=filters,
            )
        )

    return configs


def configure_logging(level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
