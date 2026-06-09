let tooltipElement = null
let showTimeout = null
let hideTimeout = null
const SHOW_DELAY = 400
const HIDE_DELAY = 100
const OFFSET = 8

function ensureTooltipElement() {
  if (!tooltipElement) {
    tooltipElement = document.createElement("div")
    tooltipElement.className = "tooltip"
    tooltipElement.setAttribute("role", "tooltip")
    document.body.appendChild(tooltipElement)
  }
  return tooltipElement
}

function positionTooltip(target) {
  const tooltip = ensureTooltipElement()
  const rect = target.getBoundingClientRect()
  const tooltipRect = tooltip.getBoundingClientRect()

  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight

  let position = "top"
  let left, top

  top = rect.top - tooltipRect.height - OFFSET
  left = rect.left + (rect.width - tooltipRect.width) / 2

  if (top < OFFSET) {
    top = rect.bottom + OFFSET
    position = "bottom"
  }

  if (top + tooltipRect.height > viewportHeight - OFFSET) {
    top = rect.top + (rect.height - tooltipRect.height) / 2

    left = rect.right + OFFSET
    position = "right"

    if (left + tooltipRect.width > viewportWidth - OFFSET) {
      left = rect.left - tooltipRect.width - OFFSET
      position = "left"
    }
  }

  const clampedLeft = Math.max(OFFSET, Math.min(left, viewportWidth - tooltipRect.width - OFFSET))
  top = Math.max(OFFSET, Math.min(top, viewportHeight - tooltipRect.height - OFFSET))

  tooltip.style.left = `${clampedLeft}px`
  tooltip.style.top = `${top}px`
  tooltip.setAttribute("data-position", position)

  if (position === "top" || position === "bottom") {
    const targetCenter = rect.left + rect.width / 2
    const arrowOffset = targetCenter - clampedLeft
    const clamped = Math.max(12, Math.min(arrowOffset, tooltipRect.width - 12))
    tooltip.style.setProperty("--arrow-offset", `${clamped}px`)
  } else {
    tooltip.style.removeProperty("--arrow-offset")
  }
}

function showTooltip(target) {
  const text = target.getAttribute("data-tooltip")
  if (!text) return

  clearTimeout(hideTimeout)

  showTimeout = setTimeout(() => {
    const tooltip = ensureTooltipElement()
    tooltip.textContent = text

    tooltip.style.visibility = "hidden"
    tooltip.classList.add("visible")

    requestAnimationFrame(() => {
      positionTooltip(target)
      tooltip.style.visibility = ""
    })
  }, SHOW_DELAY)
}

function hideTooltip() {
  clearTimeout(showTimeout)

  hideTimeout = setTimeout(() => {
    if (tooltipElement) {
      tooltipElement.classList.remove("visible")
    }
  }, HIDE_DELAY)
}

function convertTitleAttributes() {
  const elements = document.querySelectorAll("[title]")
  for (const el of elements) {
    const title = el.getAttribute("title")
    if (title && !el.hasAttribute("data-tooltip")) {
      el.setAttribute("data-tooltip", title)
      el.removeAttribute("title")
    }
  }
}

export function initTooltips() {
  convertTitleAttributes()

  document.addEventListener(
    "mouseenter",
    e => {
      if (!e.target?.closest) return
      const target = e.target.closest("[data-tooltip]")
      if (target) {
        showTooltip(target)
      }
    },
    true,
  )

  document.addEventListener(
    "mouseleave",
    e => {
      if (!e.target?.closest) return
      const target = e.target.closest("[data-tooltip]")
      if (target) {
        hideTooltip()
      }
    },
    true,
  )

  document.addEventListener("scroll", hideTooltip, true)

  document.addEventListener(
    "click",
    () => {
      clearTimeout(showTimeout)
      if (tooltipElement) {
        tooltipElement.classList.remove("visible")
      }
    },
    true,
  )

  const observer = new MutationObserver(mutations => {
    let shouldConvert = false
    for (const mutation of mutations) {
      if (mutation.type === "childList" && mutation.addedNodes.length) {
        shouldConvert = true
        break
      }
      if (mutation.type === "attributes" && mutation.attributeName === "title") {
        shouldConvert = true
        break
      }
    }
    if (shouldConvert) {
      convertTitleAttributes()
    }
  })

  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["title"],
  })
}
