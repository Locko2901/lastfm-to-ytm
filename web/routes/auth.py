"""Authentication routes for YouTube Music."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import pty
import select
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

from src.config import PROJECT_ROOT

from ..services import auth_lock, auth_state

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

BROWSER_JSON_FILE = PROJECT_ROOT / "browser.json"

logger = logging.getLogger(__name__)


def _run_auth_process():
    """Run ytmusicapi browser in a PTY so we can interact with it."""
    from collections import deque

    from ..services.state import MAX_OUTPUT_LINES

    with auth_lock:
        auth_state["output"] = deque(maxlen=MAX_OUTPUT_LINES)
        auth_state["finished"] = False
        auth_state["exit_code"] = None

    project_root = Path(__file__).parent.parent.parent

    master_fd = None
    process = None

    try:
        master_fd, slave_fd = pty.openpty()

        with auth_lock:
            auth_state["master_fd"] = master_fd

        ytmusicapi_path = Path(sys.executable).parent / "ytmusicapi"

        process = subprocess.Popen(
            [ytmusicapi_path, "browser"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(project_root),
            start_new_session=True,
        )
        os.close(slave_fd)  # Close slave in parent

        with auth_lock:
            auth_state["process"] = process

        while True:
            try:
                r, _, _ = select.select([master_fd], [], [], 0.1)
                if r:
                    data = os.read(master_fd, 1024)
                    if data:
                        text = data.decode("utf-8", errors="replace")
                        with auth_lock:
                            for line in text.splitlines():
                                if line.strip():
                                    auth_state["output"].append(line)
                    else:
                        break
            except OSError:
                break

            if process.poll() is not None:
                with auth_lock:
                    auth_state["exit_code"] = process.returncode
                break

    except FileNotFoundError:
        with auth_lock:
            auth_state["output"].append("Error: ytmusicapi not found. Is it installed?")
            auth_state["exit_code"] = -1
    except Exception as e:
        logger.exception("Auth process error")
        with auth_lock:
            auth_state["output"].append(f"Error: {type(e).__name__}")
            auth_state["exit_code"] = -1
    finally:
        if master_fd is not None:
            with contextlib.suppress(OSError):
                os.close(master_fd)

        with auth_lock:
            auth_state["running"] = False
            auth_state["finished"] = True
            auth_state["master_fd"] = None
            auth_state["process"] = None


@auth_bp.route("/start", methods=["POST"])
def start():
    """Start the ytmusicapi browser auth regeneration process."""
    with auth_lock:
        if auth_state["running"]:
            return jsonify({"error": "Auth regeneration already running"}), 400

    if BROWSER_JSON_FILE.exists():
        try:
            BROWSER_JSON_FILE.unlink()
        except OSError as e:
            logger.error(f"Failed to remove browser.json: {e}")
            return jsonify({"error": "Failed to remove old auth file"}), 500

    with auth_lock:
        auth_state["running"] = True

    thread = threading.Thread(target=_run_auth_process, daemon=True)
    thread.start()

    return jsonify({"status": "started"})


@auth_bp.route("/send", methods=["POST"])
def send_input():
    """Send input to the running ytmusicapi browser process."""
    with auth_lock:
        if not auth_state["running"] or auth_state["master_fd"] is None:
            return jsonify({"error": "No auth process running"}), 400
        master_fd = auth_state["master_fd"]

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    text = data.get("text", "")

    try:
        os.write(master_fd, (text + "\n").encode("utf-8"))
        os.write(master_fd, b"\x04")  # Ctrl-D (EOF)
        return jsonify({"status": "sent"})
    except OSError as e:
        logger.error(f"Failed to send to auth process: {e}")
        return jsonify({"error": "Failed to send input"}), 500


@auth_bp.route("/status")
def status():
    """Get current auth regeneration status and browser.json validity."""
    browser_json_exists = BROWSER_JSON_FILE.exists()
    browser_has_content = browser_json_exists and BROWSER_JSON_FILE.stat().st_size > 3
    valid = False

    if browser_has_content:
        try:
            with BROWSER_JSON_FILE.open() as f:
                data = json.load(f)
            cookie = data.get("cookie", "")
            if "cookie" in data and ("SAPISID" in cookie or "SID" in cookie):
                valid = True
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    with auth_lock:
        return jsonify(
            {
                "running": auth_state["running"],
                "output": list(auth_state["output"])[-100:],
                "finished": auth_state["finished"],
                "exit_code": auth_state["exit_code"],
                "browser_json_exists": browser_has_content,
                "valid": valid,
            }
        )


@auth_bp.route("/validate")
def validate():
    """Quick check that browser.json exists and has valid structure."""
    if not BROWSER_JSON_FILE.exists():
        return jsonify({"valid": False, "configured": False, "error": "browser.json not found"})

    if BROWSER_JSON_FILE.stat().st_size <= 3:
        return jsonify({"valid": False, "configured": False, "error": "browser.json is empty"})

    try:
        with BROWSER_JSON_FILE.open() as f:
            data = json.load(f)

        if "cookie" not in data:
            return jsonify({"valid": False, "configured": False, "error": "Missing cookie in auth file"})

        cookie = data.get("cookie", "")
        if "SAPISID" not in cookie and "SID" not in cookie:
            return jsonify({"valid": False, "configured": False, "error": "Auth cookie appears invalid"})

        return jsonify({"valid": True, "configured": True})
    except json.JSONDecodeError:
        return jsonify({"valid": False, "configured": False, "error": "Invalid JSON in auth file"})
    except OSError:
        return jsonify({"valid": False, "configured": False, "error": "Cannot read auth file"})


@auth_bp.route("/test")
def test():
    """Actually test the auth by fetching the user's last liked song."""
    if not BROWSER_JSON_FILE.exists():
        return jsonify({"valid": False, "error": "browser.json not found"})

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
            return jsonify({"valid": False, "error": "Auth expired - please regenerate", "expired": True})
        logger.exception("Auth test failed")
        return jsonify({"valid": False, "error": "Auth test failed"})


@auth_bp.route("/stop", methods=["POST"])
def stop():
    """Stop the running auth regeneration process."""
    with auth_lock:
        process = auth_state.get("process")

    if process:
        try:
            process.terminate()
            with auth_lock:
                auth_state["output"].append("--- Auth process stopped by user ---")
            return jsonify({"status": "stopped"})
        except OSError:
            pass

    return jsonify({"status": "not_running"})


@auth_bp.route("/output")
def output():
    """Stream auth output via Server-Sent Events."""

    def generate():
        last_idx = 0
        while True:
            with auth_lock:
                output_list = list(auth_state["output"])
                finished = auth_state["finished"]
                exit_code = auth_state["exit_code"]

            if last_idx < len(output_list):
                for line in output_list[last_idx:]:
                    yield f"data: {json.dumps({'line': line})}\n\n"
                last_idx = len(output_list)

            if finished and last_idx >= len(output_list):
                yield f"data: {json.dumps({'finished': True, 'exit_code': exit_code})}\n\n"
                break

            time.sleep(0.1)

    return Response(generate(), mimetype="text/event-stream")
