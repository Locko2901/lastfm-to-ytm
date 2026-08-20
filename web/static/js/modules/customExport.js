import { confirmDialog } from "./confirm.js"
import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { escapeHtml, showToast } from "./utils.js"

const PLACEHOLDER_RE = /\{(\w+)\}/g
const PREVIEW_LINES = 8

let _target = null // { base, name }
let _tracks = []
let _fieldsLoaded = false
let _formats = [] // [{ name, template, extension, ... }]
let _editingName = null // name of the saved format currently loaded in the builder (for rename/edit)

// Mirror of web/services/export.py::apply_custom_template - keep in sync.
function applyTemplate(template, values) {
  return template.replace(PLACEHOLDER_RE, (match, key) => (key in values ? values[key] : match))
}

function trackValues(track, index, total, playlistName) {
  const title = track.title || ""
  return {
    index: String(index),
    artist: track.artist || "",
    title,
    yt_title: track.yt_title || title,
    video_id: track.video_id || "",
    url: track.url || "",
    source: track.source || "",
    tags: Array.isArray(track.tags) ? track.tags.join(", ") : "",
    playlist: playlistName,
    count: String(total),
  }
}

const KNOWN_EXTENSIONS = ["txt", "md", "csv", "tsv", "json", "m3u", "m3u8", "xml", "nfo", "html"]
const EXT_RE = /^[a-z0-9]{1,8}$/

function els() {
  return {
    select: document.getElementById("customExportFormatSelect"),
    name: document.getElementById("customExportName"),
    template: document.getElementById("customExportTemplate"),
    header: document.getElementById("customExportHeader"),
    footer: document.getElementById("customExportFooter"),
    separator: document.getElementById("customExportSeparator"),
    extSelect: document.getElementById("customExportExtSelect"),
    extCustom: document.getElementById("customExportExtCustom"),
    extError: document.getElementById("customExportExtError"),
    outputError: document.getElementById("customExportOutputError"),
    del: document.getElementById("customExportDeleteBtn"),
    preview: document.getElementById("customExportPreview"),
  }
}

function rawExtension() {
  const { extSelect, extCustom } = els()
  const choice = extSelect?.value || "txt"
  const value = choice === "__custom__" ? extCustom?.value || "" : choice
  return value.trim().replace(/^\.+/, "").toLowerCase()
}

function validateExtension() {
  const { extSelect, extCustom, extError } = els()
  const isCustom = extSelect?.value === "__custom__"
  if (extCustom) extCustom.hidden = !isCustom
  const ext = rawExtension()
  const valid = EXT_RE.test(ext)
  if (extError) {
    if (isCustom && !valid) {
      extError.textContent = _("Use 1-8 letters or digits (e.g. txt, md, json).")
      extError.hidden = false
    } else {
      extError.hidden = true
    }
  }
  if (extCustom) extCustom.classList.toggle("input-error", isCustom && !valid)
  return valid ? ext : null
}

function setExtension(ext) {
  const { extSelect, extCustom } = els()
  const clean = (ext || "txt").trim().replace(/^\.+/, "").toLowerCase()
  if (KNOWN_EXTENSIONS.includes(clean)) {
    if (extSelect) extSelect.value = clean
    if (extCustom) extCustom.value = ""
  } else {
    if (extSelect) extSelect.value = "__custom__"
    if (extCustom) extCustom.value = clean
  }
  validateExtension()
}

function wrapFields() {
  const { header, footer, separator } = els()
  const sep = separator?.value ?? ""
  return {
    header: header?.value ?? "",
    footer: footer?.value ?? "",
    separator: sep === "" ? "\n" : sep,
  }
}

function renderPreview() {
  const { template, preview } = els()
  if (!template || !preview) return
  if (!_tracks.length) {
    preview.textContent = _("No cached tracks to preview.")
    refreshOutputValidation()
    return
  }
  const { header, footer, separator } = wrapFields()
  const body = renderFullBody(template.value, header, footer, separator).replace(/\n$/, "")
  const lines = body.split("\n")
  if (lines.length > PREVIEW_LINES) {
    const head = lines.slice(0, PREVIEW_LINES - 1)
    const last = lines[lines.length - 1]
    preview.textContent = [...head, `… (${lines.length - PREVIEW_LINES} ${_("more")})`, last].join("\n")
  } else {
    preview.textContent = lines.join("\n")
  }
  refreshOutputValidation()
}

