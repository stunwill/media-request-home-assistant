from __future__ import annotations

from dataclasses import dataclass
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
                headers={"User-Agent": "MediaHub/0.6.2"},
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

    async def catalogue(self, *, query: str = "", page: int = 1, collection: str = "popular") -> dict[str, Any]:
        page = max(1, min(page, 500))
        if query.strip():
            payload = await self._get(
                "/search/movie",
                {"query": query.strip(), "page": page, "include_adult": "false"},
            )
        else:
            endpoint = {
                "popular": "/movie/popular",
                "top_rated": "/movie/top_rated",
                "now_playing": "/movie/now_playing",
                "upcoming": "/movie/upcoming",
            }.get(collection, "/movie/popular")
            payload = await self._get(endpoint, {"page": page})
        results = payload.get("results") or []
        return {
            "page": int(payload.get("page") or page),
            "total_pages": min(int(payload.get("total_pages") or 1), 500),
            "total_results": int(payload.get("total_results") or len(results)),
            "movies": [normalise_movie(item) for item in results if isinstance(item, dict) and item.get("id")],
        }

    async def details(self, tmdb_id: int) -> dict[str, Any]:
        payload = await self._get(
            f"/movie/{tmdb_id}",
            {"append_to_response": "credits,videos,external_ids"},
        )
        movie = normalise_movie(payload)
        movie.update(
            {
                "runtime_minutes": payload.get("runtime"),
                "genres": [
                    {"id": int(item["id"]), "name": str(item["name"])}
                    for item in payload.get("genres", [])
                    if isinstance(item, dict) and item.get("id") and item.get("name")
                ],
                "imdb_id": (payload.get("external_ids") or {}).get("imdb_id") or payload.get("imdb_id"),
                "cast": [
                    {"name": str(item.get("name", "")), "character": str(item.get("character", ""))}
                    for item in (payload.get("credits") or {}).get("cast", [])[:8]
                    if isinstance(item, dict)
                ],
            }
        )
        videos = (payload.get("videos") or {}).get("results", [])
        trailer = next(
            (
                item
                for item in videos
                if isinstance(item, dict)
                and item.get("site") == "YouTube"
                and item.get("type") == "Trailer"
                and item.get("official")
            ),
            None,
        )
        movie["trailer_url"] = f"https://www.youtube.com/watch?v={trailer['key']}" if trailer else None
        return movie


@dataclass(frozen=True)
class RadarrDefaults:
    root_folder_path: str
    quality_profile_id: int


class RadarrClient:
    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        root_folder_path: str = "",
        quality_profile_id: int = 0,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key.strip()
        self.root_folder_path = root_folder_path.strip()
        self.quality_profile_id = quality_profile_id
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    def _configured(self) -> None:
        if not self.url or not self.api_key:
            raise MediaServiceError("Radarr is not configured", status_code=503)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        self._configured()
        try:
            async with httpx.AsyncClient(
                base_url=self.url,
                timeout=self.timeout,
                transport=self.transport,
                headers={"X-Api-Key": self.api_key, "User-Agent": "MediaHub/0.6.2"},
            ) as client:
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
            "root_folders": [
                {"path": str(item.get("path", "")), "free_space": int(item.get("freeSpace") or 0)}
                for item in roots
                if isinstance(item, dict) and item.get("path")
            ],
            "quality_profiles": [
                {"id": int(item["id"]), "name": str(item.get("name", item["id"]))}
                for item in profiles
                if isinstance(item, dict) and item.get("id")
            ],
            "selected": {
                "root_folder_path": self.root_folder_path,
                "quality_profile_id": self.quality_profile_id,
            },
        }

    async def _defaults(self) -> RadarrDefaults:
        options = await self.options()
        roots = options["root_folders"]
        profiles = options["quality_profiles"]
        root = self.root_folder_path or (roots[0]["path"] if roots else "")
        profile = self.quality_profile_id or (profiles[0]["id"] if profiles else 0)
        if not root or not profile:
            raise MediaServiceError(
                "Radarr needs at least one root folder and quality profile",
                status_code=503,
            )
        return RadarrDefaults(root_folder_path=root, quality_profile_id=profile)

    async def movies(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/movie")
        return payload if isinstance(payload, list) else []

    async def ensure_movie(self, tmdb_id: int) -> dict[str, Any]:
        existing = next((item for item in await self.movies() if int(item.get("tmdbId") or 0) == tmdb_id), None)
        if existing:
            return existing
        lookup = await self._request("GET", "/api/v3/movie/lookup/tmdb", params={"tmdbId": tmdb_id})
        defaults = await self._defaults()
        lookup.update(
            {
                "qualityProfileId": defaults.quality_profile_id,
                "rootFolderPath": defaults.root_folder_path,
                "monitored": True,
                "addOptions": {"monitor": "movieOnly", "searchForMovie": False},
            }
        )
        return await self._request("POST", "/api/v3/movie", json=lookup)

    async def releases(self, radarr_movie_id: int) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/release", params={"movieId": radarr_movie_id})
        releases = payload if isinstance(payload, list) else []
        return [self.normalise_release(item) for item in releases if isinstance(item, dict)]

    async def grab(self, *, guid: str, indexer_id: int) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            "/api/v3/release",
            json={"guid": guid, "indexerId": indexer_id},
        )
        return payload if isinstance(payload, dict) else {}

    async def queue(self) -> list[dict[str, Any]]:
        payload = await self._request(
            "GET",
            "/api/v3/queue",
            params={"page": 1, "pageSize": 200, "includeMovie": "true", "sortKey": "timeleft"},
        )
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return records if isinstance(records, list) else []

    @staticmethod
    def normalise_release(item: dict[str, Any]) -> dict[str, Any]:
        size_bytes = int(item.get("size") or 0)
        rejections = [str(value) for value in (item.get("rejections") or [])]
        raw_flags = item.get("indexerFlags") or []
        flags = [str(value) for value in raw_flags] if isinstance(raw_flags, list) else [str(raw_flags)]
        return {
            "guid": str(item.get("guid") or ""),
            "indexer_id": int(item.get("indexerId") or 0),
            "indexer": str(item.get("indexer") or "Unknown indexer"),
            "title": str(item.get("title") or "Untitled release"),
            "quality": _quality_name(item),
            "size_bytes": size_bytes,
            "size_gb": round(size_bytes / (1024**3), 2),
            "seeders": item.get("seeders"),
            "leechers": item.get("leechers"),
            "age_hours": round(float(item.get("ageHours") or 0), 1),
            "publish_date": item.get("publishDate"),
            "approved": bool(item.get("approved")) and not rejections,
            "download_allowed": bool(item.get("downloadAllowed", True)),
            "rejections": rejections,
            "flags": flags,
            "info_hash": str(item.get("infoHash") or ""),
        }


