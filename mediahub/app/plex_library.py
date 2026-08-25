from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


class PlexError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlexConfig:
    url: str = ""
    token: str = ""
    library_key: str = ""
    machine_identifier: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.url.strip() and self.token.strip())


_GUID_RE = re.compile(r"^(?P<scheme>[a-z0-9_]+)://(?P<value>[^?/#]+)", re.I)


def normalise_guid(value: str) -> dict[str, str]:
    match = _GUID_RE.match(str(value or "").strip())
    if not match:
        return {}
    scheme = match.group("scheme").lower()
    raw = match.group("value").strip()
    if scheme == "tmdb" and raw.isdigit():
        return {"tmdb_id": raw}
    if scheme == "imdb" and raw.startswith("tt"):
        return {"imdb_id": raw}
    return {}


def normalise_title(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


class PlexClient:
    def __init__(
        self,
        config: PlexConfig,
        *,
        timeout_seconds: float = 8.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.timeout = httpx.Timeout(timeout_seconds)
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        return {
            "X-Plex-Token": self.config.token,
            "Accept": "application/json",
            "User-Agent": "MediaHub/0.9.0",
        }

    async def _get(self, path: str) -> dict[str, Any]:
        if not self.config.configured:
            raise PlexError("Plex is not configured")
        try:
            async with httpx.AsyncClient(
                base_url=self.config.url.rstrip("/"),
                timeout=self.timeout,
                transport=self.transport,
                headers=self._headers(),
                follow_redirects=True,
            ) as client:
                response = await client.get(path)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as error:
            raise PlexError("Plex connection timed out") from error
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise PlexError("Plex authentication failed") from error
            raise PlexError(f"Plex returned HTTP {error.response.status_code}") from error
        except (httpx.RequestError, ValueError) as error:
            raise PlexError("Plex is unavailable") from error
        return payload if isinstance(payload, dict) else {}

    async def identity(self) -> dict[str, str]:
        payload = await self._get("/identity")
        container = payload.get("MediaContainer") or {}
        return {
            "machine_identifier": str(container.get("machineIdentifier") or ""),
            "version": str(container.get("version") or ""),
        }

    async def movie_libraries(self) -> list[dict[str, str]]:
        payload = await self._get("/library/sections")
        container = payload.get("MediaContainer") or {}
        directories = container.get("Directory") or []
        return [
            {"key": str(item.get("key") or ""), "title": str(item.get("title") or "Movies")}
            for item in directories
            if isinstance(item, dict) and str(item.get("type") or "") == "movie" and item.get("key")
        ]

    async def movies(self) -> list[dict[str, Any]]:
        library_key = self.config.library_key.strip()
        if not library_key:
            libraries = await self.movie_libraries()
            if len(libraries) != 1:
                raise PlexError("Select a Plex movie library in Setup")
            library_key = libraries[0]["key"]
        payload = await self._get(f"/library/sections/{quote(library_key, safe='')}/all?type=1&includeGuids=1")
        container = payload.get("MediaContainer") or {}
        metadata = container.get("Metadata") or []
        results: list[dict[str, Any]] = []
        for item in metadata:
            if not isinstance(item, dict):
                continue
            ids: dict[str, str] = {}
            for guid in item.get("Guid") or []:
                if isinstance(guid, dict):
                    ids.update(normalise_guid(str(guid.get("id") or "")))
            primary = normalise_guid(str(item.get("guid") or ""))
            ids.update(primary)
            results.append(
                {
                    "rating_key": str(item.get("ratingKey") or ""),
                    "title": str(item.get("title") or ""),
                    "year": int(item.get("year") or 0) or None,
                    "tmdb_id": ids.get("tmdb_id"),
                    "imdb_id": ids.get("imdb_id"),
                }
            )
        return results


class PlexLibraryCache:
    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._expires_at = 0.0
        self._items: list[dict[str, Any]] = []
        self._last_error: str | None = None

    def clear(self) -> None:
        self._expires_at = 0.0
        self._items = []
        self._last_error = None

    async def items(self, client: PlexClient) -> tuple[list[dict[str, Any]], bool]:
        now = time.monotonic()
        if self._items and now < self._expires_at:
            return list(self._items), False
        try:
            self._items = await client.movies()
            self._expires_at = now + self.ttl_seconds
            self._last_error = None
            return list(self._items), False
        except PlexError as error:
            self._last_error = str(error)
            if self._items:
                return list(self._items), True
            raise


PLEX_CACHE = PlexLibraryCache()


def match_movie(movie: dict[str, Any], plex_items: list[dict[str, Any]]) -> dict[str, Any]:
    tmdb_id = str(movie.get("tmdb_id") or "")
    imdb_id = str(movie.get("imdb_id") or "")
    if tmdb_id:
        exact = [item for item in plex_items if str(item.get("tmdb_id") or "") == tmdb_id]
        if len(exact) == 1:
            return {"match": exact[0], "confidence": "exact_identifier", "match_method": "tmdb"}
        if len(exact) > 1:
            return {"match": None, "confidence": "ambiguous", "match_method": "tmdb"}
    if imdb_id:
        exact = [item for item in plex_items if str(item.get("imdb_id") or "") == imdb_id]
        if len(exact) == 1:
            return {"match": exact[0], "confidence": "exact_identifier", "match_method": "imdb"}
        if len(exact) > 1:
            return {"match": None, "confidence": "ambiguous", "match_method": "imdb"}
    title = normalise_title(str(movie.get("title") or ""))
    year = int(movie.get("year") or 0) if str(movie.get("year") or "").isdigit() else None
    if title and year:
        candidates = [
            item for item in plex_items
            if normalise_title(str(item.get("title") or "")) == title and int(item.get("year") or 0) == year
        ]
        if len(candidates) == 1:
            return {"match": candidates[0], "confidence": "title_year", "match_method": "title_year"}
        if len(candidates) > 1:
            return {"match": None, "confidence": "ambiguous", "match_method": "title_year"}
    return {"match": None, "confidence": "not_found", "match_method": None}


def plex_web_url(machine_identifier: str, rating_key: str) -> str | None:
    machine = str(machine_identifier or "").strip()
    key = str(rating_key or "").strip()
    if not machine or not key:
        return None
    return (
        "https://app.plex.tv/desktop/#!/server/"
        f"{quote(machine, safe='')}/details?key=%2Flibrary%2Fmetadata%2F{quote(key, safe='')}"
    )
