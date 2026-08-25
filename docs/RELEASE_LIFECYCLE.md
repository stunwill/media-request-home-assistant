# Release-aware movie lifecycle

MediaHub treats movie metadata discovery and downloadable-media availability as separate concepts.

## Regional release data

Movie details request TMDb `release_dates` alongside credits, videos, and external IDs. MediaHub currently uses `AU` as the application default region because the deployed installation is Australian. Regional records take precedence over TMDb's generic `release_date` when identifying theatrical, digital, and physical milestones.

TMDb release types used by MediaHub are:

- 2 and 3: theatrical or theatrical limited
- 4: digital
- 5: physical

The release records are interpreted as signals, not guarantees that a particular release quality exists on an indexer.

## Lifecycle states

MediaHub exposes user-facing behaviour equivalent to:

- Announced
- Theatrical upcoming
- In cinemas
- Digital release upcoming
- Digital available
- Physical release upcoming
- Physical available
- Released, availability unknown

A trailer, poster, synopsis, cast record, or TMDb entry never changes `media_available` by itself.

## Search behaviour

Clearly announced and pre-theatrical titles do not automatically trigger a release search. Users can always use **Search anyway** to run the normal search path immediately.

For watched titles the scheduler uses a conservative cadence:

- announced: about every 14 days
- more than 60 days before theatrical release: about every 14 days
- 15–60 days before theatrical release: about every 7 days
- within 14 days of theatrical release: about every 2 days
- in cinemas: about every 2 days
- more than 30 days before a known digital release: about every 7 days
- 8–30 days before a known digital release: about every 2 days
- within 7 days of a known digital release: about every 12 hours
- digital/physical available or release availability unknown: about every 12 hours while still watched

The scheduler wakes once per minute only to locate due rows. It groups due watches by TMDb movie and performs at most one upstream search for that title during the cycle, even when multiple users are watching it.

## Existing recent-release fallback

Lifecycle awareness sits in front of, rather than replacing, the existing recent-release rules. Once a title is in a reasonable search window, existing Radarr, Prowlarr, quality, size, seeder, storage, duplicate-request, and CAM/TS fallback rules remain authoritative.

The important difference is that a movie merely being in the current calendar year no longer causes automatic pre-theatrical searches. Manual **Search anyway** can still exercise the existing fallback for unusual early releases.

## Persistence and migration

The `movie_watches` table is created with `CREATE TABLE IF NOT EXISTS` during startup. Existing users, requests, audits, downloads, and authentication tables are not rebuilt or replaced.

Each user can watch a given TMDb movie once. Multiple users can watch the same movie. Due processing groups those rows to avoid duplicate upstream traffic.

Watch rows store lifecycle state, selected regional dates, release preferences, last and next check timestamps, whether a qualifying result has been observed, and an optional future request ID.

## Search diagnostics

Release searches expose a concise state:

- `deferred_upcoming`: automatic search intentionally avoided because the title is too early
- `no_indexer_results`: configured sources returned no releases
- `all_rejected`: releases were returned but policy rejected every result
- `results`: at least one qualifying release exists

Detailed rejection information remains in the release result and application logs. User-facing text stays concise.
