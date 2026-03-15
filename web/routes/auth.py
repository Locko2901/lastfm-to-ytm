"""Authentication routes for YouTube Music."""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request
from flask_babel import gettext as _

from ..services import BROWSER_JSON_FILE

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

logger = logging.getLogger(__name__)


@auth_bp.route("/submit", methods=["POST"])
def submit():
    """Parse raw browser headers and write browser.json directly.

    Accepts { "headers_raw": "..." } with pasted request headers or cURL.
    Returns success/failure with optional verification via YTMusic API.
    """
    data = request.get_json()
    if not data or not data.get("headers_raw", "").strip():
        return jsonify({"success": False, "error": _("No headers provided")}), 400

    headers_raw = data["headers_raw"].strip()

    try:
        from ytmusicapi.setup import setup_browser

        setup_browser(filepath=str(BROWSER_JSON_FILE), headers_raw=headers_raw)
    except Exception as e:
        error_msg = str(e)
        if "missing" in error_msg.lower():
            return jsonify(
                {
                    "success": False,
                    "error": _("Missing required headers (cookie, x-goog-authuser). Make sure you copy from a /browse request while logged in."),
                }
            ), 400
        logger.exception("Failed to parse auth headers")
        return jsonify({"success": False, "error": _("Failed to parse headers: %(error_msg)s", error_msg=error_msg)}), 400

    _has_content, valid, error = _validate_browser_json()
    if not valid:
        return jsonify({"success": False, "error": error or "Auth file validation failed"}), 400

    try:
        from ytmusicapi import YTMusic

        yt = YTMusic(str(BROWSER_JSON_FILE))
        liked = yt.get_liked_songs(limit=1)
        tracks = liked.get("tracks", [])
        if tracks:
            track = tracks[0]
            song_info = f"{track.get('title', 'Unknown')} by {track.get('artists', [{}])[0].get('name', 'Unknown')}"
            return jsonify({"success": True, "verified": True, "lastLiked": song_info})
        return jsonify({"success": True, "verified": True, "lastLiked": None})
    except Exception as e:
        error_str = str(e)
        if "Sign in" in error_str or "singleColumnBrowseResultsRenderer" in error_str:
            return jsonify(
                {
                    "success": False,
                    "error": _("Headers were saved but auth appears expired. Try copying fresh headers."),
                }
            ), 400
        logger.warning("Auth live-test failed (file still saved): %s", e)
        return jsonify({"success": True, "verified": False})


def _validate_browser_json() -> tuple[bool, bool, str | None]:
    """Validate browser.json exists and has valid auth cookies.

    Returns:
        Tuple of (has_content, valid, error_message).
    """
    if not BROWSER_JSON_FILE.exists():
        return False, False, _("browser.json not found")
    if BROWSER_JSON_FILE.stat().st_size <= 3:
        return False, False, _("browser.json is empty")
    try:
        with BROWSER_JSON_FILE.open() as f:
            data = json.load(f)
        if "cookie" not in data:
            return True, False, _("Missing cookie in auth file")
        cookie = data.get("cookie", "")
        if "SAPISID" not in cookie and "SID" not in cookie:
            return True, False, _("Auth cookie appears invalid")
        return True, True, None
    except json.JSONDecodeError:
        return True, False, _("Invalid JSON in auth file")
    except OSError:
        return False, False, _("Cannot read auth file")


@auth_bp.route("/status")
def status():
    """Get browser.json validity."""
    browser_has_content, valid, _ = _validate_browser_json()
    return jsonify(
        {
            "browser_json_exists": browser_has_content,
            "valid": valid,
        }
    )


@auth_bp.route("/validate")
def validate():
    """Quick check that browser.json exists and has valid structure."""
    has_content, valid, error = _validate_browser_json()
    if valid:
        return jsonify({"valid": True, "configured": True})
    return jsonify({"valid": False, "configured": has_content, "error": error})


@auth_bp.route("/test")
def test():
    """Actually test the auth by fetching the user's last liked song."""
    if not BROWSER_JSON_FILE.exists():
        return jsonify({"valid": False, "error": _("browser.json not found")})

    try:
        from ytmusicapi import YTMusic

        yt = YTMusic(str(BROWSER_JSON_FILE))
        liked = yt.get_liked_songs(limit=1)
        tracks = liked.get("tracks", [])
        if tracks:
            track = tracks[0]
            song_info = f"{track.get('title', 'Unknown')} by {track.get('artists', [{}])[0].get('name', 'Unknown')}"
            return jsonify({"valid": True, "lastLiked": song_info})
        return jsonify({"valid": True, "lastLiked": None})
    except Exception as e:
        error_str = str(e)
        if "Sign in" in error_str or "singleColumnBrowseResultsRenderer" in error_str:
            return jsonify({"valid": False, "error": _("Auth expired - please regenerate"), "expired": True})
        logger.exception("Auth test failed")
        return jsonify({"valid": False, "error": _("Auth test failed")})
