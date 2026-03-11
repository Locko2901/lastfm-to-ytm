import { registerPoller, unregisterPoller } from "./visibility.js"

let _use24HourClock = null

export async function getUse24HourClock() {
  if (_use24HourClock !== null) return _use24HourClock

  try {
    const response = await fetch("/api/settings")
    if (response.ok) {
      const settings = await response.json()
      _use24HourClock = Boolean(settings.USE_24_HOUR_CLOCK)
    } else {
      _use24HourClock = true
    }
  } catch (_e) {
    _use24HourClock = true
  }
  return _use24HourClock
}

export function invalidateClockFormatCache() {
  _use24HourClock = null
}

export function formatClockTime(date, use24Hour = true) {
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: !use24Hour,
  })
}

export async function updateSystemClock() {
  const clockEl = document.getElementById("systemClock")
  if (!clockEl) return

  const use24Hour = await getUse24HourClock()
  const timeSpan = clockEl.querySelector(".clock-time")
  if (timeSpan) {
    timeSpan.textContent = formatClockTime(new Date(), use24Hour)
  }
}

export async function updateAutoSyncIndicator() {
  const indicator = document.getElementById("autoSyncIndicator")
  if (!indicator) return

  try {
    const response = await fetch("/api/scheduler/status")
    if (!response.ok) {
      indicator.classList.add("hidden")
      return
    }

    const status = await response.json()

    if (status.enabled) {
      indicator.classList.remove("hidden")

      let tooltip = "Auto-sync enabled"
      if (status.next_run) {
        const nextRun = new Date(status.next_run)
        const use24Hour = await getUse24HourClock()
        tooltip += ` • Next: ${formatDateTime(nextRun, use24Hour)}`
      }
      indicator.setAttribute("data-tooltip", tooltip)
    } else {
      indicator.classList.add("hidden")
    }
  } catch (_error) {
    indicator.classList.add("hidden")
  }
}

export function formatDateTime(date, use24Hour = true) {
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: !use24Hour,
  })
}

let _nowPlayingSettings = null

let _currentNowPlaying = { track: null, artist: null, image: null }

let _nowPlayingUpdateInProgress = false
let _nowPlayingAbortController = null
let _nowPlayingRequestId = 0
let _nowPlayingScrollHandler = null

function extractDominantColor(img) {
  return new Promise(resolve => {
    try {
      const canvas = document.createElement("canvas")
      const ctx = canvas.getContext("2d")

      const size = 50
      canvas.width = size
      canvas.height = size

      ctx.drawImage(img, 0, 0, size, size)

      const imageData = ctx.getImageData(0, 0, size, size)
      const data = imageData.data

      const colorBuckets = new Map()

      for (let i = 0; i < data.length; i += 16) {
        const r = data[i]
        const g = data[i + 1]
        const b = data[i + 2]
        const a = data[i + 3]

        if (a < 128) continue

        const brightness = (r + g + b) / 3
        if (brightness < 25 || brightness > 230) continue

        const bucketR = Math.floor(r / 32)
        const bucketG = Math.floor(g / 32)
        const bucketB = Math.floor(b / 32)
        const key = `${bucketR},${bucketG},${bucketB}`

        const existing = colorBuckets.get(key)
        if (existing) {
          existing.count++
          existing.rSum += r
          existing.gSum += g
          existing.bSum += b
        } else {
          colorBuckets.set(key, { count: 1, rSum: r, gSum: g, bSum: b })
        }
      }

      if (colorBuckets.size === 0) {
        resolve(null)
        return
      }

      let maxCount = 0
      let dominantBucket = null
      for (const bucket of colorBuckets.values()) {
        if (bucket.count > maxCount) {
          maxCount = bucket.count
          dominantBucket = bucket
        }
      }

      const avgR = Math.round(dominantBucket.rSum / dominantBucket.count)
      const avgG = Math.round(dominantBucket.gSum / dominantBucket.count)
      const avgB = Math.round(dominantBucket.bSum / dominantBucket.count)

      const bgR = Math.round(avgR * 0.5)
      const bgG = Math.round(avgG * 0.5)
      const bgB = Math.round(avgB * 0.5)

      const isWarm = avgR > avgB
      const eqR = isWarm ? 255 : 245
      const eqG = 250
      const eqB = isWarm ? 245 : 255

      resolve({
        bg: `${bgR}, ${bgG}, ${bgB}`,
        eq: `${eqR}, ${eqG}, ${eqB}`,
      })
    } catch (_e) {
      resolve(null)
    }
  })
}

function applyNowPlayingColors(widget, colors) {
  if (colors) {
    widget.style.setProperty("--np-bg-tint-local", colors.bg)
    widget.style.setProperty("--np-eq-color-local", colors.eq)
  } else {
    resetNowPlayingColors(widget)
  }
}

