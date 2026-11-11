# Movie release identity and alternate years

## Root cause

The shared identity validator previously allowed a one-year difference only when a matching IMDb or TMDb identifier was present. Alternative titles additionally required an exact year. Most torrent rows do not contain movie IDs, so valid festival/wide-release differences were rejected before household filtering. Existing TMDb detail requests already retrieve regional release dates, but matching did not use them.

## Matching rules

| Evidence | Decision |
| --- | --- |
| Explicit conflicting known IMDb/TMDb ID | Rejected, including when another ID matches |
| Matching IMDb/TMDb ID | Strong identity, even with a different year or distribution title |
| Normalised official/original/known alternative title, exact year | Strong identity |
| Same strong title, one-year difference | Accepted without requiring unavailable metadata |
| Same title, two-year difference without supporting evidence | Uncertain, unavailable for selection or submission |
| Same title, larger unsupported difference | Rejected |
| Same title, year independently present in selected-movie metadata | Accepted regardless of difference |
| Full title with missing movie/release year | Accepted with an explicit missing-year explanation |
| Grammatical shortened title with missing release year | Uncertain without a matching movie ID |
| Extra title words, fuzzy word overlap or TV episode/season | Rejected |

The score is a ranking/evidence score, not a calibrated probability. Existing `match_state`, `match_score` and `match_reasons` remain available. Additive fields expose `identity_status`, `selected_movie_year`, `torrent_release_year` and `year_tolerated`.

Normalisation handles case, accents, apostrophes, punctuation and separators. Exact boundaries permit trailing year/quality/codec/group metadata without treating a longer unrelated title as a match. Years inside movie titles, such as *1917*, are excluded from the release-year comparison.

Year evidence comes only from selected-movie metadata: available production/premiere/theatrical/digital dates and TMDb regional release records. Torrent claims do not establish alternate years. TMDb details and release dates reuse the existing request-local metadata cache; no new provider lookup, dependency or matching service is introduced.

## Discovery reliability and configuration

The previous six-second wall-clock query budget and HTTP timeout explain approximately six-second failures. Discovery now allows eight seconds per request by default, with a bounded shared retry budget of two and four concurrent queries. A retry can run within the remaining discovery deadline. The existing twelve-second discovery deadline, endpoint deadline, pagination/row limits and cancellation cleanup remain enforced. Successful pages survive sibling timeout, provider, authentication and later-page failures. Successful Radarr results also survive an entirely failed supplementary Prowlarr search.

`MEDIAHUB_PROWLARR_QUERY_SECONDS` optionally changes the per-request timeout. Values are clamped to 1–10 seconds; malformed/NaN values fall back to eight. It is an environment setting for operators, with no required configuration migration or new setup form. It cannot increase the overall search deadline. Partial results continue to be marked incomplete and excluded from the completed-search cache.

## Deduplication and diagnostics

Discovery deduplicates repeated responses using torrent hashes, indexer GUIDs/URLs or source/title/size fallback fingerprints. It retains separate source observations until Radarr mapping can identify a usable source. Final merging uses hashes across sources while preserving title, size, quality and encode distinctions. Ineligible releases with different GUIDs no longer collapse merely because their displayed titles match.

Opaque candidate IDs connect diagnostic rows to final decisions without exposing tracker GUIDs, URLs or credentials. Rows show accepted/uncertain/rejected identity, score and evidence, both years, tolerance, final eligibility and exclusions. Merged duplicates are labelled explicitly. Unique final-decision counters are separate from raw-response and processing-stage counters. Admin-only diagnostics and ingress-relative navigation remain unchanged.

## Household and manager enforcement

Identity acceptance still goes through the existing configuration-driven size, resolution, seeder and quality checks. No size, seeder or resolution preference is hardcoded into matching. Codec handling, compatibility, Radarr quality profiles, library/cutoff checks, token validation, source mapping and the acquisition workflow remain in their existing paths. Direct submissions now also refuse uncertain identity results.

The reported 2020 1080p Lootera release for *The Killing of Two Lovers* (selected year 2021) passes identity without IDs. With a 3 GB maximum, one-seeder minimum and 1080p-only preset, the 2.15 GB/one-seeder fixture is eligible; 4 GB, 720p, unknown resolution and zero-seeder variants remain excluded.

## Files

| File | Purpose |
| --- | --- |
| `mediahub/app/release_identity.py` | Shared confidence rules, metadata year evidence, punctuation normalisation and public identity fields |
| `mediahub/app/prowlarr_discovery.py` | Request timeout, bounded retries, partial success, source/hash deduplication and diagnostic evidence |
| `mediahub/app/runtime.py` | Candidate IDs, final deduplication, successful Radarr preservation and uncertain-submission rejection |
| `mediahub/app/release_lifecycle.py` | Unique-decision counters, exact diagnostic joins and composed frontend rendering |
| `tests/test_movie_year_tolerance.py` | Reported movie, IDs, years, remakes, presets, duplicate sources, diagnostics and failures |
| `tests/release_search_ui.cjs` | Deployed/composed ingress UI evidence and uncertainty assertions |
| `tests/test_birdman_discovery.py`, `tests/test_documentary_discovery.py`, `tests/test_v013_identity_mobile_live.py`, `tests/test_v01615_release_discovery.py` | Update superseded strict-year assertions and verify bounded retry/partial-failure behaviour |

## Validation and limits

Automated fixtures cover the reported release and *The Thing* (1982/2011) collision. Existing Radarr, Sonarr, Prowlarr and download regressions are included in the full Python and mobile browser suites. No live indexer credentials or household server were used, so actual tracker availability and acquisition are not asserted. Missing external IDs cannot identify every adjacent-year same-title collision; exact title boundaries, conflicting IDs and unsupported-year rejection provide the available safeguards. Two-year uncertainty is deliberately withheld rather than automatically downloaded.

Validation performed locally:

- Full Python suite: 489 passed.
- Final composed UI and new identity suite: 38 passed after the final presentation adjustment.
- Ruff critical-error check (`E9,F63,F7,F82`), Python compilation and `git diff --check`: passed.
- Chromium ingress/browser suite: all 61 tests passed, including mobile layouts, documentary partial results, Birdman discovery and download interactions.
- WebKit tests were invoked, but could not launch because this environment lacks GTK4, Graphene, WOFF2, HarfBuzz ICU, Hyphen, Manette and GLES libraries. Installing host dependencies requires unavailable administrator access; WebKit validation remains for CI.

Existing FastAPI lifespan and pytest-plugin deprecation warnings remain unrelated to this change.
