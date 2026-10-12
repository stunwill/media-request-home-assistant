# MediaHub v0.19.0: mobile management and reliability

Baseline: merged main `8e117a4`, v0.18.0 (PR #69). No open PRs or published GitHub releases existed at inspection. This feature/corrective release retains the existing composed FastAPI/JavaScript architecture and acquisition integrations. No Issue, automatic merge or release tag is created.

## Assessment and confirmed root causes

- Downloads used `table-layout:fixed` and `overflow-wrap:anywhere` on every cell, while still fitting four columns into an iPhone. Dates/requesters broke character by character. The recording shows these tall rows and repeated Mutiny attempts.
- Ratings inputs were not capability-aware. Any external source could be selected even with no supported provider configured. OMDb cannot supply RT audience scores; its configuration alone is insufficient for that filter. Coverage was reported, but its zero-match wording was ambiguous when there were no usable scores.
- Account decoration observed its own subtree mutations and unconditionally rewrote unchanged source/button text. These self-generated mutations could create a continuous observer loop. Label updates are now conditional.
- Movie/TV catalogue requests used mutable global media selection when processing responses. A late request could populate the other category. Responses now remain bound to their initiating category, and switching invalidates the previous generation.
- Failed movie attempts were eligible for general library reconciliation. A later successful acquisition could make a failed row appear Available. Terminal attempts now retain their outcome.
- qBittorrent presence alone was labelled downloading, including paused/queued/checking/metadata states. These waiting states now remain queued rather than implying active transfer.

The recording contains Radarr rejection wording, not the live API response/configuration needed to establish why Radarr rejected that particular release. No speculative category/quality-profile bypass has been introduced. Existing admin-only read-only diagnostics remain the supported investigative path.

## Downloads API and responsive layout

`GET /api/download-management` returns 30 groups per page (maximum 100). It supports newest (default), oldest, title, requester, media type and status sorts; Movie/TV, requester, completed-transfer/import, downloading, failed/rejected and Available filters. Filtering applies to each group's latest request, not just the visible page. Earlier attempts remain in the expandable history. Ties use request IDs deterministically.

Groups use stored media type and stable external identity plus TV scope, season, episode and requested-season association. No title-only matching is performed. Missing legacy identities remain individual requests. One title with a different external identity cannot be accidentally grouped with another. Grouping is presentation-only: no historical request is deleted, merged or overwritten.

`GET /api/download-management/{request_id}/attempts` pages the visible group's history in batches of 20. Admin/manager visibility matches existing permissions. Requesters can only see their own records and requester choices. IDs outside that scope return 404. Existing `/api/download-history` and `/api/downloads` consumers remain supported.

At ≤760 px, compact expandable entries show title, type, requester, request time, status, known/estimated size and attempt count. Metadata appears only on expansion. At larger sizes, an eight-column table includes quality/actions with sensible minimum widths and a contained horizontal-scroll region. Dates/usernames do not wrap character by character. Failed details show recorded reasons.

Expanded fields use reliable stored evidence only: release, source, quality, seeders, manager acceptance, client transfer, import/library evidence and timestamps. Unknown dates read **Not recorded**, not a fabricated value. Historical missing fields do not break rendering. Estimated sizes are marked `~`; actual client/queue size takes precedence. The structure leaves space for future weekly statistics, but no speculative figures are added.

Polling uses the existing ten-second cadence, a single in-flight request and bounded server reconciliation. It pauses while history is expanded or the document is hidden. Refresh/filter changes cancel superseded requests; late responses cannot overwrite newer history. Saved entries remain visible during integration failures/timeouts.

## Lifecycle, evidence and retry

The existing authoritative statuses are preserved rather than introducing competing database states. Conceptual evidence is presented separately:

| Evidence | Meaning |
|---|---|
| Requested/searching | A MediaHub request exists; acquisition is not yet confirmed |
| Selected metadata | A release was recorded, not proof of handoff |
| Sent/queued | Manager accepted submission; not proof of active transfer |
| Downloading | Client activity or manager transfer status confirms it |
| Transfer completed | Client completion timestamp or first observed confirmed manager completion |
| Imported | Media-manager file metadata provides an import timestamp |
| Available | Media-manager library file availability is verified, including while seeding |
| Failed/rejected/cancelled/timed out | Attempt did not complete successfully; earlier records are retained |

Client 100% remains waiting for import, never automatically Available. First observations of actual transfer/completion are timestamped in UTC; existing timestamps use COALESCE and are not replaced. The frontend uses local timezone formatting; browser tests use Australia/Melbourne with daylight saving. Old dates are backfilled only from actual matching audit events. An availability audit timestamp is an observation, not an invented historical import timestamp.

Additive fields: `selected_release_quality`, `selected_release_seeders`, `sent_at`, `failure_json`. Existing source/size fields are reused. Historical quality/source and sent times can be recovered from actual audit payloads. Fresh movie failures retain integration/category/recorded response code/description/time. Unknown historical codes/times stay absent. URLs and obvious credential assignments are sanitized in management output. The v0.18 cross-process migration lock remains authoritative; fresh/repeated/upgrade initialization preserves records.

**Retry is deliberate fresh discovery review, not replay.** Supported failed Movie entries open current details/releases with current presets. The user must explicitly select/confirm an eligible release; the existing downstream and active-acquisition guards remain. A new confirmed attempt creates its own record. Permanent rejection is not automatically retried. TV retry orchestration and direct one-click automatic retry are deferred: scope/episode selection and uncertain downstream acceptance must be reviewed rather than guessed. Existing normal TV acquisition remains available.

## Ratings availability and coverage

Authenticated `GET /api/ratings/availability?media_type=movie|tv` reports source capability, configured state and fresh verified cached title counts, never keys or raw external errors. TMDb remains usable without additional subscriptions. IMDb/RT critics/Metacritic can use supported MDBList or OMDb data. RT audience/Letterboxd/Trakt require MDBList or fresh verified cached records. Per-title/free-account availability is not guaranteed.

Unavailable source controls and source sort options are disabled with a reason. Administrators get a Setup action; other users get administrator guidance. Persisted unavailable criteria must be cleared/configured rather than silently applied. Server discovery independently rejects unavailable-source filters/sorts before requesting candidates, so bypassing the UI does not turn unavailable data into genuine zero matches.

Results expose `results`, `partial`, `no_matches`, `ratings_unavailable`, `enrichment_required` or `provider_error`. Coverage includes inspected, verified, awaiting, unavailable, expired, failed, outside-range, missing-excluded and per-selected-source verified counts. Inclusion of unrated titles remains explicit and labelled; results with unverified titles are not described as wholly verified matches. Missing scores are never zero. Enrichment and verified caches remain the bounded v0.18 asynchronous workflow, not a synchronous crawler. Source counts cover the actual inspected dataset; external filtering still does not claim exhaustive TMDb coverage.

## Filter keyboard and navigation

Mobile filters use a full-screen flex panel with fixed heading/actions and independently scrolling fields. VisualViewport height/offset adjusts the panel when a keyboard reduces usable space. Numeric controls request numeric/decimal keyboards; focused controls scroll into view. **Done typing** blurs the input, and Apply restores focus to Filters after validation/closing. Desktop retains a modal panel. Selected applied filters and search persist during details/media navigation and are saved to user-scoped localStorage on successful apply/page hide; no secrets or account credentials are stored there.

Existing compact hamburger navigation retains Browse/Downloads/Watchlist/role-authorized Users/Setup. The empty competing More element is hidden. Detail Back/Close and in-flow notifications remain, with notifications outside navigation and dismiss buttons. Release-area scrolling accounts for the sticky detail toolbar.

## Release search reliability

The 18-second server and 22-second client wall limits are retained, not increased to hide slow providers. Existing async disconnect cancellation, task draining, timers, generation checks, shared search guards and short result caching remain. Movie results distinguish eligible, rejected-only and no candidates. Best request is disabled while loading or without eligible candidates. Actual backend rejection details, including legacy reasons, are expandable. TV has explicit searching/results/rejected-only/empty/cancelled/timeout/error states and a cancel action.

Only actual operations are described: searching the media manager, evaluated eligible/rejected counts. No invented progress percentage/stage is added. Manager acceptance, client activity and media availability remain separate concepts. Admin read-only Radarr/Prowlarr diagnostics do not bypass the established acquisition workflow.

## Users and security

Existing users occupy a compact responsive list. Account creation is collapsed in its own panel by default. Create/update/password/activation controls prevent simultaneous duplicate submissions, report validation/duplicate usernames/permission/server errors and clean up loading state. Existing Home Assistant/MediaHub dual-login actions remain. Administrative APIs retain their original dependency authorization and CSRF/session handling. Passwords are not logged or returned, and account preference persistence excludes them.

## Unexpected Home Assistant transition investigation

Closer frame inspection confirms the transition around 132–135 seconds: after Users remains on Loading users, the HA splash screen appears, then its dashboard/navigation drawer. The user returns to MediaHub afterwards. This is an observed host/WebView reload, but the recording cannot establish whether it was app termination, a host action, authentication or a browser process failure. The Users self-triggering observer loop is a confirmed defect and a plausible contributor, not a proven cause of this reload.

Source inspection found no parent-location assignment, history.back call or page reload in MediaHub navigation actions; API requests remain ingress-relative. Browser tests navigate inside a simulated HA iframe, check the corrected Users behavior and assert the parent URL remains unchanged. No reproducible MediaHub-generated HA redirect is claimed or speculatively intercepted. The host splash/reload itself remains a live-device investigation risk.

`window.MEDIAHUB_NAVIGATION_DIAGNOSTICS()` exposes up to 30 local-only event records: view, time, detail-open and pagehide/pageshow/popstate/frontend-error categories. It excludes URLs, message contents, titles, identities and tokens and sends nothing to a server. It can help distinguish a host/back gesture from an app exception in a subsequent live reproduction. It cannot observe HA parent navigation directly. Actual HA/WebView reproduction remains manual.

## Verification, upgrade and remaining risks

Run `python -m pytest -q`, `ruff check mediahub tests --select E9,F63,F7,F82`, `python -m compileall -q mediahub tests`, `node --check mediahub/app/assets/management.js`, and `npx playwright test`. CI installs Chromium, runs browser tests and retains screenshots. Tests are mocked and do not need live/paid keys. Requested 375×667, 390×844, 393×852, 430×932, 768×1024 and 1920×1080 management viewports plus previous narrow/landscape layouts are covered. Keyboard tests simulate reduced VisualViewport, not a real iOS keyboard.

After approval/merge, back up the add-on, reload repository metadata, install v0.19.0, restart and reopen. The HA manifest and effective app version agree; inline assets inherit existing no-cache HTML headers and the Docker COPY includes the new assets. This PR creates no tag/published release and does not claim live HA update availability. Docker is not available locally for multi-architecture image builds.

Existing baseline Starlette dependency advisories remain visible in the advisory CI audit. Passing that job under the established policy is not a clean security audit. Framework upgrades are not hidden inside this focused release.

Final local checks: 380 Python/DOM tests and 15 Chromium tests passed, with 11 existing FastAPI/event deprecation warnings. Critical lint, compileall, JavaScript syntax and whitespace checks passed. GitHub Actions results are recorded in the PR after publication.

Manual acceptance before deployment:

- [ ] Physical iPhone Safari/HA WebView: filter keyboard, safe areas, long title/detail scrolling, Back/Close, notifications/menu.
- [ ] Real Downloads: groups preserve histories/requesters, filters/sorts/pages, size/progress, paused/transferring/imported/seeding, failed reasons and deliberate retry.
- [ ] Real provider keys: supported sources, cache-only coverage, pending/error/quota feedback, fresh verified AND matches.
- [ ] Live Radarr/Sonarr/Prowlarr/qBittorrent/Plex regression and read-only diagnostics.
- [ ] Users: requester/manager/admin restrictions, duplicate usernames, account/login/reset feedback.
- [ ] Actual HA backup/upgrade/restart and aarch64/amd64/armv7 image build.
- [ ] Reproduce any HA dashboard transition with the local diagnostic events and host/browser context.
