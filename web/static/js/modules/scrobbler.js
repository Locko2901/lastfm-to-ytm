import { confirmDialog } from "./confirm.js"
import { onEvent } from "./events.js"
import { _ } from "./i18n.js"
import { escapeHtml, fetchJson, formatDateTime, getDateTimePrefs, setPagination, setText, showToast } from "./utils.js"

const PAGE_SIZE = 50
const AUTH_POLL_MS = 3000
const AUTH_POLL_MAX = 100

let currentFilter = ""
let currentPage = 0
let dryRun = true
let authPollTimer = null

function statusLabel(status) {
  const labels = {
    scrobbled: _("Scrobbled"),
    would_scrobble: _("Would scrobble"),
    skipped: _("Skipped"),
    pending: _("Waiting"),
    sending: _("Sending"),
    failed: _("Failed"),
  }
  return labels[status] || status
}

function reasonText(play, prefs) {
  const reasons = {
    too_short: _("30 seconds or shorter, which Last.fm does not count"),
    unknown_duration: _("The history gives no track length, so Last.fm's threshold cannot be checked"),
    too_old: _("Older than Last.fm accepts (14 days)"),
    not_music: _("Not music (podcast episode)"),
    no_artist: _("No artist or title in the history"),
    unknown_artist: _("Not a song with a known artist: a user upload whose title does not name one"),
    recovered: _("Found on Last.fm after a request that got no answer"),
    too_many_scrobbles: _("Too many scrobbles around its uncertain time to check for duplicates"),
  }
  const detail = play.detail || {}
  if (play.reason === "duplicate" && detail.duplicate_of) {
    const d = detail.duplicate_of
    const what = `${d.artist} - ${d.track}`
    if (d.now_playing) return _("Already playing on Last.fm: %(track)s", { track: what })
    return _("Already scrobbled: %(track)s, %(minutes)s min apart", { track: what, minutes: Math.round(d.distance / 60) })
  }
  if (play.reason === "realtime_active" && detail.realtime) {
    return _("Left to the real-time scrobbler: it was active around this play (%(from)s to %(to)s)", {
      from: formatDateTime(new Date(detail.realtime.from * 1000), prefs),
      to: formatDateTime(new Date(detail.realtime.to * 1000), prefs),
    })
  }
  if (play.reason === "ignored_by_lastfm" && detail.ignored) {
    return _("Ignored by Last.fm: %(message)s (code %(code)s)", { message: detail.ignored.message || "", code: detail.ignored.code })
  }
  if (play.reason === "listened_too_little") {
    const needed = formatSeconds(play.listen_threshold)
    if (play.basis === "end_unknown") return _("Not counted: the end-unknown model skips plays whose end the history does not show")
    if (play.basis === "timing_unknown") return _("Not counted: the timing model skips plays whose timing is unknown")
    if (play.certainty === "certain")
      return _("Listened at most %(hi)s, less than the %(needed)s Last.fm needs", { hi: formatSeconds(play.listen_hi), needed })
    return _("The bounds leave it open; the tie-break says it stayed under the %(needed)s Last.fm needs", { needed })
  }
  if (play.status === "failed") return _("Last.fm refused it: %(error)s", { error: detail.error || "" })
  if (play.status === "pending" && play.next_window_end == null) {
    return _("Still the newest play: decided once it has been on top long enough, or when the next play appears")
  }
  if (play.status === "pending") return _("Decided a minute after the next play appeared, so real-time scrobblers can act first")
  if (play.status === "sending") return _("Sent, waiting to confirm Last.fm received it")
  return reasons[play.reason] || ""
}

function dryRunChoiceText(play) {
  if (play.dry_run_choice === "send" && play.status === "pending") {
    return _("From the dry run: you chose to send it; the next poll checks it for duplicates, then sends it")
  }
  if (play.dry_run_choice === "send") return _("From the dry run: you chose to send it when the dry run ended")
  if (play.dry_run_choice === "keep") return _("From the dry run: you chose not to send it when the dry run ended")
  if (play.dry_run_choice === "too_old") return _("From the dry run: too old for Last.fm when the dry run ended, not sent")
  return ""
}

