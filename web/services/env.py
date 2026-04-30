"""Environment file parsing and updating."""

from __future__ import annotations

from src.config import PROJECT_ROOT

ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE_FILE = PROJECT_ROOT / ".env.example"
BROWSER_JSON_FILE = PROJECT_ROOT / "browser.json"

BOOL_SETTINGS = {
    "DEDUPLICATE",
    "USE_ANON_SEARCH",
    "USE_RECENCY_WEIGHTING",
    "WEEKLY_ENABLED",
    "LASTFM_FORCE_IPV4",
    "AUTO_SYNC_ENABLED",
    "AUTO_TAG_SYNC_ENABLED",
    "USE_24_HOUR_CLOCK",
    "NOW_PLAYING_ENABLED",
    "HISTORY_DB_ENABLED",
    "DISPLAY_TIPS",
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
    "WEBHOOK_URL",
    "WEBHOOK_EVENTS",
]


def parse_env_file() -> dict[str, str]:
    """Parse .env file into key-value pairs."""
    settings = {}
    if not ENV_FILE.exists():
        return settings

    with ENV_FILE.open() as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                for marker in (" #", "\t#"):
                    idx = value.find(marker)
                    if idx != -1:
                        value = value[:idx]
                        break
                settings[key] = value.strip()

    return settings


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
