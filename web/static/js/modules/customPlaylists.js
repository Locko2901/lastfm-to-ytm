import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { setTagInputValue } from "./tagInput.js"
import { refreshPanel, refreshStats, showToast } from "./utils.js"

let playlistsData = []
const loadedPreviews = new Set()

export function setPlaylistsData(data) {
  playlistsData = data
}

export function showCustomPlaylistModal(editIndex = -1) {
  document.getElementById("custompl-edit-index").value = editIndex
  const limitInput = document.getElementById("custompl-limit")
  const noLimitCheckbox = document.getElementById("custompl-no-limit")
  if (editIndex >= 0 && playlistsData[editIndex]) {
    const pl = playlistsData[editIndex]
    document.getElementById("custompl-modal-title").textContent = _("Edit Custom Playlist")
    document.getElementById("custompl-name").value = pl.name || ""
    document.getElementById("custompl-description").value = pl.description || ""
    setTagInputValue("custompl-tags", (pl.tags || []).join(", "))
    document.getElementById("custompl-match").value = pl.match || "any"
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
    document.getElementById("custompl-description").value = ""
    setTagInputValue("custompl-tags", "")
    document.getElementById("custompl-match").value = "any"
    noLimitCheckbox.checked = false
    limitInput.value = "50"
    limitInput.disabled = false
    document.getElementById("custompl-backfill").checked = true
    document.getElementById("custompl-auto-sync").checked = true
    document.getElementById("custompl-blacklist").value = ""
    document.getElementById("custompl-blacklist-artists").value = ""
  }
  showModal("customPlaylistModal")
}

export function editCustomPlaylist(index) {
  showCustomPlaylistModal(index)
}

export async function saveCustomPlaylist() {
  const editIndex = parseInt(document.getElementById("custompl-edit-index").value, 10)
  const name = document.getElementById("custompl-name").value.trim()
  const description = document.getElementById("custompl-description").value.trim()
  const tagsRaw = document.getElementById("custompl-tags").value.trim()
  const match = document.getElementById("custompl-match").value
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

  if (!tagsRaw) {
    showToast(_("Please enter at least one tag"), "error")
    return
  }

  const tags = tagsRaw
    .split(",")
    .map(t => t.trim().toLowerCase())
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

  const playlist = { name, description, tags, match, limit, backfill, auto_sync: autoSync, blacklist, blacklist_artists: blacklistArtists }

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
    document.getElementById("custompl-limit").disabled = e.target.checked
  })
}

export function clearPreviewCache() {
  loadedPreviews.clear()
}
