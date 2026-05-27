import { _ } from "./i18n.js"
import { closeModal, showModal } from "./modals.js"
import { showToast } from "./utils.js"

export const CUSTOM_THEME_GROUPS = [
  {
    title: "Backgrounds",
    vars: [
      { var: "--bg-primary", label: "Page background", type: "color" },
      { var: "--bg-secondary", label: "Secondary background", type: "color" },
      { var: "--bg-card", label: "Card background", type: "color" },
      { var: "--bg-card-hover", label: "Card hover", type: "color" },
      { var: "--bg-input", label: "Input background", type: "color" },
    ],
  },
  {
    title: "Text",
    vars: [
      { var: "--text-primary", label: "Primary text", type: "color" },
      { var: "--text-secondary", label: "Secondary text", type: "color" },
      { var: "--text-muted", label: "Muted text", type: "color" },
    ],
  },
  {
    title: "Accent",
    vars: [
      { var: "--accent", label: "Accent", type: "color+rgb" },
      { var: "--accent-hover", label: "Accent hover", type: "color" },
      { var: "--accent-text", label: "Accent text", type: "color" },
    ],
  },
  {
    title: "Semantic",
    vars: [
      { var: "--success", label: "Success", type: "color+rgb" },
      { var: "--success-dim", label: "Success dim", type: "color" },
      { var: "--warning", label: "Warning", type: "color+rgb" },
      { var: "--warning-dim", label: "Warning dim", type: "color" },
      { var: "--danger", label: "Danger", type: "color+rgb" },
      { var: "--danger-dim", label: "Danger dim", type: "color" },
      { var: "--tags", label: "Tags", type: "color+rgb" },
      { var: "--tags-dim", label: "Tags dim", type: "color" },
    ],
  },
  {
    title: "Borders",
    vars: [
      { var: "--border", label: "Border", type: "color" },
      { var: "--border-light", label: "Border (light)", type: "color" },
    ],
  },
]

const ALL_VARS = CUSTOM_THEME_GROUPS.flatMap(g => g.vars)
const STYLE_ELEMENT_ID = "custom-theme-style"
const VALID_PARENTS = ["dark", "light"]

function emptyStore() {
  return { enabled: false, parents: { dark: {}, light: {} } }
}

function sanitiseStore(raw) {
  if (!raw || typeof raw !== "object") return emptyStore()
  const out = emptyStore()
  out.enabled = !!raw.enabled
  const parents = raw.parents && typeof raw.parents === "object" ? raw.parents : {}
  for (const p of VALID_PARENTS) {
    const bucket = parents[p] && typeof parents[p] === "object" ? parents[p] : {}
    for (const [k, v] of Object.entries(bucket)) {
      if (typeof k === "string" && k.startsWith("--") && typeof v === "string" && /^#[a-f0-9]{6}$/i.test(v)) {
        out.parents[p][k] = v
      }
    }
  }
  return out
}

export function loadCustomTheme() {
  return sanitiseStore(window.__themeOverrides__)
}

function saveLocal(store) {
  window.__themeOverrides__ = store
}

let _persistTimer = null
function schedulePersist(store) {
  saveLocal(store)
  if (_persistTimer) clearTimeout(_persistTimer)
  _persistTimer = setTimeout(() => {
    fetch("/api/theme", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(store),
    }).catch(() => {
      /* best-effort; localStorage still holds the value */
    })
  }, 300)
}

export function getCurrentParent() {
  const t = localStorage.getItem("ytm-theme")
  return VALID_PARENTS.includes(t) ? t : "dark"
}

function hexToRgbTriplet(hex) {
  const m = /^#?([a-f0-9]{6})$/i.exec(hex.trim())
  if (!m) return null
  const n = parseInt(m[1], 16)
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`
}

function buildCss(values) {
  const lines = []
  for (const meta of ALL_VARS) {
    const v = values[meta.var]
    if (!v) continue
    lines.push(`  ${meta.var}: ${v};`)
    if (meta.type === "color+rgb") {
      const triplet = hexToRgbTriplet(v)
      if (triplet) lines.push(`  ${meta.var}-rgb: ${triplet};`)
    }
  }
  if (!lines.length) return ""
  return `:root {\n${lines.join("\n")}\n}\n`
}

function ensureStyleElement() {
  let style = document.getElementById(STYLE_ELEMENT_ID)
  if (!style) {
    style = document.createElement("style")
    style.id = STYLE_ELEMENT_ID
    document.head.appendChild(style)
  }
  return style
}

export function applyCustomTheme(store = loadCustomTheme(), parent = null) {
  const style = ensureStyleElement()
  const activeParent = parent || getCurrentParent()
  if (!store.enabled) {
    style.textContent = ""
    return
  }
  const overrides = store.parents[activeParent] || {}
  style.textContent = buildCss(overrides)
}

export function setCustomEnabled(enabled) {
  const store = loadCustomTheme()
  store.enabled = !!enabled
  schedulePersist(store)
  applyCustomTheme(store)
}

export function onParentThemeChanged() {
  applyCustomTheme()
}

function readComputedVar(name, fallback = "#000000") {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  if (!v) return fallback
  if (/^#[a-f0-9]{3,8}$/i.test(v)) {
    if (v.length === 4) {
      return `#${v[1]}${v[1]}${v[2]}${v[2]}${v[3]}${v[3]}`
    }
    return v.length > 7 ? v.slice(0, 7) : v
  }
  const m = /rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i.exec(v)
  if (m) {
    const toHex = n => Number(n).toString(16).padStart(2, "0")
    return `#${toHex(m[1])}${toHex(m[2])}${toHex(m[3])}`
  }
  return fallback
}

