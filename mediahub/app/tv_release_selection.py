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
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_tv_episode_active
            ON requests (media_type, sonarr_episode_id, status)
            """
        )
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
    reasons = [str(value) for value in (item.get("rejections") or [])]
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
        "indexer": str(item.get("indexer") or "Sonarr"),
        "age_hours": round(float(item.get("ageHours") or 0), 1),
        "is_season_pack": bool(item.get("fullSeason")),
        "policy_rejections": list(dict.fromkeys(reasons)),
        "eligible": not reasons,
    }


def _cache_release(*, user_id: str, series_id: int, season_number: int | None, episode_id: int | None, release: dict[str, Any]) -> str:
    now = monotonic()
    for token, cached in list(_tv_release_cache.items()):
        if cached[0] <= now:
            _tv_release_cache.pop(token, None)
    token = secrets.token_urlsafe(24)
    _tv_release_cache[token] = (now + TV_RELEASE_CACHE_SECONDS, user_id, series_id, season_number, episode_id, dict(release))
    return token


def _consume_release(token: str, *, user_id: str) -> tuple[int, int | None, int | None, dict[str, Any]]:
    cached = _tv_release_cache.pop(token, None)
    if cached is None or cached[0] <= monotonic() or cached[1] != user_id:
        raise HTTPException(status_code=409, detail="This TV release selection expired. Search again.")
    return cached[2], cached[3], cached[4], cached[5]


def _invalidate_episode_tokens(episode_id: int) -> None:
    for token, cached in list(_tv_release_cache.items()):
        if cached[4] == episode_id:
            _tv_release_cache.pop(token, None)


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


async def _season_snapshot(tmdb_id: int, season_number: int) -> dict[str, Any]:
    show, sonarr, series = await _show_and_series(tmdb_id, [season_number])
    episodes = [item for item in await sonarr.episodes(int(series["id"])) if int(item.get("seasonNumber") or 0) == season_number]
    queue = await sonarr.queue()
    queued_episode_ids = {int(item.get("episodeId") or 0) for item in queue if item.get("episodeId")}
    public_episodes = []
    for episode in sorted(episodes, key=lambda item: int(item.get("episodeNumber") or 0)):
        status = _episode_status(episode, queued_episode_ids)
        episode_id = int(episode.get("id") or 0)
        if status == "available" and episode_id:
            _invalidate_episode_tokens(episode_id)
        public_episodes.append({
            "sonarr_episode_id": episode_id,
            "season_number": season_number,
            "episode_number": int(episode.get("episodeNumber") or 0),
            "title": str(episode.get("title") or f"Episode {episode.get('episodeNumber', '')}"),
            "overview": str(episode.get("overview") or ""),
            "air_date": str(episode.get("airDate") or episode.get("airDateUtc") or ""),
            "runtime_minutes": int(episode.get("runtime") or 0) or None,
            "status": status,
            "has_file": bool(episode.get("hasFile")),
        })
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
        "available_episode_count": sum(item["status"] == "available" for item in public_episodes),
        "downloading_episode_count": sum(item["status"] == "downloading" for item in public_episodes),
        "missing_episode_count": sum(item["status"] == "missing" for item in public_episodes),
        "episodes": public_episodes,
        "policy": _policy(),
    }


async def season_details(tmdb_id: int, season_number: int, _: main.CurrentUser) -> dict[str, Any]:
    if season_number <= 0:
        raise HTTPException(status_code=422, detail="Season number must be greater than zero")
    try:
        return await _season_snapshot(tmdb_id, season_number)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error


async def season_releases(tmdb_id: int, season_number: int, principal: main.CurrentUser) -> dict[str, Any]:
    try:
        snapshot = await _season_snapshot(tmdb_id, season_number)
        _, sonarr = tv_main.tv_clients()
        releases = await sonarr.season_releases(int(snapshot["series_id"]), season_number)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    if snapshot["total_episode_count"] and snapshot["available_episode_count"] >= snapshot["total_episode_count"]:
        raise HTTPException(status_code=409, detail="This season is already available")
    limit = _policy()["maximum_season_size_gb"]
    public: list[dict[str, Any]] = []
    for release in releases:
        item = _release_public(release, limit_gb=limit, scope="season")
        if not bool(release.get("fullSeason")):
            item["policy_rejections"].append("Release is not a full season pack")
            item["eligible"] = False
        item["release_token"] = _cache_release(user_id=principal.user_id, series_id=int(snapshot["series_id"]), season_number=season_number, episode_id=None, release=release)
        item["existing_episode_count"] = int(snapshot["available_episode_count"])
        item["season_episode_count"] = int(snapshot["total_episode_count"])
        public.append(item)
    public.sort(key=lambda item: (not item["eligible"], item["size_bytes"] or 10**18, -(item["seeders"] or -1)))
    with main.connect_db() as db:
        main.record_audit(db, actor_id=principal.user_id, actor_name=principal.display_name, action="tv_season_release_search", request_id=None, details={"tmdb_id": tmdb_id, "season_number": season_number, "result_count": len(public)})
        db.commit()
    return {"scope": "season", "season_number": season_number, "maximum_size_gb": limit, "releases": public}


async def episode_releases(tmdb_id: int, season_number: int, episode_number: int, principal: main.CurrentUser) -> dict[str, Any]:
    try:
        snapshot = await _season_snapshot(tmdb_id, season_number)
        episode = next((item for item in snapshot["episodes"] if int(item["episode_number"]) == episode_number), None)
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found in Sonarr")
        if episode["status"] == "available":
            raise HTTPException(status_code=409, detail="This episode is already available")
        if episode["status"] == "unaired":
            raise HTTPException(status_code=409, detail="This episode has not aired yet")
        if episode["status"] == "downloading":
            raise HTTPException(status_code=409, detail="This episode is already downloading")
        _, sonarr = tv_main.tv_clients()
        releases = await sonarr.episode_releases(int(episode["sonarr_episode_id"]))
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    limit = _policy()["maximum_episode_size_gb"]
    public: list[dict[str, Any]] = []
    for release in releases:
        item = _release_public(release, limit_gb=limit, scope="episode")
        item["release_token"] = _cache_release(user_id=principal.user_id, series_id=int(snapshot["series_id"]), season_number=season_number, episode_id=int(episode["sonarr_episode_id"]), release=release)
        public.append(item)
    public.sort(key=lambda item: (not item["eligible"], item["size_bytes"] or 10**18, -(item["seeders"] or -1)))
    with main.connect_db() as db:
        main.record_audit(db, actor_id=principal.user_id, actor_name=principal.display_name, action="tv_episode_release_search", request_id=None, details={"tmdb_id": tmdb_id, "season_number": season_number, "episode_number": episode_number, "result_count": len(public)})
        db.commit()
    return {"scope": "episode", "season_number": season_number, "episode_number": episode_number, "episode_title": str(episode["title"]), "maximum_size_gb": limit, "releases": public}


def _active_episode_request(episode_id: int) -> dict[str, Any] | None:
    with main.connect_db() as db:
        row = db.execute(
            "SELECT id,status FROM requests WHERE media_type='tv' AND sonarr_episode_id=? AND status IN ('searching','queued','downloading','processing') ORDER BY id DESC LIMIT 1",
            (episode_id,),
        ).fetchone()
    return dict(row) if row else None


async def grab_tv_release(payload: TvGrabRequest, principal: main.CurrentUser) -> dict[str, Any]:
    initialise_tv_release_database()
    series_id, season_number, episode_id, release = _consume_release(payload.release_token, user_id=principal.user_id)
    if episode_id and _active_episode_request(episode_id):
        raise HTTPException(status_code=409, detail="This episode already has an active acquisition")
    _, sonarr = tv_main.tv_clients()
    try:
        episodes = await sonarr.episodes(series_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    relevant = [item for item in episodes if (episode_id and int(item.get("id") or 0) == episode_id) or (episode_id is None and int(item.get("seasonNumber") or 0) == int(season_number or 0))]
    if episode_id and any(bool(item.get("hasFile")) for item in relevant):
        _invalidate_episode_tokens(episode_id)
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
    episode_number = next((int(item.get("episodeNumber") or 0) for item in relevant), None) if episode_id else None
    now = main.utc_now()
    with main.connect_db() as db:
        cursor = db.execute(
            """
            INSERT INTO requests (
              media_type,title,external_id,requested_by_id,requested_by_name,
              estimated_size_gb,reserved_size_gb,status,rejection_reason,progress,status_message,
              created_at,updated_at,sonarr_series_id,requested_scope,requested_seasons_json,
              available_episode_count,total_episode_count,season_number,episode_number,
              sonarr_episode_id,selected_release_title,selected_release_size_bytes,selected_release_source
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "tv", selected_title, str(series_id), principal.user_id, principal.display_name,
                public["size_gb"] or 0.01, 0, "downloading", None, 0, "Downloading selected TV release",
                now, now, series_id, "episode" if episode_id else "season_pack",
                json.dumps([season_number] if season_number else []), 0, 1 if episode_id else len(relevant),
                season_number, episode_number, episode_id, selected_title, int(release.get("size") or 0), public.get("source"),
            ),
        )
        request_id = int(cursor.lastrowid)
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="tv_episode_release_selected" if episode_id else "tv_season_release_selected",
            request_id=request_id,
            details={"series_id": series_id, "season_number": season_number, "episode_id": episode_id, "size_bytes": int(release.get("size") or 0)},
        )
        db.commit()
    return {"request_id": request_id, "status": "downloading", "scope": "episode" if episode_id else "season", "title": selected_title}


