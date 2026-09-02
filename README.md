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
- Administrator-managed household presets for catalogue language and Movie/TV release policy
- Release-aware movie lifecycle handling for announced, theatrical, digital, physical, and uncertain availability states
- Persisted **Watch for release** workflow with lightweight background checking
- Automatic movie requests using administrator-defined 720p/1080p, maximum-size and minimum-seeder rules
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

MediaHub is in active development. The current development version is `0.12.0-dev`, focused on administrator-managed Setup presets while preserving the Movie, TV, Plex, Radarr, Sonarr, Prowlarr, qBittorrent and infinite-scroll workflows delivered previously.

## Setup: Service Connections and Presets

Setup is administrator-only and is organised into two concerns:

### Service Connections

Configure TMDb, Prowlarr, Radarr, Sonarr, qBittorrent and Plex connectivity. Credentials remain private and secret values are never returned to the browser after they are saved.

### Presets

Presets are global household rules. Requesters and managers use them automatically but cannot edit them.

Default discovery policy:

- Catalogue language: **English only**

Default Movie policy:

- Allowed resolutions: **1080p and 720p**
- Maximum release size: **3 GB**
- Minimum seeders: **1**
- Recent-release low-quality fallback: **enabled**
- Recent-release window: **365 days**

Default TV policy:

- Allowed resolutions: **1080p and 720p**
- Maximum season pack: **10 GB**
- Maximum episode: **1 GB**
- Minimum seeders: **1**

Administrators can change these values or use **Reset to defaults**. New searches apply the saved rules immediately. Existing v0.11 TV-size settings remain compatible and are used as an upgrade source until the new preset set is saved.

Security controls are intentionally not presets. Duplicate protection, opaque release tokens, credential redaction, authentication/roles and safe external-link rules cannot be disabled from Setup.

## Repository metadata contract

MediaHub keeps machine-readable project/release metadata in predictable locations so DevHub and maintainers can determine repository state without inferring it from implementation details:

- `ROADMAP.md` — delivered, in-progress/planned and future phases using semantic-version headings and explicit `Status:` values.
- `CHANGELOG.md` — detailed repository/project release history.
- `mediahub/CHANGELOG.md` — concise Home Assistant user-facing release notes beside `mediahub/config.yaml`.
- `mediahub/config.yaml` — Home Assistant add-on version and manifest metadata.
- `mediahub/app/preset_ui.py` — current deployed application entrypoint; `/api/health` reports the same application version.
- Git tags/releases — actual published releases use semantic tags in the form `vX.Y.Z` and meaningful GitHub Release notes.
- Pull requests and GitHub Actions remain the authoritative sources for proposed changes and CI status.

Product release PRs must update the manifest/application version, both changelogs, roadmap status, and release metadata together.

## Browse and infinite scrolling

Browse defaults to **Movies** and provides a clear **Movies / TV Shows** selector. Each media type retains independent collection, search/filter and pagination state. Movie results never mix with TV results.

Both media types use an `IntersectionObserver` sentinel near the end of the grid. MediaHub requests one additional TMDb page at a time, appends unique TMDb IDs, prevents concurrent duplicate page loads, stops at the final page, and keeps already-loaded results visible if a later request fails.

The default **English only** preset filters explicitly non-English Movie/TV catalogue results using TMDb original-language metadata. An administrator may change the catalogue preset to allow any original language.

## Movie request workflow

1. Browse or search TMDb movies, including actor discovery.
2. Open the shared rich movie-details view.
3. For upcoming titles, choose **Watch for release** or **Search anyway**.
4. For requestable titles, choose **Request best release** or **Choose a release**.
5. MediaHub applies the administrator's Movie presets for allowed resolution, maximum size, minimum seeders and recent-release fallback.
6. MediaHub uses Radarr as the movie/request authority and Prowlarr as the indexer boundary.
7. Approved releases are handed to Radarr and qBittorrent.
8. MediaHub reconciles queued, downloading, processing and available state.
9. When Plex is configured, MediaHub independently identifies confidently matched Plex movie availability and can show a safe **Watch in Plex** action.

Requester-editable Movie size/seeder/quality controls are no longer authoritative; household policy is managed centrally through Setup Presets.

## TV request workflow

The normal TV acquisition workflow is deliberately season-first:

1. Select **TV Shows** in Browse and open a series.
2. Choose a season using **View season**.
3. MediaHub asks Sonarr for episode-file availability and displays available, downloading, missing and unaired episodes.
4. Choose either **Find season packs** or **View episodes**.
5. Season packs are searched interactively through Sonarr and displayed with actual size, quality, source, codec, seeders and indexer metadata.
6. Missing episodes can be searched independently with the same release-selection pattern.
7. MediaHub applies the administrator's TV resolution, size and minimum-seeder presets.
8. Eligible selections use opaque expiring release tokens; Sonarr performs the actual grab and remains responsible for qBittorrent/import handling.
9. An episode is only marked Available once Sonarr reports an imported episode file.
10. After an individual release is selected, MediaHub returns to the parent season list so the next missing episode can be selected.

**Request entire series** remains available as an advanced secondary action for users who deliberately want Sonarr to search the full show.

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

Configure credentials through MediaHub Setup or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr and qBittorrent through their supported APIs. Plex is optional with server-side token handling and sanitised status reporting.

Credentials entered in Setup are stored in MediaHub's private `/data/mediahub-settings.json` file with owner-only permissions. Secret values remain write-only and are never included in browser responses.

## Users, roles, and external login

MediaHub supports two deliberately separate authentication listeners:

- Home Assistant Ingress on internal port `8099` accepts only the documented Home Assistant identity.
- The external interface on port `8100` accepts only MediaHub username/password sessions and ignores Home Assistant identity headers.

The first authenticated MediaHub user becomes administrator. Administrators can manage integrations, presets, audit history and users; managers can view household operations; requesters can create requests and view their own history.

Public self-registration is disabled. Passwords are salted `scrypt` hashes, sessions are hashed and time-limited, and state-changing external requests require CSRF protection.
