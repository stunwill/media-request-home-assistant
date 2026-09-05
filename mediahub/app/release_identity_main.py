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


def _movie_policy_public(release: dict[str, Any], rules: main.ReleaseRules) -> dict[str, Any]:
    result = dict(release)
    details = [
        release_identity.classify_arr_rejection(reason, service="Radarr")
        for reason in release.get("rejections") or []
    ]
    quality = str(release.get("quality") or "").casefold()
    size_gb = float(release.get("size_gb") or 0)
    seeders = release.get("seeders")
    quality_mode = "1080p_only" if rules.require_1080p is True else rules.quality_mode

    if quality_mode == "1080p_only" and "1080" not in quality:
        details.append(release_identity.rejection_detail(
            "mediahub_policy", "MediaHub requires a 1080p release", code="movie_resolution"
        ))
    elif quality_mode == "720p_only" and "720" not in quality:
        details.append(release_identity.rejection_detail(
            "mediahub_policy", "MediaHub requires a 720p release", code="movie_resolution"
        ))
    elif quality_mode == "720p_and_1080p" and not any(resolution in quality for resolution in ("720", "1080")):
        details.append(release_identity.rejection_detail(
            "mediahub_policy", "MediaHub requires a 720p or 1080p release", code="movie_resolution"
        ))

    if not size_gb:
        details.append(release_identity.rejection_detail(
            "indexer_availability", "Release size is unavailable", code="size_unavailable"
        ))
    elif size_gb > rules.maximum_size_gb:
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            f"Exceeds {rules.maximum_size_gb:g} GB Movie limit",
            code="movie_maximum_size",
        ))

    if seeders is None:
        details.append(release_identity.rejection_detail(
            "indexer_availability", "Seeder count is unavailable", code="seeders_unknown"
        ))
    elif int(seeders) < rules.minimum_seeders:
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            f"Release has fewer than {rules.minimum_seeders} seeders",
            code="movie_minimum_seeders",
        ))

    if not release.get("download_allowed", True):
        details.append(release_identity.rejection_detail(
            "arr",
            "Radarr does not allow this release to be downloaded",
            code="radarr_download_not_allowed",
            service="Radarr",
        ))

    release_identity.with_rejection_details(result, details)
    result["eligible"] = bool(release.get("approved")) and not result["rejection_details"]
    result.pop("info_hash", None)
    result.pop("guid", None)
    return result


def _recent_fallback_public(release: dict[str, Any], rules: main.ReleaseRules) -> dict[str, Any]:
    result = dict(release)
    details: list[dict[str, Any]] = []
    size_gb = float(release.get("size_gb") or 0)
    seeders = release.get("seeders")

    if not enhanced_main._is_low_quality_release(release):
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            "Not a supported recent-release fallback quality",
            code="recent_fallback_quality",
        ))

    for reason in release.get("rejections") or []:
        text = str(reason)
        if enhanced_main._only_quality_rejections([text]):
            continue
        details.append(release_identity.classify_arr_rejection(text, service="Radarr"))

    if not size_gb:
        details.append(release_identity.rejection_detail(
            "indexer_availability", "Release size is unavailable", code="size_unavailable"
        ))
    elif size_gb > rules.maximum_size_gb:
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            f"Exceeds {rules.maximum_size_gb:g} GB Movie limit",
            code="movie_maximum_size",
        ))
    if seeders is None:
        details.append(release_identity.rejection_detail(
            "indexer_availability", "Seeder count is unavailable", code="seeders_unknown"
        ))
    elif int(seeders) < rules.minimum_seeders:
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            f"Release has fewer than {rules.minimum_seeders} seeders",
            code="movie_minimum_seeders",
        ))
    if not release.get("download_allowed", True):
        details.append(release_identity.rejection_detail(
            "arr",
            "Radarr does not allow this release to be downloaded",
            code="radarr_download_not_allowed",
            service="Radarr",
        ))

    release_identity.with_rejection_details(result, details)
    result["eligible"] = not result["rejection_details"]
    result["recent_quality_fallback"] = True
    result["quality_warning"] = (
        "Temporary lower-quality release. MediaHub offers this only inside the configured "
        "recent-release fallback window when no eligible HD release is available."
    )
    result.pop("info_hash", None)
    result.pop("guid", None)
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
        public = _movie_policy_public(release, rules)
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
        public = _recent_fallback_public(release, rules)
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
