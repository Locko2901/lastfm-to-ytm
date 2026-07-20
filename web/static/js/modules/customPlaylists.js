import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { runSyncCustomPlaylists } from "./sync.js"
import { getTagInputValue, setTagInputValue } from "./tagInput.js"
import { refreshPanel, refreshStats, showToast } from "./utils.js"

let playlistsData = []
const loadedPreviews = new Set()

let seedOptionsCache = null
let selectedSeedArtists = []
let selectedSeedTracks = []

export function setPlaylistsData(data) {
  playlistsData = data
}

function currentSeedMode() {
  return document.getElementById("custompl-discovery-seed")?.value || "artists"
}

function isSeedAuto() {
  return document.getElementById("custompl-discovery-auto")?.checked !== false
}

async function ensureSeedOptions() {
  if (seedOptionsCache) return seedOptionsCache
  try {
    const response = await fetch("/api/discovery/seed-options")
    if (!response.ok) throw new Error("failed")
    seedOptionsCache = await response.json()
  } catch (_error) {
    seedOptionsCache = { artists: [], tracks: [], source: "" }
  }
  return seedOptionsCache
}

let seedSelectedIndex = -1

function seedSearchValue() {
  return document.getElementById("custompl-seed-search")?.value || ""
}

function renderSelectedSeeds() {
  const pills = document.getElementById("custompl-seed-pills")
  const input = document.getElementById("custompl-seed-search")
  if (!pills || !input) return
  for (const p of pills.querySelectorAll(".tag-input-pill")) p.remove()
  const mode = currentSeedMode()
  if (mode === "artists") {
    selectedSeedArtists.forEach((name, idx) => {
      pills.insertBefore(
        makeSeedPill(name, () => {
          selectedSeedArtists.splice(idx, 1)
          renderSelectedSeeds()
          renderSeedDropdown(seedSearchValue())
        }),
        input,
      )
    })
  } else {
    selectedSeedTracks.forEach((t, idx) => {
      pills.insertBefore(
        makeSeedPill(`${t.artist} - ${t.track}`, () => {
          selectedSeedTracks.splice(idx, 1)
          renderSelectedSeeds()
          renderSeedDropdown(seedSearchValue())
        }),
        input,
      )
    })
  }
}

function makeSeedPill(label, onRemove) {
  const pill = document.createElement("span")
  pill.className = "tag-input-pill"
  pill.textContent = label
  const btn = document.createElement("button")
  btn.type = "button"
  btn.className = "tag-input-pill-remove"
  btn.setAttribute("aria-label", _("Remove"))
  btn.innerHTML =
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
  btn.addEventListener("click", e => {
    e.stopPropagation()
    onRemove()
  })
  pill.appendChild(btn)
  return pill
}

function seedCandidates(filter) {
  const mode = currentSeedMode()
  const needle = (filter || "").trim().toLowerCase()
  const options = seedOptionsCache || { artists: [], tracks: [] }
  if (mode === "artists") {
    const selected = new Set(selectedSeedArtists.map(a => a.toLowerCase()))
    return (options.artists || [])
      .filter(a => !selected.has(a.toLowerCase()) && (!needle || a.toLowerCase().includes(needle)))
      .slice(0, 60)
      .map(a => ({ label: a, add: () => selectedSeedArtists.push(a) }))
  }
  const selected = new Set(selectedSeedTracks.map(t => `${t.artist.toLowerCase()}|${t.track.toLowerCase()}`))
  return (options.tracks || [])
    .filter(t => {
      const key = `${t.artist.toLowerCase()}|${t.title.toLowerCase()}`
      const hay = `${t.artist} ${t.title}`.toLowerCase()
      return !selected.has(key) && (!needle || hay.includes(needle))
    })
    .slice(0, 60)
    .map(t => ({ label: `${t.artist} - ${t.title}`, add: () => selectedSeedTracks.push({ artist: t.artist, track: t.title }) }))
}

function closeSeedDropdown() {
  const dropdown = document.getElementById("custompl-seed-dropdown")
  if (!dropdown) return
  dropdown.classList.remove("open")
  dropdown.innerHTML = ""
  seedSelectedIndex = -1
}

