import { filterByTab } from "./filters.js"
import { _ } from "./i18n.js"
import { invalidateTagSuggestions, setTagInputValue } from "./tagInput.js"
import { escapeHtml, isSuccessRedirect, postFormData, refreshPanel, refreshStats, showToast, withButtonLoading } from "./utils.js"

const ITEM_SELECTORS = {
  playlist: ".track-item",
  cache: ".cache-item",
  notfound: ".notfound-item",
  overrides: ".override-item",
  tags: ".tag-item",
}

let scrollPosition = 0

export function showModal(id) {
  scrollPosition = window.scrollY
  document.getElementById(id)?.classList.add("active")
  document.body.classList.add("modal-open")
  document.body.style.top = `-${scrollPosition}px`
}

export function closeModal(id) {
  document.getElementById(id)?.classList.remove("active")
  if (!document.querySelector(".modal-overlay.active")) {
    document.body.classList.remove("modal-open")
    document.body.style.top = ""
    window.scrollTo(0, scrollPosition)
  }
}

export function showBlacklistModal(artist, title, redirectTab) {
  document.getElementById("blacklist-artist").value = artist
  document.getElementById("blacklist-title").value = title
  document.getElementById("blacklist-display").value = `${artist} – ${title}`
  document.getElementById("blacklist-redirect").value = redirectTab
  document.getElementById("blacklist-reason").value = ""
  showModal("blacklistModal")
}

export function showOverrideModal(artist, title, redirectTab, existingVideoId = "") {
  document.getElementById("override-artist").value = artist
  document.getElementById("override-title").value = title
  document.getElementById("override-display").value = `${artist} – ${title}`
  document.getElementById("override-redirect").value = redirectTab
  document.getElementById("override-video-id").value = existingVideoId
  showModal("overrideModal")
}

export function showAddOverrideModal() {
  showModal("addOverrideModal")
}

export function showAddBlacklistModal() {
  showModal("addBlacklistModal")
}

export function showTagOverrideModal(artist, title, redirectTab, existingTags = "", lastfmTags = "", hasOverride = "") {
  document.getElementById("tag-override-artist").value = artist
  document.getElementById("tag-override-title").value = title
  document.getElementById("tag-override-display").value = `${artist} – ${title}`
  document.getElementById("tag-override-redirect").value = redirectTab
  document.getElementById("tag-override-lastfm-tags").value = lastfmTags
  setTagInputValue("tag-override-tags", existingTags)
  document.getElementById("tag-override-reason").value = ""

  const removeBtn = document.getElementById("tag-override-remove-btn")
  if (removeBtn) {
    removeBtn.style.display = hasOverride ? "" : "none"
    removeBtn.dataset.artist = artist
    removeBtn.dataset.title = title
    removeBtn.dataset.tab = redirectTab
  }

  showModal("tagOverrideModal")
}

export async function removeTagOverride(artist, title, redirectTab) {
  try {
    const response = await postFormData("/remove_tag_override", {
      artist,
      title,
      redirect_tab: redirectTab,
    })

    if (!isSuccessRedirect(response)) throw new Error("Failed to remove tag override")

    closeModal("tagOverrideModal")
    refreshPanel("tags")
    refreshPanel("playlist")
    refreshPanel("overrides")
    if (redirectTab && redirectTab !== "tags" && redirectTab !== "playlist" && redirectTab !== "overrides") refreshPanel(redirectTab)
    invalidateTagSuggestions()
    refreshStats()
    showToast(_("Tag override removed"), "success")
  } catch (_error) {
    showToast(_("Failed to remove tag override"), "error")
  }
}

export async function clearTagCacheEntry(artist, title, buttonEl, tabContext = "tags") {
  const itemSelector = ITEM_SELECTORS[tabContext] || ".tag-item"
  const trackItem = buttonEl.closest(itemSelector)

  try {
    await withButtonLoading(buttonEl, "...", async () => {
      const response = await postFormData("/clear_tag_cache_entry", {
        artist,
        title,
        redirect_tab: tabContext,
      })

      if (!isSuccessRedirect(response)) throw new Error("Failed to clear tag cache")

      trackItem.remove()

      const tagsList = document.getElementById("tagsTracks")
      if (tagsList && tagsList.children.length === 0) {
        refreshPanel("tags")
      }

      showToast(_("Tag cache cleared - will re-fetch on next sync"), "success")
      refreshStats()
    })
  } catch (_error) {
    showToast(_("Failed to clear tag cache entry"), "error")
  }
}