function resetNowPlayingColors(widget) {
  widget.style.removeProperty("--np-bg-tint-local")
  widget.style.removeProperty("--np-eq-color-local")
}

async function getNowPlayingSettings() {
  if (_nowPlayingSettings !== null) return _nowPlayingSettings

  try {
    const response = await fetch("/api/settings")
    if (response.ok) {
      const settings = await response.json()
      const enabled = settings.NOW_PLAYING_ENABLED === undefined ? true : Boolean(settings.NOW_PLAYING_ENABLED)
      _nowPlayingSettings = {
        enabled: enabled,
        interval: parseInt(settings.NOW_PLAYING_INTERVAL, 10) || 15,
      }
    } else {
      _nowPlayingSettings = { enabled: true, interval: 15 }
    }
  } catch (_e) {
    _nowPlayingSettings = { enabled: true, interval: 15 }
  }
  return _nowPlayingSettings
}

export function invalidateNowPlayingSettingsCache() {
  _nowPlayingSettings = null
}

async function updateNowPlaying() {
  const widget = document.getElementById("nowPlayingWidget")
  if (!widget) return

  if (_nowPlayingUpdateInProgress) return
  _nowPlayingUpdateInProgress = true

  _nowPlayingRequestId++
  const currentRequestId = _nowPlayingRequestId

  if (_nowPlayingAbortController) {
    _nowPlayingAbortController.abort()
  }
  _nowPlayingAbortController = new AbortController()
  const signal = _nowPlayingAbortController.signal

  try {
    const response = await fetch("/api/now-playing")
    if (!response.ok) {
      widget.classList.add("hidden")
      _currentNowPlaying = { track: null, artist: null, image: null }
      return
    }

    const data = await response.json()

    if (data.playing) {
      const trackEl = document.getElementById("nowPlayingTrack")
      const artistEl = document.getElementById("nowPlayingArtist")
      const artEl = document.getElementById("nowPlayingArt")
      const artFallback = document.getElementById("nowPlayingArtFallback")

      const songChanged = data.track !== _currentNowPlaying.track || data.artist !== _currentNowPlaying.artist
      const imageChanged = data.image !== _currentNowPlaying.image

      if (songChanged) {
        if (trackEl) trackEl.textContent = data.track || ""
        if (artistEl) artistEl.textContent = data.artist || ""
      }

      if (artEl && artFallback) {
        if (imageChanged) {
          if (data.image) {
            const proxiedUrl = `/api/image-proxy?url=${encodeURIComponent(data.image)}`

            artEl.classList.add("hidden")
            artFallback.classList.remove("hidden")

            try {
              const imgController = new AbortController()
              const timeoutId = setTimeout(() => imgController.abort(), 10000)

              if (signal.aborted) {
                imgController.abort()
              } else {
                signal.addEventListener("abort", () => imgController.abort(), { once: true })
              }

              const imgResponse = await fetch(proxiedUrl, { signal: imgController.signal })
              clearTimeout(timeoutId)

              if (!imgResponse.ok) throw new Error("Image fetch failed")

              const blob = await imgResponse.blob()
              const blobUrl = URL.createObjectURL(blob)

              if (artEl._blobUrl) {
                URL.revokeObjectURL(artEl._blobUrl)
              }
              artEl._blobUrl = blobUrl

              artEl.onload = async () => {
                if (currentRequestId !== _nowPlayingRequestId) return

                artEl.classList.remove("hidden")
                artFallback.classList.add("hidden")

                try {
                  const colors = await extractDominantColor(artEl)
                  applyNowPlayingColors(widget, colors)
                } catch (_e) {
                  resetNowPlayingColors(widget)
                }

                widget.classList.remove("hidden")
              }

              artEl.onerror = () => {
                if (currentRequestId !== _nowPlayingRequestId) return

                artEl.classList.add("hidden")
                artFallback.classList.remove("hidden")
                resetNowPlayingColors(widget)
                widget.classList.remove("hidden")
              }

              artEl.src = blobUrl
            } catch (e) {
              if (e.name === "AbortError") throw e
              artEl.classList.add("hidden")
              artFallback.classList.remove("hidden")
              resetNowPlayingColors(widget)
              widget.classList.remove("hidden")
            }
          } else {
            artEl.classList.add("hidden")
            artFallback.classList.remove("hidden")
            resetNowPlayingColors(widget)
            widget.classList.remove("hidden")
          }
        } else {
          widget.classList.remove("hidden")
        }
      } else {
        widget.classList.remove("hidden")
      }

      _currentNowPlaying = {
        track: data.track,
        artist: data.artist,
        image: data.image,
      }
    } else {
      widget.classList.add("hidden")
      _currentNowPlaying = { track: null, artist: null, image: null }
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      widget.classList.add("hidden")
    }
  } finally {
    _nowPlayingUpdateInProgress = false
  }
}

