const _translations = window.__i18n__ || {}

export function _(msg, params) {
  let translated = _translations[msg] || msg
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      translated = translated.replaceAll(`%(${key})s`, value)
    }
  }
  return translated
}
