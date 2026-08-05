# MediaHub architecture

## Purpose

MediaHub provides a family-friendly Home Assistant Ingress interface for discovering, requesting, and tracking movies and television while keeping automation, download-client credentials, and indexer details hidden from requesters.

## Initial components

1. **Home Assistant add-on packaging**
   - Home Assistant Ingress
   - `/media` and `/share` mappings
   - Add-on options for storage and integrations

2. **FastAPI backend**
   - Request lifecycle API
   - Storage-space validation and reservation accounting
   - Duplicate detection
   - Audit events
   - Future adapters for TMDb, Radarr, Sonarr, and qBittorrent

3. **Integration boundary**
   - Typed configuration for TMDb, Prowlarr, Radarr, Sonarr, and qBittorrent
   - Vendor-supported health and system endpoints only
   - Bounded timeouts and sanitised failure responses
   - No direct private-tracker access

4. **SQLite persistence**
   - Requests
   - Append-only audit events
   - Future users, roles, media cache, recommendations, and integration state

## Initial request lifecycle

```text
requested
  -> approved automatically
  -> searching
  -> queued
  -> downloading
  -> processing
  -> available
```

Requests may also transition to rejected, failed, cancelled, or deleted.

## Storage protection

A request is accepted only when projected free space remains above the protected reserve after accounting for:

- existing active reservations
- estimated download size multiplied by the reservation multiplier
- the configured safety margin
- the permanent minimum-free-space threshold

Default values:

- Minimum free space: 50 GB
- Safety margin: 10 GB
- Reservation multiplier: 1.5

No automatic media deletion is permitted in v0.1.

## Audit model

Every request and administrative action creates an append-only event containing:

- timestamp
- actor ID and display name
- action
- request ID where applicable
- structured JSON details

Credentials and secrets must never be recorded.

## Smart recommendations roadmap

Smart recommendations will initially use metadata signals rather than generative AI:

- genres and keywords from previously requested or available titles
- cast and crew overlap
- TMDb recommendation and similarity data
- popularity and rating thresholds
- exclusions for already available, rejected, or disliked titles

Later versions can add per-user weighting, explicit likes/dislikes, household profiles, and explainable recommendation reasons.
