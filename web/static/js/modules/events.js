const STREAM_URL = "/api/events"
const RECONNECT_MIN_MS = 1000
const RECONNECT_MAX_MS = 30000

const handlers = new Map()
let eventSource = null
let reconnectDelay = RECONNECT_MIN_MS
let reconnectTimer = null
let started = false

function dispatch(type, data) {
  const set = handlers.get(type)
  if (!set) return
  for (const fn of set) {
    try {
      fn(data)
    } catch (_err) {
      // Swallow handler errors so one bad subscriber doesn't break the bus.
    }
  }
}

function handleSnapshot(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return
  for (const [type, data] of Object.entries(snapshot)) {
    dispatch(type, data)
  }
}

function connect() {
  if (eventSource) {
    try {
      eventSource.close()
    } catch (_e) {}
  }

  try {
    eventSource = new EventSource(STREAM_URL)
  } catch (_e) {
    scheduleReconnect()
    return
  }

  eventSource.addEventListener("snapshot", e => {
    try {
      handleSnapshot(JSON.parse(e.data))
      reconnectDelay = RECONNECT_MIN_MS
    } catch (_err) {}
  })

  eventSource.onmessage = e => {
    try {
      const event = JSON.parse(e.data)
      if (event?.type) dispatch(event.type, event.data)
    } catch (_err) {}
  }

  eventSource.onerror = () => {
    try {
      eventSource.close()
    } catch (_e) {}
    eventSource = null
    scheduleReconnect()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  const delay = reconnectDelay
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connect()
  }, delay)
}

export function onEvent(type, handler) {
  if (!handlers.has(type)) handlers.set(type, new Set())
  handlers.get(type).add(handler)
  return () => handlers.get(type)?.delete(handler)
}

export function initEvents() {
  if (started) return
  started = true
  connect()
}
