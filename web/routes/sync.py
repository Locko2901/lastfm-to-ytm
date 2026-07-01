"""Sync process routes."""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask.typing import ResponseReturnValue
from flask_babel import gettext as _

from ..services import sync_lock, sync_state
from ..services.data import get_history_db
from ..services.state import stream_state_output

if TYPE_CHECKING:
    from src.history import HistoryDB

sync_bp = Blueprint("sync", __name__)

logger = logging.getLogger(__name__)


def _run_sync_process(
    script: str = "run.py",
    db: HistoryDB | None = None,
    trigger: str = "web",
    playlist_filter: list[str] | None = None,
) -> None:
    """Run sync in background."""
    from ..services.state import reset_output

    ALLOWED_SCRIPTS = {"run.py", "run_tags.py"}
    if script not in ALLOWED_SCRIPTS:
        script = "run.py"

    sync_type = "tags" if script == "run_tags.py" else "main"
    sync_id = db.start_sync(sync_type=sync_type, trigger=trigger) if db else None

    reset_output(sync_state, sync_lock)
    with sync_lock:
        sync_state["started_at"] = datetime.now(UTC).isoformat()
        sync_state["finished_at"] = None

    try:
        from ..services import events as _events

        _events.publish(
            "sync_state",
            {"running": True, "trigger": trigger, "script": script, "started_at": sync_state["started_at"]},
        )
    except Exception:
        logger.exception("Failed to publish sync_state start event")

    try:
        project_root = Path(__file__).parent.parent.parent
        logger.info(f"Starting sync process in {project_root} (script={script})")
        logger.info(f"Python executable: {sys.executable}")

        env = {**__import__("os").environ, "SYNC_TRIGGER": trigger}
        if sync_id is not None:
            env["HISTORY_SYNC_ID"] = str(sync_id)
        if script == "run_tags.py" and playlist_filter:
            env["CUSTOM_PLAYLIST_FILTER"] = json.dumps(playlist_filter)
        else:
            env.pop("CUSTOM_PLAYLIST_FILTER", None)

        # Remove settings that may have changed since server start so the
        # subprocess re-reads them from .env via load_dotenv().
        for key in ("WEBHOOK_URL", "WEBHOOK_EVENTS"):
            env.pop(key, None)
        process = subprocess.Popen(
            [sys.executable, script],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        with sync_lock:
            sync_state["process"] = process

        assert process.stdout is not None
        for line in iter(process.stdout.readline, ""):
            with sync_lock:
                sync_state["output"].append(line.rstrip())

        try:
            process.wait(timeout=7200)  # 2 hour hard limit
        except subprocess.TimeoutExpired:
            logger.warning("Sync process timed out after 2 hours, terminating...")
            with sync_lock:
                sync_state["output"].append("--- Sync timed out after 2 hours ---")
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Process did not terminate, sending SIGKILL")
                process.kill()
                process.wait(timeout=5)
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
            exit_code = sync_state.get("exit_code", -1)

        if db and sync_id:
            sync_record = db.get_sync(sync_id)
            if sync_record and sync_record["status"] == "running":
                status = "success" if exit_code == 0 else "error"
                error_msg = None
                if exit_code != 0:
                    with sync_lock:
                        output_lines = list(sync_state["output"])
                    error_keywords = ("error", "exception", "traceback")
                    error_lines = [line for line in output_lines[-20:] if any(kw in line.lower() for kw in error_keywords)]
                    error_msg = "\n".join(error_lines[-5:]) if error_lines else f"Exit code {exit_code}"
                db.finish_sync(sync_id, status=status, error_message=error_msg)

        try:
            from ..services import events as _events
            from ..services import notifications as _notif

            label = "Custom playlist sync" if script == "run_tags.py" else "Sync"
            if exit_code == 0:
                _notif.add(f"{label} finished successfully", type_="success", source=f"sync:{trigger}")
            else:
                _notif.add(f"{label} failed (exit {exit_code})", type_="error", source=f"sync:{trigger}")

            with sync_lock:
                finished_at = sync_state["finished_at"]
            _events.publish(
                "sync_state",
                {
                    "running": False,
                    "trigger": trigger,
                    "script": script,
                    "finished_at": finished_at,
                    "exit_code": exit_code,
                },
            )
            _events.publish("stats_changed", {"reason": "sync_finished"})
            _events.publish("scheduler_changed", {"reason": "sync_finished"})
        except Exception:
            logger.exception("Failed to record sync notification")


@sync_bp.route("/run_sync", methods=["POST"])
def run_sync() -> ResponseReturnValue:
    """Trigger a manual sync run."""
    ALLOWED_SCRIPTS = {"run.py", "run_tags.py"}
    data = request.get_json(silent=True) or {}
    script = data.get("script", "run.py")
    if script not in ALLOWED_SCRIPTS:
        script = "run.py"

    playlist_filter: list[str] | None = None
    if script == "run_tags.py":
        raw = data.get("playlists")
        if isinstance(raw, list):
            names = [str(n).strip() for n in raw if isinstance(n, str) and str(n).strip()]
            playlist_filter = names or None

    with sync_lock:
        if sync_state["running"]:
            return jsonify({"error": _("Sync already running")}), 400
        sync_state["running"] = True

    db = get_history_db()
    thread = threading.Thread(target=_run_sync_process, args=(script, db, "web", playlist_filter), daemon=True)
    thread.start()

    return jsonify({"status": "started"})


@sync_bp.route("/stop_sync", methods=["POST"])
def stop_sync() -> ResponseReturnValue:
    """Stop the running sync process."""
    with sync_lock:
        process = sync_state.get("process")
        running = sync_state["running"]

    if not running:
        return jsonify({"error": _("No sync running")}), 400

    if process is not None:
        with contextlib.suppress(OSError):
            process.terminate()
        with sync_lock:
            sync_state["output"].append("--- Sync stopped by user ---")

    return jsonify({"status": "stopped"})


@sync_bp.route("/sync_output")
def sync_output() -> ResponseReturnValue:
    """Stream sync output via Server-Sent Events."""
    return Response(
        stream_with_context(stream_state_output(sync_state, sync_lock)),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
