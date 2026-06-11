"""REST endpoints for server-backed notifications.

Live updates are delivered via the unified ``/api/events`` SSE stream
(see :mod:`web.routes.events`); this blueprint only exposes CRUD.
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ..services import notifications as store

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")

logger = logging.getLogger(__name__)


@notifications_bp.route("", methods=["GET"])
def list_notifications() -> ResponseReturnValue:
    """Return the current notification list and ``last_seen_at`` marker."""
    return jsonify(store.list_all())


@notifications_bp.route("", methods=["POST"])
def create_notification() -> ResponseReturnValue:
    """Create a notification (also called by the frontend ``pushNotification``)."""
    payload = request.get_json(silent=True) or {}
    message = payload.get("message")
    if not message or not isinstance(message, str):
        return jsonify({"error": _("Message is required")}), 400
    type_ = payload.get("type", "info")
    source = payload.get("source")
    try:
        entry = store.add(message, type_=type_, source=source if isinstance(source, str) else None)
    except ValueError:
        return jsonify({"error": _("Invalid notification data")}), 400
    return jsonify(entry), 201


@notifications_bp.route("/clear", methods=["POST"])
def clear_notifications() -> ResponseReturnValue:
    """Delete every stored notification."""
    store.clear()
    return jsonify({"status": "ok"})


@notifications_bp.route("/read", methods=["POST"])
def mark_read() -> ResponseReturnValue:
    """Mark all notifications as read (updates ``last_seen_at``)."""
    return jsonify({"last_seen_at": store.mark_read()})


@notifications_bp.route("/<notification_id>", methods=["DELETE"])
def delete_notification(notification_id: str) -> ResponseReturnValue:
    """Delete one notification by id."""
    if not store.delete(notification_id):
        return jsonify({"error": _("Notification not found")}), 404
    return jsonify({"status": "ok"})
