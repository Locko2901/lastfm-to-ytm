import { _ } from "./i18n.js"

const sources = new Map()

function getSource(url, key) {
  let src = sources.get(url)
  if (!src) {
    src = { url, key, items: [], fetched: false, promise: null }
    sources.set(url, src)
  }
  return src
}

async function ensureSuggestions(src) {
  if (src.fetched) return
  if (src.promise) return src.promise
  src.promise = fetch(src.url)
    .then(r => (r.ok ? r.json() : {}))
    .then(data => {
      src.items = data[src.key] || []
      src.fetched = true
    })
    .catch(() => {
      src.items = []
      src.fetched = true
    })
  return src.promise
}

export function invalidateTagSuggestions() {
  const src = sources.get("/api/tags/suggestions")
  if (src) {
    src.fetched = false
    src.promise = null
  }
}

const instances = new Map()

export function initTagInput(inputId, sourceUrl = "/api/tags/suggestions", sourceKey = "tags") {
  const original = document.getElementById(inputId)
  if (!original || instances.has(inputId)) return

  const wrapper = document.createElement("div")
  wrapper.className = "tag-input-wrapper"

  const pillContainer = document.createElement("div")
  pillContainer.className = "tag-input-pills"

  const typingInput = document.createElement("input")
  typingInput.type = "text"
  typingInput.className = "tag-input-field"
  typingInput.placeholder = original.placeholder || _("Add a tag...")
  typingInput.autocomplete = "off"

  pillContainer.appendChild(typingInput)
  wrapper.appendChild(pillContainer)

  const dropdown = document.createElement("div")
  dropdown.className = "tag-input-dropdown"
  wrapper.appendChild(dropdown)

  original.style.display = "none"
  original.insertAdjacentElement("afterend", wrapper)

  const state = {
    tags: [],
    inputId,
    original,
    typingInput,
    pillContainer,
    dropdown,
    wrapper,
    selectedIndex: -1,
    source: getSource(sourceUrl, sourceKey),
  }
  instances.set(inputId, state)

  const existing = original.value
    .split(",")
    .map(t => t.trim().toLowerCase())
    .filter(Boolean)
  for (const t of existing) addTag(state, t, false)
  syncToOriginal(state)

  typingInput.addEventListener("input", () => onInput(state))
  typingInput.addEventListener("keydown", e => onKeydown(state, e))
  typingInput.addEventListener("focus", () => onInput(state))

  document.addEventListener("mousedown", e => {
    if (!wrapper.contains(e.target)) closeDropdown(state)
  })

  pillContainer.addEventListener("click", () => typingInput.focus())
}

export function setTagInputValue(inputId, commaSeparated) {
  const state = instances.get(inputId)
  if (!state) return
  state.tags = []
  for (const p of state.pillContainer.querySelectorAll(".tag-input-pill")) p.remove()
  const tags = commaSeparated
    .split(",")
    .map(t => t.trim().toLowerCase())
    .filter(Boolean)
  for (const t of tags) addTag(state, t, false)
  syncToOriginal(state)
}

export function getTagInputValue(inputId) {
  const state = instances.get(inputId)
  return state ? state.tags.join(", ") : ""
}

function addTag(state, tag, focus = true) {
  tag = tag.trim().toLowerCase()
  if (!tag || state.tags.includes(tag)) return

  state.tags.push(tag)

  const pill = document.createElement("span")
  pill.className = "tag-input-pill"
  pill.textContent = tag

  const removeBtn = document.createElement("button")
  removeBtn.type = "button"
  removeBtn.className = "tag-input-pill-remove"
  removeBtn.setAttribute("aria-label", _("Remove"))
  removeBtn.innerHTML =
    '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>'
  removeBtn.addEventListener("click", e => {
    e.stopPropagation()
    state.tags = state.tags.filter(t => t !== tag)
    pill.remove()
    syncToOriginal(state)
  })

  pill.appendChild(removeBtn)
  state.pillContainer.insertBefore(pill, state.typingInput)
  syncToOriginal(state)

  if (focus) {
    state.typingInput.value = ""
    state.typingInput.focus()
    closeDropdown(state)
  }
}

function syncToOriginal(state) {
  state.original.value = state.tags.join(", ")
}

async function onInput(state) {
  await ensureSuggestions(state.source)
  const query = state.typingInput.value.trim().toLowerCase()
  renderDropdown(state, query)
}

function onKeydown(state, e) {
  const items = state.dropdown.querySelectorAll(".tag-input-option")

  if (e.key === "ArrowDown") {
    e.preventDefault()
    state.selectedIndex = Math.min(state.selectedIndex + 1, items.length - 1)
    updateSelection(items, state.selectedIndex)
  } else if (e.key === "ArrowUp") {
    e.preventDefault()
    state.selectedIndex = Math.max(state.selectedIndex - 1, 0)
    updateSelection(items, state.selectedIndex)
  } else if (e.key === "Enter") {
    e.preventDefault()
    if (state.selectedIndex >= 0 && items[state.selectedIndex]) {
      items[state.selectedIndex].click()
    } else {
      const val = state.typingInput.value.trim()
      if (val) addTag(state, val)
    }
  } else if (e.key === "Backspace" && !state.typingInput.value) {
    // Remove last pill
    if (state.tags.length > 0) {
      state.tags.pop()
      const pills = state.pillContainer.querySelectorAll(".tag-input-pill")
      if (pills.length) pills[pills.length - 1].remove()
      syncToOriginal(state)
    }
  } else if (e.key === "Escape") {
    closeDropdown(state)
  } else if (e.key === ",") {
    e.preventDefault()
    const val = state.typingInput.value.trim()
    if (val) addTag(state, val)
  }
}

function renderDropdown(state, query) {
  state.selectedIndex = -1
  const { dropdown, tags: currentTags } = state
  const allTags = state.source.items

  const filtered = allTags.filter(t => {
    const lower = t.toLowerCase()
    return !currentTags.includes(lower) && (!query || lower.includes(query))
  })
  const showCustom = query && !allTags.some(t => t.toLowerCase() === query) && !currentTags.includes(query)

  if (filtered.length === 0 && !showCustom) {
    closeDropdown(state)
    return
  }

  let html = ""

  for (const tag of filtered) {
    const esc = tag.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;")
    html += `<div class="tag-input-option" data-tag="${esc}">${esc}</div>`
  }

  if (showCustom) {
    const esc = query.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;")
    html += `<div class="tag-input-option tag-input-option-custom" data-tag="${esc}">${_("Add")} "<strong>${esc}</strong>"</div>`
  }

  dropdown.innerHTML = html
  dropdown.classList.add("open")

  for (const opt of dropdown.querySelectorAll(".tag-input-option")) {
    opt.addEventListener("mousedown", e => {
      e.preventDefault()
      addTag(state, opt.dataset.tag)
    })
  }
}

function updateSelection(items, index) {
  for (const [i, item] of [...items].entries()) item.classList.toggle("selected", i === index)
}

function closeDropdown(state) {
  state.dropdown.classList.remove("open")
  state.dropdown.innerHTML = ""
  state.selectedIndex = -1
}