function nearMissText(detail) {
  const near = detail?.near_miss
  if (!near) return ""
  const what = `${near.artist} - ${near.track}`
  if (near.reason === "version_differs") return _("Near miss, another version: %(track)s", { track: what })
  return _("Near miss, other artist: %(track)s", { track: what })
}

function formatSeconds(seconds) {
  const total = Math.max(0, Math.round(seconds || 0))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`
}

function basisText(play) {
  if (play.basis === "end_unknown") {
    return _("End unknown: listening stopped or paused at a time the polls do not show, so the end-unknown model decided")
  }
  if (play.basis === "timing_unknown") {
    return _("Timing unknown: found in a burst of new plays (offline plays sync late) or after a long gap between polls, so the timing model decided")
  }
  return ""
}

function listeningText(play) {
  if (play.basis === "end_unknown" || play.basis === "timing_unknown") return basisText(play)
  if (play.listen_lo == null || play.listen_hi == null || play.listen_threshold == null) return ""
  return _("Listened between %(lo)s and %(hi)s of %(length)s; Last.fm needs %(needed)s", {
    lo: formatSeconds(play.listen_lo),
    hi: formatSeconds(play.listen_hi),
    length: formatSeconds(play.duration),
    needed: formatSeconds(play.listen_threshold),
  })
}

function tiebreakText(play) {
  const estimate = play.detail?.played?.estimate
  if (play.certainty !== "estimated" || estimate == null) return ""
  return _("Tie-break: %(chance)s percent chance it reached the threshold", { chance: Math.round(estimate * 100) })
}

function certaintyBadge(play) {
  if (play.certainty === "certain") return `<span class="badge badge-muted">${_("certain")}</span>`
  if (play.certainty === "estimated") return `<span class="badge badge-warning">${_("estimated")}</span>`
  return ""
}

function formatUncertainty(seconds) {
  if (seconds == null) return ""
  if (seconds < 90) return _("±%(n)s s", { n: Math.round(seconds) })
  if (seconds < 5400) return _("±%(n)s min", { n: Math.round(seconds / 60) })
  return _("±%(n)s h", { n: Math.round(seconds / 3600) })
}

const STATUS_BADGES = {
  scrobbled: "badge-success",
  would_scrobble: "badge-success",
  skipped: "badge-muted",
  pending: "badge-warning",
  sending: "badge-warning",
  failed: "badge-danger",
}

function badgeClass(status) {
  return `badge ${STATUS_BADGES[status] || "badge-muted"}`
}

function renderBanner(status) {
  const banner = document.getElementById("scrobblerBanner")
  if (!banner) return
  const messages = []
  if (!status.enabled) messages.push(_("The history scrobbler is disabled. Enable it in Settings, Automation."))
  if (status.enabled && !status.dry_run && !status.connected) {
    messages.push(_("Live mode needs Last.fm write access: connect Last.fm in Settings, Automation."))
  }
  if (status.account_mismatch) {
    messages.push(
      _("The Last.fm session belongs to %(session)s, not %(user)s. Reconnect with the right account.", {
        session: status.session_user,
        user: status.lastfm_user,
      }),
    )
  }
  if (status.youtube_session_expired) {
    messages.push(_("YouTube Music session expired: reconnect it from the banner at the top, or in Settings, General."))
  } else if (status.last_poll?.error) {
    messages.push(status.last_poll.error)
  }
  banner.hidden = messages.length === 0
  banner.innerHTML = messages.map(m => `<p>${escapeHtml(m)}</p>`).join("")
}

function paceText(status) {
  if (!status.enabled || !status.pace_seconds) return ""
  const minutes = Math.round(status.pace_seconds / 60)
  if (status.pace === "fast") return _("Every %(minutes)s min while the history changes", { minutes })
  if (status.pace === "idle") return _("Every %(minutes)s min, the history is quiet", { minutes })
  return _("Every %(minutes)s min after failed reads", { minutes })
}

async function renderStatus(status) {
  const prefs = await getDateTimePrefs()
  const counts = status.counts || {}
  dryRun = status.dry_run !== false
  setText("scrobblerMode", status.dry_run ? _("Dry run") : _("Live"))
  setText("scrobblerLastPoll", status.last_poll?.finished_at ? formatDateTime(new Date(status.last_poll.finished_at * 1000), prefs) : null)
  setText("scrobblerNextPoll", status.next_poll ? formatDateTime(new Date(status.next_poll), prefs) : null)
  setText("scrobblerPace", paceText(status))
  setText("scrobblerDone", (counts.scrobbled || 0) + (counts.would_scrobble || 0))
  setText("scrobblerSkipped", counts.skipped ?? 0)
  setText("scrobblerOpen", (counts.pending || 0) + (counts.sending || 0))
  setText("scrobblerFailed", counts.failed ?? 0)
  setText("scrobblerDoneLabel", status.dry_run ? _("Would scrobble (24h)") : _("Scrobbled (24h)"))
  setText("scrobblerDoneChip", status.dry_run ? _("Would scrobble") : _("Scrobbled"))
  const pollBtn = document.getElementById("scrobblerPollBtn")
  if (pollBtn) pollBtn.disabled = !status.enabled || status.polling
  renderBanner(status)
}

function renderPlay(play, prefs) {
  const when = formatDateTime(new Date(play.timestamp * 1000), prefs)
  const uncertainty = formatUncertainty(play.detail?.uncertainty ?? Math.max(play.timestamp - play.earliest, play.latest - play.timestamp))
  const reason = reasonText(play, prefs)
  const listening = listeningText(play)
  const tiebreak = tiebreakText(play)
  const near = nearMissText(play.detail)
  const fromDryRun = dryRunChoiceText(play)
  const replay = play.replay ? `<span class="badge badge-muted">${_("played again")}</span>` : ""
  const corrected =
    play.status === "scrobbled" && play.lastfm_title && (play.lastfm_title !== play.title || play.lastfm_artist !== play.artist)
      ? `<span class="scrobbler-note">${escapeHtml(_("Last.fm corrected it to %(track)s", { track: `${play.lastfm_artist} - ${play.lastfm_title}` }))}</span>`
      : ""
  const link = `https://music.youtube.com/watch?v=${encodeURIComponent(play.video_id)}`
  return `
    <div class="track-item scrobbler-play scrobbler-play-${escapeHtml(play.status)}">
      <div class="track-info">
        <span class="track-artist">${escapeHtml(play.artist)}</span>
        <span class="track-ytm"><a href="${link}" target="_blank" rel="noopener noreferrer">${escapeHtml(play.title)}</a></span>
      </div>
      <div class="scrobbler-play-when">
        <span>${escapeHtml(when)}</span>
        <span class="text-muted">${escapeHtml(uncertainty)}</span>
      </div>
      <div class="scrobbler-play-decision">
        <span><span class="${badgeClass(play.status)}">${escapeHtml(statusLabel(play.status))}</span> ${certaintyBadge(play)} ${replay}</span>
        ${reason ? `<span class="scrobbler-reason">${escapeHtml(reason)}</span>` : ""}
        ${listening ? `<span class="scrobbler-note">${escapeHtml(listening)}</span>` : ""}
        ${tiebreak ? `<span class="scrobbler-note">${escapeHtml(tiebreak)}</span>` : ""}
        ${near ? `<span class="scrobbler-note">${escapeHtml(near)}</span>` : ""}
        ${fromDryRun ? `<span class="scrobbler-note">${escapeHtml(fromDryRun)}</span>` : ""}
        ${corrected}
      </div>
    </div>`
}

