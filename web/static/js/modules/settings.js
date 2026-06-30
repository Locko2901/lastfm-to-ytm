import { applyCustomTheme, loadCustomTheme, onParentThemeChanged, setCustomEnabled } from "./customTheme.js"
import { refreshHistoryPanelState, setHistoryTabVisibility } from "./history.js"
import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import {
  escapeHtml,
  formatDateTime,
  getDateTimePrefs,
  insertBanner,
  invalidateSettingsCache,
  removeBanner,
  showToast,
  updateAutoSyncIndicator,
} from "./utils.js"

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
  "WEBHOOK_ALLOW_PRIVATE",
]

const UI_RELOAD_SETTINGS = ["USE_24_HOUR_CLOCK", "DATE_FORMAT"]

function readFormSettings(form) {
  const out = {}
  for (const input of form.querySelectorAll("input, select")) {
    if (input.id === "theme-select" || input.id === "locale-select") continue
    if (!input.name) continue
    if (input.type === "checkbox") {
      out[input.name] = input.checked
    } else {
      out[input.name] = input.value
    }
  }
  return out
}

export async function loadSettings() {
  try {
    const response = await fetch("/api/settings")
    if (!response.ok) throw new Error(_("Failed to load settings"))

    const settings = await response.json()

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
    refreshLocalLastfmVisibility()

    const form = document.getElementById("settingsForm")
    if (form) window._originalSettings = readFormSettings(form)
  } catch (_error) {
    showToast(_("Failed to load settings"), "error")
  }
}

export async function saveSettings(event) {
  event.preventDefault()

  const form = document.getElementById("settingsForm")
  const settings = readFormSettings(form)

  const changedSettings = []
  if (window._originalSettings) {
    const norm = (val, isCheckbox) => {
      if (isCheckbox) return val ? "true" : "false"
      return val === null || val === undefined ? "" : String(val)
    }
    for (const key of Object.keys(settings)) {
      const input = form.elements[key]
      const isCheckbox = input && input.type === "checkbox"
      if (norm(window._originalSettings[key], isCheckbox) !== norm(settings[key], isCheckbox)) {
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
    window._originalSettings = { ...settings }

    if (window.restartNowPlaying) {
      window.restartNowPlaying()
    }

    if (changedSettings.includes("HISTORY_DB_ENABLED")) {
      setHistoryTabVisibility(settings.HISTORY_DB_ENABLED)
      await refreshHistoryPanelState()
    }

    if (changedSettings.includes("USE_LOCAL_LASTFM_DB")) {
      await refreshHistoryPanelState()
      refreshLocalLastfmVisibility()
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
  initLocalLastfmToggle()
  initLocalLastfmImportDropzone()
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
  const dataMgmtGroup = document.getElementById("historyDataMgmtGroup")
  if (dataMgmtGroup) dataMgmtGroup.style.display = checkbox.checked ? "" : "none"
  if (checkbox.checked) loadHistoryDbSize()
}

function initHistoryDbToggle() {
  const checkbox = document.getElementById("HISTORY_DB_ENABLED")
  if (!checkbox) return
  checkbox.addEventListener("change", refreshHistoryBackfillVisibility)
}

function initLocalLastfmToggle() {
  const checkbox = document.getElementById("USE_LOCAL_LASTFM_DB")
  if (!checkbox) return
  checkbox.addEventListener("change", refreshLocalLastfmVisibility)
}

function refreshLocalLastfmVisibility() {
  const checkbox = document.getElementById("USE_LOCAL_LASTFM_DB")
  const actions = document.getElementById("localLastfmActions")
  const dataMgmtGroup = document.getElementById("localLastfmDataMgmtGroup")
  const enabled = !!checkbox?.checked
  if (actions) actions.style.display = enabled ? "" : "none"
  if (dataMgmtGroup) dataMgmtGroup.style.display = enabled ? "" : "none"
  loadLocalLastfmStatus()
}

async function loadLocalLastfmStatus() {
  const el = document.getElementById("localLastfmStatus")
  if (!el) return
  const checkbox = document.getElementById("USE_LOCAL_LASTFM_DB")
  if (checkbox && !checkbox.checked) {
    el.textContent = ""
    return
  }
  try {
    const r = await fetch("/api/lastfm-db/status")
    if (!r.ok) return
    const data = await r.json()
    if (!data.enabled) {
      el.textContent = _("Not yet synced \u2014 run a sync to build the local history database.")
      return
    }
    const kb = data.db_size_bytes != null ? (data.db_size_bytes / 1024).toFixed(1) : "?"
    const tracks = data.total_tracks ?? 0
    const plays = data.total_plays ?? 0
    if (tracks === 0) {
      el.textContent = _("Not yet synced \u2014 run a sync to build the local history database.")
    } else {
      el.textContent = `${tracks} ${_("unique tracks")} \u00b7 ${plays} ${_("plays")} \u00b7 ${kb} KB`
    }
  } catch (_e) {}
}

export function clearLocalLastfm() {
  showModal("clearLocalLastfmModal")
}

export async function confirmClearLocalLastfm() {
  closeModal("clearLocalLastfmModal")
  try {
    const r = await fetch("/api/lastfm-db/clear", { method: "POST" })
    if (!r.ok) {
      const data = await r.json()
      throw new Error(data.error || _("Failed to clear Last.fm history"))
    }
    showToast(_("Last.fm history cleared"), "success")
    loadLocalLastfmStatus()
  } catch (e) {
    showToast(e.message || _("Failed to clear Last.fm history"), "error")
  }
}

export function localLastfmExport() {
  window.location.href = "/api/lastfm-db/export"
}

export function showLocalLastfmDataModal() {
  pendingLocalLastfmImportFile = null
  const preview = document.getElementById("lastfm-import-preview")
  if (preview) preview.style.display = "none"
  const dropzone = document.getElementById("lastfm-import-dropzone")
  if (dropzone) dropzone.classList.remove("dragover")
  showModal("localLastfmDataModal")
}

let pendingLocalLastfmImportFile = null
let _lastfmDropzoneInited = false

export function initLocalLastfmImportDropzone() {
  if (_lastfmDropzoneInited) return
  const dropzone = document.getElementById("lastfm-import-dropzone")
  const fileInput = document.getElementById("lastfm-import-file-input")
  if (!dropzone || !fileInput) return
  _lastfmDropzoneInited = true

  dropzone.addEventListener("click", () => fileInput.click())
  dropzone.addEventListener("dragover", e => {
    e.preventDefault()
    dropzone.classList.add("dragover")
  })
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"))
  dropzone.addEventListener("drop", e => {
    e.preventDefault()
    dropzone.classList.remove("dragover")
    const file = e.dataTransfer?.files?.[0]
    if (file) _previewLocalLastfmImportFile(file)
  })
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0]
    if (file) _previewLocalLastfmImportFile(file)
    fileInput.value = ""
  })
}

function _previewLocalLastfmImportFile(file) {
  if (!file.name.endsWith(".json")) {
    showToast(_("Please select a JSON file"), "error")
    return
  }
  const reader = new FileReader()
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result)
      const count = Array.isArray(data?.scrobbles) ? data.scrobbles.length : 0
      pendingLocalLastfmImportFile = file
      const statsEl = document.getElementById("lastfm-import-stats")
      if (statsEl) {
        statsEl.innerHTML = `
          <p><strong>${escapeHtml(file.name)}</strong></p>
          <p>${_("Tracks")}: <strong>${count}</strong></p>
        `
      }
      const preview = document.getElementById("lastfm-import-preview")
      if (preview) preview.style.display = ""
    } catch (_err) {
      showToast(_("Invalid JSON file"), "error")
    }
  }
  reader.readAsText(file)
}