// Render the whole playlist (mirrors web/services/export.py::tracks_to_custom) so validation matches the server.
function renderFullBody(template, header, footer, separator) {
  const total = _tracks.length
  const items = _tracks.map((t, i) => applyTemplate(template, trackValues(t, i + 1, total, _target?.name || "")))
  let body = `${header}${items.join(separator)}${footer}`
  if (!body.endsWith("\n")) body += "\n"
  return body
}

// Mirror of web/services/export.py::custom_output_error - returns the bad extension or null.
function outputExtensionError(body, ext) {
  if (ext === "json") {
    try {
      JSON.parse(body)
    } catch {
      return "json"
    }
  }
  return null
}

function refreshOutputValidation() {
  const { template, outputError } = els()
  if (!outputError) return true
  const ext = validateExtension()
  if (ext === null || _tracks.length === 0) {
    outputError.hidden = true
    return true
  }
  const { header, footer, separator } = wrapFields()
  const bad = outputExtensionError(renderFullBody(template?.value ?? "", header, footer, separator), ext)
  if (bad) {
    outputError.textContent = _(
      "This template does not produce valid .%(ext)s. Pick a plain-text extension like txt, or use the built-in %(ext)s export.",
      {
        ext: bad,
      },
    )
    outputError.hidden = false
    return false
  }
  outputError.hidden = true
  return true
}

function insertPlaceholder(field) {
  const { template } = els()
  if (!template) return
  const token = `{${field}}`
  const start = template.selectionStart ?? template.value.length
  const end = template.selectionEnd ?? template.value.length
  template.value = template.value.slice(0, start) + token + template.value.slice(end)
  const caret = start + token.length
  template.setSelectionRange(caret, caret)
  template.focus()
  renderPreview()
}

async function loadFields() {
  if (_fieldsLoaded) return
  const chipsEl = document.getElementById("customExportChips")
  if (!chipsEl) return
  try {
    const resp = await fetch("/api/export/fields")
    if (!resp.ok) throw new Error()
    const data = await resp.json()
    chipsEl.innerHTML = (data.fields || [])
      .map(
        f =>
          `<button type="button" class="custom-export-chip" data-field="${escapeHtml(f.name)}" title="${escapeHtml(f.description)}">{${escapeHtml(f.name)}}</button>`,
      )
      .join("")
    chipsEl.addEventListener("click", e => {
      const chip = e.target.closest(".custom-export-chip")
      if (chip) insertPlaceholder(chip.dataset.field)
    })
    _fieldsLoaded = true
  } catch {
    chipsEl.textContent = _("Failed to load placeholders")
  }
}

function renderFormatOptions(selectedName) {
  const { select } = els()
  if (!select) return
  const opts = [`<option value="__new__">${escapeHtml(_("New format…"))}</option>`]
  for (const f of _formats) {
    const sel = f.name === selectedName ? " selected" : ""
    opts.push(`<option value="${escapeHtml(f.name)}"${sel}>${escapeHtml(f.name)}</option>`)
  }
  select.innerHTML = opts.join("")
}

export async function loadExportFormats() {
  try {
    const resp = await fetch("/api/export-formats")
    if (!resp.ok) throw new Error()
    const data = await resp.json()
    _formats = Array.isArray(data.formats) ? data.formats : []
  } catch {
    _formats = []
  }
  return _formats
}

function applyFormat(fmt) {
  const { name, template, header, footer, separator, del } = els()
  _editingName = fmt ? fmt.name : null
  if (fmt) {
    if (name) name.value = fmt.name
    if (template) template.value = fmt.template
    if (header) header.value = fmt.header ?? ""
    if (footer) footer.value = fmt.footer ?? ""
    if (separator) separator.value = fmt.separator != null && fmt.separator !== "\n" ? fmt.separator : ""
    setExtension(fmt.extension)
    if (del) del.hidden = false
  } else {
    if (name) name.value = ""
    if (header) header.value = ""
    if (footer) footer.value = ""
    if (separator) separator.value = ""
    setExtension("txt")
    if (del) del.hidden = true
  }
  renderPreview()
}

function onFormatSelected() {
  const { select } = els()
  const value = select?.value
  if (!value || value === "__new__") {
    applyFormat(null)
    return
  }
  const fmt = _formats.find(f => f.name === value)
  if (fmt) applyFormat(fmt)
}

