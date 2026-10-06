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


def test_shared_pagination_renders_pages_and_reports_clicks(page):
    result = page.evaluate(
        """async () => {
          const { setPagination } = await import('/static/js/modules/utils.js')
          const box = document.createElement('div')
          box.id = 'testPagination'
          document.body.appendChild(box)
          const pages = []
          setPagination('testPagination', 120, 1, 50, p => pages.push(p))
          const text = box.querySelector('.pagination-controls span').textContent
          for (const button of box.querySelectorAll('[data-page]')) button.click()
          setPagination('testPagination', 40, 0, 50, () => {})
          return { text, pages, empty: box.innerHTML }
        }"""
    )
    assert result == {"text": "2 / 3 (120 total)", "pages": [0, 2], "empty": ""}


def test_shared_fetch_json_returns_data_or_the_status_and_raises_the_error(page):
    page.route("**/api/test-accepted", lambda route: route.fulfill(status=202, json={"status": "pending"}))
    page.route("**/api/test-busy", lambda route: route.fulfill(status=409, json={"error": "busy"}))
    page.route("**/api/test-broken", lambda route: route.fulfill(status=500, body="oops"))
    result = page.evaluate(
        """async () => {
          const { fetchJson } = await import('/static/js/modules/utils.js')
          const errors = []
          for (const url of ['/api/test-busy', '/api/test-broken']) {
            try { await fetchJson(url) } catch (e) { errors.push(e.message) }
          }
          return {
            withStatus: await fetchJson('/api/test-accepted', {}, { withStatus: true }),
            plain: await fetchJson('/api/test-accepted'),
            errors,
          }
        }"""
    )
    assert result == {"withStatus": {"status": 202, "data": {"status": "pending"}}, "plain": {"status": "pending"}, "errors": ["busy", "HTTP 500"]}


def test_shared_tab_visibility_hides_a_tab_and_leaves_it(page):
    page.evaluate(
        """async () => {
          const { setTabVisibility } = await import('/static/js/modules/tabs.js')
          setTabVisibility('history', true)
          window.switchTab('history')
          setTabVisibility('history', false)
        }"""
    )
    assert page.locator('.tabs .tab[data-tab="history"]').is_hidden()
    assert page.locator(".tabs .tab.active").get_attribute("data-tab") == "playlist"


def test_shared_set_text_shows_a_placeholder_for_missing_values(page):
    texts = page.evaluate(
        """async () => {
          const { setText } = await import('/static/js/modules/utils.js')
          const el = document.createElement('span')
          el.id = 'testText'
          document.body.appendChild(el)
          setText('testText', null)
          const missing = el.textContent
          setText('testText', 0)
          return [missing, el.textContent]
        }"""
    )
    assert texts == ["\u2013", "0"]
