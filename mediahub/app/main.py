from __future__ import annotations

import asyncio
import base64
import hmac
import json
import os
import secrets
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .auth import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LastAdministratorError,
    LoginRateLimitedError,
    Principal,
    Role,
    UsernameUnavailableError,
    authenticate_local_user,
    create_local_user,
    create_session,
    ingress_identity,
    list_users,
    reset_local_password,
    revoke_session,
    session_from_token,
    sync_user,
    update_user_active,
    update_user_role,
)
from .discovery import SupervisorDiscovery
from .integrations import IntegrationTester, integration_configs
from .media_services import (
    MediaServiceError,
    analyse_download_workflow,
    configured_clients,
)
from .settings import (
    APP_DATA,
    load_options,
    public_integration_settings,
    save_integration_settings,
)
from .web import INDEX_HTML

DATABASE_FILE = APP_DATA / "mediahub.db"
ASSET_DIR = Path(__file__).resolve().parent / "assets"
BRAND_ASSETS = {
    "mediahub-logo.png": ASSET_DIR / "mediahub-logo.png.b64",
    "mediahub-icon.png": ASSET_DIR / "mediahub-icon.png.b64",
}

app = FastAPI(title="MediaHub", version="0.6.4-dev")
SESSION_COOKIE = "mediahub_session"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' https://image.tmdb.org data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
        "form-action 'self'"
    )
    if request.url.path.startswith(("/api/auth", "/api/users", "/api/setup", "/api/audit")):
        response.headers["Cache-Control"] = "no-store"
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0]
    if request.url.scheme == "https" or forwarded_proto.strip() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


class MediaRequest(BaseModel):
    media_type: Literal["movie", "tv"]
    title: str = Field(min_length=1, max_length=250)
    external_id: str = Field(min_length=1, max_length=100)
    estimated_size_gb: float = Field(gt=0, le=500)


IntegrationField = Literal[
    "tmdb_api_key",
    "prowlarr_url",
    "prowlarr_api_key",
    "radarr_url",
    "radarr_api_key",
    "radarr_root_folder_path",
    "radarr_quality_profile_id",
    "sonarr_url",
    "sonarr_api_key",
    "qbittorrent_url",
    "qbittorrent_auth_method",
    "qbittorrent_api_key",
    "qbittorrent_username",
    "qbittorrent_password",
]
SecretField = Literal[
    "tmdb_api_key",
    "prowlarr_api_key",
    "radarr_api_key",
    "sonarr_api_key",
    "qbittorrent_api_key",
    "qbittorrent_password",
]


class IntegrationSettingsUpdate(BaseModel):
    updates: dict[IntegrationField, str] = Field(default_factory=dict)
    clear_secrets: list[SecretField] = Field(default_factory=list)


class UserRoleUpdate(BaseModel):
    role: Role


class LocalUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    display_name: str = Field(min_length=1, max_length=250)
    role: Role = "requester"
    password: str = Field(min_length=12, max_length=1024)


