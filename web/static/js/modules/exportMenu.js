function closeAll(except) {
  for (const opts of document.querySelectorAll(".export-options")) {
    if (opts === except) continue
    opts.setAttribute("hidden", "")
    const toggle = opts.parentElement?.querySelector("[aria-controls]")
    if (toggle) toggle.setAttribute("aria-expanded", "false")
  }
}

function toggleMenu(toggleId, optionsId) {
  const toggle = document.getElementById(toggleId)
  const options = document.getElementById(optionsId)
  if (!toggle || !options) return
  const willShow = options.hasAttribute("hidden")
  closeAll(willShow ? options : null)
  if (willShow) {
    options.removeAttribute("hidden")
    toggle.setAttribute("aria-expanded", "true")
  } else {
    options.setAttribute("hidden", "")
    toggle.setAttribute("aria-expanded", "false")
  }
}

export function togglePlaylistExport() {
  toggleMenu("playlistExportToggle", "playlistExportOptions")
}

export function toggleCustomPlaylistExport(index) {
  toggleMenu(`customExportToggle-${index}`, `customExportOptions-${index}`)
}

document.addEventListener("click", event => {
  const target = event.target
  if (target.closest(".export-options a")) {
    closeAll(null)
    return
  }
  if (!target.closest(".export-menu")) closeAll(null)
})