function emptyText(filter) {
  if (filter === "done") return dryRun ? _("No play recorded as would scrobble yet.") : _("No play scrobbled yet.")
  if (filter === "skipped") return _("No skipped plays.")
  if (filter === "open") return _("No plays waiting for a decision.")
  if (filter === "failed") return _("No failed plays.")
  return _("No plays recorded yet. The first two polls only save a snapshot of the history; a new play shows up once the next poll confirms it.")
}

async function loadScrobblerPlays() {
  const list = document.getElementById("scrobblerPlays")
  if (!list) return
  const params = new URLSearchParams({ limit: PAGE_SIZE, offset: currentPage * PAGE_SIZE })
  if (currentFilter) params.set("status", currentFilter)
  try {
    const data = await fetchJson(`/api/scrobbler/plays?${params}`)
    const prefs = await getDateTimePrefs()
    if (!data.plays.length) {
      list.innerHTML = `<div class="empty-state"><p class="text-muted">${escapeHtml(emptyText(currentFilter))}</p></div>`
    } else {
      list.innerHTML = data.plays.map(p => renderPlay(p, prefs)).join("")
    }
    setPagination("scrobblerPagination", data.total, currentPage, PAGE_SIZE, page => {
      currentPage = page
      loadScrobblerPlays()
    })
  } catch (_e) {
    list.innerHTML = `<div class="empty-state"><p class="text-muted">${_("Failed to load the scrobbler decisions")}</p></div>`
  }
}

