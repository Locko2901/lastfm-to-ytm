import { closeModal } from "./modals.js"
import { removeBanner, showToast } from "./utils.js"

let authEventSource = null
let _isAuthRunning = false
let authPollInterval = null
let _authCompleting = false

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
  const output = document.getElementById("authOutput")
  const statusArea = document.getElementById("authStatusArea")
  const text = input.value.trim()

  if (!text) {
    showToast("Please paste request headers first", "error")
    input.focus()
    return
  }

  connectBtn.disabled = true
  connectBtn.classList.add("loading")
  connectBtn.querySelector(".auth-btn-text").textContent = "Connecting..."
  connectBtn.querySelector(".auth-btn-icon").innerHTML = '<circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"/>'

  output.innerHTML = ""
  statusArea.style.display = "block"
  _isAuthRunning = true
  _authCompleting = false

  try {
    const startResponse = await fetch("/api/auth/start", { method: "POST" })
    if (!startResponse.ok) {
      const data = await startResponse.json()
      throw new Error(data.error || "Failed to start auth process")
    }

    startAuthPolling()

    authEventSource = new EventSource("/api/auth/output")

    authEventSource.onmessage = event => {
      const data = JSON.parse(event.data)

      if (data.line !== undefined) {
        const line = document.createElement("div")
        line.className = "auth-line"
        line.textContent = data.line
        output.appendChild(line)
        output.scrollTop = output.scrollHeight
      }

      if (data.finished) {
        handleAuthComplete(data.exit_code)
      }
    }

    authEventSource.onerror = () => {
      if (authEventSource) {
        authEventSource.close()
        authEventSource = null
      }
      if (!_authCompleting) {
        resetConnectButton()
        _isAuthRunning = false
      }
    }

    setTimeout(async () => {
      try {
        const sendResponse = await fetch("/api/auth/send", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        })

        if (!sendResponse.ok) {
          const data = await sendResponse.json()
          throw new Error(data.error || "Failed to send headers")
        }
      } catch (error) {
        showToast(error.message, "error")
        resetConnectButton()
      }
    }, 300)
  } catch (error) {
    resetConnectButton()
    _isAuthRunning = false
    showToast(error.message, "error")
  }
}

function handleAuthComplete(exitCode) {
  if (_authCompleting) return
  _authCompleting = true

  if (authPollInterval) {
    clearInterval(authPollInterval)
    authPollInterval = null
  }
  if (authEventSource) {
    authEventSource.close()
    authEventSource = null
  }
  _isAuthRunning = false

  const output = document.getElementById("authOutput")
  const outputText = Array.from(output.querySelectorAll(".auth-line"))
    .map(el => el.textContent)
    .join(" ")
  const success = exitCode === 0 || outputText.includes("Creating file")

  if (success) {
    const successLine = document.createElement("div")
    successLine.className = "auth-line success"
    successLine.textContent = "Authentication saved successfully!"
    output.appendChild(successLine)
    showToast("YouTube Music connected!", "success")

    removeAuthBanner()

    setTimeout(() => closeAuthModal(), 1500)
  } else {
    const errorLine = document.createElement("div")
    errorLine.className = "auth-line error"
    errorLine.textContent = "Authentication failed. Check your headers and try again."
    output.appendChild(errorLine)
    showToast("Connection failed", "error")
    resetConnectButton()
  }
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

export async function stopAuthProcess() {
  try {
    await fetch("/api/auth/stop", { method: "POST" })
  } catch (_e) {}
}

export function closeAuthModal() {
  if (authPollInterval) {
    clearInterval(authPollInterval)
    authPollInterval = null
  }

  if (authEventSource) {
    authEventSource.close()
    authEventSource = null
  }

  if (_isAuthRunning) {
    stopAuthProcess()
  }

  _isAuthRunning = false
  _authCompleting = false
  closeModal("authModal")

  resetConnectButton()
  const input = document.getElementById("authInput")
  const statusArea = document.getElementById("authStatusArea")
  if (input) input.value = ""
  if (statusArea) statusArea.style.display = "none"

  updateAuthStatus()
}

function startAuthPolling() {
  if (authPollInterval) {
    clearInterval(authPollInterval)
  }

  authPollInterval = setInterval(async () => {
    try {
      if (_authCompleting) {
        clearInterval(authPollInterval)
        authPollInterval = null
        return
      }
      if (await checkAuthStatus()) {
        clearInterval(authPollInterval)
        authPollInterval = null
        if (!_authCompleting) {
          handleAuthComplete(0)
        }
      }
    } catch (_e) {}
  }, 1000)
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

  window.addEventListener("beforeunload", () => {
    navigator.sendBeacon("/api/auth/stop")
  })

  updateAuthStatus()
}
