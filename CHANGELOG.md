# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- Separate Movies and TV Shows Browse modes with independent catalogue state.
- TMDb TV discovery, search, TV genres, first-air-year/rating filters, rich series details, cast, creators, networks and season metadata.
- Whole-series and selected-season TV requests through Sonarr.
- Sonarr root-folder and quality-profile operational configuration, series lookup/addition, SeriesSearch/SeasonSearch commands, queue and episode reconciliation.
- TV request persistence and Downloads/library visibility with requested scope, seasons and episode availability counts.
- Automatic catalogue pagination using `IntersectionObserver` for both Movies and TV Shows, with appended results, duplicate-ID protection and bounded concurrent loading.
- Inline infinite-scroll loading/error state that preserves already-loaded catalogue results.

### Changed

- Development version advanced to `0.10.0-dev`.
- The deployed application entrypoint is now `app.tv_ui:app`, layered above the existing Plex/movie stack.
- Browse defaults to Movies but provides a distinct, keyboard-operable Movies / TV Shows selector.
- Manual **Load more Movies** pagination is removed; additional movie and TV pages load automatically near the end of the grid.
- Downloads can now include both movie and TV request records while keeping the media type explicit.
- Movie request, release lifecycle, Radarr/Prowlarr/qBittorrent and Plex movie behavior remain unchanged.

### Fixed

- Catalogue page appends de-duplicate TMDb IDs and prevent repeated concurrent page requests.
- Search, collection and filter changes restart the selected catalogue from page 1 rather than mixing result sets.
- Later-page loading errors no longer clear previously loaded results.

### Known limitations

- Plex TV-library matching is intentionally deferred; the existing Plex movie integration remains unchanged.
- TV requests support entire series and selected seasons in v0.10.0; single-episode request UI is deferred.
- Sonarr performs the TV release search using its native SeriesSearch/SeasonSearch workflow rather than exposing the movie-specific manual release picker.

### Repository metadata

- Root `ROADMAP.md`, root `CHANGELOG.md`, `mediahub/CHANGELOG.md`, manifest/application version and CI metadata checks remain the DevHub repository contract.
- Actual published releases continue to use semantic tags in the form `vX.Y.Z` and meaningful GitHub Release notes.

## [0.9.0-dev] - 2026-08-25

### Added

- Optional Plex integration with private server URL/token configuration, server identity lookup, movie-library discovery, stable TMDb/IMDb matching and safe Watch in Plex links.
- Shared rich movie details for Browse and Downloads, source-labelled ratings, director/cast details and stable actor-ID discovery.
- Release-aware movie lifecycle and Watch for release handling.
- Radarr/Prowlarr/qBittorrent request and download reconciliation with duplicate protection and recent-release fallback.

### Known limitations

- Rotten Tomatoes is not scraped or fabricated.
- IMDb is linked when TMDb supplies an IMDb ID, but MediaHub does not fabricate an IMDb score.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
