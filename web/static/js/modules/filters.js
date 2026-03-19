import { getInitialFilter, switchTab } from "./tabs.js"

function updateChipCounts(panelSelector, items, filterTests) {
  const chips = document.querySelectorAll(panelSelector)
  for (const chip of chips) {
    const badge = chip.querySelector(".chip-count")
    if (!badge) continue
    const filter = chip.dataset.filter
    const test = filterTests[filter]
    if (!test) continue
    let count = 0
    for (const item of items) if (test(item)) count++
    badge.textContent = count ? `(${count})` : ""
  }
}

export function filterTracks() {
  const searchInput = document.getElementById("playlistSearch")
  const search = searchInput?.value.toLowerCase() || ""
  const activeFilter = document.querySelector(".filter-chip:not([data-panel]).active")?.dataset.filter || "all"

  const trackItems = document.querySelectorAll("#playlistTracks .track-item")
  for (const item of trackItems) {
    const artist = item.dataset.artist || ""
    const title = item.dataset.title || ""
    const tags = item.dataset.tags || ""
    const source = item.dataset.source || ""
    const isOverridden = item.dataset.overridden === "yes"
    const isBlacklisted = item.dataset.blacklisted === "yes"
    const isPending = item.dataset.pending === "yes"
    const hasTags = item.dataset.hastags === "yes"

    const matchesSearch = artist.includes(search) || title.includes(search) || tags.includes(search)
    let matchesFilter = true

    if (activeFilter === "override") matchesFilter = isOverridden || source === "override"
    else if (activeFilter === "blacklisted") matchesFilter = isBlacklisted
    else if (activeFilter === "pending") matchesFilter = isPending
    else if (activeFilter === "has-tags") matchesFilter = hasTags
    else if (activeFilter === "no-tags") matchesFilter = !hasTags

    item.style.display = matchesSearch && matchesFilter ? "" : "none"
  }

  const searched = Array.from(trackItems).filter(i => {
    const a = i.dataset.artist || "",
      t = i.dataset.title || "",
      tg = i.dataset.tags || ""
    return a.includes(search) || t.includes(search) || tg.includes(search)
  })
  updateChipCounts(".filter-chip:not([data-panel])", searched, {
    all: () => true,
    override: i => i.dataset.overridden === "yes" || i.dataset.source === "override",
    blacklisted: i => i.dataset.blacklisted === "yes",
    pending: i => i.dataset.pending === "yes",
    "has-tags": i => i.dataset.hastags === "yes",
    "no-tags": i => i.dataset.hastags !== "yes",
  })
}

export function filterNotFound() {
  const notfoundSearchInput = document.getElementById("notfoundSearch")
  const search = notfoundSearchInput?.value.toLowerCase() || ""
  const notfoundItems = document.querySelectorAll(".notfound-item")
  for (const item of notfoundItems) {
    const artist = item.dataset.artist || ""
    const title = item.dataset.title || ""
    const tags = item.dataset.tags || ""
    const matches = artist.includes(search) || title.includes(search) || tags.includes(search)
    item.style.display = matches ? "" : "none"
  }
}

export function filterCache() {
  const cacheSearchInput = document.getElementById("cacheSearch")
  const search = cacheSearchInput?.value.toLowerCase() || ""
  const activeFilter = document.querySelector('.filter-chip[data-panel="cache"].active')?.dataset.filter || "all"

  const cacheItems = document.querySelectorAll(".cache-item")
  for (const item of cacheItems) {
    const artist = item.dataset.artist || ""
    const title = item.dataset.title || ""
    const tags = item.dataset.tags || ""
    const hasOverride = item.dataset.hasoverride === "yes"
    const isBlacklisted = item.dataset.blacklisted === "yes"
    const hasTags = item.dataset.hastags === "yes"

    const matchesSearch = artist.includes(search) || title.includes(search) || tags.includes(search)
    let matchesFilter = true

    if (activeFilter === "has-override") matchesFilter = hasOverride
    else if (activeFilter === "no-override") matchesFilter = !hasOverride && !isBlacklisted
    else if (activeFilter === "blacklisted") matchesFilter = isBlacklisted
    else if (activeFilter === "has-tags") matchesFilter = hasTags
    else if (activeFilter === "no-tags") matchesFilter = !hasTags

    item.style.display = matchesSearch && matchesFilter ? "" : "none"
  }

  const searched = Array.from(cacheItems).filter(i => {
    const a = i.dataset.artist || "",
      t = i.dataset.title || "",
      tg = i.dataset.tags || ""
    return a.includes(search) || t.includes(search) || tg.includes(search)
  })
  updateChipCounts('.filter-chip[data-panel="cache"]', searched, {
    all: () => true,
    "has-override": i => i.dataset.hasoverride === "yes",
    blacklisted: i => i.dataset.blacklisted === "yes",
    "no-override": i => i.dataset.hasoverride !== "yes" && i.dataset.blacklisted !== "yes",
    "has-tags": i => i.dataset.hastags === "yes",
    "no-tags": i => i.dataset.hastags !== "yes",
  })
}

