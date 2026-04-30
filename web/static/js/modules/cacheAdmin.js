import { _ } from "./i18n.js"
import { showModal } from "./modals.js"
import { escapeHtml, formatDateTime, getDateTimePrefs, getDateTimePrefsSync, refreshPanel, refreshStats, showToast } from "./utils.js"

const PANELS = ["search", "tags", "playlists"]

const state = {
  search: { items: [], selected: new Set(), filter: "" },
  tags: { items: [], selected: new Set(), filter: "" },
  playlists: { items: [], filter: "", expanded: new Map() },
  loaded: false,
}

function setActiveTab(tabId) {
  for (const btn of document.querySelectorAll(".cache-admin-tab")) {
    btn.classList.toggle("active", btn.dataset.cacheTab === tabId)
  }
  for (const panel of document.querySelectorAll(".cache-admin-panel")) {
    panel.hidden = panel.dataset.cachePanel !== tabId
  }
}

function fmtCount(n) {
  return new Intl.NumberFormat().format(n)
}

async function fetchJson(url, opts = {}) {
  const r = await fetch(url, opts)
  if (!r.ok) {
    const data = await r.json().catch(() => ({}))
    throw new Error(data.error || `HTTP ${r.status}`)
  }
  return r.json()
}

function harvestSearchCacheItemsFromDom() {
  const items = []
  const seen = new Set()

  for (const el of document.querySelectorAll("#cacheTracks .cache-item")) {
    const artist = el.dataset.originalArtist || ""
    const title = el.dataset.originalTitle || ""
    const videoId = el.dataset.videoid || ""
    const key = `${artist.toLowerCase()}|${title.toLowerCase()}`
    if (seen.has(key)) continue
    seen.add(key)
    items.push({ key, artist, title, video_id: videoId, kind: "found" })
  }

  for (const el of document.querySelectorAll("#notfoundTracks .notfound-item")) {
    const artist = el.dataset.originalArtist || ""
    const title = el.dataset.originalTitle || ""
    const key = `${artist.toLowerCase()}|${title.toLowerCase()}`
    if (seen.has(key)) continue
    seen.add(key)
    items.push({ key, artist, title, video_id: "", kind: "notfound" })
  }

  return items
}

function harvestTagCacheItemsFromDom() {
  const items = []
  const seen = new Set()
  for (const el of document.querySelectorAll("#tagsTracks .tag-item")) {
    const artist = el.dataset.originalArtist || ""
    const title = el.dataset.originalTitle || ""
    const key = `${artist.toLowerCase()}|${title.toLowerCase()}`
    if (seen.has(key)) continue
    seen.add(key)
    const tagsRaw = el.dataset.tags || ""
    const tags = tagsRaw
      .split(",")
      .map(t => t.trim())
      .filter(Boolean)
    items.push({ key, artist, title, tags })
  }
  return items
}

const PANEL_DOM_IDS = {
  search: "cacheTracks",
  notfound: "notfoundTracks",
  tags: "tagsTracks",
}

async function ensurePanelHarvested(panelName) {
  const id = PANEL_DOM_IDS[panelName] || ""
  if (!document.getElementById(id)) {
    await refreshPanel(panelName === "search" ? "cache" : panelName)
  }
}

async function loadAndRender() {
  const stats = await fetchJson("/api/cache/summary")
  renderStats(stats)
  state.playlists.items = stats.playlists || []

  await Promise.all([ensurePanelHarvested("search"), ensurePanelHarvested("notfound"), ensurePanelHarvested("tags"), getDateTimePrefs()])

  state.search.items = harvestSearchCacheItemsFromDom()
  state.tags.items = harvestTagCacheItemsFromDom()
  state.search.selected.clear()
  state.tags.selected.clear()

  renderSearchList()
  renderTagsList()
  renderPlaylistsList()
}

