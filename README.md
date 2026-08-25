# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress access
- Standalone MediaHub login for access without a Home Assistant account
- Administrator user management, password resets, account disabling, and role assignment
- Per-user request history and roles
- Automatic request approval
- TMDb movie discovery, search, pagination, genre, release-year and rating-range filters, posters, rich details, cast, director, ratings links, trailers, and regional release dates
- Stable TMDb person-ID actor discovery from clickable cast members
- Shared rich movie details for Browse and Downloads, with download/library context replacing request controls for already requested titles
- Release-aware movie lifecycle handling for announced, theatrical, digital, physical, and uncertain availability states
- Persisted **Watch for release** workflow with lightweight background checking
- Automatic movie requests using selectable 720p/1080p, maximum-size, minimum-seeder, and Radarr acceptance rules
- Interactive release selection with IPTorrents results supplied through Prowlarr and Radarr
- Release-search diagnostics that distinguish no indexer results from all results being filtered out
- Radarr movie creation, interactive search, and release submission
- Radarr and qBittorrent download and library status
- Storage-space protection and automatic rejection
- Append-only audit trail

## Project status

MediaHub is in active early development. Version `0.8.0-dev` adds richer movie discovery and downloaded-library details while preserving the v0.7.0 release lifecycle, actor text search, duplicate prevention, recent-release quality fallback, CAM/TS support, download reconciliation, user roles, and external login. Television discovery and Sonarr submission remain planned.

## Rich movie details

Browse and Downloads now use one shared movie-details presentation. Movie metadata includes TMDb title, artwork, synopsis, runtime, genres, Australian release lifecycle information, available Australian certification, director, primary cast, trailer, TMDb rating, and safe outbound IMDb/TMDb links where identifiers exist.

Cast entries retain their TMDb person IDs. Selecting a cast member uses TMDb's `with_cast` discovery path with that stable person ID instead of falling back to name matching, then returns the user to the normal Browse result grid where movies can be opened and requested as usual.

The Downloads view can open the same rich details presentation, but download context deliberately removes **Request best release**, **Choose a release**, **Watch for release**, and **Search anyway**. It adds request owner, request time, current status/progress, selected release title, estimated size, and library availability instead.

Rotten Tomatoes is not scraped. MediaHub currently displays only ratings/review links that can be supported safely from existing metadata. TMDb's score is shown directly; IMDb is linked when TMDb supplies an IMDb ID, but no IMDb score is fabricated because no licensed IMDb ratings feed is configured.

Plex deep linking was investigated for v0.8.0. The current repository has no Plex client, URL, token, or library identity configuration, so MediaHub does not attempt unsafe title-only Plex matching in this release. Plex remains optional future integration work and is not required for Downloads or rich movie details.

## Release-aware movie workflow

MediaHub deliberately separates **metadata availability** from **media availability**. A movie can exist in TMDb and have artwork, cast data, a synopsis, and a trailer while still being months away from a downloadable release.

For movie details, MediaHub loads TMDb regional release-date records and classifies the title into a lifecycle state such as announced, theatrical upcoming, in cinemas, digital upcoming, digital available, physical upcoming, physical available, or released with uncertain availability. The default region is Australia (`AU`) unless a configurable application region is introduced later.

Theatrical, digital, and physical dates are separate milestones. For clearly pre-theatrical movies, the preferred action is **Watch for release**. MediaHub stores the watch in SQLite and schedules conservative background checks rather than repeatedly querying indexers. Users retain control through **Search anyway**.

Existing recent-release behaviour remains downstream of lifecycle awareness. MediaHub continues to prefer 720p/1080p and can expose configured CAM, telesync, telecine, or screener fallbacks for genuinely recent titles when appropriate.

## Movie request workflow

1. Browse popular, now-playing, top-rated, or upcoming movies from TMDb, load additional result pages, filter by genre, release-year and rating range, or search by title or actor.
2. Open a movie to view rich metadata, ratings links, cast, director, runtime, trailer, and release lifecycle.
3. Click a cast member to discover movies by the stable TMDb person ID.
4. For an upcoming movie, choose **Watch for release** or manually **Search anyway**.
5. For a movie in a normal release window, choose **Request best release** or **Choose a release**.
6. MediaHub adds requestable titles to Radarr with automatic search disabled.
7. Radarr performs an interactive search through Prowlarr. Prowlarr handles IPTorrents authentication.
8. MediaHub applies the selected 720p/1080p, size, seeder, storage, lifecycle, and Radarr acceptance rules.
9. Radarr sends the approved release to qBittorrent and imports it when complete.
10. MediaHub displays queued, downloading, processing, failed, and available status, with rich details accessible from Downloads.

IPTorrents credentials, cookies, passkeys, and download URLs are never stored by MediaHub or returned to the browser. Configure the IPTorrents indexer directly in Prowlarr.

Movie metadata and imagery are provided by TMDb. MediaHub includes the required TMDb attribution and is not endorsed or certified by TMDb.

## Integration connection checks

Configure credentials through the MediaHub setup wizard or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent through their supported APIs at `GET /api/integrations/status`. The response and Setup page report connection state, service version, and sanitised failures without exposing API keys, usernames, passwords, or upstream response bodies.

## Users, roles, and external login

MediaHub supports two deliberately separate authentication listeners:

- Home Assistant Ingress on internal port `8099` accepts only the documented Home Assistant `X-Remote-User-*` identity.
- The external interface on port `8100` ignores Home Assistant identity headers and accepts only MediaHub username/password sessions.

This separation prevents a caller on the exposed interface from forging a Home Assistant user header. Do not expose the Ingress listener.

The first authenticated MediaHub user is assigned the `admin` role. Later users start as `requester` until a MediaHub administrator changes their role. Administrators can manage integrations, audit history, and roles. Managers can view household requests and operational status. Requesters can create requests and view only their own request history.

Port `8100` makes the authenticated interface available on the local network. A public address still requires an HTTPS reverse proxy or tunnel. Follow [External access](docs/EXTERNAL_ACCESS.md) and expose only port `8100`, never Home Assistant Ingress, Prowlarr, Radarr, Sonarr, or qBittorrent.
