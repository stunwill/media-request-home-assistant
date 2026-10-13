# MediaHub v0.19.1: Birdman release discovery correction

Baseline: merged main `b40cabf`, v0.19.0, PR #70. No open PRs existed at inspection. This is a focused patch release with no database/configuration/preset changes, new paid dependency, Issue, automatic merge or release tag.

## Confirmed root cause, reproduced before edits

The effective pipeline is:

`release_lifecycle.findReleases` → ingress-relative POST movie releases → `feature_release.movie_releases`/cached discovery → `movie_release_endpoint` deadline/disconnect control → `release_lifecycle.release_search` → `release_activity`/`authorized_expanded` → `enhanced_main.movie_releases` → captured runtime search → final `release_identity_main` evaluation → sorted public results → frontend.

For the authoritative title **Birdman or (The Unexpected Virtue of Ignorance)**, `runtime._movie_search_terms()` generated only the official/original long title, with and without 2014. `_prowlarr_search()` executed four requests: movie-category and broad variants for each term. No short Birdman query or alternative/identifier query existed.

Even when mocked Prowlarr returned all three actual observed short-title fixtures, `_prowlarr_search()` returned **zero**. Its `_matches_movie()` required at least two meaningful words from the long title; each release contained only Birdman. The final `release_identity.validate_movie_release()` independently required a full-title token prefix, so it also rejected all three. Removing just one gate would not fix the pipeline. These two deterministic defects are confirmed by baseline execution and four red regression tests before implementation.

The live Prowlarr query responses/installation credentials are unavailable here. Therefore we cannot prove which query failed to retrieve a particular live row; we can prove these rows could not survive either existing matching gate if returned. The user's screenshot values are represented as sanitised fixtures, not invented tracker results.

## Other investigated loss points

- **Categories:** old code already queried Prowlarr's normalized Movie parent 2000 and an unrestricted broad path. It was not BluRay-only. A category mapping defect is not confirmed. New code reads enabled searchable indexers' capability category trees, includes appropriate Movie parent/children and retains the broad path. Returned known TV/nonmovie categories are excluded before identity. Unknown category metadata alone does not discard an otherwise verified movie.
- **Limits:** old code requested limit 100 and then sliced every response to the first 100, including aggregated responses containing more rows. No offset paging existed. Silent slicing is removed. This is a confirmed completeness defect, but not proof that the three live Birdman rows were beyond position 100.
- **Premature exit:** old runtime returned early when Radarr had any eligible candidate, cancelling supplementary Prowlarr discovery. Searches now combine bounded independent results. This was not the reported Birdman condition (all four were oversized), but prevented fuller discovery elsewhere.
- **Codec/quality:** no blanket x265/HEVC/10-bit exclusion was found. Quality derives from resolution markers. The three 1080p fixtures remain eligible without relaxing presets.
- **Sizes:** Prowlarr API bytes are converted using 1024³, consistent with existing household configuration's legacy GB labels (binary GiB thresholds). Policy now compares the unrounded value, so e.g. 3.001 GiB cannot round down and pass a 3 GiB limit. This does not reinterpret saved presets as decimal GB.
- **Seeders/metadata:** known zero remains zero; malformed/unknown seeders and nonpositive/missing sizes have meaningful rejection reasons. Required GUID/indexer mapping guards remain. Unknown metadata never grants eligibility.
- **Duplicates:** response duplicates use provider release identifiers. Combined results use cached stable IDs, with a size/quality/source fingerprint fallback rather than title alone. Thin records without sufficient identity are retained rather than guessed to be duplicates.

## Correction

`prowlarr_discovery.py` replaces the duplicate prefilter/query implementation behind runtime's existing function interface. The final identity validator is shared with Prowlarr intake and handoff validation. `TmdbClient.details()` now appends alternative-title metadata to its existing single details call rather than creating per-alias requests.

Only grammatical **Title or (Alternate title)** prefixes and authoritative metadata alternatives are accepted as aliases. Aliases require the exact requested year immediately after their title. Birdman 2014 is accepted; Birdman of Alcatraz 1962 (or a spoofed 2014 suffix), yearless short aliases, wrong-year aliases, Detective Conan and Dr Quinn episode/season patterns are rejected. Conflicting returned IMDb/TMDb IDs are rejected. Full official-title matching retains its established year-tolerance behavior.

Queries prioritize the grammatical alias, then official/original and supported regional alternatives. At most three unique title variants, each with/without year, are used; punctuation is simplified deterministically. One authoritative identifier query is added only for indexers advertising that supported movie-search parameter. No unverified IMDb query parameter is assumed.

Prowlarr's inspected official source contracts:

