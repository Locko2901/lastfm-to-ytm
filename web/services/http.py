"""Shared HTTP sessions of the dashboard."""

from __future__ import annotations

import socket
import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter


class IPv4Adapter(HTTPAdapter):
    """HTTP adapter that forces IPv4 connections."""

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        """Initialize pool with IPv4-only options."""
        kwargs["socket_options"] = [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]
        import urllib3.util.connection

        _orig_allowed = urllib3.util.connection.allowed_gai_family
        urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
        super().init_poolmanager(*args, **kwargs)
        urllib3.util.connection.allowed_gai_family = _orig_allowed


def get_ipv4_session() -> requests.Session:
    """Create IPv4-only session."""
    session = requests.Session()
    session.mount("http://", IPv4Adapter())
    session.mount("https://", IPv4Adapter())
    return session


_ipv4_session: requests.Session | None = None
_ipv4_session_lock = threading.Lock()


def ipv4_session() -> requests.Session:
    """Get shared IPv4-only session."""
    global _ipv4_session
    if _ipv4_session is None:
        with _ipv4_session_lock:
            if _ipv4_session is None:
                _ipv4_session = get_ipv4_session()
    return _ipv4_session