function renderSeedDropdown(filter) {
  const dropdown = document.getElementById("custompl-seed-dropdown")
  if (!dropdown) return
  seedSelectedIndex = -1
  const items = seedCandidates(filter)
  dropdown.innerHTML = ""
  if (items.length === 0) {
    const hasHistory = seedOptionsCache?.artists?.length || seedOptionsCache?.tracks?.length
    if (!hasHistory) {
      const empty = document.createElement("div")
      empty.className = "tag-input-option"
      empty.textContent = _("No listening history available yet. Enable the local Last.fm database or run a sync to populate options.")
      dropdown.appendChild(empty)
      dropdown.classList.add("open")
      return
    }
    closeSeedDropdown()
    return
  }
  for (const item of items) {
    const opt = document.createElement("div")
    opt.className = "tag-input-option"
    opt.textContent = item.label
    opt.addEventListener("mousedown", e => {
      e.preventDefault()
      item.add()
      const input = document.getElementById("custompl-seed-search")
      if (input) input.value = ""
      renderSelectedSeeds()
      renderSeedDropdown("")
      input?.focus()
    })
    dropdown.appendChild(opt)
  }
  dropdown.classList.add("open")
}

function onSeedKeydown(e) {
  const dropdown = document.getElementById("custompl-seed-dropdown")
  const input = document.getElementById("custompl-seed-search")
  if (!dropdown || !input) return
  const options = dropdown.querySelectorAll(".tag-input-option")
  if (e.key === "ArrowDown") {
    e.preventDefault()
    seedSelectedIndex = Math.min(seedSelectedIndex + 1, options.length - 1)
    updateSeedSelection(options, seedSelectedIndex)
  } else if (e.key === "ArrowUp") {
    e.preventDefault()
    seedSelectedIndex = Math.max(seedSelectedIndex - 1, 0)
    updateSeedSelection(options, seedSelectedIndex)
  } else if (e.key === "Enter") {
    e.preventDefault()
    if (seedSelectedIndex >= 0 && options[seedSelectedIndex]) {
      options[seedSelectedIndex].dispatchEvent(new MouseEvent("mousedown"))
    }
  } else if (e.key === "Backspace" && !input.value) {
    const mode = currentSeedMode()
    const list = mode === "artists" ? selectedSeedArtists : selectedSeedTracks
    if (list.length > 0) {
      list.pop()
      renderSelectedSeeds()
      renderSeedDropdown(seedSearchValue())
    }
  } else if (e.key === "Escape") {
    closeSeedDropdown()
  }
}

function updateSeedSelection(items, index) {
  for (const [i, item] of [...items].entries()) item.classList.toggle("selected", i === index)
}

async function refreshSeedPicker() {
  await ensureSeedOptions()
  renderSelectedSeeds()
}

function applyDiscoverySeedVisibility() {
  const isDiscovery = document.getElementById("custompl-kind")?.value === "discovery"
  const autoGroup = document.getElementById("custompl-discovery-auto-group")
  const manualGroup = document.getElementById("custompl-discovery-manual-group")
  const excludeGroup = document.getElementById("custompl-discovery-exclude-group")
  if (autoGroup) autoGroup.style.display = isDiscovery ? "" : "none"
  if (excludeGroup) excludeGroup.style.display = isDiscovery ? "" : "none"
  const showManual = isDiscovery && !isSeedAuto()
  if (manualGroup) manualGroup.style.display = showManual ? "" : "none"
  if (showManual) refreshSeedPicker()
}

function applyKindVisibility(kind) {
  const isArtists = kind === "artists"
  const isDiscovery = kind === "discovery"
  const isTags = kind === "tags"
  const isFilter = kind === "filter"
  document.getElementById("custompl-tags-group").style.display = isTags ? "" : "none"
  document.getElementById("custompl-match-group").style.display = isTags ? "" : "none"
  document.getElementById("custompl-artists-group").style.display = isArtists ? "" : "none"
  document.getElementById("custompl-discovery-group").style.display = isDiscovery ? "" : "none"
  document.getElementById("custompl-filter-group").style.display = isFilter ? "" : "none"
  document.getElementById("custompl-backfill-group").style.display = isDiscovery || isFilter ? "none" : ""
  applyDiscoverySeedVisibility()
  applyFilterTemplateVisibility()
}

