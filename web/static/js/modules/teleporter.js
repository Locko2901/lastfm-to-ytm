import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { showToast, withButtonLoading } from "./utils.js"

let _pendingFile = null

function _showError(msg) {
  const el = document.getElementById("teleporter-error")
  if (!el) return
  el.textContent = msg
  el.style.display = ""
}

function _clearError() {
  const el = document.getElementById("teleporter-error")
  if (el) el.style.display = "none"
}

function _updateCacheCount() {
  const count = document.querySelectorAll("#teleporter-cache-menu input[type=checkbox]:checked").length
  const el = document.getElementById("teleporter-cache-count")
  if (el) el.textContent = count > 0 ? `${count} selected` : ""
}

export function toggleCacheDropdown() {
  const toggle = document.getElementById("teleporter-cache-toggle")
  const menu = document.getElementById("teleporter-cache-menu")
  if (!toggle || !menu) return
  const open = menu.style.display === "none"
  menu.style.display = open ? "" : "none"
  toggle.classList.toggle("open", open)
}

export function showTeleporterModal() {
  _pendingFile = null
  const passwordExport = document.getElementById("teleporter-export-password")
  const passwordImport = document.getElementById("teleporter-import-password")
  if (passwordExport) passwordExport.value = ""
  if (passwordImport) passwordImport.value = ""

  const fileInfo = document.getElementById("teleporter-file-info")
  if (fileInfo) fileInfo.style.display = "none"
  const dropzone = document.getElementById("teleporter-dropzone")
  if (dropzone) {
    dropzone.style.display = ""
    dropzone.classList.remove("dragover")
  }
  const preview = document.getElementById("teleporter-preview")
  if (preview) preview.style.display = "none"
  const actions = document.getElementById("teleporter-import-actions")
  if (actions) actions.style.display = "none"
  _clearError()
  const pwWarn = document.getElementById("teleporter-password-warning")
  if (pwWarn) pwWarn.style.display = "none"
  const cacheMenu = document.getElementById("teleporter-cache-menu")
  if (cacheMenu) {
    cacheMenu.style.display = "none"
    for (const cb of cacheMenu.querySelectorAll("input[type=checkbox]")) cb.checked = false
  }
  const cacheToggle = document.getElementById("teleporter-cache-toggle")
  if (cacheToggle) cacheToggle.classList.remove("open")
  _updateCacheCount()

  showModal("teleporterModal")
}

export async function teleporterExport() {
  const password = document.getElementById("teleporter-export-password")?.value || ""
  const pwWarn = document.getElementById("teleporter-password-warning")
  if (password.length < 8) {
    if (pwWarn) {
      pwWarn.textContent = _("Password must be at least 8 characters")
      pwWarn.style.display = ""
    }
    return
  }
  if (pwWarn) pwWarn.style.display = "none"

  const btn = document.getElementById("teleporter-export-btn")
  try {
    await withButtonLoading(btn, _("Encrypting..."), async () => {
      const cacheKeys = [...document.querySelectorAll("#teleporter-cache-menu input[type=checkbox]:checked")].map(cb => cb.value)
      const resp = await fetch("/api/teleporter/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password, cache_keys: cacheKeys }),
      })

      if (!resp.ok) {
        const data = await resp.json()
        throw new Error(data.error || _("Export failed"))
      }

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `teleporter-backup-${new Date().toISOString().slice(0, 10)}.bin`
      a.click()
      URL.revokeObjectURL(url)
      showToast(_("Encrypted backup downloaded"), "success")
    })
  } catch (error) {
    showToast(error.message || _("Export failed"), "error")
  }
}

export function clearTeleporterFile() {
  _pendingFile = null
  const fileInfo = document.getElementById("teleporter-file-info")
  if (fileInfo) fileInfo.style.display = "none"
  const dropzone = document.getElementById("teleporter-dropzone")
  if (dropzone) dropzone.style.display = ""
  const preview = document.getElementById("teleporter-preview")
  if (preview) preview.style.display = "none"
  const actions = document.getElementById("teleporter-import-actions")
  if (actions) actions.style.display = "none"
  const fileInput = document.getElementById("teleporter-file-input")
  if (fileInput) fileInput.value = ""
}

