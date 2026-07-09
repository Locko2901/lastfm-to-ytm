import logging
import socket
import time
from collections.abc import Iterator
from typing import Any

import requests

from .scrobble import Scrobble

log = logging.getLogger(__name__)

_orig_getaddrinfo = socket.getaddrinfo
_ipv4_enabled = False


def _getaddrinfo_ipv4_only(host: Any, port: Any, family: int = 0, type: int = 0, proto: int = 0, flags: int = 0) -> Any:
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


def enable_ipv4_only() -> None:
    """Force IPv4-only connections."""
    global _ipv4_enabled
    if not _ipv4_enabled:
        socket.getaddrinfo = _getaddrinfo_ipv4_only
        _ipv4_enabled = True


def disable_ipv4_only() -> None:
    """Restore dual-stack socket behavior."""
    global _ipv4_enabled
    if _ipv4_enabled:
        socket.getaddrinfo = _orig_getaddrinfo
        _ipv4_enabled = False


LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


def _make_api_request(
    params: dict[str, Any],
    page: int,
    max_retries: int,
) -> dict[str, Any] | None:
    """Make API request with retries."""
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            resp = requests.get(LASTFM_API_URL, params=params, timeout=30)

            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < max_retries - 1:
                    wait = retry_delay
                    retry_after = resp.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        wait = max(wait, int(retry_after))
                    log.warning(
                        "Last.fm %d error, retrying in %ds (%d/%d)",
                        resp.status_code,
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait)
                    retry_delay *= 2
                    continue
                log.error("Last.fm API error %d, max retries reached", resp.status_code)
                return None

            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

        except requests.exceptions.RequestException as e:
            if attempt < max_retries - 1:
                log.warning("Request failed: %s, retrying in %ds", e, retry_delay)
                time.sleep(retry_delay)
                retry_delay *= 2
                continue
            log.error("Request failed after %d retries: %s", max_retries, e)
            return None

    return None


def _parse_tracks(tracks: list[dict[str, Any]]) -> list[Scrobble]:
    """Parse API tracks into Scrobbles."""
    scrobbles: list[Scrobble] = []

    for t in tracks:
        if t.get("@attr", {}).get("nowplaying") == "true":
            continue

        uts = t.get("date", {}).get("uts")
        if not uts:
            continue

        artist = ""
        a = t.get("artist")
        if isinstance(a, dict):
            artist = a.get("#text") or ""
        elif isinstance(a, str):
            artist = a or ""

        track = t.get("name") or ""

        album = ""
        alb = t.get("album")
        if isinstance(alb, dict):
            album = alb.get("#text") or ""
        elif isinstance(alb, str):
            album = alb

        artist = artist.strip()
        track = track.strip()
        album = album.strip()

        if artist and track:
            scrobbles.append(Scrobble(artist=artist, track=track, album=album, ts=int(uts)))

    return scrobbles


def fetch_recent(
    username: str,
    api_key: str,
    limit: int = 100,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    max_retries: int = 5,
) -> list[Scrobble]:
    """Fetch recent scrobbles."""
    per_page = min(200, limit)
    all_scrobbles: list[Scrobble] = []
    page = 1

    while len(all_scrobbles) < limit:
        remaining = limit - len(all_scrobbles)
        current_limit = min(per_page, remaining)

        params: dict[str, Any] = {
            "method": "user.getrecenttracks",
            "user": username,
            "api_key": api_key,
            "format": "json",
            "limit": current_limit,
            "page": page,
        }

        if from_timestamp is not None:
            params["from"] = str(from_timestamp)
        if to_timestamp is not None:
            params["to"] = str(to_timestamp)

        data = _make_api_request(params, page, max_retries)
        if data is None:
            break

        recenttracks = data.get("recenttracks", {})
        tracks = recenttracks.get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]

        if not tracks:
            break

        all_scrobbles.extend(_parse_tracks(tracks))

        attr = recenttracks.get("@attr", {})
        total_pages = int(attr.get("totalPages", "0") or "0")

        if total_pages > 0 and page >= total_pages:
            break

        page += 1

    return all_scrobbles


