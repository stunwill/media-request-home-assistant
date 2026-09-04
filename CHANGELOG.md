# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- **Mobile UX Completion** for Home Assistant ingress and iPhone-sized viewports.
- Staged mobile filter bottom sheet with active-filter count, Clear filters and atomic Apply filters actions.
- Clear-search action and a single capture-owned 450 ms mobile debounced search path.
- Full-screen mobile detail/release viewport ownership with safe-area-aware bottom navigation suspension.
- Browse/detail scroll-state preservation across nested Movie/TV release navigation.
- Read-only household Movie preset summary in requester release workflows.
- Dynamic viewport and reduced-motion handling for modern iOS/embedded browser behaviour.
- Focused v0.14 regression coverage for modal ownership, filter state, requester preset protection and mobile state restoration.

### Changed

- Development version advanced to `0.14.0-dev`.
- Deployed application entrypoint is now `app.mobile_ux_ui:app`.
- Mobile collection controls are horizontally scrollable rather than clipped at narrow/keyboard-constrained widths.
- Mobile Movie/TV details use a stable structured skeleton as the first meaningful loading state and reset new details to the top.
- Cast presentation uses a horizontal swipe row at mobile widths.
- Bottom navigation is suspended while full-screen mobile modals or the iOS keyboard own the lower viewport.
- Mobile body/setup/users spacing is safe-area-aware so final content can scroll clear of persistent navigation.
- Legacy requester Movie release-rule markup is removed from release-selection surfaces; household Setup Presets remain the only policy authority.
- v0.13 roadmap status is reconciled to Delivered after successful post-merge CI.

### Protected

- Release identity validation still precedes Movie/TV download eligibility and rejected identity matches still receive no usable token.
- The Dog Stars false-positive and Buffalo Soldiers ±1-year regressions remain protected.
- Admin Setup Presets, duplicate protection, actor/person-ID discovery, infinite scrolling, Watch for release and recent-release fallback remain intact.
- Radarr, Sonarr, Prowlarr, qBittorrent and Plex Movie integration remain unchanged in authority and scope.
- Live Downloads 2.0 transfer-speed/ETA/lifecycle expansion remains deferred.

## [0.13.0-dev] - 2026-09-04

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

- Release identity validation precedes quality, size, seeder and ranking policy.
- Rejected identity matches do not receive usable release tokens.
- Mobile Browse hides the large introductory hero and gives catalogue content priority.
- Downloads refresh automatically while visible instead of relying on manual Refresh for normal progress updates.

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
