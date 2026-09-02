# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- **TV Release Selection & Size-Aware Downloads** for season packs and individual episodes.
- Dedicated season views with Sonarr-backed episode availability, downloading, missing and unaired states.
- Interactive Sonarr season-pack and individual-episode release searches with visible size, quality, source, codec, seeders and indexer metadata.
- Opaque, expiring, single-use TV release-selection tokens; sensitive release download URLs never reach the browser.
- Configurable hard TV size limits with safe defaults: 10 GB per season pack and 1 GB per episode.
- Setup controls for TV season/episode size policy with administrator-only updates.
- Selected Sonarr release grabbing through Sonarr, preserving Sonarr -> qBittorrent -> import ownership.
- Episode-level acquisition records and reconciliation metadata for selected release size, season/episode identity and Sonarr episode identity.

### Changed

- Development version advanced to `0.11.0-dev`.
- The deployed application entrypoint is now `app.tv_release_ui:app`.
- TV details now make **View season** the primary acquisition path; **Request entire series** remains available as an explicitly advanced secondary action.
- Season acquisition now favors selecting a known release instead of immediately firing automatic `SeasonSearch`.
- Individual missing episodes can be opened and searched independently.
- After an episode release is sent to Sonarr, MediaHub returns to the parent episode list and refreshes authoritative Sonarr availability state.

### Fixed / Protected

- Season packs over the configured season limit and episode releases over the configured episode limit are rejected server-side.
- Already-imported episodes cannot be searched/grabbed through the normal episode workflow.
- Expired or reused TV release tokens are rejected.
- Movie release selection, lifecycle handling, Plex movie matching, English-only catalogue filtering and infinite scrolling remain unchanged.

### Known limitations

- TV release selection uses Sonarr's interactive `/api/v3/release` results; availability depends on the indexers/search behavior configured in Sonarr/Prowlarr.
- Plex TV-library matching remains deferred; Sonarr episode-file state is authoritative for TV availability.

## [0.10.0-dev] - 2026-08-30

### Added

- Separate Movies and TV Shows Browse modes with independent catalogue state.
- TMDb TV discovery, search, TV genres, first-air-year/rating filters, rich series details, cast, creators, networks and season metadata.
- Whole-series and selected-season TV requests through Sonarr.
- Sonarr root-folder and quality-profile operational configuration, series lookup/addition, SeriesSearch/SeasonSearch commands, queue and episode reconciliation.
- TV request persistence and Downloads/library visibility with requested scope, seasons and episode availability counts.
- Automatic catalogue pagination using `IntersectionObserver` for both Movies and TV Shows, with appended results, duplicate-ID protection and bounded concurrent loading.
- Stable Movie/TV search correction and English-original-language filtering for catalogue results.

### Known limitations

- Plex TV-library matching is intentionally deferred.
- v0.10 TV requests rely primarily on Sonarr automatic series/season searches; explicit TV release selection is introduced in v0.11.

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
