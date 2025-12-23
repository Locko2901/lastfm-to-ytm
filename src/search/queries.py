from .normalization import (
    RE_ARTIST_SPLIT,
    RE_DASH,
    alnum_space,
    ascii_fold,
    clean_uploader_name,
    collapse_ws,
    match_key,
    normalize_base,
    remove_bracketed,
    strip_feat_clauses,
    tokens,
)
from .similarity import jaccard


def split_artist_aliases(artist: str) -> list[str]:
    """Split artist string into potential aliases."""
    s = normalize_base(strip_feat_clauses(artist or ""))
    s = remove_bracketed(s)
    parts = [p for p in RE_ARTIST_SPLIT.split(s) if p]
    if len(parts) <= 1 and RE_DASH.search(s):
        dparts = [p.strip() for p in RE_DASH.split(s) if p and p.strip()]
        if 1 < len(dparts) <= 4:
            parts.extend(dparts)
    out: list[str] = []
    seen: set[str] = set()
    for part in [*parts, s]:
        stripped = part.strip()
        if not stripped:
            continue
        key = match_key(stripped)
        if key in seen:
            continue
        seen.add(key)
        out.append(stripped)
    return out or [s]


def clean_title_for_match(title: str, artist_tokens: set[str]) -> str:
    """Clean and normalize title for matching."""
    raw = title or ""
    s = normalize_base(raw)

    parts = RE_DASH.split(s, maxsplit=1)
    if len(parts) == 2:
        left, right = parts
        left_tokens = tokens(left)
        if jaccard(left_tokens, artist_tokens) >= 0.5:
            s = right

    s = remove_bracketed(s)
    s = strip_feat_clauses(s)
    s = collapse_ws(alnum_space(s))

    if not s:
        s = collapse_ws(alnum_space(ascii_fold(raw)))
    return s


def candidate_artists(r: dict) -> list[str]:
    """Extract artist names from search result."""
    names: list[str] = []
    for a in r.get("artists") or []:
        name = a.get("name")
        if name:
            names.append(name)
    author = r.get("author")
    if author:
        cleaned = clean_uploader_name(author)
        if cleaned:
            names.append(cleaned)
    return names


def build_queries(artist: str, title: str, album: str | None, *, already_tried: set[str] | None = None) -> list[str]:
    """Build search queries with various artist/title combinations and fallbacks."""
    aliases = split_artist_aliases(artist)
    alias_union = set().union(*(_t for a in aliases for _t in tokens(a))) if aliases else tokens(artist)

    core_title = clean_title_for_match(title, alias_union)
    original_normalized = collapse_ws(normalize_base(title))
    bracketless_title = remove_bracketed(title or "").strip()
    bracketless_core = clean_title_for_match(bracketless_title, alias_union)

    title_variants: list[str] = []
    seen_tv: set[str] = set()

    for title_candidate in [original_normalized, core_title, bracketless_title, bracketless_core]:
        collapsed = collapse_ws(title_candidate)
        if collapsed and collapsed not in seen_tv:
            seen_tv.add(collapsed)
            title_variants.append(collapsed)
    folded_core = collapse_ws(ascii_fold(core_title))
    if folded_core and folded_core not in seen_tv:
        seen_tv.add(folded_core)
        title_variants.append(folded_core)

    queries: list[str] = []
    seen_q: set[str] = set(already_tried) if already_tried else set()
    use_aliases = aliases or [artist]

    for alias_candidate in use_aliases:
        alias = collapse_ws(alias_candidate)
        if not alias:
            continue
        for t in title_variants:
            for pat in (f"{alias} - {t}", f'"{t}" "{alias}"', f"{t} {alias}"):
                if pat not in seen_q:
                    seen_q.add(pat)
                    queries.append(pat)
            if album:
                pat = f"{alias} - {t} {album}"
                if pat not in seen_q:
                    seen_q.add(pat)
                    queries.append(pat)
    if core_title and f'"{core_title}"' not in seen_q:
        queries.append(f'"{core_title}"')

    return queries
