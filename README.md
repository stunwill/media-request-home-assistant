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

MediaHub is in active development. The current development version is `0.13.0-dev`, focused on **Release Identity & Search Accuracy** plus **Mobile UX & Live Downloads**.

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

Movie matching normalises punctuation, dots, underscores, casing and common release separators. It rejects obvious TV episode/season patterns such as `S01E10`, `1x10` and season releases. Strong title matches accept a one-year metadata difference where appropriate, so a release named `Buffalo.Soldiers.2001...` can remain eligible for TMDb's `Buffalo Soldiers (2002)` when all other identity evidence is strong. Larger conflicting years are rejected.

The primary false-positive regression case is **The Dog Stars (2026)**: unrelated releases such as `Stars.on.Mars.S01E10...` and `Krypto.The.Superdog.S01E22...Dog.Stars...` are rejected before normal download policy.

### TV matching

TV release validation combines series-title matching with requested season/episode identity. Sonarr's structured full-season and episode identity remain stronger evidence than weak title parsing. Wrong-series, wrong-season and wrong-episode releases are rejected.

## Mobile UX

At narrow Home Assistant/iPhone widths MediaHub now prioritises catalogue content rather than the large introductory hero. Advanced filters are compacted behind a Filters action, search is debounced, Movie detail loading uses a structured skeleton, release cards are denser, rejected releases are collapsible and the top eligible release is visually marked as **BEST MATCH**.

A mobile bottom navigation provides Browse and Downloads, with Setup available only to administrators. Existing server-side role enforcement remains authoritative.

## Live Downloads

While the Downloads view is active, MediaHub refreshes progress automatically and suspends polling when the page is hidden. Manual Refresh remains available as a fallback. Radarr/Sonarr import state remains authoritative for `Available`; torrent completion alone does not imply library availability.

## Setup: Service Connections and Presets

Setup remains administrator-only and is organised into **Service Connections** and **Presets**. Household presets continue to control catalogue language, Movie resolution/size/seeders/recent-release fallback and TV resolution/season size/episode size/seeders. Requesters and managers cannot alter these rules.

Security controls are intentionally not presets: duplicate protection, opaque release tokens, credential redaction, authentication/roles and safe external-link rules cannot be disabled from Setup.

## Browse and Movie workflow

Browse keeps independent Movie/TV catalogue state and automatic infinite scrolling. Movie search preserves actor/person-ID discovery. For Movie requests MediaHub now applies release identity first, then administrator presets, then deterministic ranking before issuing a token or sending a release to Radarr.

Release-aware titles retain **Watch for release** and manual **Search anyway** behavior. Identity validation remains conservative for cinema-only/pre-digital titles.

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

The v0.13 deployed entrypoint is `mediahub/app/mobile_live_ui.py` (`app.mobile_live_ui:app`).