class QBittorrentClient:
    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        *,
        api_key: str = "",
        auth_method: str = "password",
        timeout_seconds: float = 12,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.username = username.strip()
        self.password = password
        self.api_key = api_key.strip()
        self.auth_method = auth_method
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    async def torrents(self) -> list[dict[str, Any]]:
        credentials_set = (
            bool(self.api_key)
            if self.auth_method == "api_key"
            else bool(self.username and self.password)
        )
        if not self.url or not credentials_set:
            return []
        try:
            api_key = self.api_key if self.auth_method == "api_key" else ""
            async with httpx.AsyncClient(
                base_url=self.url,
                timeout=self.timeout,
                transport=self.transport,
                headers=qbittorrent_headers(self.url, api_key),
            ) as client:
                await authenticate_qbittorrent(
                    client,
                    base_url=self.url,
                    username=self.username,
                    password=self.password,
                    api_key=api_key,
                )
                response = await client.get("/api/v2/torrents/info", params={"sort": "added_on", "reverse": "true"})
                response.raise_for_status()
                payload = response.json()
        except MediaServiceError:
            raise
        except httpx.TimeoutException as error:
            raise MediaServiceError("qBittorrent request timed out") from error
        except httpx.HTTPStatusError as error:
            code = error.response.status_code
            if code in {401, 403}:
                raise MediaServiceError(
                    "qBittorrent credentials were rejected",
                    status_code=503,
                ) from error
            raise MediaServiceError(f"qBittorrent request failed with HTTP {code}") from error
        except (httpx.RequestError, ValueError) as error:
            raise MediaServiceError("qBittorrent is unavailable") from error
        return payload if isinstance(payload, list) else []


def configured_clients(options: dict[str, Any]) -> tuple[TmdbClient, RadarrClient, QBittorrentClient]:
    values = options.get("integrations", {})
    return (
        TmdbClient(str(values.get("tmdb_api_key", ""))),
        RadarrClient(
            str(values.get("radarr_url", "")),
            str(values.get("radarr_api_key", "")),
            root_folder_path=str(values.get("radarr_root_folder_path", "")),
            quality_profile_id=int(values.get("radarr_quality_profile_id") or 0),
        ),
        QBittorrentClient(
            str(values.get("qbittorrent_url", "")),
            str(values.get("qbittorrent_username", "")),
            str(values.get("qbittorrent_password", "")),
            api_key=str(values.get("qbittorrent_api_key", "")),
            auth_method=str(values.get("qbittorrent_auth_method", "password")),
        ),
    )