class UserPasswordUpdate(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


class UserActiveUpdate(BaseModel):
    active: bool


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class ReleaseRules(BaseModel):
    maximum_size_gb: float = Field(default=3, gt=0, le=100)
    minimum_seeders: int = Field(default=1, ge=0, le=10000)
    require_1080p: bool = True


class MovieRequestCreate(ReleaseRules):
    release_token: str | None = Field(default=None, min_length=16, max_length=200)


RELEASE_CACHE_SECONDS = 25 * 60
release_cache: dict[str, tuple[float, int, str, dict]] = {}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def connect_db() -> sqlite3.Connection:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def initialise_database() -> None:
    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_type TEXT NOT NULL,
                title TEXT NOT NULL,
                external_id TEXT NOT NULL,
                requested_by_id TEXT NOT NULL,
                requested_by_name TEXT NOT NULL,
                estimated_size_gb REAL NOT NULL,
                reserved_size_gb REAL NOT NULL,
                status TEXT NOT NULL,
                rejection_reason TEXT,
                radarr_movie_id INTEGER,
                selected_release_guid TEXT,
                selected_release_title TEXT,
                download_id TEXT,
                progress REAL NOT NULL DEFAULT 0,
                status_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_name TEXT NOT NULL,
                action TEXT NOT NULL,
                request_id INTEGER,
                details_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'manager', 'requester')),
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS local_credentials (
                user_id TEXT PRIMARY KEY,
                username_normalized TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                password_changed_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS login_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                failure_key TEXT NOT NULL,
                attempted_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_role_active
            ON users (role, active);

            CREATE INDEX IF NOT EXISTS idx_sessions_user
            ON sessions (user_id, expires_at);

            CREATE INDEX IF NOT EXISTS idx_login_failures_key_time
            ON login_failures (failure_key, attempted_at);

            CREATE INDEX IF NOT EXISTS idx_requests_external_status
            ON requests (media_type, external_id, status);
            """
        )
        existing_columns = {
            str(row["name"]) for row in db.execute("PRAGMA table_info(requests)").fetchall()
        }
        migrations = {
            "radarr_movie_id": "INTEGER",
            "selected_release_guid": "TEXT",
            "selected_release_title": "TEXT",
            "download_id": "TEXT",
            "progress": "REAL NOT NULL DEFAULT 0",
            "status_message": "TEXT",
        }
        for name, definition in migrations.items():
            if name not in existing_columns:
                db.execute(f"ALTER TABLE requests ADD COLUMN {name} {definition}")


def record_audit(
    db: sqlite3.Connection,
    *,
    actor_id: str,
    actor_name: str,
    action: str,
    request_id: int | None,
    details: dict,
) -> None:
    db.execute(
        """
        INSERT INTO audit_events (
            occurred_at, actor_id, actor_name, action, request_id, details_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (utc_now(), actor_id, actor_name, action, request_id, json.dumps(details)),
    )


def current_user(
    request: Request,
    x_remote_user_id: str | None = Header(default=None, alias="X-Remote-User-Id"),
    x_remote_user_name: str | None = Header(default=None, alias="X-Remote-User-Name"),
    x_remote_user_display_name: str | None = Header(
        default=None,
        alias="X-Remote-User-Display-Name",
    ),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> Principal:
    mode = os.environ.get("MEDIAHUB_AUTH_MODE", "ingress").strip().lower()
    if mode not in {"ingress", "external", "hybrid"}:
        mode = "ingress"

    if mode in {"ingress", "hybrid"} and x_remote_user_id:
        try:
            identity = ingress_identity(
                user_id=x_remote_user_id,
                username=x_remote_user_name,
                display_name=x_remote_user_display_name,
            )
        except AuthenticationRequiredError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error

        with connect_db() as db:
            principal, created = sync_user(db, identity=identity, now=utc_now())
            if created:
                record_audit(
                    db,
                    actor_id=principal.user_id,
                    actor_name=principal.display_name,
                    action="user_registered",
                    request_id=None,
                    details={"role": principal.role, "auth_source": "home_assistant"},
                )
            db.commit()
        request.state.auth_source = "home_assistant"
    elif mode in {"external", "hybrid"}:
        raw_token = request.cookies.get(SESSION_COOKIE, "")
        with connect_db() as db:
            session = session_from_token(db, raw_token=raw_token, now=datetime.now(UTC))
            db.commit()
        if session is None:
            raise HTTPException(status_code=401, detail="Sign in to MediaHub to continue")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not (
            x_csrf_token and hmac.compare_digest(x_csrf_token, session.csrf_token)
        ):
            raise HTTPException(status_code=403, detail="Invalid or missing security token")
        principal = session.principal
        request.state.auth_source = "mediahub"
        request.state.csrf_token = session.csrf_token
        request.state.session_hash = session.session_hash
    else:
        raise HTTPException(
            status_code=401,
            detail="Home Assistant Ingress authentication is required",
        )

    if not principal.active:
        raise HTTPException(status_code=403, detail="This MediaHub user is inactive")
    return principal


CurrentUser = Annotated[Principal, Depends(current_user)]


def administrator(principal: CurrentUser) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required")
    return principal


Administrator = Annotated[Principal, Depends(administrator)]


def manager_or_administrator(principal: CurrentUser) -> Principal:
    if principal.role not in {"admin", "manager"}:
        raise HTTPException(status_code=403, detail="Manager access is required")
    return principal


Manager = Annotated[Principal, Depends(manager_or_administrator)]


def current_reservations_gb(db: sqlite3.Connection) -> float:
    row = db.execute(
        """
        SELECT COALESCE(SUM(reserved_size_gb), 0) AS reserved
        FROM requests
        WHERE status IN ('approved', 'searching', 'queued', 'downloading', 'processing')
        """
    ).fetchone()
    return float(row["reserved"])


def storage_snapshot(db: sqlite3.Connection, estimated_size_gb: float) -> dict:
    options = load_options()
    storage = options.get("storage", {})
    media_path = Path(storage.get("media_path", "/media"))
    minimum_free_gb = float(storage.get("minimum_free_gb", 50))
    safety_margin_gb = float(storage.get("safety_margin_gb", 10))
    multiplier = float(storage.get("reservation_multiplier", 1.5))

    if not media_path.exists():
        raise HTTPException(status_code=503, detail=f"Media path does not exist: {media_path}")

    usage = shutil.disk_usage(media_path)
    free_gb = usage.free / (1024**3)
    reserved_gb = current_reservations_gb(db)
    request_reservation_gb = estimated_size_gb * multiplier
    projected_free_gb = free_gb - reserved_gb - request_reservation_gb - safety_margin_gb
    accepted = projected_free_gb >= minimum_free_gb

    return {
        "media_path": str(media_path),
        "free_gb": round(free_gb, 2),
        "reserved_gb": round(reserved_gb, 2),
        "request_reservation_gb": round(request_reservation_gb, 2),
        "safety_margin_gb": safety_margin_gb,
        "minimum_free_gb": minimum_free_gb,
        "projected_free_gb": round(projected_free_gb, 2),
        "accepted": accepted,
    }


def service_http_error(error: MediaServiceError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=str(error))


def release_with_policy(release: dict, rules: ReleaseRules) -> dict:
    policy_rejections = list(release.get("rejections", []))
    quality = str(release.get("quality", "")).lower()
    size_gb = float(release.get("size_gb") or 0)
    seeders = release.get("seeders")
    if rules.require_1080p and "1080" not in quality:
        policy_rejections.append("MediaHub requires a 1080p release")
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
    result = dict(release)
    result["policy_rejections"] = list(dict.fromkeys(policy_rejections))
    result["eligible"] = bool(release.get("approved")) and not result["policy_rejections"]
    result.pop("info_hash", None)
    result.pop("guid", None)
    return result


def cache_release(tmdb_id: int, user_id: str, release: dict) -> str:
    now = monotonic()
    for token, (expires_at, _, _, _) in list(release_cache.items()):
        if expires_at <= now:
            release_cache.pop(token, None)
    token = secrets.token_urlsafe(24)
    release_cache[token] = (now + RELEASE_CACHE_SECONDS, tmdb_id, user_id, dict(release))
    return token


def cached_release(token: str, tmdb_id: int, user_id: str) -> dict:
    cached = release_cache.pop(token, None)
    if (
        cached is None
        or cached[0] <= monotonic()
        or cached[1] != tmdb_id
        or cached[2] != user_id
    ):
        raise HTTPException(
            status_code=409,
            detail="This release selection expired. Search for releases again.",
        )
    return cached[3]


def request_row(db: sqlite3.Connection, request_id: int) -> dict:
    row = db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Media request not found")
    return dict(row)


def public_request(item: dict) -> dict:
    result = dict(item)
    result.pop("selected_release_guid", None)
    result.pop("download_id", None)
    return result


@app.on_event("startup")
def startup() -> None:
    initialise_database()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/assets/{asset_name}", include_in_schema=False)
def brand_asset(asset_name: str) -> Response:
    asset_file = BRAND_ASSETS.get(asset_name)
    if asset_file is None or not asset_file.is_file():
        raise HTTPException(status_code=404, detail="Brand asset not found")
    try:
        encoded = "".join(asset_file.read_text(encoding="ascii").split())
        content = base64.b64decode(encoded, validate=True)
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=500, detail="Brand asset is unavailable") from error
    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "MediaHub", "version": app.version}


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    if os.environ.get("MEDIAHUB_AUTH_MODE", "ingress").strip().lower() == "ingress":
        raise HTTPException(
            status_code=404,
            detail="MediaHub password login is not available through Home Assistant Ingress",
        )
    remote_address = request.client.host if request.client else "unknown"
    now = datetime.now(UTC)
    with connect_db() as db:
        try:
            principal = authenticate_local_user(
                db,
                username=payload.username,
                password=payload.password,
                remote_address=remote_address,
                now=now,
            )
        except LoginRateLimitedError as error:
            db.commit()
            raise HTTPException(status_code=429, detail=str(error)) from error
        except InvalidCredentialsError as error:
            db.commit()
            raise HTTPException(status_code=401, detail=str(error)) from error

        raw_token, session = create_session(db, principal=principal, now=now)
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="user_logged_in",
            request_id=None,
            details={"auth_source": "mediahub"},
        )
        db.commit()

    forwarded_proto = request.headers.get("X-Forwarded-Proto", "").split(",", 1)[0]
    secure_cookie = request.url.scheme == "https" or forwarded_proto.strip() == "https"
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    result = principal.public_dict()
    result["csrf_token"] = session.csrf_token
    return result


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, principal: CurrentUser) -> dict:
    session_hash = getattr(request.state, "session_hash", "")
    if session_hash:
        with connect_db() as db:
            revoke_session(db, session_hash=session_hash)
            record_audit(
                db,
                actor_id=principal.user_id,
                actor_name=principal.display_name,
                action="user_logged_out",
                request_id=None,
                details={"auth_source": "mediahub"},
            )
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict")
    return {"status": "signed_out"}