def iter_all_scrobbles(
    username: str,
    api_key: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    max_retries: int = 5,
    per_page: int = 200,
    max_scrobbles: int = 0,
) -> Iterator[list[Scrobble]]:
    """Yield scrobbles page by page across the user's entire history.

    Pages from newest to oldest until exhausted (or ``max_scrobbles`` reached).
    Pass ``from_timestamp`` to fetch only scrobbles newer than a watermark
    (used for incremental syncs). Yielding per page keeps memory bounded so the
    caller can stream batches straight into a database.
    """
    per_page = max(1, min(200, per_page))
    page = 1
    total_pages: int | None = None
    yielded = 0

    while True:
        params: dict[str, Any] = {
            "method": "user.getrecenttracks",
            "user": username,
            "api_key": api_key,
            "format": "json",
            "limit": per_page,
            "page": page,
        }
        if from_timestamp is not None:
            params["from"] = str(from_timestamp)
        if to_timestamp is not None:
            params["to"] = str(to_timestamp)

        data = _make_api_request(params, page, max_retries)
        if data is None:
            log.info(
                "iter_all_scrobbles: stopping at page %d - Last.fm request failed after retries (%d scrobbles fetched)",
                page,
                yielded,
            )
            break

        recenttracks = data.get("recenttracks", {})
        tracks = recenttracks.get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]

        if not tracks:
            log.info(
                "iter_all_scrobbles: stopping at page %d - empty page returned (%d scrobbles fetched)",
                page,
                yielded,
            )
            break

        if total_pages is None:
            attr = recenttracks.get("@attr", {})
            total_pages = int(attr.get("totalPages", "0") or "0")

        page_scrobbles = _parse_tracks(tracks)
        if page_scrobbles:
            if max_scrobbles > 0 and yielded + len(page_scrobbles) > max_scrobbles:
                page_scrobbles = page_scrobbles[: max_scrobbles - yielded]
            yielded += len(page_scrobbles)
            yield page_scrobbles

        if max_scrobbles > 0 and yielded >= max_scrobbles:
            log.info(
                "iter_all_scrobbles: stopping at page %d - reached max_scrobbles cap (%d scrobbles fetched)",
                page,
                yielded,
            )
            break
        if total_pages and page >= total_pages:
            log.info(
                "iter_all_scrobbles: done - Last.fm reported no more history (%d scrobbles across %d pages)",
                yielded,
                page,
            )
            break

        page += 1


def fetch_recent_with_diversity(
    username: str,
    api_key: str,
    target_unique: int = 100,
    max_raw_limit: int = 1000,
    max_retries: int = 5,
    max_consecutive_empty: int = 3,
) -> list[Scrobble]:
    """Fetch scrobbles, expanding until target unique tracks or limits reached."""
    per_page = 200
    all_scrobbles: list[Scrobble] = []
    page = 1
    consecutive_empty_pages = 0

    def count_unique(scrobbles: list[Scrobble]) -> int:
        return len({(s.artist.lower(), s.track.lower()) for s in scrobbles})

    while len(all_scrobbles) < max_raw_limit and consecutive_empty_pages < max_consecutive_empty:
        params: dict[str, Any] = {
            "method": "user.getrecenttracks",
            "user": username,
            "api_key": api_key,
            "format": "json",
            "limit": per_page,
            "page": page,
        }

        data = _make_api_request(params, page, max_retries)
        if data is None:
            break

        recenttracks = data.get("recenttracks", {})
        tracks = recenttracks.get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]

        if not tracks:
            break

        page_scrobbles = _parse_tracks(tracks)
        all_scrobbles.extend(page_scrobbles)
        unique_count = count_unique(all_scrobbles)

        if unique_count >= target_unique:
            break

        attr = recenttracks.get("@attr", {})
        total_pages = int(attr.get("totalPages", "0") or "0")

        if total_pages > 0 and page >= total_pages:
            break

        if page > 1 and page_scrobbles:
            prev_unique = count_unique(all_scrobbles[: -len(page_scrobbles)])
            if unique_count == prev_unique:
                consecutive_empty_pages += 1
            else:
                consecutive_empty_pages = 0

        page += 1

    return all_scrobbles


def _parse_tags(raw_tags: Any, min_count: int, source: str = "track") -> list[dict[str, Any]]:
    """Parse raw Last.fm tag response into filtered tag list."""
    if isinstance(raw_tags, dict):
        raw_tags = [raw_tags]
    if not isinstance(raw_tags, list):
        return []

    tags: list[dict[str, Any]] = []
    for tag in raw_tags:
        name = tag.get("name", "").strip()
        try:
            count = int(tag.get("count", 0))
        except (ValueError, TypeError):
            count = 0

        if name and count >= min_count:
            tags.append({"name": name.lower(), "count": count, "source": source})

    return tags


