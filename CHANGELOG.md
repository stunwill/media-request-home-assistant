# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- Shared rich movie-detail presentation for Browse and Downloads.
- Source-labelled TMDb ratings and safe IMDb/TMDb external review links when identifiers are available.
- Director, primary cast, cast profile images, Australian certification, and richer movie metadata in the movie detail modal.
- Clickable cast members backed by stable TMDb person IDs and a dedicated actor-filmography endpoint.
- Rich Downloads movie details with request owner, request date, current status/progress, selected release title, estimated size, and library availability.
- Responsive and keyboard-accessible cast cards, rating links, and downloadable-movie detail cards.
- Regression coverage for actor IDs, director metadata, certification, ratings, actor discovery, download detail context, and contextual action suppression.

### Changed

- Development version advanced to `0.8.0-dev`.
- The deployed application entrypoint is now `app.rich_details:app`, layered above the v0.7.0 release-lifecycle implementation.
- Browse and Downloads now share one movie-details renderer with context-specific actions instead of separate modal implementations.
- TMDb detail normalisation now retains cast person IDs/profile images, director information, AU certification, and safe external IDs.
- Actor selection now uses TMDb `with_cast` by person ID once the actor is known, while existing actor-name search remains available from Browse search.

### Fixed

- Downloaded/available movies can now be opened for full metadata without showing inappropriate request, release-selection, or watch-for-release actions.
- Missing optional ratings or actor profile images no longer require placeholder data.

### Known limitations

- Rotten Tomatoes is not scraped or fabricated. No reliable configured ratings feed currently supplies a Rotten Tomatoes score.
- IMDb is linked when TMDb supplies an IMDb ID, but MediaHub does not fabricate an IMDb score.
- Plex deep linking was investigated but is not implemented in v0.8.0 because the current repository has no Plex URL/token/library identity configuration. MediaHub does not perform unsafe title-only Plex matching.

## [0.7.0-dev] - 2026-08-25

### Added

- Release-aware movie lifecycle classification using TMDb regional release-date data, including announced, theatrical upcoming, in cinemas, digital upcoming/available, physical upcoming/available, and released/unknown states.
- Australian regional release-date selection by default, with theatrical, digital, and physical dates treated as separate milestones.
- Persisted **Watch for release** requests with per-user duplicate protection, shared movie-level scheduling, restart persistence, next-check timestamps, and lightweight background polling.
- Upcoming-title movie detail UX with lifecycle status, regional theatrical messaging, separate digital-date messaging, **Watch for release** as the primary action, **Search anyway** as the manual override, and trailer access preserved.
- Release-aware search deferral so clearly unreleased titles do not generate unnecessary automatic Radarr/Prowlarr searches.
- Search diagnostics that distinguish expected upcoming zero-results, released-title zero-results, and cases where releases were returned but all were rejected by policy.
- Concise rejection summaries for size, seeder, quality, Radarr and related release-policy filters while retaining detailed server logging.
- Resident Evil (2026) regression fixtures that verify valid metadata and trailer availability do not imply downloadable media availability before the Australian theatrical date.
- Additional lifecycle regression coverage for announced titles, future theatrical releases, movies currently in cinemas, digital and physical release milestones, regional dates, duplicate watches, multi-user watches, persisted watch state, and scheduling cadence.
- Administrator-only per-user activity history with `GET /api/users/{user_id}/activity`, showing request and download lifecycle events without exposing credentials, tracker identifiers, torrent hashes, or internal integration data.
- A responsive **View activity** action on the Users page with title, lifecycle status, date, time, and safe rejection context.
- Transition-based `movie_download_started`, failure, rejection, cancellation, and superseded lifecycle audit events, guarded against duplicate entries during repeated Downloads polling.
- Direct Prowlarr fallback search when Radarr returns zero releases for a current-year movie or a movie released within the last 12 months.
- Recent-release quality fallback for movies released within the last 12 months.
- TMDb actor-name search fallback using person lookup and cast discovery.
- A partial unique database index that prevents more than one active request for the same TMDb movie.
- Startup reconciliation that marks older active duplicate movie requests as superseded and releases their reserved storage.
- Radarr duplicate checks that reject a new request when the same TMDb movie is already queued or present in the Radarr library.
- Downloads de-duplication that collapses historical duplicate request rows to the most useful status.
- GitHub Actions CI for Python compilation, critical Ruff checks, Home Assistant add-on YAML validation, application import smoke testing, the full test suite, and dependency vulnerability auditing.

### Changed

- Development version advanced to `0.7.0-dev`.
- TMDb detail requests include regional release-date records.
- Existing recent-release and CAM/TS fallback behaviour remains downstream of lifecycle awareness.
- Downloadable release results are sorted ahead of rejected results.
- Radarr remains the preferred release source, with Prowlarr direct search used only when appropriate.

### Fixed

- Upcoming movies no longer appear to have failed when indexers correctly return no releases before the expected release window.
- Movie metadata or trailer availability no longer implies that a downloadable release exists.
- Repeated automatic searching is avoided for titles that are still clearly announced or pre-theatrical.
- Repeated Downloads refreshes do not create duplicate lifecycle activity entries for the same transition.
- Duplicate movie requests remain protected by the existing active-request uniqueness guard.
- Existing duplicate request records no longer produce repeated movie cards in Downloads.
- Completed movie imports are reconciled by stable TMDb ID if Radarr's internal movie ID changes.
- Prowlarr connection validation uses its supported `/api/v1/system/status` endpoint.
- qBittorrent password authentication continues to use the compatible authenticated API flow.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
