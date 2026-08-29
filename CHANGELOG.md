# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Repository metadata

- Added root `ROADMAP.md` with explicit delivered, planned and future MediaHub phases for DevHub ingestion.
- Added `mediahub/CHANGELOG.md` beside the Home Assistant `config.yaml` for concise add-on release notes.
- Added CI metadata-consistency checks covering roadmap/changelog presence, semantic version format, manifest/application version agreement and current release references.
- Documented the repository metadata contract in `README.md`.
- Established the release metadata convention that actual published releases use semantic tags in the form `vX.Y.Z` and meaningful GitHub Release notes.
- This maintenance update does not change MediaHub product functionality or advance the `0.9.0-dev` development version.

### Added

- Optional Plex integration with private server URL/token configuration, server identity lookup, movie-library discovery, and sanitised connection status.
- Stable Plex movie matching using TMDb IDs first, IMDb IDs second, with conservative title/year fallback only when stable identifiers are unavailable.
- Explicit Plex match confidence states for exact identifier, title/year, ambiguous, and not-found results.
- Ten-minute in-memory Plex library metadata cache with stale-cache fallback during temporary Plex outages.
- Shared Browse/Downloads movie details now include Plex library state and a safe **Watch in Plex** action when a confident exact movie match can be linked.
- Server-side duplicate protection blocks new requests when an exact stable-identifier Plex match proves the movie is already available.
- Existing Plex movies can be recognised from Browse even when they were never requested through MediaHub.
- Plex-specific setup and security regression coverage including token redaction, GUID parsing, ambiguity rejection, safe link generation, optional failure handling, and admin-only configuration.
- Shared rich movie-detail presentation for Browse and Downloads.
- Source-labelled TMDb ratings and safe IMDb/TMDb external review links when identifiers are available.
- Director, primary cast, cast profile images, Australian certification, and richer movie metadata in the movie detail modal.
- Clickable cast members backed by stable TMDb person IDs and a dedicated actor-filmography endpoint.
- Rich Downloads movie details with request owner, request date, current status/progress, selected release title, estimated size, and library availability.
- Responsive and keyboard-accessible cast cards, rating links, downloadable-movie detail cards, Escape-to-close behaviour, focus restoration, and a return path from actor discovery to the originating movie.
- Regression coverage for actor IDs, director metadata, certification, ratings, actor discovery, download detail context, and contextual action suppression.
- Release-aware movie lifecycle classification using TMDb regional release-date data, including announced, theatrical upcoming, in cinemas, digital upcoming/available, physical upcoming/available, and released/unknown states.
- Australian regional release-date selection by default, with theatrical, digital, and physical dates treated as separate milestones.
- Persisted **Watch for release** requests with per-user duplicate protection, shared movie-level scheduling, restart persistence, next-check timestamps, and lightweight background polling.
- Upcoming-title movie detail UX with lifecycle status, regional theatrical messaging, separate digital-date messaging, **Watch for release** as the primary action, **Search anyway** as the manual override, and trailer access preserved.
- Release-aware search deferral so clearly unreleased titles do not generate unnecessary automatic Radarr/Prowlarr searches.
- Search diagnostics that distinguish expected upcoming zero-results, released-title zero-results, and cases where releases were returned but all releases were rejected by policy.
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

- Development version advanced to `0.9.0-dev`.
- The deployed application entrypoint is now `app.plex_main:app`, layered above the v0.8.0 shared rich-details implementation.
- Setup and integration-status payloads now include Plex as an optional sixth integration while keeping Plex failures isolated from MediaHub core functionality.
- Shared movie details now distinguish Radarr library state from Plex availability instead of treating download/import completion as synonymous with Plex playability.
- Browse request actions are suppressed when Plex confidently confirms that the movie is already available.
- Plex tokens remain write-only and all browser-facing Plex links use the token-free Plex web application route.
- Browse and Downloads continue to share one movie-details renderer with context-specific actions.
- TMDb detail normalisation retains cast person IDs/profile images, director information, AU certification, and safe external IDs.
- Actor selection uses TMDb `with_cast` by person ID once the actor is known, while existing actor-name search remains available from Browse search.
- Existing recent-release and CAM/TS fallback behaviour remains downstream of lifecycle awareness.
- Downloadable release results remain sorted ahead of rejected results.
- Radarr remains the preferred release source, with Prowlarr direct search used only when appropriate.

### Fixed

- Existing Plex library movies are no longer presented as needing a new download when an exact stable-identifier match is available.
- Temporary Plex outages do not break Browse, Downloads, movie details, or Radarr/qBittorrent reconciliation.
- Ambiguous Plex matches never produce a **Watch in Plex** action or block a request.
- Plex authentication failures are sanitised so upstream response bodies and tokens cannot leak through MediaHub errors.
- Downloaded/available movies can be opened for full metadata without showing inappropriate request, release-selection, or watch-for-release actions.
- Missing optional ratings or actor profile images do not require placeholder data.
- Upcoming movies do not appear to have failed when indexers correctly return no releases before the expected release window.
- Repeated Downloads refreshes do not create duplicate lifecycle activity entries for the same transition.
- Duplicate movie requests remain protected by the existing active-request uniqueness guard.
- Completed movie imports remain reconciled by stable TMDb ID if Radarr's internal movie ID changes.

### Known limitations

- Plex cache is process-local and refreshes after ten minutes or when Plex settings change. The two MediaHub listener processes may maintain independent caches.
- **Watch in Plex** is produced only when MediaHub has a machine identifier and a confident movie match. Otherwise MediaHub can still show Plex availability without fabricating a playback link.
- Rotten Tomatoes is not scraped or fabricated. No reliable configured ratings feed currently supplies a Rotten Tomatoes score.
- IMDb is linked when TMDb supplies an IMDb ID, but MediaHub does not fabricate an IMDb score.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
