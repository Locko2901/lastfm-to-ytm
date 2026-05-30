import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { formatDateTime, getDateTimePrefs, getDateTimePrefsSync, refreshPanel, showToast } from "./utils.js"

let currentSubtab = "tracks"
let trackPage = 0
let syncPage = 0
let actionPage = 0
let trackSearch = ""
let trackFoundFilter = "all"
let trendDays = 7
let syncDateFrom = ""
let syncDateTo = ""
let actionDateFrom = ""
let actionDateTo = ""
const PAGE_SIZE = 50

export function initHistory() {
  const activeSubtab = document.querySelector("[data-history-tab].active")
  if (activeSubtab?.dataset.historyTab) {
    currentSubtab = activeSubtab.dataset.historyTab
  }

  initHistoryImportDropzone()
  const activeFilter = document.querySelector("[data-history-filter].active")
  if (activeFilter?.dataset.historyFilter) {
    trackFoundFilter = activeFilter.dataset.historyFilter
  }

  for (const chip of document.querySelectorAll("[data-history-tab]")) {
    chip.addEventListener("click", () => switchHistorySubtab(chip.dataset.historyTab))
  }

  for (const chip of document.querySelectorAll("[data-history-filter]")) {
    chip.addEventListener("click", () => {
      for (const c of document.querySelectorAll("[data-history-filter]")) c.classList.remove("active")
      chip.classList.add("active")
      trackFoundFilter = chip.dataset.historyFilter
      trackPage = 0
      loadHistoryTracks()
    })
  }

  const searchInput = document.getElementById("historyTrackSearch")
  if (searchInput) {
    trackSearch = searchInput.value.trim()
    let debounce = null
    searchInput.addEventListener("input", () => {
      clearTimeout(debounce)
      debounce = setTimeout(() => {
        trackSearch = searchInput.value.trim()
        trackPage = 0
        loadHistoryTracks()
      }, 300)
    })
  }

  for (const chip of document.querySelectorAll("[data-trend-days]")) {
    chip.addEventListener("click", () => {
      for (const c of document.querySelectorAll("[data-trend-days]")) c.classList.remove("active")
      chip.classList.add("active")
      trendDays = parseInt(chip.dataset.trendDays, 10)
      loadHistoryTrend()
    })
  }

  bindDateRange(
    "historySyncDateFrom",
    "historySyncDateTo",
    v => {
      syncDateFrom = v
    },
    v => {
      syncDateTo = v
    },
    () => {
      syncPage = 0
      loadHistorySyncs()
    },
  )
  bindDateRange(
    "historyActionDateFrom",
    "historyActionDateTo",
    v => {
      actionDateFrom = v
    },
    v => {
      actionDateTo = v
    },
    () => {
      actionPage = 0
      loadHistoryActions()
    },
  )
}

function bindDateRange(fromId, toId, setFrom, setTo, reload) {
  const fromEl = document.getElementById(fromId)
  const toEl = document.getElementById(toId)
  if (fromEl) {
    fromEl.addEventListener("change", () => {
      setFrom(fromEl.value)
      reload()
    })
  }
  if (toEl) {
    toEl.addEventListener("change", () => {
      setTo(toEl.value)
      reload()
    })
  }
}

function applyHistorySubtab(tab) {
  for (const c of document.querySelectorAll("[data-history-tab]")) {
    c.classList.toggle("active", c.dataset.historyTab === tab)
  }
  for (const p of document.querySelectorAll(".history-subpanel")) {
    p.classList.toggle("active", p.id === `history-${tab}`)
  }
}

function applyHistoryFilter(filter) {
  for (const c of document.querySelectorAll("[data-history-filter]")) {
    c.classList.toggle("active", c.dataset.historyFilter === filter)
  }
}

function switchHistorySubtab(tab) {
  currentSubtab = tab
  applyHistorySubtab(tab)

  if (tab === "tracks") loadHistoryTracks()
  else if (tab === "syncs") loadHistorySyncs()
  else if (tab === "actions") loadHistoryActions()
  else if (tab === "top") loadHistoryTopTracks()
  else if (tab === "trend") loadHistoryTrend()
}

export function switchHistoryView(tab = "tracks", filter = "all") {
  currentSubtab = tab
  if (tab === "tracks") {
    trackFoundFilter = filter
    trackPage = 0
    applyHistoryFilter(filter)
  } else if (tab === "syncs") {
    syncPage = 0
  } else if (tab === "actions") {
    actionPage = 0
  }

  applyHistorySubtab(tab)

  if (window.switchTab) {
    window.switchTab("history")
  } else {
    loadHistoryData()
  }
}