function applyFilterTemplateVisibility() {
  const isFilter = document.getElementById("custompl-kind")?.value === "filter"
  const template = document.getElementById("custompl-filter-template")?.value || "custom"
  const customGroup = document.getElementById("custompl-filter-custom-group")
  if (customGroup) customGroup.style.display = isFilter && template === "custom" ? "" : "none"
}

export function onCustomPlaylistKindChange() {
  applyKindVisibility(document.getElementById("custompl-kind").value)
}

export function onCustomPlaylistFilterTemplateChange() {
  applyFilterTemplateVisibility()
}

function applyLimitVisibility(noLimit) {
  const limitInput = document.getElementById("custompl-limit")
  const limitGroup = document.getElementById("custompl-limit-group")
  if (limitInput) limitInput.disabled = noLimit
  if (limitGroup) limitGroup.style.display = noLimit ? "none" : ""
}

const FILTER_INT_FIELDS = {
  "custompl-filter-min-plays": "min_plays",
  "custompl-filter-max-plays": "max_plays",
  "custompl-filter-played-within": "played_within_days",
  "custompl-filter-not-played-within": "not_played_within_days",
  "custompl-filter-first-within": "first_played_within_days",
  "custompl-filter-first-before": "first_played_before_days",
  "custompl-filter-per-artist": "per_artist_limit",
}

function setFilterInputs(filters) {
  const f = filters || {}
  for (const [id, key] of Object.entries(FILTER_INT_FIELDS)) {
    const el = document.getElementById(id)
    if (el) el.value = Number.isInteger(f[key]) && f[key] >= 0 ? f[key] : 0
  }
  const sort = document.getElementById("custompl-filter-sort")
  if (sort) sort.value = f.sort || "plays"
  const months = document.getElementById("custompl-filter-months")
  if (months) months.value = Array.isArray(f.months) ? f.months.join(", ") : ""
}

function readFilterInputs() {
  const filters = {}
  for (const [id, key] of Object.entries(FILTER_INT_FIELDS)) {
    const raw = parseInt(document.getElementById(id)?.value, 10)
    filters[key] = Number.isFinite(raw) && raw >= 0 ? raw : 0
  }
  filters.sort = document.getElementById("custompl-filter-sort")?.value || "plays"
  const monthsRaw = document.getElementById("custompl-filter-months")?.value || ""
  filters.months = [
    ...new Set(
      monthsRaw
        .split(",")
        .map(m => parseInt(m.trim(), 10))
        .filter(m => Number.isInteger(m) && m >= 1 && m <= 12),
    ),
  ].sort((a, b) => a - b)
  return filters
}

