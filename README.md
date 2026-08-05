# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress access
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

MediaHub is in active early development. Version `0.5.0-dev` delivers the first complete movie workflow. Television discovery and Sonarr submission remain planned.

## Movie request workflow

1. Browse popular, now-playing, top-rated, or upcoming movies from TMDb, or search by title.
2. Open a movie to view its synopsis, rating, cast, runtime, and trailer.
3. Choose **Request best release** for automatic selection, or **Choose a release** to inspect live indexer results.
4. MediaHub adds the title to Radarr with automatic search disabled.
5. Radarr performs an interactive search through Prowlarr. Prowlarr handles IPTorrents authentication.
6. MediaHub applies the selected 1080p, size, seeder, storage, and Radarr acceptance rules.
7. Radarr sends the approved release to qBittorrent and imports it when complete.
8. MediaHub displays queued, downloading, processing, failed, and available status.

IPTorrents credentials, cookies, passkeys, and download URLs are never stored by MediaHub or returned to the browser. Configure the IPTorrents indexer directly in Prowlarr.

Movie metadata and imagery are provided by TMDb. MediaHub includes the required TMDb attribution and is not endorsed or certified by TMDb.

## Integration connection checks

Configure credentials through the MediaHub setup wizard or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent through their supported APIs at `GET /api/integrations/status`. The response reports connection state and service version information without exposing API keys, usernames, passwords, or upstream response bodies.

## Setup wizard

Open MediaHub from the Home Assistant sidebar as an administrator. The setup wizard uses the Supervisor API to detect installed Prowlarr, Radarr, Sonarr, and qBittorrent apps and proposes their internal Home Assistant URLs. TMDb remains an external metadata service and requires its own API key.

Credentials entered in the wizard are stored in MediaHub's private `/data/mediahub-settings.json` file with owner-only permissions. Existing Home Assistant app options remain supported and act as base configuration, while wizard values override only the fields saved through MediaHub. Setup responses expose only URLs, usernames, and boolean credential-present flags.

The discovery API requires the `SUPERVISOR_TOKEN` supplied by Home Assistant. When MediaHub runs outside Home Assistant for development, discovery reports itself unavailable without preventing manual configuration.

## Users and roles

MediaHub trusts Home Assistant Ingress for authentication and links each request to the signed-in Home Assistant user using the documented `X-Remote-User-Id`, `X-Remote-User-Name`, and `X-Remote-User-Display-Name` headers. Requests without an Ingress identity are rejected.

The first authenticated MediaHub user is assigned the `admin` role. Later users start as `requester` until a MediaHub administrator changes their role. Administrators can manage integrations, audit history, and roles. Managers can view household requests and operational status. Requesters can create requests and view only their own request history.

The Home Assistant sidebar panel remains restricted to Home Assistant administrators during this bootstrap stage. A later onboarding change can open the panel to household users after an administrator has been established, without risking a first-visit role takeover.

## Radarr request settings

After Radarr connects, choose its movie root folder and quality profile on the Setup screen. Leaving either value on **Automatic** uses Radarr's first available option. MediaHub adds a movie without immediately searching, which allows the release rules and manual picker to run before any download starts.
