# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- **Release Identity & Search Accuracy** validation before Movie/TV release eligibility and token issuance.
- Deterministic Movie title normalisation, TV-episode/season rejection, year-confidence handling and explainable match states.
- Regression protection for **The Dog Stars (2026)** false positives and **Buffalo Soldiers (2002)** ±1-year release naming.
- TV series/season/episode identity validation layered over Sonarr structured metadata.
- Compact mobile Browse treatment, mobile Filters control, debounced search, detail skeletons and compact release cards.
- **BEST MATCH** highlighting for the top eligible release and collapsed unavailable-release results.
- Adaptive Downloads polling while the Downloads view is active, with visibility-aware suspension.
- Mobile bottom navigation for Browse / Downloads / Setup with admin-only Setup visibility.

### Changed

- Development version advanced to `0.13.0-dev`.
- Deployed application entrypoint is now `app.mobile_live_ui:app`.
- Release identity validation now precedes quality, size, seeder and ranking policy.
- Rejected identity matches do not receive usable release tokens.
- Mobile Browse hides the large introductory hero and gives catalogue content priority.
- Advanced discovery filters are compacted behind a mobile Filters action.
- Movie detail loading uses a structured skeleton instead of a single loading message.
- Release cards are denser at narrow Home Assistant/iPhone widths.
- Downloads refresh automatically while visible instead of relying on manual Refresh for normal progress updates.

### Protected

- Existing Admin Setup Presets remain authoritative and administrator-only.
- Actor/person-ID discovery, infinite scrolling, release lifecycle, Watch for release, recent-release fallback, duplicate protection and opaque-token security remain enabled.
- Radarr, Sonarr, Prowlarr, qBittorrent and Plex Movie integration remain the existing service authorities.
- Plex TV-library matching remains deferred.

## [0.12.0-dev] - 2026-09-02

### Added

- **Admin Setup Presets** with separate **Service Connections** and **Presets** sections.
- Administrator-managed catalogue language, Movie download and TV download presets.
- **Reset to defaults** for the complete preset set.

### Changed

- Search/download defaults are centrally managed household presets.
- Movie and TV release eligibility uses saved administrator presets.

## [0.11.0-dev] - 2026-09-02

### Added

- **TV Release Selection & Size-Aware Downloads** for season packs and individual episodes.
- Sonarr-backed episode availability and interactive release selection.
- Configurable hard TV size limits and opaque TV release tokens.

## [0.10.0-dev] - 2026-08-30

### Added

- Separate Movies and TV Shows Browse modes.
- TMDb TV discovery and Sonarr request workflow.
- Automatic catalogue infinite scrolling.

## [0.9.0-dev] - 2026-08-25

### Added

- Optional Plex Movie library intelligence.
- Shared rich Movie details and actor discovery.
- Release-aware Movie lifecycle and Radarr/Prowlarr/qBittorrent reconciliation.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
