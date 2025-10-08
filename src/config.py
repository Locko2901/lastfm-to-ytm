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
    # Last.fm
    lastfm_user: str
    lastfm_api_key: str

    # YTMusic OAuth auth file
    ytm_auth_path: str = "browser.json"

    # Playlist
    playlist_name: str = "Last.fm Recents (auto)"
    make_public: bool = False

    # Fetch/search behavior
    limit: int = 100
    deduplicate: bool = True
    sleep_between_searches: float = 0.25
    use_anon_search: bool = False
    chunk_size: int = 75

    # Recency weighting
    use_recency_weighting: bool = True
    recency_half_life_hours: float = 24.0
    recency_max_unique: Optional[int] = None

    # Logging
    log_level: str = "INFO"

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
        limit = max(1, min(200, limit))
        deduplicate = _str_to_bool(os.getenv("DEDUPLICATE"), True)
        sleep_between_searches = _str_to_float(os.getenv("SLEEP_BETWEEN_SEARCHES"), 0.25)
        use_anon_search = _str_to_bool(os.getenv("USE_ANON_SEARCH"), False)
        chunk_size = _str_to_int(os.getenv("CHUNK_SIZE"), 75)

        use_recency_weighting = _str_to_bool(os.getenv("USE_RECENCY_WEIGHTING"), True)
        recency_half_life_hours = _str_to_float(os.getenv("RECENCY_HALF_LIFE_HOURS"), 24.0)
        recency_max_unique_env = os.getenv("RECENCY_MAX_UNIQUE")
        recency_max_unique = None
        if recency_max_unique_env:
            try:
                recency_max_unique = int(recency_max_unique_env)
            except Exception:
                recency_max_unique = None

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        if log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            log_level = "INFO"

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
            use_recency_weighting=use_recency_weighting,
            recency_half_life_hours=recency_half_life_hours,
            recency_max_unique=recency_max_unique,
            log_level=log_level,
        )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