export async function clearCacheEntry(artist, title, buttonEl, tabContext = "playlist") {
  const itemSelector = ITEM_SELECTORS[tabContext] || ".track-item"
  const trackItem = buttonEl.closest(itemSelector)

  try {
    await withButtonLoading(buttonEl, "...", async () => {
      const response = await postFormData("/clear_cache_entry", {
        artist,
        title,
        redirect_tab: tabContext,
      })

      if (!isSuccessRedirect(response)) throw new Error("Failed to clear cache")

      if (tabContext === "cache") {
        trackItem.remove()

        const cacheList = document.getElementById("cacheTracks")
        if (cacheList && cacheList.children.length === 0) {
          refreshPanel("cache")
        }
      } else if (tabContext === "notfound") {
        trackItem.remove()

        const notfoundList = document.getElementById("notfoundTracks")
        if (notfoundList && notfoundList.children.length === 0) {
          refreshPanel("notfound")
        }
      } else {
        trackItem.classList.add("pending-retry")
        trackItem.dataset.pending = "yes"

        const ytmDiv = trackItem.querySelector(".track-ytm")
        if (ytmDiv) {
          ytmDiv.innerHTML = `
            <span class="text-muted">${_("Will re-search on next sync")}</span>
            <span class="track-ytm-id">
              <span class="badge badge-pending">${_("Pending Retry")}</span>
            </span>
          `
        }

        const actionsDiv = trackItem.querySelector(".track-actions")
        if (actionsDiv) {
          const safeArtist = artist.replace(/"/g, "&quot;")
          const safeTitle = title.replace(/"/g, "&quot;")
          actionsDiv.innerHTML = `
            <button class="btn btn-success btn-sm"
              data-action="showOverrideModal" data-artist="${safeArtist}" data-title="${safeTitle}" data-tab="playlist">${_("Override")}</button>
            <button class="btn btn-danger btn-sm"
              data-action="showBlacklistModal" data-artist="${safeArtist}" data-title="${safeTitle}" data-tab="playlist">${_("Blacklist")}</button>
          `
        }
      }

      filterByTab(tabContext)
      showToast(_("Cache cleared - will retry on next sync"), "success")
      refreshStats()
    })
  } catch (_error) {
    showToast(_("Failed to clear cache entry"), "error")
  }
}

export async function unblacklistTrack(artist, title, buttonEl, tabContext = "playlist") {
  const itemSelector = ITEM_SELECTORS[tabContext] || ".track-item"
  const trackItem = buttonEl.closest(itemSelector)

  try {
    await withButtonLoading(buttonEl, "...", async () => {
      const response = await postFormData("/unblacklist", {
        artist,
        title,
        redirect_tab: tabContext,
      })

      if (!isSuccessRedirect(response)) throw new Error(_("Failed to unblacklist"))

      trackItem.classList.remove("blacklisted")
      trackItem.dataset.blacklisted = "no"

      const badge = trackItem.querySelector(".badge-blacklist")
      if (badge) badge.remove()

      buttonEl.textContent = _("Blacklist")
      buttonEl.className = "btn btn-danger btn-sm"
      buttonEl.onclick = () => showBlacklistModal(artist, title, tabContext)
      buttonEl.disabled = false

      filterByTab(tabContext)
      refreshPanel("blacklist")
      refreshStats()
    })
  } catch (_error) {}
}

function initBlacklistForm() {
  document.getElementById("blacklistForm")?.addEventListener("submit", async function (e) {
    const redirectTab = document.getElementById("blacklist-redirect").value

    const ajaxTabs = ["playlist", "cache", "notfound"]
    if (!ajaxTabs.includes(redirectTab)) {
      return
    }

    e.preventDefault()

    const artist = document.getElementById("blacklist-artist").value
    const title = document.getElementById("blacklist-title").value
    const reason = document.getElementById("blacklist-reason").value || _("Blacklisted via web dashboard")

    const submitBtn = this.querySelector('button[type="submit"]')

    try {
      await withButtonLoading(submitBtn, "...", async () => {
        const response = await postFormData("/blacklist", {
          artist,
          title,
          reason,
          redirect_tab: redirectTab,
        })

        if (!isSuccessRedirect(response)) throw new Error(_("Failed to blacklist"))

        const itemSelector = ITEM_SELECTORS[redirectTab] || ".track-item"
        const items = document.querySelectorAll(itemSelector)
        for (const item of items) {
          if (item.dataset.artist === artist.toLowerCase() && item.dataset.title === title.toLowerCase()) {
            item.classList.add("blacklisted")
            item.dataset.blacklisted = "yes"

            const idSpan = item.querySelector(".track-ytm-id, .cache-ytm-id, .notfound-ytm-id")
            if (idSpan && !idSpan.querySelector(".badge-blacklist")) {
              const badge = document.createElement("span")
              badge.className = "badge badge-blacklist"
              badge.textContent = _("Blacklisted")
              idSpan.appendChild(badge)
            }

            const blacklistBtn = item.querySelector(".btn-danger")
            if (blacklistBtn && blacklistBtn.textContent.trim() === _("Blacklist")) {
              blacklistBtn.textContent = _("Restore")
              blacklistBtn.className = "btn btn-secondary btn-sm"
              blacklistBtn.onclick = () => unblacklistTrack(artist, title, blacklistBtn, redirectTab)
            }
          }
        }

        closeModal("blacklistModal")
        filterByTab(redirectTab)
        refreshPanel("blacklist")
        refreshStats()
      })
    } catch (_error) {
      showToast(_("Failed to blacklist track. Please try again."), "error")
    }
  })
}

function initOverrideForms() {
  document.getElementById("overrideForm")?.addEventListener("submit", async function (e) {
    e.preventDefault()

    const artist = document.getElementById("override-artist").value
    const title = document.getElementById("override-title").value
    const videoId = document.getElementById("override-video-id").value.trim()
    const reason = document.getElementById("override-reason")?.value || _("Override via web dashboard")
    const redirectTab = document.getElementById("override-redirect").value

    const submitBtn = this.querySelector('button[type="submit"]')

    try {
      await withButtonLoading(submitBtn, _("Saving..."), async () => {
        const response = await postFormData("/override", {
          artist,
          title,
          video_id: videoId,
          reason,
          redirect_tab: redirectTab,
        })

        if (response.status === 400) {
          const data = await response.json()
          throw new Error(data.error || _("Invalid input"))
        }

        if (!isSuccessRedirect(response)) throw new Error(_("Failed to save override"))

        const itemSelector = ITEM_SELECTORS[redirectTab] || ".track-item"
        const items = document.querySelectorAll(itemSelector)
        for (const item of items) {
          if (item.dataset.artist === artist.toLowerCase() && item.dataset.title === title.toLowerCase()) {
            const idSpan = item.querySelector(".track-ytm-id, .cache-ytm-id, .notfound-ytm-id")
            if (idSpan) {
              const existingBadge = idSpan.querySelector(".badge-override")
              if (existingBadge) existingBadge.remove()

              const badge = document.createElement("span")
              badge.className = "badge badge-override"
              badge.textContent = _("Override")
              idSpan.insertBefore(badge, idSpan.firstChild)
            }

            item.dataset.overridden = "yes"
            if (item.dataset.hasoverride !== undefined) {
              item.dataset.hasoverride = "yes"
            }
            item.classList.add("overridden")

            const actionsDiv = item.querySelector(".track-actions")
            const overrideBtn = actionsDiv?.querySelector(".btn-success")
            if (overrideBtn && overrideBtn.textContent.trim() === _("Override")) {
              const form = document.createElement("form")
              form.method = "POST"
              form.action = "/remove_override"
              form.style.display = "inline"
              form.innerHTML = `
                <input type="hidden" name="artist" value="${artist}">
                <input type="hidden" name="title" value="${title}">
                <input type="hidden" name="redirect_tab" value="${redirectTab}">
                <button type="submit" class="btn btn-secondary btn-sm">${_("Remove Override")}</button>
              `
              overrideBtn.replaceWith(form)
            }
          }
        }

        closeModal("overrideModal")
        showToast(_("Override saved!"), "success")
        filterByTab(redirectTab)
        refreshPanel("overrides")
        refreshStats()
      })
    } catch (error) {
      showToast(error.message || _("Failed to save override"), "error")
    }
  })

  document.getElementById("addOverrideForm")?.addEventListener("submit", async function (e) {
    e.preventDefault()

    const artist = document.getElementById("add-override-artist").value.trim()
    const title = document.getElementById("add-override-title").value.trim()
    const videoId = document.getElementById("add-override-video-id").value.trim()
    const reason = document.getElementById("add-override-reason")?.value || "Override via web dashboard"

    if (!artist || !title || !videoId) {
      showToast(_("Please fill in all required fields"), "error")
      return
    }

    const submitBtn = this.querySelector('button[type="submit"]')

    try {
      await withButtonLoading(submitBtn, "Saving...", async () => {
        const response = await postFormData("/override", {
          artist,
          title,
          video_id: videoId,
          reason,
          redirect_tab: "overrides",
        })

        if (!isSuccessRedirect(response)) throw new Error(_("Failed to add override"))

        closeModal("addOverrideModal")
        showToast(_("Override added!"), "success")
        this.reset()
        refreshPanel("overrides")
        refreshStats()
      })
    } catch (_error) {
      showToast(_("Failed to add override"), "error")
    }
  })
}

function initAddBlacklistForm() {
  document.getElementById("addBlacklistForm")?.addEventListener("submit", async function (e) {
    e.preventDefault()

    const artist = document.getElementById("add-blacklist-artist").value.trim()
    const title = document.getElementById("add-blacklist-title").value.trim()
    const reason = document.getElementById("add-blacklist-reason")?.value || _("Blacklisted via web dashboard")

    if (!artist || !title) {
      showToast(_("Please fill in artist and title"), "error")
      return
    }

    const submitBtn = this.querySelector('button[type="submit"]')

    try {
      await withButtonLoading(submitBtn, _("Saving..."), async () => {
        const response = await postFormData("/blacklist", {
          artist,
          title,
          reason,
          redirect_tab: "blacklist",
        })

        if (!isSuccessRedirect(response)) throw new Error(_("Failed to blacklist track"))

        closeModal("addBlacklistModal")
        showToast(_("Track blacklisted!"), "success")
        this.reset()
        refreshPanel("blacklist")
        refreshStats()
      })
    } catch (_error) {
      showToast(_("Failed to blacklist track"), "error")
    }
  })
}

function initTagOverrideForms() {
  document.getElementById("tagOverrideForm")?.addEventListener("submit", async function (e) {
    e.preventDefault()

    const artist = document.getElementById("tag-override-artist").value
    const title = document.getElementById("tag-override-title").value
    const tags = document.getElementById("tag-override-tags").value.trim()
    const reason = document.getElementById("tag-override-reason").value
    const redirectTab = document.getElementById("tag-override-redirect").value

    if (!tags) {
      showToast(_("Please enter at least one tag"), "error")
      return
    }

    const lastfmTagsRaw = document.getElementById("tag-override-lastfm-tags").value
    const lastfmSet = new Set(
      lastfmTagsRaw
        .split(",")
        .map(t => t.trim().toLowerCase())
        .filter(Boolean),
    )
    const newSet = new Set(
      tags
        .split(",")
        .map(t => t.trim().toLowerCase())
        .filter(Boolean),
    )
    const allLastfmPresent = [...lastfmSet].every(t => newSet.has(t))
    let mode, overrideTags
    if (lastfmSet.size === 0 || !allLastfmPresent) {
      mode = "replace"
      overrideTags = tags
    } else {
      const extras = [...newSet].filter(t => !lastfmSet.has(t))
      if (extras.length === 0) {
        showToast(_("No tag changes detected"), "info")
        return
      }
      mode = "add"
      overrideTags = extras.join(", ")
    }

    const submitBtn = this.querySelector('button[type="submit"]')

    try {
      await withButtonLoading(submitBtn, _("Saving..."), async () => {
        const response = await postFormData("/tag_override", {
          artist,
          title,
          tags: overrideTags,
          mode,
          reason,
          redirect_tab: redirectTab,
        })

        if (!isSuccessRedirect(response)) throw new Error(_("Failed to save tag override"))

        closeModal("tagOverrideModal")
        showToast(_("Tag override saved!"), "success")
        invalidateTagSuggestions()
        refreshPanel("tags")
        refreshPanel("playlist")
        refreshPanel("overrides")
        if (redirectTab && redirectTab !== "tags" && redirectTab !== "playlist" && redirectTab !== "overrides") refreshPanel(redirectTab)
        refreshStats()
      })
    } catch (_error) {
      showToast(_("Failed to save tag override"), "error")
    }
  })
}

export function initModals(closeAuthModalFn) {
  initBlacklistForm()
  initOverrideForms()
  initAddBlacklistForm()
  initTagOverrideForms()
  initImportDropzone()

  for (const modal of document.querySelectorAll(".modal-overlay")) {
    modal.addEventListener("click", e => {
      if (e.target === modal) {
        if (modal.id === "authModal") {
          closeAuthModalFn()
          return
        }
        closeModal(modal.id)
      }
    })
  }

  document.addEventListener("keydown", e => {
    if (e.key === "Escape") {
      const authModal = document.getElementById("authModal")
      if (authModal?.classList.contains("active")) {
        closeAuthModalFn()
      }
      for (const m of document.querySelectorAll(".modal-overlay.active")) {
        if (m.id !== "authModal") {
          closeModal(m.id)
        }
      }
    }
  })
}

export function showExportImportModal() {
  const preview = document.getElementById("import-preview")
  if (preview) preview.style.display = "none"
  const dropzone = document.getElementById("import-dropzone")
  if (dropzone) dropzone.classList.remove("dragover")
  showModal("exportImportModal")
}

export async function exportData(type = "all") {
  try {
    const resp = await fetch(`/export?type=${encodeURIComponent(type)}`)
    if (!resp.ok) throw new Error(_("Export failed"))
    const data = await resp.json()
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `ytm-${type}-export.json`
    a.click()
    URL.revokeObjectURL(url)
    showToast(_("Export downloaded"), "success")
  } catch (error) {
    showToast(error.message || _("Export failed"), "error")
  }
}

let _pendingImportData = null

function initImportDropzone() {
  const dropzone = document.getElementById("import-dropzone")
  const fileInput = document.getElementById("import-file-input")
  if (!dropzone || !fileInput) return

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
    if (file) _processImportFile(file)
  })
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0]
    if (file) _processImportFile(file)
    fileInput.value = ""
  })
}

