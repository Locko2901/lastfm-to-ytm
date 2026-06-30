import { _ } from "./i18n.js"
import { formatDateTime, getDateTimePrefsSync } from "./utils.js"

const SVG_NS = "http://www.w3.org/2000/svg"
const PAD = { top: 16, right: 16, bottom: 36, left: 44 }
const VIEW_W = 720
const VIEW_H = 280

function el(name, attrs, text) {
  const node = document.createElementNS(SVG_NS, name)
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, String(v))
  if (text != null) node.textContent = text
  return node
}

function collectPoints() {
  const items = document.querySelectorAll("#playlistTracks .track-item")
  const points = []
  let index = 0
  for (const item of items) {
    const raw = item.dataset.score
    if (raw == null || raw === "") continue
    const score = Number.parseFloat(raw)
    if (Number.isNaN(score)) continue
    index += 1
    points.push({
      x: index,
      score,
      artist: item.dataset.originalArtist || "",
      title: item.dataset.originalTitle || "",
      plays: item.dataset.plays || null,
      ts: item.dataset.ts || null,
    })
  }
  return points
}

function buildSvg(points) {
  const maxScore = Math.max(...points.map(p => p.score))
  const yMax = maxScore > 0 ? maxScore : 1
  const n = points.length
  const plotW = VIEW_W - PAD.left - PAD.right
  const plotH = VIEW_H - PAD.top - PAD.bottom

  const sx = i => PAD.left + (n > 1 ? (plotW * (i - 1)) / (n - 1) : plotW / 2)
  const sy = score => PAD.top + plotH - (plotH * score) / yMax

  const svg = el("svg", {
    viewBox: `0 0 ${VIEW_W} ${VIEW_H}`,
    class: "playlist-graph-svg",
    role: "img",
    "aria-label": _("Track score by playlist position"),
    preserveAspectRatio: "xMidYMid meet",
  })

  const ticks = 4
  for (let t = 0; t <= ticks; t++) {
    const value = (yMax * t) / ticks
    const y = sy(value)
    svg.appendChild(el("line", { x1: PAD.left, y1: y, x2: VIEW_W - PAD.right, y2: y, class: "pg-grid" }))
    svg.appendChild(el("text", { x: PAD.left - 8, y: y + 4, class: "pg-axis-label", "text-anchor": "end" }, value.toFixed(2)))
  }

  svg.appendChild(el("line", { x1: PAD.left, y1: PAD.top, x2: PAD.left, y2: PAD.top + plotH, class: "pg-axis" }))
  svg.appendChild(el("line", { x1: PAD.left, y1: PAD.top + plotH, x2: VIEW_W - PAD.right, y2: PAD.top + plotH, class: "pg-axis" }))

  const xTicks = n === 1 ? [1] : [1, Math.ceil(n / 2), n]
  for (const xv of [...new Set(xTicks)]) {
    svg.appendChild(el("text", { x: sx(xv), y: PAD.top + plotH + 18, class: "pg-axis-label", "text-anchor": "middle" }, String(xv)))
  }

  svg.appendChild(el("text", { x: PAD.left + plotW / 2, y: VIEW_H - 4, class: "pg-axis-title", "text-anchor": "middle" }, _("Playlist position")))
  svg.appendChild(
    el(
      "text",
      { x: 12, y: PAD.top + plotH / 2, class: "pg-axis-title", "text-anchor": "middle", transform: `rotate(-90 12 ${PAD.top + plotH / 2})` },
      _("Score"),
    ),
  )

  if (n > 1) {
    const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(2)} ${sy(p.score).toFixed(2)}`).join(" ")
    svg.appendChild(el("path", { d, class: "pg-line" }))
  }

  const prefs = getDateTimePrefsSync()
  for (const p of points) {
    const c = el("circle", { cx: sx(p.x), cy: sy(p.score), r: 3.5, class: "pg-point" })
    const lines = [`#${p.x} ${p.artist} - ${p.title}`, `${_("Score")}: ${p.score.toFixed(4)}`]
    if (p.plays) lines.push(`${_("Plays")}: ${p.plays}`)
    if (p.ts) {
      const date = new Date(Number(p.ts) * 1000)
      if (!Number.isNaN(date.getTime())) lines.push(`${_("Last played")}: ${formatDateTime(date, prefs)}`)
    }
    c.setAttribute("data-tooltip", lines.join("\n"))
    svg.appendChild(c)
  }

  return svg
}

export function togglePlaylistGraph() {
  const container = document.getElementById("playlistGraph")
  const toggle = document.getElementById("playlistGraphToggle")
  if (!container) return

  const willShow = container.hasAttribute("hidden")
  if (!willShow) {
    container.setAttribute("hidden", "")
    container.replaceChildren()
    if (toggle) {
      toggle.setAttribute("aria-expanded", "false")
      const label = toggle.querySelector("span")
      if (label) label.textContent = _("Show Graph")
    }
    return
  }

  const points = collectPoints()
  container.replaceChildren()
  if (points.length === 0) {
    container.appendChild(
      Object.assign(document.createElement("p"), { className: "pg-empty", textContent: _("No score data available. Run a sync first.") }),
    )
  } else {
    container.appendChild(buildSvg(points))
  }
  container.removeAttribute("hidden")
  if (toggle) {
    toggle.setAttribute("aria-expanded", "true")
    const label = toggle.querySelector("span")
    if (label) label.textContent = _("Hide Graph")
  }
}
