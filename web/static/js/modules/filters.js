import { getInitialFilter, switchTab } from "./tabs.js"

export function filterTracks() {
  const searchInput = document.getElementById("playlistSearch")
  const search = searchInput?.value.toLowerCase() || ""
  const activeFilter = document.querySelector(".filter-chip:not([data-panel]).active")?.dataset.filter || "all"

  const trackItems = document.querySelectorAll(".track-item")
  for (const item of trackItems) {
    const artist = item.dataset.artist || ""
    const title = item.dataset.title || ""
    const source = item.dataset.source || ""
    const isOverridden = item.dataset.overridden === "yes"
    const isBlacklisted = item.dataset.blacklisted === "yes"
    const isPending = item.dataset.pending === "yes"

    const matchesSearch = artist.includes(search) || title.includes(search)
    let matchesFilter = true

    if (activeFilter === "override") matchesFilter = isOverridden || source === "override"
    else if (activeFilter === "blacklisted") matchesFilter = isBlacklisted
    else if (activeFilter === "pending") matchesFilter = isPending

    item.style.display = matchesSearch && matchesFilter ? "" : "none"
  }
}

export function filterNotFound() {
  const notfoundSearchInput = document.getElementById("notfoundSearch")
  const search = notfoundSearchInput?.value.toLowerCase() || ""
  const notfoundItems = document.querySelectorAll(".notfound-item")
  for (const item of notfoundItems) {
    const artist = item.dataset.artist || ""
    const title = item.dataset.title || ""
    const matches = artist.includes(search) || title.includes(search)
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
    const hasOverride = item.dataset.hasoverride === "yes"
    const isBlacklisted = item.dataset.blacklisted === "yes"

    const matchesSearch = artist.includes(search) || title.includes(search)
    let matchesFilter = true

    if (activeFilter === "has-override") matchesFilter = hasOverride
    else if (activeFilter === "no-override") matchesFilter = !hasOverride && !isBlacklisted
    else if (activeFilter === "blacklisted") matchesFilter = isBlacklisted

    item.style.display = matchesSearch && matchesFilter ? "" : "none"
  }
}

export function filterByTab(tabContext) {
  if (tabContext === "cache") filterCache()
  else if (tabContext === "notfound") filterNotFound()
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
    if (e.target.id === "playlistSearch") {
      filterTracks()
    } else if (e.target.id === "notfoundSearch") {
      filterNotFound()
    } else if (e.target.id === "cacheSearch") {
      filterCache()
    }
  })

  document.addEventListener("click", e => {
    const chip = e.target.closest(".filter-chip")
    if (!chip) return

    const panel = chip.dataset.panel
    if (panel === "cache") {
      for (const c of document.querySelectorAll('.filter-chip[data-panel="cache"]')) c.classList.remove("active")
      chip.classList.add("active")
      filterCache()
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
      filterTracks()
    }
  }
}
