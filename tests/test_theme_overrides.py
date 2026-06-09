import pytest

pytest.importorskip("flask")

from web.services.theme import _empty, _sanitise


def test_sanitise_non_dict_returns_empty():
    assert _sanitise("nope") == _empty()
    assert _sanitise(None) == _empty()
    assert _sanitise([1, 2, 3]) == _empty()


def test_sanitise_empty_dict():
    result = _sanitise({})
    assert result == {"enabled": False, "parents": {"dark": {}, "light": {}}}


def test_sanitise_keeps_valid_hex():
    result = _sanitise({"enabled": True, "parents": {"dark": {"--accent": "#ff0000"}}})
    assert result["enabled"] is True
    assert result["parents"]["dark"]["--accent"] == "#ff0000"


def test_sanitise_accepts_short_and_alpha_hex():
    result = _sanitise({"parents": {"light": {"--a": "#abc", "--b": "#aabbccdd"}}})
    assert result["parents"]["light"]["--a"] == "#abc"
    assert result["parents"]["light"]["--b"] == "#aabbccdd"


def test_sanitise_strips_whitespace_in_value():
    result = _sanitise({"parents": {"dark": {"--accent": "  #112233  "}}})
    assert result["parents"]["dark"]["--accent"] == "#112233"


def test_sanitise_drops_keys_without_double_dash():
    result = _sanitise({"parents": {"dark": {"accent": "#ff0000"}}})
    assert result["parents"]["dark"] == {}


def test_sanitise_drops_invalid_hex():
    result = _sanitise({"parents": {"dark": {"--accent": "red", "--bg": "rgb(0,0,0)"}}})
    assert result["parents"]["dark"] == {}


def test_sanitise_drops_non_string_values():
    result = _sanitise({"parents": {"dark": {"--accent": 123}}})
    assert result["parents"]["dark"] == {}


def test_sanitise_ignores_unknown_parents():
    result = _sanitise({"parents": {"midnight": {"--accent": "#ffffff"}}})
    assert set(result["parents"].keys()) == {"dark", "light"}


def test_sanitise_enabled_is_coerced_to_bool():
    assert _sanitise({"enabled": "yes"})["enabled"] is True
    assert _sanitise({"enabled": 0})["enabled"] is False