export async function initNowPlaying() {
  const settings = await getNowPlayingSettings()

  unregisterPoller("nowPlaying")

  const widget = document.getElementById("nowPlayingWidget")

  if (!settings.enabled) {
    if (widget) widget.classList.add("hidden")
    return
  }

  setupNowPlayingContextMenu()

  updateNowPlayingPosition()

  const intervalMs = Math.max(5, Math.min(120, settings.interval)) * 1000

  registerPoller("nowPlaying", {
    callback: updateNowPlaying,
    intervalMs,
    runOnVisible: true,
    runImmediately: true,
  })
}

export async function restartNowPlaying() {
  invalidateNowPlayingSettingsCache()
  await initNowPlaying()
}

export function updateNowPlayingPosition() {
  const widget = document.getElementById("nowPlayingWidget")
  const drawer = document.getElementById("syncDrawer")
  if (!widget || !drawer) return

  const spacing = 8

  const drawerRect = drawer.getBoundingClientRect()
  const drawerHeight = window.innerHeight - drawerRect.top

  widget.style.bottom = `${drawerHeight + spacing}px`
}

export function initNowPlayingScrollHide() {
  const widget = document.getElementById("nowPlayingWidget")
  if (!widget) return

  if (_nowPlayingScrollHandler) {
    window.removeEventListener("scroll", _nowPlayingScrollHandler)
  }

  _nowPlayingScrollHandler = () => {
    const scrollBottom = window.scrollY + window.innerHeight
    const docHeight = document.documentElement.scrollHeight
    const distanceFromBottom = docHeight - scrollBottom

    const widgetHeight = widget.offsetHeight || 70
    const threshold = widgetHeight + 20

    if (distanceFromBottom < threshold) {
      widget.classList.add("scroll-hidden")
    } else {
      widget.classList.remove("scroll-hidden")
    }
  }

  window.addEventListener("scroll", _nowPlayingScrollHandler, { passive: true })

  _nowPlayingScrollHandler()
}

let _contextMenuInitialized = false
function setupNowPlayingContextMenu() {
  if (_contextMenuInitialized) return
  _contextMenuInitialized = true

  const widget = document.getElementById("nowPlayingWidget")
  const menu = document.getElementById("nowPlayingContextMenu")
  if (!widget || !menu) return

  widget.addEventListener("contextmenu", e => {
    e.preventDefault()

    const x = Math.min(e.clientX, window.innerWidth - 180)
    const y = Math.min(e.clientY, window.innerHeight - 100)
    menu.style.left = `${x}px`
    menu.style.top = `${y}px`
    menu.classList.remove("hidden")
  })

  document.addEventListener("click", e => {
    if (!menu.contains(e.target)) {
      menu.classList.add("hidden")
    }
  })

  document.addEventListener(
    "scroll",
    () => {
      menu.classList.add("hidden")
    },
    true,
  )
}

export async function hideNowPlaying() {
  const widget = document.getElementById("nowPlayingWidget")
  const menu = document.getElementById("nowPlayingContextMenu")

  if (widget) widget.classList.add("hidden")
  if (menu) menu.classList.add("hidden")

  unregisterPoller("nowPlaying")

  try {
    const response = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ NOW_PLAYING_ENABLED: false }),
    })

    if (response.ok) {
      invalidateNowPlayingSettingsCache()
      if (window.showToast) {
        window.showToast("Now Playing disabled. Re-enable in Settings &rarr; Display", "success")
      }
    }
  } catch (_error) {}
}

export function clearNowPlayingHidden() {}

export function formatRelativeTime(isoString) {
  if (!isoString) return "Never"

  const date = new Date(isoString)
  const now = new Date()
  const diffMs = now - date
  const diffSec = Math.floor(diffMs / 1000)
  const diffMin = Math.floor(diffSec / 60)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffSec < 60) return "Just now"
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHour < 24) return `${diffHour}h ago`
  if (diffDay < 7) return `${diffDay}d ago`

  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export async function updateLastSyncDisplay() {
  const el = document.querySelector(".stat-value-time")
  if (!el) return

  const timestamp = el.dataset.timestamp
  const timeSpan = el.querySelector(".last-sync-time")
  if (timeSpan && timestamp) {
    timeSpan.textContent = formatRelativeTime(timestamp)
    const use24Hour = await getUse24HourClock()
    el.setAttribute("data-tooltip", formatDateTime(new Date(timestamp), use24Hour))
  }
}

