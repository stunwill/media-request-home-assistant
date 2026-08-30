from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import HTTPException, Query
from pydantic import Field

from . import main, plex_main, rich_details, runtime, settings
from .media_services import MediaServiceError
from .tv_services import SonarrClient, TmdbTvClient

app = plex_main.app
app.version = "0.10.0-dev"


class TvRequestCreate(main.BaseModel):
    scope: Literal["series", "seasons"] = "series"
    seasons: list[int] = Field(default_factory=list, max_length=100)


def tv_clients(options: dict[str, Any] | None = None) -> tuple[TmdbTvClient, SonarrClient]:
    values = (options or main.load_options()).get("integrations", {})
    return (
        TmdbTvClient(str(values.get("tmdb_api_key") or "")),
        SonarrClient(
            str(values.get("sonarr_url") or ""),
            str(values.get("sonarr_api_key") or ""),
            root_folder_path=str(values.get("sonarr_root_folder_path") or ""),
            quality_profile_id=int(values.get("sonarr_quality_profile_id") or 0),
        ),
    )


def initialise_tv_database() -> None:
    with main.connect_db() as db:
        columns = {str(row["name"]) for row in db.execute("PRAGMA table_info(requests)").fetchall()}
        migrations = {
            "sonarr_series_id": "INTEGER",
            "requested_scope": "TEXT",
            "requested_seasons_json": "TEXT",
            "available_episode_count": "INTEGER NOT NULL DEFAULT 0",
            "total_episode_count": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in migrations.items():
            if name not in columns:
                db.execute(f"ALTER TABLE requests ADD COLUMN {name} {definition}")
        db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_requests_tv_external
            ON requests (media_type, external_id, status)
            """
        )
        db.commit()


@app.on_event("startup")
def tv_startup() -> None:
    initialise_tv_database()


async def tv_catalogue(
    _: main.CurrentUser,
    query: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=500),
    collection: Literal["popular", "airing_today", "on_the_air", "top_rated"] = "popular",
    genre_id: int | None = Query(default=None, ge=1),
    year_from: int | None = Query(default=None, ge=1874, le=2100),
    year_to: int | None = Query(default=None, ge=1874, le=2100),
    rating_from: float | None = Query(default=None, ge=1, le=10),
    rating_to: float | None = Query(default=None, ge=1, le=10),
) -> dict[str, Any]:
    tmdb, _ = tv_clients()
    try:
        return await tmdb.catalogue(
            query=query,
            page=page,
            collection=collection,
            genre_id=genre_id,
            year_from=year_from,
            year_to=year_to,
            rating_from=rating_from,
            rating_to=rating_to,
        )
    except MediaServiceError as error:
        raise main.service_http_error(error) from error


async def tv_genres(_: main.CurrentUser) -> dict[str, Any]:
    tmdb, _ = tv_clients()
    try:
        return await tmdb.genres()
    except MediaServiceError as error:
        raise main.service_http_error(error) from error


async def tv_details(tmdb_id: int, _: main.CurrentUser) -> dict[str, Any]:
    tmdb, _ = tv_clients()
    try:
        show = await tmdb.details(tmdb_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    show["context"] = "browse"
    show["ratings"] = rich_details._rating_cards({
        "tmdb_id": tmdb_id,
        "rating": show.get("rating"),
        "imdb_id": (show.get("external_ids") or {}).get("imdb_id"),
    })
    return show


def _tv_duplicate(tmdb_id: int, selected_seasons: list[int]) -> dict[str, Any] | None:
    active = {"approved", "pending_approval", "searching", "queued", "downloading", "processing", "available"}
    placeholders = ",".join("?" for _ in active)
    with main.connect_db() as db:
        rows = db.execute(
            f"""
            SELECT id,status,requested_scope,requested_seasons_json
            FROM requests
            WHERE media_type='tv' AND external_id=? AND status IN ({placeholders})
            ORDER BY id DESC
            """,
            (str(tmdb_id), *sorted(active)),
        ).fetchall()
    requested = set(selected_seasons)
    for row in rows:
        item = dict(row)
        scope = str(item.get("requested_scope") or "series")
        if scope == "series" or not requested:
            return item
        existing = set(json.loads(str(item.get("requested_seasons_json") or "[]")))
        if existing & requested:
            return item
    return None


async def request_tv(
    tmdb_id: int,
    payload: TvRequestCreate,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    initialise_tv_database()
    tmdb, sonarr = tv_clients()
    try:
        show = await tmdb.details(tmdb_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error

    available_seasons = {int(item["season_number"]) for item in show.get("seasons", [])}
    selected = sorted({int(value) for value in payload.seasons if int(value) > 0})
    if payload.scope == "seasons":
        if not selected:
            raise HTTPException(status_code=422, detail="Select at least one season")
        invalid = [value for value in selected if value not in available_seasons]
        if invalid:
            raise HTTPException(status_code=422, detail=f"Unknown season selection: {invalid}")
    else:
        selected = []

    duplicate = _tv_duplicate(tmdb_id, selected)
    if duplicate:
        raise HTTPException(status_code=409, detail={"message": "This TV show or selected season is already requested.", **duplicate})

    try:
        series = await sonarr.ensure_series(show, selected_seasons=selected or None)
        series_id = int(series.get("id") or 0)
        if not series_id:
            raise MediaServiceError("Sonarr returned an invalid series response")
        await sonarr.search(series_id, selected or None)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error

    now = main.utc_now()
    with main.connect_db() as db:
        cursor = db.execute(
            """
            INSERT INTO requests (
                media_type,title,external_id,requested_by_id,requested_by_name,
                estimated_size_gb,reserved_size_gb,status,rejection_reason,
                progress,status_message,created_at,updated_at,sonarr_series_id,
                requested_scope,requested_seasons_json,available_episode_count,total_episode_count
            ) VALUES ('tv',?,?,?,?,0.01,0,'searching',NULL,0,?,?,?,?,?,?,0,0)
            """,
            (
                show["name"], str(tmdb_id), principal.user_id, principal.display_name,
                "Searching in Sonarr", now, now, series_id,
                payload.scope, json.dumps(selected),
            ),
        )
        request_id = int(cursor.lastrowid)
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="tv_request_created",
            request_id=request_id,
            details={"tmdb_id": tmdb_id, "scope": payload.scope, "seasons": selected},
        )
        db.commit()
    return {"id": request_id, "status": "searching", "media_type": "tv", "title": show["name"], "scope": payload.scope, "seasons": selected}


async def sonarr_options(_: main.Administrator) -> dict[str, Any]:
    _, sonarr = tv_clients()
    try:
        return await sonarr.options()
    except MediaServiceError as error:
        raise main.service_http_error(error) from error


async def reconcile_tv_requests() -> None:
    initialise_tv_database()
    _, sonarr = tv_clients()
    try:
        series_items = await sonarr.series()
        queue = await sonarr.queue()
    except MediaServiceError:
        return
    by_id = {int(item.get("id") or 0): item for item in series_items}
    queue_series_ids = {int(item.get("seriesId") or 0) for item in queue}
    with main.connect_db() as db:
        rows = db.execute(
            """
            SELECT * FROM requests WHERE media_type='tv'
              AND status NOT IN ('rejected','cancelled','deleted','failed','superseded')
            """
        ).fetchall()
        for row in rows:
            item = dict(row)
            series_id = int(item.get("sonarr_series_id") or 0)
            series = by_id.get(series_id)
            if not series:
                continue
            try:
                episodes = await sonarr.episodes(series_id)
            except MediaServiceError:
                continue
            selected = set(json.loads(str(item.get("requested_seasons_json") or "[]")))
            relevant = [
                episode for episode in episodes
                if int(episode.get("seasonNumber") or 0) > 0
                and (not selected or int(episode.get("seasonNumber") or 0) in selected)
            ]
            total = len(relevant)
            available = sum(bool(episode.get("hasFile")) for episode in relevant)
            if total and available >= total:
                status, message, progress = "available", "Available in Sonarr library", 100.0
            elif available:
                status, message, progress = "processing", f"Partially available ({available}/{total} episodes)", round((available / max(total, 1)) * 100, 1)
            elif series_id in queue_series_ids:
                status, message, progress = "downloading", "Downloading through Sonarr", float(item.get("progress") or 0)
            else:
                status, message, progress = "searching", "Searching in Sonarr", float(item.get("progress") or 0)
            db.execute(
                """
                UPDATE requests SET status=?,status_message=?,progress=?,available_episode_count=?,
                    total_episode_count=?,updated_at=? WHERE id=?
                """,
                (status, message, progress, available, total, main.utc_now(), item["id"]),
            )
        db.commit()


async def downloads_with_tv(principal: main.CurrentUser) -> list[dict[str, Any]]:
    await reconcile_tv_requests()
    movies = await runtime.enhanced_main.downloads(principal)
    with main.connect_db() as db:
        if principal.role in {"admin", "manager"}:
            rows = db.execute("SELECT * FROM requests WHERE media_type='tv' ORDER BY created_at DESC").fetchall()
        else:
            rows = db.execute("SELECT * FROM requests WHERE media_type='tv' AND requested_by_id=? ORDER BY created_at DESC", (principal.user_id,)).fetchall()
    tv_items = []
    for row in rows:
        item = main.public_request(dict(row))
        item["media_type"] = "tv"
        item["requested_seasons"] = json.loads(str(item.pop("requested_seasons_json", "[]") or "[]"))
        tv_items.append(item)
    return sorted([*movies, *tv_items], key=lambda item: str(item.get("created_at") or ""), reverse=True)


async def tv_download_details(request_id: int, principal: main.CurrentUser) -> dict[str, Any]:
    initialise_tv_database()
    with main.connect_db() as db:
        row = db.execute("SELECT * FROM requests WHERE id=? AND media_type='tv'", (request_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="TV request not found")
    item = dict(row)
    if principal.role not in {"admin", "manager"} and item["requested_by_id"] != principal.user_id:
        raise HTTPException(status_code=403, detail="This TV request is not available to this user")
    tmdb, _ = tv_clients()
    try:
        show = await tmdb.details(int(item["external_id"]))
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    show["context"] = "downloads"
    show["request"] = {
        "id": int(item["id"]),
        "requested_by": str(item["requested_by_name"]),
        "requested_at": str(item["created_at"]),
        "status": str(item["status"]),
        "status_message": str(item.get("status_message") or ""),
        "progress": float(item.get("progress") or 0),
        "scope": str(item.get("requested_scope") or "series"),
        "seasons": json.loads(str(item.get("requested_seasons_json") or "[]")),
        "available_episode_count": int(item.get("available_episode_count") or 0),
        "total_episode_count": int(item.get("total_episode_count") or 0),
    }
    return show


plex_main.plex_integration.rich_details.runtime.enhanced_main._replace_route("/api/downloads", "GET", downloads_with_tv)
app.add_api_route("/api/catalog/tv", tv_catalogue, methods=["GET"])
app.add_api_route("/api/catalog/tv/genres", tv_genres, methods=["GET"])
app.add_api_route("/api/catalog/tv/{tmdb_id}", tv_details, methods=["GET"])
app.add_api_route("/api/tv/{tmdb_id}/request", request_tv, methods=["POST"])
app.add_api_route("/api/sonarr/options", sonarr_options, methods=["GET"])
app.add_api_route("/api/downloads/tv/{request_id}/details", tv_download_details, methods=["GET"])
