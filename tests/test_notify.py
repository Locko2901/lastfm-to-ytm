"""Tests for Apprise notification dispatch and URL parsing."""

import apprise

from src.notify import parse_apprise_entries, parse_apprise_urls, send_apprise


def test_parse_apprise_urls_splits_on_mixed_separators():
    raw = "discord://a/b  ntfy://host/topic, tgram://t/1\nslack://x"
    assert parse_apprise_urls(raw) == [
        "discord://a/b",
        "ntfy://host/topic",
        "tgram://t/1",
        "slack://x",
    ]


def test_parse_apprise_urls_dedupes_preserving_order():
    assert parse_apprise_urls("a://x, b://y a://x") == ["a://x", "b://y"]


def test_parse_apprise_urls_excludes_disabled():
    assert parse_apprise_urls("a://x !b://y c://z") == ["a://x", "c://z"]


def test_parse_apprise_entries_marks_enabled_state():
    assert parse_apprise_entries("a://x !b://y") == [("a://x", True), ("b://y", False)]


def test_parse_apprise_entries_empty():
    assert parse_apprise_entries("") == []
    assert parse_apprise_entries(None) == []


def test_parse_apprise_urls_empty():
    assert parse_apprise_urls("") == []
    assert parse_apprise_urls(None) == []


def test_send_apprise_empty_urls_returns_false():
    assert send_apprise([], status="test") is False


def test_send_apprise_notifies_all_targets(monkeypatch):
    captured = {}

    class FakeApprise:
        def __init__(self):
            self.urls = []

        def add(self, url):
            self.urls.append(url)
            return True

        def notify(self, title, body, notify_type):
            captured["title"] = title
            captured["body"] = body
            captured["notify_type"] = notify_type
            captured["urls"] = list(self.urls)
            return True

    monkeypatch.setattr(apprise, "Apprise", FakeApprise)
    ok = send_apprise(
        ["ntfy://host/topic", "discord://a/b"],
        status="success",
        sync_type="main",
        tracks_resolved=5,
        tracks_missed=1,
    )
    assert ok is True
    assert captured["urls"] == ["ntfy://host/topic", "discord://a/b"]
    assert "Sync complete" in captured["title"]
    assert "Resolved: 5" in captured["body"]
    assert captured["notify_type"] == apprise.NotifyType.SUCCESS


def test_send_apprise_returns_false_when_all_urls_invalid(monkeypatch):
    class FakeApprise:
        def add(self, url):
            return False

        def notify(self, title, body, notify_type):
            raise AssertionError("notify must not run when no URLs were added")

    monkeypatch.setattr(apprise, "Apprise", FakeApprise)
    assert send_apprise(["not-a-real-scheme"], status="error") is False


def test_send_apprise_returns_false_on_delivery_failure(monkeypatch):
    class FakeApprise:
        def add(self, url):
            return True

        def notify(self, title, body, notify_type):
            return False

    monkeypatch.setattr(apprise, "Apprise", FakeApprise)
    assert send_apprise(["ntfy://host/topic"], status="error", error="boom") is False
