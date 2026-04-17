import { filterByTab } from "./filters.js"

export function switchTab(tabId) {
  const targetTab = document.querySelector(`.tab[data-tab="${tabId}"]`)
  if (!targetTab || targetTab.hidden) {
    tabId = "playlist"
  }

  for (const t of document.querySelectorAll(".tab")) t.classList.remove("active")
  for (const p of document.querySelectorAll(".tab-panel")) p.classList.remove("active")

  document.querySelector(`.tab[data-tab="${tabId}"]`)?.classList.add("active")
  document.getElementById(`panel-${tabId}`)?.classList.add("active")

  const url = new URL(window.location)
  url.searchParams.set("tab", tabId)
  history.replaceState({}, "", url)

  filterByTab(tabId)
}

export function initTabs() {
  for (const tab of document.querySelectorAll(".tab")) {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab))
  }

  const urlParams = new URLSearchParams(window.location.search)
  const initialTab = urlParams.get("tab")
  if (initialTab && document.querySelector(`[data-tab="${initialTab}"]:not([hidden])`)) {
    switchTab(initialTab)
  }
}

export function getInitialFilter() {
  const urlParams = new URLSearchParams(window.location.search)
  return urlParams.get("filter")
}
