"""Launch the Flask dashboard for screenshot capture.

Imports `web.app:app` and runs it without the reloader. CACHE_DIR,
CONFIG_DIR and dummy credentials must already be set in the
environment before this module is imported (so module-level
`Path(CACHE_DIR / ...)` constants in `src.config` pick them up).

The real project ``.env`` is deliberately neutralised: ``src.config`` calls
``load_dotenv(PROJECT_ROOT / ".env", override=True)`` at import time *and* on
every ``Settings.from_env()``, which would otherwise clobber the fixture env
vars this process is launched with (pointing the app at the real cache,
short TTLs, etc.). We patch ``dotenv.load_dotenv`` to a no-op before importing
anything that reads config, so only the explicit fixture environment applies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))

import dotenv  # noqa: E402


def _noop_load_dotenv(*_args: object, **_kwargs: object) -> bool:
    return False


dotenv.load_dotenv = _noop_load_dotenv  # type: ignore[assignment]


def main() -> None:
    """Serve the Flask app on the configured port for screenshotting."""
    from web.app import app

    port = int(os.environ.get("DEMO_PORT", "2099"))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