export function filterTags() {
  const searchInput = document.getElementById("tagsSearch")
  const search = searchInput?.value.toLowerCase() || ""
  const activeFilter = document.querySelector('.filter-chip[data-panel="tags"].active')?.dataset.filter || "all"

  const tagItems = document.querySelectorAll(".tag-item")
  for (const item of tagItems) {
    const artist = item.dataset.artist || ""
    const title = item.dataset.title || ""
    const tags = item.dataset.tags || ""
    const hasOverride = item.dataset.hasoverride === "yes"
    const hasTags = item.dataset.hastags === "yes"
    const tagSource = item.dataset.tagsource || ""

    const matchesSearch = artist.includes(search) || title.includes(search) || tags.includes(search)
    let matchesFilter = true

    if (activeFilter === "has-override") matchesFilter = hasOverride
    else if (activeFilter === "has-tags") matchesFilter = hasTags
    else if (activeFilter === "no-tags") matchesFilter = !hasTags
    else if (activeFilter === "track-tags") matchesFilter = tagSource.includes("track")
    else if (activeFilter === "artist-tags") matchesFilter = tagSource.includes("artist")

    item.style.display = matchesSearch && matchesFilter ? "" : "none"
  }

  const searched = Array.from(tagItems).filter(i => {
    const a = i.dataset.artist || "",
      t = i.dataset.title || "",
      tg = i.dataset.tags || ""
    return a.includes(search) || t.includes(search) || tg.includes(search)
  })
  updateChipCounts('.filter-chip[data-panel="tags"]', searched, {
    all: () => true,
    "has-override": i => i.dataset.hasoverride === "yes",
    "has-tags": i => i.dataset.hastags === "yes",
    "no-tags": i => i.dataset.hastags !== "yes",
    "track-tags": i => (i.dataset.tagsource || "").includes("track"),
    "artist-tags": i => (i.dataset.tagsource || "").includes("artist"),
  })
}

export function filterByTab(tabContext) {
  if (tabContext === "cache") filterCache()
  else if (tabContext === "notfound") filterNotFound()
  else if (tabContext === "tags") filterTags()
  else filterTracks()
}

export function goToFilter(tabId, filter = null) {
  switchTab(tabId)
  if (filter && tabId === "playlist") {
    const chip = document.querySelector(`.filter-chip:not([data-panel])[data-filter="${filter}"]`)
    if (chip) {
      for (const c of document.querySelectorAll(".filter-chip:not([data-panel])")) c.classList.remove("active")
      chip.classList.add("active")
      filterTracks()
    }
    const url = new URL(window.location)
    url.searchParams.set("filter", filter)
    history.replaceState({}, "", url)
  }
}

export function initFilters() {
  document.addEventListener("input", e => {
    if (e.target.classList.contains("search-input")) {
      e.target.closest(".search-wrapper")?.classList.toggle("has-value", e.target.value.length > 0)
    }
    if (e.target.id === "playlistSearch") {
      filterTracks()
    } else if (e.target.id === "notfoundSearch") {
      filterNotFound()
    } else if (e.target.id === "cacheSearch") {
      filterCache()
    } else if (e.target.id === "tagsSearch") {
      filterTags()
    }
  })

  document.addEventListener("click", e => {
    const clearBtn = e.target.closest(".search-clear")
    if (!clearBtn) return
    const inputId = clearBtn.dataset.for
    const input = document.getElementById(inputId)
    if (!input) return
    input.value = ""
    clearBtn.closest(".search-wrapper")?.classList.remove("has-value")
    input.dispatchEvent(new Event("input", { bubbles: true }))
  })

  document.addEventListener("click", e => {
    const chip = e.target.closest(".filter-chip")
    if (!chip) return

    const panel = chip.dataset.panel
    if (panel === "cache") {
      for (const c of document.querySelectorAll('.filter-chip[data-panel="cache"]')) c.classList.remove("active")
      chip.classList.add("active")
      filterCache()
    } else if (panel === "tags") {
      for (const c of document.querySelectorAll('.filter-chip[data-panel="tags"]')) c.classList.remove("active")
      chip.classList.add("active")
      filterTags()
    } else if (!panel) {
      for (const c of document.querySelectorAll(".filter-chip:not([data-panel])")) c.classList.remove("active")
      chip.classList.add("active")
      filterTracks()
    }
  })

  const initialFilter = getInitialFilter()
  if (initialFilter) {
    const chip = document.querySelector(`.filter-chip:not([data-panel])[data-filter="${initialFilter}"]`)
    if (chip) {
      for (const c of document.querySelectorAll(".filter-chip:not([data-panel])")) c.classList.remove("active")
      chip.classList.add("active")
    }
  }

  filterTracks()
  filterCache()
  filterTags()
}
