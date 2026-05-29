# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
## [1.6.0](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.5.0...v1.6.0) (2026-05-29)


### Features

* **update:** detect local (unpushed) commits as build_type=local ([d9bbfad](https://github.com/Locko2901/lastfm-to-ytm/commit/d9bbfadc7ad6118342b2e2682249112065e3468e))
* **web:** live dashboard via SSE event bus and persistent notifications ([3c01a56](https://github.com/Locko2901/lastfm-to-ytm/commit/3c01a56eb04d37b33968ef645693ce70d74f02d2))


### Bug Fixes

* **update:** force build_type=local for unpushed SHAs regardless of declared channel ([60cdf3d](https://github.com/Locko2901/lastfm-to-ytm/commit/60cdf3d0ea42aa98ae7ce99b2cbb56b18b60b4f6))
* **web:** normalize checkbox and empty values when diffing settings ([45a0a03](https://github.com/Locko2901/lastfm-to-ytm/commit/45a0a0365c46f0592784d4d808de7f33eb69ea39))
* **web:** refresh .env on settings save and gate /api/restart_server on reloader ([b702d64](https://github.com/Locko2901/lastfm-to-ytm/commit/b702d64a1df45097e59682ca0b3b041a7d0287c3))


### Documentation

* **ci:** link release notes 'updating' section to docker-reference ([bf8a3ea](https://github.com/Locko2901/lastfm-to-ytm/commit/bf8a3ead4143b066172e9737a8c6c01fdf48ab56))
* update readme and index ([0c455cf](https://github.com/Locko2901/lastfm-to-ytm/commit/0c455cf8786c9437f52b7f7feec7fc2a5d85568c))


### Miscellaneous

* **i18n:** refresh DE/EN translation catalogs ([ed12d86](https://github.com/Locko2901/lastfm-to-ytm/commit/ed12d86abd8cffbb2c69f17a7a7b4f19aea5c518))

## [1.5.0](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.4.0...v1.5.0) (2026-05-28)


### Features

* add commits_url to update status; change recency half-life default to 48h ([9cb7045](https://github.com/Locko2901/lastfm-to-ytm/commit/9cb70458744c491575095990275f53ea69e3c551))
* add screenshot automation pipeline ([9abc396](https://github.com/Locko2901/lastfm-to-ytm/commit/9abc396bb012ec2891d3ff9a8e0fb6176b2a40b0))


### Bug Fixes

* **web:** invalidate update-check cache when build SHA changes ([5352527](https://github.com/Locko2901/lastfm-to-ytm/commit/535252725aeca5152b889e2b1926a7002693259b))
* **web:** show latest default branch commit instead of release tag in dev update pill ([ec2b371](https://github.com/Locko2901/lastfm-to-ytm/commit/ec2b37156ff5376f3f261c6bdf6ec09c5b9df11f))


### Documentation

* fix symlink ([d1d75e1](https://github.com/Locko2901/lastfm-to-ytm/commit/d1d75e1eb1e6b4f5b9c60b02953c288113cdb0da))
* full documentation overhaul ([00107d3](https://github.com/Locko2901/lastfm-to-ytm/commit/00107d38141edaf0079f4d6447672c060821e3f7))
* update screenshots ([fddd791](https://github.com/Locko2901/lastfm-to-ytm/commit/fddd7911984d98f991fe6f8d50666361937854f7))


### Styling

* make linters happy ([1b29fcb](https://github.com/Locko2901/lastfm-to-ytm/commit/1b29fcbe0a96ad70aef519f29c988b75724c74f6))
* make linters happy ([8c48edc](https://github.com/Locko2901/lastfm-to-ytm/commit/8c48edc2bc42d047f97c0e4aaf00b0d15476cbe0))

## [1.4.0](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.3.1...v1.4.0) (2026-05-27)


### Features

* **theme:** add per-base custom color scheme with server persistence ([f8d0291](https://github.com/Locko2901/lastfm-to-ytm/commit/f8d02914b9416bd3d3567ea393b479886bdd1d50))
* **update:** detect channel via .channel file and detached-HEAD git probe ([54f1b47](https://github.com/Locko2901/lastfm-to-ytm/commit/54f1b478a795da541fe1c2d4ad1aaca080e32224))


### Bug Fixes

* **install:** map YTMT_REF=main to --pull=dev so installer respects dev channel ([f4ddc24](https://github.com/Locko2901/lastfm-to-ytm/commit/f4ddc24c4008eb3bccde3e3311157a254ae75958))
* **web:** align settings checkbox label and restore muted hint color ([4ac7894](https://github.com/Locko2901/lastfm-to-ytm/commit/4ac78945cc17ef8efbeec07753f7ae772ec3ed55))


### Documentation

* fix punctuation in releases documentation ([4151b69](https://github.com/Locko2901/lastfm-to-ytm/commit/4151b69132d76038b15c89c41c34c734242cb1a6))
* rewrite channel detection and upgrade docs ([a732ffd](https://github.com/Locko2901/lastfm-to-ytm/commit/a732ffd7811af37ba2553e03669bd050f114c8ad))


### Styling

* make linters happy ([456abe4](https://github.com/Locko2901/lastfm-to-ytm/commit/456abe4d1c3d34cbf6366b59942b4ab0f819137e))

## [1.3.1](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.3.0...v1.3.1) (2026-05-27)


### Bug Fixes

* **ci:** publish stable image tags after release-please ([99df709](https://github.com/Locko2901/lastfm-to-ytm/commit/99df709c0c678f0ce3193e47cde167f24fedbfa4))

## [1.3.0](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.2.0...v1.3.0) (2026-05-27)


### Features

* **ci:** publish multi-arch Docker images to GHCR ([b71430c](https://github.com/Locko2901/lastfm-to-ytm/commit/b71430cb0a29b1d948af987e2bf4594b79f54f2e))
* **docker:** add one-line install script for prebuilt image ([87b14e7](https://github.com/Locko2901/lastfm-to-ytm/commit/87b14e7ff643c1755ad86f90cf63e93a890e12f5))


### Bug Fixes

* **docker:** pre-create bind-mount targets and chown browser.json ([c2c38ce](https://github.com/Locko2901/lastfm-to-ytm/commit/c2c38cefff755d9576ac7bda9e35cdd109e03d47))


### Miscellaneous

* **i18n:** refresh extracted message references ([e2881c0](https://github.com/Locko2901/lastfm-to-ytm/commit/e2881c0fc8964306a273dcd678fb75b5750b6701))

## [1.2.0](https://github.com/Locko2901/lastfm-to-ytm/compare/v1.1.3...v1.2.0) (2026-05-27)


### Features

* add RECENCY_MIN_PLAYS gate for recency-weighted playlists ([a239d68](https://github.com/Locko2901/lastfm-to-ytm/commit/a239d6863c0b8eb619d1074fafb16c84005028b3))


### Bug Fixes

* anchor trend chart success bars to baseline ([320a071](https://github.com/Locko2901/lastfm-to-ytm/commit/320a0710fc72ce2cc92a6319a241a3aa01d8ee0d))
* update last sync timestamp on no-op sync runs ([a0d6706](https://github.com/Locko2901/lastfm-to-ytm/commit/a0d67069ca9f581a9dd8eed99b35bb168ceece07))


### Styling

* format SVG elements for consistency in settings modal ([9b54eb1](https://github.com/Locko2901/lastfm-to-ytm/commit/9b54eb12f3087600c9e7932ae0c6e226b7851738))


### Internationalization

* add german ([a20f7cf](https://github.com/Locko2901/lastfm-to-ytm/commit/a20f7cff5929825a16472e61b2ad5edcbecd3ee2))

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
