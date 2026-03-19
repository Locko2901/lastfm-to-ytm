import traceback

from src.config import Settings, configure_logging
from src.main import _save_failure_log
from src.main import run_tags as _run_tags


def run():
    """Entry point for tag-based custom playlist sync only."""
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    try:
        _run_tags(settings)
    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "Unauthorized" in error_msg.lower():
            _save_failure_log("HTTP 401 - Authentication expired", traceback.format_exc())
        elif "Expecting value" in error_msg or "JSONDecodeError" in type(e).__name__:
            _save_failure_log("Invalid auth file (browser.json may be empty or corrupted)", traceback.format_exc())
        elif "403" in error_msg or "Forbidden" in error_msg:
            _save_failure_log("HTTP 403 - Access denied or rate limited", traceback.format_exc())
        else:
            _save_failure_log(f"{type(e).__name__}: {error_msg}", traceback.format_exc())
        raise


if __name__ == "__main__":
    run()