export async function refreshStats() {
  try {
    const response = await fetch("/api/stats")
    if (!response.ok) return

    const stats = await response.json()

    const updateStat = (valueEl, newValue) => {
      const currentValue = valueEl.textContent.trim()
      if (currentValue !== String(newValue)) {
        valueEl.textContent = newValue
        valueEl.classList.add("updated")
        setTimeout(() => valueEl.classList.remove("updated"), 300)
      }
    }

    const statCards = document.querySelectorAll(".stat-card")
    for (const card of statCards) {
      const label = card.querySelector(".stat-label")?.textContent?.toLowerCase()
      const valueEl = card.querySelector(".stat-value")
      if (!label || !valueEl) continue

      if (label.includes("playlist")) {
        updateStat(valueEl, stats.resolved)
      } else if (label.includes("override")) {
        updateStat(valueEl, stats.overrides)
      } else if (label.includes("blacklist")) {
        updateStat(valueEl, stats.blacklist)
      } else if (label.includes("not found")) {
        updateStat(valueEl, stats.not_found)
      } else if (label.includes("cached")) {
        updateStat(valueEl, stats.cached)
      } else if (label.includes("last sync")) {
        const timeSpan = valueEl.querySelector(".last-sync-time")
        if (stats.last_sync) {
          valueEl.dataset.timestamp = stats.last_sync
          if (timeSpan) {
            timeSpan.textContent = formatRelativeTime(stats.last_sync)
          } else {
            valueEl.innerHTML = `<span class="last-sync-time">${formatRelativeTime(stats.last_sync)}</span>`
          }
        }
      }
    }

    const tabBadges = {
      playlist: stats.resolved,
      overrides: stats.overrides,
      blacklist: stats.blacklist,
      notfound: stats.not_found,
      cache: stats.cached,
    }

    for (const [tabId, count] of Object.entries(tabBadges)) {
      const tabBtn = document.querySelector(`.tab[data-tab="${tabId}"]`)
      if (tabBtn) {
        let badge = tabBtn.querySelector(".tab-badge")
        if (badge) {
          if (badge.textContent !== String(count)) {
            badge.textContent = count
            badge.classList.add("updated")
            setTimeout(() => badge.classList.remove("updated"), 300)
          }
        } else if (count > 0) {
          badge = document.createElement("span")
          badge.className = "tab-badge"
          badge.textContent = count
          tabBtn.appendChild(badge)
        }
      }
    }
  } catch (_error) {}
}

export function showToast(message, type = "success") {
  const container = document.getElementById("toastContainer")
  const toast = document.createElement("div")
  toast.className = `toast ${type}`
  const icon =
    type === "success"
      ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
      : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
  toast.innerHTML = `${icon} ${message}`
  container.appendChild(toast)

  setTimeout(() => {
    toast.style.animation = "slideIn 0.2s ease reverse"
    setTimeout(() => toast.remove(), 200)
  }, 4000)
}

export async function refreshPanel(panelName) {
  try {
    const response = await fetch(`/api/panel/${panelName}`)
    if (!response.ok) return false

    const html = await response.text()
    const panel = document.getElementById(`panel-${panelName}`)
    if (panel) {
      const searchInput = panel.querySelector('input[type="search"], input[id$="Search"]')
      const searchValue = searchInput?.value || ""

      const activeChip = panel.querySelector(".filter-chip.active")
      const activeFilter = activeChip?.dataset.filter || null

      const temp = document.createElement("div")
      temp.innerHTML = html
      const newPanel = temp.firstElementChild
      if (newPanel) {
        newPanel.classList.remove("active")
        if (panel.classList.contains("active")) {
          newPanel.classList.add("active")
        }
        panel.replaceWith(newPanel)

        if (activeFilter && activeFilter !== "all") {
          const chips = newPanel.querySelectorAll(".filter-chip")
          for (const c of chips) c.classList.remove("active")
          const targetChip = newPanel.querySelector(`.filter-chip[data-filter="${activeFilter}"]`)
          if (targetChip) {
            targetChip.classList.add("active")
          } else {
            const allChip = newPanel.querySelector('.filter-chip[data-filter="all"]')
            if (allChip) allChip.classList.add("active")
          }
        }

        const newSearchInput = newPanel.querySelector('input[type="search"], input[id$="Search"]')
        if (newSearchInput && searchValue) {
          newSearchInput.value = searchValue
        }

        if ((searchValue || (activeFilter && activeFilter !== "all")) && newSearchInput) {
          newSearchInput.dispatchEvent(new Event("input", { bubbles: true }))
        }

        return true
      }
    }
    return false
  } catch (_error) {
    return false
  }
}
