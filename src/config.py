from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


def _str_to_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _str_to_float(val: Optional[str], default: float) -> float:
    try:
        return float(val) if val is not None else default
    except Exception:
        return default


def _str_to_int(val: Optional[str], default: int) -> int:
    try:
        return int(val) if val is not None else default
    except Exception:
        return default


@dataclass(frozen=True)
class Settings:
    lastfm_user: str
    lastfm_api_key: str
    ytm_auth_path: str = "browser.json"
    playlist_name: str = "Last.fm Recents (auto)"
    make_public: bool = False
    limit: int = 100
    deduplicate: bool = True
    sleep_between_searches: float = 0.25
    use_anon_search: bool = False
    chunk_size: int = 75
    early_termination_score: float = 0.9
    use_recency_weighting: bool = True
    recency_half_life_hours: float = 24.0
    recency_max_unique: Optional[int] = None
    log_level: str = "INFO"
    weekly_enabled: bool = True
    weekly_playlist_prefix: Optional[str] = None
    weekly_privacy_status: Optional[str] = None
    weekly_week_start: str = "MON"
    weekly_timezone: str = "UTC"
    weekly_keep_weeks: int = 2

    @property
    def privacy_status(self) -> str:
        return "PUBLIC" if self.make_public else "PRIVATE"

    @staticmethod
    def from_env() -> "Settings":
        lastfm_user = os.getenv("LASTFM_USER", "").strip()
        lastfm_api_key = os.getenv("LASTFM_API_KEY", "").strip()
        if not lastfm_user or not lastfm_api_key:
            raise RuntimeError("LASTFM_USER and LASTFM_API_KEY must be set in environment or .env")

        ytm_auth_path = os.getenv("YTM_AUTH_PATH", "browser.json")
        playlist_name = os.getenv("PLAYLIST_NAME", "Last.fm Recents (auto)")
        make_public = _str_to_bool(os.getenv("MAKE_PUBLIC"), False)

        limit = _str_to_int(os.getenv("LIMIT"), 100)
        limit = max(1, min(400, limit))
        deduplicate = _str_to_bool(os.getenv("DEDUPLICATE"), True)
        sleep_between_searches = _str_to_float(os.getenv("SLEEP_BETWEEN_SEARCHES"), 0.25)
        use_anon_search = _str_to_bool(os.getenv("USE_ANON_SEARCH"), False)
        chunk_size = _str_to_int(os.getenv("CHUNK_SIZE"), 75)
        early_termination_score = _str_to_float(os.getenv("EARLY_TERMINATION_SCORE"), 0.9)

        use_recency_weighting = _str_to_bool(os.getenv("USE_RECENCY_WEIGHTING"), True)
        recency_half_life_hours = _str_to_float(os.getenv("RECENCY_HALF_LIFE_HOURS"), 24.0)
        recency_max_unique_env = os.getenv("RECENCY_MAX_UNIQUE")
        recency_max_unique: Optional[int] = None
        if recency_max_unique_env:
            try:
                recency_max_unique = int(recency_max_unique_env)
            except Exception:
                recency_max_unique = None

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

        weekly_enabled = _str_to_bool(os.getenv("WEEKLY_ENABLED"), True)

        weekly_playlist_prefix_env = os.getenv("WEEKLY_PLAYLIST_PREFIX")
        weekly_playlist_prefix = weekly_playlist_prefix_env.strip() if weekly_playlist_prefix_env else None
        if weekly_playlist_prefix == "":
            weekly_playlist_prefix = None

        weekly_make_public_env = os.getenv("WEEKLY_MAKE_PUBLIC")
        weekly_privacy_status: Optional[str] = None
        if weekly_make_public_env is not None:
            weekly_privacy_status = "PUBLIC" if _str_to_bool(weekly_make_public_env, False) else "PRIVATE"

        weekly_week_start = os.getenv("WEEKLY_WEEK_START", "MON")
        weekly_timezone = os.getenv("WEEKLY_TIMEZONE", "UTC") or "UTC"
        weekly_keep_weeks = _str_to_int(os.getenv("WEEKLY_KEEP_WEEKS"), 2)

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
            chunk_size=chunk_size,
            early_termination_score=early_termination_score,
            use_recency_weighting=use_recency_weighting,
            recency_half_life_hours=recency_half_life_hours,
            recency_max_unique=recency_max_unique,
            log_level=log_level,
            weekly_enabled=weekly_enabled,
            weekly_playlist_prefix=weekly_playlist_prefix,
            weekly_privacy_status=weekly_privacy_status,
            weekly_week_start=weekly_week_start,
            weekly_timezone=weekly_timezone,
            weekly_keep_weeks=weekly_keep_weeks,
        )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
