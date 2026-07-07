import multiprocessing
import os
from pathlib import Path


def _get_available_memory_mb():
    """Get available system memory in MB (Linux only, returns None otherwise)."""
    try:
        with Path("/proc/meminfo").open() as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return None


def _detect_resources():
    """Detect system resources and return appropriate thread count.

    Always 1 worker because sync_state lives in process memory; multiple
    workers would each have isolated state.  Threads (gthread) share
    memory within the single worker, so concurrency is handled there.

    Returns:
        tuple: (threads, preload) optimized for the system.
    """
    cpu_count = multiprocessing.cpu_count()
    memory_mb = _get_available_memory_mb()

    is_toaster = cpu_count <= 1 or (memory_mb is not None and memory_mb < 1024)

    if is_toaster:
        return (2, False)

    return (min(cpu_count, 4) + 2, True)


_auto_threads, _auto_preload = _detect_resources()

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:2002")

worker_class = "gthread"
workers = 1
threads = int(os.getenv("GUNICORN_THREADS", _auto_threads))

timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

max_requests = 1000
max_requests_jitter = 50

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

proc_name = "lastfm-to-ytm"

_preload_env = os.getenv("GUNICORN_PRELOAD", "").lower()
preload_app = _preload_env == "true" if _preload_env else _auto_preload


def on_starting(server):
    """Called just before the master process is initialized."""
    try:
        from src.config import migrate_env_to_runtime, warn_env_incomplete

        if migrate_env_to_runtime():
            server.log.info("Migrated legacy cache/ paths in .env to runtime/")
        warn_env_incomplete()
    except Exception as e:
        server.log.warning(f"Could not migrate .env cache/ paths: {e}")


def post_fork(server, worker):  # noqa: ARG001
    """Initialize the APScheduler after forking."""
    try:
        from web.services.scheduler import init_scheduler_from_env

        init_scheduler_from_env()
        server.log.info("Scheduler initialized")
    except Exception as e:
        server.log.warning(f"Scheduler init failed: {e}")


def on_exit(server):
    """Called just before exiting Gunicorn."""


def worker_exit(server, worker):
    """Called when a worker exits."""
