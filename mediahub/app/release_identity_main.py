from __future__ import annotations

from typing import Any

from . import enhanced_main, main, preset_main, release_identity, tv_release_selection

app = preset_main.app
app.version = "0.13.0-dev"

_original_search_movie_releases = enhanced_main.search_movie_releases
_original_request_movie = enhanced_main.request_movie
_original_season_releases = tv_release_selection.season_releases
_original_episode_releases = tv_release_selection.episode_releases


def _strip_token_if_rejected(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    if not result.get("eligible"):
        result.pop("release_token", None)
    return result


async def search_movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    user_id: str,
    *,
    movie: dict[str, Any] | None = None,
):
    tmdb, radarr, _ = main.configured_clients(main.load_options())
    if movie is None:
        movie = await tmdb.details(tmdb_id)
    radarr_movie = await radarr.ensure_movie(tmdb_id)
    releases = await radarr.releases(int(radarr_movie["id"]))

    evaluated: list[dict[str, Any]] = []
    for release in releases:
        identity = release_identity.validate_movie_release(movie, release)
        public = main.release_with_policy(release, rules)
        public["recent_quality_fallback"] = False
        public = release_identity.apply_identity(public, identity)
        if public["eligible"]:
            public["release_token"] = main.cache_release(tmdb_id, user_id, release)
        evaluated.append(public)

    if any(item["eligible"] for item in evaluated) or not enhanced_main.is_recent_movie(movie):
        return radarr_movie, evaluated, False

    fallback_public: list[dict[str, Any]] = []
    for release in releases:
        identity = release_identity.validate_movie_release(movie, release)
        public = enhanced_main.recent_fallback_policy(release, rules)
        public = release_identity.apply_identity(public, identity)
        if public["eligible"]:
            public["release_token"] = main.cache_release(tmdb_id, user_id, release)
        fallback_public.append(public)
    return radarr_movie, fallback_public, any(item["eligible"] for item in fallback_public)


async def season_releases(tmdb_id: int, season_number: int, principal: main.CurrentUser) -> dict[str, Any]:
    result = await _original_season_releases(tmdb_id, season_number, principal)
    snapshot = await tv_release_selection._season_snapshot(tmdb_id, season_number)
    series_title = str(snapshot.get("series_title") or "")
    updated = []
    for item in result.get("releases", []):
        identity = release_identity.validate_tv_release(
            series_title=series_title,
            release={"title": item.get("title")},
            season_number=season_number,
            episode_number=None,
            structured_full_season=bool(item.get("is_season_pack")),
        )
        merged = release_identity.apply_identity(item, identity)
        updated.append(_strip_token_if_rejected(merged))
    result["releases"] = updated
    return result


async def episode_releases(
    tmdb_id: int,
    season_number: int,
    episode_number: int,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    result = await _original_episode_releases(tmdb_id, season_number, episode_number, principal)
    snapshot = await tv_release_selection._season_snapshot(tmdb_id, season_number)
    series_title = str(snapshot.get("series_title") or "")
    updated = []
    for item in result.get("releases", []):
        identity = release_identity.validate_tv_release(
            series_title=series_title,
            release={"title": item.get("title")},
            season_number=season_number,
            episode_number=episode_number,
        )
        merged = release_identity.apply_identity(item, identity)
        updated.append(_strip_token_if_rejected(merged))
    result["releases"] = updated
    return result


enhanced_main.search_movie_releases = search_movie_releases
preset_main._original_search_movie_releases = search_movie_releases

# Replace registered handlers so the deployed routes use the identity-aware layer.
for route in app.routes:
    if getattr(route, "path", None) == "/api/catalog/tv/{tmdb_id}/seasons/{season_number}/releases":
        route.endpoint = season_releases
        route.dependant.call = season_releases
    elif getattr(route, "path", None) == "/api/catalog/tv/{tmdb_id}/seasons/{season_number}/episodes/{episode_number}/releases":
        route.endpoint = episode_releases
        route.dependant.call = episode_releases
