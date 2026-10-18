# MediaHub v0.19.2 investigation and corrective release

## Findings recorded before implementation

Baseline: latest fetched main `945b2a9` (v0.19.1, merged PR #71). Open PR search returned none. Seven new deterministic regressions fail on this baseline: both documentary fixtures, four wrong-Daniel identity cases and a duplicate observation with missing metadata.

The effective pipeline is TMDb details (including alternative titles) -> runtime concurrent Radarr/Prowlarr discovery -> Prowlarr capability categories and query plan -> response category/identity filters -> response deduplication -> runtime normalization and preset -> combined deduplication -> final identity validation -> release lifecycle/status -> cached authenticated endpoint -> composed frontend. Download tokens remain user-bound and revalidated at handoff.

### Daniel (2023)

Confirmed: `release_identity.validate_movie_release` accepts the canonical title as a token prefix of a longer unrelated title. Its unconditional one-year tolerance then accepts the 2024 Daniel Howell release with score 110. Even a spoofed 2023 year passes. This directly reproduces the wrong identity independently of tracker access.

Confirmed category defect: `prowlarr_discovery.movie_categories` includes only Movie categories; `movie_category_rejected` rejects numeric categories 3000–7999, including documentary categories mapped under TV. A controlled 5070 TV/Documentary fixture is discarded even when its title, size and seeders match. This is a normalized capability fixture, not a claim that the user's installation returned exactly 5070.

### Beyond Utopia (2023)

The same category gate rejects the qualifying documentary fixture. Broad queries already exist, but their returned documentary rows still hit that gate. The scheduler starts up to four paths, each allowed six seconds, but cancels the entire plan at eight seconds. With up to thirteen paths, late aliases/broad queries can remain queued. This is a confirmed coverage limitation consistent with the supplied diagnostics. The lifecycle currently adds a partial-coverage suffix to an otherwise definitive no-results message and leaves its state unchanged.

### Birdman (2014)

PR #71 already fixed grammatical aliases and exact-year short-title matching. Those fixtures are preserved. Remaining category, deadline and duplicate-observation defects affect the shared path. No new Birdman-specific production loss has been established on current main.

### Other confirmed defects and limits

Response deduplication marks an identifier seen before category/identity assessment and keeps the first observation even when its size/seeders are missing. A later eligible observation can be suppressed. Final combined deduplication already sorts eligible observations first; source fingerprints and cached identifiers should be retained.

Prowlarr seeder normalization already distinguishes null/malformed from zero. Radarr normalization leaves malformed values unchecked. Extend consistent nonnegative-integer parsing without changing the minimum.

Detailed discovery diagnostics are currently returned to every authenticated household role. Restrict detailed evidence at the server and keep a simple coverage status available to all users. The successful-result cache must not retain partial searches. Visual inspection also confirmed that mobile CSS hides the heading paragraph containing the coverage message, while `assets/management.js` replaces it with a count-only summary. The visible summary must preserve the server coverage message, including when eligible releases are present.

Live Prowlarr responses, configured capabilities and credentials are unavailable. It is impossible to identify the exact live loss stage for either missing documentary from aggregate counters alone. These findings prove code paths capable of the failures; they do not prove that a particular raw live row was retrieved. No live IPTorrents verification or performance improvement is claimed.

## Implemented corrections

- Search categories combine Movie capability mappings with named Documentary mappings only for TMDb documentary movies. Response IDs without names are resolved against the returning indexer's capability tree. No tracker-local documentary identifier is assumed. Broad fallback still requires strict title/year identity and rejects episode/season patterns.
- Official titles must end at a release metadata boundary. An arbitrary longer title cannot qualify merely by starting with Daniel. Adjacent-year differences require an agreeing IMDb/TMDb identifier; conflicting identifiers remain rejected. Aliases retain exact-year protection. Year tokens belonging to titles such as 1917 are not mistaken for the release year.
- Canonical year-bearing searches run first, followed by verified year-bearing aliases and bounded yearless variants. A category-aware path and a broad path are retained for each term. At most three title variants, thirteen query paths including one supported identifier lookup, four concurrent paths, three pages/path, <=100 rows/page and 2,400 processed response rows. Individual query paths retain six seconds; overall Prowlarr work has twelve seconds after the <=2-second capability lookup. Existing 18-second server and 22-second frontend walls remain authoritative and can still produce partial/timeout outcomes.
- At most two transient HTTP transport/502/503/504 retries, only on the first four paths and inside their existing budgets. HTTP 429 and authentication failures are not immediately retried. Work is cancelled and drained on deadline/disconnect. Required queries are registered before scheduling, including cancelled and never-started work, with elapsed time, attempts, page and row counts.
- Intake deduplication selects the most complete valid observation of a release, preferring known seeder evidence, without constructing synthetic title/size/identity combinations. Conflicting title/size observations remain separate. Combined deduplication retains size/quality alongside source IDs. Seeders use one nonnegative integer parser for Prowlarr and Radarr; missing/null/invalid remain unknown and blocked.
- The public API separates coverage (`search_complete`, `search_status`) from results. Incomplete searches cannot claim a definitive no-match/no-eligible conclusion. Radarr timeout also marks coverage incomplete. Partial movie results are not cached; cache keys include the user's current role.
- Administrator diagnostics include the bounded plan, requested indexer IDs/names, category IDs, timing, pagination, filtering counts and up to 100 allowlisted release snapshots. Individual rows show source/category/quality/size/seeders, identity and exclusion reasons. Diagnostic samples disclose omitted-row counts. Details are stripped server-side for manager/requester roles, and remain collapsed in the UI. Private URLs, credentials, GUIDs and raw exceptions are never copied into these diagnostics.
- Mobile's visible summary retains the coverage message instead of silently replacing it with counts. No unrelated navigation/layout changes or preset changes were made.

## Validation and measurements

The first seven new tests were observed failing on unchanged main before implementation. They now pass. Additional deterministic tests cover documentary mappings, source-specific custom IDs, broad fallback, wrong titles/years, seeder values, retries/rate limits, budget exhaustion, queued paths, cancellation/task cleanup, distinct release observations, preset rejection, final identity/token evaluation, server-enforced role restrictions, sensitive-data redaction and partial-result caching. Existing Birdman, movie/TV acquisition and exact Prowlarr handoff tests remain in the suite.

A scaled mock-transport experiment used twelve planned paths, four concurrent paths and 30 ms simulated response latency. The unchanged scheduler with an 80 ms test wall started eleven paths, completed seven and reported partial coverage in 84.4 ms. The revised scheduler with a 120 ms test wall started/completed all twelve and reported success in 95.2 ms. These shortened walls model the 8/12-second budget ratio, not real tracker latency. The experiment demonstrates a coverage tradeoff at greater wall time, not a speed improvement. No Raspberry Pi CPU/RAM measurement or live search duration is claimed.

## Files and release process

Core changes are in `prowlarr_discovery.py` (categories, scheduling, deduplication, evidence), `release_identity.py` (identity/seeder validation), `runtime.py` (metadata and merged observations), `media_services.py` (Radarr seeder/identifier normalization), `release_lifecycle.py` (coverage, role checks and diagnostics rendering), `feature_release.py` (cache integrity), and `assets/management.js` (visible mobile status). Tests add the two documentary fixtures and fault/role coverage, plus an iPhone partial-search screenshot assertion. Existing version assertions and documented-year regression fixtures are updated for the stricter rule.

Version 0.19.2 is set in the HA manifest and effective application entrypoint. Both changelogs, README and roadmap are updated. The Dockerfile builds from source and the add-on manifest has no prebuilt image pin. This repository's CI validates/tests pull requests and main; it does not publish a release/tag. After approved merge into the configured repository branch, Home Assistant must reload repository metadata and build/install the new add-on version. A PR alone does not expose an HA update. No merge, tag or publication was performed.

## Live verification checklist

After approved merge and installation, first confirm the installed version is 0.19.2 and existing household presets remain unchanged. Reopen MediaHub to load the current inline scripts.

- Search the 2023 documentary Daniel and refresh releases. If the observed LAMA release is returned by Prowlarr with qualifying current metadata, it must be eligible. Daniel Howell must never be BEST MATCH for Daniel.
- Search Beyond Utopia (2023). Check the 1080p documentary when returned; 2160p/oversized releases must remain blocked. For any failed/cancelled/unstarted queries, confirm the visible summary says Partial results or Indexer unavailable rather than a definitive no-match conclusion.
- Search Birdman (2014), including its full official title. Confirm existing short-title fixtures still match when returned, while Birdman of Alcatraz and TV episodes remain excluded.
- As administrator, inspect collapsed query and individual-release details to locate any live loss. Compare the exact Prowlarr manual response, requested categories and current indexer mappings. Repeat as a requester to confirm detailed diagnostics are absent.
- Navigate away during a slow search, return and refresh. Confirm responsive navigation, safe cancellation and no repeated request burst. If explicitly choosing an eligible release, check the exact Radarr acquisition and Downloads state. Discovery itself must not acquire media.

The user's live Prowlarr configuration, tracker mapping, current seeder counts, tracker-internal silent failures, physical iPhone behaviour and Home Assistant update discovery still require live verification. Prowlarr aggregate results do not prove which silent indexer answered internally. These limits must remain visible in the PR/report.

Final local checks: **446 Python/DOM tests passed** (32.86 s, 11 existing deprecation warnings); **17 Chromium tests passed** (16.8 s), including the visible iPhone partial-search summary and expanded release evidence. Python compilation, configured critical Ruff checks, version metadata and `git diff --check` passed. The initial Chromium installation required a mirror retry; browser execution subsequently passed. The earlier unconditional one-year test fixtures now require agreeing authoritative identifiers. CI status is recorded in the pull request after creation.
