import json

import pytest

import src.config as config_mod
from src.config import (
    Settings,
    _parse_privacy,
    _str_to_bool,
    _str_to_float,
    _str_to_int,
    _strip_inline_comment,
    load_custom_playlists,
)


def test_strip_inline_comment_basic():
    assert _strip_inline_comment("value # comment") == "value"


def test_strip_inline_comment_tab():
    assert _strip_inline_comment("value\t# comment") == "value"


def test_strip_inline_comment_full_line_comment():
    assert _strip_inline_comment("# just a comment") is None


def test_strip_inline_comment_none():
    assert _strip_inline_comment(None) is None


def test_strip_inline_comment_empty_after_strip():
    assert _strip_inline_comment("   ") is None


def test_strip_inline_comment_preserves_hash_without_space():
    assert _strip_inline_comment("c#major") == "c#major"


def test_str_to_bool_truthy_values():
    for val in ("1", "true", "T", "yes", "y", "on", "TRUE"):
        assert _str_to_bool(val) is True


def test_str_to_bool_falsy_values():
    for val in ("0", "false", "no", "off", "anything"):
        assert _str_to_bool(val) is False


def test_str_to_bool_none_uses_default():
    assert _str_to_bool(None, default=True) is True
    assert _str_to_bool(None, default=False) is False


def test_str_to_bool_strips_inline_comment():
    assert _str_to_bool("true  # enable") is True


def test_str_to_int_valid():
    assert _str_to_int("42", 0) == 42


def test_str_to_int_with_comment():
    assert _str_to_int("100 # the limit", 0) == 100


def test_str_to_int_invalid_uses_default():
    assert _str_to_int("not-a-number", 7) == 7


def test_str_to_int_none_uses_default():
    assert _str_to_int(None, 5) == 5


def test_str_to_float_valid():
    assert _str_to_float("0.25", 1.0) == 0.25


def test_str_to_float_with_comment():
    assert _str_to_float("48.0 # half life", 1.0) == 48.0


def test_str_to_float_invalid_uses_default():
    assert _str_to_float("abc", 2.5) == 2.5


def test_parse_privacy_explicit_values():
    assert _parse_privacy("PUBLIC") == "PUBLIC"
    assert _parse_privacy("unlisted") == "UNLISTED"
    assert _parse_privacy("Private") == "PRIVATE"


def test_parse_privacy_boolean_backcompat_true():
    assert _parse_privacy("true") == "PUBLIC"
    assert _parse_privacy("1") == "PUBLIC"
    assert _parse_privacy("yes") == "PUBLIC"


def test_parse_privacy_boolean_backcompat_false():
    assert _parse_privacy("false") == "PRIVATE"
    assert _parse_privacy("0") == "PRIVATE"
    assert _parse_privacy("off") == "PRIVATE"


def test_parse_privacy_none_uses_default():
    assert _parse_privacy(None, "PRIVATE") == "PRIVATE"


def test_parse_privacy_unknown_uses_default():
    assert _parse_privacy("maybe", "UNLISTED") == "UNLISTED"


def test_parse_privacy_strips_inline_comment():
    assert _parse_privacy("PUBLIC # share it") == "PUBLIC"


@pytest.fixture
def clean_env(monkeypatch):
    """Isolate from_env from the real .env and OS environment.

    from_env calls load_dotenv(..., override=True), which would otherwise pull
    in the developer's actual .env and clobber the values set here.
    """
    monkeypatch.setattr(config_mod, "load_dotenv", lambda *_a, **_k: None)
    prefixes = ("LASTFM_", "PLAYLIST_", "WEEKLY_", "RECENCY_", "TAG_", "HISTORY_", "WEBHOOK_", "CACHE_", "AUTO_", "CUSTOM_PLAYLISTS")
    extras = {
        "MAKE_PUBLIC",
        "LIMIT",
        "DEDUPLICATE",
        "SLEEP_BETWEEN_SEARCHES",
        "USE_ANON_SEARCH",
        "EARLY_TERMINATION_SCORE",
        "USE_RECENCY_WEIGHTING",
        "MAX_RAW_SCROBBLES",
        "LOG_LEVEL",
        "API_MAX_RETRIES",
        "SEARCH_MAX_WORKERS",
        "BACKFILL_PASSES",
        "YTM_AUTH_PATH",
    }
    for key in list(__import__("os").environ):
        if key.startswith(prefixes) or key in extras:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LASTFM_USER", "alice")
    monkeypatch.setenv("LASTFM_API_KEY", "secret-key")
    return monkeypatch


def test_from_env_requires_credentials(monkeypatch):
    monkeypatch.setattr(config_mod, "load_dotenv", lambda *_a, **_k: None)
    monkeypatch.delenv("LASTFM_USER", raising=False)
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        Settings.from_env()


@pytest.mark.usefixtures("clean_env")
def test_from_env_defaults():
    settings = Settings.from_env()
    assert settings.lastfm_user == "alice"
    assert settings.limit == 100
    assert settings.deduplicate is True
    assert settings.privacy == "PRIVATE"
    assert settings.weekly_keep_weeks == 2


