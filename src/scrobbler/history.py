"""YouTube Music listening history as returned by ytmusicapi's ``get_history()``.

The history has no play times. Each row only carries the shelf it sits in
(``played``: "Today", "Yesterday", "This week", a month, ...). It is one
unpaginated page of roughly 200 rows, newest first, and a song played again
moves to the top instead of appearing twice.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ytmusicapi.exceptions import YTMusicServerError

from ..config import Settings
from ..search.normalization import RE_TOPIC_SUFFIX
from ..ytm import build_oauth_client, is_signed_out, retry_with_backoff
from .matching import clean_video_title, split_artist_title

log = logging.getLogger(__name__)

TODAY_LABEL = "today"
SONG_VIDEO_TYPE = "MUSIC_VIDEO_TYPE_ATV"
UPLOAD_VIDEO_TYPE = "MUSIC_VIDEO_TYPE_UGC"
NON_MUSIC_VIDEO_TYPES = frozenset({"MUSIC_VIDEO_TYPE_PODCAST_EPISODE"})


@dataclass(frozen=True, slots=True)
class HistoryItem:
    """One row of the YouTube Music history."""

    video_id: str
    title: str
    artists: tuple[str, ...]
    album: str = ""
    duration: int | None = None
    played: str = ""
    video_type: str = ""

    @property
    def is_today(self) -> bool:
        """True when the row sits in the "Today" shelf."""
        return self.played.strip().lower() == TODAY_LABEL

    @property
    def is_music(self) -> bool:
        """False for podcast episodes, which are never scrobbled."""
        return self.video_type not in NON_MUSIC_VIDEO_TYPES

    @property
    def is_upload(self) -> bool:
        """True for a video a user uploaded: its "artist" is the uploading channel."""
        return self.video_type == UPLOAD_VIDEO_TYPE

    @property
    def scrobble_artist(self) -> str:
        """The primary artist, as sent to Last.fm.

        For an upload it comes from an "Artist - Title" video title, since the
        channel is not the artist; empty when the title has no such form.
        """
        if self.is_upload:
            parts = split_artist_title(self.title)
            return parts[0] if parts else ""
        return RE_TOPIC_SUFFIX.sub("", self.artists[0]).strip() if self.artists else ""

    @property
    def scrobble_title(self) -> str:
        """The title as sent to Last.fm; music videos lose "(Official Video)" noise."""
        if self.is_upload:
            parts = split_artist_title(self.title)
            return parts[1] if parts else ""
        if self.video_type and self.video_type != SONG_VIDEO_TYPE:
            return clean_video_title(self.title, self.scrobble_artist)
        return self.title.strip()

    @property
    def match_artists(self) -> tuple[str, ...]:
        """Artists to compare with scrobbles: the credited ones, or the one read from an upload's title."""
        if self.is_upload:
            return (self.scrobble_artist,) if self.scrobble_artist else ()
        return self.artists


def _duration(entry: Mapping[str, Any]) -> int | None:
    """Return the duration in seconds, or None when YouTube Music gave none."""
    value = entry.get("duration_seconds")
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return None


def parse_history(raw: Iterable[Mapping[str, Any]]) -> tuple[list[HistoryItem], int]:
    """Parse ``get_history()`` rows into items, newest first.

    Rows without a video ID are dropped. A video ID seen twice keeps its first
    (newest) row; the number of such repeats is returned so the dashboard can
    show whether the "one row per song" assumption ever breaks.
    """
    items: list[HistoryItem] = []
    seen: set[str] = set()
    repeats = 0
    for entry in raw:
        video_id = entry.get("videoId")
        if not isinstance(video_id, str) or not video_id:
            continue
        if video_id in seen:
            repeats += 1
            continue
        seen.add(video_id)
        artists = tuple(
            str(a["name"]).strip() for a in entry.get("artists") or [] if isinstance(a, Mapping) and a.get("name") and str(a["name"]).strip()
        )
        album = entry.get("album")
        album_name = str(album.get("name") or "").strip() if isinstance(album, Mapping) else ""
        items.append(
            HistoryItem(
                video_id=video_id,
                title=str(entry.get("title") or "").strip(),
                artists=artists,
                album=album_name,
                duration=_duration(entry),
                played=str(entry.get("played") or "").strip(),
                video_type=str(entry.get("videoType") or ""),
            )
        )
    if repeats:
        log.info("YouTube Music history listed %d song(s) more than once", repeats)
    return items, repeats


class HistorySignedOut(Exception):
    """YouTube Music answered the history read as signed out: only reconnecting the session helps."""


def _notice_title(error: BaseException) -> str | None:
    """The title of the notice shelf ytmusicapi raised instead of the history (a paused history, for example)."""
    notice = error.args[0] if error.args else None
    if isinstance(notice, Mapping) and notice.get("text"):
        return str(notice["text"])
    return None


def fetch_history(ytm: Any, *, max_retries: int = 3) -> tuple[list[HistoryItem], int]:
    """Read the history with an authenticated ``YTMusic`` client, retried like the playlist sync (``retry_with_backoff``).

    A signed-out answer raises ``HistorySignedOut`` and a notice shelf a
    ``YTMusicServerError`` with the notice's title.
    """
    try:
        raw = retry_with_backoff(ytm.get_history, max_retries=max_retries, operation="get_history")
    except Exception as e:
        if is_signed_out(e):
            raise HistorySignedOut from e
        title = _notice_title(e)
        if title:
            raise YTMusicServerError(title) from e
        raise
    return parse_history(raw)


def history_reader(settings: Settings) -> Callable[[], tuple[list[HistoryItem], int]]:
    """A reader of the history through the sync's YouTube Music client, trying up to ``API_MAX_RETRIES`` times per read."""

    def read() -> tuple[list[HistoryItem], int]:
        return fetch_history(build_oauth_client(settings.ytm_auth_path), max_retries=settings.api_max_retries)

    return read
