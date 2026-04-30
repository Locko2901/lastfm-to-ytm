# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [1.0.0] - 2026-04-30

### Bug Fixes

- **web**: Hide update pill when not behind & link to hosted docs
- Fix graphs and add more tips + a toggle to disable them
- Fix delegation, custompl panel, and translation updates
- Fix ignored cache dir
- Fix docs
- Fix tablist
- Fix search bar
- Fix linting
- Fixes; features; formatting;
- Improve auth process readiness check and handle completion state
- Reset browser.json instead of unlinking it on start
- Fix first time setup
- Fix scheduler
- Fix csp; fix scheduler; fix project scripts
- Fix _strip_inline_comment
- Fix handling of inline comments in .env
- Set USE_ANON_SEARCH=true by default
- Fix

### Documentation

- **dashboard**: Note pybabel compile step for non-Docker installs
- Migrate README to MkDocs Material documentation site
- Fix typographical errors in README for consistency
- Correct typographical error in project title
- Update README to include known issues and improve clarity in playlist logic

### Features

- **update-pill**: Enhance update pill styling and functionality
- **web**: Reattach to running sync stream on page load
- **web**: Show "N commits behind main" pill in dashboard
- **web**: Add configurable date format (DMY/MDY/auto)
- **web**: Add cache management modal
- Overhaul web dashboard with new panels and PWA support
- Add run history tracking and webhook notifications
- Enhance core sync with privacy levels and playlist descriptions
- Feature/qol fix formatting
- Feature/qol add teleporter and some qol; fix some styling
- Feature/tag-playlists make linters happy
- Feature/tag-playlists make linters happy
- Feature/tag-playlists differentiate between track and artist tags
- Feature/tag-playlists
- Add web dashboard, Docker setup, CI linting, and core fixes
- Log final playlist order after backfills in run function
- **search**: Enhance YouTube Music search with concurrency and logging

### Internationalization

- Refresh message catalog

### Miscellaneous

- Update translations and README
- Update project config and tooling
- Add ruff and enforce linting rules

### Other

- Update docs
- Add missing
- Remove backslash escapes from LaTeX math formula
- Add MathJax support for rendering mathematical expressions
- Add error handling for invalid video IDs during playlist sync
- Commit missing file
- Update docs for tag plylists
- Add docs for tag playlists
- Move i18n logic
- Improve docs
- Update docs
- Always check linting
- Formatting
- Make linters happy
- Add i18n
- Header
- Refactor track action buttons and search functionality across panels

- Introduced a new macro for track actions to reduce code duplication in _panel_cache.html, _panel_notfound.html, and _panel_playlist.html.
- Replaced inline search input implementations with a reusable search_bar macro.
- Updated the auth.js module to streamline authentication status checks and banner management.
- Enhanced modal functionality in modals.js to utilize new utility functions for button loading and form submissions.
- Consolidated banner management functions in utils.js for better reusability.
- Improved settings management in settings.js by removing redundant code and utilizing new utility functions.
- Updated sync.js to utilize new banner management functions for data update notifications.
- Enhance caching and logging: add pruning of old weekly playlists, improve search cache entry handling, and implement run/failure logging
- Improve error handling in cache operations and enhance data class representation
- Enhance .env.example documentation and fix a bug with the playlist song order
- Edit readme
- Remove unnecessary comments
- Add readme
- Add .env.example
- Cleanup
- Create LICENSE
- Improve search
- Unify plylist logic
- Remove comment spam + slightly improved logic
- Better search and qol
- Pre

### Refactor

- Complete project overhaul
- Enhance fetch_recent function to support timestamp filtering and improve scrobble retrieval logic

### Styling

- **playlist**: Update button for removing cached tracks with icon
- **update-pill**: Format HTML for better readability