function _processImportFile(file) {
  if (!file.name.endsWith(".json")) {
    showToast(_("Please select a JSON file"), "error")
    return
  }
  const reader = new FileReader()
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result)
      _pendingImportData = data
      const oCount = data.overrides ? Object.keys(data.overrides).length : 0
      const bCount = data.blacklist ? Object.keys(data.blacklist).length : 0

      const statsEl = document.getElementById("import-stats")
      statsEl.innerHTML = `
        <p><strong>${escapeHtml(file.name)}</strong></p>
        <p>${_("Overrides")}: <strong>${oCount}</strong> · ${_("Blacklist")}: <strong>${bCount}</strong></p>
      `
      document.getElementById("import-preview").style.display = ""
    } catch (_err) {
      showToast(_("Invalid JSON file"), "error")
    }
  }
  reader.readAsText(file)
}

export async function confirmImport() {
  if (!_pendingImportData) return
  const btn = document.getElementById("import-confirm-btn")
  try {
    await withButtonLoading(btn, _("Importing..."), async () => {
      const resp = await fetch("/import", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(_pendingImportData),
      })
      const data = await resp.json()
      if (!resp.ok) throw new Error(data.error || _("Import failed"))

      _pendingImportData = null
      document.getElementById("import-preview").style.display = "none"
      showToast(
        _("Imported %(overrides)s overrides and %(blacklist)s blacklist entries", {
          overrides: data.imported_overrides,
          blacklist: data.imported_blacklist,
        }),
        "success",
      )
      refreshPanel("overrides")
      refreshPanel("blacklist")
      refreshPanel("playlist")
      refreshStats()
    })
  } catch (error) {
    showToast(error.message || _("Import failed"), "error")
  }
}

