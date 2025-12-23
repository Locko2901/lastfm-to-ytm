import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")

CACHE_DIR = Path(os.getenv("CACHE_DIR", str(PROJECT_ROOT / "cache")))

CONFIG_DIR = Path(os.getenv("CONFIG_DIR", str(PROJECT_ROOT / "config")))


def _str_to_bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _str_to_float(val: str | None, default: float) -> float:
    try:
        return float(val) if val is not None else default
    except Exception:
        return default


def _str_to_int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None else default
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    """Application configuration loaded from environment variables."""

    lastfm_user: str
    lastfm_api_key: str
    ytm_auth_path: str = str(PROJECT_ROOT / "browser.json")
    playlist_name: str = "Last.fm Recents (auto)"
    make_public: bool = False
    limit: int = 100
    deduplicate: bool = True
    sleep_between_searches: float = 0.25
    use_anon_search: bool = True
    early_termination_score: float = 0.9
    use_recency_weighting: bool = True
    recency_half_life_hours: float = 24.0
    recency_play_weight: float = 0.7
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

    @property
    def privacy_status(self) -> str:
        """Return YouTube privacy status string."""
        return "PUBLIC" if self.make_public else "PRIVATE"

    @staticmethod
    def from_env() -> "Settings":
        """Load settings from environment variables."""
        lastfm_user = os.getenv("LASTFM_USER", "").strip()
        lastfm_api_key = os.getenv("LASTFM_API_KEY", "").strip()
        if not lastfm_user or not lastfm_api_key:
            raise RuntimeError("LASTFM_USER and LASTFM_API_KEY must be set in environment or .env")

        ytm_auth_path = os.getenv("YTM_AUTH_PATH", str(PROJECT_ROOT / "browser.json"))
        playlist_name = os.getenv("PLAYLIST_NAME", "Last.fm Recents (auto)")
        make_public = _str_to_bool(os.getenv("MAKE_PUBLIC"), False)

        limit = _str_to_int(os.getenv("LIMIT"), 100)
        deduplicate = _str_to_bool(os.getenv("DEDUPLICATE"), True)
        sleep_between_searches = _str_to_float(os.getenv("SLEEP_BETWEEN_SEARCHES"), 0.25)
        use_anon_search = _str_to_bool(os.getenv("USE_ANON_SEARCH"), False)
        early_termination_score = _str_to_float(os.getenv("EARLY_TERMINATION_SCORE"), 0.9)

        use_recency_weighting = _str_to_bool(os.getenv("USE_RECENCY_WEIGHTING"), True)
        recency_half_life_hours = _str_to_float(os.getenv("RECENCY_HALF_LIFE_HOURS"), 24.0)
        recency_play_weight = _str_to_float(os.getenv("RECENCY_PLAY_WEIGHT"), 0.7)
        if not 0.0 <= recency_play_weight <= 1.0:
            recency_play_weight = 0.7

        max_raw_scrobbles = _str_to_int(os.getenv("MAX_RAW_SCROBBLES"), 2000)
        if max_raw_scrobbles == 0:
            max_raw_scrobbles = 999999  # Effectively unlimited

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

        weekly_enabled = _str_to_bool(os.getenv("WEEKLY_ENABLED"), True)

        weekly_playlist_prefix_env = os.getenv("WEEKLY_PLAYLIST_PREFIX")
        weekly_playlist_prefix = weekly_playlist_prefix_env.strip() if weekly_playlist_prefix_env else None
        if weekly_playlist_prefix == "":
            weekly_playlist_prefix = None

        weekly_make_public_env = os.getenv("WEEKLY_MAKE_PUBLIC")
        weekly_privacy_status: str | None = None
        if weekly_make_public_env is not None:
            weekly_privacy_status = "PUBLIC" if _str_to_bool(weekly_make_public_env, False) else "PRIVATE"

        weekly_week_start = os.getenv("WEEKLY_WEEK_START", "MON")
        weekly_timezone = os.getenv("WEEKLY_TIMEZONE", "UTC") or "UTC"
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

        return Settings(
            lastfm_user=lastfm_user,
            lastfm_api_key=lastfm_api_key,
            ytm_auth_path=ytm_auth_path,
            playlist_name=playlist_name,
            make_public=make_public,
            limit=limit,
            deduplicate=deduplicate,
            sleep_between_searches=sleep_between_searches,
            use_anon_search=use_anon_search,
            early_termination_score=early_termination_score,
            use_recency_weighting=use_recency_weighting,
            recency_half_life_hours=recency_half_life_hours,
            recency_play_weight=recency_play_weight,
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
        )


def configure_logging(level: str) -> None:
    """Configure logging with the specified level."""
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