async function loadTracks() {
  const { preview } = els()
  if (preview) preview.textContent = _("Loading...")
  _tracks = []
  try {
    const resp = await fetch(`${_target.base}?format=json`)
    if (!resp.ok) throw new Error()
    const data = await resp.json()
    _tracks = data.tracks || []
    if (data.playlist) _target.name = data.playlist
  } catch {
    // Preview simply stays empty; download still works server-side.
  }
  renderPreview()
}

export async function showCustomExportModal(el, preselectName = null, manage = false) {
  const manageMode = manage || el?.dataset?.manage != null
  const index = el?.dataset?.index
  if (index != null && index !== "") {
    _target = { base: `/api/custom-playlists/${parseInt(index, 10)}/export`, name: el.dataset.name || "" }
  } else {
    _target = { base: "/api/playlist/export", name: "" }
  }

  const downloadBtn = document.getElementById("customExportDownloadBtn")
  const saveBtn = document.getElementById("customExportSaveBtn")
  if (downloadBtn) downloadBtn.hidden = manageMode
  if (saveBtn) {
    saveBtn.classList.toggle("btn-primary", manageMode)
    saveBtn.classList.toggle("btn-secondary", !manageMode)
  }

  const targetEl = document.getElementById("customExportTarget")
  if (targetEl) {
    if (manageMode) {
      targetEl.textContent = _("Create or edit a reusable export format. The preview uses your main playlist.")
    } else {
      targetEl.textContent = _target.name ? _("Exporting: %(name)s", { name: _target.name }) : _("Exporting the main playlist")
    }
  }

  const { select, template, extSelect, extCustom, header, footer, separator } = els()
  if (template && !template.dataset.bound) {
    template.addEventListener("input", renderPreview)
    template.dataset.bound = "1"
  }
  for (const wrap of [header, footer, separator]) {
    if (wrap && !wrap.dataset.bound) {
      wrap.addEventListener("input", renderPreview)
      wrap.dataset.bound = "1"
    }
  }
  if (select && !select.dataset.bound) {
    select.addEventListener("change", onFormatSelected)
    select.dataset.bound = "1"
  }
  if (extSelect && !extSelect.dataset.bound) {
    extSelect.addEventListener("change", refreshOutputValidation)
    extSelect.dataset.bound = "1"
  }
  if (extCustom && !extCustom.dataset.bound) {
    extCustom.addEventListener("input", refreshOutputValidation)
    extCustom.dataset.bound = "1"
  }

  showModal("customExportModal")
  await Promise.all([loadFields(), loadTracks(), loadExportFormats()])
  const preselect = preselectName && _formats.some(f => f.name === preselectName) ? preselectName : "__new__"
  renderFormatOptions(preselect)
  if (preselect === "__new__") {
    applyFormat(null)
  } else {
    onFormatSelected()
  }
}

function currentDraft() {
  const { name, template } = els()
  const { header, footer, separator } = wrapFields()
  return {
    name: (name?.value || "").trim(),
    template: template?.value ?? "",
    extension: validateExtension(),
    header,
    footer,
    separator,
  }
}

async function persistFormats(formats) {
  const resp = await fetch("/api/export-formats", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ formats }),
  })
  if (!resp.ok) throw new Error()
  const data = await resp.json()
  _formats = Array.isArray(data.formats) ? data.formats : []
  return _formats
}

export async function saveCustomExportFormat() {
  const draft = currentDraft()
  if (!draft.name) {
    showToast(_("Give the format a name first"), "warning")
    return
  }
  if (!draft.template.trim()) {
    showToast(_("Template cannot be empty"), "error")
    return
  }
  if (draft.extension === null) {
    showToast(_("Fix the file extension first"), "error")
    return
  }
  const newKey = draft.name.toLowerCase()
  const oldKey = _editingName ? _editingName.toLowerCase() : null
  const collides = _formats.some(f => f.name.toLowerCase() === newKey && f.name.toLowerCase() !== oldKey)
  if (
    collides &&
    !(await confirmDialog({
      title: _("Overwrite format"),
      message: _('A format named "%(name)s" already exists. Overwrite it?', { name: draft.name }),
      confirmLabel: _("Overwrite"),
    }))
  ) {
    return
  }
  const next = _formats.filter(f => {
    const k = f.name.toLowerCase()
    return k !== newKey && k !== oldKey
  })
  next.push(draft)
  try {
    await persistFormats(next)
    renderFormatOptions(draft.name)
    onFormatSelected()
    if (window._renderExportFormatsSettings) window._renderExportFormatsSettings()
    showToast(_("Export format saved"), "success")
  } catch {
    showToast(_("Failed to save export format"), "error")
  }
}