export function showCustomPlaylistModal(editIndex = -1) {
  document.getElementById("custompl-edit-index").value = editIndex
  const limitInput = document.getElementById("custompl-limit")
  const noLimitCheckbox = document.getElementById("custompl-no-limit")
  if (editIndex >= 0 && playlistsData[editIndex]) {
    const pl = playlistsData[editIndex]
    document.getElementById("custompl-modal-title").textContent = _("Edit Custom Playlist")
    document.getElementById("custompl-name").value = pl.name || ""
    document.getElementById("custompl-kind").value = pl.kind || "tags"
    document.getElementById("custompl-description").value = pl.description || ""
    document.getElementById("custompl-privacy").value = pl.privacy || ""
    setTagInputValue("custompl-tags", (pl.tags || []).join(", "))
    setTagInputValue("custompl-artists", (pl.artists || []).join(", "))
    document.getElementById("custompl-match").value = pl.match || "any"
    document.getElementById("custompl-discovery-seed").value = pl.discovery_seed || "artists"
    document.getElementById("custompl-discovery-auto").checked = pl.discovery_seed_auto !== false
    document.getElementById("custompl-discovery-exclude").checked = pl.discovery_exclude_scrobbled !== false
    selectedSeedArtists = [...(pl.discovery_seed_artists || [])]
    selectedSeedTracks = (pl.discovery_seed_tracks || []).map(t => ({ artist: t.artist, track: t.track }))
    document.getElementById("custompl-filter-template").value = pl.filter_template || "custom"
    setFilterInputs(pl.filters)
    const isNoLimit = pl.limit === 0
    noLimitCheckbox.checked = isNoLimit
    limitInput.value = isNoLimit ? 50 : pl.limit || 50
    limitInput.disabled = isNoLimit
    document.getElementById("custompl-backfill").checked = pl.backfill !== false
    document.getElementById("custompl-auto-sync").checked = pl.auto_sync !== false
    document.getElementById("custompl-blacklist").value = (pl.blacklist || []).join("\n")
    document.getElementById("custompl-blacklist-artists").value = (pl.blacklist_artists || []).join("\n")
  } else {
    document.getElementById("custompl-modal-title").textContent = _("Add Custom Playlist")
    document.getElementById("custompl-name").value = ""
    document.getElementById("custompl-kind").value = "tags"
    document.getElementById("custompl-description").value = ""
    document.getElementById("custompl-privacy").value = ""
    setTagInputValue("custompl-tags", "")
    setTagInputValue("custompl-artists", "")
    document.getElementById("custompl-match").value = "any"
    document.getElementById("custompl-discovery-seed").value = "artists"
    document.getElementById("custompl-discovery-auto").checked = true
    document.getElementById("custompl-discovery-exclude").checked = true
    selectedSeedArtists = []
    selectedSeedTracks = []
    noLimitCheckbox.checked = false
    limitInput.value = "50"
    limitInput.disabled = false
    document.getElementById("custompl-backfill").checked = true
    document.getElementById("custompl-auto-sync").checked = true
    document.getElementById("custompl-blacklist").value = ""
    document.getElementById("custompl-blacklist-artists").value = ""
  }
  applyKindVisibility(document.getElementById("custompl-kind").value)
  applyLimitVisibility(document.getElementById("custompl-no-limit").checked)
  const seedSearch = document.getElementById("custompl-seed-search")
  if (seedSearch) seedSearch.value = ""
  closeSeedDropdown()
  showModal("customPlaylistModal")
}

export function editCustomPlaylist(index) {
  showCustomPlaylistModal(index)
}

export async function saveCustomPlaylist() {
  const editIndex = parseInt(document.getElementById("custompl-edit-index").value, 10)
  const name = document.getElementById("custompl-name").value.trim()
  const kind = document.getElementById("custompl-kind").value
  const description = document.getElementById("custompl-description").value.trim()
  const privacy = document.getElementById("custompl-privacy").value || null
  const tagsRaw = getTagInputValue("custompl-tags").trim()
  const artistsRaw = getTagInputValue("custompl-artists").trim()
  const match = document.getElementById("custompl-match").value
  const discoverySeed = document.getElementById("custompl-discovery-seed").value
  const discoverySeedAuto = document.getElementById("custompl-discovery-auto").checked
  const discoveryExcludeScrobbled = document.getElementById("custompl-discovery-exclude").checked
  const noLimit = document.getElementById("custompl-no-limit").checked
  const limit = noLimit ? 0 : parseInt(document.getElementById("custompl-limit").value, 10) || 50
  const backfill = document.getElementById("custompl-backfill").checked
  const autoSync = document.getElementById("custompl-auto-sync").checked
  const blacklistRaw = document.getElementById("custompl-blacklist").value.trim()
  const blacklistArtistsRaw = document.getElementById("custompl-blacklist-artists").value.trim()

  if (!name) {
    showToast(_("Please enter a playlist name"), "error")
    return
  }

  if (kind === "artists" && !artistsRaw) {
    showToast(_("Please enter at least one artist"), "error")
    return
  }

  if (kind === "tags" && !tagsRaw) {
    showToast(_("Please enter at least one tag"), "error")
    return
  }

  const tags = tagsRaw
    .split(",")
    .map(t => t.trim().toLowerCase())
    .filter(Boolean)

  const artists = artistsRaw
    .split(",")
    .map(a => a.trim().toLowerCase())
    .filter(Boolean)

  const blacklist = blacklistRaw
    ? blacklistRaw
        .split("\n")
        .map(l => l.trim())
        .filter(Boolean)
    : []

  const blacklistArtists = blacklistArtistsRaw
    ? blacklistArtistsRaw
        .split("\n")
        .map(l => l.trim())
        .filter(Boolean)
    : []

  const isTags = kind === "tags"
  const isArtists = kind === "artists"
  const isDiscovery = kind === "discovery"
  const isFilter = kind === "filter"

  const filterTemplate = document.getElementById("custompl-filter-template").value || "custom"

  const playlist = {
    name,
    kind,
    description,
    privacy,
    tags: isTags ? tags : [],
    artists: isArtists ? artists : [],
    match: isTags ? match : "any",
    discovery_seed: isDiscovery ? discoverySeed : "artists",
    discovery_seed_auto: isDiscovery ? discoverySeedAuto : true,
    discovery_seed_artists: isDiscovery ? [...selectedSeedArtists] : [],
    discovery_seed_tracks: isDiscovery ? selectedSeedTracks.map(t => ({ artist: t.artist, track: t.track })) : [],
    discovery_exclude_scrobbled: isDiscovery ? discoveryExcludeScrobbled : true,
    filter_template: isFilter ? filterTemplate : "custom",
    filters: isFilter ? readFilterInputs() : {},
    limit,
    backfill,
    auto_sync: autoSync,
    blacklist,
    blacklist_artists: blacklistArtists,
  }

  const updated = [...playlistsData]
  if (editIndex >= 0 && editIndex < updated.length) {
    updated[editIndex] = playlist
  } else {
    updated.push(playlist)
  }

  try {
    const response = await fetch("/api/custom-playlists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlists: updated }),
    })

    if (!response.ok) {
      const data = await response.json().catch(() => ({}))
      throw new Error(data.error || "Failed to save")
    }

    playlistsData = updated
    loadedPreviews.clear()
    closeModal("customPlaylistModal")
    showToast(_("Custom playlist saved!"), "success")
    refreshPanel("custompl")
    refreshStats()
  } catch (err) {
    showToast(err.message || _("Failed to save custom playlist"), "error")
  }
}

