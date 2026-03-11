import { closeAuthModal, connectAuth, initAuth } from "./modules/auth.js"
import { initDelegation } from "./modules/delegation.js"
import { filterCache, filterNotFound, filterTracks, goToFilter, initFilters } from "./modules/filters.js"
import {
  clearCacheEntry,
  closeModal,
  initModals,
  showAddBlacklistModal,
  showAddOverrideModal,
  showBlacklistModal,
  showModal,
  showOverrideModal,
  unblacklistTrack,
} from "./modules/modals.js"
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
  startDataWatcher,
  stopSync,
  toggleSyncDrawer,
} from "./modules/sync.js"
import { initTabs, switchTab } from "./modules/tabs.js"
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

window.showModal = showModal
window.closeModal = closeModal
window.showBlacklistModal = showBlacklistModal
window.showOverrideModal = showOverrideModal
window.showAddOverrideModal = showAddOverrideModal
window.showAddBlacklistModal = showAddBlacklistModal
window.unblacklistTrack = unblacklistTrack
window.clearCacheEntry = clearCacheEntry

window.toggleSyncDrawer = toggleSyncDrawer
window.openSyncDrawer = openSyncDrawer
window.closeSyncDrawer = closeSyncDrawer
window.runSync = runSync
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
  startDataWatcher()
})

window.dismissDataUpdateBanner = dismissDataUpdateBanner
