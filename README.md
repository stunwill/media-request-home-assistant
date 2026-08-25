# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress access
- Standalone MediaHub login for access without a Home Assistant account
- Administrator user management, password resets, account disabling, and role assignment
- Per-user request history and roles
- Automatic request approval
- TMDb movie discovery, search, pagination, genre, release-year and rating-range filters, posters, details, cast, ratings, trailers, and regional release dates
- Release-aware movie lifecycle handling for announced, theatrical, digital, physical, and uncertain availability states
- Persisted **Watch for release** workflow with lightweight background checking
- Automatic movie requests using selectable 720p/1080p, maximum-size, minimum-seeder, and Radarr acceptance rules
- Interactive release selection with IPTorrents results supplied through Prowlarr and Radarr
- Release-search diagnostics that distinguish no indexer results from all results being filtered out
- Radarr movie creation, interactive search, and release submission
- Radarr and qBittorrent download and library status
- Storage-space protection and automatic rejection
- Append-only audit trail
- Smart recommendations

## Project status

MediaHub is in active early development. Version `0.7.0-dev` adds release-aware movie requests and upcoming-title handling while preserving actor search, duplicate prevention, recent-release quality fallback, CAM/TS support, download reconciliation, user roles, and external login. Television discovery and Sonarr submission remain planned.

## Release-aware movie workflow

MediaHub deliberately separates **metadata availability** from **media availability**. A movie can exist in TMDb and have artwork, cast data, a synopsis, and a trailer while still being months away from a downloadable release.

For movie details, MediaHub loads TMDb regional release-date records and classifies the title into a lifecycle state such as announced, theatrical upcoming, in cinemas, digital upcoming, digital available, physical upcoming, physical available, or released with uncertain availability. The default region is Australia (`AU`) unless a configurable application region is introduced later.

Theatrical, digital, and physical dates are separate milestones. For example, an Australian theatrical date does not imply that a WEB-DL should exist. A trailer also does not imply downloadable media availability.

For clearly pre-theatrical movies, the preferred action is **Watch for release**. MediaHub stores the watch in SQLite and schedules conservative background checks rather than repeatedly querying indexers. Far-future movies are checked infrequently, checks become more frequent near theatrical or known digital milestones, and titles that have reached a reasonable release window can be searched more actively. The scheduler groups due watches by TMDb movie so multiple users watching the same title do not cause duplicate upstream searches.

Users retain control through **Search anyway**. This manual override immediately uses the established release-search path for unusual early releases, festival distribution, screeners, incomplete metadata, and region-specific exceptions.

When a search finds nothing, MediaHub distinguishes three cases:

1. An upcoming title where no release is expected yet.
2. A released title where configured sources returned no matching releases.
3. Releases were returned but every result was rejected by size, seeder, quality, Radarr, or related policy rules.

Existing recent-release behaviour remains downstream of lifecycle awareness. MediaHub continues to prefer 720p/1080p and can expose configured CAM, telesync, telecine, or screener fallbacks for genuinely recent titles when appropriate. Lifecycle awareness prevents the current-year rule from being treated as evidence that a pre-theatrical CAM/TS release should already exist.

## Movie request workflow

1. Browse popular, now-playing, top-rated, or upcoming movies from TMDb, load additional result pages, filter by genre, release-year and rating range, or search by title or actor.
2. Open a movie to view its synopsis, rating, cast, runtime, trailer, and release lifecycle.
3. For an upcoming movie, choose **Watch for release** or manually **Search anyway**.
4. For a movie in a normal release window, choose **Request best release** or **Choose a release**.
5. MediaHub adds requestable titles to Radarr with automatic search disabled.
6. Radarr performs an interactive search through Prowlarr. Prowlarr handles IPTorrents authentication.
7. MediaHub applies the selected 720p/1080p, size, seeder, storage, lifecycle, and Radarr acceptance rules.
8. Radarr sends the approved release to qBittorrent and imports it when complete.
9. MediaHub displays queued, downloading, processing, failed, and available status.

