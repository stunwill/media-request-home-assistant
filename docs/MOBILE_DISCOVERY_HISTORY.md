# MediaHub v0.17.0

Baseline: v0.16.17, main commit c2f0922. This feature release retains the existing Python/FastAPI and composed JavaScript architecture and the deployed `app.watchlist_main:app` entrypoint.

## Mobile changes

Before: a fixed bottom navigation bar, bottom notifications, manual Choose a release searches and tall download cards.

After: logo/Browse, Downloads and Setup in the header, with existing Watchlist, Users and sign-out access retained under More. Details show Browse/Downloads/Setup above Back/Close. Notifications occupy normal flow below the header or within the detail toolbar, so they cannot cover controls. Routine notifications dismiss after 6.5 seconds, errors after 15 seconds; up to three distinct notifications are retained with manual dismissal.

Details start release discovery automatically, without scrolling past the metadata. Request best release moves below discovery and uses dark styling. Explicit refresh still scrolls movie results into view. Trailers and Watchlist remain accessible. Established pre-2024 movies suppress redundant lifecycle panels; missing digital dates alone do not produce warnings. Newer titles with reliable release metadata retain useful lifecycle information. Library availability suppresses warnings.

Movie searches reuse the v0.16.17 identity, household policy, cancellation, direct-Prowlarr and Radarr handoff paths. Successful release lists cache for two minutes per user, title, flags and complete configuration. Settings changes invalidate by cache key; handoff attempts invalidate that user's cached tokens. Concurrent searches coalesce. TV opens with discovery of the latest aired season, lets users select another season, and retains episode and season views. Discovery has an 18-second backend budget and a 22-second browser escape hatch. Errors remain local to discovery. Detail metadata has a 15-second browser deadline and ignores departed responses.

Arr interactive release discovery may require creating a metadata entry in Radarr/Sonarr. New entries created for discovery are **unmonitored**, with search-on-add disabled and no MediaHub download request. Existing monitored library entries retain their settings. Explicit requests may enable monitoring and perform the existing request/grab workflow. Opening details never issues a grab or search/download command.

## Rotten Tomatoes provider and configuration

OMDb is optional. Enter its API key in Setup's Rotten Tomatoes section, save, then use Test connection. The Home Assistant options schema also accepts `integrations.omdb_api_key`. Existing metadata and downloads work without it. Keys use the existing atomic settings writer with mode 0600; keys are never returned in public settings or connection-test errors. OMDb request URLs are redacted from HTTP request logs.

References, checked 12 October 2026:

- https://www.omdbapi.com/ documents IMDb-ID lookup, movie/series types and CC BY-NC 4.0 content licensing.
- https://www.omdbapi.com/apikey.aspx documents the free key's 1,000 requests/day.

No paid dependency is introduced. The poster API is separate and is not used. Scores are OMDb-supplied Rotten Tomatoes critic percentages, not live certification by Rotten Tomatoes. Availability is variable, especially for TV. Only an exact IMDb identifier and correct movie/series type can produce a score. Missing scores remain N/A, never zero. Audience scores are not used.

Card ratings load progressively in bounded batches of at most 20 IDs with a ten-second wall deadline. IMDb mappings and successful scores persist for seven days. Confirmed missing ratings cache for a day; provider failures back off briefly. A shared SQLite counter limits the two HA workers together to 400 OMDb calls per UTC day, including connection tests. This leaves headroom within the provider's free quota but cannot account for other apps using the same key. No credential-bearing errors propagate to the client.

### Honest filtering limitation

OMDb supplies individual-title metadata, not an exhaustive critic-scored TMDB catalogue. Score filtering therefore explicitly operates on **verified cached titles for the current collection/search** across all cached pages. It is not a current-page filter and does not claim TMDB-wide completeness. The UI states this limitation whenever score bounds are active. Browse without score filters to populate more ratings. Counts and pagination refer only to the matching cached population; unknown/expired scores are excluded. Min/max are independent, inclusive integer bounds from 0 to 100. Reset clears both. Movie and TV filter state is retained in its existing category context.

Collection/search membership expires after 30 days; critic freshness remains seven days. Newly cached ratings may expand subsequent filter results. This fallback intentionally avoids scanning hundreds of TMDB pages or spending a user's quota silently.

## Downloads and migration

