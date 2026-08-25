# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

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
- Search diagnostics that distinguish expected upcoming zero-results, released-title zero-results, and cases where releases were returned but all were rejected by policy.
- Concise rejection summaries for size, seeder, quality, Radarr and related release-policy filters while retaining detailed server logging.
- Resident Evil (2026) regression fixtures that verify valid metadata and trailer availability do not imply downloadable media availability before the Australian theatrical date.
- Additional lifecycle regression coverage for announced titles, future theatrical releases, movies currently in cinemas, digital and physical release milestones, regional dates, duplicate watches, multi-user watches, persisted watch state, and scheduling cadence.
- Administrator-only per-user activity history with `GET /api/users/{user_id}/activity`, showing request and download lifecycle events without exposing credentials, tracker identifiers, torrent hashes, or internal integration data.
- A responsive **View activity** action on the Users page with title, lifecycle status, date, time, and safe rejection context.
- Transition-based `movie_download_started`, failure, rejection, cancellation, and superseded lifecycle audit events, guarded against duplicate entries during repeated Downloads polling.
- Direct Prowlarr fallback search when Radarr returns zero releases for a current-year movie or a movie released within the last 12 months. MediaHub searches the configured Prowlarr indexers by movie title and year, filters obvious title/year mismatches, maps the result back to the synced Radarr indexer, and keeps Radarr as the download/import authority.
- Recent-release quality fallback for movies released within the last 12 months. MediaHub still prefers eligible 720p/1080p releases, but when none are available it can surface CAM, telesync, telecine, or screener candidates that still meet size, seeder, download, and non-quality rejection rules.
- TMDb actor-name search fallback using person lookup and cast discovery.
- A partial unique database index that prevents more than one active request for the same TMDb movie.
- Startup reconciliation that marks older active duplicate movie requests as superseded and releases their reserved storage.
- Radarr duplicate checks that reject a new request when the same TMDb movie is already queued or present in the Radarr library.
- Downloads de-duplication that collapses historical duplicate request rows to the most useful status, preferring available and actively downloading records.
- Regression tests for actor search, recent-release fallback policy, direct Prowlarr zero-result fallback, duplicate download handling, release ordering, user activity authorization, activity ordering, sensitive-field redaction, lifecycle audit de-duplication, and responsive activity UI presence.
- GitHub Actions CI for Python compilation, critical Ruff checks, Home Assistant add-on YAML validation, application import smoke testing, the full test suite, and dependency vulnerability auditing.
- TMDb movie-rating range filtering from `1.0` to `10.0` with one-decimal input precision.
- Selectable `720p and 1080p`, `1080p only`, and `720p only` release policies.
- Incremental **Load more movies** pagination across TMDb catalogue and search results.
- Server-backed movie genre filtering using TMDb's current genre catalogue.
- Release-year range filtering for movie discovery and search results.
- An administrator-only Download workflow diagnostic for Radarr hardlinks and qBittorrent completed, incomplete, and `radarr` category paths.
- Automatic ten-second refresh while the Downloads view is open.
- Append-only `movie_available` audit events when Radarr first reports an imported library file.
- Optional qBittorrent 5.2+ API-key authentication for setup checks and download progress.
- The supplied `MediaHub by Stu` wordmark on the main interface and external sign-in screen.
- A matching play-mark browser icon derived from the supplied MediaHub artwork.
- A standalone MediaHub sign-in screen for users who do not have a Home Assistant session.
- An admin-only Users page for local account creation, role assignment, activation, deactivation, and password reset.
- Salted `scrypt` password hashing, hashed seven-day sessions, `HttpOnly`/`SameSite` cookies, HTTPS `Secure` cookies, CSRF protection, and login throttling.
- Immediate session revocation after password reset or account deactivation.
- A dedicated external listener on port `8100` that ignores Home Assistant identity headers.
- External HTTPS reverse-proxy and tunnel deployment documentation.
- A responsive movie browsing dashboard with TMDb collections, search, posters, details, cast, ratings, runtime, and trailers.
- Automatic movie requests using configurable 720p/1080p, maximum-size, minimum-seeder, storage, and Radarr acceptance rules.
- Interactive Radarr release search with indexer, release title, quality, size, seeders, age, freeleech flags, and rejection reasons.
- Opaque, user-bound, short-lived release tokens so tracker GUIDs, download URLs, passkeys, and torrent hashes never reach the browser.
- Radarr movie creation with automatic search disabled, followed by explicit release submission.
- Radarr root-folder and quality-profile selection with safe automatic defaults.
- Download status synchronisation from Radarr, qBittorrent, and the imported Radarr library.
- Backwards-compatible request-table migrations for Radarr and download lifecycle fields.
- Persistent MediaHub users linked to authenticated Home Assistant Ingress identities.
- `admin`, `manager`, and `requester` roles with API authorization boundaries.
- Administrator user-list and role-management endpoints with last-admin protection.
- Role-scoped request history and current-user profile endpoints.
- Automatic detection of installed Prowlarr, Radarr, Sonarr, and qBittorrent Home Assistant apps.
- An Ingress-safe setup wizard with discovered URL suggestions, credential entry, and live connection status.
- Private runtime integration settings with atomic writes, restrictive file permissions, and write-only secrets.
- Credential-safe setup and discovery APIs.
- Typed connection validation for TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent.
- A credential-safe `GET /api/integrations/status` endpoint for the future setup wizard.
- Prowlarr URL and API key add-on configuration.

