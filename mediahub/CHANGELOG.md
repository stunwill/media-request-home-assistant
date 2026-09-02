# MediaHub Home Assistant Changelog

## 0.11.0-dev

- Added season-by-season TV acquisition as the primary TV workflow.
- Added season-pack and individual-episode release selection through Sonarr.
- Shows actual release sizes before download.
- Added a default 10 GB maximum season-pack size and 1 GB maximum episode size.
- Added administrator Setup controls for both TV size limits.
- Added Sonarr-backed episode lists showing Available, Downloading, Missing and Unaired states.
- Completed episodes no longer offer normal release-search actions.
- Selected episode releases return to the parent season list so the next missing episode can be selected.
- Existing Movie, Plex, Radarr, Prowlarr, qBittorrent, infinite-scroll and English-only catalogue workflows remain intact.

## 0.10.0-dev

- Added separate Movies and TV Shows browsing.
- Added TV Show discovery, search, details and season selection from TMDb.
- Added whole-series and selected-season requests through Sonarr.
- Added TV request/download status and episode availability to Downloads.
- Replaced the manual **Load more Movies** button with automatic infinite scrolling for Movies and TV Shows.
- Added Sonarr root-folder and quality-profile settings required for TV requests.
- Fixed duplicate catalogue loaders after infinite-scroll rollout and filtered explicitly non-English Movie/TV results.
- Existing movie, Plex, Radarr, Prowlarr and qBittorrent workflows remain intact.

## 0.9.0-dev

- Added optional Plex integration and Plex movie-library awareness.
- Added safe Watch in Plex actions for confidently matched movies.
- Improved Browse and Downloads movie details with Plex availability.
- Preserved Radarr, Prowlarr and qBittorrent download/reconciliation behaviour when Plex is unavailable.
- Added stable TMDb/IMDb Plex matching, ambiguity protection and credential redaction.

## 0.8.0-dev

- Added richer shared movie details across Browse and Downloads.
- Added source-labelled ratings, director and cast information.
- Added clickable cast members using TMDb person IDs.
- Added richer downloaded-movie information and contextual action suppression.

## 0.7.0-dev

- Added release-aware movie lifecycle handling.
- Added Watch for release and Search anyway flows for upcoming titles.
- Added Australian release-date awareness and release-search diagnostics.
- Preserved recent-release fallbacks, duplicate protection and download reconciliation.

## Earlier development releases

- Added secure external MediaHub login and household user management.
- Added movie discovery, Radarr/Prowlarr release selection and qBittorrent status.
- Added Home Assistant integration discovery, setup validation, roles and audit history.