export async function loadScrobblerData() {
  try {
    const status = await fetchJson("/api/scrobbler/status")
    await renderStatus(status)
    renderAuthStatus(status)
  } catch (_e) {}
  await loadScrobblerPlays()
}

export async function scrobblerPollNow() {
  const btn = document.getElementById("scrobblerPollBtn")
  if (btn) btn.disabled = true
  try {
    const data = await fetchJson("/api/scrobbler/poll", { method: "POST" })
    if (data.error) showToast(data.error, "warning")
    else showToast(_("Poll done: %(count)s new play(s)", { count: data.new_plays }), "success")
  } catch (e) {
    showToast(e.message || _("Poll failed"), "error")
  } finally {
    await loadScrobblerData()
  }
}

export async function offerDryRunPlays() {
  let offer
  try {
    offer = await fetchJson("/api/scrobbler/dry-run-plays")
  } catch (_e) {
    return
  }
  if (!offer.eligible) return
  const recorded = _("The dry run recorded %(count)s play(s) as would scrobble that Last.fm still accepts.", { count: offer.eligible })
  const older = offer.too_old ? _("%(count)s older one(s) would be refused and stay unsent.", { count: offer.too_old }) : ""
  const checked = _("Each one is checked against your recent scrobbles again before it is sent, like any other play.")
  const send = await confirmDialog({
    title: _("Also send the plays from the dry run?"),
    message: [recorded, older, checked].filter(Boolean).join(" "),
    confirmLabel: _("Send them"),
    cancelLabel: _("Don't send"),
    danger: false,
    focusCancel: true,
  })
  try {
    const data = await fetchJson("/api/scrobbler/dry-run-plays", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ send }),
    })
    if (send) showToast(_("%(count)s play(s) from the dry run will be checked and sent with the next poll.", { count: data.queued }), "success")
    else showToast(_("The plays from the dry run stay unsent."), "info")
  } catch (e) {
    showToast(e.message, "error")
  }
  if (document.getElementById("panel-scrobbler")?.classList.contains("active")) loadScrobblerData()
}

export async function scrobblerReset() {
  const forget = _("This forgets the history snapshot and every recorded decision, including the ledger of plays already scrobbled.")
  const after = _("The next poll takes a new snapshot and detects nothing. Scrobbles on Last.fm are not touched.")
  const ok = await confirmDialog({
    title: _("Start over?"),
    message: `${forget} ${after}`,
    confirmLabel: _("Start over"),
  })
  if (!ok) return
  try {
    await fetchJson("/api/scrobbler/reset", { method: "POST" })
  } catch (e) {
    showToast(_("Could not reset the scrobbler: %(error)s", { error: e.message }), "error")
    return
  }
  showToast(_("Scrobbler reset. The next poll takes a new snapshot."), "success")
  currentPage = 0
  await loadScrobblerData()
}

function renderAuthStatus(status) {
  for (const el of document.querySelectorAll("[data-scrobbler-auth-status]")) {
    const text = el.querySelector(".auth-status-text")
    el.classList.remove("checking", "valid", "invalid", "missing")
    let label
    if (status.connected && !status.account_mismatch) {
      el.classList.add("valid")
      label = _("Connected as %(user)s", { user: status.session_user || status.lastfm_user })
    } else if (status.account_mismatch) {
      el.classList.add("invalid")
      label = _("Connected as %(user)s, which is not your Last.fm username", { user: status.session_user })
    } else {
      el.classList.add("missing")
      label = status.has_secret ? _("Not connected") : _("Not connected: the API secret is missing")
    }
    if (text) text.textContent = label
  }
  for (const btn of document.querySelectorAll("[data-scrobbler-disconnect]")) {
    btn.hidden = !status.connected
  }
}

