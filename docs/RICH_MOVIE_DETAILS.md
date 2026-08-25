# Rich movie details

MediaHub v0.8.0 adds a shared movie-details presentation for Browse and Downloads while preserving the v0.7.0 release-lifecycle and request stack.

## Metadata model

TMDb movie details are fetched server-side using supported append responses. The normalised movie payload retains title, synopsis, poster/backdrop, runtime, genres, TMDb rating, Australian release records and certification, safe external IDs, director, trailer, and primary cast. Cast entries retain the TMDb person ID, character and optional profile image.

MediaHub does not fabricate ratings. TMDb scores are displayed directly. When TMDb provides an IMDb ID, MediaHub can safely link to the corresponding IMDb title page, but no IMDb score is shown without a configured data source. Rotten Tomatoes is not scraped.

## Actor discovery

Free-text Browse search continues to support the existing actor-name fallback. Once a cast member has been selected from movie details, MediaHub instead uses the stable TMDb person ID through `GET /api/catalog/people/{person_id}/movies`, which maps to TMDb movie discovery using `with_cast`.

Actor results reuse the normal Browse movie cards, so resulting movies can be opened and requested normally. A **Back to movie details** action restores the movie that initiated actor discovery.

## Downloads context

`GET /api/downloads/{request_id}/details` checks the current user's role or ownership before returning rich movie metadata. The same frontend renderer is used as Browse, but the Downloads context suppresses request, release-picker and watch-for-release actions. It adds only sanitised request/library information including request owner, request timestamp, current state/progress, selected release title, estimated size and library availability.

Release GUIDs, torrent hashes, credentials, API keys and session details are not exposed by this endpoint.

## Accessibility and responsive behaviour

Cast entries are native buttons, rating links have source-specific accessible labels, Downloads cards are keyboard operable, Escape closes the modal, and focus is returned to the control that opened it. The cast and ratings layouts collapse for smaller Home Assistant/mobile viewports.

## Plex investigation

The current MediaHub repository has no Plex URL, token, machine identifier or Plex library client. v0.8.0 therefore does not attempt title-only Plex matching or construct speculative deep links. A future optional Plex integration should match by stable TMDb/IMDb GUID metadata first and must degrade cleanly when Plex is unavailable.
