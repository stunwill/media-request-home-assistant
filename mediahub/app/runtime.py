from __future__ import annotations

import posixpath
import re
from datetime import date
from time import monotonic
from typing import Any

import httpx
from fastapi import HTTPException

from . import enhanced_main, main, media_services

app = enhanced_main.app
app.version = "0.6.7-dev"

_original_analyse_download_workflow = media_services.analyse_download_workflow
_original_search_movie_releases = enhanced_main.search_movie_releases
_original_request_movie = enhanced_main.request_movie

# An interactive Prowlarr fallback selection is converted into the existing automatic
# request path so the established storage, duplicate, audit and Radarr lifecycle logic
# remains authoritative. The value is (Prowlarr GUID, Prowlarr indexer ID).
_selected_prowlarr_release: dict[tuple[int, str], tuple[str, int]] = {}


def analyse_download_workflow(
    radarr: dict[str, Any],
    qbittorrent: dict[str, Any],
) -> dict[str, Any]:
    """Normalise qBittorrent paths before applying the existing safety analysis."""
    qbittorrent_settings = dict(qbittorrent)
    completed = str(qbittorrent_settings.get("completed_path") or "").strip()
    category = str(qbittorrent_settings.get("radarr_category_path") or "").strip()
    if category and completed and not posixpath.isabs(category):
        qbittorrent_settings["radarr_category_path"] = posixpath.join(completed, category)

    result = _original_analyse_download_workflow(radarr, qbittorrent_settings)
    for check in result.get("checks", []):
        if check.get("message") == "Radarr library path could not be determined.":
            check["message"] = (
                "Select a Radarr movie root folder in Setup so MediaHub can validate "
                "the library path."
            )
    return result


async def _radarr_duplicate(radarr: Any, tmdb_id: int) -> dict[str, Any] | None:
    """Reject only movies that Radarr confirms are queued or already have a file."""
    movie = await radarr.ensure_movie(tmdb_id)
    movie_id = int(movie.get("id") or 0)
    if movie.get("hasFile"):
        return {"status": "available", "radarr_movie_id": movie_id}

    queue = await radarr.queue()
    if movie_id and any(int(item.get("movieId") or 0) == movie_id for item in queue):
        return {"status": "queued", "radarr_movie_id": movie_id}
    return None


