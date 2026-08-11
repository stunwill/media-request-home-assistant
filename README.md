# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress access
- Standalone MediaHub login for access without a Home Assistant account
- Administrator user management, password resets, account disabling, and role assignment
- Per-user request history and roles
- Automatic request approval
- TMDb movie discovery, search, posters, details, cast, ratings, and trailers
- Automatic movie requests using 1080p, maximum-size, minimum-seeder, and Radarr acceptance rules
- Interactive release selection with IPTorrents results supplied through Prowlarr and Radarr
- Radarr movie creation, interactive search, and release submission
- Radarr and qBittorrent download and library status
- Storage-space protection and automatic rejection
- Append-only audit trail
- Smart recommendations

## Project status

MediaHub is in active early development. Version `0.6.3-dev` improves completed-import reconciliation, live download status, seeding visibility, and administrator diagnostics for Radarr hardlinks and qBittorrent paths. Television discovery and Sonarr submission remain planned.

## Movie request workflow

1. Browse popular, now-playing, top-rated, or upcoming movies from TMDb, or search by title.
2. Open a movie to view its synopsis, rating, cast, runtime, and trailer.
3. Choose **Request best release** for automatic selection, or **Choose a release** to inspect live indexer results.
4. MediaHub adds the title to Radarr with automatic search disabled.
5. Radarr performs an interactive search through Prowlarr. Prowlarr handles IPTorrents authentication.
6. MediaHub applies the selected 1080p, size, seeder, storage, and Radarr acceptance rules.
7. Radarr sends the approved release to qBittorrent and imports it when complete.
8. MediaHub displays queued, downloading, processing, failed, and available status.

The Downloads view refreshes automatically while it is open. After Radarr imports a movie, MediaHub shows it as available even if the item has already left Radarr's queue. When qBittorrent still retains the torrent data for seeding, MediaHub reports that state without implying that the library file is a second full copy.

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

After Radarr connects, choose its movie root folder and quality profile on the Setup screen. Leaving either value on **Automatic** uses Radarr's first available option. MediaHub adds a movie without immediately searching, which allows the release rules and manual picker to run before any download starts.
