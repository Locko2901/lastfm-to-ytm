import { _ } from "./i18n.js"
import { escapeHtml, showToast } from "./utils.js"

let entries = []
let editingIndex = -1

const ICON_TEST =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>'
const ICON_ENABLE =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"></path><line x1="12" y1="2" x2="12" y2="12"></line></svg>'
const ICON_DISABLE =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line></svg>'
const ICON_DELETE =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>'

function parseHidden(value) {
  entries = []
  const seen = new Set()
  for (const raw of (value || "").trim().split(/[\s,]+/)) {
    let token = raw.trim()
    if (!token) continue
    let enabled = true
    if (token.startsWith("!")) {
      enabled = false
      token = token.slice(1).trim()
    }
    if (token && !seen.has(token)) {
      seen.add(token)
      entries.push({ url: token, enabled })
    }
  }
}

function syncHidden() {
  const hidden = document.getElementById("APPRISE_URLS")
  if (hidden) hidden.value = entries.map(e => (e.enabled ? "" : "!") + e.url).join(" ")
}

export function renderAppriseList() {
  const hidden = document.getElementById("APPRISE_URLS")
  const list = document.getElementById("appriseList")
  if (!hidden || !list) return
  parseHidden(hidden.value)
  syncHidden()

  if (entries.length === 0) {
    list.innerHTML = `<div class="apprise-empty">${_("No notification targets yet. Add one above.")}</div>`
    return
  }

  list.innerHTML = entries
    .map((e, i) => {
      const safeUrl = escapeHtml(e.url)
      if (i === editingIndex) {
        return `<div class="apprise-row apprise-row-editing">
          <input type="text" class="apprise-edit-input" data-index="${i}" value="${safeUrl}" spellcheck="false" aria-label="${_("Edit Apprise URL")}">
        </div>`
      }
      const rowClass = e.enabled ? "apprise-row" : "apprise-row apprise-row-disabled"
      const toggleLabel = e.enabled ? _("Disable") : _("Enable")
      const toggleIcon = e.enabled ? ICON_DISABLE : ICON_ENABLE
      const disabledFlag = _("(disabled)")
      const urlLabel = e.enabled ? safeUrl : `${safeUrl} <span class="apprise-url-flag">${escapeHtml(disabledFlag)}</span>`
      const urlTooltip = e.enabled ? safeUrl : `${safeUrl} ${escapeHtml(disabledFlag)}`
      return `<div class="${rowClass}">
        <span class="apprise-url" data-index="${i}" data-tooltip="${urlTooltip}">${urlLabel}</span>
        <div class="apprise-row-actions">
          <button type="button" class="btn btn-sm btn-icon" data-action="appriseTestEntry" data-index="${i}" data-tooltip="${_("Send test notification")}" aria-label="${_("Send test notification")}">${ICON_TEST}</button>
          <button type="button" class="btn btn-sm btn-icon" data-action="appriseToggleEntry" data-index="${i}" data-tooltip="${toggleLabel}" aria-label="${toggleLabel}">${toggleIcon}</button>
          <button type="button" class="btn btn-sm btn-icon apprise-btn-danger" data-action="appriseDeleteEntry" data-index="${i}" data-tooltip="${_("Delete")}" aria-label="${_("Delete")}">${ICON_DELETE}</button>
        </div>
      </div>`
    })
    .join("")

  if (editingIndex >= 0) {
    const input = list.querySelector(".apprise-edit-input")
    if (input) {
      input.focus()
      input.select()
      input.addEventListener("keydown", ev => {
        if (ev.key === "Enter") {
          ev.preventDefault()
          commitEdit(input)
        } else if (ev.key === "Escape") {
          ev.preventDefault()
          cancelEdit()
        }
      })
      input.addEventListener("blur", () => commitEdit(input))
    }
  }
}

function addUrl(url) {
  const token = (url || "").trim()
  if (!token) {
    showToast(_("Enter an Apprise URL first"), "warning")
    return false
  }
  if (entries.some(e => e.url === token)) {
    showToast(_("That URL is already in the list"), "warning")
    return false
  }
  entries.push({ url: token, enabled: true })
  syncHidden()
  renderAppriseList()
  return true
}

export function appriseAdd() {
  const input = document.getElementById("appriseNewUrl")
  if (addUrl(input?.value)) input.value = ""
}

export async function appriseTestNew() {
  const input = document.getElementById("appriseNewUrl")
  const url = input?.value?.trim()
  if (!url) {
    showToast(_("Enter an Apprise URL first"), "warning")
    return
  }
  await testUrl(url)
}

export function appriseToggleEntry(index) {
  const entry = entries[Number(index)]
  if (!entry) return
  entry.enabled = !entry.enabled
  syncHidden()
  renderAppriseList()
}

export function appriseDeleteEntry(index) {
  const i = Number(index)
  if (i < 0 || i >= entries.length) return
  entries.splice(i, 1)
  syncHidden()
  renderAppriseList()
}

export function appriseEditEntry(index) {
  const i = Number(index)
  if (i < 0 || i >= entries.length) return
  editingIndex = i
  renderAppriseList()
}

function commitEdit(input) {
  if (editingIndex < 0) return
  const i = editingIndex
  const token = (input.value || "").trim()
  if (!token) {
    cancelEdit()
    return
  }
  if (entries.some((e, j) => j !== i && e.url === token)) {
    showToast(_("That URL is already in the list"), "warning")
    cancelEdit()
    return
  }
  editingIndex = -1
  if (entries[i]) entries[i].url = token
  syncHidden()
  renderAppriseList()
}

function cancelEdit() {
  editingIndex = -1
  renderAppriseList()
}

export async function appriseTestEntry(index) {
  const entry = entries[Number(index)]
  if (entry) await testUrl(entry.url)
}

async function testUrl(url) {
  try {
    const resp = await fetch("/api/apprise/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls: url }),
    })
    const data = await resp.json()
    if (resp.ok) {
      showToast(_("Test notification sent successfully!"), "success")
    } else {
      showToast(data.error || _("Apprise test failed"), "error")
    }
  } catch (_error) {
    showToast(_("Apprise test failed"), "error")
  }
}

export function initApprise() {
  window._renderAppriseList = renderAppriseList
  const input = document.getElementById("appriseNewUrl")
  if (input) {
    input.addEventListener("keydown", ev => {
      if (ev.key === "Enter") {
        ev.preventDefault()
        appriseAdd()
      }
    })
  }
  const list = document.getElementById("appriseList")
  if (list) {
    list.addEventListener("dblclick", ev => {
      const chip = ev.target.closest?.(".apprise-url")
      if (chip && list.contains(chip)) appriseEditEntry(chip.dataset.index)
    })
  }
}