def test_from_env_make_public_sets_privacy(clean_env):
    clean_env.setenv("MAKE_PUBLIC", "true")
    assert Settings.from_env().privacy_status == "PUBLIC"


def test_from_env_playlist_privacy_sets_privacy(clean_env):
    clean_env.setenv("PLAYLIST_PRIVACY", "unlisted")
    assert Settings.from_env().privacy_status == "UNLISTED"


def test_from_env_playlist_privacy_takes_precedence_over_make_public(clean_env):
    clean_env.setenv("PLAYLIST_PRIVACY", "PUBLIC")
    clean_env.setenv("MAKE_PUBLIC", "PRIVATE")
    assert Settings.from_env().privacy_status == "PUBLIC"


def test_from_env_make_public_boolean_warns(clean_env, caplog):
    clean_env.setenv("MAKE_PUBLIC", "true")
    with caplog.at_level("WARNING"):
        Settings.from_env()
    assert any("deprecated" in r.message.lower() for r in caplog.records)


def test_from_env_make_public_string_does_not_warn(clean_env, caplog):
    clean_env.setenv("MAKE_PUBLIC", "PUBLIC")
    with caplog.at_level("WARNING"):
        Settings.from_env()
    assert not any("deprecated" in r.message.lower() for r in caplog.records)


def test_from_env_recency_play_weight_clamped(clean_env):
    clean_env.setenv("RECENCY_PLAY_WEIGHT", "5.0")
    assert Settings.from_env().recency_play_weight == 0.7


def test_from_env_recency_min_plays_floor(clean_env):
    clean_env.setenv("RECENCY_MIN_PLAYS", "0")
    assert Settings.from_env().recency_min_plays == 1


def test_from_env_max_raw_scrobbles_zero_means_unlimited(clean_env):
    clean_env.setenv("MAX_RAW_SCROBBLES", "0")
    assert Settings.from_env().max_raw_scrobbles == 999999


def test_from_env_invalid_log_level_falls_back(clean_env):
    clean_env.setenv("LOG_LEVEL", "verbose")
    assert Settings.from_env().log_level == "INFO"


def test_from_env_invalid_webhook_events_falls_back(clean_env):
    clean_env.setenv("WEBHOOK_EVENTS", "sometimes")
    assert Settings.from_env().webhook_events == "error"


@pytest.mark.usefixtures("clean_env")
def test_from_env_weekly_make_public_unset_is_none():
    assert Settings.from_env().weekly_privacy_status is None


def test_from_env_weekly_make_public_set(clean_env):
    clean_env.setenv("WEEKLY_MAKE_PUBLIC", "false")
    assert Settings.from_env().weekly_privacy_status == "PRIVATE"


def test_from_env_weekly_playlist_privacy_set(clean_env):
    clean_env.setenv("WEEKLY_PLAYLIST_PRIVACY", "unlisted")
    assert Settings.from_env().weekly_privacy_status == "UNLISTED"


def test_from_env_weekly_playlist_privacy_takes_precedence(clean_env):
    clean_env.setenv("WEEKLY_PLAYLIST_PRIVACY", "PUBLIC")
    clean_env.setenv("WEEKLY_MAKE_PUBLIC", "PRIVATE")
    assert Settings.from_env().weekly_privacy_status == "PUBLIC"


def test_from_env_weekly_make_public_boolean_warns(clean_env, caplog):
    clean_env.setenv("WEEKLY_MAKE_PUBLIC", "true")
    with caplog.at_level("WARNING"):
        Settings.from_env()
    assert any("deprecated" in r.message.lower() for r in caplog.records)


def test_load_custom_playlists_missing_file(tmp_path):
    assert load_custom_playlists(str(tmp_path / "nope.json")) == []


def test_load_custom_playlists_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    assert load_custom_playlists(str(path)) == []


def test_load_custom_playlists_parses_entries(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps(
            {
                "playlists": [
                    {
                        "name": "Rock",
                        "tags": ["Rock", "Metal"],
                        "match": "all",
                        "limit": 30,
                        "blacklist": ["Bad Artist"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    configs = load_custom_playlists(str(path))
    assert len(configs) == 1
    cfg = configs[0]
    assert cfg.name == "Rock"
    assert cfg.tags == ("rock", "metal")
    assert cfg.match == "all"
    assert cfg.limit == 30
    assert cfg.blacklist == frozenset({"bad artist"})


def test_load_custom_playlists_skips_entries_without_tags(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(json.dumps({"playlists": [{"name": "NoTags"}]}), encoding="utf-8")
    assert load_custom_playlists(str(path)) == []


def test_load_custom_playlists_invalid_match_defaults_to_any(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps({"playlists": [{"name": "P", "tags": ["x"], "match": "weird"}]}),
        encoding="utf-8",
    )
    assert load_custom_playlists(str(path))[0].match == "any"