@app.get("/api/storage")
def get_storage(_: Manager) -> dict:
    with connect_db() as db:
        return storage_snapshot(db, 0.001)


@app.get("/api/integrations/status")
async def integration_status(_: Manager) -> dict:
    tester = IntegrationTester()
    services = await tester.test_all(integration_configs(load_options()))
    return {
        "services": services,
        "connected": sum(service["status"] == "connected" for service in services),
        "configured": sum(service["configured"] for service in services),
        "total": len(services),
    }


async def setup_payload() -> dict:
    options = load_options()
    tester = IntegrationTester()
    discovery, services = await asyncio.gather(
        SupervisorDiscovery().discover(),
        tester.test_all(integration_configs(options)),
    )
    connections = {
        "services": services,
        "connected": sum(service["status"] == "connected" for service in services),
        "configured": sum(service["configured"] for service in services),
        "total": len(services),
    }
    return {
        "version": app.version,
        "settings": public_integration_settings(options),
        "discovery": discovery,
        "connections": connections,
    }


@app.get("/api/setup")
async def get_setup(_: Administrator) -> dict:
    return await setup_payload()


@app.get("/api/setup/discovery")
async def discover_integrations(_: Administrator) -> dict:
    return await SupervisorDiscovery().discover()


@app.put("/api/setup/integrations")
async def update_integration_settings(
    payload: IntegrationSettingsUpdate,
    principal: Administrator,
) -> dict:
    if any(len(value) > 2048 for value in payload.updates.values()):
        raise HTTPException(
            status_code=422,
            detail="Integration values must be 2048 characters or fewer",
        )

    try:
        save_integration_settings(
            dict(payload.updates),
            clear_secrets=payload.clear_secrets,
        )
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    with connect_db() as db:
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="integration_settings_updated",
            request_id=None,
            details={
                "updated_fields": sorted(payload.updates),
                "cleared_secret_fields": sorted(payload.clear_secrets),
            },
        )
        db.commit()

    return await setup_payload()