function renderStats(summary) {
  const s = summary.search || { total: 0, found: 0, not_found: 0 }
  const t = summary.tags || { total: 0, with_tags: 0, empty: 0 }
  const pl = summary.playlists || []

  const sEl = document.getElementById("cacheAdminSearchStats")
  if (sEl) {
    sEl.textContent = _("%(total)s entries · %(found)s found · %(nf)s not-found", {
      total: fmtCount(s.total),
      found: fmtCount(s.found),
      nf: fmtCount(s.not_found),
    })
  }
  const tEl = document.getElementById("cacheAdminTagsStats")
  if (tEl) {
    tEl.textContent = _("%(total)s entries · %(with)s with tags · %(empty)s empty", {
      total: fmtCount(t.total),
      with: fmtCount(t.with_tags),
      empty: fmtCount(t.empty),
    })
  }
  const pEl = document.getElementById("cacheAdminPlaylistsStats")
  if (pEl) {
    const totalVids = pl.reduce((acc, p) => acc + (p.video_count || 0), 0)
    pEl.textContent = _("%(n)s playlists · %(v)s cached video IDs", {
      n: fmtCount(pl.length),
      v: fmtCount(totalVids),
    })
  }
}

function renderSearchList() {
  const list = document.getElementById("cacheAdminSearchList")
  if (!list) return
  const filter = state.search.filter.toLowerCase().trim()
  const visible = state.search.items.filter(it => {
    if (!filter) return true
    return it.artist.toLowerCase().includes(filter) || it.title.toLowerCase().includes(filter)
  })

  if (visible.length === 0) {
    list.innerHTML = `<div class="cache-admin-empty">${_("No entries.")}</div>`
    updateSearchSelectionUi()
    return
  }

  list.innerHTML = visible
    .map(it => {
      const checked = state.search.selected.has(it.key) ? " checked" : ""
      const badge =
        it.kind === "notfound"
          ? `<span class="badge badge-notfound">${_("Not Found")}</span>`
          : `<span class="badge badge-cached">${_("Cached")}</span>`
      return `<label class="cache-admin-row">
        <input type="checkbox" data-cache-key="${escapeHtml(it.key)}"${checked}>
        <span class="cache-admin-row-main">
          <span class="cache-admin-row-artist">${escapeHtml(it.artist)}</span>
          <span class="cache-admin-row-title">${escapeHtml(it.title)}</span>
        </span>
        <span class="cache-admin-row-meta">${badge}</span>
      </label>`
    })
    .join("")

  for (const cb of list.querySelectorAll('input[type="checkbox"]')) {
    cb.addEventListener("change", () => {
      const k = cb.dataset.cacheKey
      if (cb.checked) state.search.selected.add(k)
      else state.search.selected.delete(k)
      updateSearchSelectionUi()
    })
  }
  updateSearchSelectionUi()
}

function updateSearchSelectionUi() {
  const count = state.search.selected.size
  const lbl = document.getElementById("cacheAdminSearchSelectedCount")
  if (lbl) lbl.textContent = `${fmtCount(count)} ${_("selected")}`
  const btn = document.getElementById("cacheAdminSearchBulkBtn")
  if (btn) btn.disabled = count === 0
}

