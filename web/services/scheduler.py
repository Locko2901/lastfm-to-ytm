"""Scheduler service for automated sync runs."""

from __future__ import annotations

import contextlib
import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

logger = logging.getLogger(__name__)

_RUNTIME_DIR = Path(os.environ.get("RUNTIME_DIR") or os.environ.get("CACHE_DIR") or str(Path(__file__).parent.parent.parent / "runtime"))
_TAG_SYNC_COUNTER_FILE = _RUNTIME_DIR / ".tag_sync_counter.json"

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = threading.Lock()

scheduler_state: dict[str, Any] = {
    "enabled": False,
    "schedule_type": "interval",  # "interval" or "cron"
    "interval_hours": 6,
    "start_time": "",  # HH:MM format for interval start (e.g., "00:00" for midnight)
    "cron_expression": "0 */6 * * *",  # Default: every 6 hours
    "tag_sync_enabled": False,
    "next_run": None,
    "last_run": None,
    "last_run_success": None,
}


def get_scheduler() -> BackgroundScheduler | None:
    """Get scheduler instance."""
    global _scheduler

    if not HAS_APSCHEDULER:
        logger.warning("APScheduler not installed. Automation disabled.")
        return None

    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = BackgroundScheduler(
                timezone=None,
                job_defaults={
                    "coalesce": True,
                    "max_instances": 1,
                    "misfire_grace_time": 3600,
                },
            )
        return _scheduler


def _get_sync_function() -> Callable[..., None] | None:
    """Get sync function."""
    try:
        from ..routes.sync import _run_sync_process
        from ..services import sync_lock, sync_state
        from ..services.data import get_history_db

        def _should_run_tag_sync(frequency: int) -> bool:
            """Check if tag sync should run based on frequency counter."""
            if frequency <= 1:
                return True
            try:
                _TAG_SYNC_COUNTER_FILE.parent.mkdir(parents=True, exist_ok=True)
                count = 0
                if _TAG_SYNC_COUNTER_FILE.exists():
                    with _TAG_SYNC_COUNTER_FILE.open() as f:
                        data = json.load(f)
                        count = data.get("count", 0)
                count += 1
                should_run = count >= frequency
                if should_run:
                    count = 0
                with _TAG_SYNC_COUNTER_FILE.open("w") as f:
                    json.dump({"count": count}, f)
                if not should_run:
                    logger.info("Tag sync skipped (%d/%d syncs until next tag sync)", count, frequency)
                return should_run
            except Exception as e:
                logger.warning("Tag sync counter error, running anyway: %s", e)
                return True

        def scheduled_sync() -> None:
            """Wrapper to run sync and track it in scheduler state."""
            logger.info("Scheduled sync triggered")

            with sync_lock:
                if sync_state["running"]:
                    logger.info("Skipping scheduled sync - already running")
                    return
                sync_state["running"] = True

            scheduler_state["last_run"] = datetime.now(UTC).isoformat()

            try:
                logger.info("Starting sync process...")
                db = get_history_db()
                _run_sync_process(db=db, trigger="scheduled")
                main_exit = sync_state.get("exit_code")
                logger.info(f"Sync completed with exit code: {main_exit}")

                tag_cfg = _parse_scheduler_settings()
                tag_sync_on = tag_cfg.get("tag_sync_enabled", False)
                tag_frequency = tag_cfg.get("tag_sync_frequency", 1)
                if tag_sync_on and main_exit == 0 and _should_run_tag_sync(tag_frequency):
                    logger.info("Running scheduled tag sync...")
                    with sync_lock:
                        sync_state["running"] = True
                    _run_sync_process(script="run_tags.py", db=db, trigger="scheduled")
                    logger.info(f"Tag sync completed with exit code: {sync_state.get('exit_code')}")

                scheduler_state["last_run_success"] = sync_state.get("exit_code") == 0
            except Exception as e:
                logger.exception(f"Scheduled sync failed: {e}")
                scheduler_state["last_run_success"] = False
            finally:
                _update_next_run()

        return scheduled_sync
    except ImportError as e:
        logger.error(f"Could not import sync function: {e}")
        return None


def _update_next_run() -> None:
    if _scheduler is not None and _scheduler.running:
        job = _scheduler.get_job("auto_sync")
        if job:
            next_run = job.next_run_time
            scheduler_state["next_run"] = next_run.isoformat() if next_run else None
        else:
            scheduler_state["next_run"] = None
    else:
        scheduler_state["next_run"] = None


