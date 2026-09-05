# MediaHub Roadmap

## v0.9.0 - Plex Library Intelligence

Status: Delivered

### Features
- [x] Recognise movies already available in Plex.
- [x] Show Plex availability in shared Browse and Downloads movie details.
- [x] Provide safe Watch in Plex links for confident matches.
- [x] Protect against duplicate requests for exact Plex matches.

## v0.10.0 - Television Requests and Sonarr Workflow

Status: Delivered

### Features
- [x] Add separate Movies and TV Shows Browse modes with independent catalogue state.
- [x] Add TMDb television discovery, search, filters, rich TV-series details and season metadata.
- [x] Add request lifecycle support for entire series and selected seasons.
- [x] Add Downloads/library visibility for TV content.

## v0.11.0 - TV Release Selection & Size-Aware Downloads

Status: Delivered

## v0.12.0 - Admin Setup Presets

Status: Delivered

## v0.13.0 - Release Identity, Mobile UX & Live Downloads

Status: Delivered

## v0.14.0 - Mobile UX Completion

Status: Delivered

### Features
- [x] Replace the temporary mobile filter toggle with a staged bottom-sheet flow and active-filter count.
- [x] Restore predictable Browse/detail scroll state across Movie/TV and nested release navigation.
- [x] Make household Movie presets read-only in requester release workflows.
- [x] Add full-screen mobile detail/release viewport ownership with safe-area-aware navigation behaviour.

### UX / Quality
- [x] Compact mobile chrome and make collection chips horizontally accessible at narrow widths.
- [x] Make structured detail skeletons the first meaningful loading state and reduce layout shift.
- [x] Add horizontal cast presentation, responsive Setup/Users handling and reduced-motion support.
- [x] Suspend bottom navigation during full-screen modal and iOS keyboard states.
- [x] Preserve automatic Downloads polling without expanding into Live Downloads 2.0.

### Testing
- [x] Add regression coverage for mobile filters, search ownership, modal viewport state and safe areas.
- [x] Add regression coverage preventing requester Movie policy controls from reappearing.
- [x] Complete full-suite and post-merge CI with all checks green.

## v0.14.1 - Home Assistant Ingress Freeze Correction

Status: Delivered

### Corrective scope
- [x] Harden v0.14 mobile bootstrap against missing/late DOM elements.
- [x] Remove unnecessary requester-side preset bootstrap work from initial page load.
- [x] Throttle mutation reconciliation to animation frames.
- [x] Preserve v0.14 mobile behaviour and server-side household preset authority.
- [x] Complete full-suite CI and post-merge verification.

## v0.14.2 - Download Presets & Release UX Corrections

Status: In Progress

### Corrective scope
- [x] Restore the administrator Download Presets UI to the deployed mobile/Home Assistant entrypoint.
- [x] Unify Movie and TV household policy under one administrator-managed Setup surface.
- [x] Expose Movie resolution, maximum size, minimum seeders and recent-release fallback settings.
- [x] Expose TV resolution, season-pack size, episode size and minimum seeder settings.
- [x] Remove the competing standalone TV Downloads UI while preserving safe legacy migration.
- [x] Prevent requester payloads from overriding server-side household Movie policy.
- [x] Classify MediaHub policy, identity, Radarr/Sonarr, library/upgrade and release-availability exclusions separately.
- [x] Replace the giant mobile rejection paragraph with a compact structured summary and meaningful unavailable-release labels.
- [x] Correct Browse release-selection context so absent request metadata is omitted rather than fabricated.
- [x] Keep BEST MATCH limited to genuinely eligible releases.

### Regression protection
- [x] Preserve The Dog Stars identity exclusions and Buffalo Soldiers ±1-year tolerance.
- [x] Add Goosebumps regression coverage for MediaHub-policy-pass plus Radarr-cutoff rejection.
- [x] Preserve opaque token, duplicate protection, Watch for release and recent-release fallback boundaries.
- [x] Complete the full GitHub Actions suite with all required checks green.

## Future

### Live Downloads 2.0
- Richer transferred/total progress, speed and ETA where reliable.
- Explicit Queued → Downloading → Processing/Importing → Available lifecycle.
- Active / Waiting / Recently Completed information hierarchy.

### Request → Download Continuity
- Rich Sent to Radarr/Sonarr confirmation.
- Stable request identity and View download deep link.
- Focus/highlight the exact request after acquisition.

### Frontend Performance & State
- Remaining profiling-driven request/render optimisations.

### Plex TV Library Intelligence
- Plex TV-library matching and safe TV deep links.

### Notifications & Release Lifecycle
- Watched-release, download-complete and library-available notifications.

### Recommendation Intelligence
- Household recommendations using request/library history and explainable metadata signals.
