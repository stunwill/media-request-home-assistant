# MediaHub v0.19.3: release interaction freeze

Baseline: merged main `1de02bcdd9c7532be09e890a10183e15f8072cd0`, v0.19.2.
PRs #70, #71 and #72 are merged; no open PRs were returned at investigation start.
The #70 diff introduced the second movie badge writer; #71 and #72 changed discovery and its diagnostics but did not resolve this interaction. Their merged behavior is retained.

Next corrective version: **0.19.3**. No separate Issue, merge, tag or release publication.

## Confirmed cause and before evidence

The composed page, rather than a single source fragment, reproduces a deterministic main-thread freeze after activating an eligible release. The fixture uses The Weight (2026), a long synopsis and 25 eligible releases through a simulated Home Assistant iframe. Its movie ID, tokens, indexer and backend responses are synthetic. This is not a live tracker or physical iPhone reproduction.

1. `release_lifecycle.findReleases` creates real button listeners for each `data-token` selection.
2. Hit testing returns the Download button itself. Playwright delivers the click.
3. `feature_ui.submitRequest` sets `button.disabled=true`, changes its text and invokes the authenticated API helper.
4. `mobile_live_ui.compactReleaseArea` chooses BEST MATCH using both `data-eligible` and the temporary disabled property. It removes the first card's badge and may move it to another card.
5. `management.js`'s `releaseAreaObserver` still sees the first card's authoritative `data-eligible=true` and restores its badge.
6. Those child mutations schedule both observers again. A diagnostic observer counted **1,001 child mutations** while the selected card was disabled but still eligible. The animation frame that would previously recompute eligibility cannot run because microtasks never settle.
7. The browser cannot paint processing feedback, resolve the click, service normal timers or dispatch subsequent navigation. Scrolling can advance compositor content without a corresponding settled application render.

The baseline Chromium click timed out after 30 seconds, with its action log stopped at “performing click action”. Baseline WebKit also failed the interaction regression. This establishes a sufficient code-level cause matching the silent button and unresponsive navigation. There is no evidence here that Radarr caused the freeze.

Baseline event tracing records `button_click_received`, `fetch_invoked`, `network_request_observed`, then `pending_child_mutations_exceeded_1000`. The authenticated API request is emitted in this reproduction; its feedback cannot be processed while the observer loop runs. This mock request does not establish whether a live acquisition reached Radarr. Always check Downloads before retrying an unconfirmed operation. No production network trace is available to determine whether the user's individual taps reached their backend.

The movie title is retained in the DOM in the reproduction. After removing the loop, scrollTop zero exposes the full title below the toolbar, navigation hit targets match their controls and scroll width fits the dialog on all tested sizes. No independent DOM removal, hidden backdrop, overflow clipping, ingress interception or CSS hitbox defect was established. The exact missing-content appearance on the physical phone remains a manual acceptance item; no speculative viewport or z-index workaround is included.

A separate confirmed response defect: `submitRequest` treated any resolved HTTP 200 as acceptance. The backend can return `{request:{status:'rejected'},storage:{accepted:false}}`. A baseline best-release action regression demonstrates the false-success path independently of the release-card badge loop.

## Correction and affected functions

| File | Functions or responsibilities |
|---|---|
| `mediahub/app/mobile_live_ui.py` | `compactReleaseArea`: sole movie BEST MATCH decorator; eligibility comes from evaluated candidate data, never a temporary disabled button. |
| `mediahub/app/mobile_ux_ui.py` | `improveReleaseCards`: preserve authoritative eligibility; remove legacy blanket disabling of unrelated release-area controls. |
| `mediahub/app/assets/management.js` | `releaseAreaObserver`: remove competing badge writer; respect `aria-busy` on the best-release action. |
| `mediahub/app/release_activity.py` | `decorateReleaseResults`: rejected decoration/divider uses policy eligibility, not submission state. |
| `mediahub/app/feature_ui.py` | `submitRequest`, `cancelDetailWork`, `cancelMovieSubmission`, recovery `findReleases`, `releaseFeedback`, `downloadTrace`: bounded submission lifecycle, accessible processing, response validation, inline feedback/recovery, generation fencing and diagnostics. |
| `mediahub/app/movie_release_endpoint.py` | `request_movie`: validated correlation IDs and bounded per-submission outcome/cleanup logging around the existing authoritative workflow. |
| Tests / CI | `download_interaction.spec.cjs`, `test_download_interaction.py`, updated eligibility assertion, Chromium/WebKit projects and browser dependencies. |
| Version metadata | Final app version, add-on manifest, discovery User-Agent, existing version assertions, README, roadmap and both changelogs. |

There is no schema migration, dependency change or household preset change. No acquisition endpoint, identity rule, token ownership/expiry/consumption rule or direct Prowlarr-through-Radarr validation is relaxed. No direct client download is added.

## Submission and recovery semantics

