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
- Interactive movie release selection with IPTorrents results supplied through Prowlarr and Radarr
- Season-by-season TV acquisition with interactive Sonarr release selection
- Individual missing-episode release selection with actual release sizes before download
- Configurable TV hard limits: 10 GB per season pack and 1 GB per episode by default
- Radarr movie creation, release submission, and download/library reconciliation
- Sonarr TV series lookup, monitoring, interactive release search/grab, and episode/library reconciliation
- qBittorrent download progress and path diagnostics
- Optional Plex movie-library awareness with stable TMDb/IMDb matching and safe Watch in Plex links
- Storage-space protection and automatic rejection
- Append-only audit trail

## Project status

MediaHub is in active development. The current development version is `0.11.0-dev`, focused on TV Release Selection & Size-Aware Downloads. The release preserves the Movie, Plex, Radarr, Prowlarr, qBittorrent, infinite-scroll and English-only catalogue stack delivered previously.

## Repository metadata contract

MediaHub keeps machine-readable project/release metadata in predictable locations so DevHub and maintainers can determine repository state without inferring it from implementation details:

- `ROADMAP.md` — delivered, in-progress/planned and future phases using semantic-version headings and explicit `Status:` values.
- `CHANGELOG.md` — detailed repository/project release history.
- `mediahub/CHANGELOG.md` — concise Home Assistant user-facing release notes beside `mediahub/config.yaml`.
- `mediahub/config.yaml` — Home Assistant add-on version and manifest metadata.
- `mediahub/app/tv_release_ui.py` — current deployed application entrypoint; `/api/health` reports the same application version.
- Git tags/releases — actual published releases use semantic tags in the form `vX.Y.Z` and meaningful GitHub Release notes.
- Pull requests and GitHub Actions remain the authoritative sources for proposed changes and CI status.

Metadata-only maintenance does not invent a new MediaHub product version. Product release PRs must update the manifest/application version, both changelogs, roadmap status, and release metadata together.

## Browse and infinite scrolling

Browse defaults to **Movies** and provides a clear **Movies / TV Shows** selector. Each media type retains independent collection, search/filter and pagination state. Movie results never mix with TV results.

The previous manual **Load more Movies** button is removed. Both media types use an `IntersectionObserver` sentinel near the end of the grid. MediaHub requests one additional TMDb page at a time, appends unique TMDb IDs, prevents concurrent duplicate page loads, stops at the final page, and keeps already-loaded results visible if a later request fails.

Explicitly non-English Movie/TV catalogue results are filtered using TMDb original-language metadata while legacy records without language metadata remain compatible.

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

The normal TV acquisition workflow is deliberately season-first:

1. Select **TV Shows** in Browse and open a series.
2. Choose a season using **View season**.
3. MediaHub asks Sonarr for episode-file availability and displays available, downloading, missing and unaired episodes.
4. Choose either **Find season packs** or **View episodes**.
5. Season packs are searched interactively through Sonarr and displayed with actual size, quality, source, codec, seeders and indexer metadata.
6. Missing episodes can be searched independently with the same release-selection pattern.
7. MediaHub rejects season packs larger than the configured season limit and episode releases larger than the episode limit. Defaults are 10 GB and 1 GB respectively.
8. Eligible selections use opaque expiring release tokens; Sonarr performs the actual grab and remains responsible for qBittorrent/import handling.
9. An episode is only marked Available once Sonarr reports an imported episode file.
10. After an individual release is selected, MediaHub returns to the parent season list so the next missing episode can be selected.

**Request entire series** remains available as an advanced secondary action for users who deliberately want Sonarr to search the full show. It is no longer the dominant TV action.

## TV download size policy

Administrators can configure:

- Maximum TV season-pack size — default `10 GB`
- Maximum TV individual-episode size — default `1 GB`

MediaHub evaluates exact release byte counts from Sonarr and enforces the limits server-side. Oversize releases are visible with rejection reasons but cannot be selected through the normal workflow.

## TV acquisition architecture

```text
TMDb
  ↓
TV Show
  ↓
Season
  ├── Season pack search
  │       ↓
  │   release selection
  │       ↓
  │     Sonarr
  │
  └── Episodes
          ↓
      episode search
          ↓
      release selection
          ↓
        Sonarr
          ↓
      qBittorrent
          ↓
      Sonarr import
          ↓
       Available
```

Sonarr remains authoritative for series/episode identity and imported episode-file availability. MediaHub does not bypass Sonarr with arbitrary torrent URLs.

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

After Sonarr connects, configure its TV root folder and quality profile. The v0.11 TV workflow uses Sonarr's interactive release API for deliberate season/episode selection; the legacy whole-series action still uses Sonarr's native automatic series search when explicitly chosen.
