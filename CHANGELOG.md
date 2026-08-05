# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- A responsive movie browsing dashboard with TMDb collections, search, posters, details, cast, ratings, runtime, and trailers.
- Automatic movie requests using configurable 1080p, maximum-size, minimum-seeder, storage, and Radarr acceptance rules.
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

- Development version advanced to `0.5.0-dev`.
- Ingress identity handling now uses Home Assistant's documented `X-Remote-User-*` headers.
- Setup, discovery, integration settings, audit, and user management require a MediaHub administrator.
- Storage and integration status require a MediaHub manager or administrator.
- The MediaHub panel is explicitly restricted to Home Assistant administrators during setup.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
