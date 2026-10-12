# MediaHub v0.18.0: ratings, discovery and startup reliability

## Assessment and root causes

Baseline: latest merged main `3784989`, v0.17.0. This release retains TMDb catalogue discovery, the existing FastAPI/composed JavaScript frontend, Movie/TV presets, the v0.17.0 Downloads table, authentication, HA ingress and the established Arr/Prowlarr handoff. No Issue, automatic merge or release tag is created.

The v0.17.0 Rotten Tomatoes bounds queried only `critic_catalogue` membership already populated by unfiltered browsing. Filtering did not inspect candidate pages or enqueue missing data. Its serial ten-second score batch could finish before inspecting every title. Provider errors, missing scores and absent configuration all became `None`. Consequently an empty result did not establish that no matches existed. We cannot infer the state of the user's live OMDb credentials from the repository; this implementation exposes provider tests and health to diagnose that separately.

Schema initialisers performed PRAGMA column checks followed by ALTER TABLE without a common cross-process lock. HA starts independent ingress and external workers. Both could inspect the same old schema, then race to add `download_started_at`. Multiple initialisers also overlap these additive fields. `schema_migrations.serialised` now locks the complete check/DDL sequence using a process-shared file lock, supports nested initialisers, and records successful migration-function completion. SQLite failures propagate; none are treated as harmless duplicate-column errors. Interrupted additive migrations resume by inspecting the actual schema. Requests, history, settings and audit data are not deleted.

The supplied `IMG_3160.png`, `IMG_3161.png` and `IMG_3162.jpeg` show duplicate top spacing inside HA ingress, a tall filter sheet and plain N/A text. The app applied top safe-area spacing inside an already inset HA iframe. The new embedded layout removes that duplicate top padding and oversized Browse hero, uses one hamburger header and compact grouped filters. HA's outer header is not modified.

## Provider contracts and limits

Official documentation inspected on 12 October 2026:

