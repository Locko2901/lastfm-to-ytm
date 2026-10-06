"""API routes for the history scrobbler: status, decision log, polling and Last.fm authorisation."""

from __future__ import annotations

import logging
from dataclasses import asdict

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from src.lastfm.client import LastfmError, LastfmTokenPending
from src.scrobbler.store import ALL_STATUSES, FAILED, OPEN_STATUSES, SCROBBLED, SKIPPED, WOULD_SCROBBLE

from ..services import scrobbler as service
from ..services.data import load_settings
from ..services.env import update_env_file
from ..services.scheduler import scrobbler_next_poll

scrobbler_bp = Blueprint("scrobbler", __name__, url_prefix="/api/scrobbler")

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 200
STATUS_GROUPS = {
    "done": [SCROBBLED, WOULD_SCROBBLE],
    "skipped": [SKIPPED],
    "open": list(OPEN_STATUSES),
    "failed": [FAILED],
}


@scrobbler_bp.route("/status")
def status() -> ResponseReturnValue:
    """Settings, connection, last poll and the last 24 hours of decisions."""
    return jsonify(service.get_status(load_settings(), scrobbler_next_poll()))


@scrobbler_bp.route("/plays")
def plays() -> ResponseReturnValue:
    """Decision log, newest first. ``status`` filters by a status or a group (done, skipped, open, failed)."""
    settings = load_settings()
    if settings is None:
        return jsonify({"plays": [], "total": 0})
    wanted = request.args.get("status", "").strip()
    statuses = STATUS_GROUPS.get(wanted) or ([wanted] if wanted in ALL_STATUSES else None)
    try:
        limit = max(1, min(MAX_PAGE_SIZE, int(request.args.get("limit", 50))))
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        return jsonify({"error": _("Invalid paging parameters")}), 400
    rows, total = service.get_store(settings).list_plays(statuses=statuses, limit=limit, offset=offset)
    return jsonify({"plays": rows, "total": total})


@scrobbler_bp.route("/polls")
def polls() -> ResponseReturnValue:
    """The latest polls, newest first."""
    settings = load_settings()
    if settings is None:
        return jsonify({"polls": []})
    try:
        limit = max(1, min(MAX_PAGE_SIZE, int(request.args.get("limit", 20))))
    except ValueError:
        limit = 20
    return jsonify({"polls": service.get_store(settings).recent_polls(limit)})


@scrobbler_bp.route("/poll", methods=["POST"])
def poll() -> ResponseReturnValue:
    """Run a poll right away."""
    settings = load_settings()
    if settings is None or not settings.scrobbler_enabled:
        return jsonify({"error": _("The history scrobbler is disabled. Enable it in Settings first.")}), 400
    if service.is_polling():
        return jsonify({"error": _("A poll is already running.")}), 409
    outcome = service.poll_now(settings)
    if outcome is None:
        return jsonify({"error": _("A poll is already running.")}), 409
    return jsonify(asdict(outcome))


@scrobbler_bp.route("/reset", methods=["POST"])
def reset() -> ResponseReturnValue:
    """Forget the snapshot and every decision; the next poll starts a new baseline."""
    settings = load_settings()
    if settings is None:
        return jsonify({"error": _("Last.fm credentials are not configured")}), 400
    if not service.clear_store(settings):
        return jsonify({"error": _("A poll is already running.")}), 409
    return jsonify({"status": "cleared"})


@scrobbler_bp.route("/dry-run-plays")
def dry_run_plays() -> ResponseReturnValue:
    """Plays the dry run recorded as "would scrobble" that were never offered for sending."""
    settings = load_settings()
    if settings is None:
        return jsonify({"eligible": 0, "too_old": 0})
    return jsonify(service.dry_run_offer(settings))


@scrobbler_bp.route("/dry-run-plays", methods=["POST"])
def dry_run_plays_choice() -> ResponseReturnValue:
    """Answer the offer made when the dry run is turned off: send those plays (``send: true``) or keep them."""
    data = request.get_json(silent=True) or {}
    send = data.get("send") is True
    settings = load_settings()
    if settings is None:
        return jsonify({"error": _("Last.fm credentials are not configured")}), 400
    if send and (settings.scrobbler_dry_run or not settings.scrobbler_enabled):
        return jsonify({"error": _("Turn the dry run off before sending its plays.")}), 400
    result = service.record_dry_run_choice(settings, send)
    if result is None:
        return jsonify({"error": _("A poll is already running.")}), 409
    return jsonify(result)


@scrobbler_bp.route("/auth/start", methods=["POST"])
def auth_start() -> ResponseReturnValue:
    """Start the Last.fm authorisation: save the API secret if given, fetch a token, return the approval URL."""
    data = request.get_json(silent=True) or {}
    secret = str(data.get("api_secret") or "").strip()
    if secret:
        try:
            update_env_file({"LASTFM_API_SECRET": secret})
        except OSError as e:
            logger.error(f"Failed to save the Last.fm API secret: {e}")
            return jsonify({"error": _("Failed to save credentials")}), 500
    settings = load_settings(fresh=True)
    if settings is None:
        return jsonify({"error": _("Save your Last.fm username and API key first.")}), 400
    if not settings.lastfm_api_secret:
        return jsonify({"error": _("Enter the API secret of your Last.fm API account first.")}), 400
    client = service.build_client(settings)
    try:
        token = client.get_token()
    except LastfmError as e:
        logger.warning("Last.fm auth.getToken failed: %s", e)
        return jsonify({"error": _("Last.fm refused the request: %(error)s", error=str(e))}), 502
    return jsonify({"token": token, "auth_url": client.auth_url(token)})


@scrobbler_bp.route("/auth/finish", methods=["POST"])
def auth_finish() -> ResponseReturnValue:
    """Exchange an approved token for a session key and store it in ``.env``."""
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or "").strip()
    if not token:
        return jsonify({"error": _("No token provided")}), 400
    settings = load_settings()
    if settings is None or not settings.lastfm_api_secret:
        return jsonify({"error": _("Enter the API secret of your Last.fm API account first.")}), 400
    try:
        session_key, name = service.build_client(settings).get_session(token)
    except LastfmTokenPending:
        return jsonify({"status": "pending"}), 202
    except LastfmError as e:
        logger.warning("Last.fm auth.getSession failed: %s", e)
        return jsonify({"error": _("Last.fm refused the request: %(error)s", error=str(e))}), 502
    if name and name.casefold() != settings.lastfm_user.casefold():
        return jsonify(
            {
                "error": _(
                    "You approved access as %(name)s, but the Last.fm username in Settings is %(user)s. Connect again as %(user)s.",
                    name=name,
                    user=settings.lastfm_user,
                )
            }
        ), 400
    try:
        update_env_file({"LASTFM_SESSION_KEY": session_key, "LASTFM_SESSION_USER": name or settings.lastfm_user})
    except OSError as e:
        logger.error(f"Failed to save the Last.fm session key: {e}")
        return jsonify({"error": _("Failed to save credentials")}), 500
    return jsonify({"status": "connected", "user": name or settings.lastfm_user})


@scrobbler_bp.route("/auth/disconnect", methods=["POST"])
def auth_disconnect() -> ResponseReturnValue:
    """Forget the session key (revoke it on Last.fm too, under Settings, Applications)."""
    try:
        update_env_file({"LASTFM_SESSION_KEY": "", "LASTFM_SESSION_USER": ""})
    except OSError as e:
        logger.error(f"Failed to remove the Last.fm session key: {e}")
        return jsonify({"error": _("Failed to save credentials")}), 500
    return jsonify({"status": "disconnected"})
