# Administrator movie size overrides, v0.20.0

## Access and use

MediaHub already supports local administrator accounts and administrator role assignment. Every active authenticated MediaHub administrator can use this feature. Requesters and managers cannot use it. No owner allowlist, new environment variable or schema migration is needed. Home Assistant ingress access by itself does not grant this permission.

An existing administrator can open **More → Users**, select **Administrator** in the role selector on an existing user's card, or create a new MediaHub account with **Role → Administrator**. Local accounts need a username and a password of at least 12 characters. Role changes use the existing protected API and cannot be performed by ordinary users. The installation retains its existing last-administrator protections.

Open a movie's **Unavailable releases** section. A release rejected solely because it exceeds MediaHub's configured maximum movie size has an **Allow size-limit override** button for admins. The release remains excluded from automatic best-release selection. Its row shows the release title, size, quality, indexer and reported seeders.

The button opens an inline confirmation showing the selected title, actual reported size and configured limit. **Cancel** submits nothing. **Download with size override** sends that exact selection through the established request lifecycle. Reported seeders may be stale and cannot guarantee transfer availability. The application currently has no verified live seeder-freshness timestamp to display.

For example, the 6.26 GB CMRG release of *The Killing of Two Lovers* can be explicitly approved against a 3 GB MediaHub preset if identity and all other applicable requirements pass. A stalled smaller torrent can still trigger existing active-request or Radarr queue protection. This feature does not cancel an existing download or bypass duplicate detection.

## Rules and security

- `MovieRequestCreate.allow_size_override` defaults to false. It is request-scoped and never saved as a household preference.
- The effective request handler requires an authenticated admin and an explicit release token before external integration calls.
- Selections remain opaque, expiring, single-use, and bound to the requesting user and selected movie. Ordinary download tokens and size-override tokens are presented separately.
- The server uses cached provider metadata and fresh household rules, never client-supplied size, role or eligibility. A changed maximum-size preset requires a fresh search and confirmation.
- Movie identity, resolution, existing fallback rules, seeders, source mapping, Radarr restrictions, duplicate protection and storage reservations remain enforced. An override only skips MediaHub's maximum movie size comparison.
- Radarr search selections are refreshed before acquisition. Changed size, title or identity is rejected. Direct Prowlarr selections preserve the existing exact cached handoff, with fresh metadata identity and indexer-mapping validation, followed by Radarr's push evaluation. They do not repeat the tracker search at submission time.
- No global Radarr profile, setting or MediaHub preset is changed. Radarr can still reject an approved size override.
- The UI retains its existing submission lock, deadline, cancellation handling and navigation recovery. Database duplicate protection remains the final guard against concurrent submissions.

## Diagnostics and audit

Oversized releases remain household exclusions and do not increase the normal eligible-release count. Administrator diagnostics separately report `size_override_candidates`, a subset of excluded candidates. Non-admin release responses omit the override action fields and token.

The existing `movie_request_created` audit records the acting user, timestamp, movie ID, selected release title, indexers, release size, configured maximum and explicit override approval. A SHA-256 digest identifies the selected provider GUID without disclosing a tracker URL. This audit is linked by request ID to the existing queued, storage-rejected or submission-failed outcome. Confirmed grabs also record `size_override_approved`.

Where Radarr returns rejection reasons for a pushed release, the existing error response now includes those reasons after redacting URLs and credentials. Other service failures retain the existing unconfirmed-submission handling.

## Files changed

| Files | Purpose |
|---|---|
| `main.py` | Request approval flag and size-only override detection in the shared Radarr policy. |
| `enhanced_main.py` | Admin enforcement, exact selection validation, fresh Radarr checks and request audit evidence. Preserve strict HD size-only candidates during recent-release fallback discovery. |
| `runtime.py` | Prowlarr size-only detection and authoritative selection caching. |
| `release_identity_main.py` | Retain override selections only after identity acceptance; expose separate override token and configured limit. |
| `release_lifecycle.py` | Hide restricted fields from non-admins, count override candidates separately and render the excluded-release action. |
| `feature_ui.py` | Cancellable confirmation, explicit approval payload, shared submission guard and server rejection feedback. |
| `media_services.py` | Preserve sanitised downstream Radarr push rejection reasons. |
| `mobile_management.py`, `prowlarr_discovery.py`, `config.yaml` | Runtime/add-on version 0.20.0 and discovery client identification. |
| Python and UI tests | Access, one-time approval, other restrictions, stale/modified selections, concurrency, audit, reported movie, Radarr refresh, storage and mobile confirmation. Update existing version contracts. |
| Root/add-on changelogs, README, ROADMAP | Release and usage notes. |

## Validation

Validation results are recorded in the pull request. Tests use mocked providers and a temporary database. Live tracker transfer, installed household account roles and Home Assistant update discovery need verification on the household installation after merge and publication. No merge, deployment, live download or account-role change is performed by this PR.
