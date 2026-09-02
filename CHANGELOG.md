# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- **Admin Setup Presets** with separate **Service Connections** and **Presets** sections.
- Administrator-managed catalogue language policy with **English only** retained as the default and an optional **Any original language** mode.
- Administrator-managed Movie presets for allowed 1080p/720p resolutions, maximum release size, minimum seeders and recent-release fallback policy/window.
- Administrator-managed TV presets for allowed 1080p/720p resolutions, maximum season-pack size, maximum episode size and minimum seeders.
- **Reset to defaults** for the complete preset set.
- New administrator-only `/api/setup/presets` and `/api/setup/presets/reset` API surface.

### Changed

- Development version advanced to `0.12.0-dev`.
- The deployed application entrypoint is now `app.preset_ui:app`.
- Search/download defaults that were previously hard-coded or editable per Movie request are now centrally managed household presets.
- Movie release eligibility always uses the saved administrator preset instead of requester-supplied size/seeder/quality overrides.
- TV season/episode release eligibility uses the saved administrator resolution, size and seeder presets.
- TMDb Movie and TV search/catalogue language filtering reads the saved discovery preset dynamically.
- Existing v0.11 `tv_downloads` size settings remain an upgrade source and are synchronised when Presets are saved.

### Protected

- Preset mutation is administrator-only.
- Requesters and managers cannot alter household release policy.
- Duplicate protection, opaque release tokens, credential redaction, role enforcement and other security invariants remain non-configurable.
- Existing Movie/TV discovery, infinite scrolling, release lifecycle, Radarr, Sonarr, Prowlarr, qBittorrent and Plex behavior remains intact apart from intentionally configurable preset decisions.

## [0.11.0-dev] - 2026-09-02

### Added

- **TV Release Selection & Size-Aware Downloads** for season packs and individual episodes.
- Dedicated season views with Sonarr-backed episode availability, downloading, missing and unaired states.
- Interactive Sonarr season-pack and individual-episode release searches with visible size, quality, source, codec, seeders and indexer metadata.
- Opaque, expiring, single-use TV release-selection tokens; sensitive release download URLs never reach the browser.
- Configurable hard TV size limits with safe defaults: 10 GB per season pack and 1 GB per episode.
- Selected Sonarr release grabbing through Sonarr, preserving Sonarr -> qBittorrent -> import ownership.
- Episode-level acquisition records and reconciliation metadata for selected release size, season/episode identity and Sonarr episode identity.

### Changed

- TV details make **View season** the primary acquisition path; **Request entire series** remains an explicitly advanced secondary action.
- Season acquisition favors selecting a known release instead of immediately firing automatic `SeasonSearch`.
- Individual missing episodes can be opened and searched independently.
- After an episode release is sent to Sonarr, MediaHub returns to the parent episode list and refreshes authoritative Sonarr availability state.

### Protected

- Season packs over the configured season limit and episode releases over the configured episode limit are rejected server-side.
- Already-imported episodes cannot be searched/grabbed through the normal episode workflow.
- Expired or reused TV release tokens are rejected.

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
