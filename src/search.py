#TODO: more score for artist + song in title

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Set

try:
    from unidecode import unidecode as _unidecode
except ImportError:
    from text_unidecode import unidecode as _unidecode

# Expanded brackets (ASCII and common full-width/JP/CN variants)
RE_PARENS = re.compile(r"[()\[\]\{\}（）【】「」『』〈〉《》＜＞‹›⟨⟩].*?[()\[\]\{\}（）【】「」『』〈〉《》＜＞‹›⟨⟩]")
# Keep legacy constant though we won't rely solely on it anymore
RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
RE_FEAT_CLAUSE = re.compile(r"\b(?:feat(?:\.|uring)?|ft\.?|with)\b.*$", flags=re.IGNORECASE)
# Split on common separators; also include × (times sign)
RE_ARTIST_SPLIT = re.compile(
    r"\s*(?:,|&|x|×|\/|;|\band\b|\bwith\b|\bfeat(?:\.|uring)?\b|\bft\.?\b)\s*",
    flags=re.IGNORECASE,
)
# Allow hyphen, en dash, em dash
RE_DASH = re.compile(r"\s*[-–—]\s*")

# Common noise in uploader/channel names that shouldn't count against artist similarity
UPLOADER_NOISE = {
    "official", "vevo", "topic", "music", "records", "recordings", "recording",
    "channel", "tv", "label", "auto-generated", "auto", "generated", "wmg", "umg",
    "smg", "sony", "universal", "warner", "publishing", "inc", "ltd", "co", "entertainment"
}

# Expanded negatives: light negatives remain here (penalize, but not outright reject)
NEGATIVE_TERMS = {
    "live", "acoustic", "cover", "karaoke", "instrumental", "remix", "edit", "nightcore",
    "sped", "slowed", "8d", "loop", "mashup", "mix", "medley", "tribute", "parody",
    "reverb", "pitch", "chipmunk", "fanmade", "speed", "rework", "bootleg",
    # additions
    "daycore", "bassboosted", "bass", "boosted", "tiktok", "phonk", "version"
}

# A subset of "hard negatives": strongly altered variants that should nearly always be avoided
HARD_NEGATIVE_TERMS = {
    "nightcore", "daycore", "sped", "slowed", "8d", "chipmunk", "reverb", "pitch", "bassboosted"
}

# Prefer balanced bracket removal by pair (prevents over-stripping across mismatched pairs)
BRACKET_PAIRS = [
    ("(", ")"), ("[", "]"), ("{", "}"),
    ("（", "）"), ("【", "】"), ("「", "」"),
    ("『", "』"), ("〈", "〉"), ("《", "》"),
    ("＜", "＞"), ("‹", "›"), ("⟨", "⟩"),
]
RE_BRACKETED = [
    re.compile(re.escape(l) + r"[^" + re.escape(r) + r"]*" + re.escape(r))
    for (l, r) in BRACKET_PAIRS
]


def _collapse_ws(s: str) -> str:
    return " ".join(s.split())


def _nfkc_casefold(s: str) -> str:
    # Robust Unicode normalization and case-folding
    return unicodedata.normalize("NFKC", s).casefold()


def _ascii_fold(s: str) -> str:
    # Transliterate using Unidecode
    return _unidecode(unicodedata.normalize("NFKC", s).casefold())


def _alnum_space(s: str) -> str:
    # Keep alphanumeric from all scripts; replace others with spaces
    return "".join(ch if ch.isalnum() else " " for ch in s)


def _normalize_base(s: str) -> str:
    # Replace & with 'and', normalize, and collapse whitespace
    s = _nfkc_casefold(s).replace("&", " and ")
    return _collapse_ws(s)


def _tokens(s: str) -> Set[str]:
    """
    Tokenize keeping non-Latin scripts, with additional ASCII-folded tokens
    for better cross-script matching when Unidecode is available.
    """
    if not s:
        return set()

    base = _normalize_base(s)
    # Primary tokens using full Unicode alnum
    t1 = set(filter(None, _alnum_space(base).split()))

    # Add ASCII-folded tokens to bridge diacritics and scripts
    folded = _ascii_fold(base)
    if folded and folded != base:
        t2 = set(filter(None, _alnum_space(folded).split()))
        t1 |= t2

    return t1


def _strip_feat_clauses(s: str) -> str:
    return RE_FEAT_CLAUSE.sub("", s)


def _remove_bracketed(s: str) -> str:
    """
    Remove bracketed segments using balanced pairs, iteratively until no change.
    This avoids deleting across mismatched bracket types.
    """
    prev = None
    while s and prev != s:
        prev = s
        for pat in RE_BRACKETED:
            s = pat.sub(" ", s)
    return s


