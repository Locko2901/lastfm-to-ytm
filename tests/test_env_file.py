import pytest

pytest.importorskip("flask")

import web.services.env as env_mod
from web.services.env import parse_env_file, update_env_file


def _point_env_file(monkeypatch, tmp_path, contents: str | None = None):
    env_file = tmp_path / ".env"
    if contents is not None:
        env_file.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(env_mod, "ENV_FILE", env_file)
    return env_file


def test_parse_missing_file_returns_empty(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path)
    assert parse_env_file() == {}


def test_parse_basic_pairs(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path, "LASTFM_USER=alice\nLIMIT=50\n")
    assert parse_env_file() == {"LASTFM_USER": "alice", "LIMIT": "50"}


def test_parse_skips_comments_and_blanks(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path, "# a comment\n\nLIMIT=10\n")
    assert parse_env_file() == {"LIMIT": "10"}


def test_parse_strips_inline_comment(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path, "LIMIT=10 # max tracks\n")
    assert parse_env_file() == {"LIMIT": "10"}


def test_parse_preserves_hash_without_space(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path, "ACCENT=#ff0000\n")
    assert parse_env_file() == {"ACCENT": "#ff0000"}


def test_update_existing_key_in_place(monkeypatch, tmp_path):
    env_file = _point_env_file(monkeypatch, tmp_path, "LIMIT=10\nLASTFM_USER=alice\n")
    update_env_file({"LIMIT": "99"})
    assert parse_env_file() == {"LIMIT": "99", "LASTFM_USER": "alice"}
    assert env_file.read_text(encoding="utf-8").splitlines()[0] == "LIMIT=99"


def test_update_preserves_inline_comment(monkeypatch, tmp_path):
    env_file = _point_env_file(monkeypatch, tmp_path, "LIMIT=10 # max tracks\n")
    update_env_file({"LIMIT": "42"})
    assert env_file.read_text(encoding="utf-8").strip() == "LIMIT=42 # max tracks"


def test_update_appends_new_key(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path, "LIMIT=10\n")
    update_env_file({"NEW_KEY": "value"})
    parsed = parse_env_file()
    assert parsed["LIMIT"] == "10"
    assert parsed["NEW_KEY"] == "value"


def test_update_creates_file_when_absent(monkeypatch, tmp_path):
    _point_env_file(monkeypatch, tmp_path)
    update_env_file({"LIMIT": "5"})
    assert parse_env_file() == {"LIMIT": "5"}


def test_update_preserves_comment_lines(monkeypatch, tmp_path):
    env_file = _point_env_file(monkeypatch, tmp_path, "# header comment\nLIMIT=10\n")
    update_env_file({"LIMIT": "20"})
    assert env_file.read_text(encoding="utf-8").splitlines()[0] == "# header comment"
