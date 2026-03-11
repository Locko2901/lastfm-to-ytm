"""Sync process routes."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, Response, jsonify, stream_with_context

from ..services import sync_lock, sync_state
from ..services.state import stream_state_output

sync_bp = Blueprint("sync", __name__)

logger = logging.getLogger(__name__)


def _run_sync_process():
    """Run the sync process in background."""
    from ..services.state import reset_output

    reset_output(sync_state, sync_lock)
    with sync_lock:
        sync_state["started_at"] = datetime.now(UTC).isoformat()
        sync_state["finished_at"] = None

    try:
        project_root = Path(__file__).parent.parent.parent
        logger.info(f"Starting sync process in {project_root}")
        logger.info(f"Python executable: {sys.executable}")

        process = subprocess.Popen(
            [sys.executable, "run.py"],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        with sync_lock:
            sync_state["process"] = process

        for line in iter(process.stdout.readline, ""):
            with sync_lock:
                sync_state["output"].append(line.rstrip())

        process.wait()
        with sync_lock:
            sync_state["exit_code"] = process.returncode
        logger.info(f"Sync process finished with exit code: {process.returncode}")
    except FileNotFoundError as e:
        logger.error(f"Python interpreter not found: {e}")
        with sync_lock:
            sync_state["output"].append(f"Error: Python interpreter not found - {e}")
            sync_state["exit_code"] = -1
    except Exception as e:
        logger.exception("Sync process error")
        with sync_lock:
            sync_state["output"].append(f"Error: {type(e).__name__}: {e}")
            sync_state["exit_code"] = -1
    finally:
        with sync_lock:
            sync_state["running"] = False
            sync_state["finished_at"] = datetime.now(UTC).isoformat()
            sync_state["process"] = None


@sync_bp.route("/run_sync", methods=["POST"])
def run_sync():
    """Trigger a manual sync run."""
    with sync_lock:
        if sync_state["running"]:
            return jsonify({"error": "Sync already running"}), 400
        sync_state["running"] = True

    thread = threading.Thread(target=_run_sync_process, daemon=True)
    thread.start()

    return jsonify({"status": "started"})


@sync_bp.route("/stop_sync", methods=["POST"])
def stop_sync():
    """Stop the running sync process."""
    with sync_lock:
        process = sync_state.get("process")
        running = sync_state["running"]

    if not running:
        return jsonify({"error": "No sync running"}), 400

    if process is not None:
        with contextlib.suppress(OSError):
            process.terminate()
        with sync_lock:
            sync_state["output"].append("--- Sync stopped by user ---")

    return jsonify({"status": "stopped"})


@sync_bp.route("/sync_output")
def sync_output():
    """Stream sync output via Server-Sent Events."""
    return Response(
        stream_with_context(stream_state_output(sync_state, sync_lock)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
