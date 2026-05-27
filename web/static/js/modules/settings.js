import { applyCustomTheme, loadCustomTheme, onParentThemeChanged, setCustomEnabled } from "./customTheme.js"
import { refreshHistoryPanelState, setHistoryTabVisibility } from "./history.js"
import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { formatDateTime, getDateTimePrefs, insertBanner, invalidateSettingsCache, removeBanner, showToast, updateAutoSyncIndicator } from "./utils.js"

const NO_RESTART_SETTINGS = [
  "LASTFM_USER",
  "LASTFM_API_KEY",
  "PLAYLIST_NAME",
  "MAKE_PUBLIC",
  "LIMIT",
  "DEDUPLICATE",
  "USE_RECENCY_WEIGHTING",
  "RECENCY_HALF_LIFE_HOURS",
  "RECENCY_PLAY_WEIGHT",
  "WEEKLY_ENABLED",
  "WEEKLY_WEEK_START",
  "WEEKLY_TIMEZONE",
  "WEEKLY_KEEP_WEEKS",
  "WEEKLY_PLAYLIST_PREFIX",
  "WEEKLY_MAKE_PUBLIC",
  "USE_ANON_SEARCH",
  "EARLY_TERMINATION_SCORE",
  "SLEEP_BETWEEN_SEARCHES",
  "SEARCH_MAX_WORKERS",
  "MAX_RAW_SCROBBLES",
  "BACKFILL_PASSES",
  "CACHE_SEARCH_TTL_DAYS",
  "CACHE_NOTFOUND_TTL_DAYS",
  "API_MAX_RETRIES",
  "LASTFM_MAX_RETRIES",
  "LASTFM_MAX_CONSECUTIVE_EMPTY",
  "LASTFM_FORCE_IPV4",
  "LOG_LEVEL",
  "AUTO_TAG_SYNC_ENABLED",
  "AUTO_TAG_SYNC_FREQUENCY",
  "USE_24_HOUR_CLOCK",
  "DATE_FORMAT",
  "NOW_PLAYING_ENABLED",
  "NOW_PLAYING_INTERVAL",
  "DISPLAY_TIPS",
  "CUSTOM_PLAYLISTS_PRIVACY",
  "TAG_CACHE_TTL_DAYS",
  "TAG_MIN_COUNT",
  "TAG_SLEEP_BETWEEN",
  "HISTORY_MAX_SIZE_MB",
  "WEBHOOK_URL",
  "WEBHOOK_EVENTS",
]

const UI_RELOAD_SETTINGS = ["USE_24_HOUR_CLOCK", "DATE_FORMAT"]

export async function loadSettings() {
  try {
    const response = await fetch("/api/settings")
    if (!response.ok) throw new Error(_("Failed to load settings"))

    const settings = await response.json()

    window._originalSettings = { ...settings }

    for (const [key, value] of Object.entries(settings)) {
      const input = document.getElementById(key)
      if (!input) continue

      if (input.type === "checkbox") {
        input.checked = Boolean(value)
      } else if (input.tagName === "SELECT") {
        input.value = value || input.options[0]?.value || ""
      } else {
        input.value = value ?? ""
      }
    }

    const typeSelect = document.getElementById("AUTO_SYNC_TYPE")
    if (typeSelect) {
      const section = typeSelect.closest(".settings-section")
      if (section) {
        section.classList.toggle("schedule-type-cron", typeSelect.value === "cron")
      }
    }

    const themeSelect = document.getElementById("theme-select")
    if (themeSelect) {
      themeSelect.value = localStorage.getItem("ytm-theme") || "dark"
    }

    refreshHistoryBackfillVisibility()
  } catch (_error) {
    showToast(_("Failed to load settings"), "error")
  }
}

export async function saveSettings(event) {
  event.preventDefault()

  const form = document.getElementById("settingsForm")
  const settings = {}

  for (const input of form.querySelectorAll("input, select")) {
    if (input.id === "theme-select" || input.id === "locale-select") continue
    if (input.type === "checkbox") {
      settings[input.name] = input.checked
    } else {
      settings[input.name] = input.value
    }
  }

  const changedSettings = []
  if (window._originalSettings) {
    for (const key of Object.keys(settings)) {
      const original = window._originalSettings[key]
      const current = settings[key]
      if (String(original) !== String(current)) {
        changedSettings.push(key)
      }
    }
  }

  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    })

    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.error || _("Failed to save settings"))
    }

    invalidateSettingsCache()

    if (window.restartNowPlaying) {
      window.restartNowPlaying()
    }

    if (changedSettings.includes("HISTORY_DB_ENABLED")) {
      setHistoryTabVisibility(settings.HISTORY_DB_ENABLED)
      await refreshHistoryPanelState()
    }

    if (changedSettings.includes("DISPLAY_TIPS")) {
      document.body.classList.toggle("tips-hidden", !settings.DISPLAY_TIPS)
    }

    showToast(_("Settings saved successfully!"), "success")
    closeModal("settingsModal")

    const requiresRestart = changedSettings.some(s => !NO_RESTART_SETTINGS.includes(s))
    if (requiresRestart) {
      showRestartBanner()
    }

    const requiresReload = changedSettings.some(s => UI_RELOAD_SETTINGS.includes(s))
    if (requiresReload) {
      showReloadBanner()
    }
  } catch (error) {
    showToast(error.message || _("Failed to save settings"), "error")
  }
}

