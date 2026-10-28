## 0.19.3

- Fix a reproduced BEST MATCH observer loop that froze rendering, Download feedback and navigation after a release button became disabled. Eligibility now stays independent of request processing and one decorator owns the badge.
- Show immediate accessible processing, inline recovery and correlated errors; reject unconfirmed or storage-rejected responses instead of displaying false success.
- Bound movie submission to 22 seconds, cancel obsolete UI work on navigation and fence uncertain outcomes until explicit Downloads review and fresh discovery. Never automatically retry acquisition.
- Add privacy-safe correlation logs and real Chromium/WebKit ingress regressions for touch, scrolling, navigation, timeout, duplicate taps and late responses.
- Preserve household presets, authenticated user-bound exact-release tokens and Radarr/Sonarr/Prowlarr handoffs. Physical iPhone/Home Assistant acceptance and update discovery remain manual.

## 0.19.2

- Include capability-mapped documentary categories for documentary movies, preserving strict movie identity and household presets.
- Reject longer unrelated titles sharing a short title prefix. A one-year difference requires a matching authoritative movie identifier.
- Prioritize canonical queries; bound query paths to 6 seconds within a 12-second discovery window, four concurrent paths and two transient retries. Report incomplete coverage explicitly.
- Preserve complete duplicate observations and distinct size/quality variants; distinguish unknown seeders from confirmed zero.
- Restrict detailed, redacted query and release filtering diagnostics to administrators. Do not cache partial movie searches.
- Retain Birdman aliases, exact cached-release handoff and existing movie/TV acquisition paths. No live IPTorrents verification is claimed.

## [0.19.1] - 2026-10-13

### Fixed
- Birdman short-title releases were discarded twice: preliminary word overlap and final full-title prefix checks. Shared identity validation now accepts grammatical/authoritative aliases with immediate exact years, while rejecting conflicting IDs and TV titles.
- Search official/original/alternative/short titles and a supported identifier using bounded deterministic queries; retain Prowlarr candidates even when Radarr already has eligible results.
- Remove silent first-100 slicing; honor provider page limits, bound pagination/concurrency and report partial coverage or repeated/unsupported pages.
- Use Prowlarr normalized capability categories plus a broad fallback; preserve Movie/TV identity checks and exact byte-based binary-size limits.

### Added
- Expandable safe query/row/duplicate/identity/category/metadata/preset/eligibility diagnostics and deterministic Birdman regression fixtures.
- iPhone release-list and diagnostics regression test. No schema, credentials, presets or acquisition workflow changes.

## [0.19.0] - 2026-10-13

### Added
- Compact expandable mobile Downloads and eight-column desktop table; stable-ID attempt groups preserve every underlying record.
- Permission-scoped paginated history, sort and media/requester/status filters; fresh-release review for supported failed movie retries.
- Source capability/verified-cache checks and disabled unsupported ratings; explicit no-match, unavailable, awaiting, failed and partial states.
- Keyboard-aware full-screen mobile filters, scoped Browse persistence and local-only navigation diagnostics.
- Additive quality/seeder/handoff/failure evidence, compact Users listing and expandable account creation.

### Fixed
- Character-by-character history column wrapping; paused torrents mislabelled as active; failed attempts changing to Available after another attempt imports.
- Users observer rewrites that could continuously trigger itself, concurrent account submissions and stale Movie/TV responses.
- Best-release action enabled without eligible results, TV cancellation/timeout feedback and result scrolling behind detail navigation.

### Verification and limitations
- Mocked integration regressions and real Chromium ingress layout tests; physical iPhone/WebKit and live HA upgrade/download checks remain manual.
- Retry opens fresh discovery, never automatically repeats a rejected token. Weekly statistics remain deferred.
- Existing framework dependency audit warnings remain disclosed; this release does not claim a clean security audit.

## [0.18.0] - 2026-10-12

