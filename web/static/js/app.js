import { closeAuthModal, connectAuth, initAuth } from "./modules/auth.js"
import {
  _onTogglePlaylist as cacheAdminTogglePlaylist,
  cacheBulkDeleteSearch,
  cacheBulkDeleteTags,
  cacheClearPlaylistAll,
  cacheClearSearchAll,
  cacheClearSearchNotfound,
  cacheClearTagsAll,
  cacheRemovePlaylistEntry,
  cacheRemovePlaylistTrack,
  initCacheAdmin,
  reloadCacheAdmin,
  showCacheAdminModal,
} from "./modules/cacheAdmin.js"
import {
  blacklistFromPlaylist,
  clearPreviewCache,
  confirmDeletePlaylist,
  deleteCustomPlaylist,
  editCustomPlaylist,
  initCustomPlaylists,
  loadPlaylistsData,
  saveCustomPlaylist,
  showCustomPlaylistModal,
  togglePlaylistPreview,
  unblacklistFromPlaylist,
} from "./modules/customPlaylists.js"
import {
  cancelCustomThemeModal,
  exportCustomTheme,
  onCustomThemeImportChange,
  resetCustomTheme,
  saveCustomThemeFromModal,
  showCustomThemeModal,
  triggerImportCustomTheme,
} from "./modules/customTheme.js"
import { initDelegation } from "./modules/delegation.js"
import { initEvents, onEvent } from "./modules/events.js"
import { filterCache, filterNotFound, filterTags, filterTracks, goToFilter, initFilters } from "./modules/filters.js"
import {
  clearHistory,
  confirmClearHistory,
  confirmHistoryImportMerge,
  confirmHistoryImportReplace,
  historyBackfill,
  historyExport,
  historyVacuum,
  initHistory,
  loadHistoryData,
  showHistoryDataModal,
  switchHistoryView,
} from "./modules/history.js"
import {
  clearCacheEntry,
  clearTagCacheEntry,
  closeModal,
  confirmImport,
  detailBlacklist,
  detailOverride,
  exportData,
  initModals,
  removeTagOverride,
  showAddBlacklistModal,
  showAddOverrideModal,
  showBlacklistModal,
  showExportImportModal,
  showHistorySyncModal,
  showModal,
  showOverrideModal,
  showTagOverrideModal,
  showTrackDetailModal,
  unblacklistTrack,
} from "./modules/modals.js"
import { initNotifications } from "./modules/notifications.js"
import { deleteYtmPlaylist, discoverPlaylists, loadTrackedPlaylists, pruneWeeklies, trackSelectedPlaylists } from "./modules/playlists.js"
import {
  closeSettingsModal,
  dismissReloadBanner,
  dismissRestartBanner,
  initSettings,
  loadSettings,
  restartServer,
  saveSettings,
  showSettingsModal,
  testWebhook,
} from "./modules/settings.js"
import {
  checkFailureLog,
  closeSetupWizard,
  dismissAndCloseFailureModal,
  dismissAuthBanner,
  dismissSyncFailureBanner,
  initSetup,
  onAuthModalClose,
  openAuthFromSetup,
  setupNextStep,
  setupPrevStep,
  showFailureLogModal,
  showSetupWizard,
} from "./modules/setup.js"
import {
  closeSyncDrawer,
  dismissDataUpdateBanner,
  goToSyncAndRun,
  initSyncDrawerResize,
  openSyncDrawer,
  reattachRunningSync,
  runSync,
  runSyncDefault,
  runSyncTags,
  startDataWatcher,
  stopSync,
  toggleRunMenu,
  toggleSyncDrawer,
} from "./modules/sync.js"
import { initTabs, switchTab } from "./modules/tabs.js"
import { initTagInput } from "./modules/tagInput.js"
import {
  clearTeleporterFile,
  initTeleporter,
  showTeleporterModal,
  teleporterExport,
  teleporterImport,
  teleporterPreview,
  toggleTeleporterPassword,
} from "./modules/teleporter.js"
import { initTooltips } from "./modules/tooltips.js"
import {
  hideNowPlaying,
  initNowPlaying,
  initNowPlayingScrollHide,
  refreshStats,
  restartNowPlaying,
  showToast,
  updateAutoSyncIndicator,
  updateLastSyncDisplay,
  updateSystemClock,
} from "./modules/utils.js"
import { registerPoller } from "./modules/visibility.js"

window.switchTab = switchTab
window.goToFilter = goToFilter

window.filterTracks = filterTracks
window.filterNotFound = filterNotFound
window.filterCache = filterCache
window.filterTags = filterTags

window.showModal = showModal
window.closeModal = closeModal
window.showBlacklistModal = showBlacklistModal
window.showOverrideModal = showOverrideModal
window.showAddOverrideModal = showAddOverrideModal
window.showAddBlacklistModal = showAddBlacklistModal
window.unblacklistTrack = unblacklistTrack
window.clearCacheEntry = clearCacheEntry
window.showTagOverrideModal = showTagOverrideModal
window.removeTagOverride = removeTagOverride
window.clearTagCacheEntry = clearTagCacheEntry

window.showExportImportModal = showExportImportModal
window.exportData = exportData
window.confirmImport = confirmImport
window.showHistorySyncModal = showHistorySyncModal
window.showTrackDetailModal = showTrackDetailModal
window.detailOverride = detailOverride
window.detailBlacklist = detailBlacklist

window.showTeleporterModal = showTeleporterModal
window.teleporterExport = teleporterExport
window.teleporterPreview = teleporterPreview
window.teleporterImport = teleporterImport
window.clearTeleporterFile = clearTeleporterFile
window.toggleTeleporterPassword = toggleTeleporterPassword

