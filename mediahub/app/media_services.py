from __future__ import annotations

import asyncio
import posixpath
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

from .integrations import authenticate_qbittorrent, qbittorrent_headers


class MediaServiceError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def _quality_name(payload: dict[str, Any]) -> str:
    quality = payload.get("quality") or {}
    if isinstance(quality, dict):
        nested = quality.get("quality") or {}
        if isinstance(nested, dict):
            return str(nested.get("name", "Unknown"))
        return str(quality.get("name", "Unknown"))
    return "Unknown"


def _image_url(path: Any, size: str) -> str | None:
    value = str(path or "").strip()
    return f"https://image.tmdb.org/t/p/{size}{value}" if value.startswith("/") else None


def normalise_movie(movie: dict[str, Any]) -> dict[str, Any]:
    release_date = str(movie.get("release_date") or "")
    return {
        "tmdb_id": int(movie["id"]),
        "title": str(movie.get("title") or movie.get("original_title") or "Untitled"),
        "original_title": str(movie.get("original_title") or ""),
        "overview": str(movie.get("overview") or ""),
        "release_date": release_date,
        "year": release_date[:4] if len(release_date) >= 4 else None,
        "rating": round(float(movie.get("vote_average") or 0), 1),
        "vote_count": int(movie.get("vote_count") or 0),
        "popularity": float(movie.get("popularity") or 0),
        "poster_url": _image_url(movie.get("poster_path"), "w500"),
        "backdrop_url": _image_url(movie.get("backdrop_path"), "w1280"),
        "genre_ids": [int(value) for value in movie.get("genre_ids", [])],
    }


class TmdbClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 12,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    def _configured(self) -> None:
        if not self.api_key:
            raise MediaServiceError("TMDb is not configured", status_code=503)

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._configured()
        query = {"api_key": self.api_key, "language": "en-AU", **(params or {})}
        try:
            async with httpx.AsyncClient(
                base_url="https://api.themoviedb.org/3",
                timeout=self.timeout,
                transport=self.transport,
                headers={"User-Agent": "MediaHub/0.7.0"},
            ) as client:
                response = await client.get(path, params=query)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as error:
            raise MediaServiceError("TMDb request timed out") from error
        except httpx.HTTPStatusError as error:
            status = 503 if error.response.status_code in {401, 403} else 502
            message = "TMDb credentials were rejected" if status == 503 else "TMDb request failed"
            raise MediaServiceError(message, status_code=status) from error
        except (httpx.RequestError, ValueError) as error:
            raise MediaServiceError("TMDb is unavailable") from error
        if not isinstance(payload, dict):
            raise MediaServiceError("TMDb returned an invalid response")
        return payload

    async def _search_actor_movies(self, query: str, page: int) -> dict[str, Any] | None:
        people = await self._get(
            "/search/person",
            {"query": query.strip(), "page": 1, "include_adult": "false"},
        )
        candidates = [item for item in (people.get("results") or []) if isinstance(item, dict) and item.get("id")]
        if not candidates:
            return None
        exact = next((item for item in candidates if str(item.get("name") or "").casefold() == query.strip().casefold()), candidates[0])
        return await self._get(
            "/discover/movie",
            {"page": page, "include_adult": "false", "include_video": "false", "sort_by": "popularity.desc", "with_cast": int(exact["id"])},
        )

    async def catalogue(
        self,
        *,
        query: str = "",
        page: int = 1,
        collection: str = "popular",
        genre_id: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        rating_from: float | None = None,
        rating_to: float | None = None,
    ) -> dict[str, Any]:
        page = max(1, min(page, 500))
        if year_from and year_to and year_from > year_to:
            raise MediaServiceError("Release year range is invalid", status_code=422)
        if rating_from and rating_to and rating_from > rating_to:
            raise MediaServiceError("Rating range is invalid", status_code=422)
        filters_applied = bool(genre_id or year_from or year_to or rating_from or rating_to)
        post_filtered_search = False
        search_mode = "movie"
        if query.strip():
            params: dict[str, Any] = {"query": query.strip(), "page": page, "include_adult": "false"}
            if year_from and year_from == year_to:
                params["primary_release_year"] = year_from
            payload = await self._get("/search/movie", params)
            if not (payload.get("results") or []):
                actor_payload = await self._search_actor_movies(query, page)
                if actor_payload is not None:
                    payload = actor_payload
                    search_mode = "actor"
            post_filtered_search = filters_applied
        elif filters_applied:
            params = {
                "page": page,
                "include_adult": "false",
                "include_video": "false",
                "sort_by": {"popular": "popularity.desc", "top_rated": "vote_average.desc", "now_playing": "popularity.desc", "upcoming": "popularity.desc"}.get(collection, "popularity.desc"),
            }
            if collection == "top_rated":
                params["vote_count.gte"] = 250
            if genre_id:
                params["with_genres"] = genre_id
            if rating_from:
                params["vote_average.gte"] = rating_from
            if rating_to:
                params["vote_average.lte"] = rating_to
            earliest = date(year_from, 1, 1) if year_from else None
            latest = date(year_to, 12, 31) if year_to else None
            today = date.today()
            if collection == "now_playing":
                collection_start, collection_end = today - timedelta(days=60), today
                earliest = max(filter(None, (earliest, collection_start)))
                latest = min(filter(None, (latest, collection_end)))
            elif collection == "upcoming":
                collection_start, collection_end = today + timedelta(days=1), today + timedelta(days=365)
                earliest = max(filter(None, (earliest, collection_start)))
                latest = min(filter(None, (latest, collection_end)))
            if earliest and latest and earliest > latest:
                return {"page": 1, "total_pages": 1, "total_results": 0, "movies": [], "filters_applied": True, "post_filtered_search": False, "search_mode": search_mode}
            if earliest:
                params["primary_release_date.gte"] = earliest.isoformat()
            if latest:
                params["primary_release_date.lte"] = latest.isoformat()
            payload = await self._get("/discover/movie", params)
        else:
            endpoint = {"popular": "/movie/popular", "top_rated": "/movie/top_rated", "now_playing": "/movie/now_playing", "upcoming": "/movie/upcoming"}.get(collection, "/movie/popular")
            payload = await self._get(endpoint, {"page": page})
        results = payload.get("results") or []
        movies = [normalise_movie(item) for item in results if isinstance(item, dict) and item.get("id")]
        if post_filtered_search:
            movies = [movie for movie in movies if (not genre_id or genre_id in movie["genre_ids"]) and (not year_from or (str(movie["year"] or "").isdigit() and int(movie["year"]) >= year_from)) and (not year_to or (str(movie["year"] or "").isdigit() and int(movie["year"]) <= year_to)) and (not rating_from or movie["rating"] >= rating_from) and (not rating_to or movie["rating"] <= rating_to)]
        return {"page": int(payload.get("page") or page), "total_pages": min(int(payload.get("total_pages") or 1), 500), "total_results": int(payload.get("total_results") or len(results)), "movies": movies, "filters_applied": filters_applied, "post_filtered_search": post_filtered_search, "search_mode": search_mode}

    async def genres(self) -> dict[str, list[dict[str, Any]]]:
        payload = await self._get("/genre/movie/list")
        genres = [{"id": int(item["id"]), "name": str(item["name"])} for item in payload.get("genres", []) if isinstance(item, dict) and item.get("id") and item.get("name")]
        return {"genres": sorted(genres, key=lambda item: item["name"].casefold())}

    async def details(self, tmdb_id: int) -> dict[str, Any]:
        payload = await self._get(f"/movie/{tmdb_id}", {"append_to_response": "credits,videos,external_ids,release_dates"})
        movie = normalise_movie(payload)
        regional_dates: dict[str, list[dict[str, Any]]] = {}
        for country in (payload.get("release_dates") or {}).get("results", []):
            if not isinstance(country, dict) or not country.get("iso_3166_1"):
                continue
            records: list[dict[str, Any]] = []
            for item in country.get("release_dates") or []:
                if not isinstance(item, dict):
                    continue
                records.append({"type": int(item.get("type") or 0), "release_date": str(item.get("release_date") or "")})
            regional_dates[str(country["iso_3166_1"]).upper()] = records
        movie.update(
            {
                "runtime_minutes": payload.get("runtime"),
                "status": str(payload.get("status") or ""),
                "genres": [{"id": int(item["id"]), "name": str(item["name"])} for item in payload.get("genres", []) if isinstance(item, dict) and item.get("id") and item.get("name")],
                "imdb_id": (payload.get("external_ids") or {}).get("imdb_id") or payload.get("imdb_id"),
                "cast": [{"name": str(item.get("name", "")), "character": str(item.get("character", ""))} for item in (payload.get("credits") or {}).get("cast", [])[:8] if isinstance(item, dict)],
                "release_dates": regional_dates,
            }
        )
        videos = (payload.get("videos") or {}).get("results", [])
        trailer = next((item for item in videos if isinstance(item, dict) and item.get("site") == "YouTube" and item.get("type") == "Trailer" and item.get("official")), None)
        movie["trailer_url"] = f"https://www.youtube.com/watch?v={trailer['key']}" if trailer else None
        return movie


@dataclass(frozen=True)
class RadarrDefaults:
    root_folder_path: str
    quality_profile_id: int