- [MDBList OpenAPI](https://api.mdblist.com/schema/) and [API explorer](https://api.mdblist.com/docs/).
- [MDBList limits](https://docs.mdblist.com/docs/api): free key, 1,000 requests/day; paid supporter tiers increase quotas. Every tier also has account-shared five-minute read/write limits. The API documents 429/Retry-After and rate-limit response headers.
- [MDBList terms](https://mdblist.com/static/legal.html): users must comply with third-party terms. We found no explicit blanket redistribution grant or permanent-cache licence. MediaHub uses an expiring household cache and does not export/resell/provider-scrape ratings.
- [OMDb](https://www.omdbapi.com/), [keys](https://www.omdbapi.com/apikey.aspx) and [terms](https://www.omdbapi.com/legal.htm). OMDb supports IMDb-ID lookup; its site publishes non-commercial CC BY-NC 4.0 content and a free 1,000-call/day key.
- [TMDb discovery](https://developer.themoviedb.org/reference/discover-movie) and [TV discovery](https://developer.themoviedb.org/reference/discover-tv).

MDBList's documented single-item route is `/tmdb/movie/{id}/` or `/tmdb/show/{id}/`. Its ratings API documents IMDb, TMDb, tomatoes, audience, Metacritic, Letterboxd and Trakt sources. The adapter supports returned native-scale fields only. An advertised source is not a promise that every title or free account returns that score. Missing or restricted data stays unavailable. Supporter-only episode rating matrices are not requested. No paid service is silently required.

| Source | Scale | Provider path | Notes |
|---|---|---|---|
| TMDb | 0–10 | Existing TMDb catalogue | Vote count and popularity retained; no new subscription |
| IMDb | 0–10 | MDBList, OMDb fallback | IMDb votes where supplied |
| RT critics | 0–100% | MDBList, OMDb fallback | Only Tomatometer, never audience substitution |
| RT audience | 0–100% | MDBList | `popcorn`/audience aliases; OMDb is not assumed to supply it |
| Metacritic | 0–100 | MDBList, OMDb fallback | Metascore, not percent-positive |
| Letterboxd | 0–5 | MDBList when returned | No direct Letterboxd scraping or unapproved API |
| Trakt | 0–10 | MDBList when returned | Votes where supplied; no duplicate direct integration |

Authoritative returned TMDb/IMDb identity and media type are checked. Provider-native values are validated as finite and in range. MDBList's aggregate `score` is not substituted for a source rating. Unknown values are never zero.

## Setup

TMDb remains required for catalogue access. External keys are optional:

- `integrations.mdblist_api_key`
- `integrations.omdb_api_key`

Keys can be saved through Setup using the existing 0600 atomic settings writer. The ratings-provider panel adds connection tests, per-provider health, successful-request/error timestamps, queue counts and coverage. Changing a failed key resets its cooldown without deleting good cached scores. Public settings do not return keys. Request logging redacts external-rating credential URLs. Diagnostics never return download URLs or credentials.

Configurable ratings settings, saved through Setup:

- `cache_days`: 1–30, default 7.
- `daily_budget`: 0–900 per external provider, default 400, shared by both HA workers. Other apps using the same account may still exhaust the provider's quota.
- `background_enabled`: pause/resume background work.

Provider tests use a known authoritative ID and consume budget. A failed provider never prevents the TMDb catalogue from loading. Some titles require no external provider at all when using only TMDb thresholds.

## Cache and bounded enrichment

Additive tables: `rating_titles`, `rating_values`, `rating_jobs`, `rating_health`, `rating_budget`, `discovery_progress`, and the migration-function registry. Old critic tables are retained and verified legacy scores are imported without inventing a status for legacy nulls.

Each source record stores native value, votes, provider, status, retrieval/expiry times and a sanitized error code. Title payloads retain identity, title and year. Source precedence chooses fresh verified MDBList data, with OMDb fallback for its supported sources. A failure does not erase last verified values or refresh their original expiry deceptively.

States distinguish verified, not retrieved, unavailable, expired, authentication failure, lookup failure, temporary unavailability and rate limiting. Coverage exposes inspected titles, awaiting/failed/unavailable/expired titles and verified scores outside the selected range. Admin coverage also reports per-record counts and queue states.

Browse returns promptly and queues enrichment. `/api/ratings` is cache-first; it does not synchronously spend provider requests. One background worker per HA process claims jobs under a SQLite write transaction with a 90-second lease. The same title/provider cannot be claimed twice concurrently. Outstanding jobs cap at 400; each enqueue handles at most 100 IDs. Each job has a 12-second deadline. Transient failures retry at most three attempts with increasing delays, and provider cooldowns honour Retry-After. Confirmed unavailable source values negative-cache for one day. The worker rate plus daily cap remains below free-account read quotas. Shutdown releases claimed jobs; abandoned leases are recoverable after restart.

The frontend refreshes cached ratings every ten seconds only while Browse or details are visible, at most 20 IDs. It does not poll external providers directly. This updates compact score rows as background coverage increases.

## Discovery, filters and search scope

Individual source criteria can be enabled, disabled or cleared. Inclusive bounds combine with **AND** logic. IMDb/TMDb can require minimum votes. Missing-score policy defaults to exclusion, or explicitly includes unverified titles with labels. Known scores outside bounds remain excluded even when unverified titles are included. Vote counts that are unknown cannot be passed off as meeting a threshold.

Supported sorting: highest native-source rating, TMDb popularity, TMDb vote count, newest/oldest release and recently inspected local titles. Missing/expired scores sort last; TMDb IDs break ties deterministically. TMDb-native sort/filter discovery uses provider-side queries. External-score sorting/filtering uses the inspected TMDb candidate dataset across all its stored pages, not just the visible page. Counts refer to that actual dataset, never the whole TMDb catalogue.

Practical coverage workflow:

1. Select one or more rating ranges and apply.
2. Inspect the coverage message. An empty partial dataset is not described as proof of no matching films.
3. Use **Enrich this discovery**. One action inspects at most three further TMDb pages under an 18-second deadline and queues ratings.
4. Ratings appear progressively; use **Refresh results** to rerun the filtered dataset as coverage grows. Additional explicit enrichment advances through candidate pages.

There is no unbounded crawler. Catalogue completeness cannot be guaranteed inside free-tier quotas. Provider-wide MDBList catalogue substitution is deferred: TMDb remains authoritative, and the official MDBList catalogue contract does not expose all independent source bounds required here. Its list/catalogue APIs are not silently substituted for the household's discovery categories.

Practical additional discovery: Movie/TV modes, genre multiselect, year range, original language, country, runtime, TMDb vote thresholds and subscription-streaming availability in Australia. Country/language inputs use ISO codes. TMDb's AU streaming data is availability metadata, not guaranteed subscription access or a live entitlement check. Text search does not support all native discovery constraints; language/country/runtime/streaming combinations with a search term return a clear validation error instead of silently ignoring constraints. Clear the text search to use these discovery filters. Search text remains persistent when switching Movie/TV modes.

## Compact mobile UI and visual acceptance

The app header is a small logo plus one hamburger menu. Existing Browse, Downloads, Setup, Watchlist, Users and sign-out access and permissions are retained. Detail navigation remains above Back/Close. No bottom navigation or oversized Browse promotional hero returns. iPhone portrait controls and the beginning of the catalogue fit near the top of the usable iframe.

Ratings use compact wrapping indicators with critic/audience labels, native scales, provider/vote/retrieval information in accessible title text. Unknown sources do not fill the page with repeated N/A cards. Existing poster metadata no longer repeats the TMDb star score beside the new score row. Source values stay readable and do not horizontally scroll.

Filter sheets have a fixed flex heading and action section, independently scrollable grouped fields, visible errors, Clear/Apply actions and safe-area-aware bottom padding. Successful apply closes the modal. Validation failure leaves it open with the error. Controls use readable mobile input sizes. The previous filter-button mutation now updates only when the HTML changes, avoiding repeated observer rewrites.

Chromium tests render a simulated HA outer header and actual composed application in an iframe at 320×740, 375×812, 390×844, 430×932, 844×390, 768×1024 and 1440×900. Assertions cover header height/top, grid position, duplicate bottom-nav absence, overflow, filter height/scroll/actions, combined criteria, active count, four-score row wrapping and close behaviour. Fixture-based Browse/detail screenshots are retained as CI artifacts. These are representative synthetic test titles, not live ratings or actual HA screenshots.

## Administrator release diagnostics

Details expose a collapsed admin-only **Run read-only diagnostics** action. It inspects existing Radarr movie identity/release candidates without adding a title, grabbing or changing acquisition. It counts candidates, eligible and rejected releases, separates Arr policy from household rejection categories, timestamps the result and reports request/timeout failures.

When Radarr returns zero candidates, read-only Prowlarr queries compare the configured Movie category against a broad title/year query. Counts and matching/rejection counts are returned, not indexer names, raw URLs or release payloads. A broad-match/zero-category observation is labelled **possible** category mismatch, not proof of a mapping defect. This does not bypass the existing Radarr-authoritative or approved direct-Prowlarr-through-Radarr workflow.

## Deferred capabilities and reasons

- Direct Trakt trending feeds: a separate authorised client/account contract is not configured; MDBList-returned ratings are supported without redundant credentials. No unsupported trend endpoint is invented.
- Awards/nominations filtering: neither the existing TMDb normalized catalogue nor the verified MDBList catalogue schema offers the required dependable filter. OMDb prose is not parsed into fabricated structured awards.
- Direct Letterboxd API: no approved access is supplied. MDBList values are supported when actually returned.
- Exhaustive external-rating catalogue filtering: impossible to guarantee inside bounded candidate inspection/free API budgets. Coverage and explicit enrichment remain honest and actionable.
- MDBList supporter-only per-episode matrices and commercial redistribution: not enabled; account entitlements and third-party licensing are not assumed.
- Runtime/origin/streaming intersections with text search: TMDb discovery and search have different contracts; unsupported combinations are rejected clearly.
- OR rating logic: deferred to avoid ambiguous partial-rating UX. AND semantics are implemented and tested.

## Upgrade and troubleshooting

After review and approved merge, back up the HA add-on, reload the repository, install v0.18.0 and restart. No release tag is created by this PR. The manifest version enables HA discovery after merge; application and changelog/roadmap metadata agree. Embedded UI is served with the existing no-cache response headers, so restart/reopen loads the updated composed frontend. Keys and household data remain intact.

For empty filtered results, read the inspected/awaiting/expired/failed coverage before assuming no matches. Configure/test MDBList or OMDb if using external sources; enrich candidates and refresh results. An invalid key or quota error is shown independently from TMDb connectivity. On startup errors, preserve the actual SQLite traceback and backup; do not delete the database. Migration locking fixes the check/ALTER race instead of suppressing it.

Outstanding live acceptance:

- Actual iPhone/WebKit in HA ingress, including keyboard and device safe areas.
- Real configured MDBList/OMDb free-account response availability, quota headers and supported TV fields.
- Real Radarr/Sonarr/Prowlarr and qBittorrent regression download/import/seeding behaviour.
- Actual upgrade backup/restart and user-role checks on the installation.
- Docker image builds for HA aarch64/amd64/armv7 (Docker is unavailable locally).

Automated tests use mocked integration responses and need no paid/live credentials. Chromium checks validate real layout, but do not claim an end-to-end physical iPhone test.

## Verification results

Local final validation: Python/DOM regression suite, compilation, critical Ruff lint and whitespace checks passed. Seven Chromium ingress layout tests passed and generated Browse/detail screenshots. Exact test totals and GitHub Actions status are recorded in the PR after the final run.