function getEffectiveValue(meta, parentOverrides) {
  if (parentOverrides[meta.var]) return parentOverrides[meta.var]
  return readComputedVar(meta.var)
}

let _editingParent = null
let _previewOverrides = null

function renderModalBody() {
  const body = document.getElementById("customThemeBody")
  if (!body) return
  body.innerHTML = CUSTOM_THEME_GROUPS.map(group => {
    const rows = group.vars
      .map(meta => {
        const val = getEffectiveValue(meta, _previewOverrides)
        return `
          <div class="custom-theme-row">
            <label class="custom-theme-row-label" for="ct-${meta.var}">${_(meta.label)}</label>
            <div class="custom-theme-row-controls">
              <input type="color" id="ct-${meta.var}" data-var="${meta.var}" data-type="${meta.type}" value="${val}">
              <input type="text" class="custom-theme-hex" data-var="${meta.var}" value="${val}" maxlength="7" spellcheck="false">
            </div>
          </div>`
      })
      .join("")
    return `
        <div class="custom-theme-group">
          <h4>${_(group.title)}</h4>
          ${rows}
        </div>`
  }).join("")

  for (const input of body.querySelectorAll("input[type=color]")) {
    input.addEventListener("input", e => {
      const name = e.target.dataset.var
      const value = e.target.value
      _previewOverrides[name] = value
      const hexInput = body.querySelector(`.custom-theme-hex[data-var="${name}"]`)
      if (hexInput) hexInput.value = value
      previewApply()
    })
  }
  for (const input of body.querySelectorAll(".custom-theme-hex")) {
    input.addEventListener("input", e => {
      const value = e.target.value.trim()
      if (!/^#[a-f0-9]{6}$/i.test(value)) return
      const name = e.target.dataset.var
      _previewOverrides[name] = value
      const colorInput = body.querySelector(`input[type=color][data-var="${name}"]`)
      if (colorInput) colorInput.value = value
      previewApply()
    })
  }

  const header = document.getElementById("customThemeParentLabel")
  if (header) {
    const label = _editingParent === "light" ? _("Light theme") : _("Dark theme")
    header.textContent = _("Editing: %(parent)s").replace("%(parent)s", label)
  }
}

function previewApply() {
  const tempStore = loadCustomTheme()
  tempStore.enabled = true
  tempStore.parents[_editingParent] = { ..._previewOverrides }
  applyCustomTheme(tempStore, _editingParent)
}

export function showCustomThemeModal() {
  _editingParent = getCurrentParent()
  if (_editingParent === "dark") document.documentElement.removeAttribute("data-theme")
  else document.documentElement.setAttribute("data-theme", _editingParent)

  const store = loadCustomTheme()
  _previewOverrides = { ...(store.parents[_editingParent] || {}) }

  const style = document.getElementById(STYLE_ELEMENT_ID)
  const savedCss = style ? style.textContent : ""
  if (style) style.textContent = ""

  renderModalBody()

  if (style) style.textContent = savedCss
  previewApply()

  showModal("customThemeModal")
}

export function saveCustomThemeFromModal() {
  const store = loadCustomTheme()
  store.enabled = true
  store.parents[_editingParent] = { ..._previewOverrides }
  schedulePersist(store)
  applyCustomTheme(store)
  const toggle = document.getElementById("custom-theme-toggle")
  if (toggle) toggle.checked = true
  closeModal("customThemeModal")
  showToast(_("Custom theme saved"), "success")
}

export function cancelCustomThemeModal() {
  applyCustomTheme(loadCustomTheme())
  _previewOverrides = null
  _editingParent = null
  closeModal("customThemeModal")
}

export function resetCustomTheme() {
  _previewOverrides = {}
  renderModalBody()
  previewApply()
  showToast(_("Reset to base theme"), "info")
}

export function exportCustomTheme() {
  const payload = {
    enabled: true,
    parents: { ...loadCustomTheme().parents, [_editingParent]: { ..._previewOverrides } },
  }
  const data = JSON.stringify(payload, null, 2)
  const blob = new Blob([data], { type: "application/json" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "ytm-custom-theme.json"
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function importCustomThemeFile(file) {
  const reader = new FileReader()
  reader.onload = () => {
    try {
      const parsed = JSON.parse(reader.result)
      const clean = sanitiseStore(parsed)
      schedulePersist(clean)
      _previewOverrides = { ...(clean.parents[_editingParent] || {}) }
      renderModalBody()
      previewApply()
      showToast(_("Theme imported"), "success")
    } catch (_e) {
      showToast(_("Invalid theme file"), "error")
    }
  }
  reader.readAsText(file)
}

export function triggerImportCustomTheme() {
  const input = document.getElementById("customThemeImportInput")
  if (input) input.click()
}

export function onCustomThemeImportChange(e) {
  const file = e.target.files?.[0]
  if (file) importCustomThemeFile(file)
  e.target.value = ""
}