export function showSettingsModal() {
  loadSettings()
  showModal("settingsModal")
}

export function closeSettingsModal() {
  loadSettings()
  closeModal("settingsModal")
}

function showRestartBanner() {
  insertBanner(
    "restartBanner",
    "auth-required-banner",
    `
    <div class="auth-banner-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
        <path d="M3 3v5h5"></path>
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path>
        <path d="M16 21h5v-5"></path>
      </svg>
      <span>${_("Settings saved. Restart the server to apply changes.")}</span>
      <button class="btn btn-sm btn-primary" data-action="restartServer">${_("Restart Now")}</button>
      <button class="auth-banner-close" data-action="dismissRestartBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `,
  )
}

export function dismissRestartBanner() {
  removeBanner("restartBanner")
}

function showReloadBanner() {
  insertBanner(
    "reloadBanner",
    "auth-required-banner",
    `
    <div class="auth-banner-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
        <path d="M3 3v5h5"></path>
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path>
        <path d="M16 21h5v-5"></path>
      </svg>
      <span>${_("Display settings changed. Reload the page to update.")}</span>
      <button class="btn btn-sm btn-primary" data-action="reloadPage">${_("Reload")}</button>
      <button class="auth-banner-close" data-action="dismissReloadBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `,
  )
}

export function dismissReloadBanner() {
  removeBanner("reloadBanner")
}

