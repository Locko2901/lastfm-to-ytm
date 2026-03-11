"""Scheduler service for automated sync runs."""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = threading.Lock()

scheduler_state: dict = {
    "enabled": False,
    "schedule_type": "interval",  # "interval" or "cron"
    "interval_hours": 6,
    "start_time": "",  # HH:MM format for interval start (e.g., "00:00" for midnight)
    "cron_expression": "0 */6 * * *",  # Default: every 6 hours
    "next_run": None,
    "last_run": None,
    "last_run_success": None,
}


def get_scheduler() -> BackgroundScheduler | None:
    """Get or create the scheduler instance."""
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


def _get_sync_function() -> Callable | None:
    """Get the sync function from the sync routes module."""
    try:
        from ..routes.sync import _run_sync_process
        from ..services import sync_lock, sync_state

        def scheduled_sync():
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
                _run_sync_process()
                logger.info(f"Sync completed with exit code: {sync_state.get('exit_code')}")
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


def _update_next_run():
    """Update the next_run field in scheduler_state."""
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
) -> bool:
    """Start or reconfigure the scheduler.

    Args:
        enabled: Whether automation is enabled
        schedule_type: "interval" or "cron"
        interval_hours: Hours between runs (for interval type)
        start_time: HH:MM format for when interval should start (e.g., "00:00")
        cron_expression: Cron expression (for cron type)

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


def stop_scheduler():
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


def get_scheduler_status() -> dict:
    """Get current scheduler status for the API.

    Reads the enabled/config state from the .env file so that all Gunicorn
    workers return consistent results, even if only worker-1 actually owns
    the running APScheduler instance.  Runtime-only fields (next_run,
    last_run, last_run_success) still come from the in-memory state of the
    worker that handles the request — they will be ``None`` on non-scheduler
    workers, which is acceptable.
    """
    from .env import parse_env_file

    settings = parse_env_file()
    enabled = settings.get("AUTO_SYNC_ENABLED", "").lower() in (
        "true", "1", "yes", "on",
    )
    schedule_type = settings.get("AUTO_SYNC_TYPE", "interval").lower()
    try:
        interval_hours = float(settings.get("AUTO_SYNC_INTERVAL_HOURS", "6"))
    except ValueError:
        interval_hours = 6.0
    start_time = settings.get("AUTO_SYNC_START_TIME", "")
    cron_expression = settings.get("AUTO_SYNC_CRON", "0 */6 * * *")

    _update_next_run()

    return {
        "available": HAS_APSCHEDULER,
        "enabled": enabled and HAS_APSCHEDULER,
        "schedule_type": schedule_type,
        "interval_hours": interval_hours,
        "start_time": start_time,
        "cron_expression": cron_expression,
        "next_run": scheduler_state["next_run"],
        "last_run": scheduler_state["last_run"],
        "last_run_success": scheduler_state["last_run_success"],
    }


def init_scheduler_from_env():
    """Initialize scheduler from environment variables on app startup."""
    from .env import parse_env_file

    settings = parse_env_file()

    enabled = settings.get("AUTO_SYNC_ENABLED", "").lower() in ("true", "1", "yes", "on")
    schedule_type = settings.get("AUTO_SYNC_TYPE", "interval").lower()

    try:
        interval_hours = float(settings.get("AUTO_SYNC_INTERVAL_HOURS", "6"))
    except ValueError:
        interval_hours = 6.0

    start_time = settings.get("AUTO_SYNC_START_TIME", "")
    cron_expression = settings.get("AUTO_SYNC_CRON", "0 */6 * * *")

    if enabled:
        logger.info(f"Initializing scheduler from env: type={schedule_type}, interval={interval_hours}h, start={start_time}")
        start_scheduler(
            enabled=True,
            schedule_type=schedule_type,
            interval_hours=interval_hours,
            start_time=start_time,
            cron_expression=cron_expression,
        )
    else:
        logger.info("Scheduler disabled in settings")
