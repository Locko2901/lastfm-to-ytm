"""Web dashboard services."""

from .data import (
    clear_failure_log,
    get_cache_stats,
    get_cached_tracks,
    get_last_sync_time,
    get_not_found_tracks,
    get_overrides_data,
    get_playlist_links,
    get_playlist_mappings,
    get_setup_status,
    load_failure_log,
    load_overrides,
    load_run_log,
    load_search_cache,
)
from .env import (
    ALL_SETTINGS,
    BOOL_SETTINGS,
    BROWSER_JSON_FILE,
    ENV_EXAMPLE_FILE,
    ENV_FILE,
    parse_env_file,
    update_env_file,
)
from .scheduler import (
    get_scheduler_status,
    init_scheduler_from_env,
    start_scheduler,
    stop_scheduler,
)
from .state import (
    sync_lock,
    sync_state,
)

__all__ = [
    "ALL_SETTINGS",
    "BOOL_SETTINGS",
    "BROWSER_JSON_FILE",
    "ENV_EXAMPLE_FILE",
    "ENV_FILE",
    "clear_failure_log",
    "get_cache_stats",
    "get_cached_tracks",
    "get_last_sync_time",
    "get_not_found_tracks",
    "get_overrides_data",
    "get_playlist_links",
    "get_playlist_mappings",
    "get_scheduler_status",
    "get_setup_status",
    "init_scheduler_from_env",
    "load_failure_log",
    "load_overrides",
    "load_run_log",
    "load_search_cache",
    "parse_env_file",
    "start_scheduler",
    "stop_scheduler",
    "sync_lock",
    "sync_state",
    "update_env_file",
]
