const _pollers = new Map()

let _initialized = false

function _ensureInitialized() {
  if (_initialized) return
  _initialized = true

  document.addEventListener("visibilitychange", _handleVisibilityChange)
}

function _handleVisibilityChange() {
  const isVisible = !document.hidden

  _pollers.forEach((poller, _name) => {
    if (isVisible) {
      if (poller.runOnVisible && poller.callback) {
        try {
          poller.callback()
        } catch (_e) {}
      }
      _startPoller(poller)
    } else {
      _stopPoller(poller)
    }
  })
}

function _startPoller(poller) {
  if (poller.intervalId) return
  if (!poller.callback || !poller.intervalMs) return

  poller.intervalId = setInterval(() => {
    try {
      poller.callback()
    } catch (_e) {}
  }, poller.intervalMs)
}

function _stopPoller(poller) {
  if (poller.intervalId) {
    clearInterval(poller.intervalId)
    poller.intervalId = null
  }
}

export function registerPoller(name, { callback, intervalMs, runOnVisible = true, runImmediately = true }) {
  _ensureInitialized()

  if (_pollers.has(name)) {
    unregisterPoller(name)
  }

  const poller = {
    name,
    callback,
    intervalMs,
    runOnVisible,
    intervalId: null,
  }

  _pollers.set(name, poller)

  if (!document.hidden) {
    if (runImmediately && callback) {
      try {
        callback()
      } catch (_e) {}
    }
    _startPoller(poller)
  }
}

export function unregisterPoller(name) {
  const poller = _pollers.get(name)
  if (poller) {
    _stopPoller(poller)
    _pollers.delete(name)
  }
}

export function isPageVisible() {
  return !document.hidden
}

export function onVisibilityChange(callback) {
  const handler = () => callback(!document.hidden)
  document.addEventListener("visibilitychange", handler)
  return () => document.removeEventListener("visibilitychange", handler)
}

export function triggerPoller(name) {
  const poller = _pollers.get(name)
  if (poller?.callback) {
    try {
      poller.callback()
    } catch (_e) {}
  }
}
