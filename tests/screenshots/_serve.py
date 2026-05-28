"""Launch the Flask dashboard for screenshot capture.

Imports `web.app:app` and runs it without the reloader. CACHE_DIR,
CONFIG_DIR and dummy credentials must already be set in the
environment before this module is imported (so module-level
`Path(CACHE_DIR / ...)` constants in `src.config` pick them up).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_ROOT))


def main() -> None:
    """Serve the Flask app on the configured port for screenshotting."""
    from web.app import app

    port = int(os.environ.get("DEMO_PORT", "2099"))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()
