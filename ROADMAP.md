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
- [x] Preserve Radarr, Prowlarr and qBittorrent request/download flows independently of Plex availability.

### UX / Quality
- [x] Keep Plex optional and fail gracefully when unavailable.
- [x] Keep Plex credentials server-side and out of browser URLs.
- [x] Reuse the shared rich movie-details experience.

### Testing
- [x] Plex configuration, redaction and connection tests.
- [x] GUID normalisation and match-confidence tests.
- [x] Browse/Downloads Plex regression coverage.
- [x] Existing Radarr/Prowlarr/qBittorrent and lifecycle regression coverage retained.

## v0.10.0 - Television Requests and Sonarr Workflow

Status: In Progress

### Features
- [x] Add separate Movies and TV Shows Browse modes with independent catalogue state.
- [x] Add TMDb television discovery, search, filters, rich TV-series details and season metadata.
- [x] Add request lifecycle support for entire series and selected seasons.
- [x] Add Downloads/library visibility for TV content without weakening movie workflows.

### Integrations
- [x] Use Sonarr for real TV series lookup, add, search and status reconciliation.
- [x] Add Sonarr root-folder and quality-profile operational settings.
- [x] Preserve Prowlarr as the configured indexer boundary and qBittorrent as Sonarr's downstream download client.
- [ ] Extend Plex library awareness to TV only where stable identifiers can be matched confidently.

### UX / Quality
- [x] Replace manual movie catalogue pagination with automatic IntersectionObserver infinite scrolling.
- [x] Use the same automatic infinite scrolling behavior for TV Shows.
- [x] Prevent duplicate page requests and duplicate TMDb cards while appending results.
- [x] Keep movie and TV states clearly distinguishable and maintain responsive/mobile behavior.

### Testing
- [x] Add TMDb TV and Sonarr request/reconciliation regression tests.
- [x] Add TV duplicate-protection and season-scope tests.
- [x] Add infinite-scroll and media-mode UI regression coverage.
- [x] Keep existing movie, Radarr, Prowlarr, qBittorrent, Plex and lifecycle tests intact.

## Future

- Plex TV-library matching and safe TV deep links after the TV/Sonarr workflow has proven stable.
- Notifications for watched releases, download completion and library availability.
- Household recommendation improvements using request/library history and explainable metadata signals.
- Persistent metadata caching and broader performance tuning where profiling shows value.
- Additional media types only after movie and television workflows are stable.
