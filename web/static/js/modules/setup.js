import { checkAuthStatus } from "./auth.js"
import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { escapeHtml, formatDateTime, formatRelativeTime, getUse24HourClock, insertBanner, removeBanner, showToast } from "./utils.js"

let currentSetupStep = 1
const totalSetupSteps = 2
let setupAuthPollInterval = null

export function showSetupWizard() {
  currentSetupStep = 1
  updateSetupUI()
  showModal("setupModal")

  setTimeout(() => {
    const firstInput = document.getElementById("setup-lastfm-user")
    if (firstInput) firstInput.focus()
  }, 100)
}

export function closeSetupWizard() {
  stopAuthPolling()
  closeModal("setupModal")
}

function stopAuthPolling() {
  if (setupAuthPollInterval) {
    clearInterval(setupAuthPollInterval)
    setupAuthPollInterval = null
  }
}

function updateSetupUI() {
  for (const step of document.querySelectorAll(".setup-step")) {
    const stepNum = parseInt(step.dataset.step, 10)
    step.classList.remove("active", "completed")
    if (stepNum === currentSetupStep) {
      step.classList.add("active")
    } else if (stepNum < currentSetupStep) {
      step.classList.add("completed")
    }
  }

  for (let i = 1; i <= totalSetupSteps; i++) {
    const content = document.getElementById(`setup-step-${i}`)
    if (content) {
      content.style.display = i === currentSetupStep ? "" : "none"
    }
  }

  const backBtn = document.getElementById("setup-back-btn")
  const nextBtn = document.getElementById("setup-next-btn")

  backBtn.style.display = currentSetupStep > 1 ? "" : "none"

  if (currentSetupStep === totalSetupSteps) {
    checkAuthStatus().then(hasAuth => {
      nextBtn.textContent = hasAuth ? _("Finish Setup") : _("Skip for Now")
      nextBtn.classList.toggle("btn-success", hasAuth)
      nextBtn.classList.toggle("btn-secondary", !hasAuth)

      const authBtn = document.getElementById("setupAuthBtn")
      if (authBtn) {
        authBtn.textContent = hasAuth ? _("Reconnect YouTube Music") : _("Connect YouTube Music")
      }
    })
  } else {
    nextBtn.textContent = _("Next")
    nextBtn.classList.add("btn-success")
    nextBtn.classList.remove("btn-secondary")
  }

  if (currentSetupStep === 2) {
    updateAuthStatusDisplay()
    startAuthPolling()
  } else {
    stopAuthPolling()
  }
}

export async function setupNextStep() {
  const nextBtn = document.getElementById("setup-next-btn")

  if (currentSetupStep === 1) {
    const username = document.getElementById("setup-lastfm-user").value.trim()
    const apiKey = document.getElementById("setup-lastfm-key").value.trim()

    if (!username || !apiKey) {
      showToast(_("Please enter both username and API key"), "error")
      if (!username) document.getElementById("setup-lastfm-user").classList.add("input-error")
      if (!apiKey) document.getElementById("setup-lastfm-key").classList.add("input-error")
      return
    }

    document.getElementById("setup-lastfm-user").classList.remove("input-error")
    document.getElementById("setup-lastfm-key").classList.remove("input-error")

    nextBtn.disabled = true
    nextBtn.textContent = _("Saving...")
    try {
      await fetch("/api/setup/init", { method: "POST" })

      const response = await fetch("/api/setup/lastfm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, api_key: apiKey }),
      })
      if (!response.ok) {
        const data = await response.json()
        throw new Error(data.error)
      }
      showToast(_("Last.fm credentials saved!"), "success")
      currentSetupStep++
      updateSetupUI()
    } catch (error) {
      showToast(error.message, "error")
    } finally {
      nextBtn.disabled = false
      nextBtn.textContent = _("Next")
    }
  } else if (currentSetupStep === 2) {
    stopAuthPolling()
    const hasAuth = await checkAuthStatus()
    closeModal("setupModal")

    if (hasAuth) {
      showToast(_("Setup complete! You can now run a sync."), "success")
    } else {
      showToast(_("Setup saved. You can authenticate with YouTube Music later in Settings."), "info")
    }
    setTimeout(() => location.reload(), 1000)
  }
}