export async function loadHistoryData() {
  await loadHistoryStats()
  if (currentSubtab === "tracks") loadHistoryTracks()
  else if (currentSubtab === "syncs") loadHistorySyncs()
  else if (currentSubtab === "actions") loadHistoryActions()
  else if (currentSubtab === "top") loadHistoryTopTracks()
  else if (currentSubtab === "trend") loadHistoryTrend()
}

async function loadHistoryStats() {
  try {
    const r = await fetch("/api/history/status")
    if (!r.ok) return
    const data = await r.json()
    if (!data.enabled) return

    setText("histStatTracks", data.total_tracks)
    setText("histStatFound", data.found_tracks)
    setText("histStatMissed", data.not_found_tracks)
    setText("histStatSyncs", data.total_syncs)
    setText("histStatAvgDuration", data.avg_duration != null ? `${data.avg_duration}s` : "–")
    setText("histStatCacheRate", data.cache_hit_rate != null ? `${data.cache_hit_rate}%` : "–")
    setText("histStatApiCalls", data.total_api_searches)
    setText("histStatActions", data.total_actions)

    updateBackfillSection(data)
  } catch (_e) {}
}

function updateBackfillSection(data) {
  const section = document.getElementById("historyBackfillSection")
  if (section) section.style.display = ""

  const sizeEl = document.getElementById("historyDbSize")
  if (sizeEl && data.db_size_bytes != null) {
    const kb = (data.db_size_bytes / 1024).toFixed(1)
    sizeEl.textContent = `${_("DB size:")} ${kb} KB`
  }
}

async function loadHistoryTracks() {
  const list = document.getElementById("historyTrackList")
  if (!list) return

  const params = new URLSearchParams({
    limit: PAGE_SIZE,
    offset: trackPage * PAGE_SIZE,
    sort: "last_seen",
    order: "desc",
  })
  if (trackSearch) params.set("search", trackSearch)
  if (trackFoundFilter !== "all") params.set("found", trackFoundFilter)

  try {
    const r = await fetch(`/api/history/tracks?${params}`)
    if (!r.ok) return
    const data = await r.json()

    if (!data.tracks.length) {
      list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("No tracks found")}</p></div>`
      setPagination("historyTrackPagination", 0, 0, () => {})
      return
    }

    list.innerHTML = data.tracks
      .map(
        t => `
      <div class="track-item" data-artist="${escAttr(t.artist.toLowerCase())}" data-title="${escAttr(t.title.toLowerCase())}" data-original-artist="${escAttr(t.artist)}" data-original-title="${escAttr(t.title)}">
        <div class="track-info">
          <span class="track-artist">${esc(t.artist)}</span>
          <span class="track-title">${esc(t.title)}</span>
        </div>
        <div class="track-ytm">
          ${
            t.video_id
              ? `<a href="https://music.youtube.com/watch?v=${esc(t.video_id)}" target="_blank" rel="noopener">${esc(t.yt_title || t.title)}</a>`
              : `<span class="text-muted">${_("Not found")}</span>`
          }
          <span class="track-ytm-id">
            ${t.video_id ? esc(t.video_id) : ""}
            <span class="badge badge-${sourceBadge(t.source)}">${esc(t.source)}</span>
            <span class="badge badge-muted">${_("seen")} ${t.times_found}×</span>
            ${t.times_missed ? `<span class="badge badge-danger">${_("missed")} ${t.times_missed}×</span>` : ""}
          </span>
        </div>
      </div>`,
      )
      .join("")

    setPagination("historyTrackPagination", data.total, trackPage, p => {
      trackPage = p
      loadHistoryTracks()
    })
  } catch (_e) {
    list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("Failed to load tracks")}</p></div>`
  }
}

async function loadHistorySyncs() {
  const list = document.getElementById("historySyncList")
  if (!list) return

  try {
    const prefs = await getDateTimePrefs()
    const syncParams = new URLSearchParams({ limit: PAGE_SIZE, offset: syncPage * PAGE_SIZE })
    if (syncDateFrom) syncParams.set("from", syncDateFrom)
    if (syncDateTo) syncParams.set("to", syncDateTo)
    const r = await fetch(`/api/history/syncs?${syncParams}`)
    if (!r.ok) return
    const data = await r.json()

    if (!data.syncs.length) {
      list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("No syncs recorded yet")}</p></div>`
      setPagination("historySyncPagination", 0, 0, () => {})
      return
    }

    list.innerHTML = data.syncs
      .map(s => {
        const statusMap = { success: "success", error: "danger" }
        const statusBadge = statusMap[s.status] ?? "warning"
        const duration = s.duration_secs != null ? `${s.duration_secs.toFixed(1)}s` : "–"
        const date = formatShortDate(s.started_at, prefs)
        return `
        <div class="track-item" data-action="showHistorySyncModal" data-sync-id="${s.id}" style="cursor: pointer;">
          <div class="track-info">
            <span class="track-artist">${date}</span>
            <span class="track-title">${esc(s.sync_type)} · ${esc(s.trigger)}</span>
          </div>
          <div class="track-ytm">
            <span>
              <span class="badge badge-${statusBadge}">${esc(s.status)}</span>
              <span class="badge badge-muted">${duration}</span>
            </span>
            <span class="track-ytm-id">
              ${_("Resolved")}: ${s.tracks_resolved}/${s.tracks_total}
              · ${_("Cache")}: ${s.cache_hits}/${s.cache_hits + s.cache_misses}
              · ${_("API")}: ${s.api_searches}
            </span>
          </div>
        </div>`
      })
      .join("")

    setPagination("historySyncPagination", data.total, syncPage, p => {
      syncPage = p
      loadHistorySyncs()
    })
  } catch (_e) {
    list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("Failed to load syncs")}</p></div>`
  }
}