function renderTagsList() {
  const list = document.getElementById("cacheAdminTagsList")
  if (!list) return
  const filter = state.tags.filter.toLowerCase().trim()
  const visible = state.tags.items.filter(it => {
    if (!filter) return true
    if (it.artist.toLowerCase().includes(filter)) return true
    if (it.title.toLowerCase().includes(filter)) return true
    return it.tags.some(t => t.includes(filter))
  })

  if (visible.length === 0) {
    list.innerHTML = `<div class="cache-admin-empty">${_("No entries.")}</div>`
    updateTagsSelectionUi()
    return
  }

  list.innerHTML = visible
    .map(it => {
      const checked = state.tags.selected.has(it.key) ? " checked" : ""
      const tagsHtml =
        it.tags.length > 0
          ? `<span class="cache-admin-row-tags">${it.tags
              .slice(0, 6)
              .map(t => `<span class="cache-admin-tag-pill">${escapeHtml(t)}</span>`)
              .join("")}${
              it.tags.length > 6 ? `<span class="cache-admin-tag-pill cache-admin-tag-pill-more">+${it.tags.length - 6}</span>` : ""
            }</span>`
          : `<span class="cache-admin-row-meta">${_("No tags")}</span>`
      return `<label class="cache-admin-row cache-admin-row--tags">
        <input type="checkbox" data-cache-key="${escapeHtml(it.key)}"${checked}>
        <span class="cache-admin-row-main">
          <span class="cache-admin-row-artist">${escapeHtml(it.artist)}</span>
          <span class="cache-admin-row-title">${escapeHtml(it.title)}</span>
        </span>
        ${tagsHtml}
      </label>`
    })
    .join("")

  for (const cb of list.querySelectorAll('input[type="checkbox"]')) {
    cb.addEventListener("change", () => {
      const k = cb.dataset.cacheKey
      if (cb.checked) state.tags.selected.add(k)
      else state.tags.selected.delete(k)
      updateTagsSelectionUi()
    })
  }
  updateTagsSelectionUi()
}

function updateTagsSelectionUi() {
  const count = state.tags.selected.size
  const lbl = document.getElementById("cacheAdminTagsSelectedCount")
  if (lbl) lbl.textContent = `${fmtCount(count)} ${_("selected")}`
  const btn = document.getElementById("cacheAdminTagsBulkBtn")
  if (btn) btn.disabled = count === 0
}

function renderPlaylistsList() {
  const list = document.getElementById("cacheAdminPlaylistsList")
  if (!list) return
  const filter = state.playlists.filter.toLowerCase().trim()
  const visible = state.playlists.items.filter(p => !filter || p.name.toLowerCase().includes(filter))

  if (visible.length === 0) {
    list.innerHTML = `<div class="cache-admin-empty">${_("No cached playlists.")}</div>`
    return
  }

  list.innerHTML = visible
    .map(p => {
      const safeName = escapeHtml(p.name)
      const updated = p.last_updated ? formatDateTime(new Date(p.last_updated), getDateTimePrefsSync()) : "-"
      const expanded = state.playlists.expanded.has(p.name)
      const tracksHtml = expanded ? renderPlaylistTracksHtml(p.name) : ""
      return `<div class="cache-admin-playlist" data-pl-name="${safeName}">
        <div class="cache-admin-playlist-header">
          <button type="button" class="cache-admin-pl-toggle" data-action="cacheAdminTogglePlaylist" data-name="${safeName}">
            <span class="cache-admin-pl-arrow">${expanded ? "▾" : "▸"}</span>
            <span class="cache-admin-pl-name">${safeName}</span>
            <span class="cache-admin-pl-count">${fmtCount(p.video_count)} ${_("tracks")}</span>
          </button>
          <span class="cache-admin-pl-meta">${updated}</span>
          <button type="button" class="btn btn-danger btn-sm" data-action="cacheRemovePlaylist" data-name="${safeName}">
            ${_("Remove from cache")}
          </button>
        </div>
        <div class="cache-admin-pl-tracks" data-tracks-for="${safeName}">${tracksHtml}</div>
      </div>`
    })
    .join("")
}

function renderPlaylistTracksHtml(name) {
  const cached = state.playlists.expanded.get(name)
  if (cached === "loading") return `<div class="cache-admin-empty">${_("Loading...")}</div>`
  if (cached === "error") return `<div class="cache-admin-empty">${_("Failed to load tracks.")}</div>`
  if (!Array.isArray(cached) || cached.length === 0) {
    return `<div class="cache-admin-empty">${_("No cached tracks.")}</div>`
  }
  const safeName = escapeHtml(name)
  return cached
    .map(t => {
      const artist = escapeHtml(t.artist || "")
      const title = escapeHtml(t.title || t.yt_title || t.video_id)
      const vid = escapeHtml(t.video_id)
      return `<div class="cache-admin-pl-track">
        <span class="cache-admin-row-main">
          <span class="cache-admin-row-artist">${artist || `<em>${_("Unknown")}</em>`}</span>
          <span class="cache-admin-row-title">${title}</span>
        </span>
        <span class="cache-admin-row-vid">${vid}</span>
        <button type="button" class="btn btn-secondary btn-sm" data-action="cacheRemovePlaylistTrack"
          data-name="${safeName}" data-video-id="${vid}" title="${_("Remove from cached template")}">×</button>
      </div>`
    })
    .join("")
}

