import logging

import pytest

from src.playlist import sync
from src.ytm import retry_with_backoff


def test_the_sync_uses_the_shared_retry():
    assert sync._retry_with_backoff is retry_with_backoff


def test_unauthorized_is_not_retried(monkeypatch):
    monkeypatch.setattr("src.ytm.retry.time.sleep", lambda _s: None)
    calls = []

    def expired():
        calls.append(1)
        raise RuntimeError("Server returned HTTP 401: Unauthorized")

    with pytest.raises(RuntimeError):
        retry_with_backoff(expired, max_retries=3, operation="x")
    assert len(calls) == 1


def test_a_conflict_fails_at_once_and_a_rate_limit_backs_off(monkeypatch, caplog):
    sleeps = []
    monkeypatch.setattr("src.ytm.retry.time.sleep", sleeps.append)

    def conflict():
        raise RuntimeError("Server returned HTTP 409: Conflict")

    with pytest.raises(RuntimeError):
        retry_with_backoff(conflict, max_retries=3, operation="x")
    assert sleeps == []

    def limited():
        raise RuntimeError("Server returned HTTP 429: Too Many Requests")

    with caplog.at_level(logging.WARNING), pytest.raises(RuntimeError):
        retry_with_backoff(limited, max_retries=3, initial_delay=1.0, operation="get_history")
    assert sleeps == [1.0, 2.0]
    assert "get_history: HTTP 429 (retry 1/2 in 1.0s)" in caplog.text
