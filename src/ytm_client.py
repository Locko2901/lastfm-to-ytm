from __future__ import annotations

import time
from typing import Dict, List, Optional

from ytmusicapi import YTMusic


def build_oauth_client(auth_path: str) -> YTMusic:
    return YTMusic(auth_path)


def get_existing_playlist_by_name(ytm: YTMusic, name: str) -> Optional[str]:
    try:
        playlists = ytm.get_library_playlists(limit=1000)
    except Exception:
        playlists = []
    for p in playlists or []:
        if p.get("title") == name:
            return p.get("playlistId")
    return None


def add_items_fallback(ytm: YTMusic, pl_id: str, video_ids: List[str], chunk_size: int = 75) -> None:
    for start in range(0, len(video_ids), chunk_size):
        chunk = video_ids[start : start + chunk_size]
        try:
            ytm.add_playlist_items(pl_id, chunk, duplicates=False)
        except Exception:
            for vid in chunk:
                try:
                    ytm.add_playlist_items(pl_id, [vid], duplicates=False)
                except Exception:
                    pass
        time.sleep(0.2)


def create_playlist_with_items(
    ytm: YTMusic, name: str, desc: str, privacy: str, video_ids: List[str]
) -> str:
    """
    Create a playlist, adding items in one call if supported, else fallback.
    """
    try:
        return ytm.create_playlist(name, desc, privacy_status=privacy, video_ids=video_ids)
    except TypeError:
        pass
    except Exception:
        pass

    pl_id = ytm.create_playlist(name, desc, privacy_status=privacy)
    add_items_fallback(ytm, pl_id, video_ids)
    return pl_id
