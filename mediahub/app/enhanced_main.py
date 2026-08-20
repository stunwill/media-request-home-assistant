from __future__ import annotations

import asyncio
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

from . import main
from .media_services import MediaServiceError

app = main.app
app.version = "0.6.6-dev"

ACTIVE_REQUEST_STATUSES = {
    "approved",
    "pending_approval",
    "searching",
    "queued",
    "downloading",
    "processing",
    "available",
}
LOW_QUALITY_MARKERS = (
    "cam",
    "hdcam",
    "telesync",
    " ts ",
    ".ts.",
    "-ts-",
    "telecine",
    " tc ",
    ".tc.",
    "screener",
    "scr",
)
QUALITY_REJECTION_MARKERS = (
    "quality",
    "profile",
    "cutoff",
    "resolution",
    "720",
    "1080",
    "2160",
)


def _parse_release_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def is_recent_movie(movie: dict[str, Any], *, today: date | None = None) -> bool:
    released = _parse_release_date(movie.get("release_date"))
    if released is None:
        return False
    today = today or date.today()
    age_days = (today - released).days
    return -30 <= age_days <= 365


def _is_low_quality_release(release: dict[str, Any]) -> bool:
    haystack = f" {release.get('quality', '')} {release.get('title', '')} ".lower()
    return any(marker in haystack for marker in LOW_QUALITY_MARKERS)


def _only_quality_rejections(rejections: list[str]) -> bool:
    if not rejections:
        return True
    return all(
        any(marker in rejection.lower() for marker in QUALITY_REJECTION_MARKERS)
        for rejection in rejections
    )


def recent_fallback_policy(release: dict[str, Any], rules: main.ReleaseRules) -> dict[str, Any]:
    result = dict(release)
    rejections = [str(value) for value in release.get("rejections", [])]
    policy_rejections: list[str] = []
    size_gb = float(release.get("size_gb") or 0)
    seeders = release.get("seeders")

    if not _is_low_quality_release(release):
        policy_rejections.append("Not a supported recent-release fallback quality")
    if not _only_quality_rejections(rejections):
        policy_rejections.extend(rejections)
    if not size_gb or size_gb > rules.maximum_size_gb:
        policy_rejections.append(
            f"Release exceeds the {rules.maximum_size_gb:g} GB movie limit"
        )
    if seeders is None or int(seeders) < rules.minimum_seeders:
        policy_rejections.append(
            f"Release has fewer than {rules.minimum_seeders} seeders"
        )
    if not release.get("download_allowed", True):
        policy_rejections.append("Radarr does not allow this release to be downloaded")

    result["policy_rejections"] = list(dict.fromkeys(policy_rejections))
    result["eligible"] = not result["policy_rejections"]
    result["recent_quality_fallback"] = True
    result["quality_warning"] = (
        "Temporary low-quality release. MediaHub normally prefers 720p/1080p and only "
        "offers this because the movie was released within the last 12 months and no "
        "eligible HD release is currently available."
    )
    result.pop("info_hash", None)
    result.pop("guid", None)
    return result


