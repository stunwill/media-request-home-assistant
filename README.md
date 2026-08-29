# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress access
- Standalone MediaHub login for access without a Home Assistant account
- Administrator user management, password resets, account disabling, and role assignment
- Per-user request history and roles
- Automatic request approval
- TMDb movie discovery, search, pagination, genre, release-year and rating-range filters, posters, rich details, cast, ratings, trailers, and regional release dates
- Release-aware movie lifecycle handling for announced, theatrical, digital, physical, and uncertain availability states
- Persisted **Watch for release** workflow with lightweight background checking
- Automatic movie requests using selectable 720p/1080p, maximum-size, minimum-seeder, and Radarr acceptance rules
- Interactive release selection with IPTorrents results supplied through Prowlarr and Radarr
- Release-search diagnostics that distinguish no indexer results from all results being filtered out
- Radarr movie creation, interactive search, release submission, and download/library reconciliation
- qBittorrent download progress and path diagnostics
- Optional Plex library awareness with stable TMDb/IMDb matching and safe Watch in Plex links
- Storage-space protection and automatic rejection
- Append-only audit trail

## Project status

MediaHub is in active development. The current development version is `0.9.0-dev`, which includes Plex Library Intelligence on top of the rich movie-details and release-aware request stack. Television discovery and real Sonarr request submission remain planned work.

## Repository metadata contract

MediaHub keeps machine-readable project/release metadata in predictable locations so DevHub and maintainers can determine repository state without inferring it from implementation details:

- `ROADMAP.md` — delivered, planned and future phases using semantic-version headings and explicit `Status:` values.
- `CHANGELOG.md` — detailed repository/project release history.
- `mediahub/CHANGELOG.md` — concise Home Assistant user-facing release notes beside `mediahub/config.yaml`.
- `mediahub/config.yaml` — Home Assistant add-on version and manifest metadata.
- `mediahub/app/plex_main.py` — current deployed application entrypoint; `/api/health` reports the same application version.
- Git tags/releases — actual published releases use semantic tags in the form `vX.Y.Z` and meaningful GitHub Release notes.
- Pull requests and GitHub Actions remain the authoritative sources for proposed changes and CI status.

Metadata-only maintenance does not invent a new MediaHub product version. Product release PRs must update the manifest/application version, both changelogs, roadmap status, and release metadata together.

## Release-aware movie workflow

MediaHub deliberately separates **metadata availability** from **media availability**. A movie can exist in TMDb and have artwork, cast data, a synopsis, and a trailer while still being months away from a downloadable release.

For movie details, MediaHub loads TMDb regional release-date records and classifies the title into a lifecycle state such as announced, theatrical upcoming, in cinemas, digital upcoming, digital available, physical upcoming, physical available, or released with uncertain availability. The default region is Australia (`AU`) unless a configurable application region is introduced later.

Theatrical, digital, and physical dates are separate milestones. For clearly pre-theatrical movies, the preferred action is **Watch for release**. Users retain control through **Search anyway** for unusual early releases or incomplete metadata.

## Movie request workflow

1. Browse or search TMDb movies, including actor discovery.
2. Open the shared rich movie-details view.
3. For upcoming titles, choose **Watch for release** or **Search anyway**.
4. For requestable titles, choose **Request best release** or **Choose a release**.
5. MediaHub uses Radarr as the movie/request authority and Prowlarr as the indexer boundary.
6. Approved releases are handed to Radarr and qBittorrent.
7. MediaHub reconciles queued, downloading, processing and available state.
8. When Plex is configured, MediaHub independently identifies confidently matched Plex library availability and can show a safe **Watch in Plex** action.

Plex availability is optional and never determines whether Radarr import/reconciliation succeeded.

## Integration connection checks

Configure credentials through the MediaHub setup wizard or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr and qBittorrent through their supported APIs. Plex is an optional additional integration with server-side token handling and sanitised status reporting.

Credentials entered in the wizard are stored in MediaHub's private `/data/mediahub-settings.json` file with owner-only permissions. Secret values remain write-only and are never included in browser responses.

## Users, roles, and external login

MediaHub supports two deliberately separate authentication listeners:

- Home Assistant Ingress on internal port `8099` accepts only the documented Home Assistant identity.
- The external interface on port `8100` accepts only MediaHub username/password sessions and ignores Home Assistant identity headers.

The first authenticated MediaHub user becomes administrator. Administrators can manage integrations, audit history and users; managers can view household operations; requesters can create requests and view their own history.

Public self-registration is disabled. Passwords are salted `scrypt` hashes, sessions are hashed and time-limited, and state-changing external requests require CSRF protection.

## Radarr request settings

After Radarr connects, choose its movie root folder and quality profile on the Setup screen. Leaving either value on **Automatic** uses Radarr's first available option. MediaHub adds a movie without immediately searching, allowing lifecycle awareness, release rules and the manual picker to run before any download starts.
