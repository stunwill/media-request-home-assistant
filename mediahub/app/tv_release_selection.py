from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import main, settings, tv_main
from .media_services import MediaServiceError
from .tv_services import SonarrClient

app = tv_main.app
app.version = "0.11.0-dev"

TV_RELEASE_CACHE_SECONDS = 25 * 60
_tv_release_cache: dict[str, tuple[float, str, int, int | None, int | None, dict[str, Any]]] = {}


class TvPolicyUpdate(BaseModel):
    maximum_season_size_gb: float = Field(gt=0, le=100)
    maximum_episode_size_gb: float = Field(gt=0, le=20)


class TvGrabRequest(BaseModel):
    release_token: str = Field(min_length=16, max_length=200)


def initialise_tv_release_database() -> None:
    tv_main.initialise_tv_database()
    with main.connect_db() as db:
        columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(requests)").fetchall()}
        migrations = {
            "season_number": "INTEGER",
            "episode_number": "INTEGER",
            "sonarr_episode_id": "INTEGER",
            "selected_release_size_bytes": "INTEGER",
            "selected_release_source": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in columns:
                db.execute(f"ALTER TABLE requests ADD COLUMN {name} {definition}")
        db.commit()


def _policy(options: dict[str, Any] | None = None) -> dict[str, float]:
    values = (options or main.load_options()).get("tv_downloads", {})
    return {
        "maximum_season_size_gb": float(values.get("maximum_season_size_gb") or 10),
        "maximum_episode_size_gb": float(values.get("maximum_episode_size_gb") or 1),
    }


def _size_gb(size_bytes: int) -> float:
    return round(max(0, int(size_bytes)) / (1024 ** 3), 2)


def _release_quality(item: dict[str, Any]) -> str:
    quality = item.get("quality") or {}
    if isinstance(quality, dict):
        nested = quality.get("quality") or quality
        if isinstance(nested, dict):
            return str(nested.get("name") or "Unknown")
    return str(quality or "Unknown")


def _release_codec(title: str) -> str | None:
    lowered = title.casefold()
    if "x265" in lowered or "h265" in lowered or "hevc" in lowered:
        return "x265/HEVC"
    if "x264" in lowered or "h264" in lowered or "avc" in lowered:
        return "x264/H.264"
    return None


def _release_source(title: str, quality: str) -> str | None:
    haystack = f"{title} {quality}".casefold()
    for marker, label in (
        ("web-dl", "WEB-DL"),
        ("webdl", "WEB-DL"),
        ("webrip", "WEBRip"),
        ("bluray", "BluRay"),
        ("bdrip", "BluRay"),
        ("hdtv", "HDTV"),
    ):
        if marker in haystack:
            return label
    return None


def _release_public(item: dict[str, Any], *, limit_gb: float, scope: Literal["season", "episode"]) -> dict[str, Any]:
    title = str(item.get("title") or "Untitled release")
    size_bytes = int(item.get("size") or 0)
    quality = _release_quality(item)
    seeders = item.get("seeders")
    rejections = [str(value) for value in (item.get("rejections") or [])]
    reasons = list(rejections)
    if size_bytes <= 0:
        reasons.append("Release size is unavailable")
    if size_bytes > int(limit_gb * (1024 ** 3)):
        reasons.append(f"Release exceeds the {limit_gb:g} GB TV {scope} limit")
    if not any(res in quality.casefold() for res in ("720", "1080")):
        reasons.append("MediaHub requires a 720p or 1080p TV release")
    if item.get("downloadAllowed") is False:
        reasons.append("Sonarr does not allow this release to be grabbed")
    return {
        "title": title,
        "size_bytes": size_bytes,
        "size_gb": _size_gb(size_bytes),
        "quality": quality,
        "source": _release_source(title, quality),
        "codec": _release_codec(title),
        "seeders": int(seeders) if seeders is not None else None,
        "indexer": str(item.get("indexer") or item.get("indexerFlags") or "Sonarr"),
        "age_hours": round(float(item.get("ageHours") or 0), 1),
        "is_season_pack": bool(item.get("fullSeason")),
        "policy_rejections": list(dict.fromkeys(reasons)),
        "eligible": not reasons,
    }


def _cache_release(
    *,
    user_id: str,
    series_id: int,
    season_number: int | None,
    episode_id: int | None,
    release: dict[str, Any],
) -> str:
    now = monotonic()
    for token, cached in list(_tv_release_cache.items()):
        if cached[0] <= now:
            _tv_release_cache.pop(token, None)
    token = secrets.token_urlsafe(24)
    _tv_release_cache[token] = (
        now + TV_RELEASE_CACHE_SECONDS,
        user_id,
        series_id,
        season_number,
        episode_id,
        dict(release),
    )
    return token


def _consume_release(token: str, *, user_id: str) -> tuple[int, int | None, int | None, dict[str, Any]]:
    cached = _tv_release_cache.pop(token, None)
    if cached is None or cached[0] <= monotonic() or cached[1] != user_id:
        raise HTTPException(status_code=409, detail="This TV release selection expired. Search again.")
    return cached[2], cached[3], cached[4], cached[5]


def _episode_status(episode: dict[str, Any], queued_episode_ids: set[int]) -> str:
    if bool(episode.get("hasFile")):
        return "available"
    episode_id = int(episode.get("id") or 0)
    if episode_id and episode_id in queued_episode_ids:
        return "downloading"
    air_date = str(episode.get("airDateUtc") or episode.get("airDate") or "")
    if air_date:
        try:
            aired = datetime.fromisoformat(air_date.replace("Z", "+00:00"))
            if aired.astimezone(UTC) > datetime.now(UTC):
                return "unaired"
        except ValueError:
            pass
    return "missing"


async def _show_and_series(tmdb_id: int, seasons: list[int] | None = None) -> tuple[dict[str, Any], SonarrClient, dict[str, Any]]:
    tmdb, sonarr = tv_main.tv_clients()
    show = await tmdb.details(tmdb_id)
    series = await sonarr.ensure_series(show, selected_seasons=seasons)
    if not int(series.get("id") or 0):
        raise MediaServiceError("Sonarr returned an invalid series response")
    return show, sonarr, series


async def season_details(tmdb_id: int, season_number: int, _: main.CurrentUser) -> dict[str, Any]:
    if season_number <= 0:
        raise HTTPException(status_code=422, detail="Season number must be greater than zero")
    try:
        show, sonarr, series = await _show_and_series(tmdb_id, [season_number])
        episodes = [item for item in await sonarr.episodes(int(series["id"])) if int(item.get("seasonNumber") or 0) == season_number]
        queue = await sonarr.queue()
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    queued_episode_ids = {int(item.get("episodeId") or 0) for item in queue if item.get("episodeId")}
    public_episodes = []
    for episode in sorted(episodes, key=lambda item: int(item.get("episodeNumber") or 0)):
        public_episodes.append({
            "sonarr_episode_id": int(episode.get("id") or 0),
            "season_number": season_number,
            "episode_number": int(episode.get("episodeNumber") or 0),
            "title": str(episode.get("title") or f"Episode {episode.get('episodeNumber', '')}"),
            "overview": str(episode.get("overview") or ""),
            "air_date": str(episode.get("airDate") or episode.get("airDateUtc") or ""),
            "runtime_minutes": int(episode.get("runtime") or 0) or None,
            "status": _episode_status(episode, queued_episode_ids),
            "has_file": bool(episode.get("hasFile")),
        })
    available = sum(item["status"] == "available" for item in public_episodes)
    downloading = sum(item["status"] == "downloading" for item in public_episodes)
    missing = sum(item["status"] == "missing" for item in public_episodes)
    season_meta = next((item for item in show.get("seasons", []) if int(item.get("season_number") or 0) == season_number), {})
    return {
        "tmdb_id": tmdb_id,
        "series_id": int(series["id"]),
        "series_title": str(show.get("name") or show.get("title") or "TV Show"),
        "season_number": season_number,
        "season_name": str(season_meta.get("name") or f"Season {season_number}"),
        "poster_url": season_meta.get("poster_url"),
        "air_date": season_meta.get("air_date"),
        "total_episode_count": len(public_episodes),
        "available_episode_count": available,
        "downloading_episode_count": downloading,
        "missing_episode_count": missing,
        "episodes": public_episodes,
        "policy": _policy(),
    }


async def season_releases(tmdb_id: int, season_number: int, principal: main.CurrentUser) -> dict[str, Any]:
    try:
        _, sonarr, series = await _show_and_series(tmdb_id, [season_number])
        releases = await sonarr.season_releases(int(series["id"]), season_number)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    limit = _policy()["maximum_season_size_gb"]
    public: list[dict[str, Any]] = []
    for release in releases:
        item = _release_public(release, limit_gb=limit, scope="season")
        if not bool(release.get("fullSeason")):
            item["policy_rejections"].append("Release is not a full season pack")
            item["eligible"] = False
        item["release_token"] = _cache_release(
            user_id=principal.user_id,
            series_id=int(series["id"]),
            season_number=season_number,
            episode_id=None,
            release=release,
        )
        public.append(item)
    public.sort(key=lambda item: (not item["eligible"], item["size_bytes"] or 10**18, -(item["seeders"] or -1)))
    return {"scope": "season", "season_number": season_number, "maximum_size_gb": limit, "releases": public}


async def episode_releases(
    tmdb_id: int,
    season_number: int,
    episode_number: int,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    try:
        _, sonarr, series = await _show_and_series(tmdb_id, [season_number])
        episodes = await sonarr.episodes(int(series["id"]))
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    episode = next((item for item in episodes if int(item.get("seasonNumber") or 0) == season_number and int(item.get("episodeNumber") or 0) == episode_number), None)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found in Sonarr")
    if bool(episode.get("hasFile")):
        raise HTTPException(status_code=409, detail="This episode is already available")
    episode_id = int(episode.get("id") or 0)
    try:
        releases = await sonarr.episode_releases(episode_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    limit = _policy()["maximum_episode_size_gb"]
    public: list[dict[str, Any]] = []
    for release in releases:
        item = _release_public(release, limit_gb=limit, scope="episode")
        item["release_token"] = _cache_release(
            user_id=principal.user_id,
            series_id=int(series["id"]),
            season_number=season_number,
            episode_id=episode_id,
            release=release,
        )
        public.append(item)
    public.sort(key=lambda item: (not item["eligible"], item["size_bytes"] or 10**18, -(item["seeders"] or -1)))
    return {
        "scope": "episode",
        "season_number": season_number,
        "episode_number": episode_number,
        "episode_title": str(episode.get("title") or f"Episode {episode_number}"),
        "maximum_size_gb": limit,
        "releases": public,
    }


async def grab_tv_release(payload: TvGrabRequest, principal: main.CurrentUser) -> dict[str, Any]:
    initialise_tv_release_database()
    series_id, season_number, episode_id, release = _consume_release(payload.release_token, user_id=principal.user_id)
    _, sonarr = tv_main.tv_clients()
    try:
        episodes = await sonarr.episodes(series_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    relevant = [item for item in episodes if (episode_id and int(item.get("id") or 0) == episode_id) or (episode_id is None and int(item.get("seasonNumber") or 0) == int(season_number or 0))]
    if episode_id and any(bool(item.get("hasFile")) for item in relevant):
        raise HTTPException(status_code=409, detail="This episode is already available")
    if episode_id is None and relevant and all(bool(item.get("hasFile")) for item in relevant):
        raise HTTPException(status_code=409, detail="This season is already available")
    limit = _policy()["maximum_episode_size_gb" if episode_id else "maximum_season_size_gb"]
    public = _release_public(release, limit_gb=limit, scope="episode" if episode_id else "season")
    if not public["eligible"] or (episode_id is None and not bool(release.get("fullSeason"))):
        raise HTTPException(status_code=409, detail={"message": "This TV release is not eligible", "reasons": public["policy_rejections"]})
    try:
        await sonarr.grab_release(str(release.get("guid") or ""), int(release.get("indexerId") or 0))
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    selected_title = str(release.get("title") or "TV release")
    now = main.utc_now()
    with main.connect_db() as db:
        existing = None
        if episode_id:
            existing = db.execute(
                "SELECT id FROM requests WHERE media_type='tv' AND sonarr_episode_id=? AND status IN ('searching','queued','downloading','processing') ORDER BY id DESC LIMIT 1",
                (episode_id,),
            ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="This episode already has an active acquisition")
        cursor = db.execute(
            """
            INSERT INTO requests (
              media_type,title,external_id,requested_by_id,requested_by_name,
              estimated_size_gb,reserved_size_gb,status,rejection_reason,progress,status_message,
              created_at,updated_at,sonarr_series_id,requested_scope,requested_seasons_json,
              available_episode_count,total_episode_count,season_number,episode_number,
              sonarr_episode_id,selected_release_title,selected_release_size_bytes,selected_release_source
            ) VALUES ('tv',?,?,?,?,?,0,'downloading',NULL,0,?,?,?,?,?,?,0,0,?,?,?,?,?,?)
            """,
            (
                selected_title,
                str(series_id),
                principal.user_id,
                principal.display_name,
                public["size_gb"] or 0.01,
                "Downloading selected TV release",
                now,
                now,
                series_id,
                "episode" if episode_id else "season_pack",
                json.dumps([season_number] if season_number else []),
                season_number,
                next((int(item.get("episodeNumber") or 0) for item in relevant), None) if episode_id else None,
                episode_id,
                selected_title,
                int(release.get("size") or 0),
                public.get("source"),
            ),
        )
        request_id = int(cursor.lastrowid)
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="tv_episode_release_selected" if episode_id else "tv_season_release_selected",
            request_id=request_id,
            details={
                "series_id": series_id,
                "season_number": season_number,
                "episode_id": episode_id,
                "size_bytes": int(release.get("size") or 0),
            },
        )
        db.commit()
    return {"request_id": request_id, "status": "downloading", "scope": "episode" if episode_id else "season", "title": selected_title}


async def tv_policy(_: main.CurrentUser) -> dict[str, float]:
    return _policy()


async def update_tv_policy(payload: TvPolicyUpdate, _: main.Administrator) -> dict[str, float]:
    return settings.save_tv_download_settings(
        maximum_season_size_gb=payload.maximum_season_size_gb,
        maximum_episode_size_gb=payload.maximum_episode_size_gb,
    )


async def release_health(_: main.CurrentUser) -> dict[str, Any]:
    return {"version": app.version, "tv_downloads": _policy()}


app.add_api_route("/api/catalog/tv/{tmdb_id}/seasons/{season_number}", season_details, methods=["GET"])
app.add_api_route("/api/catalog/tv/{tmdb_id}/seasons/{season_number}/releases", season_releases, methods=["GET"])
app.add_api_route("/api/catalog/tv/{tmdb_id}/seasons/{season_number}/episodes/{episode_number}/releases", episode_releases, methods=["GET"])
app.add_api_route("/api/tv/releases/grab", grab_tv_release, methods=["POST"])
app.add_api_route("/api/setup/tv-downloads", tv_policy, methods=["GET"])
app.add_api_route("/api/setup/tv-downloads", update_tv_policy, methods=["PUT"])
app.add_api_route("/api/tv-release-health", release_health, methods=["GET"])