let pendingDeleteIndex = -1

export function deleteCustomPlaylist(index, name) {
  pendingDeleteIndex = index
  document.getElementById("delete-pl-name").textContent = name
  document.getElementById("delete-pl-from-ytm").checked = false
  showModal("deletePlaylistModal")
}

export async function confirmDeletePlaylist() {
  if (pendingDeleteIndex < 0) return
  const index = pendingDeleteIndex
  const deleteFromYtm = document.getElementById("delete-pl-from-ytm").checked
  closeModal("deletePlaylistModal")

  try {
    const response = await fetch(`/api/custom-playlists/${index}`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delete_from_ytm: deleteFromYtm }),
    })

    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.error || "Failed to delete")

    playlistsData = playlistsData.filter((_, i) => i !== index)
    loadedPreviews.clear()

    if (data.warnings?.length) {
      for (const w of data.warnings) showToast(w, "error")
    }
    showToast(_("Custom playlist deleted"), "success")
    refreshPanel("custompl")
    refreshStats()
  } catch (err) {
    showToast(err.message || _("Failed to delete custom playlist"), "error")
  } finally {
    pendingDeleteIndex = -1
  }
}

export async function loadPlaylistsData() {
  try {
    const response = await fetch("/api/custom-playlists")
    if (response.ok) {
      const data = await response.json()
      playlistsData = data.playlists || []
    }
  } catch (_error) {
    // silently fail
  }
}

export async function togglePlaylistPreview(index) {
  const card = document.querySelector(`.expandable-card[data-pl-index="${index}"]`)
  const preview = document.getElementById(`playlist-preview-${index}`)
  if (!card || !preview) return

  const isExpanded = !preview.classList.contains("collapsed")
  if (isExpanded) {
    card.classList.remove("expanded")
    preview.classList.add("collapsed")
    return
  }

  card.classList.add("expanded")
  preview.classList.remove("collapsed")

  if (loadedPreviews.has(index)) return
  loadedPreviews.add(index)

  try {
    const response = await fetch(`/api/custom-playlists/${index}/tracks`)
    if (!response.ok) throw new Error("Failed to load")
    preview.innerHTML = await response.text()
  } catch (_error) {
    preview.innerHTML = `<div class="playlist-preview-empty">${_("Failed to load tracks")}</div>`
    loadedPreviews.delete(index)
  }
}

