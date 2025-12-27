from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Scrobble:
    """A single Last.fm scrobble entry."""

    artist: str
    track: str
    album: str
    ts: int
