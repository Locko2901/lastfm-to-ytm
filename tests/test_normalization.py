import pytest

from src.search.normalization import (
    alnum_space,
    ascii_fold,
    clean_uploader_name,
    collapse_ws,
    match_key,
    nfkc_casefold,
    normalize_base,
    remove_bracketed,
    strip_feat_clauses,
    tokens,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  hello   world ", "hello world"),
        ("a\tb\nc", "a b c"),
        ("", ""),
        ("single", "single"),
    ],
)
def test_collapse_ws(raw, expected):
    assert collapse_ws(raw) == expected


def test_nfkc_casefold_lowercases():
    assert nfkc_casefold("HELLO") == "hello"


def test_nfkc_casefold_normalizes_fullwidth():
    assert nfkc_casefold("\uff21") == "a"


def test_ascii_fold_removes_diacritics():
    assert ascii_fold("Beyoncé") == "beyonce"
    assert ascii_fold("Mötley Crüe") == "motley crue"


def test_alnum_space_replaces_punctuation_with_space():
    assert alnum_space("a-b_c!d") == "a b c d"


def test_normalize_base_expands_ampersand():
    assert normalize_base("Simon & Garfunkel") == "simon and garfunkel"


def test_normalize_base_collapses_and_casefolds():
    assert normalize_base("  The  XX  ") == "the xx"


def test_tokens_empty_string_returns_empty_set():
    assert tokens("") == set()


def test_tokens_splits_and_includes_folded_variant():
    result = tokens("Beyoncé Halo")
    assert "halo" in result
    assert "beyonce" in result


def test_tokens_ampersand_becomes_and():
    assert tokens("rock & roll") == {"rock", "and", "roll"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Song feat. Artist", "Song "),
        ("Song ft. Artist", "Song "),
        ("Song featuring Artist", "Song "),
        ("Song with Artist", "Song "),
        ("Plain Title", "Plain Title"),
    ],
)
def test_strip_feat_clauses(raw, expected):
    assert strip_feat_clauses(raw) == expected


def test_remove_bracketed_handles_nested_and_multiple():
    assert remove_bracketed("Title (Remix) [Live]").strip() == "Title"


def test_remove_bracketed_unicode_brackets():
    assert remove_bracketed("曲名（ライブ）").strip() == "曲名"


def test_match_key_is_ascii_alnum_collapsed():
    assert match_key("Beyoncé - Halo!") == "beyonce halo"


def test_match_key_none_safe():
    assert match_key("") == ""


def test_clean_uploader_name_strips_noise():
    assert clean_uploader_name("Adele - Topic") == "adele"
    assert clean_uploader_name("ColdplayVEVO") == "coldplayvevo"


def test_clean_uploader_name_removes_official_records():
    assert "official" not in clean_uploader_name("Official Band Records")


def test_clean_uploader_name_empty_input():
    assert clean_uploader_name("") == ""


def test_tokens_deduplicates():
    assert tokens("na na na") == {"na"}


def test_remove_bracketed_no_brackets_unchanged():
    assert remove_bracketed("Plain Title") == "Plain Title"


def test_ascii_fold_passthrough_ascii():
    assert ascii_fold("plain text") == "plain text"