`GET /api/download-history?page=1&page_size=50` adds an authenticated, owner-filtered, paginated API. Existing `/api/downloads` consumers remain compatible. History contains only MediaHub requests; Plex library entries are not imported. One database request produces one table row. Superseded/deleted rows remain stored but are omitted from the table.

The table displays Title, Requested by, Date & time, Type, Size and Status. On narrow screens Type/Size move into the expandable details, leaving four compact columns. All details stay accessible by tapping the title/row. Active percentages appear only with verified transfer progress. `processing` is presented as Importing using the existing persisted state. A torrent reaching 100% does not make a title Available. Arr library evidence remains authoritative, including after a torrent continues seeding.

Additive nullable fields on `requests`:

- `download_started_at`, `download_completed_at`, `imported_at`, `available_observed_at`
- `actual_size_bytes`, `progress_known`, `series_title`

Existing audit events can backfill known start/availability-observation dates. Availability observation is kept separate from actual import time. Transfer completion comes from qBittorrent `completion_on`; import timestamps come from Arr file metadata where supplied. Existing historical timestamps are never overwritten. A completed request displays a verified transfer-completion or import time; otherwise Unknown. Incomplete/failed requests display creation time. Dates display in the browser's local timezone, using DST-aware `Date` formatting (Australia/Melbourne or Australia/Sydney for Victoria).

Actual transfer/client size wins over estimated release size. Estimated values carry `~` and an explicit explanation in expanded details. Legacy whole-series TV placeholder estimates are not displayed as real sizes. Unknown fields remain Unknown. Human series names are retained with season/episode identifiers for new selected-TV requests; legacy release titles remain intact.

New persistent metadata tables: `critic_cache`, `critic_identity`, `critic_budget`, `critic_catalogue`. Request history and metadata live in the existing `/data` SQLite database. Migrations are idempotent and non-destructive. Download refresh reuses existing reconciliation, is coalesced for ten seconds per worker, has an 18-second deadline, and falls back to saved rows on integration failure. Queries page history instead of returning the whole table to the frontend.

## Upgrade and outstanding acceptance

After the PR is reviewed and merged, reload the HA add-on repository, install v0.17.0 and restart. Take a normal HA add-on backup before upgrading. No required new configuration or credential migration exists; OMDb is optional. Database migration runs at startup. The unmerged PR alone will not create an update on HA's main-branch add-on repository.

Manual acceptance still required on the actual installation:

- iPhone portrait and landscape, tablet and desktop visual layout and touch targets.
- Back/Close preserves search/category/filters/scroll, including while Movie/TV APIs are slow.
- Notifications remain within layout and header/More navigation remains reachable.
- Real Radarr and direct-Prowlarr Movie requests, Sonarr season/episode requests, requester attribution and error details.
- qBittorrent progress, completed transfer awaiting import, imported media while still seeding.
- Historical data survives upgrade/restart and requester-only users see their own rows.
- Actual OMDb key connection test, supported Movie/TV scores, quota exhaustion and unavailable ratings.
- Local timezone shows 11-hour daylight-saving offset in Victoria in October and ten hours in winter.
- HA ingress and external login, role restrictions, Plex library detection and Setup.

Browser screenshots could not be captured in this environment: Playwright is present but Chromium is not installed, and downloading the executable failed. Four representative viewport sizes are exercised in composed DOM behaviour tests; those tests do not verify visual layout. Docker/image builds and live HA/Arr/OMDb acceptance could not run here. Compilation, repository metadata, packaging entrypoint/static files and automated mocked integration tests are checked separately.

## Subsequent Downloads work

Weekly statistics, user-facing table sorting and table filters are deliberately deferred. The paginated endpoint, persistent lifecycle evidence and compact table leave room for a statistics strip and server-side filter/sort parameters. No placeholder statistics are rendered.

## Automated validation completed

- `python -m pytest -q`: 333 passed (11 existing deprecation warnings).
- `python -m compileall -q mediahub tests`: passed.
- `python -m ruff check mediahub tests --select E9,F63,F7,F82`: passed.
- `git diff --check`: passed.
- Version/changelogs/roadmap, final runtime routes, ingress/external entrypoints, HA password schema and static packaging assertions: passed for v0.17.0.
- Composed DOM feature tests at 390x844, 844x390, 768x1024 and 1440x900: passed. Existing search cancellation/deadline and Radarr/Sonarr/Prowlarr/qBittorrent/Plex regression suites passed.

These are mocked integration and DOM checks, not a claim of live services or real-browser visual acceptance.
