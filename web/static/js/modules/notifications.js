import { onEvent } from "./events.js"
import { formatRelativeTime } from "./utils.js"

const API_BASE = "/api/notifications"
const RELATIVE_REFRESH_MS = 60000

let notifications = []
let lastSeenAt = null
let panelOpen = false
let relativeTimer = null
let renderQueued = false
let busSubscribed = false

function getElements() {
  return {
    bell: document.getElementById("notifBell"),
    badge: document.getElementById("notifBadge"),
    panel: document.getElementById("notifPanel"),
    list: document.getElementById("notifList"),
    empty: document.getElementById("notifEmpty"),
    clearBtn: document.getElementById("notifClear"),
  }
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

function typeIcon(type) {
  if (type === "success") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
  }
  if (type === "info") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
  }
  if (type === "warning") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>'
  }
  return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
}

const deleteIcon =
  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'

function unreadCount() {
  if (!lastSeenAt) return notifications.length
  const seenMs = Date.parse(lastSeenAt)
  if (Number.isNaN(seenMs)) return notifications.length
  return notifications.filter(n => {
    const t = Date.parse(n.created_at)
    return !Number.isNaN(t) && t > seenMs
  }).length
}

function updateBadge() {
  const { badge } = getElements()
  if (!badge) return
  const count = unreadCount()
  if (count > 0) {
    badge.textContent = count > 99 ? "99+" : String(count)
    badge.classList.remove("hidden")
  } else {
    badge.classList.add("hidden")
  }
}

async function renderList() {
  const { list, empty, clearBtn } = getElements()
  if (!list) return

  if (notifications.length === 0) {
    list.innerHTML = ""
    if (empty) empty.classList.remove("hidden")
    if (clearBtn) clearBtn.classList.add("hidden")
    return
  }

  if (empty) empty.classList.add("hidden")
  if (clearBtn) clearBtn.classList.remove("hidden")

  const times = await Promise.all(notifications.map(n => formatRelativeTime(n.created_at)))

  list.innerHTML = notifications
    .map(
      (n, i) => `
    <div class="notif-item notif-${escapeHtml(n.type || "info")}" data-id="${escapeHtml(n.id)}">
      <span class="notif-icon">${typeIcon(n.type)}</span>
      <span class="notif-message notif-truncated">${escapeHtml(n.message)}</span>
      <span class="notif-time" title="${escapeHtml(n.created_at)}">${escapeHtml(times[i])}</span>
      <button class="notif-delete-btn" type="button" aria-label="Dismiss">${deleteIcon}</button>
    </div>`,
    )
    .join("")

  for (const item of list.querySelectorAll(".notif-item")) {
    item.addEventListener("click", e => {
      if (e.target.closest(".notif-delete-btn")) return
      item.querySelector(".notif-message").classList.toggle("notif-truncated")
    })
    const delBtn = item.querySelector(".notif-delete-btn")
    if (delBtn) {
      delBtn.addEventListener("click", e => {
        e.stopPropagation()
        deleteOne(item.dataset.id)
      })
    }
  }
}

function scheduleRender() {
  if (renderQueued) return
  renderQueued = true
  Promise.resolve().then(() => {
    renderQueued = false
    if (panelOpen) renderList()
    updateBadge()
  })
}

function applyEvent(event) {
  if (!event?.event) return
  if (event.event === "add" && event.notification) {
    const existing = notifications.findIndex(n => n.id === event.notification.id)
    if (existing >= 0) {
      notifications[existing] = event.notification
    } else {
      notifications.unshift(event.notification)
    }
  } else if (event.event === "delete" && event.id) {
    notifications = notifications.filter(n => n.id !== event.id)
  } else if (event.event === "clear") {
    notifications = []
  } else if (event.event === "read" && event.last_seen_at) {
    lastSeenAt = event.last_seen_at
  }
  scheduleRender()
}

function applySnapshot(snapshot) {
  if (!snapshot) return
  notifications = Array.isArray(snapshot.notifications) ? snapshot.notifications : []
  lastSeenAt = snapshot.last_seen_at || null
  scheduleRender()
}

function connectStream() {
  if (busSubscribed) return
  busSubscribed = true
  onEvent("notifications", applySnapshot)
  onEvent("notification", applyEvent)
}

async function fetchInitial() {
  try {
    const res = await fetch(API_BASE, { headers: { Accept: "application/json" } })
    if (!res.ok) return
    applySnapshot(await res.json())
  } catch (_e) {}
}

async function deleteOne(id) {
  if (!id) return
  const prev = notifications
  notifications = notifications.filter(n => n.id !== id)
  scheduleRender()
  try {
    const res = await fetch(`${API_BASE}/${encodeURIComponent(id)}`, { method: "DELETE" })
    if (!res.ok && res.status !== 404) {
      notifications = prev
      scheduleRender()
    }
  } catch (_e) {
    notifications = prev
    scheduleRender()
  }
}

async function markRead() {
  try {
    const res = await fetch(`${API_BASE}/read`, { method: "POST" })
    if (!res.ok) return
    const data = await res.json()
    if (data?.last_seen_at) {
      lastSeenAt = data.last_seen_at
      updateBadge()
    }
  } catch (_e) {}
}

export function pushNotification(message, type = "success") {
  if (!message) return
  // Fire-and-forget: SSE delivers the event back to all tabs (including this one).
  try {
    fetch(API_BASE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: String(message), type }),
      keepalive: true,
    }).catch(() => {})
  } catch (_e) {}
}

export function toggleNotifPanel() {
  const { panel } = getElements()
  if (!panel) return
  panelOpen = !panelOpen
  panel.classList.toggle("hidden", !panelOpen)
  if (panelOpen) {
    renderList()
    markRead()
  }
}

export async function clearNotifications() {
  const prev = notifications
  notifications = []
  scheduleRender()
  try {
    const res = await fetch(`${API_BASE}/clear`, { method: "POST" })
    if (!res.ok) {
      notifications = prev
      scheduleRender()
    }
  } catch (_e) {
    notifications = prev
    scheduleRender()
  }
}

export function initNotifications() {
  connectStream()
  fetchInitial()

  if (relativeTimer) clearInterval(relativeTimer)
  relativeTimer = setInterval(() => {
    if (panelOpen && notifications.length > 0) renderList()
  }, RELATIVE_REFRESH_MS)

  const { bell, clearBtn } = getElements()
  if (bell) {
    bell.addEventListener("click", e => {
      e.stopPropagation()
      toggleNotifPanel()
    })
  }
  if (clearBtn) {
    clearBtn.addEventListener("click", clearNotifications)
  }

  const closeBtn = document.getElementById("notifClose")
  if (closeBtn) {
    closeBtn.addEventListener("click", e => {
      e.stopPropagation()
      if (panelOpen) {
        panelOpen = false
        const { panel } = getElements()
        if (panel) panel.classList.add("hidden")
      }
    })
  }

  document.addEventListener("click", e => {
    const { panel, bell: bellEl } = getElements()
    if (panelOpen && panel && !panel.contains(e.target) && bellEl && !bellEl.contains(e.target)) {
      panelOpen = false
      panel.classList.add("hidden")
    }
  })
}