async def reconcile_selected_tv_releases() -> None:
    initialise_tv_release_database()
    _, sonarr = tv_main.tv_clients()
    with main.connect_db() as db:
        rows = db.execute(
            "SELECT * FROM requests WHERE media_type='tv' AND requested_scope IN ('episode','season_pack') AND status IN ('searching','queued','downloading','processing')"
        ).fetchall()
    series_ids = sorted({int(row["sonarr_series_id"] or 0) for row in rows if int(row["sonarr_series_id"] or 0)})
    for series_id in series_ids:
        try:
            episodes = await sonarr.episodes(series_id)
            queue = await sonarr.queue()
        except MediaServiceError:
            continue
        queued_episode_ids = {int(item.get("episodeId") or 0) for item in queue if item.get("episodeId")}
        with main.connect_db() as db:
            relevant_rows = [dict(row) for row in rows if int(row["sonarr_series_id"] or 0) == series_id]
            for row in relevant_rows:
                if row.get("requested_scope") == "episode":
                    episode_id = int(row.get("sonarr_episode_id") or 0)
                    episode = next((item for item in episodes if int(item.get("id") or 0) == episode_id), None)
                    if not episode:
                        continue
                    if episode.get("hasFile"):
                        status, progress, message = "available", 100.0, "Available in Sonarr library"
                        _invalidate_episode_tokens(episode_id)
                        main.record_audit(db, actor_id="system", actor_name="MediaHub", action="tv_episode_available", request_id=int(row["id"]), details={"episode_id": episode_id})
                    elif episode_id in queued_episode_ids:
                        status, progress, message = "downloading", float(row.get("progress") or 0), "Downloading through Sonarr"
                    else:
                        status, progress, message = "processing", float(row.get("progress") or 0), "Waiting for Sonarr import"
                    db.execute("UPDATE requests SET status=?,progress=?,status_message=?,available_episode_count=?,updated_at=? WHERE id=?", (status, progress, message, 1 if status == "available" else 0, main.utc_now(), row["id"]))
                else:
                    season_number = int(row.get("season_number") or 0)
                    season_eps = [item for item in episodes if int(item.get("seasonNumber") or 0) == season_number]
                    available = sum(bool(item.get("hasFile")) for item in season_eps)
                    total = len(season_eps)
                    queued = any(int(item.get("id") or 0) in queued_episode_ids for item in season_eps)
                    if total and available == total:
                        status, progress, message = "available", 100.0, "Season available in Sonarr library"
                        main.record_audit(db, actor_id="system", actor_name="MediaHub", action="tv_season_available", request_id=int(row["id"]), details={"season_number": season_number})
                    elif available:
                        status, progress, message = "processing", round(available / max(total, 1) * 100, 1), f"Partially available ({available}/{total} episodes)"
                    elif queued:
                        status, progress, message = "downloading", float(row.get("progress") or 0), "Downloading season through Sonarr"
                    else:
                        status, progress, message = "processing", float(row.get("progress") or 0), "Waiting for Sonarr import"
                    db.execute("UPDATE requests SET status=?,progress=?,status_message=?,available_episode_count=?,total_episode_count=?,updated_at=? WHERE id=?", (status, progress, message, available, total, main.utc_now(), row["id"]))
            db.commit()