async function togglePlaylistExpand(name) {
  if (state.playlists.expanded.has(name)) {
    state.playlists.expanded.delete(name)
    renderPlaylistsList()
    return
  }
  state.playlists.expanded.set(name, "loading")
  renderPlaylistsList()
  try {
    const data = await fetchJson(`/api/cache/playlist-tracks?name=${encodeURIComponent(name)}`)
    state.playlists.expanded.set(name, data.tracks || [])
  } catch {
    state.playlists.expanded.set(name, "error")
  }
  renderPlaylistsList()
}

function confirmAction(message) {
  // biome-ignore lint/suspicious/noAlert: Using window.confirm for user confirmation
  return window.confirm(message)
}

async function deleteJson(url, body) {
  const opts = { method: "DELETE" }
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" }
    opts.body = JSON.stringify(body)
  }
  return fetchJson(url, opts)
}

export async function showCacheAdminModal() {
  showModal("cacheAdminModal")
  setActiveTab("search")
  await reloadCacheAdmin()
}

export async function reloadCacheAdmin() {
  try {
    state.playlists.expanded.clear()
    await loadAndRender()
  } catch (e) {
    showToast(_("Failed to load cache data: %(msg)s", { msg: e.message || "" }), "error")
  }
}

export function cacheAdminSwitchTab(tabId) {
  if (PANELS.includes(tabId)) setActiveTab(tabId)
}