def start_scheduler(
    enabled: bool = True,
    schedule_type: str = "interval",
    interval_hours: float = 6,
    start_time: str = "",
    cron_expression: str = "0 */6 * * *",
    tag_sync_enabled: bool = False,
) -> bool:
    """Start or reconfigure the scheduler.

    Args:
        enabled: Whether automation is enabled
        schedule_type: "interval" or "cron"
        interval_hours: Hours between runs (for interval type)
        start_time: HH:MM format for when interval should start (e.g., "00:00")
        cron_expression: Cron expression (for cron type)
        tag_sync_enabled: Also run tag sync after each scheduled main sync

    Returns:
        True if scheduler started successfully, False otherwise
    """
    if not HAS_APSCHEDULER:
        logger.warning("APScheduler not installed. Cannot start scheduler.")
        return False

    scheduler = get_scheduler()
    if scheduler is None:
        return False

    scheduler_state["enabled"] = enabled
    scheduler_state["schedule_type"] = schedule_type
    scheduler_state["interval_hours"] = interval_hours
    scheduler_state["start_time"] = start_time
    scheduler_state["cron_expression"] = cron_expression
    scheduler_state["tag_sync_enabled"] = tag_sync_enabled

    with contextlib.suppress(Exception):
        scheduler.remove_job("auto_sync")

    if not enabled:
        scheduler_state["next_run"] = None
        logger.info("Scheduler disabled")
        return True

    sync_func = _get_sync_function()
    if sync_func is None:
        logger.error("Could not get sync function")
        return False

    try:
        if schedule_type == "cron":
            trigger = CronTrigger.from_crontab(cron_expression)
            scheduler.add_job(
                sync_func,
                trigger=trigger,
                id="auto_sync",
                name="Automated Sync",
                replace_existing=True,
            )
            logger.info(f"Scheduler configured with cron: {cron_expression}")
        else:
            trigger_start = None
            if start_time:
                try:
                    hour, minute = map(int, start_time.split(":"))
                    now = datetime.now()
                    trigger_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    logger.info(f"Interval start time set to {hour:02d}:{minute:02d}")
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Invalid start_time '{start_time}', ignoring: {e}")

            trigger = IntervalTrigger(hours=interval_hours, start_date=trigger_start)
            scheduler.add_job(
                sync_func,
                trigger=trigger,
                id="auto_sync",
                name="Automated Sync",
                replace_existing=True,
            )
            log_msg = f"Scheduler configured with interval: {interval_hours} hours"
            if start_time:
                log_msg += f" starting at {start_time}"
            logger.info(log_msg)

        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started")

        _update_next_run()
        return True

    except Exception as e:
        logger.error(f"Failed to configure scheduler: {e}")
        scheduler_state["enabled"] = False
        return False


def stop_scheduler() -> None:
    """Stop the scheduler completely."""
    global _scheduler

    with _scheduler_lock:
        if _scheduler is not None:
            with contextlib.suppress(Exception):
                _scheduler.shutdown(wait=False)
            _scheduler = None

    scheduler_state["enabled"] = False
    scheduler_state["next_run"] = None
    logger.info("Scheduler stopped")


def _parse_scheduler_settings() -> dict[str, Any]:
    """Parse AUTO_SYNC_* settings from the .env file.

    Returns dict with keys: enabled, schedule_type, interval_hours,
    start_time, cron_expression.
    """
    from .env import parse_env_file

    settings = parse_env_file()
    try:
        interval_hours = float(settings.get("AUTO_SYNC_INTERVAL_HOURS", "6"))
    except ValueError:
        interval_hours = 6.0

    try:
        tag_sync_frequency = max(1, int(settings.get("AUTO_TAG_SYNC_FREQUENCY", "1")))
    except (ValueError, TypeError):
        tag_sync_frequency = 1

    return {
        "enabled": settings.get("AUTO_SYNC_ENABLED", "").lower() in ("true", "1", "yes", "on"),
        "schedule_type": settings.get("AUTO_SYNC_TYPE", "interval").lower(),
        "interval_hours": interval_hours,
        "start_time": settings.get("AUTO_SYNC_START_TIME", ""),
        "cron_expression": settings.get("AUTO_SYNC_CRON", "0 */6 * * *"),
        "tag_sync_enabled": settings.get("AUTO_TAG_SYNC_ENABLED", "").lower() in ("true", "1", "yes", "on"),
        "tag_sync_frequency": tag_sync_frequency,
    }


def get_scheduler_status() -> dict[str, Any]:
    """Get current scheduler status for the API.

    Reads the enabled/config state from the .env file so that all Gunicorn
    workers return consistent results, even if only worker-1 actually owns
    the running APScheduler instance.  Runtime-only fields (next_run,
    last_run, last_run_success) still come from the in-memory state of the
    worker that handles the request - they will be ``None`` on non-scheduler
    workers, which is acceptable.
    """
    cfg = _parse_scheduler_settings()

    _update_next_run()

    return {
        "available": HAS_APSCHEDULER,
        "enabled": cfg["enabled"] and HAS_APSCHEDULER,
        "schedule_type": cfg["schedule_type"],
        "interval_hours": cfg["interval_hours"],
        "start_time": cfg["start_time"],
        "cron_expression": cfg["cron_expression"],
        "tag_sync_enabled": cfg["tag_sync_enabled"],
        "tag_sync_frequency": cfg["tag_sync_frequency"],
        "next_run": scheduler_state["next_run"],
        "last_run": scheduler_state["last_run"],
        "last_run_success": scheduler_state["last_run_success"],
    }


def init_scheduler_from_env() -> None:
    """Initialize scheduler from environment variables on app startup."""
    cfg = _parse_scheduler_settings()

    if cfg["enabled"]:
        logger.info(
            "Initializing scheduler from env: type=%s, interval=%sh, start=%s",
            cfg["schedule_type"],
            cfg["interval_hours"],
            cfg["start_time"],
        )
        start_scheduler(
            enabled=True,
            schedule_type=cfg["schedule_type"],
            interval_hours=cfg["interval_hours"],
            start_time=cfg["start_time"],
            cron_expression=cfg["cron_expression"],
            tag_sync_enabled=cfg["tag_sync_enabled"],
        )
    else:
        logger.info("Scheduler disabled in settings")