async function loadHistoryActions() {
  const list = document.getElementById("historyActionList")
  if (!list) return

  try {
    const prefs = await getDateTimePrefs()
    const actionParams = new URLSearchParams({ limit: PAGE_SIZE, offset: actionPage * PAGE_SIZE })
    if (actionDateFrom) actionParams.set("from", actionDateFrom)
    if (actionDateTo) actionParams.set("to", actionDateTo)
    const r = await fetch(`/api/history/actions?${actionParams}`)
    if (!r.ok) return
    const data = await r.json()

    if (!data.actions.length) {
      list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("No actions recorded yet")}</p></div>`
      setPagination("historyActionPagination", 0, 0, () => {})
      return
    }

    list.innerHTML = data.actions
      .map(a => {
        const date = formatShortDate(a.timestamp, prefs)
        const trackInfo = a.artist ? `${esc(a.artist)} – ${esc(a.title || "")}` : ""
        const trackAttrs =
          a.artist && a.title
            ? ` data-artist="${escAttr(a.artist.toLowerCase())}" data-title="${escAttr(a.title.toLowerCase())}" data-original-artist="${escAttr(a.artist)}" data-original-title="${escAttr(a.title)}"`
            : ""
        return `
        <div class="track-item"${trackAttrs}>
          <div class="track-info">
            <span class="track-artist">${date}</span>
            <span class="track-title">${esc(actionLabel(a.action_type))}</span>
          </div>
          <div class="track-ytm">
            <span>${trackInfo}</span>
            <span class="track-ytm-id">
              ${a.detail ? esc(a.detail) : ""}
              <span class="badge badge-muted">${esc(a.source)}</span>
            </span>
          </div>
        </div>`
      })
      .join("")

    setPagination("historyActionPagination", data.total, actionPage, p => {
      actionPage = p
      loadHistoryActions()
    })
  } catch (_e) {
    list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("Failed to load actions")}</p></div>`
  }
}

async function loadHistoryTopTracks() {
  const list = document.getElementById("historyTopList")
  if (!list) return

  try {
    const r = await fetch("/api/history/top-tracks?limit=30")
    if (!r.ok) return
    const data = await r.json()

    if (!data.tracks.length) {
      list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("No tracks found")}</p></div>`
      return
    }

    list.innerHTML = data.tracks
      .map(
        (t, i) => `
      <div class="track-item" data-artist="${escAttr(t.artist.toLowerCase())}" data-title="${escAttr(t.title.toLowerCase())}" data-original-artist="${escAttr(t.artist)}" data-original-title="${escAttr(t.title)}">
        <div class="track-info">
          <span class="track-artist"><span class="badge badge-muted">#${i + 1}</span> ${esc(t.artist)}</span>
          <span class="track-title">${esc(t.title)}</span>
        </div>
        <div class="track-ytm">
          ${
            t.video_id
              ? `<a href="https://music.youtube.com/watch?v=${esc(t.video_id)}" target="_blank" rel="noopener">${esc(t.yt_title || t.title)}</a>`
              : `<span class="text-muted">${_("Not found")}</span>`
          }
          <span class="track-ytm-id">
            <span class="badge badge-success">${_("seen")} ${t.times_found}×</span>
          </span>
        </div>
      </div>`,
      )
      .join("")
  } catch (_e) {
    list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("Failed to load top tracks")}</p></div>`
  }
}

