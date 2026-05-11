# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [1.1.3](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.1.2...v1.1.3) (2026-05-11)


### Refactor

* remove outdated update pill component ([c24931d](https://github.com/Locko2901/lastfm-to-ytm/commit/c24931ddfbd4d6155904b773efb7dbb00a6e332d))


### Documentation

* add roadmap ([32d949a](https://github.com/Locko2901/lastfm-to-ytm/commit/32d949a71a7198ead23430138f25bcb88e1a919f))
* update outdated ([5f150ac](https://github.com/Locko2901/lastfm-to-ytm/commit/5f150ac23e61de041e1f326a012fc31e4599b174))


### CI/CD

* merge lint and release-please into single ci workflow ([400353c](https://github.com/Locko2901/lastfm-to-ytm/commit/400353cad17455cdb176821729d53eef756aaec4))
* remove leftover release-please workflow file ([6bf75f5](https://github.com/Locko2901/lastfm-to-ytm/commit/6bf75f541d0f13cf91ec3b38829fe80395e08eb6))

## [1.1.2](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.1.1...v1.1.2) (2026-04-30)


### CI/CD

* set GH_REPO so release notes patch step works without checkout ([b9865fb](https://github.com/Locko2901/lastfm-to-ytm/commit/b9865fbf747efa05a4ba2891e921632ab30f9f1e))

## [1.1.1](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.1.0...v1.1.1) (2026-04-30)


### CI/CD

* **release-please:** append update guide link to GitHub release body ([e495624](https://github.com/Locko2901/lastfm-to-ytm/commit/e495624c681429a03902ee4668b5671d77c36ee7))

## [1.1.0](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.0.1...v1.1.0) (2026-04-30)


### Features

* **web:** replace commits-behind pill with version pill tied to releases ([ad4a8b2](https://github.com/Locko2901/lastfm-to-ytm/commit/ad4a8b2b2baf446a43bd9f0297f18987916fc3b1))


### Documentation

* add CONTRIBUTING and release-please documentation ([adbb4fe](https://github.com/Locko2901/lastfm-to-ytm/commit/adbb4fe13fa8a0d4fff976579dd0308ab50a152b))
* clarify that all conventional commits trigger releases ([a35f093](https://github.com/Locko2901/lastfm-to-ytm/commit/a35f093d36cf67f6bd75abbf67137bb02c0fef34))


### Styling

* tweak CONTRIBUTING intro ([bddb2a5](https://github.com/Locko2901/lastfm-to-ytm/commit/bddb2a521c4748952d928d478fa42d2346a74651))


### Miscellaneous

* I hate em dashes ([9c1ea18](https://github.com/Locko2901/lastfm-to-ytm/commit/9c1ea18028265371b36293ee8b5591e35c48e4c6))

## [1.0.1](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.0.0...v1.0.1) (2026-04-30)


### Bug Fixes

* verify release-please pipeline ([3b9df66](https://github.com/Locko2901/lastfm-to-ytm/commit/3b9df66ad5944cf73e400b860e8c8283525b2a60))


### Miscellaneous

* align pyproject version with v1.0.0 tag ([cd0ba93](https://github.com/Locko2901/lastfm-to-ytm/commit/cd0ba9379ec991ed53043018fe7fd299abcde0d0))

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
