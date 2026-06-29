const actionHandlers = {
  hideNowPlaying: () => window.hideNowPlaying(),
  showSettingsModal: () => window.showSettingsModal(),
  closeSettingsModal: () => window.closeSettingsModal(),
  goToSyncAndRun: () => window.goToSyncAndRun(),
  toggleSyncDrawer: () => window.toggleSyncDrawer(),
  toggleRunMenu: () => window.toggleRunMenu(),
  runSyncDefault: () => window.runSyncDefault(),
  runSyncTags: () => window.runSyncTags(),
  stopSync: () => window.stopSync(),
  showAddBlacklistModal: () => window.showAddBlacklistModal(),
  showAddBlacklistArtistModal: () => window.showAddBlacklistArtistModal(),
  showAddOverrideModal: () => window.showAddOverrideModal(),
  showExportImportModal: () => window.showExportImportModal(),
  showTeleporterModal: () => window.showTeleporterModal(),
  teleporterExport: () => window.teleporterExport(),
  teleporterPreview: () => window.teleporterPreview(),
  teleporterImport: () => window.teleporterImport(),
  clearTeleporterFile: () => window.clearTeleporterFile(),
  toggleTeleporterPassword: el => window.toggleTeleporterPassword(el.dataset.target),
  closeSetupWizard: () => window.closeSetupWizard(),
  openAuthFromSetup: () => window.openAuthFromSetup(),
  setupPrevStep: () => window.setupPrevStep(),
  setupNextStep: () => window.setupNextStep(),
  closeAuthModal: () => window.closeAuthModal(),
  connectAuth: () => window.connectAuth(),
  openSyncDrawer: () => window.openSyncDrawer(),
  historyBackfill: () => window.historyBackfill(),
  historyVacuum: () => window.historyVacuum(),
  historyExport: () => window.historyExport(),
  showHistoryDataModal: () => window.showHistoryDataModal(),
  clearHistory: () => window.clearHistory(),
  confirmClearHistory: () => window.confirmClearHistory(),
  confirmHistoryImportMerge: () => window.confirmHistoryImportMerge(),
  confirmHistoryImportReplace: () => window.confirmHistoryImportReplace(),
  restartServer: () => window.restartServer(),
  dismissRestartBanner: () => window.dismissRestartBanner(),
  dismissReloadBanner: () => window.dismissReloadBanner(),
  testWebhook: () => window.testWebhook(),
  dismissAuthBanner: () => window.dismissAuthBanner(),
  showFailureLogModal: () => window.showFailureLogModal(),
  dismissSyncFailureBanner: () => window.dismissSyncFailureBanner(),
  dismissAndCloseFailureModal: () => window.dismissAndCloseFailureModal(),
  reloadPage: () => window.location.reload(),
  dismissDataUpdateBanner: () => window.dismissDataUpdateBanner(),
  switchHistoryView: el => window.switchHistoryView(el.dataset.historyViewTab || "tracks", el.dataset.historyViewFilter || "all"),

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
  showBlacklistArtistModal: el => {
    const { artist, tab } = el.dataset
    window.showBlacklistArtistModal(artist, tab)
  },
  unblacklistTrack: el => {
    const { artist, title, tab } = el.dataset
    window.unblacklistTrack(artist, title, el, tab)
  },
  clearCacheEntry: el => {
    const { artist, title, tab } = el.dataset
    window.clearCacheEntry(artist, title, el, tab)
  },
  showTagOverrideModal: el => {
    const { artist, title, tab, tags } = el.dataset
    const lastfmTags = el.dataset.lastfmTags || ""
    const hasOverride = el.dataset.hasOverride || ""
    window.showTagOverrideModal(artist, title, tab, tags || "", lastfmTags, hasOverride)
  },
  removeTagOverride: el => {
    const { artist, title, tab } = el.dataset
    window.removeTagOverride(artist, title, tab)
  },
  clearTagCacheEntry: el => {
    const { artist, title, tab } = el.dataset
    window.clearTagCacheEntry(artist, title, el, tab)
  },
  showCustomPlaylistModal: () => window.showCustomPlaylistModal(),
  editCustomPlaylist: el => window.editCustomPlaylist(parseInt(el.dataset.index, 10)),
  deleteCustomPlaylist: el => window.deleteCustomPlaylist(parseInt(el.dataset.index, 10), el.dataset.name),
  confirmDeletePlaylist: () => window.confirmDeletePlaylist(),
  saveCustomPlaylist: () => window.saveCustomPlaylist(),
  togglePlaylistPreview: el => window.togglePlaylistPreview(parseInt(el.dataset.index, 10)),
  blacklistFromPlaylist: el => {
    const { artist, title, plIndex } = el.dataset
    window.blacklistFromPlaylist(parseInt(plIndex, 10), artist, title)
  },
  unblacklistFromPlaylist: el => {
    const { artist, title, plIndex } = el.dataset
    window.unblacklistFromPlaylist(parseInt(plIndex, 10), artist, title)
  },
  blacklistArtistFromPlaylist: el => {
    const { artist, plIndex } = el.dataset
    window.blacklistArtistFromPlaylist(parseInt(plIndex, 10), artist)
  },
  unblacklistArtistFromPlaylist: el => {
    const { artist, plIndex } = el.dataset
    window.unblacklistArtistFromPlaylist(parseInt(plIndex, 10), artist)
  },
  expandTags: el => {
    const container = el.closest(".track-tags")
    if (container) container.classList.toggle("expanded")
  },

  exportData: el => window.exportData(el.dataset.type || "all"),
  confirmImport: () => window.confirmImport(),
  showHistorySyncModal: el => window.showHistorySyncModal(parseInt(el.dataset.syncId, 10)),
  showTrackDetailModal: el => {
    const { artist, title } = el.dataset
    window.showTrackDetailModal(artist, title)
  },
  detailOverride: () => window.detailOverride(),
  detailBlacklist: () => window.detailBlacklist(),

  showCacheAdminModal: () => window.showCacheAdminModal(),
  reloadCacheAdmin: () => window.reloadCacheAdmin(),
  cacheClearSearchAll: () => window.cacheClearSearchAll(),
  cacheClearSearchNotfound: () => window.cacheClearSearchNotfound(),
  cacheBulkDeleteSearch: () => window.cacheBulkDeleteSearch(),
  cacheClearTagsAll: () => window.cacheClearTagsAll(),
  cacheBulkDeleteTags: () => window.cacheBulkDeleteTags(),
  cacheClearPlaylistAll: () => window.cacheClearPlaylistAll(),
  cacheRemovePlaylist: el => window.cacheRemovePlaylistEntry(el.dataset.name),
  cacheRemovePlaylistTrack: el => window.cacheRemovePlaylistTrack(el.dataset.name, el.dataset.videoId),
  cacheAdminTogglePlaylist: el => window.cacheAdminTogglePlaylist(el.dataset.name),

  discoverPlaylists: () => window.discoverPlaylists(),
  trackSelectedPlaylists: () => window.trackSelectedPlaylists(),
  deleteYtmPlaylist: el => window.deleteYtmPlaylist(el.dataset.id, el.dataset.name),
  pruneWeeklies: () => window.pruneWeeklies(),

  showCustomThemeModal: () => window.showCustomThemeModal(),
  cancelCustomThemeModal: () => window.cancelCustomThemeModal(),
  saveCustomThemeFromModal: () => window.saveCustomThemeFromModal(),
  resetCustomTheme: () => window.resetCustomTheme(),
  exportCustomTheme: () => window.exportCustomTheme(),
  triggerImportCustomTheme: () => window.triggerImportCustomTheme(),
}

export function initDelegation() {
  document.addEventListener("click", e => {
    const el = e.target.closest("[data-action]")
    if (!el) return

    if (e.target.closest("a") && e.target.closest("a") !== el) return

    const handler = actionHandlers[el.dataset.action]
    if (!handler) return

    if (el.dataset.stopPropagation != null) {
      e.stopPropagation()
    }

    handler(el)
  })

  document.addEventListener("click", e => {
    if (e.target.closest("a, button, form, input, [data-action]")) return
    const row = e.target.closest(".track-item")
    if (!row) return
    const artist = row.dataset.originalArtist
    const title = row.dataset.originalTitle
    if (artist && title) {
      window.showTrackDetailModal(artist, title)
    }
  })
}
