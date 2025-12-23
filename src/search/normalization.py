import re
import unicodedata

try:
    from unidecode import unidecode as _unidecode
except ImportError:
    from text_unidecode import unidecode as _unidecode

RE_FEAT_CLAUSE = re.compile(r"\b(?:feat(?:\.|uring)?|ft\.?|with)\b.*$", flags=re.IGNORECASE)
RE_ARTIST_SPLIT = re.compile(
    r"\s*(?:,|&|x|×|\/|;|\band\b|\bwith\b|\bfeat(?:\.|uring)?\b|\bft\.?\b)\s*",
    flags=re.IGNORECASE,
)
RE_DASH = re.compile(r"\s*[-–—]\s*")

BRACKET_PAIRS = [
    ("(", ")"),
    ("[", "]"),
    ("{", "}"),
    ("（", "）"),
    ("【", "】"),
    ("「", "」"),
    ("『", "』"),
    ("〈", "〉"),
    ("《", "》"),
    ("＜", "＞"),
    ("‹", "›"),
    ("⟨", "⟩"),
]
RE_BRACKETED = [re.compile(re.escape(left) + r"[^" + re.escape(right) + r"]*" + re.escape(right)) for (left, right) in BRACKET_PAIRS]

UPLOADER_NOISE = {
    "official",
    "vevo",
    "topic",
    "music",
    "records",
    "recordings",
    "recording",
    "channel",
    "tv",
    "label",
    "auto-generated",
    "auto",
    "generated",
    "wmg",
    "umg",
    "smg",
    "sony",
    "universal",
    "warner",
    "publishing",
    "inc",
    "ltd",
    "co",
    "entertainment",
}


def collapse_ws(s: str) -> str:
    return " ".join(s.split())


def nfkc_casefold(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def ascii_fold(s: str) -> str:
    return _unidecode(unicodedata.normalize("NFKC", s).casefold())


def alnum_space(s: str) -> str:
    return "".join(ch if ch.isalnum() else " " for ch in s)


def normalize_base(s: str) -> str:
    """Base normalization: NFKC casefolding + ampersand replacement."""
    return collapse_ws(nfkc_casefold(s).replace("&", " and "))


def tokens(s: str) -> set[str]:
    """Extract normalized token set from string."""
    if not s:
        return set()
    base = normalize_base(s)
    t1 = set(filter(None, alnum_space(base).split()))
    folded = ascii_fold(base)
    if folded and folded != base:
        t2 = set(filter(None, alnum_space(folded).split()))
        t1 |= t2
    return t1


def strip_feat_clauses(s: str) -> str:
    """Remove featuring clauses from string."""
    return RE_FEAT_CLAUSE.sub("", s)


def remove_bracketed(s: str) -> str:
    """Remove bracketed content from string."""
    prev = None
    while s and prev != s:
        prev = s
        for pat in RE_BRACKETED:
            s = pat.sub(" ", s)
    return s


def match_key(s: str) -> str:
    """Generate a match key for string comparison."""
    return collapse_ws(alnum_space(ascii_fold(s or "")))


def clean_uploader_name(author: str) -> str:
    """Clean uploader name by removing common noise words."""
    s = normalize_base(author or "")
    s = re.sub(r"[-–—]\s*topic\b", " ", s)
    toks = [t for t in tokens(s) if t not in UPLOADER_NOISE]
    return " ".join(toks)
