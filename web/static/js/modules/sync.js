import { onEvent } from "./events.js"
import { _ } from "./i18n.js"
import { insertBanner, refreshPanel, removeBanner, showToast, updateNowPlayingPosition } from "./utils.js"

let syncEventSource = null
let manualSyncInProgress = false
let userScrolledAway = false
let scrollHandler = null

export function toggleSyncDrawer() {
  const drawer = document.getElementById("syncDrawer")
  drawer?.classList.toggle("collapsed")
  requestAnimationFrame(() => updateNowPlayingPosition())
}

export function openSyncDrawer() {
  const drawer = document.getElementById("syncDrawer")
  drawer?.classList.remove("collapsed")
  requestAnimationFrame(() => updateNowPlayingPosition())
}

export function closeSyncDrawer() {
  const drawer = document.getElementById("syncDrawer")
  drawer?.classList.add("collapsed")
  requestAnimationFrame(() => updateNowPlayingPosition())
}

export function toggleRunMenu() {
  const menu = document.getElementById("syncRunMenu")
  if (!menu) return
  const isOpen = menu.classList.contains("open")
  menu.classList.toggle("open", !isOpen)
  if (!isOpen) {
    const close = e => {
      if (!e.target.closest(".sync-run-wrapper")) {
        menu.classList.remove("open")
        document.removeEventListener("click", close)
      }
    }
    requestAnimationFrame(() => document.addEventListener("click", close))
  }
}

export function runSyncDefault() {
  runSync("run.py")
}

export function runSyncCustom() {
  document.getElementById("syncRunMenu")?.classList.remove("open")
  runSync("run_tags.py")
}

export function runSyncCustomPlaylists(names) {
  runSync("run_tags.py", names)
}

function classifyLine(text) {
  if (text.includes("ERROR") || text.includes("Error")) return "error"
  if (text.includes("WARNING") || text.includes("Not found")) return "warning"
  if (text.includes("INFO")) return "info"
  if (text.includes("SUCCESS") || text.includes("Sync complete")) return "success"
  return ""
}

function appendSyncLine(text) {
  const output = document.getElementById("syncOutput")
  if (!output) return
  const line = document.createElement("div")
  line.className = "sync-line"
  line.textContent = text
  const cls = classifyLine(text)
  if (cls) line.classList.add(cls)
  output.appendChild(line)
  if (!userScrolledAway) {
    output.scrollTop = output.scrollHeight
  }
}

function attachSyncStream() {
  const indicator = document.getElementById("syncIndicator")
  const statusText = document.getElementById("syncStatusText")
  const runBtn = document.getElementById("runSyncBtn")
  const stopBtn = document.getElementById("stopSyncBtn")

  if (syncEventSource) {
    syncEventSource.close()
    syncEventSource = null
  }

  syncEventSource = new EventSource("/sync_output")

  syncEventSource.onmessage = event => {
    const data = JSON.parse(event.data)

    if (data.line !== undefined) {
      appendSyncLine(data.line)
    }

    if (data.finished) {
      syncEventSource.close()
      syncEventSource = null

      const success = data.exit_code === 0
      indicator.className = `sync-indicator ${success ? "success" : "error"}`
      statusText.textContent = success ? _("Completed") : _("Failed")
      runBtn.style.display = ""
      stopBtn.style.display = "none"

      showToast(success ? _("Sync completed successfully!") : _("Sync failed. Check output for errors."), success ? "success" : "error")

      if (window.refreshStats) window.refreshStats()
      manualSyncInProgress = false

      if (success) {
        refreshPanel("playlist")
        refreshPanel("cache")
        refreshPanel("notfound")
        refreshPanel("overrides")
        refreshPanel("blacklist")
        refreshPanel("tags")
        refreshPanel("custompl")
        if (window.loadPlaylistsData) window.loadPlaylistsData()
        if (window.clearPreviewCache) window.clearPreviewCache()
      }

      if (window.checkFailureLog) window.checkFailureLog()
    }
  }

  syncEventSource.onerror = () => {
    syncEventSource.close()
    syncEventSource = null
    manualSyncInProgress = false
    indicator.className = "sync-indicator error"
    statusText.textContent = _("Connection lost")
    runBtn.style.display = ""
    stopBtn.style.display = "none"
  }
}

export async function reattachRunningSync() {
  let status
  try {
    const res = await fetch("/api/status")
    if (!res.ok) return
    status = await res.json()
  } catch (_e) {
    return
  }

  if (!status.running) return

  const output = document.getElementById("syncOutput")
  const indicator = document.getElementById("syncIndicator")
  const statusText = document.getElementById("syncStatusText")
  const runBtn = document.getElementById("runSyncBtn")
  const stopBtn = document.getElementById("stopSyncBtn")
  if (!output || !indicator || !statusText || !runBtn || !stopBtn) return

  openSyncDrawer()
  manualSyncInProgress = true
  userScrolledAway = false

  if (scrollHandler) {
    output.removeEventListener("scroll", scrollHandler)
  }
  scrollHandler = () => {
    const threshold = 50
    const isAtBottom = output.scrollHeight - output.scrollTop - output.clientHeight < threshold
    userScrolledAway = !isAtBottom
  }
  output.addEventListener("scroll", scrollHandler)

  output.innerHTML = ""
  indicator.className = "sync-indicator running"
  statusText.textContent = _("Running...")
  runBtn.style.display = "none"
  stopBtn.style.display = ""

  attachSyncStream()
}

