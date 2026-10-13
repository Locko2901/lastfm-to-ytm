"""Teleporter restore of files Docker bind-mounts one at a time.

``.env`` and ``browser.json`` are single-file bind mounts in Docker, where a
rename onto them fails with EBUSY. The restore must rewrite them in place
instead of skipping them.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

pytest.importorskip("argon2")
pytest.importorskip("cryptography")

from web.services import teleporter

_PASSWORD = "correct horse battery"


@pytest.fixture
def config_files(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    browser = tmp_path / "browser.json"
    monkeypatch.setattr(teleporter, "_CONFIG_FILES", [("env", env), ("browser_json", browser)])
    monkeypatch.setattr(teleporter, "_CACHE_FILES", {})
    env.write_text("LASTFM_USER=alice\n", encoding="utf-8")
    browser.write_text('{"cookie": "abc"}', encoding="utf-8")
    return env, browser


def _fail_rename_onto(targets, err):
    """Return a ``Path.replace`` that raises ``err`` when renaming onto ``targets``."""
    real_replace = Path.replace

    def replace(self, target):
        if Path(target) in targets:
            raise OSError(err, os.strerror(err))
        return real_replace(self, target)

    return replace


def test_restore_rewrites_bind_mounted_files_in_place(config_files, monkeypatch):
    env, browser = config_files
    blob = teleporter.export_config(_PASSWORD)
    env.write_text("LASTFM_USER=changed\n", encoding="utf-8")
    browser.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "replace", _fail_rename_onto({env, browser}, errno.EBUSY))

    result = teleporter.import_config(blob, _PASSWORD)

    assert set(result["restored"]) == {"env", "browser_json"}
    assert env.read_text(encoding="utf-8") == "LASTFM_USER=alice\n"
    assert browser.read_text(encoding="utf-8") == '{"cookie": "abc"}'
    assert not env.with_name(".env.tmp").exists()
    assert not browser.with_name("browser.json.tmp").exists()


def test_restore_skips_file_on_other_write_errors(config_files, monkeypatch):
    env, _browser = config_files
    blob = teleporter.export_config(_PASSWORD)
    env.write_text("LASTFM_USER=changed\n", encoding="utf-8")
    monkeypatch.setattr(Path, "replace", _fail_rename_onto({env}, errno.EACCES))

    result = teleporter.import_config(blob, _PASSWORD)

    assert "env" in result["skipped"]
    assert "browser_json" in result["restored"]
    assert env.read_text(encoding="utf-8") == "LASTFM_USER=changed\n"
    assert not env.with_name(".env.tmp").exists()
