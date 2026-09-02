from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from .media_services import MediaServiceError, _image_url


def normalise_tv_show(show: dict[str, Any]) -> dict[str, Any]:
    first_air_date = str(show.get("first_air_date") or "")
    return {
        "media_type": "tv",
        "tmdb_id": int(show["id"]),
        "name": str(show.get("name") or show.get("original_name") or "Untitled"),
        "title": str(show.get("name") or show.get("original_name") or "Untitled"),
        "original_name": str(show.get("original_name") or ""),
        "overview": str(show.get("overview") or ""),
        "first_air_date": first_air_date,
        "year": first_air_date[:4] if len(first_air_date) >= 4 else None,
        "rating": round(float(show.get("vote_average") or 0), 1),
        "vote_count": int(show.get("vote_count") or 0),
        "popularity": float(show.get("popularity") or 0),
        "poster_url": _image_url(show.get("poster_path"), "w500"),
        "backdrop_url": _image_url(show.get("backdrop_path"), "w1280"),
        "genre_ids": [int(value) for value in show.get("genre_ids", [])],
    }


class TmdbTvClient:
    def __init__(self, api_key: str, *, timeout_seconds: float = 12, transport: httpx.AsyncBaseTransport | None = None) -> None:
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
            async with httpx.AsyncClient(base_url="https://api.themoviedb.org/3", timeout=self.timeout, transport=self.transport, headers={"User-Agent": "MediaHub/0.11.0"}) as client:
                response = await client.get(path, params=query)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as error:
            raise MediaServiceError("TMDb TV request timed out") from error
        except httpx.HTTPStatusError as error:
            status = 503 if error.response.status_code in {401, 403} else 502
            raise MediaServiceError("TMDb credentials were rejected" if status == 503 else "TMDb TV request failed", status_code=status) from error
        except (httpx.RequestError, ValueError) as error:
            raise MediaServiceError("TMDb is unavailable") from error
        if not isinstance(payload, dict):
            raise MediaServiceError("TMDb returned an invalid TV response")
        return payload

    async def catalogue(self, *, query: str = "", page: int = 1, collection: str = "popular", genre_id: int | None = None, year_from: int | None = None, year_to: int | None = None, rating_from: float | None = None, rating_to: float | None = None) -> dict[str, Any]:
        page = max(1, min(page, 500))
        if year_from and year_to and year_from > year_to:
            raise MediaServiceError("First-air year range is invalid", status_code=422)
        if rating_from and rating_to and rating_from > rating_to:
            raise MediaServiceError("Rating range is invalid", status_code=422)
        filters = bool(genre_id or year_from or year_to or rating_from or rating_to)
        if query.strip():
            params: dict[str, Any] = {"query": query.strip(), "page": page, "include_adult": "false"}
            if year_from and year_from == year_to:
                params["first_air_date_year"] = year_from
            payload = await self._get("/search/tv", params)
        elif filters:
            params = {"page": page, "include_adult": "false", "sort_by": "vote_average.desc" if collection == "top_rated" else "popularity.desc"}
            if collection == "top_rated":
                params["vote_count.gte"] = 50
            if genre_id:
                params["with_genres"] = genre_id
            if rating_from:
                params["vote_average.gte"] = rating_from
            if rating_to:
                params["vote_average.lte"] = rating_to
            if year_from:
                params["first_air_date.gte"] = f"{year_from:04d}-01-01"
            if year_to:
                params["first_air_date.lte"] = f"{year_to:04d}-12-31"
            payload = await self._get("/discover/tv", params)
        else:
            endpoint = {"popular": "/tv/popular", "airing_today": "/tv/airing_today", "on_the_air": "/tv/on_the_air", "top_rated": "/tv/top_rated"}.get(collection, "/tv/popular")
            payload = await self._get(endpoint, {"page": page})
        results = payload.get("results") or []
        shows = [normalise_tv_show(item) for item in results if isinstance(item, dict) and item.get("id")]
        if query.strip() and filters:
            shows = [item for item in shows if (not genre_id or genre_id in item["genre_ids"]) and (not year_from or (str(item["year"] or "").isdigit() and int(item["year"]) >= year_from)) and (not year_to or (str(item["year"] or "").isdigit() and int(item["year"]) <= year_to)) and (not rating_from or item["rating"] >= rating_from) and (not rating_to or item["rating"] <= rating_to)]
        return {"page": int(payload.get("page") or page), "total_pages": min(int(payload.get("total_pages") or 1), 500), "total_results": int(payload.get("total_results") or len(results)), "shows": shows, "filters_applied": filters, "search_mode": "tv"}

    async def genres(self) -> dict[str, list[dict[str, Any]]]:
        payload = await self._get("/genre/tv/list")
        genres = [{"id": int(item["id"]), "name": str(item["name"])} for item in payload.get("genres", []) if isinstance(item, dict) and item.get("id") and item.get("name")]
        return {"genres": sorted(genres, key=lambda item: item["name"].casefold())}

    async def details(self, tmdb_id: int) -> dict[str, Any]:
        payload = await self._get(f"/tv/{tmdb_id}", {"append_to_response": "credits,videos,external_ids,content_ratings"})
        show = normalise_tv_show(payload)
        credits = payload.get("credits") or {}
        certification = ""
        for item in (payload.get("content_ratings") or {}).get("results", []):
            if isinstance(item, dict) and str(item.get("iso_3166_1") or "").upper() == "AU":
                certification = str(item.get("rating") or "").strip()
                break
        show.update({
            "last_air_date": str(payload.get("last_air_date") or ""), "status": str(payload.get("status") or ""),
            "number_of_seasons": int(payload.get("number_of_seasons") or 0), "number_of_episodes": int(payload.get("number_of_episodes") or 0),
            "episode_runtime": [int(value) for value in payload.get("episode_run_time", []) if value],
            "genres": [{"id": int(item["id"]), "name": str(item["name"])} for item in payload.get("genres", []) if isinstance(item, dict) and item.get("id") and item.get("name")],
            "networks": [{"id": int(item.get("id") or 0), "name": str(item.get("name") or "")} for item in payload.get("networks", []) if isinstance(item, dict)],
            "creators": [{"id": int(item.get("id") or 0), "name": str(item.get("name") or "")} for item in payload.get("created_by", []) if isinstance(item, dict)],
            "certification": certification or None,
            "external_ids": {key: value for key, value in (payload.get("external_ids") or {}).items() if key in {"imdb_id", "tvdb_id", "facebook_id", "instagram_id", "twitter_id"} and value},
            "cast": [{"id": int(item.get("id") or 0), "name": str(item.get("name") or ""), "character": str(item.get("character") or ""), "profile_url": _image_url(item.get("profile_path"), "w185")} for item in (credits.get("cast") or [])[:12] if isinstance(item, dict)],
            "seasons": [{"id": int(item.get("id") or 0), "season_number": int(item.get("season_number") or 0), "name": str(item.get("name") or f"Season {item.get('season_number', '')}"), "episode_count": int(item.get("episode_count") or 0), "air_date": str(item.get("air_date") or ""), "poster_url": _image_url(item.get("poster_path"), "w342")} for item in payload.get("seasons", []) if isinstance(item, dict) and int(item.get("season_number") or 0) > 0],
        })
        videos = (payload.get("videos") or {}).get("results", [])
        trailer = next((item for item in videos if isinstance(item, dict) and item.get("site") == "YouTube" and item.get("type") in {"Trailer", "Teaser"} and item.get("official")), None)
        show["trailer_url"] = f"https://www.youtube.com/watch?v={trailer['key']}" if trailer else None
        return show