export async function runSync(script = "run.py", playlists = null) {
  const output = document.getElementById("syncOutput")
  const indicator = document.getElementById("syncIndicator")
  const statusText = document.getElementById("syncStatusText")
  const runBtn = document.getElementById("runSyncBtn")
  const stopBtn = document.getElementById("stopSyncBtn")

  openSyncDrawer()

  manualSyncInProgress = true
  userScrolledAway = false

  if (scrollHandler) {
    output.removeEventListener("scroll", scrollHandler)
  }

  scrollHandler = () => {
    const threshold = 50
    const isAtBottom = output.scrollHeight - output.scrollTop - output.clientHeight < threshold
    userScrolledAway = !isAtBottom
  }
  output.addEventListener("scroll", scrollHandler)

  output.innerHTML = ""
  indicator.className = "sync-indicator running"
  statusText.textContent = _("Running...")
  runBtn.style.display = "none"
  stopBtn.style.display = ""

  try {
    const body = { script }
    if (Array.isArray(playlists) && playlists.length) {
      body.playlists = playlists
    }
    const response = await fetch("/run_sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.error || _("Failed to start sync"))
    }

    attachSyncStream()
  } catch (error) {
    manualSyncInProgress = false
    indicator.className = "sync-indicator error"
    statusText.textContent = `Error: ${error.message}`
    runBtn.style.display = ""
    stopBtn.style.display = "none"
    showToast(error.message, "error")
  }
}

export async function stopSync() {
  manualSyncInProgress = false
  if (syncEventSource) {
    syncEventSource.close()
    syncEventSource = null
  }

  try {
    await fetch("/stop_sync", { method: "POST" })
  } catch (_e) {}

  const indicator = document.getElementById("syncIndicator")
  const statusText = document.getElementById("syncStatusText")
  indicator.className = "sync-indicator"
  statusText.textContent = _("Stopped")
  document.getElementById("runSyncBtn").style.display = ""
  document.getElementById("stopSyncBtn").style.display = "none"

  showToast(_("Sync stopped"), "error")
}

export function goToSyncAndRun() {
  openSyncDrawer()
  runSyncDefault()
}

export function initSyncDrawerResize() {
  const drawer = document.getElementById("syncDrawer")
  const resizeHandle = document.getElementById("syncDrawerResize")
  const output = document.getElementById("syncOutput")

  if (!drawer || !resizeHandle || !output) return

  let isResizing = false
  let startY = 0
  let startHeight = 0
  const minHeight = 100
  const maxHeight = window.innerHeight * 0.8

  const savedHeight = localStorage.getItem("syncDrawerHeight")
  if (savedHeight) {
    output.style.setProperty("--drawer-height", `${savedHeight}px`)
  }

  requestAnimationFrame(() => updateNowPlayingPosition())

  resizeHandle.addEventListener("mousedown", e => {
    isResizing = true
    startY = e.clientY
    startHeight = output.offsetHeight
    resizeHandle.classList.add("dragging")
    document.body.style.cursor = "ns-resize"
    document.body.style.userSelect = "none"
    e.preventDefault()
  })

  document.addEventListener("mousemove", e => {
    if (!isResizing) return

    const deltaY = startY - e.clientY
    const newHeight = Math.min(maxHeight, Math.max(minHeight, startHeight + deltaY))

    output.style.setProperty("--drawer-height", `${newHeight}px`)
    updateNowPlayingPosition()
  })

  document.addEventListener("mouseup", () => {
    if (!isResizing) return

    isResizing = false
    resizeHandle.classList.remove("dragging")
    document.body.style.cursor = ""
    document.body.style.userSelect = ""

    const currentHeight = output.offsetHeight
    localStorage.setItem("syncDrawerHeight", currentHeight)
  })

  resizeHandle.addEventListener("touchstart", e => {
    isResizing = true
    startY = e.touches[0].clientY
    startHeight = output.offsetHeight
    resizeHandle.classList.add("dragging")
    e.preventDefault()
  })

  document.addEventListener("touchmove", e => {
    if (!isResizing) return

    const deltaY = startY - e.touches[0].clientY
    const newHeight = Math.min(maxHeight, Math.max(minHeight, startHeight + deltaY))

    output.style.setProperty("--drawer-height", `${newHeight}px`)
    updateNowPlayingPosition()
  })

  document.addEventListener("touchend", () => {
    if (!isResizing) return

    isResizing = false
    resizeHandle.classList.remove("dragging")

    const currentHeight = output.offsetHeight
    localStorage.setItem("syncDrawerHeight", currentHeight)
  })
}

export function startDataWatcher() {
  let prevRunning = null
  onEvent("sync_state", state => {
    if (!state) return
    const running = state.running === true
    const wasRunning = prevRunning === true
    prevRunning = running
    if (running || !wasRunning) return
    if (manualSyncInProgress) return
    showDataUpdateBanner()
    if (window.checkFailureLog) window.checkFailureLog()
  })
}

export function stopDataWatcher() {}

function showDataUpdateBanner() {
  insertBanner(
    "dataUpdateBanner",
    "data-update-banner",
    `
    <div class="data-update-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
        <path d="M3 3v5h5"></path>
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path>
        <path d="M16 21h5v-5"></path>
      </svg>
      <span>${_("Scheduled sync completed! New data available.")}</span>
      <button class="btn btn-sm btn-primary" data-action="reloadPage">${_("Refresh")}</button>
      <button class="data-update-close" data-action="dismissDataUpdateBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `,
  )
}

export function dismissDataUpdateBanner() {
  removeBanner("dataUpdateBanner")
}