@app.get("/api/catalog/movies")
async def movie_catalogue(
    _: CurrentUser,
    query: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1, le=500),
    collection: Literal["popular", "top_rated", "now_playing", "upcoming"] = "popular",
    genre_id: int | None = Query(default=None, ge=1),
    year_from: int | None = Query(default=None, ge=1874, le=2100),
    year_to: int | None = Query(default=None, ge=1874, le=2100),
) -> dict:
    tmdb, _, _ = configured_clients(load_options())
    try:
        return await tmdb.catalogue(
            query=query,
            page=page,
            collection=collection,
            genre_id=genre_id,
            year_from=year_from,
            year_to=year_to,
        )
    except MediaServiceError as error:
        raise service_http_error(error) from error


@app.get("/api/catalog/genres")
async def movie_genres(_: CurrentUser) -> dict:
    tmdb, _, _ = configured_clients(load_options())
    try:
        return await tmdb.genres()
    except MediaServiceError as error:
        raise service_http_error(error) from error


@app.get("/api/catalog/movies/{tmdb_id}")
async def movie_details(tmdb_id: int, _: CurrentUser) -> dict:
    tmdb, _, _ = configured_clients(load_options())
    try:
        return await tmdb.details(tmdb_id)
    except MediaServiceError as error:
        raise service_http_error(error) from error