async function loadHistoryTrend() {
  const container = document.getElementById("historyTrendChart")
  const legend = document.getElementById("historyTrendLegend")
  if (!container) return

  const requestedDays = trendDays

  try {
    await getDateTimePrefs()
    const r = await fetch(`/api/history/trend?days=${requestedDays}`)
    if (!r.ok) return
    const data = await r.json()

    if (!data.trend.length) {
      container.innerHTML = `<div class="empty-state"><p class="text-muted">${_("No sync data yet")}</p></div>`
      if (legend) legend.innerHTML = ""
      return
    }

    const padded = padTrendToRange(data.trend, requestedDays)
    renderTrendCanvas(container, padded)

    if (legend) {
      legend.innerHTML = `
        <span class="trend-legend-item"><span class="trend-dot" style="background:#4ade80"></span> ${_("Success")}</span>
        <span class="trend-legend-item"><span class="trend-dot" style="background:#ef4444"></span> ${_("Error")}</span>
        <span class="trend-legend-item"><span class="trend-dot" style="background:#a78bfa"></span> ${_("Cache Rate")} (%)</span>
        <span class="trend-legend-item"><span class="trend-dot" style="background:#60a5fa"></span> ${_("Avg Duration")} (s)</span>
      `
    }
  } catch (_e) {
    container.innerHTML = `<div class="empty-state"><p class="text-muted">${_("Failed to load trend data")}</p></div>`
  }
}

function padTrendToRange(trend, days) {
  const byDate = new Map()
  for (const d of trend) byDate.set(d.date, d)

  const out = []
  const today = new Date()
  const end = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())
  const dayMs = 86400000
  for (let i = days - 1; i >= 0; i--) {
    const ts = end - i * dayMs
    const dt = new Date(ts)
    const iso = `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}-${String(dt.getUTCDate()).padStart(2, "0")}`
    const existing = byDate.get(iso)
    if (existing) {
      out.push(existing)
    } else {
      out.push({
        date: iso,
        total: 0,
        success: 0,
        error: 0,
        avg_duration: null,
        avg_resolved: null,
        avg_missed: null,
        avg_cache_rate: null,
        empty: true,
      })
    }
  }
  return out
}

