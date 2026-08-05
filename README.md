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

Configure credentials in the Home Assistant add-on options. MediaHub validates TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent through their supported APIs at `GET /api/integrations/status`. The response reports connection state and service version information without exposing API keys, usernames, passwords, or upstream response bodies.