@app.get("/api/radarr/options")
async def radarr_options(_: Administrator) -> dict:
    _, radarr, _ = configured_clients(load_options())
    try:
        return await radarr.options()
    except MediaServiceError as error:
        raise service_http_error(error) from error


@app.get("/api/setup/download-workflow")
async def download_workflow(_: Administrator) -> dict:
    _, radarr, qbittorrent = configured_clients(load_options())
    radarr_result, qbittorrent_result = await asyncio.gather(
        radarr.download_settings(),
        qbittorrent.download_settings(),
        return_exceptions=True,
    )
    failures = [
        result
        for result in (radarr_result, qbittorrent_result)
        if isinstance(result, Exception)
    ]
    if failures:
        not_configured = all(
            isinstance(error, MediaServiceError)
            and "not configured" in str(error).lower()
            for error in failures
        )
        return {
            "status": "not_configured" if not_configured else "unavailable",
            "message": (
                "Connect Radarr and qBittorrent to validate the download workflow."
                if not_configured
                else "Download paths could not be validated. Check the Radarr and qBittorrent connections."
            ),
            "checks": [],
        }
    return analyse_download_workflow(radarr_result, qbittorrent_result)


async def search_movie_releases(
    tmdb_id: int,
    rules: ReleaseRules,
    user_id: str,
) -> tuple[dict, list[dict]]:
    _, radarr, _ = configured_clients(load_options())
    try:
        radarr_movie = await radarr.ensure_movie(tmdb_id)
        releases = await radarr.releases(int(radarr_movie["id"]))
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Radarr returned an invalid movie response") from error
    except MediaServiceError as error:
        raise service_http_error(error) from error

    public_releases = []
    for release in releases:
        public = release_with_policy(release, rules)
        public["release_token"] = cache_release(tmdb_id, user_id, release)
        public_releases.append(public)
    return radarr_movie, public_releases


@app.post("/api/movies/{tmdb_id}/releases")
async def movie_releases(
    tmdb_id: int,
    rules: ReleaseRules,
    principal: CurrentUser,
) -> dict:
    radarr_movie, releases = await search_movie_releases(tmdb_id, rules, principal.user_id)
    with connect_db() as db:
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="movie_releases_searched",
            request_id=None,
            details={"tmdb_id": tmdb_id, "result_count": len(releases)},
        )
        db.commit()
    return {
        "radarr_movie_id": int(radarr_movie["id"]),
        "rules": rules.model_dump(),
        "releases": releases,
    }


