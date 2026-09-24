# MediaHub Home Assistant Changelog

## 0.16.1-dev

- Fixed mobile **Apply filters** so selected genres, release years and ratings refresh the active infinite-scroll Browse catalogue.

## 0.16.0-dev

- Added a mobile multi-select Genre picker and multiple-genre catalogue filtering.
- Fixed the mobile filter sheet capturing only the initial `All genres` option before TMDb genres finish loading.

## 0.15.0-dev

- Added a first-class **Watchlist** page for upcoming and currently unavailable movies.
- Upgraded the existing Watch for release foundation into a persistent user-owned workflow with Add to Watchlist and Remove from Watchlist actions on Movie details.
- Added All, Upcoming, Waiting and Available Watchlist filters with mobile-first poster cards and release-date context.
- Added manual **Check now** release refresh while preserving automatic lifecycle-aware monitoring.
- Automatic monitoring reuses the existing identity-aware Radarr/Prowlarr release pipeline and current administrator Movie Download Presets. It never bypasses quality, size, seeder, Radarr or identity rules.
- Watchlist policy is server-authoritative. Requesters cannot store looser per-movie release rules, and later checks use the current household presets.
- Added availability states for upcoming, waiting, no eligible release, available, downloading and downloaded movies.
- Added persistent poster metadata, first-available timestamp and availability state through upgrade-safe SQLite migrations.
- Provider/network failures preserve the last known Watchlist state instead of falsely changing a movie to unavailable.
- Available movies still require the user to open the existing release-selection workflow and explicitly choose/request a release. Watchlist monitoring never auto-downloads.
- Preserved release identity validation for ambiguous titles such as **Below**, including title/year protections already enforced by MediaHub.
- Acceptance examples include **The Social Reckoning (2026)**, **Remain** and **Below**.
- Updated the deployed Home Assistant ingress/external entrypoint to `app.watchlist_main:app`.

## 0.14.2-dev

- Restored the administrator **Download Presets** UI to the deployed Home Assistant ingress entrypoint.
- Unified Movie and TV household policy under one administrator-managed Download Presets interface.
- Added editable Movie resolution, maximum-size, minimum-seeder and recent-release fallback settings.
- Added editable TV resolution, season-pack size, episode size and minimum-seeder settings.
- Removed the competing standalone **TV Downloads** Setup card while preserving legacy-setting migration compatibility.
- Added clear preset save confirmation, validation and scoped reset-to-defaults behaviour.
- Enforced current Movie household presets again when a release is acquired, preventing requester payload overrides.
- Classified release exclusions as identity, MediaHub preset, Radarr/Sonarr, library/upgrade, availability or other reasons.
- Replaced the large raw rejection-summary paragraph with a compact structured exclusion summary.
- Kept unavailable releases collapsed and gave each unavailable card a meaningful primary rejection label.
- Corrected the Goosebumps-style case where a small, well-seeded 1080p release is blocked by Radarr cutoff/library state rather than MediaHub's size preset.
- Corrected Browse release selection so missing request data does not appear as `Invalid Date`, fake `0%`, fake `0.00 GB` or `Not recorded`.
- BEST MATCH now applies only to genuinely eligible releases.
- Preserved The Dog Stars identity safety, Buffalo Soldiers ±1-year tolerance, opaque tokens, duplicate protection, Watch for release, Radarr, Sonarr, Prowlarr, qBittorrent, Plex Movie integration and Home Assistant ingress behaviour.

## 0.14.1-dev

- Fixed a Home Assistant ingress freeze introduced by the v0.14 mobile UX layer.
- Hardened mobile startup so optional/late DOM elements cannot abort the entire UI bootstrap.
- Removed an unnecessary requester-side preset bootstrap call from startup.
- Throttled DOM reconciliation work to animation frames to avoid excessive mutation processing.
- Preserved v0.14 filter sheet, modal ownership, safe-area handling, Browse/detail state restoration and read-only requester policy presentation.

## 0.14.0-dev

- Completed the iPhone/Home Assistant ingress mobile UX pass.
- Added a proper staged mobile filter sheet with active-filter count, Clear and Apply actions.
- Fixed collection controls so Popular / Now Playing / Top Rated / Upcoming remain reachable at narrow widths and with the iOS keyboard open.
- Added clear-search support and consolidated the mobile debounced search ownership.
- Made Movie/TV details full-screen mobile surfaces with safe-area-aware Back/Close behaviour and suspended bottom navigation while a modal owns the viewport.
- Improved structured detail loading and reduced scroll/layout jumps when details replace the skeleton.
- Preserves Browse and parent-detail scroll position across nested release selection.
- Uses horizontal cast presentation on mobile.
- Corrected the requester Movie policy regression: maximum size, seeders and quality remain administrator-controlled household Presets rather than editable request controls.
- Added safe-area-aware bottom content spacing, reduced-motion handling and dynamic visual viewport/keyboard behaviour.
- Existing release identity, BEST MATCH, automatic Downloads polling, Admin Presets, Radarr, Sonarr, Prowlarr, qBittorrent, Plex Movie, actor search, infinite scrolling and Watch for release remain intact.

## 0.13.0-dev

- Added release identity validation before Movie/TV releases can become downloadable.
- Fixed false-positive Movie results such as **The Dog Stars** returning unrelated TV episodes.
- Accepts strong title matches with sensible ±1-year tolerance, including **Buffalo Soldiers 2001/2002** naming.
- Rejected identity matches no longer receive usable release-selection tokens.
- Added clearer match/rejection information and **BEST MATCH** highlighting.
- Optimised iPhone/HA ingress Browse with a smaller first viewport, compact Filters control and denser release cards.
- Added debounced search and a structured Movie-detail loading skeleton.
- Added collapsed unavailable releases on mobile.
- Downloads now refresh automatically while visible instead of requiring manual Refresh for normal progress updates.
- Added mobile bottom navigation while keeping Setup administrator-only.
- Existing Admin Presets, Radarr, Sonarr, Prowlarr, qBittorrent, Plex Movie, actor search, infinite scrolling and Watch for release remain intact.
