from difflib import SequenceMatcher

from .normalization import RE_DASH, clean_uploader_name, match_key, normalize_base, tokens
from .queries import candidate_artists, clean_title_for_match, split_artist_aliases
from .similarity import (
    JACCARD_WEIGHT,
    SEQUENCE_RATIO_WEIGHT,
    best_similarity,
    coverage,
    jaccard,
)

TITLE_SCORE_WEIGHT = 0.56
ARTIST_SCORE_WEIGHT = 0.32
UPLOADER_SCORE_WEIGHT = 0.07
ALBUM_SCORE_WEIGHT = 0.05

MIN_ARTIST_SIMILARITY = 0.30
MIN_TITLE_SIMILARITY = 0.25

SOFT_PENALTY_PER_HIT = 0.08
SOFT_PENALTY_CAP = 0.25
HARD_PENALTY_PER_HIT = 0.35
HARD_PENALTY_CAP = 0.60

VIDEO_MISMATCH_PENALTY = 0.10
VIDEO_MISMATCH_JACCARD_THRESHOLD = 0.3
STYLE_MISMATCH_VIDEO_PENALTY = 0.18
STYLE_MISMATCH_SONG_PENALTY = 0.12

PRESENCE_BONUS_MIN_COVERAGE = 0.2
PRESENCE_BONUS_STRONG_COVERAGE = 0.5
PRESENCE_BONUS_CAP = 0.07
PRESENCE_BONUS_STRONG_SLOPE = 0.10
PRESENCE_BONUS_STRONG_OFFSET = 0.02
PRESENCE_BONUS_WEAK_SLOPE = 0.04

SONG_TYPE_BONUS = 0.06
VIDEO_TYPE_PENALTY = 0.03
TOPIC_CHANNEL_BONUS = 0.02
TOPIC_CHANNEL_MIN_UPLOADER_SIM = 0.6

HARD_NEGATIVE_TERMS = {
    "nightcore",
    "daycore",
    "sped",
    "slowed",
    "8d",
    "chipmunk",
    "reverb",
    "pitch",
    "bassboosted",
}

SOFT_NEGATIVE_TERMS = {
    "live",
    "acoustic",
    "cover",
    "karaoke",
    "instrumental",
    "remix",
    "edit",
    "loop",
    "mashup",
    "mix",
    "medley",
    "tribute",
    "parody",
    "fanmade",
    "speed",
    "rework",
    "bootleg",
    "bass",
    "boosted",
    "tiktok",
    "phonk",
    "version",
    "lyric",
    "lyrics",
    "visualizer",
    "teaser",
    "preview",
    "short",
    "radio",
    "demo",
}

ALL_NEGATIVE_TERMS = HARD_NEGATIVE_TERMS | SOFT_NEGATIVE_TERMS


def artist_similarity(target_artist: str, r: dict) -> float:
    """Calculate similarity between target artist and search result artists."""
    aliases = split_artist_aliases(target_artist)
    cands = candidate_artists(r)
    best = 0.0
    for cand in cands:
        for alias in aliases:
            best = max(best, best_similarity(alias, cand))
    return best


def uploader_similarity(target_artist: str, r: dict) -> float:
    """Calculate similarity between target artist and video uploader name."""
    author = r.get("author") or ""
    if not author:
        return 0.0
    uploader = clean_uploader_name(author)
    best = 0.0
    for alias in split_artist_aliases(target_artist):
        best = max(best, best_similarity(alias, uploader))
    return best


def title_similarity(target_title: str, r: dict, artist_tokens: set[str]) -> float:
    """Calculate similarity between target title and search result title."""
    candidate_title = r.get("title") or ""
    core_target = clean_title_for_match(target_title, artist_tokens)
    core_candidate = clean_title_for_match(candidate_title, artist_tokens)
    j = jaccard(tokens(core_target), tokens(core_candidate))
    rratio = SequenceMatcher(None, match_key(core_target), match_key(core_candidate)).ratio()
    return JACCARD_WEIGHT * j + SEQUENCE_RATIO_WEIGHT * rratio


def album_name_from_result(r: dict) -> str | None:
    """Extract album name from search result (handles dict or string format)."""
    album = r.get("album")
    if isinstance(album, dict):
        return album.get("name")
    if isinstance(album, str):
        return album
    return None


def hard_negative_hits(candidate_title: str, user_title: str) -> set[str]:
    """Find hard negative terms in candidate that aren't in user's query."""
    cand_tokens = tokens(candidate_title)
    user_tokens = tokens(user_title)
    return (cand_tokens & HARD_NEGATIVE_TERMS) - user_tokens


