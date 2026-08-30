# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress access
- Standalone MediaHub login for access without a Home Assistant account
- Administrator user management, password resets, account disabling, and role assignment
- Per-user request history and roles
- Automatic request approval
- Separate Movies and TV Shows Browse modes with automatic infinite scrolling
- TMDb movie discovery, search, genre, release-year/rating filters, rich details, cast, ratings, trailers, and regional release dates
- TMDb TV discovery, search, genres, first-air-year/rating filters, rich series details, cast, creators, networks and seasons
- Release-aware movie lifecycle handling for announced, theatrical, digital, physical, and uncertain availability states
- Persisted **Watch for release** workflow with lightweight background checking
- Automatic movie requests using selectable 720p/1080p, maximum-size, minimum-seeder, and Radarr acceptance rules
- Whole-series and selected-season TV requests through Sonarr
- Interactive movie release selection with IPTorrents results supplied through Prowlarr and Radarr
- Radarr movie creation, release submission, and download/library reconciliation
- Sonarr TV series lookup, monitoring/search, and episode/library reconciliation
- qBittorrent download progress and path diagnostics
- Optional Plex movie-library awareness with stable TMDb/IMDb matching and safe Watch in Plex links
- Storage-space protection and automatic rejection
- Append-only audit trail

## Project status

MediaHub is in active development. The current development version is `0.10.0-dev`, delivering the planned Television Requests and Sonarr Workflow phase while preserving the existing movie, Plex, Radarr, Prowlarr and qBittorrent stack. Plex TV-library matching remains future work; TV requests do not depend on Plex.

## Repository metadata contract

MediaHub keeps machine-readable project/release metadata in predictable locations so DevHub and maintainers can determine repository state without inferring it from implementation details:

- `ROADMAP.md` — delivered, in-progress/planned and future phases using semantic-version headings and explicit `Status:` values.
- `CHANGELOG.md` — detailed repository/project release history.
- `mediahub/CHANGELOG.md` — concise Home Assistant user-facing release notes beside `mediahub/config.yaml`.
- `mediahub/config.yaml` — Home Assistant add-on version and manifest metadata.
- `mediahub/app/tv_ui.py` — current deployed application entrypoint; `/api/health` reports the same application version.
- Git tags/releases — actual published releases use semantic tags in the form `vX.Y.Z` and meaningful GitHub Release notes.
- Pull requests and GitHub Actions remain the authoritative sources for proposed changes and CI status.

Metadata-only maintenance does not invent a new MediaHub product version. Product release PRs must update the manifest/application version, both changelogs, roadmap status, and release metadata together.

## Browse and infinite scrolling

Browse defaults to **Movies** and provides a clear **Movies / TV Shows** selector. Each media type retains independent collection, search/filter and pagination state. Movie results never mix with TV results.

The previous manual **Load more Movies** button is removed. Both media types use an `IntersectionObserver` sentinel near the end of the grid. MediaHub requests one additional TMDb page at a time, appends unique TMDb IDs, prevents concurrent duplicate page loads, stops at the final page, and keeps already-loaded results visible if a later request fails.

## Movie request workflow

1. Browse or search TMDb movies, including actor discovery.
2. Open the shared rich movie-details view.
3. For upcoming titles, choose **Watch for release** or **Search anyway**.
4. For requestable titles, choose **Request best release** or **Choose a release**.
5. MediaHub uses Radarr as the movie/request authority and Prowlarr as the indexer boundary.
6. Approved releases are handed to Radarr and qBittorrent.
7. MediaHub reconciles queued, downloading, processing and available state.
8. When Plex is configured, MediaHub independently identifies confidently matched Plex movie availability and can show a safe **Watch in Plex** action.

Movie Plex availability is optional and never determines whether Radarr import/reconciliation succeeded.

## TV request workflow

1. Select **TV Shows** in Browse and browse Popular, Airing today, On TV or Top rated TMDb collections, or search by title.
2. Open a series to view overview, dates/status, seasons, episode counts, creators, networks, cast and trailer metadata.
3. Choose **Request entire series** or select one or more seasons.
4. MediaHub uses the TMDb/TVDB identity to locate or reuse the series in Sonarr.
5. Sonarr monitors the requested scope and runs `SeriesSearch` or `SeasonSearch` through its configured indexers/download client.
6. MediaHub reconciles episode-file availability and distinguishes searching, downloading, partially available and available TV requests in Downloads.

Single-episode request UI and Plex TV-library matching are intentionally deferred from the first TV release.

## Integration connection checks

Configure credentials through the MediaHub setup wizard or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr and qBittorrent through their supported APIs. Plex is an optional additional integration with server-side token handling and sanitised status reporting.

Sonarr TV requests additionally require a TV root folder and quality profile. Leaving these unselected may use Sonarr's first available values when valid, following the same conservative setup principle as Radarr.

Credentials entered in the wizard are stored in MediaHub's private `/data/mediahub-settings.json` file with owner-only permissions. Secret values remain write-only and are never included in browser responses.

## Users, roles, and external login

MediaHub supports two deliberately separate authentication listeners:

- Home Assistant Ingress on internal port `8099` accepts only the documented Home Assistant identity.
- The external interface on port `8100` accepts only MediaHub username/password sessions and ignores Home Assistant identity headers.

The first authenticated MediaHub user becomes administrator. Administrators can manage integrations, audit history and users; managers can view household operations; requesters can create requests and view their own history.

Public self-registration is disabled. Passwords are salted `scrypt` hashes, sessions are hashed and time-limited, and state-changing external requests require CSRF protection.

## Radarr and Sonarr request settings

After Radarr connects, choose its movie root folder and quality profile on the Setup screen. MediaHub adds movies without uncontrolled automatic search so lifecycle awareness and release rules remain authoritative.

After Sonarr connects, configure its TV root folder and quality profile. TV requests use Sonarr's native series/season monitoring and search commands rather than reusing the movie-specific release-token picker.