The Downloads view refreshes automatically while it is open. Watched upcoming movies remain separate from active downloads until they enter the normal request lifecycle. After Radarr imports a movie, MediaHub shows it as available even if the item has already left Radarr's queue. When qBittorrent still retains torrent data for seeding, MediaHub reports that state without implying that the library file is a second full copy.

IPTorrents credentials, cookies, passkeys, and download URLs are never stored by MediaHub or returned to the browser. Configure the IPTorrents indexer directly in Prowlarr.

Movie metadata and imagery are provided by TMDb. MediaHub includes the required TMDb attribution and is not endorsed or certified by TMDb.

## Integration connection checks

Configure credentials through the MediaHub setup wizard or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent through their supported APIs at `GET /api/integrations/status`. Prowlarr validation uses its `/api/v1/system/status` endpoint, while Radarr and Sonarr use `/api/v3/system/status`. The response and Setup page report connection state, service version, and sanitised failures without exposing API keys, usernames, passwords, or upstream response bodies.

## Setup wizard

Open MediaHub from the Home Assistant sidebar as an administrator. The setup wizard uses the Supervisor API to detect installed Prowlarr, Radarr, Sonarr, and qBittorrent apps and proposes their internal Home Assistant URLs. TMDb remains an external metadata service and requires its own API key.

Credentials entered in the wizard are stored in MediaHub's private `/data/mediahub-settings.json` file with owner-only permissions. Existing Home Assistant app options remain supported and act as base configuration, while wizard values override only the fields saved through MediaHub. Setup responses expose only URLs, usernames, and boolean credential-present flags.

qBittorrent can use either its Web UI username and password or a qBittorrent 5.2+ API key. Password authentication sends qBittorrent's required matching `Origin` and `Referer` headers and verifies the authenticated application-version endpoint instead of relying on one exact login response body. API keys use the documented bearer-token header and are preferred when available.

After Radarr and qBittorrent connect, Setup displays a Download workflow diagnostic. It verifies Radarr's hardlink setting and checks that qBittorrent's completed, incomplete, and `radarr` category paths are not inside the Radarr movie library. The intended design keeps downloads under `/media/completed` and `/media/incomplete`, imports organised movies into `/media/Movies`, and lets qBittorrent continue seeding the hardlinked download data.

The discovery API requires the `SUPERVISOR_TOKEN` supplied by Home Assistant. When MediaHub runs outside Home Assistant for development, discovery reports itself unavailable without preventing manual configuration.

## Users, roles, and external login

MediaHub supports two deliberately separate authentication listeners:

- Home Assistant Ingress on internal port `8099` accepts only the documented Home Assistant `X-Remote-User-*` identity.
- The external interface on port `8100` ignores Home Assistant identity headers and accepts only MediaHub username/password sessions.

This separation prevents a caller on the exposed interface from forging a Home Assistant user header. Do not expose the Ingress listener.

The first authenticated MediaHub user is assigned the `admin` role. Later users start as `requester` until a MediaHub administrator changes their role. Administrators can manage integrations, audit history, and roles. Managers can view household requests and operational status. Requesters can create requests and view only their own request history.

Public self-registration is disabled. An administrator opens MediaHub through Home Assistant and uses the **Users** page to create a MediaHub account, assign its role, disable or enable it, and reset its password. Passwords require at least 12 characters and are stored only as salted `scrypt` hashes. Password resets and account disabling revoke existing sessions.

Sessions expire after seven days and use `HttpOnly`, `SameSite=Strict` cookies. HTTPS routes receive `Secure` cookies. State-changing requests from password sessions also require a per-session CSRF token. Failed logins are limited to five attempts per username and connection source within 15 minutes.

Port `8100` makes the authenticated interface available on the local network. A public address still requires an HTTPS reverse proxy or tunnel. Follow [External access](docs/EXTERNAL_ACCESS.md) and expose only port `8100`, never Home Assistant Ingress, Prowlarr, Radarr, Sonarr, or qBittorrent.

## Radarr request settings

After Radarr connects, choose its movie root folder and quality profile on the Setup screen. Leaving either value on **Automatic** uses Radarr's first available option. MediaHub adds a movie without immediately searching, which allows lifecycle awareness, release rules, and the manual picker to run before any download starts.
