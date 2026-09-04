# MediaHub Roadmap

## v0.9.0 - Plex Library Intelligence

Status: Delivered

### Features
- [x] Recognise movies already available in Plex.
- [x] Show Plex availability in shared Browse and Downloads movie details.
- [x] Provide safe Watch in Plex links for confident matches.
- [x] Protect against duplicate requests for exact Plex matches.

### Integrations
- [x] Optional Plex server configuration.
- [x] Stable TMDb/IMDb identifier matching.
- [x] Plex movie-library discovery and bounded caching.

## v0.10.0 - Television Requests and Sonarr Workflow

Status: Delivered

### Features
- [x] Add separate Movies and TV Shows Browse modes with independent catalogue state.
- [x] Add TMDb television discovery, search, filters, rich TV-series details and season metadata.
- [x] Add request lifecycle support for entire series and selected seasons.
- [x] Add Downloads/library visibility for TV content.

### Integrations
- [x] Use Sonarr for series lookup, add, search and status reconciliation.
- [x] Preserve Prowlarr and qBittorrent integration boundaries.

### UX / Quality
- [x] Replace manual catalogue pagination with automatic infinite scrolling.
- [x] Stabilise search and exclude explicitly non-English catalogue results by default.

## v0.11.0 - TV Release Selection & Size-Aware Downloads

Status: Delivered

### Features
- [x] Add season details and Sonarr-backed episode availability views.
- [x] Add interactive season-pack and individual-episode release selection.
- [x] Add opaque single-use TV release tokens.

### Integrations
- [x] Use Sonarr interactive release endpoints and Sonarr-managed grab/import flow.
- [x] Add configurable 10 GB season and 1 GB episode size limits with server-side enforcement.

## v0.12.0 - Admin Setup Presets

Status: Delivered

### Features
- [x] Split Setup into Service Connections and Presets sections.
- [x] Add administrator-managed discovery, Movie and TV presets.
- [x] Add Reset to defaults.

### UX / Quality
- [x] Remove requester-editable Movie release-policy controls in favour of global administrator presets.
- [x] Keep Setup/preset mutation administrator-only.

## v0.13.0 - Release Identity, Mobile UX & Live Downloads

Status: In Progress

### Features
- [x] Add deterministic Movie release identity validation before quality/download eligibility.
- [x] Reject TV episodes and unrelated title matches from Movie release results.
- [x] Support explainable title/year confidence including strong ±1-year Movie matches.
- [x] Add TV series/season/episode release identity validation.
- [x] Prevent rejected identity matches from receiving usable release-selection tokens.
- [x] Add BEST MATCH and collapsed unavailable-release treatment.

### UX / Quality
- [x] Reduce mobile Browse vertical overhead and hide the large hero on narrow screens.
- [x] Add compact mobile Filters control and debounced search.
- [x] Add structured Movie-detail loading skeletons and denser release cards.
- [x] Add mobile bottom navigation with administrator-only Setup visibility.
- [x] Add visibility-aware automatic Downloads polling for live progress.

### Testing
- [x] Add The Dog Stars false-positive regression coverage.
- [x] Add Buffalo Soldiers ±1-year matching regression coverage.
- [x] Add TV identity and core mobile UX regression coverage.
- [ ] Complete full-suite CI and resolve any integration regressions.

## Future

- Plex TV-library matching and safe TV deep links after the TV/Sonarr workflow has proven stable.
- Notifications for watched releases, download completion and library availability.
- Household recommendation improvements using request/library history and explainable metadata signals.
- Persistent metadata caching and broader performance tuning where profiling shows value.
- Additional media types only after movie and television workflows are stable.
