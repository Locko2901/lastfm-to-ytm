import { closeAuthModal, connectAuth, initAuth } from "./modules/auth.js"
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
import { initDelegation } from "./modules/delegation.js"
import { filterCache, filterNotFound, filterTags, filterTracks, goToFilter, initFilters } from "./modules/filters.js"
import {
  clearCacheEntry,
  clearTagCacheEntry,
  closeModal,
  initModals,
  removeTagOverride,
  showAddBlacklistModal,
  showAddOverrideModal,
  showBlacklistModal,
  showModal,
  showOverrideModal,
  showTagOverrideModal,
  unblacklistTrack,
} from "./modules/modals.js"
import { initNotifications } from "./modules/notifications.js"
import {
  closeSettingsModal,
  dismissRestartBanner,
  initSettings,
  loadSettings,
  restartServer,
  saveSettings,
  showSettingsModal,
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
window.restartServer = restartServer

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

initDelegation()

document.addEventListener("DOMContentLoaded", () => {
  registerPoller("lastSyncDisplay", {
    callback: updateLastSyncDisplay,
    intervalMs: 60000,
  })

  registerPoller("systemClock", {
    callback: updateSystemClock,
    intervalMs: 1000,
  })

  registerPoller("autoSyncIndicator", {
    callback: updateAutoSyncIndicator,
    intervalMs: 60000,
  })

  initNowPlaying()
  initNowPlayingScrollHide()
  initTabs()
  initFilters()
  initModals(window.closeAuthModal)
  initSyncDrawerResize()

  const enhancedSwitchTab = initSettings(switchTab)
  window.switchTab = enhancedSwitchTab

  initAuth()
  initSetup()
  initTooltips()
  initNotifications()
  startDataWatcher()
  loadPlaylistsData()
  initCustomPlaylists()

  initTagInput("tag-override-tags")
  initTagInput("add-tag-override-tags")
  initTagInput("custompl-tags")
})

window.dismissDataUpdateBanner = dismissDataUpdateBanner
