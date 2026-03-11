const actionHandlers = {
  hideNowPlaying: () => window.hideNowPlaying(),
  showSettingsModal: () => window.showSettingsModal(),
  closeSettingsModal: () => window.closeSettingsModal(),
  goToSyncAndRun: () => window.goToSyncAndRun(),
  toggleSyncDrawer: () => window.toggleSyncDrawer(),
  runSync: () => window.runSync(),
  stopSync: () => window.stopSync(),
  showAddBlacklistModal: () => window.showAddBlacklistModal(),
  showAddOverrideModal: () => window.showAddOverrideModal(),
  closeSetupWizard: () => window.closeSetupWizard(),
  openAuthFromSetup: () => window.openAuthFromSetup(),
  setupPrevStep: () => window.setupPrevStep(),
  setupNextStep: () => window.setupNextStep(),
  closeAuthModal: () => window.closeAuthModal(),
  connectAuth: () => window.connectAuth(),
  openSyncDrawer: () => window.openSyncDrawer(),

  closeModal: el => window.closeModal(el.dataset.modal),
  showModal: el => window.showModal(el.dataset.modal),

  goToFilter: el => window.goToFilter(el.dataset.tab, el.dataset.filter),
  switchTab: el => window.switchTab(el.dataset.tab),

  showOverrideModal: el => {
    const { artist, title, tab, videoId } = el.dataset
    window.showOverrideModal(artist, title, tab, videoId || undefined)
  },
  showBlacklistModal: el => {
    const { artist, title, tab } = el.dataset
    window.showBlacklistModal(artist, title, tab)
  },
  unblacklistTrack: el => {
    const { artist, title, tab } = el.dataset
    window.unblacklistTrack(artist, title, el, tab)
  },
  clearCacheEntry: el => {
    const { artist, title, tab } = el.dataset
    window.clearCacheEntry(artist, title, el, tab)
  },
}

export function initDelegation() {
  document.addEventListener("click", e => {
    const el = e.target.closest("[data-action]")
    if (!el) return

    const handler = actionHandlers[el.dataset.action]
    if (!handler) return

    if (el.dataset.stopPropagation != null) {
      e.stopPropagation()
    }

    handler(el)
  })
}
