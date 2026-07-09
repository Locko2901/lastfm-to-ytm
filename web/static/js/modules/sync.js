import { onEvent } from "./events.js"
import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { insertBanner, refreshPanel, removeBanner, showToast, updateNowPlayingPosition } from "./utils.js"

let syncEventSource = null
let manualSyncInProgress = false
let previewMode = false
let userScrolledAway = false
let scrollHandler = null
let lastPreviewScript = "run.py"
let lastPreviewPlaylists = null
let suppressNextDataBanner = false

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

export function runSyncDefault() {
  runSync("run.py", null, { dryRun: false })
}

export function previewSync() {
  showToast(_("Previewing sync - no changes will be made..."), "info")
  runSync("run.py", null, { dryRun: true })
}

export function runSyncFromPreview() {
  closeModal("syncPreviewModal")
  runSync(lastPreviewScript, lastPreviewPlaylists, { dryRun: false })
}

export function runSyncCustomPlaylists(names, options = {}) {
  runSync("run_tags.py", names, options)
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
      runBtn.style.display = ""
      stopBtn.style.display = "none"
      manualSyncInProgress = false

      if (previewMode) {
        previewMode = false
        statusText.textContent = success ? _("Preview ready") : _("Preview failed")
        if (success) {
          showToast(_("Sync preview ready"), "success")
          loadAndShowPreview()
        } else {
          showToast(_("Preview failed. Check output for errors."), "error")
        }
        if (window.checkFailureLog) window.checkFailureLog()
        return
      }

      statusText.textContent = success ? _("Completed") : _("Failed")

      showToast(success ? _("Sync completed successfully!") : _("Sync failed. Check output for errors."), success ? "success" : "error")

      if (window.refreshStats) window.refreshStats()

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

export async function runSync(script = "run.py", playlists = null, options = {}) {
  const preview = Boolean(options.dryRun)
  previewMode = preview
  if (preview) {
    lastPreviewScript = script
    lastPreviewPlaylists = playlists
  }
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
  statusText.textContent = preview ? _("Previewing...") : _("Running...")
  runBtn.style.display = "none"
  stopBtn.style.display = ""

  try {
    const body = { script }
    if (Array.isArray(playlists) && playlists.length) {
      body.playlists = playlists
    }
    if (preview) {
      body.dry_run = true
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
    previewMode = false
    indicator.className = "sync-indicator error"
    statusText.textContent = `Error: ${error.message}`
    runBtn.style.display = ""
    stopBtn.style.display = "none"
    showToast(error.message, "error")
  }
}

async function loadAndShowPreview() {
  let data
  try {
    const res = await fetch("/preview_result")
    if (!res.ok) throw new Error("request failed")
    data = await res.json()
  } catch (_e) {
    showToast(_("Failed to load sync preview"), "error")
    return
  }
  if (!data || data.available === false) {
    showToast(_("No preview data available"), "error")
    return
  }
  renderSyncPreview(data)
  showModal("syncPreviewModal")
}

function previewTrackRow(t, kind) {
  const li = document.createElement("li")
  li.className = `preview-track preview-${kind}`

  const main = document.createElement("div")
  main.className = "preview-track-main"
  const title = document.createElement("span")
  title.className = "preview-track-title"
  title.textContent = t.title || t.video_id || ""
  const artist = document.createElement("span")
  artist.className = "preview-track-artist"
  artist.textContent = t.artist || ""
  main.appendChild(title)
  main.appendChild(artist)
  li.appendChild(main)

  const meta = document.createElement("div")
  meta.className = "preview-track-meta"
  if (typeof t.score === "number") {
    const score = document.createElement("span")
    score.className = "preview-badge preview-badge-score"
    score.textContent = `${_("score")} ${t.score.toFixed(3)}`
    meta.appendChild(score)
  }
  if (typeof t.plays === "number") {
    const plays = document.createElement("span")
    plays.className = "preview-badge"
    plays.textContent = `${t.plays} ${_("plays")}`
    meta.appendChild(plays)
  }
  if (t.source) {
    const src = document.createElement("span")
    src.className = "preview-badge preview-badge-muted"
    src.textContent = t.source
    meta.appendChild(src)
  }
  li.appendChild(meta)
  return li
}

function previewSection(titleText, tracks, kind) {
  const section = document.createElement("div")
  section.className = "preview-section"
  const heading = document.createElement("h3")
  heading.className = "preview-section-title"
  heading.textContent = `${titleText} (${tracks.length})`
  section.appendChild(heading)
  if (!tracks.length) {
    const empty = document.createElement("p")
    empty.className = "preview-empty"
    empty.textContent = _("None")
    section.appendChild(empty)
    return section
  }
  const list = document.createElement("ul")
  list.className = "preview-track-list"
  for (const t of tracks) {
    list.appendChild(previewTrackRow(t, kind))
  }
  section.appendChild(list)
  return section
}

function renderPlaylistPreview(container, data) {
  const s = data.summary || {}

  const header = document.createElement("div")
  header.className = "preview-summary"
  const name = document.createElement("div")
  name.className = "preview-playlist-name"
  name.textContent = data.playlist_name || ""
  if (!data.exists) {
    const badge = document.createElement("span")
    badge.className = "preview-badge preview-badge-new"
    badge.textContent = _("Would be created")
    name.appendChild(document.createTextNode(" "))
    name.appendChild(badge)
  }
  header.appendChild(name)

  const stats = document.createElement("div")
  stats.className = "preview-stats"
  const items = [
    { label: _("Added"), value: s.added || 0, cls: "added" },
    { label: _("Removed"), value: s.removed || 0, cls: "removed" },
    { label: _("Unchanged"), value: s.unchanged || 0, cls: "unchanged" },
  ]
  for (const it of items) {
    const chip = document.createElement("span")
    chip.className = `preview-stat preview-stat-${it.cls}`
    chip.textContent = `${it.value} ${it.label}`
    stats.appendChild(chip)
  }
  if (s.reordered) {
    const chip = document.createElement("span")
    chip.className = "preview-stat preview-stat-reorder"
    chip.textContent = _("Reordered")
    stats.appendChild(chip)
  }
  if (data.misses) {
    const chip = document.createElement("span")
    chip.className = "preview-stat preview-stat-miss"
    chip.textContent = `${data.misses} ${_("not found")}`
    stats.appendChild(chip)
  }
  header.appendChild(stats)
  container.appendChild(header)

  if (!s.added && !s.removed && !s.reordered) {
    const uptodate = document.createElement("p")
    uptodate.className = "preview-uptodate"
    uptodate.textContent = _("Playlist is already up to date - no changes needed.")
    container.appendChild(uptodate)
    return
  }

  container.appendChild(previewSection(_("Tracks to add"), data.added || [], "add"))
  container.appendChild(previewSection(_("Tracks to remove"), data.removed || [], "remove"))
}

function renderSyncPreview(data) {
  const container = document.getElementById("syncPreviewContent")
  if (!container) return
  container.innerHTML = ""

  const playlists = Array.isArray(data.playlists) ? data.playlists : []
  if (!playlists.length) {
    const empty = document.createElement("p")
    empty.className = "preview-empty"
    empty.textContent = _("No preview data available")
    container.appendChild(empty)
    return
  }

  for (const playlist of playlists) {
    const block = document.createElement("div")
    block.className = "preview-playlist-block"
    renderPlaylistPreview(block, playlist)
    container.appendChild(block)
  }
}

export async function stopSync() {
  manualSyncInProgress = false
  suppressNextDataBanner = true
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
    if (suppressNextDataBanner) {
      suppressNextDataBanner = false
      return
    }
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