function updateBlacklistBadge(index) {
  const pl = playlistsData[index]
  if (!pl) return
  const count = (pl.blacklist || []).length
  const badge = document.querySelector(`.blacklist-count-badge[data-pl-index="${index}"]`)
  if (!badge) return
  badge.style.display = count ? "" : "none"
  badge.textContent = `${count} ${_("blacklisted")}`
}

export async function blacklistFromPlaylist(index, artist, title) {
  const pl = playlistsData[index]
  if (!pl) return

  const key = `${artist.toLowerCase()}|${title.toLowerCase()}`
  const blacklist = pl.blacklist || []
  if (blacklist.includes(key)) {
    showToast(_("Track already blacklisted"), "info")
    return
  }

  blacklist.push(key)
  pl.blacklist = blacklist

  try {
    const response = await fetch("/api/custom-playlists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlists: playlistsData }),
    })
    if (!response.ok) throw new Error("Failed to save")

    showToast(`${title} ${_("blacklisted from")} ${pl.name}`, "success")
    updateBlacklistBadge(index)
    loadedPreviews.delete(index)
    const card = document.querySelector(`.expandable-card[data-pl-index="${index}"]`)
    if (card?.classList.contains("expanded")) {
      card.classList.remove("expanded")
      const preview = document.getElementById(`playlist-preview-${index}`)
      if (preview) preview.classList.add("collapsed")
      await togglePlaylistPreview(index)
    }
  } catch (_error) {
    blacklist.pop()
    showToast(_("Failed to blacklist track"), "error")
  }
}

export async function unblacklistFromPlaylist(index, artist, title) {
  const pl = playlistsData[index]
  if (!pl) return

  const key = `${artist.toLowerCase()}|${title.toLowerCase()}`
  const blacklist = pl.blacklist || []
  const idx = blacklist.indexOf(key)
  if (idx === -1) return

  blacklist.splice(idx, 1)
  pl.blacklist = blacklist

  try {
    const response = await fetch("/api/custom-playlists", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ playlists: playlistsData }),
    })
    if (!response.ok) throw new Error("Failed to save")

    showToast(`${title} ${_("restored in")} ${pl.name}`, "success")
    updateBlacklistBadge(index)
    loadedPreviews.delete(index)
    const card = document.querySelector(`.expandable-card[data-pl-index="${index}"]`)
    if (card?.classList.contains("expanded")) {
      card.classList.remove("expanded")
      const preview = document.getElementById(`playlist-preview-${index}`)
      if (preview) preview.classList.add("collapsed")
      await togglePlaylistPreview(index)
    }
  } catch (_error) {
    blacklist.splice(idx, 0, key)
    showToast(_("Failed to restore track"), "error")
  }
}

async function refreshPreview(index) {
  loadedPreviews.delete(index)
  const card = document.querySelector(`.expandable-card[data-pl-index="${index}"]`)
  if (card?.classList.contains("expanded")) {
    card.classList.remove("expanded")
    const preview = document.getElementById(`playlist-preview-${index}`)
    if (preview) preview.classList.add("collapsed")
    await togglePlaylistPreview(index)
  }
}

async function savePlaylists() {
  const response = await fetch("/api/custom-playlists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ playlists: playlistsData }),
  })
  if (!response.ok) throw new Error("Failed to save")
}

export async function blacklistArtistFromPlaylist(index, artist) {
  const pl = playlistsData[index]
  if (!pl) return

  const key = artist.toLowerCase()
  const list = pl.blacklist_artists || []
  if (list.includes(key)) {
    showToast(_("Artist already blacklisted"), "info")
    return
  }

  list.push(key)
  pl.blacklist_artists = list

  try {
    await savePlaylists()
    showToast(`${artist} ${_("blacklisted from")} ${pl.name}`, "success")
    await refreshPreview(index)
  } catch (_error) {
    list.pop()
    showToast(_("Failed to blacklist artist"), "error")
  }
}

