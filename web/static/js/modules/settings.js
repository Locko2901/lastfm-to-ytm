import { closeModal, showModal } from "./modals.js"
import {
  formatDateTime,
  getUse24HourClock,
  invalidateClockFormatCache,
  invalidateNowPlayingSettingsCache,
  showToast,
  updateAutoSyncIndicator,
} from "./utils.js"

const _BOOL_SETTINGS = [
  "MAKE_PUBLIC",
  "DEDUPLICATE",
  "USE_ANON_SEARCH",
  "USE_RECENCY_WEIGHTING",
  "WEEKLY_ENABLED",
  "WEEKLY_MAKE_PUBLIC",
  "LASTFM_FORCE_IPV4",
  "AUTO_SYNC_ENABLED",
  "USE_24_HOUR_CLOCK",
  "NOW_PLAYING_ENABLED",
]

const NO_RESTART_SETTINGS = [
  "USE_24_HOUR_CLOCK",
  "NOW_PLAYING_ENABLED",
  "NOW_PLAYING_INTERVAL",
  "AUTO_SYNC_TYPE",
  "AUTO_SYNC_INTERVAL_HOURS",
  "AUTO_SYNC_START_TIME",
  "AUTO_SYNC_CRON",
]

export async function loadSettings() {
  try {
    const response = await fetch("/api/settings")
    if (!response.ok) throw new Error("Failed to load settings")

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
  } catch (_error) {
    showToast("Failed to load settings", "error")
  }
}

export async function saveSettings(event) {
  event.preventDefault()

  const form = document.getElementById("settingsForm")
  const settings = {}

  for (const input of form.querySelectorAll("input, select")) {
    if (input.id === "theme-select") continue
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
      throw new Error(data.error || "Failed to save settings")
    }

    invalidateClockFormatCache()
    invalidateNowPlayingSettingsCache()

    if (window.restartNowPlaying) {
      window.restartNowPlaying()
    }

    showToast("Settings saved successfully!", "success")
    closeModal("settingsModal")

    const requiresRestart = changedSettings.some(s => !NO_RESTART_SETTINGS.includes(s))
    if (requiresRestart) {
      showRestartBanner()
    }
  } catch (error) {
    showToast(error.message || "Failed to save settings", "error")
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
  if (document.getElementById("restartBanner")) return

  const banner = document.createElement("div")
  banner.id = "restartBanner"
  banner.className = "auth-required-banner"
  banner.innerHTML = `
    <div class="auth-banner-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
        <path d="M3 3v5h5"></path>
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path>
        <path d="M16 21h5v-5"></path>
      </svg>
      <span>Settings saved. Restart the server to apply changes.</span>
      <button class="btn btn-sm btn-primary" data-action="restartServer">Restart Now</button>
      <button class="auth-banner-close" data-action="dismissRestartBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `

  const container = document.querySelector(".container")
  if (container) {
    container.insertBefore(banner, container.firstChild)
  }
}

export function dismissRestartBanner() {
  const banner = document.getElementById("restartBanner")
  if (banner) {
    banner.remove()
  }
}

export async function restartServer() {
  const btn = document.querySelector("#restartBanner .btn-primary")
  if (btn) {
    btn.disabled = true
    btn.textContent = "Restarting..."
  }

  try {
    await fetch("/api/restart", { method: "POST" })
    showToast("Server restarting...", "info")
    pollForRestart()
  } catch (_error) {
    showToast("Failed to restart server", "error")
    if (btn) {
      btn.disabled = false
      btn.textContent = "Restart Now"
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
      showToast("Server may have restarted. Please refresh manually.", "warning")
    }
  }

  setTimeout(poll, 1000)
}

const THEME_STORAGE_KEY = "ytm-theme"
const DEFAULT_THEME = "dark"

export function initTheme() {
  const savedTheme = localStorage.getItem(THEME_STORAGE_KEY) || DEFAULT_THEME
  applyTheme(savedTheme)

  const themeSelect = document.getElementById("theme-select")
  if (themeSelect) {
    themeSelect.value = savedTheme
    themeSelect.addEventListener("change", e => {
      applyTheme(e.target.value)
      saveTheme(e.target.value)
    })
  }
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

export function initSettings(switchTabFn) {
  const settingsForm = document.getElementById("settingsForm")
  if (settingsForm) {
    settingsForm.addEventListener("submit", saveSettings)
    loadSettings()
  }

  initTheme()
  initSchedulerTypeToggle()
  loadSchedulerStatus()

  return tabId => {
    switchTabFn(tabId)
    if (tabId === "settings") {
      loadSettings()
      loadSchedulerStatus()
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
          <span class="scheduler-status-text">APScheduler not installed</span>
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
        <span class="scheduler-status-text">${isEnabled ? "Automation Active" : "Automation Disabled"}</span>
      </div>
    `
  }

  if (nextRunInfo && nextRunTime) {
    if (status.enabled && status.next_run) {
      nextRunInfo.style.display = "flex"
      const nextDate = new Date(status.next_run)
      const use24Hour = await getUse24HourClock()
      nextRunTime.textContent = formatDateTime(nextDate, use24Hour)
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
