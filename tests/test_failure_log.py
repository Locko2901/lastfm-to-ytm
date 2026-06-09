"""Tests for persistent failure / run-log files consumed by the web dashboard."""

from __future__ import annotations

import json

import pytest

from src.observability import failure_log
from src.observability.failure_log import (
    clear_failure_log,
    save_failure_log,
    save_run_log,
)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(failure_log, "CACHE_DIR", tmp_path)
    return tmp_path


def test_save_run_log_writes_mappings(cache_dir):
    mappings = [{"artist": "A", "title": "B", "source": "search"}]
    save_run_log(mappings)

    data = json.loads((cache_dir / ".last_run_log.json").read_text())
    assert data["total"] == 1
    assert data["mappings"] == mappings
    assert "timestamp" in data


def test_save_failure_log_basic_fields(cache_dir):
    save_failure_log("something broke", "Traceback ...", sync_type="weekly")

    data = json.loads((cache_dir / ".last_failure.json").read_text())
    assert data["error"] == "something broke"
    assert data["traceback"] == "Traceback ..."
    assert data["sync_type"] == "weekly"
    assert data["hint"] is None


@pytest.mark.parametrize(
    ("message", "needle"),
    [
        ("HTTP 401 Unauthorized", "Authentication expired"),
        ("got unauthorized response", "Authentication expired"),
        ("HTTP 429 Too Many Requests", "Rate limited"),
        ("rate limit exceeded", "Rate limited"),
        ("HTTP 403 Forbidden", "Access denied"),
        ("forbidden by server", "Access denied"),
    ],
)
def test_save_failure_log_hint_mapping(cache_dir, message, needle):
    save_failure_log(message)
    data = json.loads((cache_dir / ".last_failure.json").read_text())
    assert data["hint"] is not None
    assert needle in data["hint"]


def test_clear_failure_log_removes_file(cache_dir):
    save_failure_log("boom")
    assert (cache_dir / ".last_failure.json").exists()
    clear_failure_log()
    assert not (cache_dir / ".last_failure.json").exists()


def test_clear_failure_log_noop_when_absent(cache_dir):
    clear_failure_log()
    assert not (cache_dir / ".last_failure.json").exists()
