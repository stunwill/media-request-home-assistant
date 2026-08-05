# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Planned capabilities

- Home Assistant Ingress access
- Per-user request history and roles
- Automatic request approval
- Movie and TV discovery
- Search by title, genre, year, rating, and cast
- Radarr and Sonarr integration
- qBittorrent download status
- Storage-space protection and automatic rejection
- Append-only audit trail
- Smart recommendations

## Project status

MediaHub is in early development. The first release will establish the Home Assistant add-on structure, backend service, frontend shell, configuration model, storage safeguards, and auditing foundation.

## Integration connection checks

Configure credentials through the MediaHub setup wizard or Home Assistant app options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent through their supported APIs at `GET /api/integrations/status`. The response reports connection state and service version information without exposing API keys, usernames, passwords, or upstream response bodies.

## Setup wizard

Open MediaHub from the Home Assistant sidebar as an administrator. The setup wizard uses the Supervisor API to detect installed Prowlarr, Radarr, Sonarr, and qBittorrent apps and proposes their internal Home Assistant URLs. TMDb remains an external metadata service and requires its own API key.

Credentials entered in the wizard are stored in MediaHub's private `/data/mediahub-settings.json` file with owner-only permissions. Existing Home Assistant app options remain supported and act as base configuration, while wizard values override only the fields saved through MediaHub. Setup responses expose only URLs, usernames, and boolean credential-present flags.

The discovery API requires the `SUPERVISOR_TOKEN` supplied by Home Assistant. When MediaHub runs outside Home Assistant for development, discovery reports itself unavailable without preventing manual configuration.
