"""End-to-end frontend tests for the dashboard, driven by Playwright.

Skipped automatically when Playwright is not installed (e.g. the unit-only
CI job), so they never break the lightweight test run.
"""

import pytest

pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.frontend

EXPECTED_TABS = ["playlist", "overrides", "blacklist", "notfound", "cache", "tags", "custompl"]


def test_dashboard_renders_all_tabs(page):
    present = page.eval_on_selector_all(
        ".tabs .tab",
        "els => els.map(e => e.dataset.tab)",
    )
    for tab in EXPECTED_TABS:
        assert tab in present


def test_playlist_tab_active_by_default(page):
    active = page.locator(".tabs .tab.active")
    assert active.count() == 1
    assert active.get_attribute("data-tab") == "playlist"
    assert page.locator("#panel-playlist.active").count() == 1


@pytest.mark.parametrize("tab", ["overrides", "blacklist", "notfound", "cache", "tags", "custompl"])
def test_switch_tab_activates_panel(page, tab):
    page.evaluate("(t) => window.switchTab(t)", tab)
    page.wait_for_selector(f'.tabs .tab[data-tab="{tab}"].active')
    page.wait_for_selector(f"#panel-{tab}.active")
    playlist_class = page.locator("#panel-playlist").get_attribute("class") or ""
    assert "active" not in playlist_class.split()


def test_settings_modal_opens(page):
    page.evaluate("window.showSettingsModal()")
    page.wait_for_selector("#settingsModal.active", state="visible")
    assert page.locator("#settingsModal.active").is_visible()


def test_teleporter_modal_opens(page):
    page.evaluate("window.showTeleporterModal()")
    page.wait_for_selector("#teleporterModal.active", state="visible")
    assert page.locator("#teleporterModal.active").is_visible()


def test_sync_drawer_opens(page):
    page.evaluate("window.openSyncDrawer()")
    output = page.locator("#syncOutput")
    output.wait_for(state="visible")
    assert output.is_visible()


def test_no_uncaught_page_errors_on_load(context, base_url):
    errors = []
    page = context.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.goto(base_url)
    page.wait_for_selector(".tabs .tab.active", state="visible")
    page.close()
    assert errors == []
