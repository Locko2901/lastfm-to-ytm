"""Sync process routes."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from flask import Blueprint, Response, jsonify, stream_with_context

from ..services import sync_lock, sync_state

sync_bp = Blueprint("sync", __name__)

logger = logging.getLogger(__name__)


def _run_sync_process():
    """Run the sync process in background."""
    from collections import deque

    from ..services.state import MAX_OUTPUT_LINES

    with sync_lock:
        sync_state["output"] = deque(maxlen=MAX_OUTPUT_LINES)
        sync_state["exit_code"] = None
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

    if process:
        try:
            process.terminate()
            with sync_lock:
                sync_state["output"].append("--- Sync stopped by user ---")
            return jsonify({"status": "stopped"})
        except OSError:
            pass

    return jsonify({"error": "No sync running"}), 400


@sync_bp.route("/sync_output")
def sync_output():
    """Stream sync output via Server-Sent Events."""

    def generate():
        last_idx = 0
        while True:
            with sync_lock:
                output_list = list(sync_state["output"])
                running = sync_state["running"]
                exit_code = sync_state["exit_code"]

            if last_idx < len(output_list):
                for line in output_list[last_idx:]:
                    yield f"data: {json.dumps({'line': line})}\n\n"
                last_idx = len(output_list)

            if not running and last_idx >= len(output_list):
                yield f"data: {json.dumps({'finished': True, 'exit_code': exit_code})}\n\n"
                break

            time.sleep(0.1)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