export async function testWebhook() {
  const urlInput = document.getElementById("WEBHOOK_URL")
  const url = urlInput?.value?.trim()
  if (!url) {
    showToast(_("Enter a webhook URL first"), "warning")
    return
  }
  try {
    const resp = await fetch("/api/webhook/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
    const data = await resp.json()
    if (resp.ok) {
      showToast(_("Test webhook sent successfully!"), "success")
    } else {
      showToast(data.error || _("Webhook test failed"), "error")
    }
  } catch (_error) {
    showToast(_("Webhook test failed"), "error")
  }
}

export async function restartServer() {
  const btn = document.querySelector("#restartBanner .btn-primary")
  if (btn) {
    btn.disabled = true
    btn.textContent = _("Restarting...")
  }

  try {
    await fetch("/api/restart", { method: "POST" })
    showToast(_("Server restarting..."), "info")
    pollForRestart()
  } catch (_error) {
    showToast(_("Failed to restart server"), "error")
    if (btn) {
      btn.disabled = false
      btn.textContent = _("Restart Now")
    }
  }
}

function pollForRestart() {
  let attempts = 0
  const maxAttempts = 30

  const poll = async () => {
    attempts++
    try {
      const response = await fetch("/api/status", { method: "GET" })
      if (response.ok) {
        updateAutoSyncIndicator()
        window.location.reload()
        return
      }
    } catch (_e) {}

    if (attempts < maxAttempts) {
      setTimeout(poll, 500)
    } else {
      showToast(_("Server may have restarted. Please refresh manually."), "warning")
    }
  }

  setTimeout(poll, 1000)
}

const THEME_STORAGE_KEY = "ytm-theme"
const DEFAULT_THEME = "dark"
const LOCALE_COOKIE = "ytm-locale"
const DEFAULT_LOCALE = "en"

export function initTheme() {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || DEFAULT_THEME
  applyTheme(savedTheme)

  const themeSelect = document.getElementById("theme-select")
  if (themeSelect) {
    themeSelect.value = savedTheme
    themeSelect.addEventListener("change", e => {
      applyTheme(e.target.value)
      saveTheme(e.target.value)
      onParentThemeChanged()
    })
  }

  const customToggle = document.getElementById("custom-theme-toggle")
  if (customToggle) {
    customToggle.checked = !!loadCustomTheme().enabled
    customToggle.addEventListener("change", e => {
      setCustomEnabled(e.target.checked)
    })
  }

  applyCustomTheme()
}

function applyTheme(theme) {
  if (theme === "dark" || theme === DEFAULT_THEME) {
    document.documentElement.removeAttribute("data-theme")
  } else {
    document.documentElement.setAttribute("data-theme", theme)
  }
}

function saveTheme(theme) {
  localStorage.setItem(THEME_STORAGE_KEY, theme)
}

function initLocale() {
  const localeSelect = document.getElementById("locale-select")
  if (!localeSelect) return

  const saved =
    document.cookie
      .split("; ")
      .find(c => c.startsWith(`${LOCALE_COOKIE}=`))
      ?.split("=")[1] || DEFAULT_LOCALE
  localeSelect.value = saved

  localeSelect.addEventListener("change", e => {
    // biome-ignore lint/suspicious/noDocumentCookie: intended
    document.cookie = `${LOCALE_COOKIE}=${e.target.value};path=/;max-age=31536000;SameSite=Lax`
    location.reload()
  })
}

export function initSettings(switchTabFn) {
  const settingsForm = document.getElementById("settingsForm")
  if (settingsForm) {
    settingsForm.addEventListener("submit", saveSettings)
    loadSettings()
  }

  initTheme()
  initLocale()
  initSchedulerTypeToggle()
  initHistoryDbToggle()
  loadSchedulerStatus()

  const importInput = document.getElementById("customThemeImportInput")
  if (importInput) {
    importInput.addEventListener("change", e => window.onCustomThemeImportChange?.(e))
  }

  return tabId => {
    switchTabFn(tabId)
    if (tabId === "settings") {
      loadSettings()
      loadSchedulerStatus()
    }
    if (tabId === "history" && window.loadHistoryData) {
      window.loadHistoryData()
    }
  }
}

function initSchedulerTypeToggle() {
  const typeSelect = document.getElementById("AUTO_SYNC_TYPE")
  const section = typeSelect?.closest(".settings-section")

  if (!typeSelect || !section) return

  const updateVisibility = () => {
    const isCron = typeSelect.value === "cron"
    section.classList.toggle("schedule-type-cron", isCron)
  }

  typeSelect.addEventListener("change", updateVisibility)
  updateVisibility()
}

function refreshHistoryBackfillVisibility() {
  const checkbox = document.getElementById("HISTORY_DB_ENABLED")
  const backfillSection = document.getElementById("historyBackfillSection")
  if (!checkbox || !backfillSection) return
  backfillSection.style.display = checkbox.checked ? "" : "none"
  if (checkbox.checked) loadHistoryDbSize()
}

function initHistoryDbToggle() {
  const checkbox = document.getElementById("HISTORY_DB_ENABLED")
  if (!checkbox) return
  checkbox.addEventListener("change", refreshHistoryBackfillVisibility)
}

async function loadHistoryDbSize() {
  try {
    const r = await fetch("/api/history/status")
    if (!r.ok) return
    const data = await r.json()
    const sizeEl = document.getElementById("historyDbSize")
    if (sizeEl && data.db_size_bytes != null) {
      const kb = (data.db_size_bytes / 1024).toFixed(1)
      sizeEl.textContent = `${_("DB size:")} ${kb} KB`
    }
  } catch (_e) {}
}

export async function loadSchedulerStatus() {
  try {
    const response = await fetch("/api/scheduler/status")
    if (!response.ok) return

    const status = await response.json()
    await updateSchedulerUI(status)
  } catch (_error) {}
}

async function updateSchedulerUI(status) {
  const statusDiv = document.getElementById("schedulerStatus")
  const nextRunInfo = document.getElementById("nextRunInfo")
  const nextRunTime = document.getElementById("nextRunTime")

  if (!status.available) {
    if (statusDiv) {
      statusDiv.style.display = "block"
      statusDiv.innerHTML = `
        <div class="scheduler-status-badge scheduler-unavailable">
          <span class="scheduler-status-dot"></span>
          <span class="scheduler-status-text">${_("APScheduler not installed")}</span>
        </div>
      `
    }
    return
  }

  if (statusDiv) {
    statusDiv.style.display = "block"
    const isEnabled = status.enabled
    statusDiv.innerHTML = `
      <div class="scheduler-status-badge ${isEnabled ? "scheduler-active" : "scheduler-inactive"}">
        <span class="scheduler-status-dot"></span>
        <span class="scheduler-status-text">${isEnabled ? _("Automation Active") : _("Automation Disabled")}</span>
      </div>
    `
  }

  if (nextRunInfo && nextRunTime) {
    if (status.enabled && status.next_run) {
      nextRunInfo.style.display = "flex"
      const nextDate = new Date(status.next_run)
      const prefs = await getDateTimePrefs()
      nextRunTime.textContent = formatDateTime(nextDate, prefs)
    } else {
      nextRunInfo.style.display = "none"
    }
  }

  const typeSelect = document.getElementById("AUTO_SYNC_TYPE")
  if (typeSelect) {
    const section = typeSelect.closest(".settings-section")
    if (section) {
      section.classList.toggle("schedule-type-cron", typeSelect.value === "cron")
    }
  }
}