function renderTrendCanvas(container, trend) {
  if (container._trendResizeObserver) {
    container._trendResizeObserver.disconnect()
    container._trendResizeObserver = null
  }
  container.innerHTML = ""

  const wrapper = document.createElement("div")
  wrapper.className = "trend-canvas-wrap"
  container.appendChild(wrapper)

  const canvas = document.createElement("canvas")
  canvas.className = "trend-canvas"
  wrapper.appendChild(canvas)

  const tooltip = document.createElement("div")
  tooltip.className = "trend-tooltip"
  wrapper.appendChild(tooltip)

  const dpr = window.devicePixelRatio || 1
  const rect = wrapper.getBoundingClientRect()
  const W = rect.width
  const H = 260
  wrapper.style.height = `${H}px`
  canvas.width = W * dpr
  canvas.height = H * dpr
  canvas.style.width = `${W}px`
  canvas.style.height = `${H}px`

  const ctx = canvas.getContext("2d")
  ctx.scale(dpr, dpr)

  const pad = { top: 16, right: 56, bottom: 32, left: 48 }
  const plotW = W - pad.left - pad.right
  const plotH = H - pad.top - pad.bottom

  const cs = getComputedStyle(document.documentElement)
  const colSuccess = "#4ade80"
  const colError = "#ef4444"
  const colCache = "#a78bfa"
  const colDuration = "#60a5fa"
  const colGrid = cs.getPropertyValue("--border").trim() || "#27272a"
  const colText = cs.getPropertyValue("--text-muted").trim() || "#71717a"

  const maxSyncs = niceMax(Math.max(...trend.map(d => d.total), 1))
  const maxDur = niceMax(Math.max(...trend.map(d => d.avg_duration || 0), 1))

  const n = trend.length
  const barGap = Math.max(2, Math.min(6, (plotW / n) * 0.2))
  const barW = Math.min(12, Math.max(3, ((plotW - barGap * (n + 1)) / n) * 0.5))
  const stepX = (plotW - barGap * 2) / Math.max(n - 1, 1)

  function xPos(i) {
    return pad.left + barGap + i * stepX
  }

  function yLeft(v) {
    return pad.top + plotH - (v / maxSyncs) * plotH
  }

  function yRight(v, max) {
    return pad.top + plotH - (v / max) * plotH
  }

  ctx.font = "11px system-ui, sans-serif"
  ctx.textBaseline = "middle"
  const gridSteps = 4
  for (let i = 0; i <= gridSteps; i++) {
    const v = (maxSyncs / gridSteps) * i
    const y = yLeft(v)
    ctx.strokeStyle = colGrid
    ctx.lineWidth = 0.5
    ctx.beginPath()
    ctx.moveTo(pad.left, y)
    ctx.lineTo(W - pad.right, y)
    ctx.stroke()
    ctx.fillStyle = colText
    ctx.textAlign = "right"
    ctx.fillText(formatAxisVal(v), pad.left - 6, y)
  }

  ctx.textAlign = "left"
  for (let i = 0; i <= gridSteps; i++) {
    const v = (maxDur / gridSteps) * i
    const y = yRight(v, maxDur)
    ctx.fillStyle = colText
    ctx.fillText(`${formatAxisVal(v)}s`, W - pad.right + 6, y)
  }

  ctx.textAlign = "center"
  ctx.textBaseline = "top"
  const maxLabels = Math.floor(plotW / 48)
  const labelStep = Math.max(1, Math.ceil(n / maxLabels))
  for (let i = 0; i < n; i++) {
    if (i % labelStep !== 0 && i !== n - 1) continue
    const x = xPos(i)
    ctx.fillStyle = colText
    ctx.fillText(formatTrendAxisDate(trend[i].date), x, pad.top + plotH + 8)
  }

  for (let i = 0; i < n; i++) {
    const d = trend[i]
    const x = xPos(i) - barW / 2
    const hSuccess = (d.success / maxSyncs) * plotH
    const hError = (d.error / maxSyncs) * plotH

    if (d.error > 0) {
      ctx.fillStyle = colError
      ctx.globalAlpha = 0.45
      roundRect(ctx, x, yLeft(d.error), barW, hError, 2)
      ctx.fill()
    }

    if (d.success > 0) {
      ctx.fillStyle = colSuccess
      ctx.globalAlpha = 0.45
      roundRect(ctx, x, yLeft(d.total), barW, hSuccess, 2)
      ctx.fill()
    }
    ctx.globalAlpha = 1
  }

  drawLine(
    ctx,
    trend,
    i => xPos(i),
    i => (trend[i].avg_cache_rate == null ? null : yRight(trend[i].avg_cache_rate, 100)),
    colCache,
    2,
  )

  drawLine(
    ctx,
    trend,
    i => xPos(i),
    i => (trend[i].avg_duration == null ? null : yRight(trend[i].avg_duration, maxDur)),
    colDuration,
    2,
  )

  for (let i = 0; i < n; i++) {
    if (trend[i].avg_cache_rate != null) dot(ctx, xPos(i), yRight(trend[i].avg_cache_rate, 100), colCache, 3)
    if (trend[i].avg_duration != null) dot(ctx, xPos(i), yRight(trend[i].avg_duration, maxDur), colDuration, 3)
  }

  let activeIdx = -1

  canvas.addEventListener("mousemove", e => {
    const bnd = canvas.getBoundingClientRect()
    const mx = e.clientX - bnd.left
    const my = e.clientY - bnd.top

    let closest = -1
    let closestDist = Number.POSITIVE_INFINITY
    for (let i = 0; i < n; i++) {
      const dist = Math.abs(mx - xPos(i))
      if (dist < closestDist) {
        closestDist = dist
        closest = i
      }
    }

    if (closestDist > Math.max(stepX * 0.6, 20)) closest = -1

    const idxChanged = closest !== activeIdx
    activeIdx = closest

    if (closest < 0) {
      tooltip.classList.remove("visible")
      if (idxChanged) redraw()
      return
    }

    if (idxChanged) {
      redraw()
      const cx = xPos(closest)
      ctx.strokeStyle = colText
      ctx.lineWidth = 0.5
      ctx.globalAlpha = 0.4
      ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.moveTo(cx, pad.top)
      ctx.lineTo(cx, pad.top + plotH)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.globalAlpha = 1

      const d = trend[closest]
      if (d.avg_cache_rate != null) dot(ctx, cx, yRight(d.avg_cache_rate, 100), colCache, 5)
      if (d.avg_duration != null) dot(ctx, cx, yRight(d.avg_duration, maxDur), colDuration, 5)

      const cacheRate = d.avg_cache_rate ?? "–"
      tooltip.innerHTML = `
        <div class="trend-tip-date">${esc(formatTrendTipDate(d.date))}</div>
        <div class="trend-tip-row"><span style="color:${colSuccess}">${_("Success")}</span> ${d.success}</div>
        <div class="trend-tip-row"><span style="color:${colError}">${_("Error")}</span> ${d.error}</div>
        <div class="trend-tip-row"><span style="color:${colCache}">${_("Cache Rate")}</span> ${cacheRate === "–" ? "–" : `${cacheRate}%`}</div>
        <div class="trend-tip-row"><span style="color:${colDuration}">${_("Avg Duration")}</span> ${d.avg_duration ?? "–"}${d.avg_duration == null ? "" : "s"}</div>
        <div class="trend-tip-row"><span>${_("Avg Resolved")}</span> ${d.avg_resolved ?? "–"}</div>
        <div class="trend-tip-row"><span>${_("Avg Missed")}</span> ${d.avg_missed ?? "–"}</div>
      `
      tooltip.classList.add("visible")
    }

    const cx = xPos(closest)
    const tipW = tooltip.offsetWidth
    let tx = cx + 12
    if (tx + tipW > W - 4) tx = cx - tipW - 12
    let ty = my - 10
    if (ty < 0) ty = 4
    tooltip.style.left = `${tx}px`
    tooltip.style.top = `${ty}px`
  })

  canvas.addEventListener("mouseleave", () => {
    activeIdx = -1
    tooltip.classList.remove("visible")
    redraw()
  })

  function redraw() {
    ctx.clearRect(0, 0, W, H)
    ctx.save()

    for (let i = 0; i <= gridSteps; i++) {
      const v = (maxSyncs / gridSteps) * i
      const y = yLeft(v)
      ctx.strokeStyle = colGrid
      ctx.lineWidth = 0.5
      ctx.beginPath()
      ctx.moveTo(pad.left, y)
      ctx.lineTo(W - pad.right, y)
      ctx.stroke()
      ctx.fillStyle = colText
      ctx.font = "11px system-ui, sans-serif"
      ctx.textAlign = "right"
      ctx.textBaseline = "middle"
      ctx.fillText(formatAxisVal(v), pad.left - 6, y)
    }

    ctx.textAlign = "left"
    for (let i = 0; i <= gridSteps; i++) {
      const v = (maxDur / gridSteps) * i
      const y = yRight(v, maxDur)
      ctx.fillStyle = colText
      ctx.fillText(`${formatAxisVal(v)}s`, W - pad.right + 6, y)
    }

    ctx.textAlign = "center"
    ctx.textBaseline = "top"
    for (let i = 0; i < n; i++) {
      if (i % labelStep !== 0 && i !== n - 1) continue
      ctx.fillStyle = colText
      ctx.fillText(formatTrendAxisDate(trend[i].date), xPos(i), pad.top + plotH + 8)
    }

    for (let i = 0; i < n; i++) {
      const d = trend[i]
      const x = xPos(i) - barW / 2
      const hSuccess = (d.success / maxSyncs) * plotH
      const hError = (d.error / maxSyncs) * plotH
      const alpha = activeIdx >= 0 && activeIdx !== i ? 0.2 : 0.45

      if (d.error > 0) {
        ctx.fillStyle = colError
        ctx.globalAlpha = alpha
        roundRect(ctx, x, yLeft(d.error), barW, hError, 2)
        ctx.fill()
      }

      if (d.success > 0) {
        ctx.fillStyle = colSuccess
        ctx.globalAlpha = alpha
        roundRect(ctx, x, yLeft(d.total), barW, hSuccess, 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    drawLine(
      ctx,
      trend,
      i => xPos(i),
      i => (trend[i].avg_cache_rate == null ? null : yRight(trend[i].avg_cache_rate, 100)),
      colCache,
      2,
    )
    drawLine(
      ctx,
      trend,
      i => xPos(i),
      i => (trend[i].avg_duration == null ? null : yRight(trend[i].avg_duration, maxDur)),
      colDuration,
      2,
    )

    for (let i = 0; i < n; i++) {
      if (trend[i].avg_cache_rate != null) dot(ctx, xPos(i), yRight(trend[i].avg_cache_rate, 100), colCache, 3)
      if (trend[i].avg_duration != null) dot(ctx, xPos(i), yRight(trend[i].avg_duration, maxDur), colDuration, 3)
    }

    ctx.restore()
  }

  const ro = new ResizeObserver(() => {
    if (!wrapper.isConnected) return
    const newRect = wrapper.getBoundingClientRect()
    if (newRect.width <= 0) return
    if (Math.abs(newRect.width - W) > 2) {
      renderTrendCanvas(container, trend)
    }
  })
  ro.observe(wrapper)
  container._trendResizeObserver = ro
}

function drawLine(ctx, data, xFn, yFn, color, width) {
  ctx.strokeStyle = color
  ctx.lineWidth = width
  ctx.lineJoin = "round"
  ctx.lineCap = "round"
  let drawing = false
  ctx.beginPath()
  for (let i = 0; i < data.length; i++) {
    const y = yFn(i)
    if (y == null) {
      drawing = false
      continue
    }
    const x = xFn(i)
    if (!drawing) {
      ctx.moveTo(x, y)
      drawing = true
    } else {
      ctx.lineTo(x, y)
    }
  }
  ctx.stroke()
}

function dot(ctx, x, y, color, r) {
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fillStyle = color
  ctx.fill()
}

function roundRect(ctx, x, y, w, h, r) {
  if (h <= 0) return
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.lineTo(x + w - r, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + r)
  ctx.lineTo(x + w, y + h)
  ctx.lineTo(x, y + h)
  ctx.lineTo(x, y + r)
  ctx.quadraticCurveTo(x, y, x + r, y)
  ctx.closePath()
}

function niceMax(v) {
  if (v <= 0) return 1
  const mag = 10 ** Math.floor(Math.log10(v))
  const norm = v / mag
  if (norm <= 1) return mag
  if (norm <= 2) return 2 * mag
  if (norm <= 5) return 5 * mag
  return 10 * mag
}

function formatAxisVal(v) {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  if (Number.isInteger(v)) return String(v)
  return v.toFixed(1)
}

export async function historyBackfill() {
  try {
    const r = await fetch("/api/history/backfill", { method: "POST" })
    if (!r.ok) {
      const data = await r.json()
      throw new Error(data.error || _("Backfill failed"))
    }
    const data = await r.json()
    showToast(`${_("Backfill complete:")} ${data.cache_entries} ${_("cache")} + ${data.override_entries} ${_("override entries")}`, "success")
    await refreshHistoryPanelState()
  } catch (e) {
    showToast(e.message || _("Backfill failed"), "error")
  }
}

export async function refreshHistoryPanelState() {
  const refreshed = await refreshPanel("history")
  if (refreshed) {
    initHistory()
  }
  await loadHistoryData()
}

export async function clearHistory() {
  showModal("clearHistoryModal")
}

export async function confirmClearHistory() {
  closeModal("clearHistoryModal")
  try {
    const r = await fetch("/api/history/clear", { method: "POST" })
    if (!r.ok) {
      const data = await r.json()
      throw new Error(data.error || _("Failed to clear history"))
    }
    showToast(_("History cleared"), "success")
    await refreshHistoryPanelState()
  } catch (e) {
    showToast(e.message || _("Failed to clear history"), "error")
  }
}

export async function historyVacuum() {
  try {
    const r = await fetch("/api/history/vacuum", { method: "POST" })
    if (!r.ok) {
      const data = await r.json()
      throw new Error(data.error || _("Vacuum failed"))
    }
    const data = await r.json()
    const total = (data.actions_pruned || 0) + (data.syncs_pruned || 0) + (data.size_pruned_rows || 0)
    showToast(`${_("Vacuum complete:")} ${total} ${_("rows pruned")}`, "success")
    await refreshHistoryPanelState()
  } catch (e) {
    showToast(e.message || _("Vacuum failed"), "error")
  }
}

export function historyExport() {
  window.location.href = "/api/history/export"
}

export function showHistoryDataModal() {
  pendingHistoryImportFile = null
  const preview = document.getElementById("history-import-preview")
  if (preview) preview.style.display = "none"
  const dropzone = document.getElementById("history-import-dropzone")
  if (dropzone) dropzone.classList.remove("dragover")
  showModal("historyDataModal")
}

let pendingHistoryImportFile = null
let _historyDropzoneInited = false

export function initHistoryImportDropzone() {
  if (_historyDropzoneInited) return
  const dropzone = document.getElementById("history-import-dropzone")
  const fileInput = document.getElementById("history-import-file-input")
  if (!dropzone || !fileInput) return
  _historyDropzoneInited = true

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
    if (file) _previewHistoryImportFile(file)
  })
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0]
    if (file) _previewHistoryImportFile(file)
    fileInput.value = ""
  })
}

