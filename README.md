# MediaHub

MediaHub is a Home Assistant add-on for searching, requesting, tracking, and managing movies and TV shows through a family-friendly interface.

## Current capabilities

- Home Assistant Ingress and standalone MediaHub login
- Administrator user management and household Download Presets
- Separate Movies and TV Shows Browse modes with automatic infinite scrolling
- TMDb discovery/search/details, actor discovery and release lifecycle awareness
- Deterministic release identity validation before download eligibility
- Interactive Movie releases through Radarr/Prowlarr and TV releases through Sonarr
- Opaque release-selection tokens and duplicate protection
- qBittorrent/Radarr/Sonarr reconciliation and live Downloads polling
- Optional Plex Movie-library awareness and safe Watch in Plex links

## Project status

MediaHub is in active development. The current development version is `0.14.2-dev`, focused on **Download Presets & Release UX Corrections**. This corrective release restores the administrator Download Presets UI in the deployed Home Assistant entrypoint, removes the competing standalone TV policy UI, makes Movie and TV household policy one source of truth, distinguishes MediaHub policy from Radarr/Sonarr decisions, and corrects Browse release-selection context metadata.

## Release and policy architecture

Release identity remains the safety boundary. Household settings are administrator-managed, server-enforced policy, not per-request preferences.

```text
Administrator Download Presets
  ↓
Server-side household policy
  ↓
Provider result
  ↓
Media identity validation
  ↓
Title / Movie / TV validation
  ↓
Year / season / episode validation
  ↓
Match confidence
  ↓
Quality / size / seeder eligibility
  ↓
Radarr / Sonarr eligibility and library state
  ↓
Deterministic ranking
  ↓
Opaque release token
  ↓
Acquisition
```

A release that fails identity validation is never made downloadable merely because it is 1080p, small enough or has sufficient seeders. Identity-rejected results do not receive usable release tokens.

MediaHub policy and Radarr/Sonarr policy are deliberately separate. Increasing MediaHub's Movie maximum size, for example from 3 GB to 5 GB, allows MediaHub to consider larger releases, but it does not override a Radarr cutoff, an existing-file decision, an upgrade restriction, or Sonarr's own quality/library rules.

### Movie matching

Movie matching normalises punctuation, dots, underscores, casing and common release separators. It rejects obvious TV episode/season patterns such as `S01E10`, `1x10` and season releases. Strong title matches accept a one-year metadata difference where appropriate, so `Buffalo.Soldiers.2001...` can remain eligible for TMDb's `Buffalo Soldiers (2002)` when all other identity evidence is strong. The Dog Stars false-positive cases remain protected.

### TV matching

TV release validation combines series-title matching with requested season/episode identity. Sonarr structured identity remains stronger evidence than weak title parsing.

## Download Presets

Setup is administrator-only and presents one **Download Presets** section with separate **Movies** and **TV Shows** groups. Persisted values are loaded dynamically.

Movie presets include:

- allowed 1080p / 720p resolutions;
- maximum Movie release size;
- minimum known seeders;
- recent-release lower-quality fallback enablement;
- recent-release fallback window.

TV presets include:

- allowed 1080p / 720p resolutions;
- maximum season-pack size;
- maximum individual-episode size;
- minimum known seeders.

The earlier `tv_downloads` settings remain only as an upgrade compatibility mirror for existing installations. They are not a second user-facing configuration source. Existing TV size values are migrated into Download Presets where required, and legacy API writes are reconciled into the authoritative preset structure.

Requesters and managers cannot edit household Download Presets. Release selection may read a safe policy summary so users can understand the active resolution, size and seeder limits, but submitted request payloads cannot override server-side household policy.

## Release rejection presentation

Unavailable releases expose a structured primary reason instead of a generic `Rejected` state. Reasons are classified as:

- identity mismatch;
- MediaHub household preset;
- Radarr/Sonarr decision;
- library/upgrade state;
- indexer/release availability;
- other.

Each release is counted once in the compact exclusion summary using its deterministic primary category. Identity has the highest precedence so a secondary size or quality reason cannot obscure an unsafe media mismatch. Non-sensitive underlying diagnostics can remain available in details, while credentials, API keys, tokens, torrent URLs and sensitive identifiers are not exposed.

A release can satisfy MediaHub policy and still be unavailable. For example, a 1.60 GB 1080p release with 44 seeders satisfies a 3 GB / 1080p-or-720p / one-seeder household policy. If Radarr reports that an existing or queued quality already meets cutoff, MediaHub presents that as a Radarr/library-state block rather than blaming the 3 GB preset.

## Mobile UX

At narrow Home Assistant/iPhone widths MediaHub prioritises content and owns the mobile viewport deliberately:

- compact application chrome and collection chips;
- a staged mobile filter sheet with Apply/Clear and active-filter count;
- one debounced search owner with clear-search support;
- structured Movie/TV detail loading with stable artwork placeholders;
- Browse and detail scroll preservation across nested navigation;
- horizontal cast presentation;
- compact release cards with BEST MATCH only on genuinely eligible releases;
- unavailable releases collapsed by default with meaningful rejection labels;
- requester release rules shown as read-only household presets, never editable overrides;
- full-screen mobile details/release surfaces suspend bottom navigation so it cannot cover content;
- safe-area-aware bottom spacing, dynamic viewport handling and reduced-motion support;
- responsive Setup and Users layouts with no intended page-level horizontal overflow.

Browse to **Choose a release** is a pre-request workflow. It does not fabricate request metadata. Download/library status, request time, progress, selected release and size are shown only when an actual Downloads request context exists. Missing dates are omitted instead of displaying `Invalid Date`, and unknown progress/size are kept distinct from genuine zero values.

## Live Downloads

While Downloads is active, MediaHub refreshes progress automatically and suspends polling when the page is hidden. Manual Refresh remains available as a recovery control. v0.14.2 does not introduce the planned Live Downloads 2.0 redesign.

## Setup

Setup is organised into **Service Connections** and **Download Presets**. Service credentials remain separate from policy, and resetting Download Presets does not reset service connections, credentials or users.

Security controls are intentionally not presets: duplicate protection, opaque release tokens, credential redaction, authentication/roles and safe external-link rules cannot be disabled from Setup.

## Browse and Movie workflow

Browse keeps independent Movie/TV catalogue state and automatic infinite scrolling. Movie search preserves actor/person-ID discovery. For Movie requests MediaHub validates release identity, applies household policy, honours Radarr eligibility/library decisions, then ranks only genuinely eligible releases before issuing a token or sending a release to Radarr.

Release-aware titles retain **Watch for release** and manual **Search anyway** behaviour. **Search again** refreshes candidates using current household presets. It does not create a request, change Radarr profiles, bypass identity validation or reset presets.

## TV workflow

The normal TV workflow remains season-first:

1. Open a TV show.
2. Select a season.
3. Choose **Find season packs** or **View episodes**.
4. Inspect actual Sonarr releases and sizes.
5. MediaHub validates series/season/episode identity before applying TV presets.
6. Sonarr eligibility and library state are evaluated separately from MediaHub presets.
7. Eligible selections use opaque tokens and Sonarr performs the grab/import flow.
8. Sonarr episode-file state is authoritative for completion.

## Integration boundaries

- TMDb: discovery and metadata
- Radarr: Movie library/request authority and quality/upgrade decisions
- Sonarr: TV series/episode authority and quality/upgrade decisions
- Prowlarr: configured indexer boundary
- qBittorrent: downstream download client
- Plex: optional Movie library awareness

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
