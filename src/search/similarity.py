from difflib import SequenceMatcher

from .normalization import match_key, tokens


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def best_similarity(a: str, b: str) -> float:
    a_tokens, b_tokens = tokens(a), tokens(b)
    j = jaccard(a_tokens, b_tokens)
    r = SequenceMatcher(None, match_key(a), match_key(b)).ratio()
    return 0.7 * j + 0.3 * r


def coverage(sub: set[str], sup: set[str]) -> float:
    if not sub:
        return 0.0
    return len(sub & sup) / len(sub)