export async function confirmLocalLastfmImportMerge() {
  await submitLocalLastfmImport("merge")
}

export async function confirmLocalLastfmImportReplace() {
  await submitLocalLastfmImport("replace")
}

async function submitLocalLastfmImport(mode) {
  const file = pendingLocalLastfmImportFile
  if (!file) return
  try {
    const fd = new FormData()
    fd.append("file", file)
    fd.append("mode", mode)
    const r = await fetch("/api/lastfm-db/import", { method: "POST", body: fd })
    const data = await r.json()
    if (!r.ok) {
      throw new Error(data.error || _("Import failed"))
    }
    showToast(`${_("Imported:")} ${data.imported} ${_("tracks")}`, "success")
    pendingLocalLastfmImportFile = null
    const preview = document.getElementById("lastfm-import-preview")
    if (preview) preview.style.display = "none"
    closeModal("localLastfmDataModal")
    loadLocalLastfmStatus()
  } catch (e) {
    showToast(e.message || _("Import failed"), "error")
  }
}

async function loadHistoryDbSize() {
  const el = document.getElementById("historyDbStatus")
  if (!el) return
  try {
    const r = await fetch("/api/history/status")
    if (!r.ok) return
    const data = await r.json()
    if (!data.enabled) {
      el.textContent = ""
      return
    }
    const kb = data.db_size_bytes != null ? (data.db_size_bytes / 1024).toFixed(1) : "?"
    const tracks = data.total_tracks ?? 0
    const syncs = data.total_syncs ?? 0
    el.textContent = `${tracks} ${_("lookups")} \u00b7 ${syncs} ${_("syncs")} \u00b7 ${kb} KB`
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