async def tv_policy(_: main.CurrentUser) -> dict[str, float]:
    return _policy()


async def update_tv_policy(payload: TvPolicyUpdate, _: main.Administrator) -> dict[str, float]:
    try:
        return settings.save_tv_download_settings(maximum_season_size_gb=payload.maximum_season_size_gb, maximum_episode_size_gb=payload.maximum_episode_size_gb)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


async def release_health(_: main.CurrentUser) -> dict[str, Any]:
    return {"version": app.version, "tv_downloads": _policy()}


app.add_api_route("/api/catalog/tv/{tmdb_id}/seasons/{season_number}", season_details, methods=["GET"])
app.add_api_route("/api/catalog/tv/{tmdb_id}/seasons/{season_number}/releases", season_releases, methods=["GET"])
app.add_api_route("/api/catalog/tv/{tmdb_id}/seasons/{season_number}/episodes/{episode_number}/releases", episode_releases, methods=["GET"])
app.add_api_route("/api/tv/releases/grab", grab_tv_release, methods=["POST"])
app.add_api_route("/api/setup/tv-downloads", tv_policy, methods=["GET"])
app.add_api_route("/api/setup/tv-downloads", update_tv_policy, methods=["PUT"])
app.add_api_route("/api/tv-release-health", release_health, methods=["GET"])