def fetch_track_tags(
    api_key: str,
    artist: str,
    track: str,
    min_count: int = 10,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Fetch top tags for a track from Last.fm, falling back to artist tags."""
    params: dict[str, Any] = {
        "method": "track.getTopTags",
        "artist": artist,
        "track": track,
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
    }

    data = _make_api_request(params, page=1, max_retries=max_retries)
    if data is not None and "error" not in data:
        raw_tags = data.get("toptags", {}).get("tag", [])
        tags = _parse_tags(raw_tags, min_count, source="track")
        if tags:
            return tags

    artist_params: dict[str, Any] = {
        "method": "artist.getTopTags",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
    }

    data = _make_api_request(artist_params, page=1, max_retries=max_retries)
    if data is None or "error" in data:
        log.debug("No tags found for %s - %s (track and artist)", artist, track)
        return []

    raw_tags = data.get("toptags", {}).get("tag", [])
    tags = _parse_tags(raw_tags, min_count, source="artist")

    if tags:
        log.debug("Using artist-level tags for %s - %s (%d tags)", artist, track, len(tags))

    return tags


def _coerce_match(value: Any) -> float:
    """Coerce a Last.fm ``match`` field (str/float) into a float, defaulting to 0.0."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def fetch_similar_tracks(
    api_key: str,
    artist: str,
    track: str,
    limit: int = 50,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Fetch tracks similar to a seed track via Last.fm ``track.getSimilar``.

    Returns a list of ``{"artist", "track", "match"}`` dicts sorted by descending
    match score. Used to build discovery playlists from songs the user has *not*
    scrobbled yet.
    """
    params: dict[str, Any] = {
        "method": "track.getSimilar",
        "artist": artist,
        "track": track,
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
        "limit": max(1, limit),
    }

    data = _make_api_request(params, page=1, max_retries=max_retries)
    if data is None or "error" in data:
        return []

    raw = data.get("similartracks", {}).get("track", [])
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    results: list[dict[str, Any]] = []
    for item in raw:
        name = (item.get("name") or "").strip()
        a = item.get("artist")
        sim_artist = (a.get("name") if isinstance(a, dict) else a) or ""
        sim_artist = sim_artist.strip()
        if sim_artist and name:
            results.append({"artist": sim_artist, "track": name, "match": _coerce_match(item.get("match"))})

    return results


def fetch_similar_artists(
    api_key: str,
    artist: str,
    limit: int = 30,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Fetch artists similar to a seed artist via Last.fm ``artist.getSimilar``.

    Returns a list of ``{"artist", "match"}`` dicts sorted by descending match score.
    """
    params: dict[str, Any] = {
        "method": "artist.getSimilar",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
        "limit": max(1, limit),
    }

    data = _make_api_request(params, page=1, max_retries=max_retries)
    if data is None or "error" in data:
        return []

    raw = data.get("similarartists", {}).get("artist", [])
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    results: list[dict[str, Any]] = []
    for item in raw:
        name = (item.get("name") or "").strip()
        if name:
            results.append({"artist": name, "match": _coerce_match(item.get("match"))})

    return results


def fetch_artist_top_tracks(
    api_key: str,
    artist: str,
    limit: int = 10,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    """Fetch an artist's most popular tracks via Last.fm ``artist.getTopTracks``.

    Returns a list of ``{"artist", "track"}`` dicts ordered by popularity.
    """
    params: dict[str, Any] = {
        "method": "artist.getTopTracks",
        "artist": artist,
        "api_key": api_key,
        "format": "json",
        "autocorrect": 1,
        "limit": max(1, limit),
    }

    data = _make_api_request(params, page=1, max_retries=max_retries)
    if data is None or "error" in data:
        return []

    raw = data.get("toptracks", {}).get("track", [])
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    results: list[dict[str, Any]] = []
    for item in raw:
        name = (item.get("name") or "").strip()
        a = item.get("artist")
        top_artist = (a.get("name") if isinstance(a, dict) else a) or ""
        top_artist = top_artist.strip()
        if top_artist and name:
            results.append({"artist": top_artist, "track": name})

    return results