### Changed

- Development version advanced to `0.8.0-dev`.
- The deployed application entrypoint is now `app.rich_details:app`, layered above the v0.7.0 release-lifecycle implementation.
- Browse and Downloads now share one movie-details renderer with context-specific actions instead of separate modal implementations.
- TMDb detail normalisation now retains cast person IDs/profile images, director information, AU certification, and safe external IDs.
- Actor selection now uses TMDb `with_cast` by person ID once the actor is known, while existing actor-name search remains available from Browse search.
- TMDb detail requests include regional release-date records so MediaHub can distinguish metadata availability from actual media availability.
- Existing recent-release and CAM/TS fallback behaviour remains downstream of lifecycle awareness. MediaHub does not treat a pre-theatrical current-year title as evidence that a low-quality release should exist.
- Downloadable release results are always sorted ahead of rejected results. Eligible results retain quality, seeder, size, and age ranking, while rejected entries remain visible below a labelled **Other unavailable releases** section with their rejection reasons intact.
- Movies dated later in the current calendar year remain eligible for manual recent-release fallback, but lifecycle-aware automatic behaviour defers searches before their reasonable release window.
- Radarr remains the preferred release source. MediaHub queries Prowlarr directly only when appropriate, rather than bypassing normal Radarr quality handling for every search.
- Recent movies keep 720p/1080p as the preferred policy, with lower-quality fallback only when no eligible HD release exists.
- Movie request submission continues to check both MediaHub and live Radarr queue/library state before creating a request.
- The Downloads view continues to return one logical card per TMDb movie instead of exposing historical duplicate rows.
- The default release policy continues to accept both 720p and 1080p results while respecting Radarr approval, size, and seeder rules.

### Fixed

- Downloaded/available movies can now be opened for full metadata without showing inappropriate request, release-selection, or watch-for-release actions.
- Missing optional ratings or actor profile images no longer require placeholder data.
- Upcoming movies no longer appear to have failed when indexers correctly return no releases before the expected release window.
- Movie metadata or trailer availability no longer implies that a downloadable release exists.
- Repeated automatic searching is avoided for titles that are still clearly announced or pre-theatrical.
- Repeated Downloads refreshes do not create duplicate lifecycle activity entries for the same transition.
- Duplicate movie requests remain protected by the existing active-request uniqueness guard.
- Existing duplicate request records no longer produce repeated movie cards in Downloads.
- Completed movie imports are reconciled by stable TMDb ID if Radarr's internal movie ID changes, and the stored Radarr ID is repaired automatically.
- Prowlarr connection validation uses its supported `/api/v1/system/status` endpoint.
- qBittorrent password authentication continues to use the compatible authenticated API flow.

### Known limitations

- Rotten Tomatoes is not scraped or fabricated. No reliable configured ratings feed currently supplies a Rotten Tomatoes score.
- IMDb is linked when TMDb supplies an IMDb ID, but MediaHub does not fabricate an IMDb score.
- Plex deep linking was investigated but is not implemented in v0.8.0 because the current repository has no Plex URL, token, machine identifier, or library identity configuration. MediaHub does not perform unsafe title-only Plex matching.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
