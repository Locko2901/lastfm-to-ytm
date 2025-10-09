import re
import unicodedata
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Set

# both unidecode and text_unidecode work, use whichever you prefer
try:
    from unidecode import unidecode as _unidecode
except ImportError:
    from text_unidecode import unidecode as _unidecode

RE_PARENS = re.compile(r"[()\[\]\{\}（）【】「」『』〈〉《》＜＞‹›⟨⟩].*?[()\[\]\{\}（）【】「」『』〈〉《》＜＞‹›⟨⟩]")
RE_NON_ALNUM = re.compile(r"[^a-z0-9]+")
RE_FEAT_CLAUSE = re.compile(r"\b(?:feat(?:\.|uring)?|ft\.?|with)\b.*$", flags=re.IGNORECASE)
RE_ARTIST_SPLIT = re.compile(
    r"\s*(?:,|&|x|×|\/|;|\band\b|\bwith\b|\bfeat(?:\.|uring)?\b|\bft\.?\b)\s*",
    flags=re.IGNORECASE,
)
RE_DASH = re.compile(r"\s*[-–—]\s*")

UPLOADER_NOISE = {
    "official", "vevo", "topic", "music", "records", "recordings", "recording",
    "channel", "tv", "label", "auto-generated", "auto", "generated", "wmg", "umg",
    "smg", "sony", "universal", "warner", "publishing", "inc", "ltd", "co", "entertainment"
}

NEGATIVE_TERMS = {
    "live", "acoustic", "cover", "karaoke", "instrumental", "remix", "edit", "nightcore",
    "sped", "slowed", "8d", "loop", "mashup", "mix", "medley", "tribute", "parody",
    "reverb", "pitch", "chipmunk", "fanmade", "speed", "rework", "bootleg",
    "daycore", "bassboosted", "bass", "boosted", "tiktok", "phonk", "version",
    "lyric", "lyrics", "visualizer", "teaser", "preview", "short", "radio", "demo"
}

HARD_NEGATIVE_TERMS = {
    "nightcore", "daycore", "sped", "slowed", "8d", "chipmunk", "reverb", "pitch", "bassboosted"
}

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
    return unicodedata.normalize("NFKC", s).casefold()


def _ascii_fold(s: str) -> str:
    return _unidecode(unicodedata.normalize("NFKC", s).casefold())


def _alnum_space(s: str) -> str:
    return "".join(ch if ch.isalnum() else " " for ch in s)


def _normalize_base(s: str) -> str:
    return _collapse_ws(_nfkc_casefold(s).replace("&", " and "))


def _tokens(s: str) -> Set[str]:
    if not s:
        return set()
    base = _normalize_base(s)
    t1 = set(filter(None, _alnum_space(base).split()))
    folded = _ascii_fold(base)
    if folded and folded != base:
        t2 = set(filter(None, _alnum_space(folded).split()))
        t1 |= t2
    return t1


def _strip_feat_clauses(s: str) -> str:
    return RE_FEAT_CLAUSE.sub("", s)


def _remove_bracketed(s: str) -> str:
    prev = None
    while s and prev != s:
        prev = s
        for pat in RE_BRACKETED:
            s = pat.sub(" ", s)
    return s


def _clean_title_for_match(title: str, artist_tokens: Set[str]) -> str:
    raw = title or ""
    s = _normalize_base(raw)

    parts = RE_DASH.split(s, maxsplit=1)
    if len(parts) == 2:
        left, right = parts
        left_tokens = _tokens(left)
        if _jaccard(left_tokens, artist_tokens) >= 0.5:
            s = right

    s = _remove_bracketed(s)
    s = _strip_feat_clauses(s)
    s = _collapse_ws(_alnum_space(s))

    if not s:
        s = _collapse_ws(_alnum_space(_ascii_fold(raw)))
    return s


