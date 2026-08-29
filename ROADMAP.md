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

Status: Planned

### Features
- [ ] Add television discovery and TV-series detail workflows.
- [ ] Add request lifecycle support for series, seasons and episodes.
- [ ] Add Downloads/library visibility for TV content without weakening movie workflows.

### Integrations
- [ ] Use the existing Sonarr integration for real TV request submission and status reconciliation.
- [ ] Preserve Prowlarr as the indexer boundary and qBittorrent as the download client.
- [ ] Extend Plex library awareness to TV only where stable identifiers can be matched confidently.

### UX / Quality
- [ ] Reuse existing Browse, rich-details and Downloads interaction patterns where practical.
- [ ] Keep movie and TV states clearly distinguishable.
- [ ] Maintain Home Assistant ingress, external login and responsive/mobile behaviour.

### Testing
- [ ] Add Sonarr request and reconciliation tests.
- [ ] Add TV duplicate-protection tests.
- [ ] Add TV release-selection and library-state regression coverage.
- [ ] Keep all existing movie, Radarr, Prowlarr, qBittorrent, Plex and lifecycle tests intact.

## Future

- Notifications for watched releases, download completion and library availability.
- Household recommendation improvements using request/library history and explainable metadata signals.
- Persistent metadata caching and broader performance tuning where profiling shows value.
- Additional media types only after movie and television workflows are stable.