export async function refreshScrobblerAuthStatus() {
  try {
    renderAuthStatus(await fetchJson("/api/scrobbler/status"))
  } catch (_e) {}
}

function stopAuthPolling() {
  if (authPollTimer) {
    clearTimeout(authPollTimer)
    authPollTimer = null
  }
}

function showAuthSteps(container, html) {
  const steps = container?.querySelector("[data-scrobbler-auth-steps]")
  if (!steps) return
  steps.hidden = !html
  steps.innerHTML = html || ""
}

export async function scrobblerConnect(el) {
  const container = el.closest(".scrobbler-auth")
  const input = el.dataset.secretInput ? document.getElementById(el.dataset.secretInput) : null
  const secret = input?.value?.trim() || ""
  stopAuthPolling()
  el.disabled = true
  try {
    const data = await fetchJson("/api/scrobbler/auth/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_secret: secret }),
    })
    refreshScrobblerAuthStatus()
    showAuthSteps(
      container,
      `<ol>
        <li>${escapeHtml(_("Open Last.fm and allow access for this app:"))} <a href="${escapeHtml(data.auth_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(_("Approve on Last.fm"))}</a></li>
        <li>${escapeHtml(_("Come back here: the connection completes by itself once you approved."))}</li>
      </ol>`,
    )
    waitForApproval(container, data.token, 0)
  } catch (e) {
    showToast(e.message, "error")
    showAuthSteps(container, "")
  } finally {
    el.disabled = false
  }
}

function waitForApproval(container, token, attempt) {
  if (attempt >= AUTH_POLL_MAX) {
    showAuthSteps(container, `<p class="text-muted">${escapeHtml(_("No approval received. Click Connect Last.fm to try again."))}</p>`)
    return
  }
  authPollTimer = setTimeout(async () => {
    try {
      const { status, data } = await fetchJson(
        "/api/scrobbler/auth/finish",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        },
        { withStatus: true },
      )
      if (status === 202) {
        waitForApproval(container, token, attempt + 1)
        return
      }
      showAuthSteps(container, "")
      showToast(_("Connected to Last.fm as %(user)s", { user: data.user }), "success")
      await refreshScrobblerAuthStatus()
    } catch (e) {
      showAuthSteps(container, "")
      showToast(e.message, "error")
    }
  }, AUTH_POLL_MS)
}

export async function scrobblerDisconnect() {
  const removed = _("The session key is removed from .env and live scrobbling stops.")
  const revoke = _("To revoke the access completely, also remove the app on Last.fm under Settings, Applications.")
  const ok = await confirmDialog({
    title: _("Disconnect Last.fm?"),
    message: `${removed} ${revoke}`,
    confirmLabel: _("Disconnect"),
  })
  if (!ok) return
  try {
    await fetchJson("/api/scrobbler/auth/disconnect", { method: "POST" })
  } catch (e) {
    showToast(_("Could not disconnect: %(error)s", { error: e.message }), "error")
    return
  }
  stopAuthPolling()
  showToast(_("Disconnected from Last.fm"), "success")
  await refreshScrobblerAuthStatus()
}

export function initScrobbler() {
  for (const chip of document.querySelectorAll("[data-scrobbler-filter]")) {
    chip.addEventListener("click", () => {
      for (const c of document.querySelectorAll("[data-scrobbler-filter]")) c.classList.remove("active")
      chip.classList.add("active")
      currentFilter = chip.dataset.scrobblerFilter
      currentPage = 0
      loadScrobblerPlays()
    })
  }
  onEvent("scrobbler_changed", () => {
    if (document.getElementById("panel-scrobbler")?.classList.contains("active")) loadScrobblerData()
  })
  if (document.getElementById("panel-scrobbler")?.classList.contains("active")) loadScrobblerData()
}