let _detailArtist = ""
let _detailTitle = ""
let _detailTab = "playlist"

const _sourceLabels = {
  cache: "Cached",
  search: "Search",
  override: "Override",
  not_found: "Not Found",
  not_found_cached: "Not Found",
  blacklisted: "Blacklisted",
}

const _sourceBadgeClass = {
  cache: "badge-cached",
  search: "badge-search",
  override: "badge-override",
  not_found: "badge-notfound",
  not_found_cached: "badge-notfound",
  blacklisted: "badge-blacklist",
}

function _setDetailLoading() {
  for (const id of ["detail-video-id", "detail-yt-title", "detail-source", "detail-tags", "detail-status"]) {
    const el = document.getElementById(id)
    if (el) el.innerHTML = `<span class="detail-skeleton"></span>`
  }
  document.getElementById("detail-links").innerHTML = ""
  document.getElementById("detail-override-btn").style.display = "none"
  document.getElementById("detail-blacklist-btn").style.display = "none"
}

export async function showTrackDetailModal(artist, title, tab) {
  _detailArtist = artist
  _detailTitle = title
  _detailTab = tab || _detectCurrentTab() || "playlist"

  document.getElementById("detail-track-name").textContent = `${artist} – ${title}`
  document.getElementById("detail-artist").textContent = artist
  document.getElementById("detail-title").textContent = title

  _setDetailLoading()
  showModal("trackDetailModal")

  try {
    const resp = await fetch(`/api/track-detail?artist=${encodeURIComponent(artist)}&title=${encodeURIComponent(title)}`)
    if (!resp.ok) throw new Error(_("Failed to load details"))
    const d = await resp.json()

    document.getElementById("detail-video-id").textContent = d.video_id || "—"
    document.getElementById("detail-yt-title").textContent = d.yt_title || "—"

    const sourceEl = document.getElementById("detail-source")
    if (d.source) {
      const badgeClass = _sourceBadgeClass[d.source] || ""
      const label = _sourceLabels[d.source] || d.source
      sourceEl.innerHTML = `<span class="badge ${badgeClass}">${escapeHtml(label)}</span>`
    } else {
      sourceEl.textContent = "—"
    }

    const tagsEl = document.getElementById("detail-tags")
    if (d.tags && d.tags.length > 0) {
      tagsEl.innerHTML = d.tags.map(t => `<span class="tag-pill">${escapeHtml(t)}</span>`).join(" ")
      if (d.has_tag_override) {
        tagsEl.innerHTML += ` <span class="badge badge-tagoverride">${_("Override")}</span>`
      }
    } else {
      tagsEl.textContent = _("No tags")
    }

    const statusEl = document.getElementById("detail-status")
    const badges = []
    if (d.is_overridden) badges.push(`<span class="badge badge-override">${_("Override")}</span>`)
    if (d.is_blacklisted) badges.push(`<span class="badge badge-blacklist">${_("Blacklisted")}</span>`)
    if (d.cache_timestamp) badges.push(`<span class="text-muted">${_("Cached:")} ${d.cache_timestamp.slice(0, 10)}</span>`)
    statusEl.innerHTML = badges.join(" ") || "—"

    const linksEl = document.getElementById("detail-links")
    const links = []
    if (d.video_id) {
      links.push(
        `<a href="https://music.youtube.com/watch?v=${encodeURIComponent(d.video_id)}" target="_blank" rel="noopener" class="detail-link">${_("Open in YouTube Music")}</a>`,
      )
    }
    links.push(
      `<a href="https://www.last.fm/music/${encodeURIComponent(artist)}/_/${encodeURIComponent(title)}" target="_blank" rel="noopener" class="detail-link">${_("View on Last.fm")}</a>`,
    )
    linksEl.innerHTML = links.join("")

    document.getElementById("detail-override-btn").style.display = d.is_overridden ? "none" : ""
    document.getElementById("detail-blacklist-btn").style.display = d.is_blacklisted ? "none" : ""
  } catch (_err) {
    document.getElementById("detail-video-id").textContent = _("Error loading details")
    document.getElementById("detail-yt-title").textContent = "-"
    document.getElementById("detail-source").textContent = "-"
    document.getElementById("detail-tags").textContent = "-"
    document.getElementById("detail-status").textContent = "-"
  }
}

function _detectCurrentTab() {
  const active = document.querySelector(".tab.active")
  return active ? active.dataset.tab : null
}

export function detailOverride() {
  closeModal("trackDetailModal")
  showOverrideModal(_detailArtist, _detailTitle, _detailTab)
}

export function detailBlacklist() {
  closeModal("trackDetailModal")
  showBlacklistModal(_detailArtist, _detailTitle, _detailTab)
}