def negative_penalty(candidate_title: str, user_title: str) -> float:
    """Calculate penalty for unwanted terms (live, remix, cover, etc.) in candidate."""
    cand_tokens = tokens(candidate_title)
    user_tokens = tokens(user_title)
    soft_hits = (cand_tokens & SOFT_NEGATIVE_TERMS) - user_tokens
    hard_hits = (cand_tokens & HARD_NEGATIVE_TERMS) - user_tokens
    if not soft_hits and not hard_hits:
        return 0.0
    light = len(soft_hits)
    hard = len(hard_hits)
    light_penalty = min(SOFT_PENALTY_CAP, SOFT_PENALTY_PER_HIT * light)
    hard_penalty = min(HARD_PENALTY_CAP, HARD_PENALTY_PER_HIT * hard)
    return light_penalty + hard_penalty


def video_mismatch_penalty(r: dict) -> float:
    """Penalize videos where title prefix doesn't match artist (user uploads)."""
    rt = (r.get("resultType") or "").lower()
    if rt != "video":
        return 0.0
    s = normalize_base(r.get("title") or "")
    parts = RE_DASH.split(s, maxsplit=1)
    if len(parts) != 2:
        return 0.0
    left = parts[0]
    left_tokens = tokens(left)
    cand_artist_tokens: set[str] = set()
    for name in candidate_artists(r):
        cand_artist_tokens |= tokens(name)
    if not left_tokens or not cand_artist_tokens:
        return 0.0
    j = jaccard(left_tokens, cand_artist_tokens)
    return VIDEO_MISMATCH_PENALTY if j < VIDEO_MISMATCH_JACCARD_THRESHOLD else 0.0


def style_mismatch_penalty(user_title: str, candidate_title: str, result_type: str) -> float:
    """Penalize when user wants a style (e.g., nightcore) but candidate lacks it."""
    user_styles = tokens(user_title) & HARD_NEGATIVE_TERMS
    if not user_styles:
        return 0.0
    cand_styles = tokens(candidate_title) & HARD_NEGATIVE_TERMS
    if user_styles.issubset(cand_styles):
        return 0.0
    return STYLE_MISMATCH_VIDEO_PENALTY if (result_type or "").lower() == "video" else STYLE_MISMATCH_SONG_PENALTY


def artist_title_presence_bonus(artist: str, title: str, candidate_title: str) -> float:
    """Bonus when both artist and title tokens appear in the candidate title."""
    cand_tokens = tokens(candidate_title)
    if not cand_tokens:
        return 0.0

    aliases = split_artist_aliases(artist)
    alias_token_sets = [tokens(a) for a in aliases if a]
    artist_cov = 0.0
    for ats in alias_token_sets:
        artist_cov = max(artist_cov, coverage(ats, cand_tokens))

    artist_union = set().union(*alias_token_sets) if alias_token_sets else tokens(artist)
    core_title = clean_title_for_match(title, artist_union)
    title_tokens = tokens(core_title)
    title_cov = coverage(title_tokens, cand_tokens)

    both = min(artist_cov, title_cov)
    if both <= PRESENCE_BONUS_MIN_COVERAGE:
        return 0.0
    return min(
        PRESENCE_BONUS_CAP,
        PRESENCE_BONUS_STRONG_SLOPE * both + PRESENCE_BONUS_STRONG_OFFSET
        if both >= PRESENCE_BONUS_STRONG_COVERAGE
        else PRESENCE_BONUS_WEAK_SLOPE * both,
    )


def score_candidate(r: dict, artist: str, title: str, album: str | None) -> float:
    """Calculate match score for a YouTube Music search result."""
    rt = (r.get("resultType") or "").lower()
    if rt not in ("song", "video", ""):
        return 0.0

    candidate_title = r.get("title") or ""
    author_cf = (r.get("author") or "").casefold()
    hard_hits = hard_negative_hits(candidate_title, title)
    if hard_hits and rt == "video" and "topic" not in author_cf:
        return 0.0

    artist_tokens = tokens(artist)
    title_score = title_similarity(title, r, artist_tokens)
    artist_score = artist_similarity(artist, r)
    uploader_score = uploader_similarity(artist, r)
    album_name = album_name_from_result(r)
    album_score = best_similarity(album, album_name) if (album and album_name) else 0.0

    if artist_score < MIN_ARTIST_SIMILARITY and uploader_score < MIN_ARTIST_SIMILARITY:
        return 0.0
    if title_score < MIN_TITLE_SIMILARITY:
        return 0.0

    score = (
        TITLE_SCORE_WEIGHT * title_score
        + ARTIST_SCORE_WEIGHT * artist_score
        + UPLOADER_SCORE_WEIGHT * uploader_score
        + ALBUM_SCORE_WEIGHT * album_score
    )

    score += artist_title_presence_bonus(artist, title, candidate_title)
    score -= negative_penalty(candidate_title, title)
    score -= style_mismatch_penalty(title, candidate_title, rt)
    score -= video_mismatch_penalty(r)

    if rt == "song":
        score += SONG_TYPE_BONUS
    elif rt == "video":
        score -= VIDEO_TYPE_PENALTY
    if "topic" in author_cf and uploader_score >= TOPIC_CHANNEL_MIN_UPLOADER_SIM:
        score += TOPIC_CHANNEL_BONUS
    return max(0.0, min(1.0, score))
