# MediaHub Home Assistant Changelog

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
