from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List

import requests


@dataclass(frozen=True)
class Scrobble:
    artist: str
    track: str
    album: str
    ts: int  # unix timestamp


def fetch_recent(username: str, api_key: str, limit: int = 100) -> List[Scrobble]:
    """
    Fetch recent scrobbles from Last.fm (skips 'now playing').
    """
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "user.getrecenttracks",
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": max(1, min(400, int(limit))),
    }
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    tracks = data.get("recenttracks", {}).get("track", [])
    if isinstance(tracks, dict):
        tracks = [tracks]

    out: List[Scrobble] = []
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
            out.append(Scrobble(artist=artist, track=track, album=album, ts=int(uts)))
    return out