def _clean_title_for_match(title: str, artist_tokens: Set[str]) -> str:
    """
    Extract a 'core' title for matching:
    - Remove bracketed parts and feat/ft clauses
    - If "Artist - Title" and left matches artist tokens, keep only right
    - Normalize, keep Unicode letters/digits, collapse whitespace
    """
    raw = title or ""
    s = _normalize_base(raw)

    # Handle "Artist - Title" using -, – or —
    parts = RE_DASH.split(s, maxsplit=1)
    if len(parts) == 2:
        left, right = parts
        left_tokens = _tokens(left)
        # Require decent overlap with the passed-in artist tokens
        if _jaccard(left_tokens, artist_tokens) >= 0.5:
            s = right

    # Remove bracketed segments using balanced pairs
    s = _remove_bracketed(s)
    # Strip feat./ft./with clauses
    s = _strip_feat_clauses(s)

    # Reduce to alphanumeric + spaces (Unicode-aware) and collapse
    s = _collapse_ws(_alnum_space(s))

    # Fallback: if we stripped everything, try with ASCII-folded normalized raw
    if not s:
        s = _collapse_ws(_alnum_space(_ascii_fold(raw)))

    return s


def _split_artist_aliases(artist: str) -> List[str]:
    s = _normalize_base(_strip_feat_clauses(artist or ""))
    parts = [p for p in RE_ARTIST_SPLIT.split(s) if p]
    return parts or [s]


def _match_key(s: str) -> str:
    # A key for SequenceMatcher: normalized + ASCII-folded + alnum-only
    return _collapse_ws(_alnum_space(_ascii_fold(s or "")))


def _best_similarity(a: str, b: str) -> float:
    a_tokens, b_tokens = _tokens(a), _tokens(b)
    j = _jaccard(a_tokens, b_tokens)
    r = SequenceMatcher(None, _match_key(a), _match_key(b)).ratio()
    return 0.7 * j + 0.3 * r


def _jaccard(a: Set[str], b: Set[str]) -> float:
    # Fix: both-empty sets should not be treated as a perfect match
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _clean_uploader_name(author: str) -> str:
    """
    Clean uploader/channel names: remove common noise and normalize.
    """
    s = _normalize_base(author or "")
    # Remove ' - topic' with any dash variant
    s = re.sub(r"[-–—]\s*topic\b", " ", s)
    # Remove some common suffix words
    toks = [t for t in _tokens(s) if t not in UPLOADER_NOISE]
    return " ".join(toks)


def _candidate_artists(r: Dict) -> List[str]:
    names: List[str] = []
    for a in (r.get("artists") or []):
        name = a.get("name")
        if name:
            names.append(name)

    author = r.get("author")
    if author:
        # Include a cleaned uploader name as an additional candidate artist string
        cleaned = _clean_uploader_name(author)
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


def _uploader_similarity(target_artist: str, r: Dict) -> float:
    """
    Explicit similarity between artist and uploader/channel (cleaned).
    """
    author = r.get("author") or ""
    if not author:
        return 0.0
    uploader = _clean_uploader_name(author)
    best = 0.0
    for alias in _split_artist_aliases(target_artist):
        best = max(best, _best_similarity(alias, uploader))
    return best


def _title_similarity(target_title: str, r: Dict, artist_tokens: Set[str]) -> float:
    candidate_title = r.get("title") or ""
    core_target = _clean_title_for_match(target_title, artist_tokens)
    core_candidate = _clean_title_for_match(candidate_title, artist_tokens)
    j = _jaccard(_tokens(core_target), _tokens(core_candidate))
    rratio = SequenceMatcher(None, _match_key(core_target), _match_key(core_candidate)).ratio()
    return 0.7 * j + 0.3 * rratio


def _album_name_from_result(r: Dict) -> Optional[str]:
    album = r.get("album")
    if isinstance(album, dict):
        return album.get("name")
    if isinstance(album, str):
        return album
    return None


def _hard_negative_hits(candidate_title: str, user_title: str) -> Set[str]:
    cand_tokens = _tokens(candidate_title)
    user_tokens = _tokens(user_title)
    return (cand_tokens & HARD_NEGATIVE_TERMS) - user_tokens


def _negative_penalty(candidate_title: str, user_title: str) -> float:
    cand_tokens = _tokens(candidate_title)
    user_tokens = _tokens(user_title)

    # Terms present in candidate but not explicitly in the user's title
    undesired = (cand_tokens & NEGATIVE_TERMS) - user_tokens
    hard_hits = (cand_tokens & HARD_NEGATIVE_TERMS) - user_tokens

    if not undesired:
        return 0.0

    # Two-tier penalty: light for general negatives, heavy for "hard" negatives
    light = len(undesired - hard_hits)
    hard = len(hard_hits)

    # Keep caps to avoid runaway penalties while making them meaningful
    light_penalty = min(0.25, 0.08 * light)
    hard_penalty = min(0.60, 0.35 * hard)

    return light_penalty + hard_penalty


