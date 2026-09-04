# MediaHub Home Assistant Changelog

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

## 0.12.0-dev

- Reorganised Setup into **Service Connections** and **Presets**.
- Added administrator-only household presets for catalogue language, Movie resolutions/size/seeders, TV resolutions/season size/episode size/seeders and recent-release fallback.
- English-only browsing remains the default but can now be changed by an administrator.
- Movie and TV release rules are applied centrally so requesters cannot override household download limits.
- Added **Reset to defaults** for presets.

## 0.11.0-dev

- Added season-by-season TV acquisition as the primary TV workflow.
- Added season-pack and individual-episode release selection through Sonarr.
- Shows actual release sizes before download.
- Added a default 10 GB maximum season-pack size and 1 GB maximum episode size.
- Added Sonarr-backed episode lists showing Available, Downloading, Missing and Unaired states.

## 0.10.0-dev

- Added separate Movies and TV Shows browsing.
- Added TV Show discovery, search, details and season selection from TMDb.
- Added whole-series and selected-season requests through Sonarr.
- Replaced manual catalogue pagination with automatic infinite scrolling.

## 0.9.0-dev

- Added optional Plex integration and Plex movie-library awareness.
- Added safe Watch in Plex actions for confidently matched movies.
- Added stable TMDb/IMDb Plex matching and credential redaction.

## Earlier development releases

- Added rich movie details, actor discovery, release-aware lifecycle handling and Watch for release.
- Added secure external MediaHub login, household user management and the Radarr/Prowlarr/qBittorrent request stack.