export function setupPrevStep() {
  if (currentSetupStep > 1) {
    stopAuthPolling()
    currentSetupStep--
    updateSetupUI()
  }
}

export function openAuthFromSetup() {
  showModal("authModal")
}

function startAuthPolling() {
  stopAuthPolling()

  setupAuthPollInterval = setInterval(async () => {
    const hasAuth = await checkAuthStatus()
    if (hasAuth) {
      updateAuthStatusDisplay()
      updateSetupUI()
    }
  }, 1000)
}

async function updateAuthStatusDisplay() {
  const statusBox = document.getElementById("setup-auth-status-box")
  if (!statusBox) return

  const hasAuth = await checkAuthStatus()

  if (hasAuth) {
    statusBox.innerHTML = `
      <div class="setup-auth-success">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
          <polyline points="22 4 12 14.01 9 11.01"></polyline>
        </svg>
        <span>${_("YouTube Music is connected!")}</span>
      </div>`
  } else {
    statusBox.innerHTML = `
      <div class="setup-auth-pending">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="8" x2="12" y2="12"></line>
          <line x1="12" y1="16" x2="12.01" y2="16"></line>
        </svg>
        <span>${_("Not connected yet. Click the button below to authenticate.")}</span>
      </div>`
  }
}

export function onAuthModalClose() {
  if (currentSetupStep === 2) {
    updateAuthStatusDisplay()
    updateSetupUI()
  }
}

export function showAuthRequiredBanner() {
  if (sessionStorage.getItem("authBannerDismissed")) return

  insertBanner(
    "authRequiredBanner",
    "auth-required-banner",
    `
    <div class="auth-banner-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="8" x2="12" y2="12"></line>
        <line x1="12" y1="16" x2="12.01" y2="16"></line>
      </svg>
      <span>${_("YouTube Music authentication is missing.")}</span>
      <button class="btn btn-sm btn-primary" data-action="showModal" data-modal="authModal">${_("Set Up Auth")}</button>
      <button class="auth-banner-close" data-action="dismissAuthBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `,
  )
}

export function dismissAuthBanner() {
  if (removeBanner("authRequiredBanner")) {
    sessionStorage.setItem("authBannerDismissed", "true")
  }
}

export function initSetup() {
  const needsSetup = document.body.dataset.needsSetup === "true"
  const needsAuth = document.body.dataset.needsAuth === "true"

  const setupUserInput = document.getElementById("setup-lastfm-user")
  const setupKeyInput = document.getElementById("setup-lastfm-key")

  if (setupUserInput) {
    setupUserInput.addEventListener("input", () => setupUserInput.classList.remove("input-error"))
  }
  if (setupKeyInput) {
    setupKeyInput.addEventListener("input", () => setupKeyInput.classList.remove("input-error"))
  }

  if (needsSetup) {
    showSetupWizard()
  } else if (needsAuth) {
    showAuthRequiredBanner()
  }

  checkFailureLog()
}

let lastFailureData = null

export async function checkFailureLog() {
  try {
    const response = await fetch("/api/failure_log")
    const data = await response.json()

    if (data.has_failure) {
      lastFailureData = data
      showSyncFailureBanner(data)
    } else {
      removeSyncFailureBanner()
      lastFailureData = null
    }
  } catch (_e) {}
}

