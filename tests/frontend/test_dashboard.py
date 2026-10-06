"""End-to-end frontend tests for the dashboard, driven by Playwright.

Skipped automatically when Playwright is not installed (e.g. the unit-only
CI job), so they never break the lightweight test run.
"""

import itertools

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


def test_browser_switches_fall_back_to_the_defaults_sent_with_the_page(page):
    from web.services.dashboard import DASHBOARD_SWITCH_DEFAULTS

    assert page.evaluate("window.__switchDefaults__") == DASHBOARD_SWITCH_DEFAULTS
    page.add_init_script(
        """Object.defineProperty(window, '__switchDefaults__', {
          configurable: true,
          get() { return this._sentSwitchDefaults },
          set(value) { this._sentSwitchDefaults = { ...value, USE_24_HOUR_CLOCK: !value.USE_24_HOUR_CLOCK } },
        })"""
    )
    page.route("**/api/settings", lambda route: route.abort())
    page.reload()
    result = page.evaluate(
        """async () => {
          const utils = await import('/static/js/modules/utils.js')
          utils.invalidateSettingsCache()
          return [await utils.getUse24HourClock(), utils.getDateTimePrefsSync().use24Hour]
        }"""
    )
    assert result == [not DASHBOARD_SWITCH_DEFAULTS["USE_24_HOUR_CLOCK"]] * 2


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


@pytest.mark.parametrize("variant", ["success", "danger"])
def test_history_badges_have_a_colour(page, variant):
    background = page.evaluate(
        """(variant) => {
          const badge = document.createElement('span')
          badge.className = `badge badge-${variant}`
          document.body.appendChild(badge)
          return getComputedStyle(badge).backgroundColor
        }""",
        variant,
    )
    assert background not in ("rgba(0, 0, 0, 0)", "transparent")


def test_scrobbler_tab_hidden_while_disabled(page):
    assert page.locator('.tabs .tab[data-tab="scrobbler"]').is_hidden()


def test_scrobbler_settings_section_has_connect_step(page):
    page.evaluate("window.showSettingsModal()")
    page.wait_for_selector("#settingsModal.active", state="visible")
    page.evaluate("document.querySelector('[data-settings-nav=\"automation\"]').click()")
    section = page.locator('[data-settings-section="scrobbler"]')
    section.wait_for(state="visible")
    assert section.locator('[data-action="scrobblerConnect"]').count() == 1
    assert section.locator("#SCROBBLER_ENABLED").count() == 1
    assert page.locator('[data-settings-section="credentials"] #LASTFM_API_SECRET').count() == 1
    page.evaluate("document.querySelector('[data-action=\"showSettingsField\"]').click()")
    page.wait_for_selector('[data-settings-page="general"].active')


STEP_GEOMETRY = """() => [...document.querySelectorAll('#setupModal .setup-step')].map(step => {
  const box = step.getBoundingClientRect()
  const circle = step.querySelector('.step-number').getBoundingClientRect()
  const line = getComputedStyle(step, '::before')
  const right = box.right - parseFloat(line.right)
  const label = document.createRange()
  label.selectNodeContents(step.querySelector('.step-label'))
  return {
    circle: [circle.left, circle.right, (circle.top + circle.bottom) / 2],
    line: line.content === 'none' ? null : [right - parseFloat(line.width), right, box.top + parseFloat(line.top) + parseFloat(line.height) / 2],
    labelLines: [...label.getClientRects()].filter(r => r.width > 0).map(r => (r.left + r.right) / 2),
  }
})"""


@pytest.mark.parametrize("width", [1280, 375])
@pytest.mark.parametrize("steps", [3, 2])
def test_setup_steps_join_their_circles_and_centre_their_labels(page, width, steps):
    page.set_viewport_size({"width": width, "height": 800})
    page.evaluate("window.showSetupWizard()")
    page.wait_for_selector("#setupModal.active", state="visible")
    page.evaluate("(n) => [...document.querySelectorAll('#setupModal .setup-step')].slice(n).forEach(s => s.remove())", steps)
    geometry = page.evaluate(STEP_GEOMETRY)
    assert len(geometry) == steps
    assert geometry[0]["line"] is None
    for step in geometry:
        circle_centre = (step["circle"][0] + step["circle"][1]) / 2
        assert step["labelLines"] == pytest.approx([circle_centre] * len(step["labelLines"]), abs=1)
    if width > 640 and steps == 3:
        assert len(geometry[2]["labelLines"]) == 2
    for before, after in itertools.pairwise(geometry):
        start, end, middle = after["line"]
        assert start == pytest.approx(before["circle"][1], abs=1)
        assert end == pytest.approx(after["circle"][0], abs=1)
        assert middle == pytest.approx(after["circle"][2], abs=1)
        assert end - start > 8


