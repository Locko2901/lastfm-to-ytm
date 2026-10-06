"""Signed Last.fm API client: web auth, scrobbling and recent tracks with now playing.

Write calls (``auth.getToken``, ``auth.getSession``, ``track.scrobble``) are
signed with the API secret as described at https://www.last.fm/api/authspec.
Every request goes through an injectable transport so tests never reach the
network.
"""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode

import requests

from .fetch import LASTFM_API_URL, as_list, field_text, parse_tracks
from .scrobble import Scrobble

log = logging.getLogger(__name__)

AUTH_PAGE_URL = "https://www.last.fm/api/auth/"
SCROBBLE_BATCH_SIZE = 50
RECENT_PAGE_SIZE = 200
RECENT_MAX_PAGES = 25
RETRYABLE_ERROR_CODES = frozenset({8, 11, 16, 29})
NOT_PROCESSED_ERROR_CODES = frozenset({11, 16, 29})
INVALID_SESSION_CODE = 9
TOKEN_NOT_AUTHORIZED_CODE = 14
MIN_CALL_INTERVAL_SECONDS = 0.25
MAX_BACKOFF_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 30
_UNSIGNED_PARAMS = frozenset({"format", "callback"})


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """The parts of an HTTP response the client looks at."""

    status: int
    payload: dict[str, Any] | None
    retry_after: int | None = None


Transport = Callable[[str, Mapping[str, str]], HttpResponse]


class HttpSender(Protocol):
    """What a transport sends through: a ``requests.Session``, or the ``requests`` module itself."""

    def get(self, url: str, *, params: Mapping[str, str], timeout: float) -> requests.Response:
        """Send a GET request."""

    def post(self, url: str, *, data: Mapping[str, str], timeout: float) -> requests.Response:
        """Send a POST request."""


def session_transport(session: HttpSender) -> Transport:
    """Return a transport that sends through ``session`` (e.g. an IPv4-only one)."""

    def send(http_method: str, params: Mapping[str, str]) -> HttpResponse:
        if http_method == "POST":
            resp = session.post(LASTFM_API_URL, data=dict(params), timeout=HTTP_TIMEOUT_SECONDS)
        else:
            resp = session.get(LASTFM_API_URL, params=dict(params), timeout=HTTP_TIMEOUT_SECONDS)
        return _to_http_response(resp)

    return send


requests_transport = session_transport(requests)


def _to_http_response(resp: requests.Response) -> HttpResponse:
    """Keep the status, JSON body and Retry-After of a ``requests`` response."""
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    retry_after_raw = resp.headers.get("Retry-After", "")
    retry_after = int(retry_after_raw) if retry_after_raw.isdigit() else None
    return HttpResponse(resp.status_code, payload if isinstance(payload, dict) else None, retry_after)