export function showSyncFailureBanner(data) {
  const timeAgo = data.timestamp ? formatRelativeTime(data.timestamp) : ""

  let hintHtml = ""
  if (data.hint) {
    hintHtml = `<div class="failure-banner-hint">${escapeHtml(data.hint)}</div>`
  }

  let syncLabel = _("Sync")
  if (data.sync_type === "tags") {
    syncLabel = data.playlist_name ? `${_("Tag playlist")} '${escapeHtml(data.playlist_name)}'` : _("Tag sync")
  }
  const failedLabel = `${syncLabel} ${_("failed")}`

  insertBanner(
    "syncFailureBanner",
    "sync-failure-banner",
    `
    <div class="failure-banner-content">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="15" y1="9" x2="9" y2="15"></line>
        <line x1="9" y1="9" x2="15" y2="15"></line>
      </svg>
      <div class="failure-banner-text">
        <span><strong>${failedLabel}</strong>${timeAgo ? ` (${timeAgo})` : ""}: ${escapeHtml(data.error || _("Unknown error"))}</span>
        ${hintHtml}
      </div>
      <button class="btn btn-sm btn-secondary" data-action="showFailureLogModal">${_("View Details")}</button>
      <button class="failure-banner-close" data-action="dismissSyncFailureBanner" title="Dismiss"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
    </div>
  `,
  )
}

export function removeSyncFailureBanner() {
  removeBanner("syncFailureBanner")
}

export async function dismissSyncFailureBanner() {
  try {
    await fetch("/api/failure_log", { method: "DELETE" })
  } catch (_e) {}
  removeSyncFailureBanner()
  lastFailureData = null
}

export async function showFailureLogModal() {
  if (!lastFailureData) return

  let modalTitle = "Sync Failure Details"
  if (lastFailureData.sync_type === "tags") {
    modalTitle = lastFailureData.playlist_name ? `Tag Playlist '${lastFailureData.playlist_name}' Failure Details` : "Tag Sync Failure Details"
  }

  let modal = document.getElementById("failureLogModal")
  if (!modal) {
    modal = document.createElement("div")
    modal.id = "failureLogModal"
    modal.className = "modal-overlay"
    modal.innerHTML = `
      <div class="modal failure-log-modal">
        <div class="modal-header">
          <h2>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px; vertical-align: middle; color: var(--danger);">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="15" y1="9" x2="9" y2="15"></line>
              <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
            <span class="failure-modal-title">${escapeHtml(modalTitle)}</span>
          </h2>
          <button class="modal-close" data-action="closeModal" data-modal="failureLogModal"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
        </div>
        <div class="modal-body">
          <div class="failure-details">
            <div class="failure-time"></div>
            <div class="failure-error"></div>
            <div class="failure-hint"></div>
            <div class="failure-traceback-section">
              <h4>Stack Trace</h4>
              <pre class="failure-traceback"></pre>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-action="closeModal" data-modal="failureLogModal">Close</button>
          <button type="button" class="btn btn-primary" data-action="dismissAndCloseFailureModal">Dismiss & Close</button>
        </div>
      </div>
    `
    document.body.appendChild(modal)
  }

  const titleEl = modal.querySelector(".failure-modal-title")
  if (titleEl) titleEl.textContent = modalTitle

  const timeEl = modal.querySelector(".failure-time")
  const errorEl = modal.querySelector(".failure-error")
  const hintEl = modal.querySelector(".failure-hint")
  const tracebackEl = modal.querySelector(".failure-traceback")
  const tracebackSection = modal.querySelector(".failure-traceback-section")

  if (lastFailureData.timestamp) {
    const date = new Date(lastFailureData.timestamp)
    const use24Hour = await getUse24HourClock()
    timeEl.innerHTML = `<strong>Time:</strong> ${formatDateTime(date, use24Hour)}`
  }

  errorEl.innerHTML = `<strong>Error:</strong> ${escapeHtml(lastFailureData.error || "Unknown error")}`

  if (lastFailureData.hint) {
    hintEl.innerHTML = `<strong>Hint:</strong> ${escapeHtml(lastFailureData.hint)}`
    hintEl.style.display = ""
  } else {
    hintEl.style.display = "none"
  }

  if (lastFailureData.traceback) {
    tracebackEl.textContent = lastFailureData.traceback
    tracebackSection.style.display = ""
  } else {
    tracebackSection.style.display = "none"
  }

  showModal("failureLogModal")
}

export async function dismissAndCloseFailureModal() {
  await dismissSyncFailureBanner()
  closeModal("failureLogModal")
}
