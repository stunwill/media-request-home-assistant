from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import catalogue_fixes, enhanced_main, main, media_services, release_identity, settings, tv_release_selection, tv_release_ui, tv_services

app = tv_release_ui.app
app.version = "0.12.0-dev"

DEFAULT_PRESETS: dict[str, Any] = {
    "discovery": {"original_language": "en"},
    "movies": {
        "allowed_resolutions": ["1080p", "720p"],
        "maximum_size_gb": 3.0,
        "minimum_seeders": 1,
        "recent_release_fallback_enabled": True,
        "recent_release_fallback_days": 365,
    },
    "tv": {
        "allowed_resolutions": ["1080p", "720p"],
        "maximum_season_size_gb": 10.0,
        "maximum_episode_size_gb": 1.0,
        "minimum_seeders": 1,
    },
}


class DiscoveryPresets(BaseModel):
    original_language: Literal["en", "all"] = "en"


class MoviePresets(BaseModel):
    allowed_resolutions: list[Literal["1080p", "720p"]] = Field(default_factory=lambda: ["1080p", "720p"], min_length=1)
    maximum_size_gb: float = Field(default=3.0, gt=0, le=100)
    minimum_seeders: int = Field(default=1, ge=0, le=10000)
    recent_release_fallback_enabled: bool = True
    recent_release_fallback_days: int = Field(default=365, ge=1, le=730)


class TvPresets(BaseModel):
    allowed_resolutions: list[Literal["1080p", "720p"]] = Field(default_factory=lambda: ["1080p", "720p"], min_length=1)
    maximum_season_size_gb: float = Field(default=10.0, gt=0, le=100)
    maximum_episode_size_gb: float = Field(default=1.0, gt=0, le=20)
    minimum_seeders: int = Field(default=1, ge=0, le=10000)


class PresetsUpdate(BaseModel):
    discovery: DiscoveryPresets = Field(default_factory=DiscoveryPresets)
    movies: MoviePresets = Field(default_factory=MoviePresets)
    tv: TvPresets = Field(default_factory=TvPresets)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_presets() -> dict[str, Any]:
    options = main.load_options()
    raw = options.get("presets") or {}
    merged = _merge(DEFAULT_PRESETS, raw if isinstance(raw, dict) else {})
    legacy_tv = options.get("tv_downloads") or {}
    if not isinstance(raw, dict) or "tv" not in raw:
        merged["tv"]["maximum_season_size_gb"] = float(legacy_tv.get("maximum_season_size_gb") or 10.0)
        merged["tv"]["maximum_episode_size_gb"] = float(legacy_tv.get("maximum_episode_size_gb") or 1.0)
    return PresetsUpdate.model_validate(merged).model_dump()


def save_presets(payload: PresetsUpdate) -> dict[str, Any]:
    value = payload.model_dump()
    stored = settings._read_json(settings.SETTINGS_FILE)
    stored["presets"] = value
    stored["tv_downloads"] = {
        "maximum_season_size_gb": value["tv"]["maximum_season_size_gb"],
        "maximum_episode_size_gb": value["tv"]["maximum_episode_size_gb"],
    }
    settings._atomic_write(stored, settings.SETTINGS_FILE)
    return value


def reset_presets() -> dict[str, Any]:
    stored = settings._read_json(settings.SETTINGS_FILE)
    stored["presets"] = deepcopy(DEFAULT_PRESETS)
    stored["tv_downloads"] = {
        "maximum_season_size_gb": DEFAULT_PRESETS["tv"]["maximum_season_size_gb"],
        "maximum_episode_size_gb": DEFAULT_PRESETS["tv"]["maximum_episode_size_gb"],
    }
    settings._atomic_write(stored, settings.SETTINGS_FILE)
    return deepcopy(DEFAULT_PRESETS)


def _movie_quality_mode(presets: dict[str, Any]) -> str:
    allowed = set(presets["movies"]["allowed_resolutions"])
    if allowed == {"1080p"}:
        return "1080p_only"
    if allowed == {"720p"}:
        return "720p_only"
    return "720p_and_1080p"


def movie_rules() -> main.ReleaseRules:
    presets = load_presets()
    return main.ReleaseRules(
        maximum_size_gb=float(presets["movies"]["maximum_size_gb"]),
        minimum_seeders=int(presets["movies"]["minimum_seeders"]),
        quality_mode=_movie_quality_mode(presets),
    )


def public_download_presets() -> dict[str, Any]:
    presets = load_presets()
    return {
        "movies": dict(presets["movies"]),
        "tv": dict(presets["tv"]),
    }


_original_search_movie_releases = enhanced_main.search_movie_releases
_original_request_movie = enhanced_main.request_movie
_original_is_recent_movie = enhanced_main.is_recent_movie
_original_tv_release_public = tv_release_selection._release_public


async def _preset_search_movie_releases(
    tmdb_id: int,
    _rules: main.ReleaseRules,
    user_id: str,
    *,
    movie: dict[str, Any] | None = None,
):
    return await _original_search_movie_releases(tmdb_id, movie_rules(), user_id, movie=movie)