function _previewHistoryImportFile(file) {
  if (!file.name.endsWith(".json")) {
    showToast(_("Please select a JSON file"), "error")
    return
  }
  const reader = new FileReader()
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result)
      const tables = data?.tables || {}
      const tCount = tables.tracks?.length || 0
      const sCount = tables.syncs?.length || 0
      const aCount = tables.actions?.length || 0
      pendingHistoryImportFile = file
      const statsEl = document.getElementById("history-import-stats")
      if (statsEl) {
        statsEl.innerHTML = `
          <p><strong>${esc(file.name)}</strong></p>
          <p>${_("Tracks")}: <strong>${tCount}</strong> &middot; ${_("Syncs")}: <strong>${sCount}</strong> &middot; ${_("Actions")}: <strong>${aCount}</strong></p>
        `
      }
      const preview = document.getElementById("history-import-preview")
      if (preview) preview.style.display = ""
    } catch (_err) {
      showToast(_("Invalid JSON file"), "error")
    }
  }
  reader.readAsText(file)
}

export async function confirmHistoryImportMerge() {
  await submitHistoryImport("merge")
}

export async function confirmHistoryImportReplace() {
  await submitHistoryImport("replace")
}

async function submitHistoryImport(mode) {
  const file = pendingHistoryImportFile
  if (!file) return
  try {
    const fd = new FormData()
    fd.append("file", file)
    fd.append("mode", mode)
    const r = await fetch("/api/history/import", { method: "POST", body: fd })
    const data = await r.json()
    if (!r.ok) {
      throw new Error(data.error || _("Import failed"))
    }
    showToast(`${_("Imported:")} ${data.tracks} ${_("tracks")} + ${data.syncs} ${_("syncs")} + ${data.actions} ${_("actions")}`, "success")
    pendingHistoryImportFile = null
    const preview = document.getElementById("history-import-preview")
    if (preview) preview.style.display = "none"
    closeModal("historyDataModal")
    await refreshHistoryPanelState()
  } catch (e) {
    showToast(e.message || _("Import failed"), "error")
  }
}

