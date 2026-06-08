"""Builder for the main dashboard page context.

Collects the independent data sources the dashboard template needs into a
single :class:`DashboardContext`, keeping the ``/`` route thin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .data import (
    get_cache_stats,
    get_cached_tracks,
    get_last_sync_time,
    get_not_found_tracks,
    get_overrides_data,
    get_playlist_links,
    get_playlist_mappings,
    get_setup_status,
    get_tag_cache_tracks,
    get_tag_overrides_data,
    get_tag_stats,
    get_track_tag_overrides_map,
    get_track_tags_map,
    is_history_enabled,
    load_custom_playlists_config,
)
from .env import parse_env_file
from .state import sync_state

DOCS_URL = "https://locko2901.github.io/lastfm-to-ytm/"

_TRUTHY_DEFAULT = "true"
_FALSY_VALUES = frozenset({"false", "0", "no", "off", "f", "n"})


def _display_tips_enabled() -> bool:
    """Read the ``DISPLAY_TIPS`` env flag, defaulting to enabled."""
    raw = parse_env_file().get("DISPLAY_TIPS", _TRUTHY_DEFAULT).strip().lower()
    return raw not in _FALSY_VALUES


@dataclass(frozen=True, slots=True)
class DashboardContext:
    """All data required to render the main dashboard template."""

    mappings: Any
    limit: Any
    timestamp: Any
    total: Any
    resolved: int
    overrides: Any
    blacklist: Any
    cache_stats: Any
    cached_tracks: Any
    not_found_tracks: Any
    sync_running: bool
    last_sync: Any
    playlist_links: Any
    needs_setup: bool
    needs_auth: bool
    tag_cache_tracks: Any
    tag_stats: Any
    tag_overrides: Any
    custom_playlists: Any
    track_tags_map: Any
    tag_overrides_map: Any
    history_enabled: bool
    display_tips: bool
    docs_url: str = DOCS_URL

    @classmethod
    def build(cls) -> DashboardContext:
        """Gather every data source the dashboard needs."""
        playlist_mappings, run_log = get_playlist_mappings()
        override_list, blacklist = get_overrides_data()
        setup = get_setup_status()

        return cls(
            mappings=playlist_mappings,
            limit=run_log["limit"],
            timestamp=run_log["timestamp"],
            total=run_log["total"],
            resolved=len(playlist_mappings),
            overrides=override_list,
            blacklist=blacklist,
            cache_stats=get_cache_stats(),
            cached_tracks=get_cached_tracks(),
            not_found_tracks=get_not_found_tracks(),
            sync_running=sync_state["running"],
            last_sync=get_last_sync_time(),
            playlist_links=get_playlist_links(),
            needs_setup=setup["needs_setup"],
            needs_auth=setup["needs_auth"],
            tag_cache_tracks=get_tag_cache_tracks(),
            tag_stats=get_tag_stats(),
            tag_overrides=get_tag_overrides_data(),
            custom_playlists=load_custom_playlists_config(),
            track_tags_map=get_track_tags_map(),
            tag_overrides_map=get_track_tag_overrides_map(),
            history_enabled=is_history_enabled(),
            display_tips=_display_tips_enabled(),
        )

    def to_template_context(self) -> dict[str, Any]:
        """Return the keyword arguments for ``render_template``."""
        return {
            "mappings": self.mappings,
            "limit": self.limit,
            "timestamp": self.timestamp,
            "total": self.total,
            "resolved": self.resolved,
            "overrides": self.overrides,
            "blacklist": self.blacklist,
            "cache_stats": self.cache_stats,
            "cached_tracks": self.cached_tracks,
            "not_found_tracks": self.not_found_tracks,
            "sync_running": self.sync_running,
            "last_sync": self.last_sync,
            "playlist_links": self.playlist_links,
            "needs_setup": self.needs_setup,
            "needs_auth": self.needs_auth,
            "tag_cache_tracks": self.tag_cache_tracks,
            "tag_stats": self.tag_stats,
            "tag_overrides": self.tag_overrides,
            "custom_playlists": self.custom_playlists,
            "track_tags_map": self.track_tags_map,
            "tag_overrides_map": self.tag_overrides_map,
            "history_enabled": self.history_enabled,
            "display_tips": self.display_tips,
            "docs_url": self.docs_url,
        }
