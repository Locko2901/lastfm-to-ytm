"""Shared Playwright fixtures for the dashboard frontend tests.

These tests reuse the Flask fixture server and stubbed API routes from the
screenshot automation (``tests/screenshots/generate.py``) so the dashboard
renders with deterministic demo data and never touches real credentials or
the live Last.fm / YouTube Music APIs.

The whole module is skipped automatically when Playwright (or the web extra)
is not installed, so the default unit-test run stays dependency-light.
"""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

_SCREENSHOTS_GENERATE = Path(__file__).resolve().parents[1] / "screenshots" / "generate.py"


@pytest.fixture(scope="session")
def _demo():
    """Load the screenshot automation helpers as a standalone module.

    Loaded by file path (rather than imported as a package) so the frontend
    tests don't depend on the screenshots directory being an importable
    package.
    """
    spec = importlib.util.spec_from_file_location("_frontend_demo_helpers", _SCREENSHOTS_GENERATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def base_url(_demo) -> Iterator[str]:
    """Start the demo Flask server on a free port and yield its base URL."""
    port = _demo._find_free_port()
    proc = _demo.start_server(port)

    def _drain() -> None:
        if proc.stdout is None:
            return
        for _ in iter(proc.stdout.readline, b""):
            pass

    threading.Thread(target=_drain, daemon=True).start()

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


@pytest.fixture(scope="session")
def _playwright():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(_playwright):
    try:
        instance = _playwright.chromium.launch(headless=True)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"Chromium browser is not available: {exc}")
    yield instance
    instance.close()


@pytest.fixture
def context(browser, _demo):
    ctx = browser.new_context(viewport=_demo.VIEWPORT, device_scale_factor=1)
    _demo._stub_routes(ctx)
    ctx.add_init_script(_demo._DATE_FREEZE_SCRIPT)
    yield ctx
    ctx.close()


@pytest.fixture
def page(context, base_url):
    """Open the dashboard, wait for it to render, and yield the page."""
    pg = context.new_page()
    pg.set_default_timeout(8_000)
    pg.goto(base_url)
    pg.wait_for_selector(".tabs .tab.active", state="visible")
    yield pg
    pg.close()