def _video_mismatch_penalty(r: Dict) -> float:
    """
    Penalize 'Artist - Title' style video uploads when the left side doesn't
    look like any of the candidate's recognized artists/uploader.
    """
    rt = (r.get("resultType") or "").lower()
    if rt != "video":
        return 0.0

    s = _normalize_base(r.get("title") or "")
    parts = RE_DASH.split(s, maxsplit=1)
    if len(parts) != 2:
        return 0.0

    left = parts[0]
    left_tokens = _tokens(left)
    # Collect tokens from all candidate artists and uploader
    cand_artist_tokens: Set[str] = set()
    for name in _candidate_artists(r):
        cand_artist_tokens |= _tokens(name)

    if not left_tokens or not cand_artist_tokens:
        return 0.0

    j = _jaccard(left_tokens, cand_artist_tokens)
    # If the 'Artist' in the video title doesn't overlap with the structured artists/uploader,
    # it's likely an arbitrary reupload. Penalize a bit.
    return 0.10 if j < 0.3 else 0.0


def _score_candidate(r: Dict, artist: str, title: str, album: Optional[str]) -> float:
    rt = (r.get("resultType") or "").lower()
    if rt not in ("song", "video", ""):
        return 0.0

    candidate_title = r.get("title") or ""
    author_cf = (r.get("author") or "").casefold()

    # Early hard-exclusion: altered videos (unless explicitly requested by user)
    hard_hits = _hard_negative_hits(candidate_title, title)
    if hard_hits and rt == "video" and "topic" not in author_cf:
        return 0.0

    artist_tokens = _tokens(artist)
    title_score = _title_similarity(title, r, artist_tokens)
    artist_score = _artist_similarity(artist, r)
    uploader_score = _uploader_similarity(artist, r)
    album_name = _album_name_from_result(r)
    album_score = _best_similarity(album, album_name) if (album and album_name) else 0.0

    # Rebalanced weights and stronger preference for 'song' results
    score = (
        0.60 * title_score
        + 0.27 * artist_score
        + 0.08 * uploader_score
        + 0.05 * album_score
    )

    # Penalties
    score -= _negative_penalty(candidate_title, title)
    score -= _video_mismatch_penalty(r)

    if rt == "song":
        score += 0.05  # Stronger preference for 'song' results
    elif rt == "video":
        # Slight downweight to 'video' (they're noisier)
        score -= 0.01

    # Small bonus for Artist - Topic when uploader matches artist
    if "topic" in author_cf and uploader_score >= 0.6:
        score += 0.01

    # Clamp
    return max(0.0, min(1.0, score))


def find_on_ytm(ytm, artist: str, title: str, album: Optional[str] = None) -> Optional[str]:
    """
    Search YouTube Music and return a videoId (11 chars) if a high-confidence match is found.
    Prefers 'songs', then 'videos', then mixed; ranks candidates by title/artist/album similarity,
    and avoids common mismatches (live, cover, karaoke, slowed/sped, etc.).
    """
    base_queries = [
        f"{artist} - {title}",
        f"{title} {artist}",
        f"\"{title}\" \"{artist}\"",
    ]
    if album:
        base_queries.append(f"{artist} - {title} {album}")

    # Add per-alias queries (helps with multi-artist credits and collabs)
    alias_queries = []
    for alias in _split_artist_aliases(artist):
        if alias and alias != artist:
            alias_queries.extend([
                f"{alias} - {title}",
                f"{title} {alias}",
                f"\"{title}\" \"{alias}\"",
            ])

    # Deduplicate while preserving order
    seen_q = set()
    queries: List[str] = []
    for q in base_queries + alias_queries:
        if q not in seen_q:
            seen_q.add(q)
            queries.append(q)

    filters = ["songs", "videos", None]

    best_vid: Optional[str] = None
    best_score = 0.0
    best_rt = ""
    seen: Set[str] = set()

    # Slightly higher threshold when album is provided; even higher for videos
    base_threshold = 0.66 if not album else 0.68
    video_extra = 0.05  # raise bar for 'video' matches

    for q in queries:
        for flt in filters:
            try:
                # Higher limit to reduce misses
                results = ytm.search(q, filter=flt, limit=20)
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
                    best_rt = rt

    if not best_vid:
        return None

    # Type-aware acceptance threshold
    threshold = base_threshold + (video_extra if best_rt == "video" else 0.0)
    if best_score >= threshold:
        return best_vid

    # Soft fallback if we got close
    if best_score >= (threshold - 0.06):
        return best_vid

    return None