def _release_date(movie: dict[str, Any]) -> date | None:
    raw = str(movie.get("release_date") or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def recent_or_current_year_movie(
    movie: dict[str, Any],
    *,
    today: date | None = None,
) -> bool:
    """Use fallback for any current-year movie or for one year after release."""
    today = today or date.today()
    released = _release_date(movie)
    if released is not None:
        if released.year == today.year:
            return True
        age_days = (today - released).days
        return 0 <= age_days <= 365

    raw_year = str(movie.get("year") or "").strip()
    return raw_year.isdigit() and int(raw_year) == today.year


def _normalised_words(value: Any) -> list[str]:
    stop_words = {"a", "an", "and", "of", "the"}
    return [
        word
        for word in re.findall(r"[a-z0-9]+", str(value or "").casefold())
        if len(word) >= 2 and word not in stop_words
    ]


def _movie_year(movie: dict[str, Any]) -> str:
    released = _release_date(movie)
    if released is not None:
        return str(released.year)
    raw = str(movie.get("year") or "").strip()
    return raw if len(raw) == 4 and raw.isdigit() else ""


def _matches_movie(release_title: Any, movie: dict[str, Any]) -> bool:
    """Reject obvious franchise/title-year mismatches from a broad text search."""
    candidate_text = str(release_title or "")
    candidate_words = set(_normalised_words(candidate_text))
    if not candidate_words:
        return False

    variants = [movie.get("title"), movie.get("original_title")]
    variant_matches = False
    for variant in variants:
        words = _normalised_words(variant)
        if not words:
            continue
        required = min(len(words), 2)
        if sum(word in candidate_words for word in words) >= required:
            variant_matches = True
            break
    if not variant_matches:
        return False

    year = _movie_year(movie)
    candidate_years = set(re.findall(r"\b(?:19|20)\d{2}\b", candidate_text))
    if year and candidate_years and year not in candidate_years:
        return False
    return True


def _quality_from_title(title: Any) -> str:
    text = f" {str(title or '').casefold()} "
    if "hdcam" in text or re.search(r"\bcam(?:rip)?\b", text):
        return "CAM"
    if "hdts" in text or "telesync" in text or re.search(r"\bts\b", text):
        return "Telesync"
    if "telecine" in text or re.search(r"\btc\b", text):
        return "Telecine"
    if "screener" in text or "dvdscr" in text or re.search(r"\bscr\b", text):
        return "Screener"
    if "2160" in text:
        return "2160p"
    if "1080" in text:
        return "1080p"
    if "720" in text:
        return "720p"
    return "Unknown"


def _is_low_quality(release: dict[str, Any]) -> bool:
    text = f" {release.get('quality', '')} {release.get('title', '')} ".casefold()
    return bool(
        "cam" in text
        or "hdts" in text
        or "telesync" in text
        or "telecine" in text
        or "screener" in text
        or "dvdscr" in text
        or re.search(r"\b(?:ts|tc|scr)\b", text)
    )


def _movie_search_terms(movie: dict[str, Any]) -> list[str]:
    year = _movie_year(movie)
    variants: list[str] = []
    for value in (movie.get("title"), movie.get("original_title")):
        title = str(value or "").strip()
        if title and title.casefold() not in {item.casefold() for item in variants}:
            variants.append(title)

    terms: list[str] = []
    for title in variants:
        if year:
            terms.append(f"{title} {year}")
        terms.append(title)
    return terms


async def _prowlarr_search(movie: dict[str, Any]) -> list[dict[str, Any]]:
    options = main.load_options()
    integrations = options.get("integrations", {}) if isinstance(options, dict) else {}
    url = str(integrations.get("prowlarr_url") or "").rstrip("/")
    api_key = str(integrations.get("prowlarr_api_key") or "").strip()
    if not url or not api_key:
        return []

    results: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    successful_request = False
    last_error: Exception | None = None

    try:
        async with httpx.AsyncClient(
            base_url=url,
            timeout=httpx.Timeout(30),
            headers={"X-Api-Key": api_key, "User-Agent": "MediaHub/0.6.7"},
        ) as client:
            for term in _movie_search_terms(movie):
                attempts = (
                    {"query": term, "type": "movie", "categories": 2000, "limit": 100},
                    {"query": term, "limit": 100},
                )
                for params in attempts:
                    try:
                        response = await client.get("/api/v1/search", params=params)
                        if response.status_code == 400:
                            continue
                        response.raise_for_status()
                        successful_request = True
                        payload = response.json()
                    except (httpx.HTTPError, ValueError) as error:
                        last_error = error
                        continue

                    if not isinstance(payload, list):
                        continue
                    for item in payload:
                        if not isinstance(item, dict) or not _matches_movie(item.get("title"), movie):
                            continue
                        try:
                            indexer_id = int(item.get("indexerId") or 0)
                        except (TypeError, ValueError):
                            indexer_id = 0
                        guid = str(item.get("guid") or "")
                        key = (indexer_id, guid or str(item.get("downloadUrl") or ""))
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(item)
                    if results:
                        break
                if results:
                    break
    except (httpx.HTTPError, ValueError) as error:
        last_error = error

    if not successful_request and last_error is not None:
        raise HTTPException(
            status_code=502,
            detail="Prowlarr direct fallback search is unavailable. Check the Prowlarr connection in Setup.",
        ) from last_error
    return results


async def _radarr_indexers(radarr: Any) -> list[dict[str, Any]]:
    try:
        payload = await radarr._request("GET", "/api/v3/indexer")
    except Exception:
        return []
    return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []


def _mapped_radarr_indexer_id(
    prowlarr_release: dict[str, Any],
    radarr_indexers: list[dict[str, Any]],
) -> int:
    prowlarr_name = str(
        prowlarr_release.get("indexer") or prowlarr_release.get("indexerName") or ""
    ).strip()
    if not prowlarr_name:
        return int(radarr_indexers[0].get("id") or 0) if len(radarr_indexers) == 1 else 0

    wanted = prowlarr_name.casefold()
    for item in radarr_indexers:
        if str(item.get("name") or "").strip().casefold() == wanted:
            return int(item.get("id") or 0)

    # Prowlarr application syncs sometimes add a short prefix/suffix to the Radarr name.
    for item in radarr_indexers:
        candidate = str(item.get("name") or "").strip().casefold()
        if candidate and (wanted in candidate or candidate in wanted):
            return int(item.get("id") or 0)

    return int(radarr_indexers[0].get("id") or 0) if len(radarr_indexers) == 1 else 0


def _normalise_prowlarr_release(
    item: dict[str, Any],
    *,
    radarr_indexer_id: int,
) -> dict[str, Any]:
    try:
        size_bytes = int(item.get("size") or 0)
    except (TypeError, ValueError):
        size_bytes = 0
    try:
        prowlarr_indexer_id = int(item.get("indexerId") or 0)
    except (TypeError, ValueError):
        prowlarr_indexer_id = 0

    title = str(item.get("title") or "Untitled release")
    return {
        "source": "prowlarr_direct",
        "guid": str(item.get("guid") or ""),
        "indexer_id": radarr_indexer_id,
        "prowlarr_indexer_id": prowlarr_indexer_id,
        "indexer": str(item.get("indexer") or item.get("indexerName") or "Prowlarr"),
        "title": title,
        "quality": _quality_from_title(title),
        "size_bytes": size_bytes,
        "size_gb": round(size_bytes / (1024**3), 2),
        "seeders": item.get("seeders"),
        "leechers": item.get("leechers"),
        "age_hours": round(float(item.get("ageHours") or 0), 1),
        "publish_date": item.get("publishDate"),
        "approved": True,
        "download_allowed": True,
        "rejections": [],
        "flags": item.get("indexerFlags") or [],
        "info_hash": str(item.get("infoHash") or ""),
    }


def _prowlarr_policy(release: dict[str, Any], rules: main.ReleaseRules) -> dict[str, Any]:
    result = dict(release)
    rejections: list[str] = []
    size_gb = float(release.get("size_gb") or 0)
    seeders = release.get("seeders")
    quality = str(release.get("quality") or "").casefold()
    low_quality = _is_low_quality(release)

    if not release.get("guid"):
        rejections.append("Prowlarr did not provide a downloadable release identifier")
    if not int(release.get("indexer_id") or 0):
        rejections.append("This Prowlarr indexer is not synced to Radarr")

    if low_quality:
        result["quality_warning"] = (
            "Temporary low-quality release found directly through Prowlarr. MediaHub normally "
            "prefers 720p/1080p and only exposes CAM/TS/telecine/screener results for current-year "
            "or recently released movies when Radarr returns no results."
        )
    else:
        quality_mode = "1080p_only" if rules.require_1080p is True else rules.quality_mode
        if quality_mode == "1080p_only" and "1080" not in quality:
            rejections.append("MediaHub requires a 1080p release")
        elif quality_mode == "720p_only" and "720" not in quality:
            rejections.append("MediaHub requires a 720p release")
        elif quality_mode == "720p_and_1080p" and not any(
            resolution in quality for resolution in ("720", "1080")
        ):
            rejections.append("MediaHub requires a 720p or 1080p release, or a supported recent-release fallback")
        result["quality_warning"] = (
            "Found directly through Prowlarr because Radarr's movie search returned no releases."
        )

    if not size_gb or size_gb > rules.maximum_size_gb:
        rejections.append(f"Release exceeds the {rules.maximum_size_gb:g} GB movie limit")
    if seeders is None or int(seeders) < rules.minimum_seeders:
        rejections.append(f"Release has fewer than {rules.minimum_seeders} seeders")

    result["policy_rejections"] = list(dict.fromkeys(rejections))
    result["eligible"] = not result["policy_rejections"]
    result["recent_quality_fallback"] = low_quality
    result["search_source"] = "prowlarr_direct"
    result.pop("guid", None)
    result.pop("info_hash", None)
    return result


async def search_movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    user_id: str,
    *,
    movie: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """Use Radarr first, then query Prowlarr directly when Radarr returns zero releases."""
    selection_key = (tmdb_id, user_id)
    preferred = _selected_prowlarr_release.get(selection_key)

    if movie is None:
        tmdb, _, _ = main.configured_clients(main.load_options())
        try:
            movie = await tmdb.details(tmdb_id)
        except media_services.MediaServiceError as error:
            raise main.service_http_error(error) from error

    if preferred is None:
        radarr_movie, releases, fallback_active = await _original_search_movie_releases(
            tmdb_id,
            rules,
            user_id,
            movie=movie,
        )
        if releases or not recent_or_current_year_movie(movie):
            return radarr_movie, releases, fallback_active
    else:
        _, radarr, _ = main.configured_clients(main.load_options())
        try:
            radarr_movie = await radarr.ensure_movie(tmdb_id)
        except media_services.MediaServiceError as error:
            raise main.service_http_error(error) from error
        if not recent_or_current_year_movie(movie):
            return radarr_movie, [], False

    _, radarr, _ = main.configured_clients(main.load_options())
    raw_results = await _prowlarr_search(movie)
    if not raw_results:
        return radarr_movie, [], False

    radarr_indexers = await _radarr_indexers(radarr)
    public_results: list[dict[str, Any]] = []
    for raw in raw_results:
        mapped_indexer = _mapped_radarr_indexer_id(raw, radarr_indexers)
        release = _normalise_prowlarr_release(raw, radarr_indexer_id=mapped_indexer)

        if preferred is not None and (
            str(release.get("guid") or "") != preferred[0]
            or int(release.get("prowlarr_indexer_id") or 0) != preferred[1]
        ):
            continue

        public = _prowlarr_policy(release, rules)
        public["release_token"] = main.cache_release(tmdb_id, user_id, release)
        public_results.append(public)

    public_results.sort(
        key=lambda item: (
            bool(item.get("eligible")),
            int(item.get("seeders") or 0),
            -float(item.get("size_gb") or 0),
        ),
        reverse=True,
    )
    return radarr_movie, public_results, any(item.get("eligible") for item in public_results)


async def request_movie(
    tmdb_id: int,
    payload: main.MovieRequestCreate,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    """Preserve the exact interactive Prowlarr choice while reusing the proven request flow."""
    token = str(payload.release_token or "")
    if not token:
        return await _original_request_movie(tmdb_id, payload, principal)

    cached = main.release_cache.get(token)
    if (
        cached is None
        or cached[0] <= monotonic()
        or cached[1] != tmdb_id
        or cached[2] != principal.user_id
        or str(cached[3].get("source") or "") != "prowlarr_direct"
    ):
        return await _original_request_movie(tmdb_id, payload, principal)

    selected = main.cached_release(token, tmdb_id, principal.user_id)
    preferred = (
        str(selected.get("guid") or ""),
        int(selected.get("prowlarr_indexer_id") or 0),
    )
    selection_key = (tmdb_id, principal.user_id)
    _selected_prowlarr_release[selection_key] = preferred
    try:
        automatic_payload = payload.model_copy(update={"release_token": None})
        return await _original_request_movie(tmdb_id, automatic_payload, principal)
    finally:
        _selected_prowlarr_release.pop(selection_key, None)


# Keep the public modules consistent. Existing FastAPI route functions resolve these
# globals at request time, so patching them here avoids duplicating the established
# storage, audit, request and download lifecycle code.
media_services.analyse_download_workflow = analyse_download_workflow
main.analyse_download_workflow = analyse_download_workflow
enhanced_main._radarr_duplicate = _radarr_duplicate
enhanced_main.search_movie_releases = search_movie_releases

# The request endpoint itself holds a release token branch, so replace only that route
# to translate direct-Prowlarr selections into the existing automatic request path.
enhanced_main._replace_route("/api/movies/{tmdb_id}/request", "POST", request_movie)
