import pytest

from src.search.similarity import best_similarity, coverage, jaccard


def test_jaccard_identical_sets():
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint_sets():
    assert jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_both_empty():
    assert jaccard(set(), set()) == 0.0


def test_jaccard_one_empty():
    assert jaccard({"a"}, set()) == 0.0


def test_jaccard_partial_overlap():
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


def test_best_similarity_identical_strings():
    assert best_similarity("hello world", "hello world") == pytest.approx(1.0)


def test_best_similarity_unrelated_strings_low():
    assert best_similarity("abcdef", "zzzzzz") < 0.2


def test_best_similarity_bounded():
    val = best_similarity("the beatles", "beatles the")
    assert 0.0 <= val <= 1.0


def test_coverage_full():
    assert coverage({"a", "b"}, {"a", "b", "c"}) == 1.0


def test_coverage_partial():
    assert coverage({"a", "b"}, {"a", "x"}) == 0.5


def test_coverage_empty_sub():
    assert coverage(set(), {"a"}) == 0.0
