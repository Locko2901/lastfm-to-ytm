from dataclasses import dataclass


@dataclass(frozen=True)
class Scrobble:
    artist: str
    track: str
    album: str
    ts: int
