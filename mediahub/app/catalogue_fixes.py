from __future__ import annotations

from typing import Any

from . import main, media_services, tv_services

_MOVIE_RESULT_PATHS = {
    "/search/movie",
    "/discover/movie",
    "/movie/popular",
    "/movie/top_rated",
    "/movie/now_playing",
    "/movie/upcoming",
}
_TV_RESULT_PATHS = {
    "/search/tv",
    "/discover/tv",
    "/tv/popular",
    "/tv/airing_today",
    "/tv/on_the_air",
    "/tv/top_rated",
}

_original_movie_get = media_services.TmdbClient._get
_original_tv_get = tv_services.TmdbTvClient._get


def _english_results(payload: dict[str, Any], *, allowed_path: bool) -> dict[str, Any]:
    if not allowed_path:
        return payload
    results = payload.get("results")
    if not isinstance(results, list):
        return payload
    filtered = []
    for item in results:
        if not isinstance(item, dict):
            continue
        language = str(item.get("original_language") or "").strip().casefold()
        if not language or language == "en":
            filtered.append(item)
    if len(filtered) == len(results):
        return payload
    result = dict(payload)
    result["results"] = filtered
    result["mediahub_language_filter"] = "en"
    return result


async def _movie_get_english_only(
    self: media_services.TmdbClient,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_params = dict(params or {})
    if path == "/discover/movie":
        request_params.setdefault("with_original_language", "en")
    payload = await _original_movie_get(self, path, request_params)
    return _english_results(payload, allowed_path=path in _MOVIE_RESULT_PATHS)


async def _tv_get_english_only(
    self: tv_services.TmdbTvClient,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_params = dict(params or {})
    if path == "/discover/tv":
        request_params.setdefault("with_original_language", "en")
    payload = await _original_tv_get(self, path, request_params)
    return _english_results(payload, allowed_path=path in _TV_RESULT_PATHS)


media_services.TmdbClient._get = _movie_get_english_only
tv_services.TmdbTvClient._get = _tv_get_english_only

# v0.10 introduced a new IntersectionObserver catalogue controller but the older
# movie loader and its anonymous event listeners still exist in the base HTML.
# Mark the page before the base script runs and make that legacy loader a no-op,
# so only the new controller can render/search/paginate the Browse grid.
if "MEDIAHUB_INFINITE_CATALOGUE" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace(
        "  <script>\n    const state=",
        "  <script>window.MEDIAHUB_INFINITE_CATALOGUE=true;</script>\n  <script>\n    const state=",
        1,
    )
    main.INDEX_HTML = main.INDEX_HTML.replace(
        "async function loadMovies(append=false){if(state.movieLoading)",
        "async function loadMovies(append=false){if(window.MEDIAHUB_INFINITE_CATALOGUE)return;if(state.movieLoading)",
        1,
    )
