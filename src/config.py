"""Settings from environment variables."""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")

CACHE_DIR = Path(os.getenv("CACHE_DIR", str(PROJECT_ROOT / "cache")))

CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(PROJECT_ROOT / "config")))


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


_VALID_PRIVACY = {"PUBLIC", "UNLISTED", "PRIVATE"}


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
    max_raw_scrobbles: int = 2000
    log_level: str = "INFO"
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
    cache_playlist_file: str = str(CACHE_DIR / ".playlist_cache.json")
    cache_search_file: str = str(CACHE_DIR / ".search_cache.json")
    cache_overrides_file: str = str(CONFIG_DIR / "search_overrides.json")
    cache_search_ttl_days: int = 30
    cache_notfound_ttl_days: int = 7
    custom_playlists_file: str = str(CONFIG_DIR / "custom_playlists.json")
    custom_playlists_privacy_status: str | None = None
    tag_cache_file: str = str(CACHE_DIR / ".tag_cache.json")
    tag_cache_ttl_days: int = 90
    tag_min_count: int = 10
    tag_sleep_between: float = 0.25
    tag_overrides_file: str = str(CONFIG_DIR / "tag_overrides.json")
    history_db_enabled: bool = False
    history_db_file: str = str(CACHE_DIR / "history.db")
    history_max_size_mb: float = 0
    history_retention_days: int = 0
    webhook_url: str = ""
    webhook_events: str = "error"

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
        privacy = _parse_privacy(os.getenv("MAKE_PUBLIC"), "PRIVATE")

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

        max_raw_scrobbles = _str_to_int(os.getenv("MAX_RAW_SCROBBLES"), 2000)
        if max_raw_scrobbles == 0:
            max_raw_scrobbles = 999999  # Effectively unlimited

        log_level = (_strip_inline_comment(os.getenv("LOG_LEVEL")) or "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

        weekly_enabled = _str_to_bool(os.getenv("WEEKLY_ENABLED"), True)

        weekly_playlist_prefix = _strip_inline_comment(os.getenv("WEEKLY_PLAYLIST_PREFIX"))

        weekly_make_public_env = _strip_inline_comment(os.getenv("WEEKLY_MAKE_PUBLIC"))
        weekly_privacy_status: str | None = None
        if weekly_make_public_env is not None:
            weekly_privacy_status = _parse_privacy(weekly_make_public_env, "PRIVATE")

        weekly_week_start = _strip_inline_comment(os.getenv("WEEKLY_WEEK_START")) or "MON"
        weekly_timezone = _strip_inline_comment(os.getenv("WEEKLY_TIMEZONE")) or "UTC"
        weekly_keep_weeks = _str_to_int(os.getenv("WEEKLY_KEEP_WEEKS"), 2)
        api_max_retries = _str_to_int(os.getenv("API_MAX_RETRIES"), 3)
        search_max_workers = _str_to_int(os.getenv("SEARCH_MAX_WORKERS"), 2)
        backfill_passes = _str_to_int(os.getenv("BACKFILL_PASSES"), 3)
        lastfm_max_retries = _str_to_int(os.getenv("LASTFM_MAX_RETRIES"), 5)
        lastfm_max_consecutive_empty = _str_to_int(os.getenv("LASTFM_MAX_CONSECUTIVE_EMPTY"), 3)
        lastfm_force_ipv4 = _str_to_bool(os.getenv("LASTFM_FORCE_IPV4"), True)

        cache_playlist_file = os.getenv("CACHE_PLAYLIST_FILE", str(CACHE_DIR / ".playlist_cache.json"))
        cache_search_file = os.getenv("CACHE_SEARCH_FILE", str(CACHE_DIR / ".search_cache.json"))
        cache_overrides_file = os.getenv("CACHE_OVERRIDES_FILE", str(CONFIG_DIR / "search_overrides.json"))
        cache_search_ttl_days = _str_to_int(os.getenv("CACHE_SEARCH_TTL_DAYS"), 30)
        cache_notfound_ttl_days = _str_to_int(os.getenv("CACHE_NOTFOUND_TTL_DAYS"), 7)

        custom_playlists_file = os.getenv("CUSTOM_PLAYLISTS_FILE", str(CONFIG_DIR / "custom_playlists.json"))
        custom_playlists_privacy_env = _strip_inline_comment(os.getenv("CUSTOM_PLAYLISTS_PRIVACY"))
        custom_playlists_privacy_status: str | None = None
        if custom_playlists_privacy_env is not None:
            custom_playlists_privacy_status = _parse_privacy(custom_playlists_privacy_env, "PRIVATE")
        tag_cache_file = os.getenv("TAG_CACHE_FILE", str(CACHE_DIR / ".tag_cache.json"))
        tag_cache_ttl_days = _str_to_int(os.getenv("TAG_CACHE_TTL_DAYS"), 90)
        tag_min_count = _str_to_int(os.getenv("TAG_MIN_COUNT"), 10)
        tag_sleep_between = _str_to_float(os.getenv("TAG_SLEEP_BETWEEN"), 0.25)
        tag_overrides_file = os.getenv("TAG_OVERRIDES_FILE", str(CONFIG_DIR / "tag_overrides.json"))
        history_db_enabled = _str_to_bool(os.getenv("HISTORY_DB_ENABLED"), False)
        history_db_file = os.getenv("HISTORY_DB_FILE", str(CACHE_DIR / "history.db"))
        history_max_size_mb = _str_to_float(os.getenv("HISTORY_MAX_SIZE_MB"), 0)
        history_retention_days = _str_to_int(os.getenv("HISTORY_RETENTION_DAYS"), 0)
        webhook_url = (_strip_inline_comment(os.getenv("WEBHOOK_URL")) or "").strip()
        webhook_events = (_strip_inline_comment(os.getenv("WEBHOOK_EVENTS")) or "error").strip().lower()
        if webhook_events not in {"all", "error"}:
            webhook_events = "error"

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
            webhook_url=webhook_url,
            webhook_events=webhook_events,
        )


@dataclass(frozen=True)
class CustomPlaylistConfig:
    """Configuration for a single tag-based custom playlist."""

    name: str
    tags: tuple[str, ...]
    match: str = "any"
    limit: int = 50
    blacklist: frozenset[str] = frozenset()
    backfill: bool = True
    auto_sync: bool = True
    description: str = ""


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
        tags = entry.get("tags")
        if not name or not tags:
            continue

        match = entry.get("match", "any")
        if match not in ("any", "all"):
            match = "any"

        raw_blacklist = entry.get("blacklist", [])
        blacklist = frozenset(k.lower() for k in raw_blacklist if isinstance(k, str))

        backfill = entry.get("backfill", True)
        if not isinstance(backfill, bool):
            backfill = True

        auto_sync = entry.get("auto_sync", True)
        if not isinstance(auto_sync, bool):
            auto_sync = True

        description = entry.get("description", "")
        if not isinstance(description, str):
            description = ""

        configs.append(
            CustomPlaylistConfig(
                name=name,
                tags=tuple(t.lower() for t in tags),
                match=match,
                limit=entry.get("limit", 50),
                blacklist=blacklist,
                backfill=backfill,
                auto_sync=auto_sync,
                description=description,
            )
        )

    return configs


def configure_logging(level: str) -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