def _show_scrobbler_tab(page, plays, **changes):
    status = {"configured": True, "enabled": True, "dry_run": True, "counts": {}, "last_poll": None, **changes}
    page.route("**/api/scrobbler/status", lambda route: route.fulfill(json=status))
    page.route("**/api/scrobbler/plays*", lambda route: route.fulfill(json={"plays": plays, "total": len(plays)}))
    page.evaluate("document.getElementById('scrobblerTab').hidden = false; window.switchTab('scrobbler')")
    page.wait_for_selector("#panel-scrobbler.active")
    page.evaluate("window.loadScrobblerData()")


@pytest.mark.parametrize(("width", "columns"), [(1280, 3), (900, 3), (375, 1)])
def test_scrobbler_plays_keep_the_title_and_collapse_on_phones(page, width, columns):
    page.set_viewport_size({"width": width, "height": 800})
    play = {"id": 1, "video_id": "v1", "artist": "Max Richter", "title": "On the Nature of Daylight", "timestamp": 1790000000, "status": "skipped"}
    _show_scrobbler_tab(page, [play])
    page.wait_for_selector("#scrobblerPlays .scrobbler-play .track-ytm a", state="visible")
    row = page.locator("#scrobblerPlays .scrobbler-play")
    assert len(row.evaluate("e => getComputedStyle(e).gridTemplateColumns").split()) == columns


@pytest.mark.parametrize(
    ("chip", "text"),
    [
        ("", "No plays recorded yet"),
        ("done", "No play recorded as would scrobble yet."),
        ("skipped", "No skipped plays."),
        ("open", "No plays waiting for a decision."),
        ("failed", "No failed plays."),
    ],
)
def test_scrobbler_empty_state_follows_the_filter(page, chip, text):
    _show_scrobbler_tab(page, [])
    page.evaluate('(c) => document.querySelector(`#panel-scrobbler [data-scrobbler-filter="${c}"]`).click()', chip)
    page.wait_for_selector(f'#scrobblerPlays .empty-state:has-text("{text}")')


def test_scrobbler_filter_chips_start_at_the_left(page):
    _show_scrobbler_tab(page, [])
    bar = page.locator("#panel-scrobbler .filter-bar").bounding_box()
    chips = page.locator("#panel-scrobbler .filter-chips").bounding_box()
    actions = page.locator("#panel-scrobbler .filter-bar-actions").bounding_box()
    assert chips["x"] == pytest.approx(bar["x"], abs=1)
    assert actions["x"] + actions["width"] == pytest.approx(bar["x"] + bar["width"], abs=1)


SCROBBLER_STATUS = {"configured": True, "enabled": True, "dry_run": True, "counts": {}, "last_poll": None}


def test_clicking_the_scrobbler_tab_loads_it(page):
    asked = []

    def status(route):
        asked.append("status")
        route.fulfill(json=SCROBBLER_STATUS)

    def plays(route):
        asked.append("plays")
        route.fulfill(json={"plays": [], "total": 0})

    page.route("**/api/scrobbler/status", status)
    page.route("**/api/scrobbler/plays*", plays)
    page.evaluate("document.getElementById('scrobblerTab').hidden = false")
    page.evaluate("document.querySelector('.tabs .tab[data-tab=scrobbler]').click()")
    page.wait_for_selector("#scrobblerPlays .empty-state:has-text('No plays recorded yet')")
    assert {"status", "plays"} <= set(asked)
    assert page.locator("#scrobblerMode").inner_text() == "Dry run"


@pytest.mark.parametrize(
    ("action", "endpoint", "message"),
    [("scrobblerReset", "reset", "Could not reset"), ("scrobblerDisconnect", "auth/disconnect", "Could not disconnect")],
)
def test_a_network_error_in_a_scrobbler_action_shows_a_toast(page, action, endpoint, message):
    page.route(f"**/api/scrobbler/{endpoint}", lambda route: route.abort())
    page.evaluate(f"() => {{ window.{action}() }}")
    page.wait_for_selector("#appConfirmModal.active", state="visible")
    page.evaluate("document.getElementById('appConfirmAcceptBtn').click()")
    page.wait_for_selector(f"#toastContainer .toast.error:has-text('{message}')")


def test_an_expired_session_shows_the_auth_banner_until_reconnected(page):
    stream = {"body": 'event: snapshot\ndata: {"auth_status": {"valid": false, "expired": true}}\n\n'}
    page.route("**/api/events", lambda route: route.fulfill(status=200, content_type="text/event-stream", body=stream["body"]))
    page.reload()
    banner = page.locator("#authRequiredBanner")
    banner.wait_for(state="visible")
    assert "YouTube Music session expired: reconnect." in banner.inner_text()
    assert banner.locator('button[data-modal="authModal"]').inner_text() == "Set Up Auth"
    stream["body"] = 'data: {"type": "auth_status", "data": {"valid": true}}\n\n'
    banner.wait_for(state="detached")


def test_the_scrobbler_notice_points_to_the_banner_when_the_session_expired(page):
    _show_scrobbler_tab(page, [], youtube_session_expired=True, last_poll={"finished_at": 1790000000, "error": "a long engine message"})
    notice = page.locator("#scrobblerBanner")
    notice.wait_for(state="visible")
    assert "reconnect it from the banner at the top" in notice.inner_text()
    assert "a long engine message" not in notice.inner_text()