- [SearchResource](https://github.com/Prowlarr/Prowlarr/blob/develop/src/Prowlarr.Api.V1/Search/SearchResource.cs): query/type/indexer IDs/categories/limit/offset.
- [SearchController](https://github.com/Prowlarr/Prowlarr/blob/develop/src/Prowlarr.Api.V1/Search/SearchController.cs): forwards pagination and category lists and parses identifiers from the query.
- [NewznabRequest](https://github.com/Prowlarr/Prowlarr/blob/develop/src/NzbDrone.Core/IndexerSearch/NewznabRequest.cs): supported `{imdbid:...}`/`{tmdbid:...}` query syntax.
- [IndexerCapabilityResource](https://github.com/Prowlarr/Prowlarr/blob/develop/src/Prowlarr.Api.V1/Indexers/IndexerCapabilityResource.cs): normalized category tree, maximum limits and supported movie parameters.
- [IndexerResource](https://github.com/Prowlarr/Prowlarr/blob/develop/src/Prowlarr.Api.V1/Indexers/IndexerResource.cs): enabled/searchable/pagination capabilities. These are not tracker-local category IDs.

Only credential-free capability fields are cached in memory for five minutes, keyed by URL plus a key hash. API settings/fields/passkeys/URLs are not returned in diagnostics. On capability failure, Movie parent plus broad searching remains available and the missing evidence is disclosed.

## Bounded completeness and reliability

Maximum four concurrent query paths, three pages per path, page size ≤100 and limited by published capability maxima. Each path retains the existing six-second stage budget across its pages. Capability lookup has a two-second limit; independent Prowlarr work has an eight-second wall budget. Existing 18-second endpoint and 22-second frontend limits remain, and all child tasks are cancelled/drained on timeout/navigation. No crawler or acquisition runs when details open.

Every returned response row is evaluated up to a disclosed 2,400-row processing budget, including rows beyond the first 100. Repeated pages, lack of paging support, maximum pages, queued queries not started, failures and budget exhaustion are marked partial. A limit in one path no longer prematurely stops other paths. Bounded discovery is not a guarantee of every tracker release. Results already obtained survive sibling failures; authentication failures remain explicit. Radarr candidates survive supplementary provider failures where safe. Existing direct Prowlarr-to-Radarr exact cached-release handoff remains unchanged.

## Before and after fixture behavior

| Observed release fixture | Size (GiB) | Seeders | Before | After |
|---|---:|---:|---|---|
| Birdman 2014 1080p BluRay x265 | 1.8 | 74 | discarded by title gates | eligible |
| Birdman 2014 1080p BluRay x265-LAMA | 1.8 | 13 | discarded by title gates | eligible |
| Birdman 2014 1080p BluRay DDP5.1 x265 10bit-LAMA | 2.7 | 31 | discarded by title gates | eligible |

The composed fixture pipeline with the four original oversized official-title candidates produces **seven displayed releases: three eligible, four preset-blocked**. This result is automated fixture evidence, not a live IPTorrents verification. A suitable synced Radarr indexer and a supported exact-release link remain required for actual handoff.

## Diagnostics

An expandable **Release discovery diagnostics** section displays executed queries, category scope, page/row counts and outcomes; configured searchable indexer counts and indexers returning rows; raw response rows, duplicate rows, title/year mismatches, category exclusions, malformed rows, merged duplicates, displayed metadata/compatibility/preset exclusions and eligible results. Raw rows repeat across queries; counts describe stages, not invented tracker totals. Per-result primary rejection classes avoid double counting household versus compatibility exclusions.

Prowlarr's aggregate search response cannot prove which silent indexer was contacted or failed internally. Configured/requested/returning indexer counts are distinguished, and no category mismatch is claimed from absence alone. No private tracker names/configuration fields, API keys, GUIDs, download/magnet URLs, passkeys or exception URLs are included in the new diagnostics. Existing role-restricted deeper admin diagnostics remain.

## Tests, compatibility and release

Baseline: 380 tests passed. New deterministic tests cover all three observations, official/alternate/short identity, wrong years/IDs, unrelated TV/franchise titles, category mappings, supported identifiers, capped paging, results after the first 100, repeated pages, limits, missing metadata, deduplication, sibling failures, empty results, cancellation/task cleanup and exact-byte preset bounds. Existing Radarr/Sonarr, direct handoff, client timeouts, Setup, authentication, history/migrations and UI regressions remain in the full suite. Chromium adds an iPhone eligible-release/diagnostic view test without external APIs.

Run `python -m pytest -q`, `ruff check mediahub tests --select E9,F63,F7,F82`, `python -m compileall -q mediahub tests`, `npx playwright test` and `git diff --check`. Final totals and CI results are recorded in the PR. Existing FastAPI deprecation and advisory Starlette audit warnings are not hidden. Docker/physical iPhone/live IPTorrents checks remain unavailable locally.

Local final verification: **408 Python/DOM tests passed**, with 11 existing deprecation warnings; **16 Chromium tests passed**. Critical Ruff, compilation, all composed JavaScript syntax, version metadata and whitespace checks passed. The original four Birdman tests were observed failing before the correction and now pass. GitHub Actions is checked after PR creation.

After approved merge, back up the HA add-on, reload repository metadata, install **0.19.1**, restart and reopen MediaHub. Manifest/effective app version and changelogs are consistent; existing inline no-cache asset loading and packaging remain. No published release/tag is created, and live HA update availability is not claimed.

## Live Home Assistant acceptance

1. Confirm v0.19.1 and existing presets: 1080p/720p, maximum 3 GB (legacy binary threshold), minimum one seeder. Confirm Prowlarr and Radarr connection/indexer sync.
2. Open the **2014** Birdman with the full official title. Let automatic discovery complete, or refresh releases to bypass the short result cache.
3. Confirm the three observed short-title releases appear if still returned by the tracker, with current sizes/seeders and eligibility. Confirm oversized releases remain unavailable.
4. Expand discovery diagnostics: short/official queries, Movie/broad scopes, counts and any partial/failure indicators. Do not equate a tracker/provider limit with a complete no-match result.
5. Confirm unrelated Alcatraz/Conan/Dr Quinn results are not downloadable. Navigate Back/Close/Browse/Setup during a slow search and retry without freezing.
6. Optionally, explicitly select one eligible release. Verify exact Radarr handoff, one new request, queued/downloading/import/library stages, and no duplicate submission. Discovery alone must never download.