- Valid activation synchronously disables the selected button, sets `aria-busy`, labels it Sending request and displays local status before awaiting network work.
- The existing global submission guard prevents duplicate acquisition even if synthetic events bypass the native disabled guard. It does not lock navigation or global pointer events.
- The exact selected token is sent through the existing ingress-relative API helper, session authentication and CSRF handling.
- Acceptance requires a recognised backend request status. Rejected storage and empty/malformed HTTP 200 responses never become success.
- Success displays confirmation and opens the existing Downloads view. Rejection gives local, persistent feedback beside the selected release plus an accessible notification and reference ID.
- A 22-second client wall covers fetch and response parsing. Existing server handoff limits remain 18 seconds. Timer, submission state and accessible button state are cleaned in `finally`.
- Closing, navigating or opening another title cancels obsolete client observation. A late promise cannot close or overwrite the next view. Aborting a request does not prove Radarr rejected it.
- Timeout, lost network, server uncertainty or cancellation fences that movie for the current page lifetime. Another tap does not automatically resubmit. The user must review Downloads/Radarr, then explicitly confirm fresh discovery before a new acquisition. Refresh bypasses discovery cache; the exact consumed token is never automatically replayed.
- Definitive rejection offers Refresh releases and Review Downloads. Server tokens are single-use, so a fresh selection is the supported retry route.
- Ordinary household users receive categorised errors rather than raw provider messages or credentials. Authentication and permission failures have specific guidance.

## Diagnostics and security

`window.MEDIAHUB_DOWNLOAD_DIAGNOSTICS()` returns a local-only ring of at most 60 events: interaction, request start, completion/failure and cleanup. Fields are random correlation ID, current view, numeric movie ID, exact/best selection state, status/category and elapsed milliseconds. It includes no release token, title, tracker URL, user identity, cookie or credentials. Existing navigation diagnostics remain local and bounded; no scroll event logging is added.

The server accepts only a strict hexadecimal/UUID correlation format, otherwise generates its own. Two structured log entries per request contain the safe correlation, numeric movie ID, selection type, outcome, HTTP status, duration and cleanup. Exceptions and payloads are not interpolated into these logs. No diagnostic endpoint or administrative permission is added. Existing admin-only discovery diagnostic enforcement remains intact.

The full suite retains authenticated, user-bound token validation, active-request uniqueness, exact Prowlarr-to-Radarr handoff, Sonarr, cancellation/storage reservation cleanup, history, presets and partial discovery tests. No new authentication bypass or additional data exposure was found in the focused changes. Existing dependency advisories are outside this correction; no clean dependency audit is claimed.

## Automated verification

- Unchanged main: **446 Python/DOM tests passed**.
- Baseline interaction: Chromium click freezes after correct hit-test; diagnostic observer records 1,001 mutations. WebKit before-test failures confirm the same interaction defect.
- Baseline best-release/storage test: HTTP 200 rejection triggers the old false acceptance path.
- Final Python/DOM suite: **452 passed**, 11 existing deprecation warnings. Critical Ruff, compilation, every composed inline script and app/add-on/release metadata checks passed. Final Playwright suite: **105 passed** (61 Chromium, 44 WebKit), including all existing 17 Chromium checks.

Browser regression coverage includes real touch input, repeated synthetic clicks, one and 25 eligible releases, exact token and CSRF headers, acceptance/history, rejection/retry, storage rejection, malformed response, 401/422/500/network errors, virtual-time 22-second timeout, uncertain-outcome fencing, late submission, unchanged title DOM and automatic-search scroll preservation. All five Browse/Downloads/Setup/Back/Close controls are hit-tested during search, submission, rejection, cancellation and after scrolling. The parent ingress URL is retained.

Chromium and Linux Playwright WebKit cover 393×852 portrait, 852×393 landscape, 320×740 narrow mobile, 768×1024 tablet and 1440×900 desktop. Existing Chromium layout and management suites remain. Linux WebKit is engine-level coverage, not physical iPhone Safari or Home Assistant WebView certification. The simulated HA parent includes its viewport meta tag. An earlier mock without it caused WebKit touch coordinates to hit the document root; event tracing identified and corrected that harness error. Local WebKit runtime dependencies required an extracted library path; CI installs official Playwright Chromium/WebKit dependencies normally.

## Home Assistant delivery

The effective FastAPI app and `mediahub/config.yaml` both declare 0.19.3. `repository.yaml` retains the existing repository URL and add-on identity. The Dockerfile copies the full `app` tree, including composed UI assets; HTML retains existing `Cache-Control: no-store` behavior. The existing source-built add-on has no prebuilt image field or separate publishing workflow. CI validates metadata and now executes the WebKit regressions as well.

After approved merge through the normal project process, Home Assistant must fetch updated repository metadata, build/install the new add-on and restart it. This PR does not publish an update, and neither actual update discovery nor multi-architecture Docker builds are verified in this environment.

## Physical iPhone / Home Assistant acceptance

- [ ] Back up the add-on, refresh repository metadata after approved merge and verify that the offered and running version is 0.19.3.
- [ ] On iPhone 15 Pro through HA ingress, open The Weight (2026), wait for releases and scroll to BEST MATCH.
- [ ] Explicitly acquire one eligible release. Confirm immediate Sending state, one request, correct selected title/quality/source, success and Downloads progress.
- [ ] Repeat taps while processing; verify one Radarr handoff. Check both Radarr and Downloads before retrying any uncertain submission.
- [ ] Exercise a definitive rejection and Refresh releases recovery. Confirm no success notification and restored controls.
- [ ] Under a slow/interrupted connection, navigate away during submission, inspect Downloads and verify that late completion does not replace the next page.
- [ ] Scroll to the bottom and back to the title, expand diagnostics, rotate portrait/landscape and check all information, safe areas, HA header and horizontal bounds.
- [ ] Use Browse, Downloads, Setup, Back and Close before/during discovery, during submission and after rejection/cancellation/scrolling.
- [ ] Switch movies quickly during discovery; verify no stale release results. Confirm movie/TV discovery, existing presets, Sonarr/Radarr/Prowlarr, partial results, authentication and download history.

No real household acquisition or physical device test was performed from this development environment.