### Added
- Optional modular MDBList/OMDb enrichment for IMDb, RT critics/audience, Metacritic, Letterboxd and Trakt, with validated identities/native scales and no scraping.
- Persistent per-source states, bounded background jobs, shared quotas, provider health/tests, configurable expiry and legacy verified-score preservation.
- AND-combined ratings/vote filters, explicit missing-rating policy, native/local sorting, coverage states and bounded candidate enrichment.
- Practical TMDb language/country/runtime/Australian streaming discovery filters.
- Admin-only read-only Radarr/Prowlarr release diagnostics and evidence-based category hints.
- Chromium ingress visual regression tests and CI screenshot artifacts.

### Fixed
- Serialize schema checks/DDL across HA worker processes, preventing duplicate-column startup races without deleting data or masking SQLite errors.
- Replace duplicate ingress safe-area spacing, oversized Browse hero and competing header controls with compact hamburger navigation.
- Compact multi-source rating rows, grouped scrollable filters with fixed actions, idempotent filter-count rendering and clear coverage/validation states.

### Limitations
- External-score discovery is an incrementally enriched TMDb candidate dataset, not a claim of whole-catalogue coverage.
- Awards, direct Trakt trending, direct Letterboxd access and supporter-only episode matrices are deferred with reasons in docs/RATINGS_DISCOVERY_V018.md.

## [0.17.0] - 2026-10-12

### Added
- Automatic, cancellable Movie/TV release discovery with short user/settings-scoped caching, retry and refresh. Discovery-created Arr metadata stays unmonitored.
- Optional IMDb-matched OMDb Rotten Tomatoes critic scores, secure Setup configuration and connection testing, bounded progressive loading, persistent caching and a shared daily request budget.
- Rotten Tomatoes minimum/maximum filtering across verified cached catalogue/search titles, with explicit coverage limitations and correct cached-population pagination.
- Compact responsive Downloads history table, six fields, expandable details and an authenticated paginated history endpoint.
- Additive request lifecycle/size evidence and metadata caches without deleting legacy history.

### Changed
- Header navigation replaces the fixed bottom bar. Detail navigation sits above Back/Close; notifications occupy layout below navigation.
- Dark Request best release action sits below releases. Older movies suppress redundant availability panels.
- Download history retains cached records during service failures, distinguishes transfer from import and displays local timezone dates and known progress only.

### Fixed
- Completed Arr queue transfers with zero bytes remaining enter the import state correctly.
- Movie/TV stale responses, duplicate discovery/submission and cancellation remain bounded through the effective runtime routes.

### Notes
- OMDb is optional; no paid service is required. RT filtering is explicitly limited to verified cached titles, not the complete TMDB catalogue.
- See docs/MOBILE_DISCOVERY_HISTORY.md for migrations, provider limitations, upgrade and outstanding manual acceptance.

## [0.16.17] - 2026-10-08

### Fixed

- Direct Prowlarr/IPTorrents releases selected in Choose a release retain their identity through Download.
- Submit the exact cached torrent through Radarr’s external-release API without requiring a second Radarr search; confirm the grab before marking the request queued.
- Revalidate current household rules and indexer mapping, retain storage/audit/tracking, and bound submission with timeout/cancellation cleanup.

## [0.16.16] - 2026-10-08

### Fixed
- On mobile, Choose a release now scrolls the movie-detail dialog directly to the release-search area after it is rendered.
- Release results remain anchored at the release area when the searching state is replaced, including Search again.

# Changelog

All notable MediaHub changes are documented in this file.

## [Unreleased]

## [0.16.15] - 2026-10-08

### Fixed

- Bound the effective Movie release endpoint, including metadata, Radarr, direct Prowlarr fallback, mapping and policy/audit work, to 18 seconds.
- Replaced the overriding lifecycle search UI with a cancellable 22-second lifecycle, explicit terminal states, Cancel Search, retry and administrator Setup actions.
- Propagated disconnect cancellation, preserved partial Prowlarr results, reused request metadata and moved file/database work off the event loop.
- Enforced household Movie rules at the final route boundary and aligned the deployed watchlist entrypoint version.
- Fixed invalid lifecycle JavaScript and a self-triggering mobile best-match observer; added composed-application behavioural regression coverage.

## [0.16.14-dev] - 2026-10-08

### Fixed

- Stabilized the mobile Movie detail scroll lifecycle so newly rendered details start at the top.
- Prevented the fixed bottom navigation from overlaying full-screen Movie detail content.
- Added regression coverage for modal navigation suspension, deferred scroll reset and bottom safe space.

