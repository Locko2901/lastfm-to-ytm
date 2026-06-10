"""CLI entrypoint (tag playlist sync)."""

import traceback

from src.config import Settings, configure_logging
from src.main import run_tags as _run_tags
from src.observability import extract_http_status, save_failure_log


def run() -> None:
    """Entry point for tag-based custom playlist sync only."""
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    try:
        _run_tags(settings)
    except Exception as e:
        error_msg = str(e)
        status = extract_http_status(error_msg)
        if status == 401 or "unauthorized" in error_msg.lower():
            save_failure_log("HTTP 401 - Authentication expired", traceback.format_exc())
        elif "Expecting value" in error_msg or "JSONDecodeError" in type(e).__name__:
            save_failure_log("Invalid auth file (browser.json may be empty or corrupted)", traceback.format_exc())
        elif status in (403, 429):
            save_failure_log(f"HTTP {status} - Access denied or rate limited", traceback.format_exc())
        else:
            save_failure_log(f"{type(e).__name__}: {error_msg}", traceback.format_exc())
        raise


if __name__ == "__main__":
    run()