export async function cacheClearSearchAll() {
  if (!confirmAction(_("Delete ALL search cache entries? Tracks will be re-searched on the next sync."))) return
  try {
    const r = await deleteJson("/api/cache/search/all")
    showToast(_("Cleared %(n)s search cache entries", { n: r.deleted }), "success")
    await afterMutation(["cache", "notfound", "playlist"])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheClearSearchNotfound() {
  if (!confirmAction(_("Delete all not-found search cache entries?"))) return
  try {
    const r = await deleteJson("/api/cache/search/notfound")
    showToast(_("Cleared %(n)s not-found entries", { n: r.deleted }), "success")
    await afterMutation(["notfound", "cache"])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheBulkDeleteSearch() {
  const keys = [...state.search.selected]
  if (keys.length === 0) return
  if (!confirmAction(_("Delete %(n)s selected search cache entries?", { n: keys.length }))) return
  try {
    const r = await deleteJson("/api/cache/search/bulk", { keys })
    showToast(_("Deleted %(n)s entries", { n: r.deleted }), "success")
    await afterMutation(["cache", "notfound", "playlist"])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheClearTagsAll() {
  if (!confirmAction(_("Delete ALL tag cache entries? Tags will be re-fetched on the next sync."))) return
  try {
    const r = await deleteJson("/api/cache/tags/all")
    showToast(_("Cleared %(n)s tag cache entries", { n: r.deleted }), "success")
    await afterMutation(["tags"])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheBulkDeleteTags() {
  const keys = [...state.tags.selected]
  if (keys.length === 0) return
  if (!confirmAction(_("Delete %(n)s selected tag cache entries?", { n: keys.length }))) return
  try {
    const r = await deleteJson("/api/cache/tags/bulk", { keys })
    showToast(_("Deleted %(n)s entries", { n: r.deleted }), "success")
    await afterMutation(["tags"])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheClearPlaylistAll() {
  if (
    !confirmAction(
      _("Clear the ENTIRE playlist cache? Your YouTube Music playlists will NOT be deleted, but the next sync will need to re-discover their IDs."),
    )
  )
    return
  try {
    const r = await deleteJson("/api/cache/playlist/all")
    showToast(_("Cleared %(n)s playlist cache entries", { n: r.deleted }), "success")
    await afterMutation([])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheRemovePlaylistEntry(name) {
  if (!name) return
  if (!confirmAction(_("Remove playlist '%(n)s' from the cache? The actual YTM playlist is left intact.", { n: name }))) return
  try {
    await deleteJson("/api/cache/playlist/entry", { name })
    showToast(_("Removed '%(n)s' from playlist cache", { n: name }), "success")
    state.playlists.expanded.delete(name)
    await afterMutation([])
  } catch (e) {
    showToast(e.message, "error")
  }
}

export async function cacheRemovePlaylistTrack(name, videoId) {
  if (!name || !videoId) return
  try {
    await deleteJson("/api/cache/playlist/track", { name, video_id: videoId })
    showToast(_("Removed track from cached template"), "success")
    if (state.playlists.expanded.has(name)) {
      state.playlists.expanded.set(name, "loading")
      renderPlaylistsList()
      try {
        const data = await fetchJson(`/api/cache/playlist-tracks?name=${encodeURIComponent(name)}`)
        state.playlists.expanded.set(name, data.tracks || [])
      } catch {
        state.playlists.expanded.set(name, "error")
      }
    }
    const pl = state.playlists.items.find(p => p.name === name)
    if (pl) pl.video_count = Math.max(0, (pl.video_count || 0) - 1)
    renderPlaylistsList()
    refreshStats()
  } catch (e) {
    showToast(e.message, "error")
  }
}

async function afterMutation(panelsToRefresh) {
  for (const p of panelsToRefresh) {
    refreshPanel(p).catch(() => {})
  }
  refreshStats()
  await reloadCacheAdmin()
}

export function initCacheAdmin() {
  document.addEventListener("click", e => {
    const tab = e.target.closest(".cache-admin-tab")
    if (tab?.dataset.cacheTab) {
      setActiveTab(tab.dataset.cacheTab)
    }
  })

  const sFilter = document.getElementById("cacheAdminSearchFilter")
  if (sFilter) {
    sFilter.addEventListener("input", () => {
      state.search.filter = sFilter.value
      renderSearchList()
    })
  }
  const tFilter = document.getElementById("cacheAdminTagsFilter")
  if (tFilter) {
    tFilter.addEventListener("input", () => {
      state.tags.filter = tFilter.value
      renderTagsList()
    })
  }
  const pFilter = document.getElementById("cacheAdminPlaylistsFilter")
  if (pFilter) {
    pFilter.addEventListener("input", () => {
      state.playlists.filter = pFilter.value
      renderPlaylistsList()
    })
  }

  const sSelectAll = document.getElementById("cacheAdminSearchSelectAll")
  if (sSelectAll) {
    sSelectAll.addEventListener("change", () => {
      const list = document.getElementById("cacheAdminSearchList")
      if (!list) return
      for (const cb of list.querySelectorAll('input[type="checkbox"]')) {
        cb.checked = sSelectAll.checked
        const k = cb.dataset.cacheKey
        if (sSelectAll.checked) state.search.selected.add(k)
        else state.search.selected.delete(k)
      }
      updateSearchSelectionUi()
    })
  }
  const tSelectAll = document.getElementById("cacheAdminTagsSelectAll")
  if (tSelectAll) {
    tSelectAll.addEventListener("change", () => {
      const list = document.getElementById("cacheAdminTagsList")
      if (!list) return
      for (const cb of list.querySelectorAll('input[type="checkbox"]')) {
        cb.checked = tSelectAll.checked
        const k = cb.dataset.cacheKey
        if (tSelectAll.checked) state.tags.selected.add(k)
        else state.tags.selected.delete(k)
      }
      updateTagsSelectionUi()
    })
  }
}

export function _onTogglePlaylist(name) {
  return togglePlaylistExpand(name)
}
