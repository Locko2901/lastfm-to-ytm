import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Set

RE_PARENS = re.compile(r"[\(\[\{].*?[\)\]\}]")
RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
RE_FEAT_CLAUSE = re.compile(r"\b(?:feat(?:\.|uring)?|ft\.?|with)\b.*$", flags=re.IGNORECASE)
RE_ARTIST_SPLIT = re.compile(r"\s*(?:,|&|x|\/|;| and | with | feat(?:\.|uring)? | ft\.? )\s*", flags=re.IGNORECASE)
RE_DASH = re.compile(r"\s+-\s+")

NEGATIVE_TERMS = {
    "live", "acoustic", "cover", "karaoke", "instrumental", "remix", "edit", "nightcore",
    "sped", "slowed", "8d", "loop", "mashup", "mix", "medley", "tribute", "parody",
    "reverb", "pitch", "chipmunk", "fanmade", "speed", "rework", "bootleg"
}


def _to_ascii_lower(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s.lower()


def _collapse_ws(s: str) -> str:
    return " ".join(s.split())


def _normalize_base(s: str) -> str:
    s = _to_ascii_lower(s).replace("&", " and ")
    return _collapse_ws(s)


def _tokens(s: str) -> Set[str]:
    s = _normalize_base(s)
    s = RE_NON_ALNUM.sub(" ", s).strip()
    return set(s.split()) if s else set()


def _strip_feat_clauses(s: str) -> str:
    return RE_FEAT_CLAUSE.sub("", s)


def _clean_title_for_match(title: str, artist_tokens: Set[str]) -> str:
    """
    Extract a 'core' title for matching:
    - Remove bracketed parts and feat/ft clauses
    - If "Artist - Title" and left matches artist tokens, keep only right
    - Remove non-alnum and normalize whitespace
    """
    raw = title
    s = _normalize_base(title)

    if " - " in s:
        parts = RE_DASH.split(s, maxsplit=1)
        if len(parts) == 2:
            left, right = parts
            left_tokens = _tokens(left)
            if _jaccard(left_tokens, artist_tokens) >= 0.5:
                s = right

    s = RE_PARENS.sub(" ", s)
    s = _strip_feat_clauses(s)

    s = RE_NON_ALNUM.sub(" ", s)
    s = _collapse_ws(s)

    if not s:
        s = RE_NON_ALNUM.sub(" ", _normalize_base(raw)).strip()
    return s


def _split_artist_aliases(artist: str) -> List[str]:
    s = _normalize_base(_strip_feat_clauses(artist))
    parts = [p for p in RE_ARTIST_SPLIT.split(s) if p]
    return parts or [s]


def _best_similarity(a: str, b: str) -> float:
    a_norm, b_norm = _normalize_base(a), _normalize_base(b)
    j = _jaccard(_tokens(a_norm), _tokens(b_norm))
    r = SequenceMatcher(None, a_norm, b_norm).ratio()
    return 0.7 * j + 0.3 * r


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _candidate_artists(r: Dict) -> List[str]:
    names: List[str] = []
    for a in (r.get("artists") or []):
        name = a.get("name")
        if name:
            names.append(name)

    author = r.get("author")
    if author:
        cleaned = _normalize_base(author)
        cleaned = cleaned.replace(" - topic", " ").replace(" topic", " ")
        cleaned = cleaned.replace(" vevo", " ").replace(" official", " ")
        cleaned = _collapse_ws(cleaned)
        if cleaned:
            names.append(cleaned)

    return names


def _artist_similarity(target_artist: str, r: Dict) -> float:
    aliases = _split_artist_aliases(target_artist)
    cands = _candidate_artists(r)
    best = 0.0
    for cand in cands:
        for alias in aliases:
            best = max(best, _best_similarity(alias, cand))
    return best


def _title_similarity(target_title: str, r: Dict, artist_tokens: Set[str]) -> float:
    candidate_title = r.get("title") or ""
    core_target = _clean_title_for_match(target_title, artist_tokens)
    core_candidate = _clean_title_for_match(candidate_title, artist_tokens)
    j = _jaccard(_tokens(core_target), _tokens(core_candidate))
    rratio = SequenceMatcher(None, core_target, core_candidate).ratio()
    return 0.7 * j + 0.3 * rratio


def _album_name_from_result(r: Dict) -> Optional[str]:
    album = r.get("album")
    if isinstance(album, dict):
        return album.get("name")
    if isinstance(album, str):
        return album
    return None


def _negative_penalty(candidate_title: str, user_title: str) -> float:
    cand_tokens = _tokens(candidate_title)
    user_tokens = _tokens(user_title)
    undesired = (cand_tokens & NEGATIVE_TERMS) - user_tokens
    if not undesired:
        return 0.0
    return min(0.25, 0.10 * len(undesired))


def _score_candidate(r: Dict, artist: str, title: str, album: Optional[str]) -> float:
    rt = (r.get("resultType") or "").lower()
    if rt not in ("song", "video", ""):
        return 0.0

    artist_tokens = _tokens(artist)
    title_score = _title_similarity(title, r, artist_tokens)
    artist_score = _artist_similarity(artist, r)
    album_name = _album_name_from_result(r)
    album_score = _best_similarity(album, album_name) if (album and album_name) else 0.0

    score = 0.60 * title_score + 0.35 * artist_score + 0.05 * album_score

    score -= _negative_penalty(r.get("title") or "", title)

    if rt == "song":
        score += 0.03

    author = (r.get("author") or "").lower()
    if "topic" in author and artist_score >= 0.6:
        score += 0.02

    return max(0.0, min(1.0, score))


def find_on_ytm(ytm, artist: str, title: str, album: Optional[str] = None) -> Optional[str]:
    """
    Search YouTube Music and return a videoId (11 chars) if a high-confidence match is found.
    Prefers 'songs', then 'videos', then mixed; ranks candidates by title/artist/album similarity
    and avoids common mismatches (live, cover, karaoke, slowed/sped, etc.).
    """
    queries = [
        f"{artist} - {title}",
        f"{title} {artist}",
    ]
    if album:
        queries.append(f"{artist} - {title} {album}")

    filters = ["songs", "videos", None]

    best_vid: Optional[str] = None
    best_score = 0.0
    seen: Set[str] = set()

    base_threshold = 0.66 if not album else 0.68

    for q in queries:
        for flt in filters:
            try:
                results = ytm.search(q, filter=flt, limit=12)
            except Exception:
                results = []

            if not results:
                continue

            for r in results:
                rt = (r.get("resultType") or "").lower()
                if rt not in ("song", "video", ""):
                    continue

                vid = r.get("videoId")
                if not (isinstance(vid, str) and len(vid) == 11):
                    continue
                if vid in seen:
                    continue
                seen.add(vid)

                score = _score_candidate(r, artist, title, album)
                if score > best_score:
                    best_score = score
                    best_vid = vid

    if best_vid and best_score >= base_threshold:
        return best_vid

    if best_vid and best_score >= (base_threshold - 0.06):
        return best_vid

    return None
