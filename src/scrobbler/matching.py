"""Artist and title matching between detected plays and existing scrobbles.

Builds on the search normalisation helpers (``src/search``). Two plays are the
same track when an artist overlaps and the core titles are equal; the album is
ignored. Remaster, edit and "official video" qualifiers are dropped, while
version qualifiers such as "live" or "remix" must agree, so a live recording
is never taken for the studio one.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

from ..search.normalization import (
    RE_ARTIST_SPLIT,
    RE_BRACKETED,
    RE_DASH,
    RE_TOPIC_SUFFIX,
    match_key,
    normalize_base,
    remove_bracketed,
    strip_feat_clauses,
    tokens,
)
from ..search.queries import clean_title_for_match
from ..search.scoring import HARD_NEGATIVE_TERMS

VERSION_TERMS = HARD_NEGATIVE_TERMS | frozenset(
    {
        "live",
        "remix",
        "acoustic",
        "instrumental",
        "demo",
        "karaoke",
        "cover",
        "unplugged",
        "acapella",
        "cappella",
        "mashup",
        "medley",
        "rework",
        "bootleg",
    }
)

DECORATION_TERMS = frozenset(
    {
        "remaster",
        "remastered",
        "version",
        "edit",
        "mono",
        "stereo",
        "single",
        "album",
        "deluxe",
        "bonus",
        "track",
        "explicit",
        "clean",
        "radio",
        "official",
        "video",
        "audio",
        "music",
        "lyric",
        "lyrics",
        "visualizer",
        "visualiser",
        "hd",
        "hq",
        "4k",
        "mv",
        "original",
        "anniversary",
        "edition",
        "expanded",
        "digital",
    }
)

MATCH = "match"
VERSION_DIFFERS = "version_differs"
TITLE_DIFFERS = "title_differs"
ARTIST_DIFFERS = "artist_differs"

RE_LEADING_THE = re.compile(r"^the\s+")


@dataclass(frozen=True, slots=True)
class TrackKey:
    """Normalised identity of a track for duplicate checks."""

    artists: frozenset[str]
    title: str
    versions: frozenset[str]


def _compact(key: str) -> str:
    """Drop spaces so "don t" and "dont" compare equal."""
    return key.replace(" ", "")


def artist_keys(names: str | Sequence[str]) -> frozenset[str]:
    """Return every individual artist of ``names`` plus the full credit, normalised."""
    raw = [names] if isinstance(names, str) else list(names)
    keys: set[str] = set()
    for name in raw:
        base = remove_bracketed(normalize_base(RE_TOPIC_SUFFIX.sub("", name or "")))
        for part in [base, *RE_ARTIST_SPLIT.split(base)]:
            key = _compact(RE_LEADING_THE.sub("", match_key(part)))
            if key:
                keys.add(key)
    return frozenset(keys)


def _is_qualifier(text: str) -> bool:
    """True when a dash suffix like "Remastered 2011" or "Live at Wembley" qualifies the title."""
    return bool(tokens(text) & (VERSION_TERMS | DECORATION_TERMS))


def split_title(title: str) -> tuple[str, str]:
    """Split ``title`` into its core and its qualifier text (brackets and qualifying dash suffixes)."""
    s = normalize_base(title or "")
    qualifiers = [m.group(0) for pattern in RE_BRACKETED for m in pattern.finditer(s)]
    core = remove_bracketed(s)
    parts = RE_DASH.split(core)
    while len(parts) > 1 and _is_qualifier(parts[-1]):
        qualifiers.append(parts.pop())
    return " - ".join(p.strip() for p in parts), " ".join(qualifiers)


def track_key(artists: str | Sequence[str], title: str) -> TrackKey:
    """Build the comparison key for one play or scrobble."""
    return _track_key((artists,) if isinstance(artists, str) else tuple(artists), title)


@lru_cache(maxsize=4096)
def _track_key(artists: tuple[str, ...], title: str) -> TrackKey:
    """Cached body of ``track_key``: a poll compares the same scrobbles against several plays."""
    akeys = artist_keys(artists)
    artist_tokens: set[str] = set()
    for name in artists:
        artist_tokens |= tokens(strip_feat_clauses(name or ""))
    core, qualifiers = split_title(title)
    cleaned = match_key(clean_title_for_match(core, artist_tokens)) or match_key(title)
    return TrackKey(artists=akeys, title=_compact(cleaned), versions=frozenset(tokens(qualifiers) & VERSION_TERMS))


def compare(a: TrackKey, b: TrackKey) -> str:
    """Compare two keys: ``match``, or why they differ (title first, then artist, then version)."""
    if not a.title or a.title != b.title:
        return TITLE_DIFFERS
    if not a.artists & b.artists:
        return ARTIST_DIFFERS
    if a.versions != b.versions:
        return VERSION_DIFFERS
    return MATCH


def strip_video_noise(text: str) -> str:
    """Drop "(Official Video)", "[Lyrics]", "(4K)"-style brackets from a title."""
    cleaned = text
    for pattern in RE_BRACKETED:
        for found in pattern.findall(cleaned):
            words = tokens(found)
            if words and words <= DECORATION_TERMS | {"4k", "1080p", "720p"}:
                cleaned = cleaned.replace(found, " ")
    return " ".join(cleaned.split())


def clean_video_title(title: str, artist: str) -> str:
    """Tidy a music-video title for scrobbling: drop an "Artist - " prefix and "(Official Video)"-style brackets."""
    text = (title or "").strip()
    parts = RE_DASH.split(text, maxsplit=1)
    if len(parts) == 2 and artist_keys(parts[0]) & artist_keys(artist):
        text = parts[1].strip()
    return strip_video_noise(text) or (title or "").strip()


def split_artist_title(title: str) -> tuple[str, str] | None:
    """Read ``(artist, title)`` from an "Artist - Title" video title, or None when it has no such form."""
    parts = RE_DASH.split((title or "").strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    artist, rest = parts[0].strip(), strip_video_noise(parts[1].strip())
    if not artist or not rest:
        return None
    return artist, rest
