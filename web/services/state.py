"""Global state for sync and auth processes."""

from __future__ import annotations

import atexit
import contextlib
import os
from collections import deque
from threading import Lock

MAX_OUTPUT_LINES = 5000

sync_lock = Lock()
auth_lock = Lock()

sync_state: dict = {
    "running": False,
    "output": deque(maxlen=MAX_OUTPUT_LINES),
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "process": None,
}

auth_state: dict = {
    "running": False,
    "output": deque(maxlen=MAX_OUTPUT_LINES),
    "master_fd": None,
    "process": None,
    "finished": False,
    "exit_code": None,
}


def cleanup_processes() -> None:
    """Clean up any running child processes on exit."""
    if sync_state.get("process"):
        try:
            sync_state["process"].terminate()
            sync_state["process"].wait(timeout=5)
        except Exception:
            pass

    if auth_state.get("process"):
        try:
            auth_state["process"].terminate()
            auth_state["process"].wait(timeout=5)
        except Exception:
            pass

    if auth_state.get("master_fd") is not None:
        with contextlib.suppress(OSError):
            os.close(auth_state["master_fd"])


atexit.register(cleanup_processes)