export function setHistoryTabVisibility(enabled) {
  const historyTab = document.getElementById("historyTab")
  if (historyTab) {
    historyTab.hidden = !enabled
  }

  if (!enabled) {
    const activeTab = document.querySelector(".tab.active")
    if (activeTab?.dataset.tab === "history" && window.switchTab) {
      window.switchTab("playlist")
    }
  }
}

function setText(id, val) {
  const el = document.getElementById(id)
  if (el) el.textContent = val ?? "–"
}

function esc(str) {
  if (!str) return ""
  const d = document.createElement("div")
  d.textContent = str
  return d.innerHTML
}

function escAttr(str) {
  return esc(str).replaceAll('"', "&quot;")
}

function sourceBadge(source) {
  const map = { search: "search", cache: "cached", override: "override", cache_backfill: "muted", override_backfill: "muted" }
  return map[source] || "muted"
}

function actionLabel(type) {
  const labels = {
    override_add: _("Added override"),
    override_remove: _("Removed override"),
    blacklist_add: _("Blacklisted"),
    blacklist_remove: _("Unblacklisted"),
    cache_clear: _("Cleared cache entry"),
    tag_override_add: _("Added tag override"),
    tag_override_remove: _("Removed tag override"),
    tag_cache_clear: _("Cleared tag cache"),
    backfill_from_cache: _("Backfill from cache"),
    backfill_from_overrides: _("Backfill from overrides"),
    sync_start: _("Sync started"),
    sync_complete: _("Sync completed"),
    sync_error: _("Sync failed"),
    custom_playlist_sync: _("Custom playlist synced"),
    custom_playlist_error: _("Custom playlist failed"),
    substitution: _("YouTube substitution"),
  }
  return labels[type] || type.replace(/_/g, " ")
}

