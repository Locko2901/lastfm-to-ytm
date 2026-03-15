const MAX_NOTIFICATIONS = 20
const STORAGE_KEY = "ytm-notifications"

let notifications = []
let unreadCount = 0
let panelOpen = false

function saveToStorage() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ notifications, unreadCount }))
  } catch (_e) {}
}

function loadFromStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    notifications = (data.notifications || []).map(n => ({
      ...n,
      time: new Date(n.time),
    }))
    unreadCount = data.unreadCount || 0
  } catch (_e) {
    notifications = []
    unreadCount = 0
  }
}

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

function formatTime(date) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

function typeIcon(type) {
  if (type === "success") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>'
  }
  if (type === "info") {
    return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
  }
  return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
}

function renderList() {
  const { list, empty, clearBtn } = getElements()
  if (!list) return

  if (notifications.length === 0) {
    list.innerHTML = ""
    empty.classList.remove("hidden")
    clearBtn.classList.add("hidden")
    return
  }

  empty.classList.add("hidden")
  clearBtn.classList.remove("hidden")

  list.innerHTML = notifications
    .map(
      n => `
    <div class="notif-item notif-${n.type}">
      <span class="notif-icon">${typeIcon(n.type)}</span>
      <span class="notif-message notif-truncated">${n.message}</span>
      <span class="notif-time">${formatTime(n.time)}</span>
    </div>`,
    )
    .join("")

  for (const item of list.querySelectorAll(".notif-item")) {
    item.addEventListener("click", () => {
      item.querySelector(".notif-message").classList.toggle("notif-truncated")
    })
  }
}

function updateBadge() {
  const { badge } = getElements()
  if (!badge) return
  if (unreadCount > 0) {
    badge.textContent = unreadCount > 99 ? "99+" : unreadCount
    badge.classList.remove("hidden")
  } else {
    badge.classList.add("hidden")
  }
}

export function pushNotification(message, type = "success") {
  notifications.unshift({ message, type, time: new Date() })
  if (notifications.length > MAX_NOTIFICATIONS) {
    notifications = notifications.slice(0, MAX_NOTIFICATIONS)
  }
  if (!panelOpen) {
    unreadCount++
  }
  saveToStorage()
  updateBadge()
  if (panelOpen) {
    renderList()
  }
}

export function toggleNotifPanel() {
  const { panel } = getElements()
  if (!panel) return
  panelOpen = !panelOpen
  panel.classList.toggle("hidden", !panelOpen)
  if (panelOpen) {
    unreadCount = 0
    saveToStorage()
    updateBadge()
    renderList()
  }
}

export function clearNotifications() {
  notifications = []
  unreadCount = 0
  saveToStorage()
  updateBadge()
  renderList()
}

export function initNotifications() {
  loadFromStorage()
  updateBadge()

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

  document.addEventListener("click", e => {
    const { panel, bell } = getElements()
    if (panelOpen && panel && !panel.contains(e.target) && !bell.contains(e.target)) {
      panelOpen = false
      panel.classList.add("hidden")
    }
  })
}