def _split_artist_aliases(artist: str) -> List[str]:
    s = _normalize_base(_strip_feat_clauses(artist or ""))
    s = _remove_bracketed(s)
    parts = [p for p in RE_ARTIST_SPLIT.split(s) if p]
    if len(parts) <= 1 and RE_DASH.search(s):
        dparts = [p.strip() for p in RE_DASH.split(s) if p and p.strip()]
        if 1 < len(dparts) <= 4:
            parts.extend(dparts)
    out: List[str] = []
    seen: Set[str] = set()
    for p in parts + [s]:
        p = p.strip()
        if not p:
            continue
        key = _match_key(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out or [s]


def _match_key(s: str) -> str:
    return _collapse_ws(_alnum_space(_ascii_fold(s or "")))


def _best_similarity(a: str, b: str) -> float:
    a_tokens, b_tokens = _tokens(a), _tokens(b)
    j = _jaccard(a_tokens, b_tokens)
    r = SequenceMatcher(None, _match_key(a), _match_key(b)).ratio()
    return 0.7 * j + 0.3 * r


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _clean_uploader_name(author: str) -> str:
    s = _normalize_base(author or "")
    s = re.sub(r"[-–—]\s*topic\b", " ", s)
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
    undesired = (cand_tokens & NEGATIVE_TERMS) - user_tokens
    hard_hits = (cand_tokens & HARD_NEGATIVE_TERMS) - user_tokens
    if not undesired:
        return 0.0
    light = len(undesired - hard_hits)
    hard = len(hard_hits)
    light_penalty = min(0.25, 0.08 * light)
    hard_penalty = min(0.60, 0.35 * hard)
    return light_penalty + hard_penalty


def _video_mismatch_penalty(r: Dict) -> float:
    rt = (r.get("resultType") or "").lower()
    if rt != "video":
        return 0.0
    s = _normalize_base(r.get("title") or "")
    parts = RE_DASH.split(s, maxsplit=1)
    if len(parts) != 2:
        return 0.0
    left = parts[0]
    left_tokens = _tokens(left)
    cand_artist_tokens: Set[str] = set()
    for name in _candidate_artists(r):
        cand_artist_tokens |= _tokens(name)
    if not left_tokens or not cand_artist_tokens:
        return 0.0
    j = _jaccard(left_tokens, cand_artist_tokens)
    return 0.10 if j < 0.3 else 0.0


def _style_mismatch_penalty(user_title: str, candidate_title: str, result_type: str) -> float:
    """
    If the user title explicitly includes a hard style token (sped, slowed, nightcore, 8d, daycore, chipmunk, bassboosted)
    but the candidate title doesn't, apply a small penalty so the correct style is preferred.
    Still keep it soft enough to allow fallback to the normal version if no styled version exists.
    """
    user_styles = _tokens(user_title) & HARD_NEGATIVE_TERMS
    if not user_styles:
        return 0.0
    cand_styles = _tokens(candidate_title) & HARD_NEGATIVE_TERMS
    if user_styles.issubset(cand_styles):
        return 0.0
    return 0.18 if (result_type or "").lower() == "video" else 0.12


def _coverage(sub: Set[str], sup: Set[str]) -> float:
    if not sub:
        return 0.0
    return len(sub & sup) / len(sub)


def _artist_title_presence_bonus(artist: str, title: str, candidate_title: str) -> float:
    cand_tokens = _tokens(candidate_title)
    if not cand_tokens:
        return 0.0

    aliases = _split_artist_aliases(artist)
    alias_token_sets = [_tokens(a) for a in aliases if a]
    artist_cov = 0.0
    for ats in alias_token_sets:
        artist_cov = max(artist_cov, _coverage(ats, cand_tokens))

    artist_union = set().union(*alias_token_sets) if alias_token_sets else _tokens(artist)
    core_title = _clean_title_for_match(title, artist_union)
    title_tokens = _tokens(core_title)
    title_cov = _coverage(title_tokens, cand_tokens)

    both = min(artist_cov, title_cov)
    if both <= 0.2:
        return 0.0
    return min(0.07, 0.10 * both + 0.02 if both >= 0.5 else 0.04 * both)


def _build_queries(artist: str, title: str, album: Optional[str]) -> List[str]:
    """
    Build a set of search queries that try:
      - alias + core_title (brackets/features stripped)
      - alias + bracketless title
      - ascii-folded variants
      - quoted pairs
      - album-assisted variants
      - title-only quoted fallback (when artist info is messy)
    """
    aliases = _split_artist_aliases(artist)
    alias_union = set().union(*(_tokens(a) for a in aliases)) if aliases else _tokens(artist)
    core_title = _clean_title_for_match(title, alias_union)
    bracketless_title = _remove_bracketed(title or "").strip()
    bracketless_core = _clean_title_for_match(bracketless_title, alias_union)
    title_variants: List[str] = []
    seen_tv: Set[str] = set()
    for t in [core_title, bracketless_title, bracketless_core]:
        t = _collapse_ws(t)
        if t and t not in seen_tv:
            seen_tv.add(t)
            title_variants.append(t)
    folded_core = _collapse_ws(_ascii_fold(core_title))
    if folded_core and folded_core not in seen_tv:
        seen_tv.add(folded_core)
        title_variants.append(folded_core)
    queries: List[str] = []
    seen_q: Set[str] = set()
    use_aliases = aliases or [artist]

    for alias in use_aliases:
        alias = _collapse_ws(alias)
        if not alias:
            continue
        for t in title_variants:
            for pat in (f"{alias} - {t}", f"\"{t}\" \"{alias}\"", f"{t} {alias}"):
                if pat not in seen_q:
                    seen_q.add(pat)
                    queries.append(pat)
            if album:
                pat = f"{alias} - {t} {album}"
                if pat not in seen_q:
                    seen_q.add(pat)
                    queries.append(pat)
    if core_title and f"\"{core_title}\"" not in seen_q:
        queries.append(f"\"{core_title}\"")

    return queries


def _score_candidate(r: Dict, artist: str, title: str, album: Optional[str]) -> float:
    rt = (r.get("resultType") or "").lower()
    if rt not in ("song", "video", ""):
        return 0.0

    candidate_title = r.get("title") or ""
    author_cf = (r.get("author") or "").casefold()
    hard_hits = _hard_negative_hits(candidate_title, title)
    if hard_hits and rt == "video" and "topic" not in author_cf:
        return 0.0

    artist_tokens = _tokens(artist)
    title_score = _title_similarity(title, r, artist_tokens)
    artist_score = _artist_similarity(artist, r)
    uploader_score = _uploader_similarity(artist, r)
    album_name = _album_name_from_result(r)
    album_score = _best_similarity(album, album_name) if (album and album_name) else 0.0

    score = (
        0.60 * title_score
        + 0.27 * artist_score
        + 0.08 * uploader_score
        + 0.05 * album_score
    )

    score += _artist_title_presence_bonus(artist, title, candidate_title)
    score -= _negative_penalty(candidate_title, title)
    score -= _style_mismatch_penalty(title, candidate_title, rt)
    score -= _video_mismatch_penalty(r)

    if rt == "song":
        score += 0.05
    elif rt == "video":
        score -= 0.01
    if "topic" in author_cf and uploader_score >= 0.6:
        score += 0.02  
    return max(0.0, min(1.0, score))


def find_on_ytm(ytm, artist: str, title: str, album: Optional[str] = None) -> Optional[str]:
    """
    Search YouTube Music and return a videoId if a high-confidence match is found.
    Prefers 'songs', then 'videos'; ranks by title/artist/album similarity and avoids common mismatches.
    """
    queries = _build_queries(artist, title, album)
    filters = ["songs", "videos", "uploads", None]

    best_vid: Optional[str] = None
    best_score = 0.0
    best_rt = ""
    seen: Set[str] = set()

    base_threshold = 0.66 if not album else 0.68
    video_extra = 0.05

    for q in queries:
        for flt in filters:
            try:
                results = ytm.search(q, filter=flt, limit=25)
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

    threshold = base_threshold + (video_extra if best_rt == "video" else 0.0)
    if best_score >= threshold:
        return best_vid
    if best_score >= (threshold - 0.06):
        return best_vid

    return None