## [0.16.13-dev] - 2026-10-07

### Fixed

- Prevented mobile UX cleanup from removing the base release-area container generated by Movie release search.
- Release discovery now keeps its searching, results, zero-result and error state visible instead of collapsing to a blank panel.

## [0.16.12-dev] - 2026-10-07

### Fixed

- Rebound the deployed Movie release-search route after runtime discovery overrides are installed.
- Choose a Release now executes the intended direct Prowlarr fallback and hard timeout path when Radarr has no releases.
- Added regression coverage for the actual FastAPI route binding.

## [0.16.11-dev] - 2026-10-07

### Fixed

- Fixed the MediaHub mobile UI becoming non-interactive after startup.
- Corrected an invalid literal escaped newline in the generated browser JavaScript from the release-search cancellation change.
- Restored catalogue loading and navigation while retaining cancellable Choose a Release behaviour.

## [0.16.10-dev] - 2026-10-07

### Fixed

- Prevented Choose a release from trapping the Movie detail UI while release discovery is pending.
- Back and close actions now cancel the active release search immediately.
- Home Assistant and MediaHub navigation remain available during release discovery, while keyboard-specific mobile navigation suspension is preserved.

## [0.16.9-dev] - 2026-10-07

### Fixed

- Prevented Choose a release from remaining indefinitely in its searching state when Prowlarr or an indexer is slow.
- Added server and browser deadlines with a visible timeout error path.
- Preserved the v0.16.8 concurrent documentary-capable release discovery behavior.

## [0.16.8-dev] - 2026-10-07

### Fixed

- Prevented direct Prowlarr fallback searches from leaving Movie release selection waiting on slow serial indexer requests.
- Movie-category and identity-filtered broad Prowlarr searches now run concurrently with bounded timeouts.
- Preserved Movie/TV identity validation while allowing standalone documentaries to be discovered through the broad fallback.\n\n## [0.16.7-dev] - 2026-10-07\n\n### Fixed\n\n- Movie release selection now falls back to direct Prowlarr discovery whenever Radarr returns no releases, including older catalogue titles.\n- Direct Prowlarr discovery keeps Movie searches media-safe by validating title/year identity and rejecting TV episode or season matches before selection.\n- Documentary movies can now be discovered when a tracker files them outside its standard Movie categories, while TV-only release results remain ineligible for Movie requests.\n- Low-quality CAM/TS-style fallback remains restricted to current-year or recently released movies.\n- The final release-identity layer now preserves the established Radarr/Prowlarr discovery pipeline instead of replacing it with a Radarr-only search.\n

## [0.16.6-dev] - 2026-10-05

### Fixed

- Preserved the active Browse text search when switching between Movies and TV Shows, so the same query is immediately applied to the newly selected media type.


## [0.16.5-dev] - 2026-09-25

### Fixed

- Removed the mobile Filters modal's invalid dependency on `window.state`. The base application declares `state` with top-level `const`, so it is not a `window` property; attempting to assign `window.state.genreIds` caused Apply to throw before committing or dismissing the modal.


## [0.16.4-dev] - 2026-09-25

### Fixed

- Multi-select movie genres now remain authoritative when the infinite catalogue resets, instead of being overwritten by the hidden legacy single-genre control.


## [0.16.3-dev] - 2026-09-25

### Fixed

- Applying mobile filters now supersedes any in-flight infinite-scroll catalogue request instead of silently dropping the filtered reload.
- Stale catalogue responses are ignored so unfiltered results cannot overwrite newly filtered results.


## [0.16.2-dev] - 2026-09-25

### Fixed

- **Apply filters** now dismisses the mobile filter sheet immediately before refreshing Browse results.
- Filter-sheet dismissal explicitly removes its visible display state and releases the body modal lock.


## [0.16.1-dev] - 2026-09-24

### Fixed

- Mobile **Apply filters** now refreshes the active infinite-scroll catalogue instead of calling the intentionally disabled legacy movie loader.
- Genre, release-year and rating filters now flow through the active catalogue controller together.