function _handleFile(file) {
  if (!file.name.endsWith(".bin")) {
    showToast(_("Please select a .bin backup file"), "error")
    return
  }
  _pendingFile = file
  const fileInfo = document.getElementById("teleporter-file-info")
  const fileName = document.getElementById("teleporter-file-name")
  const dropzone = document.getElementById("teleporter-dropzone")
  const actions = document.getElementById("teleporter-import-actions")

  if (fileName) fileName.textContent = file.name
  if (fileInfo) fileInfo.style.display = ""
  if (dropzone) dropzone.style.display = "none"
  if (actions) actions.style.display = ""

  const preview = document.getElementById("teleporter-preview")
  if (preview) preview.style.display = "none"
}

export function initTeleporter() {
  const dropzone = document.getElementById("teleporter-dropzone")
  const fileInput = document.getElementById("teleporter-file-input")
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
    if (file) _handleFile(file)
  })
  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0]
    if (file) _handleFile(file)
    fileInput.value = ""
  })

  const cacheToggle = document.getElementById("teleporter-cache-toggle")
  if (cacheToggle) cacheToggle.addEventListener("click", toggleCacheDropdown)
  const cacheMenu = document.getElementById("teleporter-cache-menu")
  if (cacheMenu) cacheMenu.addEventListener("change", _updateCacheCount)
}

export async function teleporterPreview() {
  if (!_pendingFile) return
  const password = document.getElementById("teleporter-import-password")?.value || ""
  if (!password) {
    showToast(_("Enter the decryption password"), "error")
    return
  }

  _clearError()
  const btn = document.getElementById("teleporter-preview-btn")
  try {
    await withButtonLoading(btn, _("Decrypting..."), async () => {
      const formData = new FormData()
      formData.append("file", _pendingFile)
      formData.append("password", password)

      const resp = await fetch("/api/teleporter/preview", {
        method: "POST",
        body: formData,
      })

      const data = await resp.json()
      if (!resp.ok) throw new Error(data.error || _("Preview failed"))

      const statsEl = document.getElementById("teleporter-preview-stats")
      const filesHtml = data.files.map(f => `<span class="teleporter-file-badge">${f}</span>`).join(" ")
      statsEl.innerHTML = `
        <p><strong>${_("Files included")}:</strong> ${data.file_count}</p>
        <div class="teleporter-file-list">${filesHtml}</div>
        ${data.exported_at ? `<p class="text-muted">${_("Exported")}: ${data.exported_at}</p>` : ""}
      `
      document.getElementById("teleporter-preview").style.display = ""
    })
  } catch (error) {
    const msg = error.message || _("Preview failed")
    _showError(msg)
    showToast(msg, "error")
  }
}

export async function teleporterImport() {
  if (!_pendingFile) return
  const password = document.getElementById("teleporter-import-password")?.value || ""
  if (!password) {
    showToast(_("Enter the decryption password"), "error")
    return
  }

  _clearError()
  const btn = document.getElementById("teleporter-import-btn")
  try {
    await withButtonLoading(btn, _("Restoring..."), async () => {
      const formData = new FormData()
      formData.append("file", _pendingFile)
      formData.append("password", password)

      const resp = await fetch("/api/teleporter/import", {
        method: "POST",
        body: formData,
      })

      const data = await resp.json()
      if (!resp.ok) throw new Error(data.error || _("Import failed"))

      _pendingFile = null
      closeModal("teleporterModal")

      const restoredCount = data.restored ? data.restored.length : 0
      showToast(_("Restored %(count)s config files. Restart may be needed for changes to take effect.", { count: restoredCount }), "success")
    })
  } catch (error) {
    const msg = error.message || _("Import failed")
    _showError(msg)
    showToast(msg, "error")
  }
}

export function toggleTeleporterPassword(targetId) {
  const input = document.getElementById(targetId)
  if (!input) return
  const wrapper = input.closest(".password-input-wrapper")
  if (!wrapper) return

  const isPassword = input.type === "password"
  input.type = isPassword ? "text" : "password"

  const eyeOpen = wrapper.querySelector(".eye-open")
  const eyeClosed = wrapper.querySelector(".eye-closed")
  if (eyeOpen) eyeOpen.style.display = isPassword ? "none" : ""
  if (eyeClosed) eyeClosed.style.display = isPassword ? "" : "none"
}