async def search_movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    user_id: str,
    *,
    movie: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    tmdb, radarr, _ = main.configured_clients(main.load_options())
    try:
        if movie is None:
            movie = await tmdb.details(tmdb_id)
        radarr_movie = await radarr.ensure_movie(tmdb_id)
        releases = await radarr.releases(int(radarr_movie["id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Radarr returned an invalid movie response") from error
    except MediaServiceError as error:
        raise main.service_http_error(error) from error

    strict_public: list[dict[str, Any]] = []
    for release in releases:
        public = main.release_with_policy(release, rules)
        public["recent_quality_fallback"] = False
        public["release_token"] = main.cache_release(tmdb_id, user_id, release)
        strict_public.append(public)

    if any(item["eligible"] for item in strict_public) or not is_recent_movie(movie):
        return radarr_movie, strict_public, False

    fallback_public: list[dict[str, Any]] = []
    for release in releases:
        public = recent_fallback_policy(release, rules)
        public["release_token"] = main.cache_release(tmdb_id, user_id, release)
        fallback_public.append(public)

    # Keep the full release list visible, but replace strict rejection results with
    # fallback evaluation so CAM/TS-style candidates can be deliberately selected.
    return radarr_movie, fallback_public, any(item["eligible"] for item in fallback_public)


def _request_duplicate(db: Any, tmdb_id: int) -> dict[str, Any] | None:
    placeholders = ",".join("?" for _ in ACTIVE_REQUEST_STATUSES)
    row = db.execute(
        f"""
        SELECT id, status, requested_by_name, created_at
        FROM requests
        WHERE media_type = 'movie' AND external_id = ?
          AND status IN ({placeholders})
        ORDER BY id DESC LIMIT 1
        """,
        (str(tmdb_id), *sorted(ACTIVE_REQUEST_STATUSES)),
    ).fetchone()
    return dict(row) if row else None


async def _radarr_duplicate(radarr: Any, tmdb_id: int) -> dict[str, Any] | None:
    movies, queue = await asyncio.gather(radarr.movies(), radarr.queue())
    movie = next(
        (item for item in movies if int(item.get("tmdbId") or 0) == tmdb_id),
        None,
    )
    if not movie:
        return None
    if movie.get("hasFile"):
        return {"status": "available", "radarr_movie_id": int(movie.get("id") or 0)}
    movie_id = int(movie.get("id") or 0)
    if any(int(item.get("movieId") or 0) == movie_id for item in queue):
        return {"status": "queued", "radarr_movie_id": movie_id}
    return None


def _choose_download_rows(rows: list[Any]) -> list[Any]:
    rank = {
        "available": 100,
        "processing": 90,
        "downloading": 80,
        "queued": 70,
        "searching": 60,
        "approved": 50,
        "pending_approval": 40,
        "failed": 20,
        "rejected": 10,
        "cancelled": 5,
        "deleted": 0,
        "superseded": -1,
    }
    selected: dict[str, Any] = {}
    for row in rows:
        item = dict(row)
        key = str(item.get("external_id") or f"request:{item.get('id')}")
        current = selected.get(key)
        if current is None:
            selected[key] = row
            continue
        current_item = dict(current)
        candidate_key = (
            rank.get(str(item.get("status")), 30),
            str(item.get("updated_at") or item.get("created_at") or ""),
            int(item.get("id") or 0),
        )
        current_key = (
            rank.get(str(current_item.get("status")), 30),
            str(current_item.get("updated_at") or current_item.get("created_at") or ""),
            int(current_item.get("id") or 0),
        )
        if candidate_key > current_key:
            selected[key] = row
    return sorted(
        selected.values(),
        key=lambda row: (str(dict(row).get("created_at") or ""), int(dict(row).get("id") or 0)),
        reverse=True,
    )


def _cleanup_historical_active_duplicates() -> None:
    with main.connect_db() as db:
        rows = db.execute(
            """
            SELECT id, external_id, status
            FROM requests
            WHERE media_type = 'movie'
            ORDER BY external_id, id DESC
            """
        ).fetchall()
        seen: set[str] = set()
        for row in rows:
            item = dict(row)
            external_id = str(item.get("external_id") or "")
            if not external_id or item.get("status") not in ACTIVE_REQUEST_STATUSES:
                continue
            if external_id not in seen:
                seen.add(external_id)
                continue
            db.execute(
                """
                UPDATE requests
                SET status = 'superseded', reserved_size_gb = 0,
                    status_message = 'Superseded duplicate request', updated_at = ?
                WHERE id = ?
                """,
                (main.utc_now(), item["id"]),
            )
        db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_requests_one_active_movie
            ON requests (external_id)
            WHERE media_type = 'movie'
              AND status IN (
                'approved','pending_approval','searching','queued',
                'downloading','processing','available'
              )
            """
        )
        db.commit()


@app.on_event("startup")
def enhanced_startup() -> None:
    _cleanup_historical_active_duplicates()


async def movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    tmdb, _, _ = main.configured_clients(main.load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    radarr_movie, releases, fallback_active = await search_movie_releases(
        tmdb_id,
        rules,
        principal.user_id,
        movie=movie,
    )
    with main.connect_db() as db:
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="movie_releases_searched",
            request_id=None,
            details={
                "tmdb_id": tmdb_id,
                "result_count": len(releases),
                "recent_quality_fallback": fallback_active,
            },
        )
        db.commit()
    return {
        "radarr_movie_id": int(radarr_movie["id"]),
        "rules": rules.model_dump(),
        "recent_quality_fallback": fallback_active,
        "releases": releases,
    }


async def request_movie(
    tmdb_id: int,
    payload: main.MovieRequestCreate,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    tmdb, radarr, _ = main.configured_clients(main.load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error

    with main.connect_db() as db:
        duplicate = _request_duplicate(db, tmdb_id)
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={"message": "This movie is already requested or available.", **duplicate},
        )

    try:
        radarr_duplicate = await _radarr_duplicate(radarr, tmdb_id)
    except MediaServiceError as error:
        raise main.service_http_error(error) from error
    if radarr_duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "This movie is already queued or available in Radarr.",
                **radarr_duplicate,
            },
        )

    selected: dict[str, Any] | None = None
    selected_public: dict[str, Any] | None = None
    fallback_active = False

    if payload.release_token:
        selected = main.cached_release(payload.release_token, tmdb_id, principal.user_id)
        strict = main.release_with_policy(selected, payload)
        selected_public = strict
        if not strict["eligible"] and is_recent_movie(movie):
            selected_public = recent_fallback_policy(selected, payload)
            fallback_active = bool(selected_public["eligible"])
        if not selected_public["eligible"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "The selected release does not meet the download rules.",
                    "rejections": selected_public["policy_rejections"],
                },
            )
        try:
            radarr_movie = await radarr.ensure_movie(tmdb_id)
            fresh_releases = await radarr.releases(int(radarr_movie["id"]))
        except MediaServiceError as error:
            raise main.service_http_error(error) from error
        selected = next(
            (
                item
                for item in fresh_releases
                if item["guid"] == selected["guid"]
                and item["indexer_id"] == selected["indexer_id"]
            ),
            None,
        )
        if selected is None:
            raise HTTPException(
                status_code=409,
                detail="The selected release is no longer available. Search again.",
            )
        selected_public = main.release_with_policy(selected, payload)
        if not selected_public["eligible"] and is_recent_movie(movie):
            selected_public = recent_fallback_policy(selected, payload)
            fallback_active = bool(selected_public["eligible"])
        if not selected_public["eligible"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "The selected release no longer meets the download rules.",
                    "rejections": selected_public["policy_rejections"],
                },
            )
    else:
        radarr_movie, releases, fallback_active = await search_movie_releases(
            tmdb_id,
            payload,
            principal.user_id,
            movie=movie,
        )
        candidate = next((item for item in releases if item["eligible"]), None)
        if candidate:
            selected = main.cached_release(
                candidate["release_token"],
                tmdb_id,
                principal.user_id,
            )
            selected_public = candidate

    if selected is None:
        raise HTTPException(
            status_code=409,
            detail="No release currently meets the selected quality, size, seeder, and Radarr rules.",
        )

    estimated_size_gb = max(float(selected["size_gb"]), 0.01)
    with main.connect_db() as db:
        # Re-check inside the write transaction to close the ordinary double-click race.
        duplicate = _request_duplicate(db, tmdb_id)
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={"message": "This movie is already requested or available.", **duplicate},
            )
        storage = main.storage_snapshot(db, estimated_size_gb)
        now = main.utc_now()
        status = "searching" if storage["accepted"] else "rejected"
        rejection_reason = None if storage["accepted"] else "insufficient_storage"
        try:
            cursor = db.execute(
                """
                INSERT INTO requests (
                    media_type, title, external_id, requested_by_id, requested_by_name,
                    estimated_size_gb, reserved_size_gb, status, rejection_reason,
                    radarr_movie_id, selected_release_guid, selected_release_title,
                    download_id, progress, status_message, created_at, updated_at
                ) VALUES ('movie', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    movie["title"],
                    str(tmdb_id),
                    principal.user_id,
                    principal.display_name,
                    estimated_size_gb,
                    storage["request_reservation_gb"] if storage["accepted"] else 0,
                    status,
                    rejection_reason,
                    int(radarr_movie["id"]),
                    selected["guid"],
                    selected["title"],
                    selected.get("info_hash") or None,
                    "Submitting release to Radarr" if storage["accepted"] else "Insufficient storage",
                    now,
                    now,
                ),
            )
        except Exception as error:
            if "idx_requests_one_active_movie" in str(error) or "UNIQUE constraint failed" in str(error):
                raise HTTPException(
                    status_code=409,
                    detail="This movie was requested by another request at the same time.",
                ) from error
            raise
        request_id = int(cursor.lastrowid)
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="movie_request_created",
            request_id=request_id,
            details={
                "tmdb_id": tmdb_id,
                "title": movie["title"],
                "recent_quality_fallback": fallback_active,
                "release": {
                    "indexer": selected["indexer"],
                    "title": selected["title"],
                    "size_gb": selected["size_gb"],
                    "quality": selected["quality"],
                },
                "storage": storage,
            },
        )
        db.commit()

    if not storage["accepted"]:
        with main.connect_db() as db:
            rejected_request = main.request_row(db, request_id)
        return {"request": main.public_request(rejected_request), "storage": storage}

    try:
        grabbed = await radarr.grab(guid=selected["guid"], indexer_id=selected["indexer_id"])
    except MediaServiceError as error:
        with main.connect_db() as db:
            db.execute(
                "UPDATE requests SET status = 'failed', reserved_size_gb = 0, status_message = ?, updated_at = ? WHERE id = ?",
                (str(error), main.utc_now(), request_id),
            )
            main.record_audit(
                db,
                actor_id="system",
                actor_name="MediaHub",
                action="movie_request_submission_failed",
                request_id=request_id,
                details={"message": str(error)},
            )
            db.commit()
        raise main.service_http_error(error) from error

    download_id = str(grabbed.get("infoHash") or selected.get("info_hash") or "") or None
    with main.connect_db() as db:
        db.execute(
            """
            UPDATE requests
            SET status = 'queued', download_id = ?, status_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (download_id, "Release sent to Radarr", main.utc_now(), request_id),
        )
        main.record_audit(
            db,
            actor_id="system",
            actor_name="MediaHub",
            action="movie_release_grabbed",
            request_id=request_id,
            details={
                "indexer": selected["indexer"],
                "quality": selected["quality"],
                "recent_quality_fallback": fallback_active,
            },
        )
        db.commit()
        result = main.request_row(db, request_id)
    return {
        "request": main.public_request(result),
        "release": selected_public or main.release_with_policy(selected, payload),
        "storage": storage,
    }


async def downloads(principal: main.CurrentUser) -> list[dict[str, Any]]:
    _, radarr, qbittorrent = main.configured_clients(main.load_options())
    queue_result, movies_result, torrents_result = await asyncio.gather(
        radarr.queue(),
        radarr.movies(),
        qbittorrent.torrents(),
        return_exceptions=True,
    )
    if isinstance(queue_result, Exception) or isinstance(movies_result, Exception):
        error = queue_result if isinstance(queue_result, Exception) else movies_result
        if isinstance(error, MediaServiceError):
            raise main.service_http_error(error) from error
        raise HTTPException(status_code=502, detail="Radarr status could not be loaded")

    queue_by_movie = {
        int(item.get("movieId") or 0): item
        for item in queue_result
        if isinstance(item, dict) and item.get("movieId")
    }
    library_by_movie = {
        int(item.get("id") or 0): item
        for item in movies_result
        if isinstance(item, dict) and item.get("id")
    }
    library_by_tmdb = {
        int(item.get("tmdbId") or 0): item
        for item in movies_result
        if isinstance(item, dict) and item.get("tmdbId")
    }
    torrents = [] if isinstance(torrents_result, Exception) else torrents_result
    torrent_by_hash = {
        str(item.get("hash") or "").lower(): item
        for item in torrents
        if isinstance(item, dict) and item.get("hash")
    }

    with main.connect_db() as db:
        if principal.role in {"admin", "manager"}:
            rows = db.execute(
                "SELECT * FROM requests WHERE media_type = 'movie' ORDER BY created_at DESC, id DESC"
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM requests
                WHERE media_type = 'movie' AND requested_by_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (principal.user_id,),
            ).fetchall()
        rows = _choose_download_rows(list(rows))

        results: list[dict[str, Any]] = []
        now = main.utc_now()
        for row in rows:
            item = dict(row)
            radarr_movie_id = int(item.get("radarr_movie_id") or 0)
            queue_item = queue_by_movie.get(radarr_movie_id)
            library_movie = library_by_movie.get(radarr_movie_id)
            try:
                tmdb_id = int(item.get("external_id") or 0)
            except (TypeError, ValueError):
                tmdb_id = 0
            if not library_movie and tmdb_id:
                library_movie = library_by_tmdb.get(tmdb_id)
            resolved_radarr_movie_id = int((library_movie or {}).get("id") or radarr_movie_id)
            torrent = torrent_by_hash.get(str(item.get("download_id") or "").lower())
            if library_movie and library_movie.get("hasFile"):
                message = (
                    "Available in the media library; qBittorrent retains the seeding data"
                    if torrent
                    else "Available in the media library"
                )
                status, progress = "available", 100.0
            elif queue_item:
                download_id = str(queue_item.get("downloadId") or item.get("download_id") or "")
                torrent = torrent_by_hash.get(download_id.lower())
                status, progress, message = main._download_status(queue_item, torrent)
                item["download_id"] = download_id or item.get("download_id")
            else:
                status = item["status"]
                progress = float(item.get("progress") or 0)
                message = str(item.get("status_message") or status.replace("_", " ").title())

            changed = (
                status != item["status"]
                or progress != float(item.get("progress") or 0)
                or message != str(item.get("status_message") or "")
                or resolved_radarr_movie_id != radarr_movie_id
            )
            if changed:
                db.execute(
                    """
                    UPDATE requests
                    SET status = ?, progress = ?, status_message = ?, download_id = ?,
                        radarr_movie_id = ?,
                        reserved_size_gb = CASE WHEN ? IN ('available', 'failed') THEN 0 ELSE reserved_size_gb END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        status,
                        progress,
                        message,
                        item.get("download_id"),
                        resolved_radarr_movie_id or None,
                        status,
                        now,
                        item["id"],
                    ),
                )
            if status == "available" and item["status"] != "available":
                main.record_audit(
                    db,
                    actor_id="system",
                    actor_name="MediaHub",
                    action="movie_available",
                    request_id=item["id"],
                    details={"source": "radarr_library"},
                )
            item.update({"status": status, "progress": progress, "status_message": message})
            results.append(main.public_request(item))
        db.commit()
    return results


def _replace_route(path: str, method: str, endpoint: Any) -> None:
    app.router.routes = [
        route
        for route in app.router.routes
        if not (
            getattr(route, "path", None) == path
            and method in (getattr(route, "methods", set()) or set())
        )
    ]
    app.add_api_route(path, endpoint, methods=[method])


_replace_route("/api/movies/{tmdb_id}/releases", "POST", movie_releases)
_replace_route("/api/movies/{tmdb_id}/request", "POST", request_movie)
_replace_route("/api/downloads", "GET", downloads)
