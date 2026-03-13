import { _ } from "./i18n.js"
import { closeModal } from "./modals.js"
import { removeBanner, showToast } from "./utils.js"

function removeAuthBanner() {
  removeBanner("authRequiredBanner")
}

export async function checkAuthStatus() {
  try {
    const response = await fetch("/api/auth/status")
    const data = await response.json()
    return data.browser_json_exists && data.valid
  } catch (_e) {
    return false
  }
}

export async function connectAuth() {
  const input = document.getElementById("authInput")
  const connectBtn = document.getElementById("authConnectBtn")
  const resultArea = document.getElementById("authResult")
  const text = input.value.trim()

  if (!text) {
    showToast(_("Please paste request headers first"), "error")
    input.focus()
    return
  }

  connectBtn.disabled = true
  connectBtn.classList.add("loading")
  connectBtn.querySelector(".auth-btn-text").textContent = _("Connecting...")
  connectBtn.querySelector(".auth-btn-icon").innerHTML = '<circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"/>'

  resultArea.style.display = "none"

  try {
    const response = await fetch("/api/auth/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ headers_raw: text }),
    })

    const data = await response.json()

    if (data.success) {
      showResult("success", data.verified ? buildSuccessMessage(data.lastLiked) : _("Auth saved (could not verify live)"))
      showToast(_("YouTube Music connected!"), "success")
      removeAuthBanner()
      setTimeout(() => closeAuthModal(), 1500)
    } else {
      showResult("error", data.error || _("Connection failed"))
      showToast(_("Connection failed"), "error")
      resetConnectButton()
    }
  } catch (_error) {
    showResult("error", _("Network error - check your connection and try again"))
    showToast(_("Connection failed"), "error")
    resetConnectButton()
  }
}

function buildSuccessMessage(lastLiked) {
  if (lastLiked) {
    return _("Connected! Last liked song: %(song)s", { song: lastLiked })
  }
  return _("Connected and verified!")
}

function showResult(type, message) {
  const resultArea = document.getElementById("authResult")
  const icon = document.getElementById("authResultIcon")
  const text = document.getElementById("authResultText")

  resultArea.style.display = "flex"
  resultArea.className = `auth-result auth-result-${type}`

  if (type === "success") {
    icon.innerHTML =
      '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>'
  } else {
    icon.innerHTML =
      '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>'
  }

  text.textContent = message
}

function resetConnectButton() {
  const connectBtn = document.getElementById("authConnectBtn")
  if (connectBtn) {
    connectBtn.disabled = false
    connectBtn.classList.remove("loading")
    connectBtn.querySelector(".auth-btn-text").textContent = "Connect"
    connectBtn.querySelector(".auth-btn-icon").innerHTML = '<path d="M5 12h14"></path><path d="m12 5 7 7-7 7"></path>'
  }
}

export function closeAuthModal() {
  closeModal("authModal")
  resetConnectButton()

  const input = document.getElementById("authInput")
  const resultArea = document.getElementById("authResult")
  if (input) input.value = ""
  if (resultArea) resultArea.style.display = "none"

  updateAuthStatus()
}

export async function updateAuthStatus() {
  const statusEl = document.getElementById("ytmAuthStatus")
  if (!statusEl) return

  const textEl = statusEl.querySelector(".auth-status-text")

  try {
    const response = await fetch("/api/auth/status")
    const data = await response.json()

    if (data.browser_json_exists && data.valid) {
      statusEl.className = "auth-status valid"
      textEl.textContent = "Configured"
    } else if (data.browser_json_exists) {
      statusEl.className = "auth-status invalid"
      textEl.textContent = "Invalid"
    } else {
      statusEl.className = "auth-status missing"
      textEl.textContent = "Not configured"
    }
  } catch (_error) {
    statusEl.className = "auth-status invalid"
    textEl.textContent = "Error"
  }
}

export function initAuth() {
  const authInput = document.getElementById("authInput")
  if (authInput) {
    authInput.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey && e.ctrlKey) {
        e.preventDefault()
        connectAuth()
      }
    })
  }

  updateAuthStatus()
}
