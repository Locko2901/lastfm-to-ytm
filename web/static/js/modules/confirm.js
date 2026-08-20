import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"

let _resolver = null

function settle(result) {
  const resolve = _resolver
  _resolver = null
  if (resolve) resolve(result)
}

export function confirmDialog({ title, message, confirmLabel, danger = true } = {}) {
  settle(false)

  const titleEl = document.getElementById("appConfirmTitle")
  const msgEl = document.getElementById("appConfirmMessage")
  const acceptBtn = document.getElementById("appConfirmAcceptBtn")
  if (titleEl) titleEl.textContent = title || _("Please confirm")
  if (msgEl) msgEl.textContent = message || ""
  if (acceptBtn) {
    acceptBtn.textContent = confirmLabel || _("Confirm")
    acceptBtn.classList.toggle("btn-danger", danger)
    acceptBtn.classList.toggle("btn-primary", !danger)
  }

  showModal("appConfirmModal")
  acceptBtn?.focus()
  return new Promise(resolve => {
    _resolver = resolve
  })
}

export function appConfirmAccept() {
  closeModal("appConfirmModal")
  settle(true)
}

export function appConfirmCancel() {
  closeModal("appConfirmModal")
  settle(false)
}

export function initConfirm() {
  const modal = document.getElementById("appConfirmModal")
  modal?.addEventListener("click", e => {
    if (e.target === modal) appConfirmCancel()
  })
  document.addEventListener(
    "keydown",
    e => {
      if (e.key === "Escape" && modal?.classList.contains("active")) {
        e.stopPropagation()
        appConfirmCancel()
      }
    },
    true,
  )
}