export async function deleteCustomExportFormat() {
  const { select } = els()
  const name = select?.value
  if (!name || name === "__new__") return
  if (
    !(await confirmDialog({
      title: _("Delete format"),
      message: _('Delete the export format "%(name)s"?', { name }),
      confirmLabel: _("Delete"),
    }))
  ) {
    return
  }
  const next = _formats.filter(f => f.name !== name)
  try {
    await persistFormats(next)
    renderFormatOptions("__new__")
    applyFormat(null)
    if (window._renderExportFormatsSettings) window._renderExportFormatsSettings()
    showToast(_("Export format deleted"), "success")
  } catch {
    showToast(_("Failed to delete export format"), "error")
  }
}

export function downloadCustomExport() {
  if (!_target) return
  const draft = currentDraft()
  if (!draft.template.trim()) {
    showToast(_("Template cannot be empty"), "error")
    return
  }
  if (draft.extension === null) {
    showToast(_("Fix the file extension first"), "error")
    return
  }
  if (!refreshOutputValidation()) {
    showToast(_("This template does not produce a valid file for the chosen extension"), "error")
    return
  }
  const params = new URLSearchParams({
    format: "custom",
    template: draft.template,
    ext: draft.extension,
    header: draft.header,
    footer: draft.footer,
    sep: draft.separator,
  })
  const a = document.createElement("a")
  a.href = `${_target.base}?${params.toString()}`
  a.download = ""
  a.click()
  closeModal("customExportModal")
}

export async function renderExportFormatsSettings() {
  const list = document.getElementById("exportFormatsList")
  if (!list) return
  await loadExportFormats()
  if (_formats.length === 0) {
    list.innerHTML = `<div class="export-formats-empty">${escapeHtml(_("No saved formats yet. Use “Restore defaults” to bring back the built-ins."))}</div>`
    return
  }
  const editLabel = _("Edit")
  const deleteLabel = _("Delete")
  const builtinLabel = _("Built-in")
  list.innerHTML = _formats
    .map(f => {
      const safeName = escapeHtml(f.name)
      const badge = f.builtin
        ? `<span class="export-formats-badge" title="${escapeHtml(_("Ships with the app"))}">${escapeHtml(builtinLabel)}</span>`
        : ""
      return `<div class="export-formats-row" data-action="editExportFormat" data-name="${safeName}" role="button" tabindex="0" title="${escapeHtml(_("Edit this format"))}">
        <div class="export-formats-info">
          <div class="export-formats-head">
            <span class="export-formats-name">${safeName}</span>
            ${badge}
            <span class="export-formats-ext">.${escapeHtml(f.extension || "txt")}</span>
          </div>
          <code class="export-formats-template">${escapeHtml(f.template)}</code>
        </div>
        <div class="export-formats-actions">
          <button type="button" class="btn btn-sm btn-icon" data-action="editExportFormat" data-name="${safeName}" data-stop-propagation aria-label="${escapeHtml(editLabel)}" title="${escapeHtml(editLabel)}">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path></svg>
          </button>
          <button type="button" class="btn btn-sm btn-icon export-formats-del" data-action="deleteExportFormatByName" data-name="${safeName}" data-stop-propagation aria-label="${escapeHtml(deleteLabel)}" title="${escapeHtml(deleteLabel)}">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      </div>`
    })
    .join("")
}

export function editExportFormat(name) {
  if (!name) return
  showCustomExportModal(null, name, true)
}

export async function restoreDefaultExportFormats() {
  try {
    const resp = await fetch("/api/export-formats/restore-defaults", { method: "POST" })
    if (!resp.ok) throw new Error()
    const data = await resp.json()
    _formats = Array.isArray(data.formats) ? data.formats : []
    await renderExportFormatsSettings()
    showToast(_("Built-in formats restored"), "success")
  } catch {
    showToast(_("Failed to restore defaults"), "error")
  }
}

export async function deleteExportFormatByName(name) {
  if (!name) return
  if (
    !(await confirmDialog({
      title: _("Delete format"),
      message: _('Delete the export format "%(name)s"?', { name }),
      confirmLabel: _("Delete"),
    }))
  ) {
    return
  }
  const next = _formats.filter(f => f.name !== name)
  try {
    await persistFormats(next)
    await renderExportFormatsSettings()
    showToast(_("Export format deleted"), "success")
  } catch {
    showToast(_("Failed to delete export format"), "error")
  }
}

export function initExportFormats() {
  window._renderExportFormatsSettings = renderExportFormatsSettings
}
