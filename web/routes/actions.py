"""Form action routes (blacklist, override, cache management)."""

from __future__ import annotations

import logging
import re
from typing import Any

from flask import Blueprint, jsonify, redirect, request, url_for
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ..services import history_record_action, load_overrides, load_search_cache, load_tag_cache, load_tag_overrides

actions_bp = Blueprint("actions", __name__)

logger = logging.getLogger(__name__)

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
def blacklist() -> ResponseReturnValue:
    """Add a track to the blacklist."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")
    reason = request.form.get("reason", "Blacklisted via web dashboard")

    if artist and title:
        overrides = load_overrides()
        overrides.blacklist(artist, title, reason)
        history_record_action("blacklist_add", artist, title, detail=reason)

    redirect_tab = request.form.get("redirect_tab", "playlist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/unblacklist", methods=["POST"])
def unblacklist() -> ResponseReturnValue:
    """Remove a track from the blacklist."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        overrides = load_overrides()
        overrides.remove_blacklist(artist, title)
        history_record_action("blacklist_remove", artist, title)

    redirect_tab = request.form.get("redirect_tab", "blacklist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/override", methods=["POST"])
def override() -> ResponseReturnValue:
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
    history_record_action("override_add", artist, title, video_id=video_id, detail=reason)

    redirect_tab = request.form.get("redirect_tab", "playlist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/remove_override", methods=["POST"])
def remove_override() -> ResponseReturnValue:
    """Remove a manual override."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        overrides = load_overrides()
        overrides.remove(artist, title)
        history_record_action("override_remove", artist, title)

    redirect_tab = request.form.get("redirect_tab", "overrides")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/clear_cache_entry", methods=["POST"])
def clear_cache_entry() -> ResponseReturnValue:
    """Clear a specific cache entry."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        cache = load_search_cache()
        cache.delete_by_track(artist, title)
        history_record_action("cache_clear", artist, title)

    redirect_tab = request.form.get("redirect_tab", "playlist")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/tag_override", methods=["POST"])
def tag_override() -> ResponseReturnValue:
    """Add or update a tag override for a track."""
    artist = request.form.get("artist", "").strip()
    title = request.form.get("title", "").strip()
    tags_raw = request.form.get("tags", "").strip()
    mode = request.form.get("mode", "add").strip()
    reason = request.form.get("reason", "Tag override via web dashboard")

    if not artist or not title:
        return jsonify({"error": _("Artist and title are required.")}), 400

    if not tags_raw:
        return jsonify({"error": _("At least one tag is required.")}), 400

    tags = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]
    if not tags:
        return jsonify({"error": _("At least one tag is required.")}), 400

    if mode not in ("add", "replace"):
        mode = "add"

    overrides = load_tag_overrides()
    overrides.set(artist, title, tags, mode=mode, reason=reason)
    history_record_action("tag_override_add", artist, title, detail=f"mode={mode}, tags={','.join(tags)}")

    redirect_tab = request.form.get("redirect_tab", "tags")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/remove_tag_override", methods=["POST"])
def remove_tag_override() -> ResponseReturnValue:
    """Remove a tag override."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        overrides = load_tag_overrides()
        overrides.remove(artist, title)
        history_record_action("tag_override_remove", artist, title)

    redirect_tab = request.form.get("redirect_tab", "tags")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/clear_tag_cache_entry", methods=["POST"])
def clear_tag_cache_entry() -> ResponseReturnValue:
    """Clear a specific tag cache entry."""
    artist = request.form.get("artist", "")
    title = request.form.get("title", "")

    if artist and title:
        cache = load_tag_cache()
        cache.delete_by_track(artist, title)
        history_record_action("tag_cache_clear", artist, title)

    redirect_tab = request.form.get("redirect_tab", "tags")
    return redirect(url_for("index") + f"?tab={redirect_tab}")


@actions_bp.route("/export", methods=["GET"])
def export_data() -> ResponseReturnValue:
    """Export overrides, blacklist, and/or tag overrides as JSON."""
    export_type = request.args.get("type", "all")
    overrides = load_overrides()

    result: dict[str, Any] = {}
    if export_type in ("all", "overrides"):
        result["overrides"] = dict(overrides.override_items())
    if export_type in ("all", "blacklist"):
        result["blacklist"] = dict(overrides.blacklist_items())
    if export_type in ("all", "tag_overrides"):
        tag_ov = load_tag_overrides()
        result["tag_overrides"] = dict(tag_ov.items())

    result["_export_meta"] = {
        "type": export_type,
        "version": 1,
    }

    return jsonify(result)


@actions_bp.route("/import", methods=["POST"])
def import_data() -> ResponseReturnValue:
    """Import overrides and/or blacklist from JSON."""
    data = request.get_json()
    if not data:
        return jsonify({"error": _("No data provided")}), 400

    overrides_obj = load_overrides()
    imported_overrides = 0
    imported_blacklist = 0

    if "overrides" in data and isinstance(data["overrides"], dict):
        for entry in data["overrides"].values():
            if not isinstance(entry, dict):
                continue
            artist = entry.get("artist", "").strip()
            title = entry.get("title", "").strip()
            video_id = entry.get("video_id", "").strip()
            reason = entry.get("reason", _("Imported"))
            if artist and title and video_id and VIDEO_ID_PATTERN.match(video_id):
                overrides_obj.set(artist, title, video_id, reason)
                imported_overrides += 1

    if "blacklist" in data and isinstance(data["blacklist"], dict):
        for entry in data["blacklist"].values():
            if not isinstance(entry, dict):
                continue
            artist = entry.get("artist", "").strip()
            title = entry.get("title", "").strip()
            reason = entry.get("reason", _("Imported"))
            if artist and title:
                overrides_obj.blacklist(artist, title, reason)
                imported_blacklist += 1

    imported_tag_overrides = 0
    if "tag_overrides" in data and isinstance(data["tag_overrides"], dict):
        tag_ov = load_tag_overrides()
        for entry in data["tag_overrides"].values():
            if not isinstance(entry, dict):
                continue
            artist = entry.get("artist", "").strip()
            title = entry.get("title", "").strip()
            tags = entry.get("tags", [])
            mode = entry.get("mode", "add")
            reason = entry.get("reason", _("Imported"))
            if artist and title and tags and isinstance(tags, list):
                clean_tags = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()]
                if clean_tags:
                    tag_ov.set(artist, title, clean_tags, mode=mode, reason=reason)
                    imported_tag_overrides += 1

    return jsonify(
        {
            "status": "ok",
            "imported_overrides": imported_overrides,
            "imported_blacklist": imported_blacklist,
            "imported_tag_overrides": imported_tag_overrides,
        }
    )
