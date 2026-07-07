"""Tests for the .env completeness/reconcile helpers in web.services.env.

Pure and offline: every filesystem path is redirected into ``tmp_path`` via
monkeypatch, so no real ``.env``/``.env.example`` is ever touched. Flask is not
needed here, but the module lives under ``web`` so we guard the import.
"""

from __future__ import annotations

import pytest

env = pytest.importorskip("web.services.env")


@pytest.fixture
def env_paths(monkeypatch, tmp_path):
    """Redirect ENV_FILE/ENV_EXAMPLE_FILE/RUNTIME_DIR into tmp_path."""
    env_file = tmp_path / ".env"
    example_file = tmp_path / ".env.example"
    monkeypatch.setattr(env, "ENV_FILE", env_file)
    monkeypatch.setattr(env, "ENV_EXAMPLE_FILE", example_file)
    monkeypatch.setattr(env, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(env, "PROJECT_ROOT", tmp_path)
    return env_file, example_file


def test_parse_env_example_orders_keys(env_paths):
    _env_file, example_file = env_paths
    example_file.write_text("# header\nB=2\nA=1 # inline\n", encoding="utf-8")
    parsed = env.parse_env_example()
    assert list(parsed) == ["B", "A"]
    assert parsed["A"] == "1"


def test_check_completeness_reports_missing(env_paths):
    env_file, example_file = env_paths
    env_file.write_text("A=1\n", encoding="utf-8")
    example_file.write_text("A=1\nB=2\nC=3\n", encoding="utf-8")
    info = env.check_env_completeness()
    assert info["env_present"] is True
    assert info["example_present"] is True
    assert info["missing_keys"] == ["B", "C"]
    assert info["missing_count"] == 2


def test_check_completeness_no_env_is_empty(env_paths):
    _env_file, example_file = env_paths
    example_file.write_text("A=1\n", encoding="utf-8")
    info = env.check_env_completeness()
    assert info["env_present"] is False
    assert info["missing_count"] == 0


def test_check_completeness_flags_missing_example(env_paths):
    env_file, _example_file = env_paths
    env_file.write_text("A=1\n", encoding="utf-8")
    info = env.check_env_completeness()
    assert info["example_present"] is False
    assert info["missing_count"] == 0


def test_reconcile_preserves_values_and_inserts_missing(env_paths):
    env_file, example_file = env_paths
    env_file.write_text("A=myvalue\n", encoding="utf-8")
    example_file.write_text(
        "# section\nA=default_a # comment a\nB=default_b # comment b\n",
        encoding="utf-8",
    )
    result = env.reconcile_env_file()
    contents = env_file.read_text(encoding="utf-8")

    assert "A=myvalue # comment a\n" in contents
    assert "B=default_b # comment b\n" in contents
    assert "# section\n" in contents
    assert result["imported"] == ["B"]
    assert result["preserved_unknown"] == []
    assert result["backup"] is not None
    assert (env_file.parent / result["backup"]).exists()


def test_reconcile_preserves_unknown_keys(env_paths):
    env_file, example_file = env_paths
    env_file.write_text("A=1\nCUSTOM_KEY=keepme\n", encoding="utf-8")
    example_file.write_text("A=default\n", encoding="utf-8")
    result = env.reconcile_env_file()
    contents = env_file.read_text(encoding="utf-8")
    assert "CUSTOM_KEY=keepme" in contents
    assert env._PRESERVED_HEADER in contents
    assert result["preserved_unknown"] == ["CUSTOM_KEY"]


def test_reconcile_follows_example_order(env_paths):
    env_file, example_file = env_paths
    env_file.write_text("B=2\nA=1\n", encoding="utf-8")
    example_file.write_text("A=x\nB=y\n", encoding="utf-8")
    env.reconcile_env_file()
    lines = [ln for ln in env_file.read_text(encoding="utf-8").splitlines() if "=" in ln]
    assert lines == ["A=1", "B=2"]


def test_reconcile_backs_up_before_writing(env_paths):
    env_file, example_file = env_paths
    env_file.write_text("A=original\n", encoding="utf-8")
    example_file.write_text("A=default\nB=new\n", encoding="utf-8")
    result = env.reconcile_env_file()
    assert result["backup"].startswith("runtime/backups/")
    backup = env_file.parent / result["backup"]
    assert backup.read_text(encoding="utf-8") == "A=original\n"


def test_reconcile_writes_in_place_without_temp_file(env_paths):
    env_file, example_file = env_paths
    env_file.write_text("A=keep\n", encoding="utf-8")
    example_file.write_text("A=default\nB=new\n", encoding="utf-8")
    env.reconcile_env_file()
    assert not (env_file.parent / (env_file.name + ".tmp")).exists()


def test_reconcile_backup_falls_back_when_runtime_unwritable(env_paths, monkeypatch, tmp_path):
    env_file, example_file = env_paths
    env_file.write_text("A=original\n", encoding="utf-8")
    example_file.write_text("A=default\nB=new\n", encoding="utf-8")

    runtime = tmp_path / "runtime"
    real_copy = env.shutil.copy2

    def fake_copy(src, dst, *args, **kwargs):
        if runtime in dst.parents:
            raise PermissionError("read-only directory")
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(env.shutil, "copy2", fake_copy)

    result = env.reconcile_env_file()
    assert result["backup"] is not None
    backup = env_file.parent / result["backup"].split("/")[-1]
    assert backup.read_text(encoding="utf-8") == "A=original\n"
    assert "B=new" in env_file.read_text(encoding="utf-8")


def test_reconcile_missing_example_raises(env_paths):
    env_file, _example_file = env_paths
    env_file.write_text("A=1\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        env.reconcile_env_file()


def test_example_download_info_shape():
    info = env.example_download_info()
    assert "raw_url" in info
    assert info["raw_url"].startswith("https://raw.githubusercontent.com/")
    assert info["blob_url"].startswith("https://github.com/")
    assert "ref" in info