## [0.16.0-dev] - 2026-09-24

### Added

- Mobile multi-select Genre filtering with genre choices synchronised after TMDb genre loading.
- Catalogue API support for multiple simultaneous genre IDs.


## [0.15.0-dev] - 2026-09-17

### Added

- Persistent Upcoming Movie Watchlist built on the existing movie-watch lifecycle.
- Watchlist availability states for upcoming, awaiting release, no eligible release, available, downloading and downloaded movies.
- Mobile-first Watchlist navigation, filters, release-date and last-check context, plus explicit Check now actions.
- Upgrade-safe watch availability fields and focused v0.15 regression coverage.

### Changed

- Development version advanced to `0.15.0-dev`.
- Availability checks reuse the identity-aware release pipeline and current administrator Movie Download Presets.
- Watched movies remain user-controlled: becoming available does not automatically start a download.

### Protected

- Release identity, server-authoritative household presets, duplicate protection, existing request/download lifecycle and service integrations remain protected by regression coverage.


### Fixed

- Restored the administrator **Download Presets** UI to the actual deployed `app.mobile_ux_ui:app` import chain after the mobile entrypoint stopped importing the v0.12 preset UI layer.
- Removed the competing standalone **TV Downloads** Setup card and its active frontend submission path.
- Corrected Browse → **Choose a release** so it does not render fabricated request metadata such as `Invalid Date`, `0%`, `0.00 GB` or `Not recorded` when no request exists.
- Preserved unknown request size/progress as unknown instead of coercing them to real zero values.
- Corrected release-rejection presentation so Radarr/Sonarr cutoff, library and upgrade decisions are not described as MediaHub household-preset failures.
- Corrected BEST MATCH so only genuinely eligible release cards can receive the badge.

### Added

- Unified administrator **Download Presets** with separate **Movies** and **TV Shows** groups.
- Movie controls for allowed 1080p/720p resolutions, maximum Movie release size, minimum seeders, recent-release fallback enablement and fallback window.
- TV controls for allowed 1080p/720p resolutions, maximum season-pack size, maximum episode size and minimum seeders.
- Clear save confirmation, server-side validation and scoped **Reset download presets to defaults** behaviour.
- Safe read-only requester policy summary loaded only when release selection is opened.
- Structured rejection categories for identity, MediaHub policy, Radarr/Sonarr, library/upgrade state, indexer/release availability and other failures.
- Compact per-release primary rejection labels and a collapsed structured exclusion summary instead of the large raw-reason paragraph.
- Regression coverage based on the demonstrated **Goosebumps (2015)** 1.60 GB / 44-seeder Radarr-cutoff example.
- Additional regression coverage for household-policy persistence, legacy TV migration, administrator-only writes, request override prevention, invalid release-selection context, safe diagnostics, BEST MATCH eligibility, The Dog Stars and Buffalo Soldiers identity protections.

### Changed

- Development version advanced to `0.14.2-dev`.
- Movie acquisition revalidates request payloads against the current administrator household policy, so requester-supplied size, resolution or seeder values cannot override Presets.
- Legacy `tv_downloads` values remain only as upgrade compatibility data and are reconciled into the authoritative Presets structure.
- TV release evaluation preserves MediaHub season/episode size rules while separately classifying Sonarr decisions.
- Unavailable releases remain collapsed by default and display a meaningful rejection category rather than a generic `Rejected` label where a reason is known.
- Release summaries count each unavailable candidate once by deterministic primary category to avoid misleading double-counting.
- Setup mobile layout keeps one policy source of truth and retains existing Home Assistant ingress navigation and safe-area behaviour.

### Protected

- Release identity remains ahead of household quality/size/seeder eligibility and rejected identities receive no usable opaque release token.
- **The Dog Stars (2026)** unrelated TV-release exclusions remain protected.
- **Buffalo Soldiers (2002)** ±1-year strong-title tolerance remains protected.
- Watch for release, recent-release fallback, duplicate request protection, Movie/TV Browse, actor/person search, infinite scrolling, Downloads reconciliation, Radarr, Sonarr, Prowlarr, qBittorrent, Plex Movie integration, authentication, roles and Home Assistant ingress remain in scope for regression testing.
- MediaHub does not alter or bypass Radarr/Sonarr quality profiles, cutoffs or upgrade rules when household presets are relaxed.

