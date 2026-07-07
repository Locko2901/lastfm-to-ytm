import json

import pytest

import src.config as config_mod
from src.config import (
    Settings,
    _parse_privacy,
    _parse_session_hours,
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
        "TIMEZONE",
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


def test_parse_session_hours_valid():
    assert _parse_session_hours("9-23") == (9, 23)
    assert _parse_session_hours("22-4") == (22, 4)
    assert _parse_session_hours("0-0") == (0, 0)


def test_parse_session_hours_invalid_uses_default():
    assert _parse_session_hours(None) == (9, 23)
    assert _parse_session_hours("") == (9, 23)
    assert _parse_session_hours("9") == (9, 23)
    assert _parse_session_hours("9-24") == (9, 23)
    assert _parse_session_hours("-1-5") == (9, 23)
    assert _parse_session_hours("a-b") == (9, 23)


def test_parse_session_hours_strips_comment():
    assert _parse_session_hours("18-2 # my evenings") == (18, 2)


@pytest.mark.usefixtures("clean_env")
def test_from_env_recency_new_defaults():
    settings = Settings.from_env()
    assert settings.recency_normalization == "linear"
    assert settings.recency_velocity_weight == 0.0
    assert settings.recency_session_weighting is False
    assert settings.recency_session_start == 9
    assert settings.recency_session_end == 23
    assert settings.recency_session_timezone == "UTC"


def test_from_env_recency_normalization_valid(clean_env):
    clean_env.setenv("RECENCY_NORMALIZATION", "LOG")
    assert Settings.from_env().recency_normalization == "log"


def test_from_env_recency_normalization_invalid_falls_back(clean_env):
    clean_env.setenv("RECENCY_NORMALIZATION", "bogus")
    assert Settings.from_env().recency_normalization == "linear"


def test_from_env_recency_velocity_weight_clamped(clean_env):
    clean_env.setenv("RECENCY_VELOCITY_WEIGHT", "2.0")
    assert Settings.from_env().recency_velocity_weight == 0.0
    clean_env.setenv("RECENCY_VELOCITY_WEIGHT", "0.5")
    assert Settings.from_env().recency_velocity_weight == 0.5


def test_from_env_recency_session_hours_parsed(clean_env):
    clean_env.setenv("RECENCY_SESSION_WEIGHTING", "true")
    clean_env.setenv("RECENCY_SESSION_HOURS", "20-2")
    settings = Settings.from_env()
    assert settings.recency_session_weighting is True
    assert settings.recency_session_start == 20
    assert settings.recency_session_end == 2


def test_from_env_recency_session_timezone_falls_back_to_weekly(clean_env):
    clean_env.setenv("WEEKLY_TIMEZONE", "America/New_York")
    assert Settings.from_env().recency_session_timezone == "America/New_York"


def test_from_env_recency_session_timezone_explicit_wins(clean_env):
    clean_env.setenv("WEEKLY_TIMEZONE", "America/New_York")
    clean_env.setenv("RECENCY_SESSION_TIMEZONE", "Europe/Berlin")
    assert Settings.from_env().recency_session_timezone == "Europe/Berlin"


@pytest.mark.usefixtures("clean_env")
def test_from_env_timezone_default_is_utc():
    settings = Settings.from_env()
    assert settings.timezone == "UTC"
    assert settings.weekly_timezone == "UTC"
    assert settings.recency_session_timezone == "UTC"


def test_from_env_general_timezone_inherited_by_weekly_and_session(clean_env):
    clean_env.setenv("TIMEZONE", "Europe/Berlin")
    settings = Settings.from_env()
    assert settings.timezone == "Europe/Berlin"
    assert settings.weekly_timezone == "Europe/Berlin"
    assert settings.recency_session_timezone == "Europe/Berlin"


def test_from_env_weekly_timezone_overrides_general(clean_env):
    clean_env.setenv("TIMEZONE", "Europe/Berlin")
    clean_env.setenv("WEEKLY_TIMEZONE", "America/New_York")
    settings = Settings.from_env()
    assert settings.weekly_timezone == "America/New_York"
    assert settings.recency_session_timezone == "America/New_York"


def test_from_env_session_timezone_overrides_general(clean_env):
    clean_env.setenv("TIMEZONE", "Europe/Berlin")
    clean_env.setenv("RECENCY_SESSION_TIMEZONE", "Asia/Tokyo")
    settings = Settings.from_env()
    assert settings.recency_session_timezone == "Asia/Tokyo"
    assert settings.weekly_timezone == "Europe/Berlin"


def test_from_env_local_lastfm_db_defaults(clean_env):
    clean_env.delenv("USE_LOCAL_LASTFM_DB", raising=False)
    settings = Settings.from_env()
    assert settings.use_local_lastfm_db is False
    assert settings.lastfm_local_db_file.endswith("lastfm_history.db")
    assert settings.lastfm_local_db_max_scrobbles == 0


def test_from_env_local_lastfm_db_enabled(clean_env):
    clean_env.setenv("USE_LOCAL_LASTFM_DB", "true")
    clean_env.setenv("LASTFM_LOCAL_DB_MAX_SCROBBLES", "5000")
    settings = Settings.from_env()
    assert settings.use_local_lastfm_db is True
    assert settings.lastfm_local_db_max_scrobbles == 5000


def test_from_env_max_raw_scrobbles_zero_means_unlimited(clean_env):
    clean_env.setenv("MAX_RAW_SCROBBLES", "0")
    assert Settings.from_env().max_raw_scrobbles == 999999


def test_from_env_invalid_log_level_falls_back(clean_env):
    clean_env.setenv("LOG_LEVEL", "verbose")
    assert Settings.from_env().log_level == "INFO"


def test_from_env_invalid_webhook_events_falls_back(clean_env):
    clean_env.setenv("WEBHOOK_EVENTS", "sometimes")
    assert Settings.from_env().webhook_events == "error"


def test_from_env_webhook_allow_private_default_false(clean_env):
    clean_env.delenv("WEBHOOK_ALLOW_PRIVATE", raising=False)
    assert Settings.from_env().webhook_allow_private is False


def test_from_env_webhook_allow_private_true(clean_env):
    clean_env.setenv("WEBHOOK_ALLOW_PRIVATE", "true")
    assert Settings.from_env().webhook_allow_private is True


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


def test_load_custom_playlists_parses_blacklist_artists(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps(
            {
                "playlists": [
                    {
                        "name": "Rock",
                        "tags": ["rock"],
                        "blacklist_artists": ["Unwanted Artist"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = load_custom_playlists(str(path))[0]
    assert cfg.blacklist_artists == frozenset({"unwanted artist"})


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


def test_load_custom_playlists_parses_artist_playlist(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps(
            {
                "playlists": [
                    {
                        "name": "Faves",
                        "kind": "artists",
                        "artists": ["Radiohead", "Aphex Twin"],
                        "limit": 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = load_custom_playlists(str(path))[0]
    assert cfg.kind == "artists"
    assert cfg.artists == ("radiohead", "aphex twin")
    assert cfg.tags == ()
    assert cfg.limit == 40


def test_load_custom_playlists_skips_artist_playlist_without_artists(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps({"playlists": [{"name": "Faves", "kind": "artists"}]}),
        encoding="utf-8",
    )
    assert load_custom_playlists(str(path)) == []


def test_load_custom_playlists_invalid_kind_defaults_to_tags(tmp_path):
    path = tmp_path / "custom.json"
    path.write_text(
        json.dumps({"playlists": [{"name": "P", "tags": ["x"], "kind": "weird"}]}),
        encoding="utf-8",
    )
    assert load_custom_playlists(str(path))[0].kind == "tags"


def test_resolve_runtime_dir_prefers_runtime_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "rt"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "legacy"))
    assert config_mod._resolve_runtime_dir() == tmp_path / "rt"


def test_resolve_runtime_dir_legacy_cache_env_is_alias(monkeypatch, tmp_path):
    monkeypatch.delenv("RUNTIME_DIR", raising=False)
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "legacy"))
    assert config_mod._resolve_runtime_dir() == tmp_path / "legacy"


def test_resolve_runtime_dir_migrates_legacy_cache(monkeypatch, tmp_path):
    monkeypatch.delenv("RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CACHE_DIR", raising=False)
    legacy = tmp_path / "cache"
    legacy.mkdir()
    (legacy / "history.db").write_text("data", encoding="utf-8")
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", legacy)

    result = config_mod._resolve_runtime_dir()

    assert result == tmp_path / "runtime"
    assert (tmp_path / "runtime" / "history.db").read_text(encoding="utf-8") == "data"
    assert not legacy.exists()


def test_resolve_runtime_dir_default_when_no_legacy(monkeypatch, tmp_path):
    monkeypatch.delenv("RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CACHE_DIR", raising=False)
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", tmp_path / "cache")
    assert config_mod._resolve_runtime_dir() == tmp_path / "runtime"


def test_remap_legacy_path_relative(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", tmp_path / "cache")
    assert config_mod._remap_legacy_path("cache/history.db") == str(tmp_path / "runtime" / "history.db")


def test_remap_legacy_path_absolute(monkeypatch, tmp_path):
    legacy = tmp_path / "cache"
    monkeypatch.setattr(config_mod, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", legacy)
    assert config_mod._remap_legacy_path(str(legacy / "sub" / "db.sqlite")) == str(tmp_path / "runtime" / "sub" / "db.sqlite")


def test_remap_legacy_path_leaves_unrelated_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(config_mod, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", tmp_path / "cache")
    assert config_mod._remap_legacy_path("/somewhere/else/db.sqlite") == "/somewhere/else/db.sqlite"
    assert config_mod._remap_legacy_path("runtime/history.db") == "runtime/history.db"


def test_remap_legacy_path_noop_when_pinned_to_legacy(monkeypatch, tmp_path):
    legacy = tmp_path / "cache"
    monkeypatch.setattr(config_mod, "RUNTIME_DIR", legacy)
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", legacy)
    assert config_mod._remap_legacy_path("cache/history.db") == "cache/history.db"


def _prep_env_migration(monkeypatch, tmp_path):
    monkeypatch.delenv("RUNTIME_DIR", raising=False)
    monkeypatch.delenv("CACHE_DIR", raising=False)
    monkeypatch.setattr(config_mod, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(config_mod, "_LEGACY_CACHE_DIR", tmp_path / "cache")
    return tmp_path / ".env"


def test_migrate_env_rewrites_legacy_cache_paths(monkeypatch, tmp_path):
    env_file = _prep_env_migration(monkeypatch, tmp_path)
    env_file.write_text(
        "HISTORY_DB_FILE=cache/history.db\nTAG_CACHE_FILE=cache/.tag_cache.json # tag cache\nLASTFM_USER=alice\n",
        encoding="utf-8",
    )
    assert config_mod.migrate_env_to_runtime() is True
    contents = env_file.read_text(encoding="utf-8")
    assert "HISTORY_DB_FILE=runtime/history.db\n" in contents
    assert "TAG_CACHE_FILE=runtime/.tag_cache.json # tag cache\n" in contents
    assert "LASTFM_USER=alice\n" in contents


def test_migrate_env_leaves_custom_paths(monkeypatch, tmp_path):
    env_file = _prep_env_migration(monkeypatch, tmp_path)
    env_file.write_text("HISTORY_DB_FILE=/data/mydb.sqlite\n", encoding="utf-8")
    assert config_mod.migrate_env_to_runtime() is False
    assert env_file.read_text(encoding="utf-8") == "HISTORY_DB_FILE=/data/mydb.sqlite\n"


def test_migrate_env_leaves_runtime_paths(monkeypatch, tmp_path):
    env_file = _prep_env_migration(monkeypatch, tmp_path)
    env_file.write_text("HISTORY_DB_FILE=runtime/history.db\n", encoding="utf-8")
    assert config_mod.migrate_env_to_runtime() is False
    assert env_file.read_text(encoding="utf-8") == "HISTORY_DB_FILE=runtime/history.db\n"


def test_migrate_env_skipped_when_custom_dir_env_set(monkeypatch, tmp_path):
    env_file = _prep_env_migration(monkeypatch, tmp_path)
    env_file.write_text("HISTORY_DB_FILE=cache/history.db\n", encoding="utf-8")
    monkeypatch.setenv("RUNTIME_DIR", str(tmp_path / "custom"))
    assert config_mod.migrate_env_to_runtime() is False
    assert env_file.read_text(encoding="utf-8") == "HISTORY_DB_FILE=cache/history.db\n"


def test_migrate_env_rewrites_absolute_legacy_path(monkeypatch, tmp_path):
    env_file = _prep_env_migration(monkeypatch, tmp_path)
    legacy_abs = tmp_path / "cache" / "history.db"
    env_file.write_text(f"HISTORY_DB_FILE={legacy_abs}\n", encoding="utf-8")
    assert config_mod.migrate_env_to_runtime() is True
    expected = tmp_path / "runtime" / "history.db"
    assert env_file.read_text(encoding="utf-8") == f"HISTORY_DB_FILE={expected}\n"


def test_migrate_env_missing_file_is_noop(monkeypatch, tmp_path):
    _prep_env_migration(monkeypatch, tmp_path)
    assert config_mod.migrate_env_to_runtime() is False


def test_migrate_env_ignores_non_runtime_keys(monkeypatch, tmp_path):
    env_file = _prep_env_migration(monkeypatch, tmp_path)
    env_file.write_text("SOME_OTHER_PATH=cache/thing.json\n", encoding="utf-8")
    assert config_mod.migrate_env_to_runtime() is False
    assert env_file.read_text(encoding="utf-8") == "SOME_OTHER_PATH=cache/thing.json\n"