window.toggleSyncDrawer = toggleSyncDrawer
window.openSyncDrawer = openSyncDrawer
window.closeSyncDrawer = closeSyncDrawer
window.runSync = runSync
window.toggleRunMenu = toggleRunMenu
window.runSyncDefault = runSyncDefault
window.runSyncTags = runSyncTags
window.stopSync = stopSync
window.goToSyncAndRun = goToSyncAndRun

window.connectAuth = connectAuth
window.closeAuthModal = () => {
  closeAuthModal()
  onAuthModalClose()
}

window.loadSettings = loadSettings
window.saveSettings = saveSettings
window.showSettingsModal = showSettingsModal
window.closeSettingsModal = closeSettingsModal

window.showSetupWizard = showSetupWizard
window.setupNextStep = setupNextStep
window.setupPrevStep = setupPrevStep
window.closeSetupWizard = closeSetupWizard
window.openAuthFromSetup = openAuthFromSetup
window.dismissAuthBanner = dismissAuthBanner
window.showFailureLogModal = showFailureLogModal
window.dismissSyncFailureBanner = dismissSyncFailureBanner
window.dismissAndCloseFailureModal = dismissAndCloseFailureModal
window.checkFailureLog = checkFailureLog

window.dismissRestartBanner = dismissRestartBanner
window.dismissReloadBanner = dismissReloadBanner
window.restartServer = restartServer
window.testWebhook = testWebhook

window.showCustomThemeModal = showCustomThemeModal
window.cancelCustomThemeModal = cancelCustomThemeModal
window.saveCustomThemeFromModal = saveCustomThemeFromModal
window.resetCustomTheme = resetCustomTheme
window.exportCustomTheme = exportCustomTheme
window.triggerImportCustomTheme = triggerImportCustomTheme
window.onCustomThemeImportChange = onCustomThemeImportChange

window.showCustomPlaylistModal = showCustomPlaylistModal
window.editCustomPlaylist = editCustomPlaylist
window.deleteCustomPlaylist = deleteCustomPlaylist
window.confirmDeletePlaylist = confirmDeletePlaylist
window.saveCustomPlaylist = saveCustomPlaylist
window.togglePlaylistPreview = togglePlaylistPreview
window.blacklistFromPlaylist = blacklistFromPlaylist
window.unblacklistFromPlaylist = unblacklistFromPlaylist
window.loadPlaylistsData = loadPlaylistsData
window.clearPreviewCache = clearPreviewCache

window.showToast = showToast
window.refreshStats = refreshStats
window.updateAutoSyncIndicator = updateAutoSyncIndicator
window.restartNowPlaying = restartNowPlaying
window.hideNowPlaying = hideNowPlaying

window.historyBackfill = historyBackfill
window.historyVacuum = historyVacuum
window.historyExport = historyExport
window.showHistoryDataModal = showHistoryDataModal
window.clearHistory = clearHistory
window.confirmClearHistory = confirmClearHistory
window.confirmHistoryImportMerge = confirmHistoryImportMerge
window.confirmHistoryImportReplace = confirmHistoryImportReplace
window.loadHistoryData = loadHistoryData
window.switchHistoryView = switchHistoryView

window.showCacheAdminModal = showCacheAdminModal
window.reloadCacheAdmin = reloadCacheAdmin
window.cacheClearSearchAll = cacheClearSearchAll
window.cacheClearSearchNotfound = cacheClearSearchNotfound
window.cacheBulkDeleteSearch = cacheBulkDeleteSearch
window.cacheClearTagsAll = cacheClearTagsAll
window.cacheBulkDeleteTags = cacheBulkDeleteTags
window.cacheClearPlaylistAll = cacheClearPlaylistAll
window.cacheRemovePlaylistEntry = cacheRemovePlaylistEntry
window.cacheRemovePlaylistTrack = cacheRemovePlaylistTrack
window.cacheAdminTogglePlaylist = cacheAdminTogglePlaylist
window.discoverPlaylists = discoverPlaylists
window.loadTrackedPlaylists = loadTrackedPlaylists
window.trackSelectedPlaylists = trackSelectedPlaylists
window.deleteYtmPlaylist = deleteYtmPlaylist
window.pruneWeeklies = pruneWeeklies
initDelegation()

document.addEventListener("DOMContentLoaded", () => {
  registerPoller("systemClock", {
    callback: updateSystemClock,
    intervalMs: 1000,
  })

  onEvent("stats_changed", () => {
    updateLastSyncDisplay()
    if (window.refreshStats) window.refreshStats()
  })
  onEvent("scheduler_changed", () => {
    updateAutoSyncIndicator()
  })
  updateLastSyncDisplay()
  updateAutoSyncIndicator()
  initEvents()

  initNowPlaying()
  initNowPlayingScrollHide()
  initTabs()
  initFilters()
  initModals(window.closeAuthModal)
  initSyncDrawerResize()
  reattachRunningSync()
  initTeleporter()

  const enhancedSwitchTab = initSettings(switchTab)
  window.switchTab = enhancedSwitchTab

  initAuth()
  initSetup()
  initTooltips()
  initNotifications()
  startDataWatcher()
  loadPlaylistsData()
  initCustomPlaylists()
  initHistory()
  initCacheAdmin()

  initTagInput("tag-override-tags")
  initTagInput("add-tag-override-tags")
  initTagInput("custompl-tags")
})

window.dismissDataUpdateBanner = dismissDataUpdateBanner