## [0.14.1-dev] - 2026-09-04

### Fixed

- **Home Assistant ingress freeze after v0.14**: hardened the final mobile UX bootstrap so missing/late DOM elements cannot abort startup.
- Removed an unnecessary requester-side `/api/setup/presets` bootstrap request from the mobile layer; household download policy remains server-authoritative.
- Throttled mobile DOM reconciliation work to animation frames instead of performing repeated full-document work on every mutation.
- Added null-safe modal/filter/search initialisation to avoid a single mobile enhancement preventing the application from becoming interactive.

### Changed

- Development version advanced to `0.14.1-dev`.
- Deployed application entrypoint remains `app.mobile_ux_ui:app`.

### Protected

- v0.14 Mobile UX Completion behaviour remains intact, including filter sheet, safe-area handling, modal ownership, Browse/detail state restoration and read-only requester policy presentation.
- Release identity validation, administrator Presets, duplicate protection, Downloads polling and all service integration boundaries remain unchanged.

## [0.14.0-dev] - 2026-09-04

### Added

- **Mobile UX Completion** for Home Assistant ingress and iPhone-sized viewports.
- Staged mobile filter bottom sheet with active-filter count, Clear filters and atomic Apply filters actions.
- Clear-search action and a single capture-owned 450 ms mobile debounced search path.
- Full-screen mobile detail/release viewport ownership with safe-area-aware bottom navigation suspension.
- Browse/detail scroll-state preservation across nested Movie/TV release navigation.
- Read-only household Movie preset summary in requester release workflows.
- Dynamic viewport and reduced-motion handling for modern iOS/embedded browser behaviour.
- Focused v0.14 regression coverage for modal ownership, filter state, requester preset protection and mobile state restoration.

### Changed

- Deployed application entrypoint became `app.mobile_ux_ui:app`.
- Mobile collection controls are horizontally scrollable rather than clipped at narrow/keyboard-constrained widths.
- Mobile Movie/TV details use a stable structured skeleton as the first meaningful loading state and reset new details to the top.
- Cast presentation uses a horizontal swipe row at mobile widths.
- Bottom navigation is suspended while full-screen mobile modals or the iOS keyboard own the lower viewport.
- Mobile body/setup/users spacing is safe-area-aware so final content can scroll clear of persistent navigation.
- Legacy requester Movie release-rule markup is removed from release-selection surfaces; household Setup Presets remain the only policy authority.
- v0.13 roadmap status is reconciled to Delivered after successful post-merge CI.

## [0.13.0-dev] - 2026-09-04

### Added

- **Release Identity & Search Accuracy** validation before Movie/TV release eligibility and token issuance.
- Deterministic Movie title normalisation, TV-episode/season rejection, year-confidence handling and explainable match states.
- Regression protection for **The Dog Stars (2026)** false positives and **Buffalo Soldiers (2002)** ±1-year release naming.
- TV series/season/episode identity validation layered over Sonarr structured metadata.
- Compact mobile Browse treatment, mobile Filters control, debounced search, detail skeletons and compact release cards.
- **BEST MATCH** highlighting for the top eligible release and collapsed unavailable-release results.
- Adaptive Downloads polling while the Downloads view is active, with visibility-aware suspension.
- Mobile bottom navigation for Browse / Downloads / Setup with admin-only Setup visibility.

### Changed

- Release identity validation precedes quality, size, seeder and ranking policy.
- Rejected identity matches do not receive usable release tokens.
- Mobile Browse hides the large introductory hero and gives catalogue content priority.
- Downloads refresh automatically while visible instead of relying on manual Refresh for normal progress updates.

## [0.12.0-dev] - 2026-09-02

### Added

- **Admin Setup Presets** with separate **Service Connections** and **Presets** sections.
- Administrator-managed catalogue language, Movie download and TV download presets.
- **Reset to defaults** for the complete preset set.

### Changed

- Search/download defaults are centrally managed household presets.
- Movie and TV release eligibility uses saved administrator presets.