@dataclass(frozen=True)
class SonarrDefaults:
    root_folder_path: str
    quality_profile_id: int


class SonarrClient:
    def __init__(self, url: str, api_key: str, *, root_folder_path: str = "", quality_profile_id: int = 0, timeout_seconds: float = 30, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.url = url.rstrip("/")
        self.api_key = api_key.strip()
        self.root_folder_path = root_folder_path.strip()
        self.quality_profile_id = int(quality_profile_id or 0)
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    def _configured(self) -> None:
        if not self.url or not self.api_key:
            raise MediaServiceError("Sonarr is not configured", status_code=503)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        self._configured()
        try:
            async with httpx.AsyncClient(base_url=self.url, timeout=self.timeout, transport=self.transport, headers={"X-Api-Key": self.api_key, "User-Agent": "MediaHub/0.11.0"}) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                if not response.content:
                    return None
                return response.json()
        except httpx.TimeoutException as error:
            raise MediaServiceError("Sonarr request timed out") from error
        except httpx.HTTPStatusError as error:
            status = 503 if error.response.status_code in {401, 403} else 502
            raise MediaServiceError("Sonarr credentials were rejected" if status == 503 else "Sonarr request failed", status_code=status) from error
        except (httpx.RequestError, ValueError) as error:
            raise MediaServiceError("Sonarr is unavailable") from error

    async def options(self) -> dict[str, Any]:
        roots = await self._request("GET", "/api/v3/rootfolder")
        profiles = await self._request("GET", "/api/v3/qualityprofile")
        return {"root_folders": [item for item in roots or [] if isinstance(item, dict)], "quality_profiles": [item for item in profiles or [] if isinstance(item, dict)]}

    async def defaults(self) -> SonarrDefaults:
        options = await self.options()
        roots, profiles = options["root_folders"], options["quality_profiles"]
        root = self.root_folder_path or (str(roots[0].get("path") or "") if roots else "")
        profile_id = self.quality_profile_id or (int(profiles[0].get("id") or 0) if profiles else 0)
        if not root or not profile_id:
            raise MediaServiceError("Sonarr root folder and quality profile must be configured", status_code=503)
        return SonarrDefaults(root, profile_id)

    async def series(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/series")
        return [item for item in payload or [] if isinstance(item, dict)]

    async def lookup(self, *, tvdb_id: int | None = None, term: str = "") -> list[dict[str, Any]]:
        query = f"tvdb:{int(tvdb_id)}" if tvdb_id else term.strip()
        payload = await self._request("GET", "/api/v3/series/lookup", params={"term": query})
        return [item for item in payload or [] if isinstance(item, dict)]

    async def ensure_series(self, show: dict[str, Any], *, selected_seasons: list[int] | None = None) -> dict[str, Any]:
        tvdb_id = int((show.get("external_ids") or {}).get("tvdb_id") or 0)
        existing = None
        for item in await self.series():
            if tvdb_id and int(item.get("tvdbId") or 0) == tvdb_id:
                existing = item; break
            if int(item.get("tmdbId") or 0) == int(show.get("tmdb_id") or 0):
                existing = item; break
        if existing:
            return existing
        candidates = await self.lookup(tvdb_id=tvdb_id or None, term=str(show.get("name") or show.get("title") or ""))
        candidate = next((item for item in candidates if tvdb_id and int(item.get("tvdbId") or 0) == tvdb_id), candidates[0] if candidates else None)
        if candidate is None:
            raise MediaServiceError("Sonarr could not find this TV series", status_code=404)
        defaults = await self.defaults()
        requested = set(int(value) for value in (selected_seasons or []) if int(value) > 0)
        seasons = []
        for season in candidate.get("seasons", []) or []:
            number = int(season.get("seasonNumber") or 0)
            item = dict(season); item["monitored"] = number > 0 and (not requested or number in requested); seasons.append(item)
        body = {**candidate, "qualityProfileId": defaults.quality_profile_id, "rootFolderPath": defaults.root_folder_path, "monitored": True, "seasonFolder": True, "seasons": seasons, "addOptions": {"searchForMissingEpisodes": False}}
        return await self._request("POST", "/api/v3/series", json=body)

    async def search(self, series_id: int, selected_seasons: list[int] | None = None) -> None:
        seasons = [int(value) for value in (selected_seasons or []) if int(value) > 0]
        if seasons:
            for season_number in seasons:
                await self._request("POST", "/api/v3/command", json={"name": "SeasonSearch", "seriesId": int(series_id), "seasonNumber": season_number})
            return
        await self._request("POST", "/api/v3/command", json={"name": "SeriesSearch", "seriesId": int(series_id)})

    async def queue(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/queue", params={"page": 1, "pageSize": 1000, "includeUnknownSeriesItems": True})
        if isinstance(payload, dict):
            payload = payload.get("records") or []
        return [item for item in payload or [] if isinstance(item, dict)]

    async def episodes(self, series_id: int) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/episode", params={"seriesId": int(series_id), "includeImages": False})
        return [item for item in payload or [] if isinstance(item, dict)]

    async def season_releases(self, series_id: int, season_number: int) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/release", params={"seriesId": int(series_id), "seasonNumber": int(season_number)})
        return [item for item in payload or [] if isinstance(item, dict)]

    async def episode_releases(self, episode_id: int) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v3/release", params={"episodeId": int(episode_id)})
        return [item for item in payload or [] if isinstance(item, dict)]

    async def grab_release(self, guid: str, indexer_id: int) -> None:
        if not guid or not indexer_id:
            raise MediaServiceError("Sonarr release identity is incomplete", status_code=409)
        await self._request("POST", "/api/v3/release", json={"guid": guid, "indexerId": int(indexer_id)})
