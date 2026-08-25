# Plex library intelligence

MediaHub v0.9.0 adds Plex as an optional library-awareness integration. Plex is not required for Browse, Downloads, requesting, release selection, Radarr import, qBittorrent progress, or authentication.

## Configuration

Administrators can configure a Plex server URL, write-only Plex token, optional movie-library key, and optional machine identifier. The token remains server-side and is never returned in setup payloads, audit details, errors, logs, or generated browser links.

## Matching

MediaHub normalises Plex GUID metadata and matches movies conservatively:

1. TMDb ID exact match.
2. IMDb ID exact match.
3. Title plus exact release year only when stable identifiers are unavailable.

Multiple matching candidates are classified as ambiguous and are not considered playable. MediaHub prefers no Plex action over a potentially incorrect match.

## Cache

The configured Plex movie library is cached in memory for ten minutes. Opening individual Browse cards does not cause a separate Plex library scan. When a refresh fails temporarily, previously cached library metadata may be used and marked stale. Saving Plex integration settings clears the local cache.

The Home Assistant Ingress and external login listeners are separate processes, so each process maintains its own bounded in-memory cache.

## Library state

Movie details keep request/download, Radarr import, and Plex availability distinct. A movie can be successfully imported by Radarr while Plex is still scanning or unavailable. Plex outages never convert a successful Radarr import back to downloading or failed.

Pre-existing Plex movies do not require a MediaHub request record. If TMDb or IMDb identity proves a Browse movie already exists in Plex, the shared movie-details UI reports it as available and removes inappropriate request controls.

## Watch in Plex

When MediaHub has both a confident match and a Plex machine identifier, it creates a token-free `app.plex.tv` details link for the exact Plex rating key. Authentication tokens are used only for server-side Plex API requests and are never inserted into browser URLs.

## Security

Plex configuration follows MediaHub's existing integration boundary:

- configuration changes require the administrator role;
- service URLs reject embedded credentials, query strings, and fragments;
- tokens are stored in the private runtime settings file;
- public settings expose only a `token_set` boolean;
- Plex error messages are sanitised;
- no arbitrary external URL from Plex metadata is sent to the browser;
- generated Plex links are constructed from validated internal identifiers rather than upstream URL fields.
