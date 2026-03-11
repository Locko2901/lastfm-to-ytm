import { refreshPanel, showToast, updateNowPlayingPosition } from "./utils.js"
import { registerPoller, unregisterPoller } from "./visibility.js"

let syncEventSource = null
let lastKnownSyncTime = null
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

export async function runSync() {
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
  statusText.textContent = "Running..."
  runBtn.style.display = "none"
  stopBtn.style.display = ""

  try {
    const response = await fetch("/run_sync", { method: "POST" })
    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.error || "Failed to start sync")
    }

    syncEventSource = new EventSource("/sync_output")

    syncEventSource.onmessage = event => {
      const data = JSON.parse(event.data)

      if (data.line !== undefined) {
        const line = document.createElement("div")
        line.className = "sync-line"
        line.textContent = data.line

        if (data.line.includes("ERROR") || data.line.includes("Error")) {
          line.classList.add("error")
        } else if (data.line.includes("WARNING") || data.line.includes("Not found")) {
          line.classList.add("warning")
        } else if (data.line.includes("INFO")) {
          line.classList.add("info")
        } else if (data.line.includes("SUCCESS") || data.line.includes("Sync complete")) {
          line.classList.add("success")
        }

        output.appendChild(line)
        if (!userScrolledAway) {
          output.scrollTop = output.scrollHeight
        }
      }

      if (data.finished) {
        syncEventSource.close()
        syncEventSource = null

        const success = data.exit_code === 0
        indicator.className = `sync-indicator ${success ? "success" : "error"}`
        statusText.textContent = success ? "Completed" : "Failed"
        runBtn.style.display = ""
        stopBtn.style.display = "none"

        showToast(success ? "Sync completed successfully!" : "Sync failed. Check output for errors.", success ? "success" : "error")

        if (window.refreshStats) window.refreshStats()
        fetch("/api/stats")
          .then(r => r.json())
          .then(stats => {
            if (stats.last_sync) lastKnownSyncTime = stats.last_sync
            manualSyncInProgress = false
          })
          .catch(() => {
            manualSyncInProgress = false
          })

        if (success) {
          refreshPanel("playlist")
          refreshPanel("cache")
          refreshPanel("notfound")
          refreshPanel("overrides")
          refreshPanel("blacklist")
        }

        if (window.checkFailureLog) window.checkFailureLog()
      }
    }

    syncEventSource.onerror = () => {
      syncEventSource.close()
      syncEventSource = null
      manualSyncInProgress = false
      indicator.className = "sync-indicator error"
      statusText.textContent = "Connection lost"
      runBtn.style.display = ""
      stopBtn.style.display = "none"
    }
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
  statusText.textContent = "Stopped"
  document.getElementById("runSyncBtn").style.display = ""
  document.getElementById("stopSyncBtn").style.display = "none"

  showToast("Sync stopped", "error")
}

export function goToSyncAndRun() {
  openSyncDrawer()
  runSync()
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
  fetch("/api/stats")
    .then(r => r.json())
    .then(stats => {
      lastKnownSyncTime = stats.last_sync || null
    })
    .catch(() => {})

  registerPoller("dataWatcher", {
    callback: checkForDataUpdates,
    intervalMs: 30000,
    runOnVisible: true,
    runImmediately: false,
  })
}

export function stopDataWatcher() {
  unregisterPoller("dataWatcher")
}

async function checkForDataUpdates() {
  if (lastKnownSyncTime === null || manualSyncInProgress) return

  try {
    const response = await fetch("/api/stats")
    if (!response.ok) return

    const stats = await response.json()
    const newSyncTime = stats.last_sync

    if (newSyncTime && lastKnownSyncTime && newSyncTime !== lastKnownSyncTime) {
      lastKnownSyncTime = newSyncTime
      showDataUpdateBanner()
    } else if (newSyncTime) {
      lastKnownSyncTime = newSyncTime
    }
  } catch (_error) {}

  if (window.checkFailureLog) {
    window.checkFailureLog()
  }
}

function showDataUpdateBanner() {
  if (document.getElementById("dataUpdateBanner")) return

  const banner = document.createElement("div")
  banner.id = "dataUpdateBanner"
  banner.className = "data-update-banner"
  banner.innerHTML = `
    <div class="data-update-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
        <path d="M3 3v5h5"></path>
        <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path>
        <path d="M16 21h5v-5"></path>
      </svg>
      <span>Scheduled sync completed! New data available.</span>
      <button class="btn btn-sm btn-primary" data-action="reloadPage">Refresh</button>
      <button class="data-update-close" data-action="dismissDataUpdateBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `

  const container = document.querySelector(".container")
  if (container) {
    container.insertBefore(banner, container.firstChild)
  }
}

export function dismissDataUpdateBanner() {
  const banner = document.getElementById("dataUpdateBanner")
  if (banner) {
    banner.remove()
  }
}