export async function unblacklistArtistFromPlaylist(index, artist) {
  const pl = playlistsData[index]
  if (!pl) return

  const key = artist.toLowerCase()
  const list = pl.blacklist_artists || []
  const idx = list.indexOf(key)
  if (idx === -1) return

  list.splice(idx, 1)
  pl.blacklist_artists = list

  try {
    await savePlaylists()
    showToast(`${artist} ${_("restored in")} ${pl.name}`, "success")
    await refreshPreview(index)
  } catch (_error) {
    list.splice(idx, 0, key)
    showToast(_("Failed to restore artist"), "error")
  }
}

export function initCustomPlaylists() {
  document.getElementById("custompl-no-limit")?.addEventListener("change", e => {
    applyLimitVisibility(e.target.checked)
  })
  document.getElementById("custompl-kind")?.addEventListener("change", () => onCustomPlaylistKindChange())
  document.getElementById("custompl-filter-template")?.addEventListener("change", () => onCustomPlaylistFilterTemplateChange())
  document.getElementById("custompl-discovery-auto")?.addEventListener("change", () => applyDiscoverySeedVisibility())
  document.getElementById("custompl-discovery-seed")?.addEventListener("change", () => {
    renderSelectedSeeds()
    renderSeedDropdown(seedSearchValue())
  })
  const seedSearch = document.getElementById("custompl-seed-search")
  if (seedSearch) {
    seedSearch.addEventListener("input", e => renderSeedDropdown(e.target.value))
    seedSearch.addEventListener("focus", () => renderSeedDropdown(seedSearch.value))
    seedSearch.addEventListener("keydown", onSeedKeydown)
  }
  document.getElementById("custompl-seed-pills")?.addEventListener("click", () => {
    document.getElementById("custompl-seed-search")?.focus()
  })
  document.addEventListener("mousedown", e => {
    const wrapper = document.getElementById("custompl-seed-dropdown")?.parentElement
    if (wrapper && !wrapper.contains(e.target)) closeSeedDropdown()
  })
}

export function clearPreviewCache() {
  loadedPreviews.clear()
}

export function syncCustomPlaylist(index) {
  const pl = playlistsData[index]
  if (!pl?.name) return
  showToast(`${_("Syncing")} ${pl.name}...`, "info")
  runSyncCustomPlaylists([pl.name], { dryRun: false })
}

export function previewCustomPlaylist(index) {
  const pl = playlistsData[index]
  if (!pl?.name) return
  showToast(`${_("Previewing")} ${pl.name}...`, "info")
  runSyncCustomPlaylists([pl.name], { dryRun: true })
}

export function showSyncPlaylistsModal() {
  const list = document.getElementById("sync-pl-list")
  if (!list) return
  list.innerHTML = ""
  playlistsData.forEach((pl, i) => {
    const label = document.createElement("label")
    label.className = "sync-pl-item"
    const span = document.createElement("span")
    span.className = "sync-pl-name"
    span.textContent = pl.name
    const cb = document.createElement("input")
    cb.type = "checkbox"
    cb.className = "sync-pl-check toggle-switch"
    cb.dataset.index = String(i)
    label.appendChild(span)
    label.appendChild(cb)
    list.appendChild(label)
  })
  const dryToggle = document.getElementById("syncPlDryRun")
  if (dryToggle) dryToggle.checked = false
  showModal("syncPlaylistsModal")
}

function setAllSyncChecks(checked) {
  for (const cb of document.querySelectorAll(".sync-pl-check")) {
    cb.checked = checked
  }
}

export function syncPlaylistsSelectAll() {
  setAllSyncChecks(true)
}

export function syncPlaylistsSelectNone() {
  setAllSyncChecks(false)
}

export function confirmSyncPlaylists() {
  const checked = [...document.querySelectorAll(".sync-pl-check:checked")]
  const names = checked.map(cb => playlistsData[parseInt(cb.dataset.index, 10)]?.name).filter(Boolean)
  const dryRun = Boolean(document.getElementById("syncPlDryRun")?.checked)
  closeModal("syncPlaylistsModal")

  if (!names.length) {
    showToast(dryRun ? _("Previewing all custom playlists...") : _("Syncing all custom playlists..."), "info")
    runSyncCustomPlaylists([], { dryRun })
    return
  }
  showToast(`${dryRun ? _("Previewing") : _("Syncing")} ${names.length} ${_("playlist(s)")}...`, "info")
  runSyncCustomPlaylists(names, { dryRun })
}