@app.post("/api/movies/{tmdb_id}/request")
async def request_movie(
    tmdb_id: int,
    payload: MovieRequestCreate,
    principal: CurrentUser,
) -> dict:
    tmdb, radarr, _ = configured_clients(load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except MediaServiceError as error:
        raise service_http_error(error) from error

    with connect_db() as db:
        duplicate = db.execute(
            """
            SELECT id, status FROM requests
            WHERE media_type = 'movie' AND external_id = ?
              AND status NOT IN ('rejected', 'cancelled', 'deleted', 'failed')
            ORDER BY id DESC LIMIT 1
            """,
            (str(tmdb_id),),
        ).fetchone()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={"message": "This movie is already requested or available.", **dict(duplicate)},
            )

    selected: dict | None = None
    if payload.release_token:
        selected = cached_release(payload.release_token, tmdb_id, principal.user_id)
        public_selected = release_with_policy(selected, payload)
        if not public_selected["eligible"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "The selected release does not meet the download rules.",
                    "rejections": public_selected["policy_rejections"],
                },
            )
        try:
            radarr_movie = await radarr.ensure_movie(tmdb_id)
            # Refreshing the search also refreshes Radarr's short-lived release cache.
            fresh_releases = await radarr.releases(int(radarr_movie["id"]))
        except MediaServiceError as error:
            raise service_http_error(error) from error
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
        refreshed_selected = release_with_policy(selected, payload)
        if not refreshed_selected["eligible"]:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "The selected release no longer meets the download rules.",
                    "rejections": refreshed_selected["policy_rejections"],
                },
            )
    else:
        radarr_movie, releases = await search_movie_releases(
            tmdb_id,
            payload,
            principal.user_id,
        )
        selected_public = next((item for item in releases if item["eligible"]), None)
        if selected_public:
            selected = cached_release(
                selected_public["release_token"],
                tmdb_id,
                principal.user_id,
            )

    if selected is None:
        raise HTTPException(
            status_code=409,
            detail="No release currently meets the 1080p, size, seeder, and Radarr rules.",
        )

    estimated_size_gb = max(float(selected["size_gb"]), 0.01)
    with connect_db() as db:
        storage = storage_snapshot(db, estimated_size_gb)
        now = utc_now()
        status = "searching" if storage["accepted"] else "rejected"
        rejection_reason = None if storage["accepted"] else "insufficient_storage"
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
        request_id = int(cursor.lastrowid)
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="movie_request_created",
            request_id=request_id,
            details={
                "tmdb_id": tmdb_id,
                "title": movie["title"],
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
        with connect_db() as db:
            rejected_request = request_row(db, request_id)
        return {"request": public_request(rejected_request), "storage": storage}

    try:
        grabbed = await radarr.grab(guid=selected["guid"], indexer_id=selected["indexer_id"])
    except MediaServiceError as error:
        with connect_db() as db:
            db.execute(
                "UPDATE requests SET status = 'failed', reserved_size_gb = 0, status_message = ?, updated_at = ? WHERE id = ?",
                (str(error), utc_now(), request_id),
            )
            record_audit(
                db,
                actor_id="system",
                actor_name="MediaHub",
                action="movie_request_submission_failed",
                request_id=request_id,
                details={"message": str(error)},
            )
            db.commit()
        raise service_http_error(error) from error

    download_id = str(grabbed.get("infoHash") or selected.get("info_hash") or "") or None
    with connect_db() as db:
        db.execute(
            """
            UPDATE requests
            SET status = 'queued', download_id = ?, status_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (download_id, "Release sent to Radarr", utc_now(), request_id),
        )
        record_audit(
            db,
            actor_id="system",
            actor_name="MediaHub",
            action="movie_release_grabbed",
            request_id=request_id,
            details={"indexer": selected["indexer"], "quality": selected["quality"]},
        )
        db.commit()
        result = request_row(db, request_id)
    return {
        "request": public_request(result),
        "release": release_with_policy(selected, payload),
        "storage": storage,
    }


def _download_status(queue_item: dict, torrent: dict | None) -> tuple[str, float, str]:
    tracked_status = str(queue_item.get("trackedDownloadStatus") or "").lower()
    if torrent:
        progress = round(float(torrent.get("progress") or 0) * 100, 1)
        state = str(torrent.get("state") or "")
        if tracked_status in {"warning", "error"}:
            return "processing", progress, "Radarr import needs attention"
        if progress >= 100:
            return "processing", progress, "Download complete, waiting for Radarr import"
        return "downloading", progress, state or "Downloading"
    size = float(queue_item.get("size") or 0)
    size_left = float(queue_item.get("sizeleft") or queue_item.get("sizeLeft") or size)
    progress = round(max(0, min(100, (1 - size_left / size) * 100)), 1) if size else 0
    status = str(queue_item.get("status") or "queued").lower()
    if tracked_status in {"warning", "error"}:
        return "processing", progress, "Radarr import needs attention"
    if status == "completed" or progress >= 100:
        return "processing", 100.0, "Download complete, waiting for Radarr import"
    if status == "downloading" or progress > 0:
        return "downloading", progress, str(queue_item.get("trackedDownloadStatus") or status)
    return "queued", progress, status or "Queued"


@app.get("/api/downloads")
async def downloads(principal: CurrentUser) -> list[dict]:
    _, radarr, qbittorrent = configured_clients(load_options())
    queue_result, movies_result, torrents_result = await asyncio.gather(
        radarr.queue(),
        radarr.movies(),
        qbittorrent.torrents(),
        return_exceptions=True,
    )
    if isinstance(queue_result, Exception) or isinstance(movies_result, Exception):
        error = queue_result if isinstance(queue_result, Exception) else movies_result
        if isinstance(error, MediaServiceError):
            raise service_http_error(error) from error
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

    with connect_db() as db:
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

        results = []
        now = utc_now()
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
            resolved_radarr_movie_id = int(
                (library_movie or {}).get("id") or radarr_movie_id
            )
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
                status, progress, message = _download_status(queue_item, torrent)
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
                record_audit(
                    db,
                    actor_id="system",
                    actor_name="MediaHub",
                    action="movie_available",
                    request_id=item["id"],
                    details={"source": "radarr_library"},
                )
            item.update({"status": status, "progress": progress, "status_message": message})
            results.append(public_request(item))
        db.commit()
    return results


@app.post("/api/requests")
def create_request(
    payload: MediaRequest,
    principal: CurrentUser,
) -> dict:
    options = load_options()
    auto_approve = bool(options.get("approvals", {}).get("auto_approve", True))

    with connect_db() as db:
        duplicate = db.execute(
            """
            SELECT id, status FROM requests
            WHERE media_type = ? AND external_id = ?
              AND status NOT IN ('rejected', 'cancelled', 'deleted', 'failed')
            ORDER BY id DESC LIMIT 1
            """,
            (payload.media_type, payload.external_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={"message": "This title is already requested or available.", **dict(duplicate)},
            )

        storage = storage_snapshot(db, payload.estimated_size_gb)
        status = "approved" if auto_approve and storage["accepted"] else "pending_approval"
        rejection_reason = None
        if not storage["accepted"]:
            status = "rejected"
            rejection_reason = "insufficient_storage"

        now = utc_now()
        cursor = db.execute(
            """
            INSERT INTO requests (
                media_type, title, external_id, requested_by_id, requested_by_name,
                estimated_size_gb, reserved_size_gb, status, rejection_reason,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.media_type,
                payload.title,
                payload.external_id,
                principal.user_id,
                principal.display_name,
                payload.estimated_size_gb,
                storage["request_reservation_gb"] if status == "approved" else 0,
                status,
                rejection_reason,
                now,
                now,
            ),
        )
        request_id = int(cursor.lastrowid)

        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="request_created",
            request_id=request_id,
            details={"payload": payload.model_dump(), "storage": storage, "status": status},
        )
        record_audit(
            db,
            actor_id="system",
            actor_name="MediaHub",
            action=(
                "request_rejected_insufficient_storage"
                if status == "rejected"
                else "request_automatically_approved"
                if status == "approved"
                else "request_pending_approval"
            ),
            request_id=request_id,
            details={"storage": storage},
        )
        db.commit()

    return {
        "id": request_id,
        "status": status,
        "rejection_reason": rejection_reason,
        "storage": storage,
    }


