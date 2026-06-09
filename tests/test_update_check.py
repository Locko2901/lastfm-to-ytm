import pytest

pytest.importorskip("flask")

from web.services.update_check import _parse_version


def test_parse_simple_version():
    assert _parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_with_v_prefix():
    assert _parse_version("v1.2.3") == (1, 2, 3)
    assert _parse_version("V2.0.0") == (2, 0, 0)


def test_parse_version_strips_prerelease_suffix():
    assert _parse_version("1.2.3-beta.1") == (1, 2, 3)
    assert _parse_version("1.2.3+build5") == (1, 2, 3)


def test_parse_two_component_version():
    assert _parse_version("1.2") == (1, 2)


def test_parse_version_none():
    assert _parse_version(None) is None


def test_parse_version_empty_string():
    assert _parse_version("") is None


def test_parse_version_non_numeric():
    assert _parse_version("abc") is None


def test_parse_version_ordering():
    assert _parse_version("1.10.0") > _parse_version("1.9.0")
    assert _parse_version("2.0.0") > _parse_version("1.99.99")
