"""Tests for webhook dispatch and the SSRF URL guard."""

import socket

import pytest

import src.webhook as webhook_mod
from src.webhook import _is_discord, _is_safe_webhook_url, send_webhook


def _fake_getaddrinfo(ip: str):
    """Return a getaddrinfo stub that always resolves to ``ip``."""

    def _inner(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]

    return _inner


def test_is_discord_matches_discord_hosts():
    assert _is_discord("https://discord.com/api/webhooks/123/abc")
    assert _is_discord("https://discordapp.com/api/webhooks/123/abc")
    assert not _is_discord("https://ntfy.sh/topic")


def test_safe_url_public_host_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    assert _is_safe_webhook_url("https://ntfy.sh/topic") is True


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.1.1", "::1", "0.0.0.0"],
)
def test_safe_url_rejects_private_and_loopback(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo(ip))
    assert _is_safe_webhook_url("http://internal.example") is False


def test_safe_url_rejects_non_http_scheme():
    assert _is_safe_webhook_url("file:///etc/passwd") is False
    assert _is_safe_webhook_url("gopher://example.com/") is False


def test_safe_url_rejects_missing_host():
    assert _is_safe_webhook_url("http://") is False


def test_safe_url_rejects_dns_failure(monkeypatch):
    def _boom(*args, **kwargs):
        raise socket.gaierror("name resolution failed")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    assert _is_safe_webhook_url("https://does-not-resolve.invalid") is False


def test_allow_private_bypasses_ip_check(monkeypatch):
    # getaddrinfo must not even be called when allow_private is set.
    def _should_not_call(*args, **kwargs):
        raise AssertionError("getaddrinfo should not be called when allow_private=True")

    monkeypatch.setattr(socket, "getaddrinfo", _should_not_call)
    assert _is_safe_webhook_url("http://192.168.1.50/hook", allow_private=True) is True


def test_allow_private_still_requires_http_scheme():
    assert _is_safe_webhook_url("ftp://192.168.1.50/hook", allow_private=True) is False


def test_send_webhook_empty_url_returns_false():
    assert send_webhook("", status="test") is False


def test_send_webhook_rejects_unsafe_url_without_posting(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("127.0.0.1"))

    def _should_not_post(*args, **kwargs):
        raise AssertionError("requests.post should not run for an unsafe URL")

    monkeypatch.setattr(webhook_mod.requests, "post", _should_not_post)
    assert send_webhook("http://localhost/hook", status="error") is False


def test_send_webhook_posts_for_safe_url(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo("93.184.216.34"))
    captured = {}

    class _Resp:
        status_code = 204

        def raise_for_status(self):
            return None

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(webhook_mod.requests, "post", _fake_post)
    ok = send_webhook("https://ntfy.sh/topic", status="success", tracks_resolved=5)
    assert ok is True
    assert captured["url"] == "https://ntfy.sh/topic"
    assert captured["json"]["status"] == "success"


def test_send_webhook_allow_private_posts_to_lan(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

    def _fake_post(url, json=None, timeout=None):
        captured["url"] = url
        return _Resp()

    monkeypatch.setattr(webhook_mod.requests, "post", _fake_post)
    ok = send_webhook("http://192.168.1.50/hook", status="test", allow_private=True)
    assert ok is True
    assert captured["url"] == "http://192.168.1.50/hook"