class LastfmError(Exception):
    """A Last.fm call that failed for good (bad request, rejected parameters)."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class LastfmUnavailable(LastfmError):
    """Last.fm could not be reached or stayed unavailable after every retry."""


class LastfmTooManyScrobbles(LastfmError):
    """The time range holds more recent scrobbles than the page cap allows reading."""


class LastfmAuthError(LastfmError):
    """The session key was rejected: the user revoked it or it is invalid."""


class LastfmTokenPending(LastfmError):
    """The auth token exists but the user has not approved it on Last.fm yet."""


@dataclass(frozen=True, slots=True)
class NowPlaying:
    """The track Last.fm currently shows as now playing for the user."""

    artist: str
    track: str
    album: str


@dataclass(frozen=True, slots=True)
class ScrobbleEntry:
    """One play to submit with ``track.scrobble``."""

    artist: str
    track: str
    timestamp: int
    album: str = ""
    duration: int | None = None


@dataclass(frozen=True, slots=True)
class ScrobbleOutcome:
    """What Last.fm did with one submitted play."""

    accepted: bool
    ignored_code: int
    ignored_message: str
    artist: str
    track: str


def api_signature(params: Mapping[str, str], secret: str) -> str:
    """Return the ``api_sig`` for a call: md5 of the sorted ``<name><value>`` pairs plus the secret."""
    raw = "".join(f"{name}{params[name]}" for name in sorted(params) if name not in _UNSIGNED_PARAMS)
    return hashlib.md5((raw + secret).encode("utf-8"), usedforsecurity=False).hexdigest()


def _error_code(payload: Mapping[str, Any]) -> int | None:
    """Return the Last.fm ``error`` code of a response, or None for a success."""
    code = payload.get("error")
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if isinstance(code, str) and code.isdigit():
        return int(code)
    return None


def parse_scrobble_response(payload: Mapping[str, Any], count: int) -> list[ScrobbleOutcome]:
    """Turn a ``track.scrobble`` response into one outcome per submitted play."""
    items = as_list(payload.get("scrobbles", {}).get("scrobble"))
    if len(items) != count:
        raise LastfmError(f"Last.fm answered {len(items)} results for {count} scrobbles")
    outcomes: list[ScrobbleOutcome] = []
    for item in items:
        ignored = item.get("ignoredMessage") or {}
        try:
            code = int(ignored.get("code", 0) or 0)
        except (TypeError, ValueError):
            code = 0
        outcomes.append(
            ScrobbleOutcome(
                accepted=code == 0,
                ignored_code=code,
                ignored_message=field_text(ignored),
                artist=field_text(item.get("artist")),
                track=field_text(item.get("track")),
            )
        )
    return outcomes


class LastfmClient:
    """Last.fm API calls the history scrobbler needs, with retries and pacing."""

    def __init__(
        self,
        api_key: str,
        api_secret: str = "",
        session_key: str = "",
        *,
        max_retries: int = 5,
        transport: Transport = requests_transport,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session_key = session_key
        self.max_retries = max(1, max_retries)
        self._transport = transport
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    def _pace(self) -> None:
        """Keep at least ``MIN_CALL_INTERVAL_SECONDS`` between calls (Last.fm allows 5 per second)."""
        now = self._clock()
        if self._last_call is not None:
            wait = MIN_CALL_INTERVAL_SECONDS - (now - self._last_call)
            if wait > 0:
                self._sleep(wait)
        self._last_call = self._clock()

    def _call(self, method: str, params: Mapping[str, str], *, signed: bool, http_method: str = "GET", idempotent: bool = True) -> dict[str, Any]:
        """Call ``method``, retrying transient failures with exponential backoff.

        A call that is not ``idempotent`` is only retried when Last.fm said it did
        not process it (HTTP 429, errors 11, 16, 29, or no connection at all). Any
        other failure may have been processed, so it is raised at once as
        ``LastfmUnavailable`` instead of being sent again.
        """
        full: dict[str, str] = {"method": method, "api_key": self.api_key, **params}
        if signed:
            if not self.api_secret:
                raise LastfmError("LASTFM_API_SECRET is not set")
            full["api_sig"] = api_signature(full, self.api_secret)
        full["format"] = "json"

        delay = 1.0
        last_problem = ""
        for attempt in range(1, self.max_retries + 1):
            self._pace()
            retry_after: int | None = None
            unprocessed = False
            try:
                resp = self._transport(http_method, full)
            except requests.RequestException as e:
                last_problem = f"network error: {e}"
                unprocessed = isinstance(e, requests.ConnectTimeout)
            else:
                payload = resp.payload or {}
                code = _error_code(payload)
                message = str(payload.get("message") or "")
                retry_after = resp.retry_after
                if code == INVALID_SESSION_CODE:
                    raise LastfmAuthError(message or "Invalid session key", code)
                if code == TOKEN_NOT_AUTHORIZED_CODE:
                    raise LastfmTokenPending(message or "Token not authorised yet", code)
                if resp.status == 429 or resp.status >= 500 or code in RETRYABLE_ERROR_CODES:
                    last_problem = f"HTTP {resp.status}" + (f", error {code}: {message}" if code else "")
                    unprocessed = resp.status == 429 or code in NOT_PROCESSED_ERROR_CODES
                elif code is not None:
                    raise LastfmError(f"Last.fm error {code}: {message}", code)
                elif resp.status >= 400:
                    raise LastfmError(f"Last.fm returned HTTP {resp.status}")
                elif resp.payload is None:
                    last_problem = "unreadable response"
                else:
                    return resp.payload
            if not idempotent and not unprocessed:
                raise LastfmUnavailable(f"Last.fm {method} got no clear answer ({last_problem}); not sent again")
            if attempt < self.max_retries:
                wait = min(MAX_BACKOFF_SECONDS, max(delay, float(retry_after or 0)))
                log.warning("Last.fm %s failed (%s), retrying in %.0fs (%d/%d)", method, last_problem, wait, attempt, self.max_retries)
                self._sleep(wait)
                delay *= 2
        raise LastfmUnavailable(f"Last.fm {method} failed after {self.max_retries} attempts: {last_problem}")

    def get_token(self) -> str:
        """Fetch a fresh, not yet approved auth token (valid for 60 minutes)."""
        data = self._call("auth.getToken", {}, signed=True)
        token = str(data.get("token") or "")
        if not token:
            raise LastfmError("Last.fm returned no token")
        return token

    def auth_url(self, token: str) -> str:
        """Return the Last.fm page where the user approves ``token``."""
        return f"{AUTH_PAGE_URL}?{urlencode({'api_key': self.api_key, 'token': token})}"

    def get_session(self, token: str) -> tuple[str, str]:
        """Exchange an approved token for ``(session_key, username)``.

        Raises ``LastfmTokenPending`` while the user has not approved the token.
        """
        data = self._call("auth.getSession", {"token": token}, signed=True)
        session = data.get("session") or {}
        key = str(session.get("key") or "")
        name = str(session.get("name") or "")
        if not key:
            raise LastfmError("Last.fm returned no session key")
        return key, name

    def now_playing(self, username: str) -> NowPlaying | None:
        """Return the user's now playing track, if Last.fm shows one."""
        data = self._call("user.getRecentTracks", {"user": username, "limit": "1"}, signed=False)
        for item in as_list(data.get("recenttracks", {}).get("track")):
            if (item.get("@attr") or {}).get("nowplaying") == "true":
                artist = field_text(item.get("artist")).strip()
                track = str(item.get("name") or "").strip()
                if artist and track:
                    return NowPlaying(artist=artist, track=track, album=field_text(item.get("album")).strip())
        return None

    def recent_scrobbles(self, username: str, from_ts: int, to_ts: int | None = None, *, max_pages: int = RECENT_MAX_PAGES) -> list[Scrobble]:
        """Return every scrobble from ``from_ts`` (to ``to_ts`` when given), newest first.

        Raises ``LastfmTooManyScrobbles`` when the range holds more than
        ``max_pages`` pages, since an incomplete list cannot rule out duplicates.
        """
        scrobbles: list[Scrobble] = []
        page = 1
        while True:
            params = {"user": username, "limit": str(RECENT_PAGE_SIZE), "page": str(page), "from": str(max(0, from_ts))}
            if to_ts is not None:
                params["to"] = str(max(0, to_ts))
            data = self._call("user.getRecentTracks", params, signed=False)
            recent = data.get("recenttracks") or {}
            tracks = as_list(recent.get("track"))
            scrobbles.extend(parse_tracks(tracks))
            try:
                total_pages = int((recent.get("@attr") or {}).get("totalPages", "0") or "0")
            except (TypeError, ValueError):
                total_pages = 0
            if not tracks or page >= total_pages:
                return scrobbles
            if page >= max_pages:
                raise LastfmTooManyScrobbles(f"More than {max_pages} pages of recent scrobbles to check")
            page += 1

    def scrobble_batch(self, entries: Sequence[ScrobbleEntry]) -> list[ScrobbleOutcome]:
        """Submit up to 50 plays in one ``track.scrobble`` call."""
        if not entries:
            return []
        if len(entries) > SCROBBLE_BATCH_SIZE:
            raise ValueError(f"track.scrobble takes at most {SCROBBLE_BATCH_SIZE} plays per call")
        if not self.session_key:
            raise LastfmAuthError("Not connected to Last.fm: no session key")
        params: dict[str, str] = {"sk": self.session_key}
        for i, entry in enumerate(entries):
            params[f"artist[{i}]"] = entry.artist
            params[f"track[{i}]"] = entry.track
            params[f"timestamp[{i}]"] = str(int(entry.timestamp))
            if entry.album:
                params[f"album[{i}]"] = entry.album
            if entry.duration:
                params[f"duration[{i}]"] = str(int(entry.duration))
        data = self._call("track.scrobble", params, signed=True, http_method="POST", idempotent=False)
        return parse_scrobble_response(data, len(entries))


def iter_batches(items: Sequence[Any], size: int = SCROBBLE_BATCH_SIZE) -> list[Sequence[Any]]:
    """Split ``items`` into consecutive chunks of at most ``size``."""
    return [items[i : i + size] for i in range(0, len(items), size)]
