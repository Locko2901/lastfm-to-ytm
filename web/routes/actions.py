"""Form action routes (blacklist, override, cache management)."""

from __future__ import annotations

import re

from flask import Blueprint, jsonify, redirect, request, url_for
from flask_babel import gettext as _

from ..services import load_overrides, load_search_cache

actions_bp = Blueprint("actions", __name__)

VIDEO_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{11}$")


def extract_video_id(url_or_id: str) -> str | None:
    """Extract and validate YouTube video ID from URL or direct ID.

    Returns the video ID if valid, None otherwise.
    """
    url_or_id = url_or_id.strip()
    if not url_or_id:
        return None

    patterns = [
        r"[?&]v=([a-zA-Z0-9_-]{11})",  # youtube.com/watch?v=...
        r"youtu\.be/([a-zA-Z0-9_-]{11})",  # youtu.be/...
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",  # youtube.com/embed/...
        r"music\.youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",  # music.youtube.com
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    if VIDEO_ID_PATTERN.match(url_or_id):
        return url_or_id

    return None


@actions_bp.route("/blacklist", methods=["POST"])
def blacklist():
    """Add a track to the blacklist."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")
    reason = request.form.get("reason", "Blacklisted via web dashboard")

    if artist and title:
        overrides = load_overrides()
        overrides.blacklist(artist, title, reason)

    redirect_tab = request.form.get("redirect_tab", "playlist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/unblacklist", methods=["POST"])
def unblacklist():
    """Remove a track from the blacklist."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        overrides = load_overrides()
        overrides.remove_blacklist(artist, title)

    redirect_tab = request.form.get("redirect_tab", "blacklist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/override", methods=["POST"])
def override():
    """Add a manual override for a track."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")
    video_id_input = request.form.get("video_id", "")
    reason = request.form.get("reason", "Override via web dashboard")

    video_id = extract_video_id(video_id_input)

    if not video_id:
        return jsonify({"error": _("Invalid video ID. Must be 11 characters (or a valid YouTube URL).")}), 400

    if not artist or not title:
        return jsonify({"error": _("Artist and title are required.")}), 400

    overrides = load_overrides()
    overrides.set(artist, title, video_id, reason)

    redirect_tab = request.form.get("redirect_tab", "playlist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/remove_override", methods=["POST"])
def remove_override():
    """Remove a manual override."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        overrides = load_overrides()
        overrides.remove(artist, title)

    redirect_tab = request.form.get("redirect_tab", "overrides")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/clear_cache_entry", methods=["POST"])
def clear_cache_entry():
    """Clear a specific cache entry."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        cache = load_search_cache()
        cache.delete_by_track(artist, title)

    redirect_tab = request.form.get("redirect_tab", "playlist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")