function formatShortDate(isoStr, prefs) {
  if (!isoStr) return "–"
  try {
    return formatDateTime(new Date(isoStr), prefs)
  } catch (_e) {
    return isoStr.slice(0, 16)
  }
}

function _parseIsoDateOnly(iso) {
  const [y, m, d] = iso.split("-").map(Number)
  return new Date(y, (m || 1) - 1, d || 1)
}

function formatTrendAxisDate(iso) {
  const prefs = getDateTimePrefsSync()
  const date = _parseIsoDateOnly(iso)
  if (prefs.dateFormat === "DMY") {
    return `${String(date.getDate()).padStart(2, "0")}/${String(date.getMonth() + 1).padStart(2, "0")}`
  }
  if (prefs.dateFormat === "MDY") {
    return `${String(date.getMonth() + 1).padStart(2, "0")}/${String(date.getDate()).padStart(2, "0")}`
  }
  return iso.slice(5)
}

function formatTrendTipDate(iso) {
  const prefs = getDateTimePrefsSync()
  const date = _parseIsoDateOnly(iso)
  if (prefs.dateFormat === "DMY") {
    return date.toLocaleDateString("en-GB", { year: "numeric", month: "2-digit", day: "2-digit" })
  }
  if (prefs.dateFormat === "MDY") {
    return date.toLocaleDateString("en-US", { year: "numeric", month: "2-digit", day: "2-digit" })
  }
  return iso
}

function setPagination(containerId, total, currentPage, onPageChange) {
  const container = document.getElementById(containerId)
  if (!container) return

  const totalPages = Math.ceil(total / PAGE_SIZE)
  if (totalPages <= 1) {
    container.innerHTML = ""
    return
  }

  const prev = currentPage > 0 ? `<button class="btn btn-sm btn-secondary" data-page="${currentPage - 1}">${_("Previous")}</button>` : ""
  const next = currentPage < totalPages - 1 ? `<button class="btn btn-sm btn-secondary" data-page="${currentPage + 1}">${_("Next")}</button>` : ""

  container.innerHTML = `
    <div class="pagination-controls">
      ${prev}
      <span class="text-muted">${currentPage + 1} / ${totalPages} (${total} ${_("total")})</span>
      ${next}
    </div>`

  for (const btn of container.querySelectorAll("[data-page]")) {
    btn.addEventListener("click", () => onPageChange(Number.parseInt(btn.dataset.page, 10)))
  }
}
