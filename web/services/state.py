"""Global state for sync and auth processes."""

from __future__ import annotations

import atexit
import json
import time
from collections import deque
from collections.abc import Generator
from threading import Lock

MAX_OUTPUT_LINES = 5000

sync_lock = Lock()

sync_state: dict = {
    "running": False,
    "output": deque(maxlen=MAX_OUTPUT_LINES),
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "process": None,
}


def reset_output(state: dict, lock: Lock) -> None:
    """Reset output deque and exit code for a fresh process run."""
    with lock:
        state["output"] = deque(maxlen=MAX_OUTPUT_LINES)
        state["exit_code"] = None


def stream_state_output(
    state: dict,
    lock: Lock,
    running_key: str = "running",
    finished_key: str | None = None,
) -> Generator[str, None, None]:
    """Generate Server-Sent Events from a shared state dict.

    Args:
        state: The state dict containing 'output' (deque) and 'exit_code'.
        lock: The threading lock protecting the state dict.
        running_key: Key in state for 'is still running' flag.
        finished_key: Key in state for 'is finished' flag (used instead of not-running).
    """
    last_idx = 0
    while True:
        with lock:
            output_list = list(state["output"])
            done = state.get(finished_key, False) if finished_key else not state[running_key]
            exit_code = state["exit_code"]

        if last_idx < len(output_list):
            for line in output_list[last_idx:]:
                yield f"data: {json.dumps({'line': line})}\n\n"
            last_idx = len(output_list)

        if done and last_idx >= len(output_list):
            yield f"data: {json.dumps({'finished': True, 'exit_code': exit_code})}\n\n"
            break

        time.sleep(0.1)


def cleanup_processes() -> None:
    """Clean up any running child processes on exit."""
    if sync_state.get("process"):
        try:
            sync_state["process"].terminate()
            sync_state["process"].wait(timeout=5)
        except Exception:
            pass


atexit.register(cleanup_processes)
