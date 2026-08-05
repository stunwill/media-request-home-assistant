# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

### Added

- Automatic detection of installed Prowlarr, Radarr, Sonarr, and qBittorrent Home Assistant apps.
- An Ingress-safe setup wizard with discovered URL suggestions, credential entry, and live connection status.
- Private runtime integration settings with atomic writes, restrictive file permissions, and write-only secrets.
- Credential-safe setup and discovery APIs.
- Typed connection validation for TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent.
- A credential-safe `GET /api/integrations/status` endpoint for the future setup wizard.
- Prowlarr URL and API key add-on configuration.

### Changed

- Development version advanced to `0.3.0-dev`.
- The MediaHub panel is explicitly restricted to Home Assistant administrators during setup.

## [0.1.1-dev] - 2026-08-04

### Added

- Home Assistant Ingress-compatible landing page and service status display.

## [0.1.0] - 2026-08-04

### Added

- Initial Home Assistant add-on, FastAPI, SQLite, request, audit, and storage-protection foundation.