@app.get("/api/requests")
def get_requests(principal: CurrentUser) -> list[dict]:
    with connect_db() as db:
        if principal.role in {"admin", "manager"}:
            rows = db.execute(
                "SELECT * FROM requests ORDER BY created_at DESC, id DESC"
            ).fetchall()
        else:
            rows = db.execute(
                """
                SELECT * FROM requests
                WHERE requested_by_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (principal.user_id,),
            ).fetchall()
        return [public_request(dict(row)) for row in rows]


@app.get("/api/audit")
def list_audit_events(_: Administrator) -> list[dict]:
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM audit_events ORDER BY occurred_at DESC, id DESC LIMIT 500"
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/api/users/me")
def get_current_user(request: Request, principal: CurrentUser) -> dict[str, str | bool]:
    result = principal.public_dict()
    csrf_token = getattr(request.state, "csrf_token", "")
    if csrf_token:
        result["csrf_token"] = csrf_token
    return result


@app.get("/api/users")
def get_users(_: Administrator) -> list[dict[str, str | bool]]:
    with connect_db() as db:
        return list_users(db)


@app.post("/api/users", status_code=201)
def add_local_user(
    payload: LocalUserCreate,
    principal: Administrator,
) -> dict[str, str | bool]:
    with connect_db() as db:
        try:
            created = create_local_user(
                db,
                username=payload.username,
                display_name=payload.display_name,
                role=payload.role,
                password=payload.password,
                now=utc_now(),
            )
        except UsernameUnavailableError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="local_user_created",
            request_id=None,
            details={
                "user_id": created.user_id,
                "username": created.username,
                "role": created.role,
            },
        )
        db.commit()
    return created.public_dict()


@app.put("/api/users/{user_id}/role")
def set_user_role(
    user_id: str,
    payload: UserRoleUpdate,
    principal: Administrator,
) -> dict[str, str | bool]:
    with connect_db() as db:
        try:
            updated = update_user_role(
                db,
                user_id=user_id,
                role=payload.role,
                now=utc_now(),
            )
        except LastAdministratorError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

        if updated is None:
            raise HTTPException(status_code=404, detail="MediaHub user not found")

        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="user_role_updated",
            request_id=None,
            details={"user_id": updated.user_id, "role": updated.role},
        )
        db.commit()
    return updated.public_dict()


@app.put("/api/users/{user_id}/active")
def set_user_active(
    user_id: str,
    payload: UserActiveUpdate,
    principal: Administrator,
) -> dict[str, str | bool]:
    with connect_db() as db:
        try:
            updated = update_user_active(
                db,
                user_id=user_id,
                active=payload.active,
                now=utc_now(),
            )
        except LastAdministratorError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        if updated is None:
            raise HTTPException(status_code=404, detail="MediaHub user not found")
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="user_activation_updated",
            request_id=None,
            details={"user_id": updated.user_id, "active": updated.active},
        )
        db.commit()
    return updated.public_dict()


@app.put("/api/users/{user_id}/password")
def set_user_password(
    user_id: str,
    payload: UserPasswordUpdate,
    principal: Administrator,
) -> dict:
    with connect_db() as db:
        try:
            updated = reset_local_password(
                db,
                user_id=user_id,
                password=payload.password,
                now=utc_now(),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not updated:
            raise HTTPException(
                status_code=404,
                detail="This account does not use a MediaHub password",
            )
        record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="local_user_password_reset",
            request_id=None,
            details={"user_id": user_id},
        )
        db.commit()
    return {"status": "password_reset", "user_id": user_id}