class RadarrClient:
    def __init__(self, url: str, api_key: str, *, root_folder_path: str = "", quality_profile_id: int = 0, timeout_seconds: float = 30, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key.strip()
        self.root_folder_path = root_folder_path.strip()
        self.quality_profile_id = quality_profile_id
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    def _configured(self) -> None:
        if not self.url or not self.api_key:
            raise MediaServiceError("Radarr is not configured", status_code=503)

    async def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None) -> Any:
        self._configured()
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=self.timeout, transport=self.transport, headers={"X-Api-Key": self.api_key, "User-Agent": "MediaHub/0.7.0"}) as client:
                response = await client.request(method, path, params=params, json=json)
                response.raise_for_status()
                return response.json() if response.content else {}
        except httpx.TimeoutException as error:
            raise MediaServiceError("Radarr request timed out") from error
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            if code in {401, 403}:
                raise MediaServiceError("Radarr credentials were rejected", status_code=503) from error
            if code == 404:
                raise MediaServiceError("Radarr could not find the requested item", status_code=404) from error
            raise MediaServiceError(f"Radarr request failed with HTTP {code}") from error
        except (httpx.RequestError, ValueError) as error:
            raise MediaServiceError("Radarr is unavailable") from error

    async def options(self) -> dict[str, Any]:
        roots = await self._request("GET", "/api/v3/rootfolder")
        profiles = await self._request("GET", "/api/v3/qualityprofile")
        return {
            "root_folders": [{"path": str(item.get("path", "")), "free_space": int(item.get("freeSpace") or 0)} for item in roots if isinstance(item, dict) and item.get("path")],
            "quality_profiles": [{"id": int(item["id"]), "name": str(item.get("name", item["id"]))} for item in profiles if isinstance(item, dict) and item.get("id")],
            "selected": {"root_folder_path": self.root_folder_path, "quality_profile_id": self.quality_profile_id},
        }

    async def download_settings(self) -> dict[str, Any]:
        options, media_management = await asyncio.gather(self.options(), self._request("GET", "/api/v3/config/mediamanagement"))
        roots = options["root_folders"]
        selected_root = self.root_folder_path or (roots[0]["path"] if roots else "")
        return {"library_path": selected_root, "hardlinks_enabled": bool(media_management.get("copyUsingHardlinks") if isinstance(media_management, dict) else False)}

    async def _defaults(self) -> RadarrDefaults:
        options = await self.options()
        roots = options["root_folders"]
        profiles = options["quality_profiles"]
        root = self.root_folder_path or (roots[0]["path"] if roots else "")
        profile_id = self.quality_profile_id or (profiles[0]["id"] if profiles else 0)
        if not root or not profile_id:
            raise MediaServiceError("Radarr needs at least one root folder and quality profile", status_code=503)
        return RadarrDefaults(root, profile_id)

    async def lookup(self, tmdb_id: int) -> dict[str, Any]:
        results = await self._request("GET", "/api/v3/movie/lookup", params={"term": f"tmdb:{tmdb_id}"})
        if not isinstance(results, list) or not results:
            raise MediaServiceError("Radarr could not find the TMDb movie", status_code=404)
        return results[0]

    async def movies(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/movie")
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    async def ensure_movie(self, tmdb_id: int) -> dict[str, Any]:
        for movie in await self.movies():
            if int(movie.get("tmdbId") or 0) == tmdb_id:
                return movie
        lookup = await self.lookup(tmdb_id)
        defaults = await self._defaults()
        payload = {**lookup, "qualityProfileId": defaults.quality_profile_id, "rootFolderPath": defaults.root_folder_path, "monitored": True, "addOptions": {"searchForMovie": False}}
        return await self._request("POST", "/api/v3/movie", json=payload)

    async def releases(self, movie_id: int) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/release", params={"movieId": movie_id})
        releases: list[dict[str, Any]] = []
        for item in payload if isinstance(payload, list) else []:
            if not isinstance(item, dict):
                continue
            size_bytes = int(item.get("size") or 0)
            releases.append({
                "guid": str(item.get("guid") or ""), "indexer_id": item.get("indexerId"), "indexer": str(item.get("indexer") or "Unknown"),
                "title": str(item.get("title") or "Untitled release"), "quality": _quality_name(item), "size_bytes": size_bytes,
                "size_gb": round(size_bytes / (1024**3), 2), "seeders": item.get("seeders"), "leechers": item.get("leechers"),
                "age_hours": round(float(item.get("ageHours") or 0), 1), "publish_date": item.get("publishDate"), "approved": bool(item.get("approved", True)),
                "download_allowed": bool(item.get("downloadAllowed", True)), "rejections": [str(value) for value in item.get("rejections", [])],
                "flags": item.get("indexerFlags") or [], "info_hash": str(item.get("infoHash") or ""),
            })
        return releases

    async def grab(self, release: dict[str, Any]) -> None:
        payload = {"guid": release["guid"], "indexerId": release.get("indexer_id")}
        await self._request("POST", "/api/v3/release", json=payload)

    async def queue(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/queue", params={"pageSize": 100, "includeUnknownMovieItems": True})
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return [item for item in records if isinstance(item, dict)]


class QbittorrentClient:
    def __init__(self, url: str, username: str, password: str, *, auth_method: str = "password", api_key: str = "", timeout_seconds: float = 12, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.auth_method = auth_method
        self.api_key = api_key
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    async def _authenticated_client(self) -> httpx.AsyncClient:
        client = httpx.AsyncClient(base_url=self.url, timeout=self.timeout, transport=self.transport, headers=qbittorrent_headers(self.url))
        await authenticate_qbittorrent(client, self.url, self.username, self.password, auth_method=self.auth_method, api_key=self.api_key)
        return client

    async def torrents(self) -> list[dict[str, Any]]:
        try:
            client = await self._authenticated_client()
            async with client:
                response = await client.get("/api/v2/torrents/info")
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise MediaServiceError("qBittorrent is unavailable") from error
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    async def download_settings(self) -> dict[str, Any]:
        try:
            client = await self._authenticated_client()
            async with client:
                preferences, categories = await asyncio.gather(client.get("/api/v2/app/preferences"), client.get("/api/v2/torrents/categories"))
                preferences.raise_for_status(); categories.raise_for_status()
                prefs = preferences.json(); category_map = categories.json()
        except (httpx.HTTPError, ValueError) as error:
            raise MediaServiceError("qBittorrent is unavailable") from error
        radarr = category_map.get("radarr", {}) if isinstance(category_map, dict) else {}
        return {"completed_path": str(prefs.get("save_path") or "") if isinstance(prefs, dict) else "", "incomplete_path": str(prefs.get("temp_path") or "") if isinstance(prefs, dict) and prefs.get("temp_path_enabled") else "", "radarr_category_path": str(radarr.get("savePath") or "") if isinstance(radarr, dict) else ""}


def configured_clients(options: dict[str, Any]) -> tuple[TmdbClient, RadarrClient, QbittorrentClient]:
    integrations = options.get("integrations", {}) if isinstance(options, dict) else {}
    return (
        TmdbClient(str(integrations.get("tmdb_api_key", ""))),
        RadarrClient(str(integrations.get("radarr_url", "")), str(integrations.get("radarr_api_key", "")), root_folder_path=str(integrations.get("radarr_root_folder_path", "")), quality_profile_id=int(integrations.get("radarr_quality_profile_id") or 0)),
        QbittorrentClient(str(integrations.get("qbittorrent_url", "")), str(integrations.get("qbittorrent_username", "")), str(integrations.get("qbittorrent_password", "")), auth_method=str(integrations.get("qbittorrent_auth_method", "password")), api_key=str(integrations.get("qbittorrent_api_key", ""))),
    )


def analyse_download_workflow(radarr: dict[str, Any], qbittorrent: dict[str, Any]) -> dict[str, Any]:
    library = posixpath.normpath(str(radarr.get("library_path") or "")) if radarr.get("library_path") else ""
    paths = {"completed": str(qbittorrent.get("completed_path") or ""), "incomplete": str(qbittorrent.get("incomplete_path") or ""), "radarr": str(qbittorrent.get("radarr_category_path") or "")}
    checks: list[dict[str, str]] = []
    if not library:
        checks.append({"level": "warning", "message": "Radarr library path could not be determined."})
    elif not radarr.get("hardlinks_enabled"):
        checks.append({"level": "warning", "message": "Radarr hardlinks are disabled. Completed downloads may consume a second full copy after import."})
    else:
        checks.append({"level": "ok", "message": "Radarr hardlinks are enabled."})
    for label, raw_path in paths.items():
        if not raw_path:
            continue
        path = posixpath.normpath(raw_path)
        if library and (path == library or path.startswith(f"{library}/")):
            checks.append({"level": "error", "message": f"qBittorrent {label} path is inside the Radarr library. Move it outside {library}."})
        else:
            checks.append({"level": "ok", "message": f"qBittorrent {label} path is separate from the Radarr library."})
    level = "error" if any(item["level"] == "error" for item in checks) else "warning" if any(item["level"] == "warning" for item in checks) else "healthy"
    return {"status": level, "library_path": library or None, "paths": paths, "hardlinks_enabled": bool(radarr.get("hardlinks_enabled")), "checks": checks}
