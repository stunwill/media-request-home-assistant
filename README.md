# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress and standalone MediaHub login
- Administrator user management and household presets
- Separate Movies and TV Shows Browse modes with automatic infinite scrolling
- TMDb discovery/search/details, actor discovery and release lifecycle awareness
- Deterministic release identity validation before download eligibility
- Interactive Movie releases through Radarr/Prowlarr and TV releases through Sonarr
- Opaque release-selection tokens and duplicate protection
- qBittorrent/Radarr/Sonarr reconciliation and live Downloads polling
- Optional Plex Movie-library awareness and safe Watch in Plex links

## Project status

MediaHub is in active development. The current development version is `0.14.0-dev`, focused on **Mobile UX Completion** for iPhone and Home Assistant ingress while preserving release identity, household presets and the existing media-service boundaries.

## Release identity architecture

Release identity is validated before quality, size, seeder and ranking rules:

```text
Search provider / Radarr / Sonarr
  ↓
Structured metadata
  ↓
Media-type validation
  ↓
Title identity validation
  ↓
Year / season / episode validation
  ↓
Explainable match confidence
  ↓
Admin quality/size/seeder presets
  ↓
Deterministic ranking
  ↓
Opaque release token
  ↓
Radarr / Sonarr
  ↓
qBittorrent
  ↓
Import
  ↓
Available
```

A release that fails identity validation is never made downloadable merely because it is 1080p, small enough or has sufficient seeders. Rejected identity matches do not receive usable release tokens.

### Movie matching

Movie matching normalises punctuation, dots, underscores, casing and common release separators. It rejects obvious TV episode/season patterns such as `S01E10`, `1x10` and season releases. Strong title matches accept a one-year metadata difference where appropriate, so `Buffalo.Soldiers.2001...` can remain eligible for TMDb's `Buffalo Soldiers (2002)` when all other identity evidence is strong. The Dog Stars false-positive cases remain protected.

### TV matching

TV release validation combines series-title matching with requested season/episode identity. Sonarr structured identity remains stronger evidence than weak title parsing.

## Mobile UX

At narrow Home Assistant/iPhone widths MediaHub prioritises content and owns the mobile viewport more deliberately:

- compact application chrome and collection chips;
- a staged mobile filter sheet with Apply/Clear and active-filter count;
- one debounced search owner with clear-search support;
- structured Movie/TV detail loading with stable artwork placeholders;
- Browse and detail scroll preservation across nested navigation;
- horizontal cast presentation;
- compact release cards with BEST MATCH and collapsed unavailable results;
- requester release rules are read-only household presets, never editable request overrides;
- full-screen mobile details/release surfaces suspend bottom navigation so it cannot cover content;
- safe-area-aware bottom spacing, dynamic viewport handling and reduced-motion support;
- responsive Setup and Users layouts.

## Live Downloads

While Downloads is active, MediaHub refreshes progress automatically and suspends polling when the page is hidden. Manual Refresh remains available as a recovery control. v0.14 does not introduce the planned richer speed/ETA/lifecycle redesign.

## Setup: Service Connections and Presets

Setup remains administrator-only and is organised into **Service Connections** and **Presets**. Household presets control catalogue language, Movie resolution/size/seeders/recent-release fallback and TV resolution/season size/episode size/seeders. Requesters and managers cannot alter these rules.

Security controls are intentionally not presets: duplicate protection, opaque release tokens, credential redaction, authentication/roles and safe external-link rules cannot be disabled from Setup.

## Browse and Movie workflow

Browse keeps independent Movie/TV catalogue state and automatic infinite scrolling. Movie search preserves actor/person-ID discovery. For Movie requests MediaHub applies release identity first, then administrator presets, then deterministic ranking before issuing a token or sending a release to Radarr.

Release-aware titles retain **Watch for release** and manual **Search anyway** behaviour.

## TV workflow

The normal TV workflow remains season-first:

1. Open a TV show.
2. Select a season.
3. Choose **Find season packs** or **View episodes**.
4. Inspect actual Sonarr releases and sizes.
5. MediaHub validates series/season/episode identity before applying TV presets.
6. Eligible selections use opaque tokens and Sonarr performs the grab/import flow.
7. Sonarr episode-file state is authoritative for completion.

## Integration boundaries

- TMDb — discovery and metadata
- Radarr — Movie library/request authority
- Sonarr — TV series/episode authority
- Prowlarr — configured indexer boundary
- qBittorrent — downstream download client
- Plex — optional Movie library awareness

MediaHub does not treat qBittorrent completed-download staging folders as the authoritative library.

## Repository metadata contract

DevHub/maintainer metadata lives in predictable locations:

- `ROADMAP.md`
- `CHANGELOG.md`
- `mediahub/CHANGELOG.md`
- `mediahub/config.yaml`
- deployed FastAPI entrypoint and `/api/health`
- GitHub PRs/Actions/tags/releases

The v0.14 deployed entrypoint is `mediahub/app/mobile_ux_ui.py` (`app.mobile_ux_ui:app`).