async def _preset_request_movie(
    tmdb_id: int,
    payload: main.MovieRequestCreate,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    rules = movie_rules()
    safe_payload = payload.model_copy(update={
        "maximum_size_gb": rules.maximum_size_gb,
        "minimum_seeders": rules.minimum_seeders,
        "quality_mode": rules.quality_mode,
        "require_1080p": rules.require_1080p,
    })
    return await _original_request_movie(tmdb_id, safe_payload, principal)


def _preset_is_recent_movie(movie: dict[str, Any], *, today=None) -> bool:
    presets = load_presets()["movies"]
    if not presets["recent_release_fallback_enabled"]:
        return False
    released = enhanced_main._parse_release_date(movie.get("release_date"))
    if released is None:
        return False
    if today is None:
        from datetime import date
        today = date.today()
    age_days = (today - released).days
    return -30 <= age_days <= int(presets["recent_release_fallback_days"])


def _preset_tv_policy(_options: dict[str, Any] | None = None) -> dict[str, float]:
    tv = load_presets()["tv"]
    return {
        "maximum_season_size_gb": float(tv["maximum_season_size_gb"]),
        "maximum_episode_size_gb": float(tv["maximum_episode_size_gb"]),
    }


def _preset_tv_release_public(item: dict[str, Any], *, limit_gb: float, scope: Literal["season", "episode"]) -> dict[str, Any]:
    result = _original_tv_release_public(item, limit_gb=limit_gb, scope=scope)
    details = [dict(value) for value in result.get("rejection_details") or []]
    if not details:
        details = [
            release_identity.classify_arr_rejection(value, service="Sonarr")
            for value in item.get("rejections") or []
        ]
    tv = load_presets()["tv"]
    quality = str(result.get("quality") or "").casefold()
    allowed = [str(value).casefold() for value in tv["allowed_resolutions"]]
    if not any(resolution in quality for resolution in allowed):
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            "Release resolution is not enabled in MediaHub Presets",
            code="tv_resolution",
        ))
    minimum_seeders = int(tv["minimum_seeders"])
    seeders = result.get("seeders")
    if minimum_seeders and seeders is not None and int(seeders) < minimum_seeders:
        details.append(release_identity.rejection_detail(
            "mediahub_policy",
            f"Release has fewer than {minimum_seeders} seeders",
            code="tv_minimum_seeders",
        ))
    release_identity.with_rejection_details(result, details)
    result["eligible"] = not result["rejection_details"]
    return result


async def _movie_get_with_language(self: media_services.TmdbClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    request_params = dict(params or {})
    language = load_presets()["discovery"]["original_language"]
    if language == "en" and path == "/discover/movie":
        request_params.setdefault("with_original_language", "en")
    payload = await catalogue_fixes._original_movie_get(self, path, request_params)
    if language == "en":
        return catalogue_fixes._english_results(payload, allowed_path=path in catalogue_fixes._MOVIE_RESULT_PATHS)
    return payload


async def _tv_get_with_language(self: tv_services.TmdbTvClient, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    request_params = dict(params or {})
    language = load_presets()["discovery"]["original_language"]
    if language == "en" and path == "/discover/tv":
        request_params.setdefault("with_original_language", "en")
    payload = await catalogue_fixes._original_tv_get(self, path, request_params)
    if language == "en":
        return catalogue_fixes._english_results(payload, allowed_path=path in catalogue_fixes._TV_RESULT_PATHS)
    return payload


enhanced_main.search_movie_releases = _preset_search_movie_releases
enhanced_main.is_recent_movie = _preset_is_recent_movie
tv_release_selection._policy = _preset_tv_policy
tv_release_selection._release_public = _preset_tv_release_public
media_services.TmdbClient._get = _movie_get_with_language
tv_services.TmdbTvClient._get = _tv_get_with_language


def _replace_route(path: str, method: str, endpoint: Any) -> None:
    enhanced_main._replace_route(path, method, endpoint)


_replace_route("/api/movies/{tmdb_id}/request", "POST", _preset_request_movie)


async def get_presets(_: main.Administrator) -> dict[str, Any]:
    return load_presets()


async def put_presets(payload: PresetsUpdate, _: main.Administrator) -> dict[str, Any]:
    try:
        return save_presets(payload)
    except (ValueError, TypeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def restore_presets(_: main.Administrator) -> dict[str, Any]:
    return reset_presets()


async def get_download_policy(_: main.CurrentUser) -> dict[str, Any]:
    return public_download_presets()


async def legacy_tv_policy(_: main.CurrentUser) -> dict[str, float]:
    return _preset_tv_policy()


async def update_legacy_tv_policy(payload: tv_release_selection.TvPolicyUpdate, _: main.Administrator) -> dict[str, float]:
    current = load_presets()
    current["tv"]["maximum_season_size_gb"] = payload.maximum_season_size_gb
    current["tv"]["maximum_episode_size_gb"] = payload.maximum_episode_size_gb
    saved = save_presets(PresetsUpdate.model_validate(current))
    return {
        "maximum_season_size_gb": float(saved["tv"]["maximum_season_size_gb"]),
        "maximum_episode_size_gb": float(saved["tv"]["maximum_episode_size_gb"]),
    }


app.add_api_route("/api/setup/presets", get_presets, methods=["GET"])
app.add_api_route("/api/setup/presets", put_presets, methods=["PUT"])
app.add_api_route("/api/setup/presets/reset", restore_presets, methods=["POST"])
app.add_api_route("/api/download-presets", get_download_policy, methods=["GET"])
_replace_route("/api/setup/tv-downloads", "GET", legacy_tv_policy)
_replace_route("/api/setup/tv-downloads", "PUT", update_legacy_tv_policy)
