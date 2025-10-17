from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass(frozen=True)
class Scrobble:
    artist: str
    track: str
    album: str
    ts: int  # unix timestamp


def fetch_recent(username: str, api_key: str, limit: int = 100, from_timestamp: Optional[int] = None, to_timestamp: Optional[int] = None) -> List[Scrobble]:
    """Fetch recent scrobbles from Last.fm (skips 'now playing')."""
    url = "https://ws.audioscrobbler.com/2.0/"
    
    per_page = min(200, limit)
    all_scrobbles: List[Scrobble] = []
    page = 1
    
    while len(all_scrobbles) < limit:
        remaining = limit - len(all_scrobbles)
        current_limit = min(per_page, remaining)
        
        params = {
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
        
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        
        tracks = data.get("recenttracks", {}).get("track", [])
        if isinstance(tracks, dict):
            tracks = [tracks]
        
        if not tracks:
            break
            
        page_scrobbles: List[Scrobble] = []
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
                page_scrobbles.append(Scrobble(artist=artist, track=track, album=album, ts=int(uts)))
        
        all_scrobbles.extend(page_scrobbles)
        
        if len(tracks) < current_limit:
            break
            
        page += 1
    
    return all_scrobbles


def fetch_recent_with_diversity(username: str, api_key: str, target_unique: int = 100, max_raw_limit: int = 1000, max_days_back: int = 60) -> List[Scrobble]:
    """Fetch recent scrobbles with smart expansion to get more unique tracks."""
    raw_limit = min(target_unique + 50, 200)
    scrobbles = fetch_recent(username, api_key, raw_limit)
    
    unique_tracks = set()
    for s in scrobbles:
        unique_tracks.add((s.artist.lower(), s.track.lower()))
    
    unique_count = len(unique_tracks)
    
    if unique_count >= target_unique or len(scrobbles) < raw_limit:
        return scrobbles
    
    duplication_ratio = len(scrobbles) / unique_count if unique_count > 0 else 1
    needed_unique = target_unique - unique_count
    estimated_raw_needed = int(needed_unique * duplication_ratio * 1.2)
    new_raw_limit = min(len(scrobbles) + estimated_raw_needed, max_raw_limit)
    
    scrobbles = fetch_recent(username, api_key, new_raw_limit)
    
    unique_tracks = set()
    for s in scrobbles:
        unique_tracks.add((s.artist.lower(), s.track.lower()))
    unique_count = len(unique_tracks)
    
    if unique_count < target_unique and len(scrobbles) >= new_raw_limit:
        current_time = int(time.time())
        days_back = 14
        
        while unique_count < target_unique and days_back <= max_days_back:
            from_timestamp = current_time - (days_back * 24 * 60 * 60)
            extended_scrobbles = fetch_recent(username, api_key, new_raw_limit, from_timestamp=from_timestamp)
            
            if len(extended_scrobbles) <= len(scrobbles):
                break
            
            scrobbles = extended_scrobbles
            
            unique_tracks = set()
            for s in scrobbles:
                unique_tracks.add((s.artist.lower(), s.track.lower()))
            unique_count = len(unique_tracks)
            
            if unique_count >= target_unique:
                break
                
            days_back += 14
    
    return scrobbles


def fetch_recent_extended(username: str, api_key: str, limit: int = 100, max_days_back: int = 30) -> List[Scrobble]:
    """DEPRECATED: Use fetch_recent_with_diversity instead."""
    return fetch_recent_with_diversity(username, api_key, limit, limit * 4, max_days_back)
