from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .auth import (
    AuthenticationRequiredError,
    LastAdministratorError,
    Principal,
    Role,
    ingress_identity,
    list_users,
    sync_user,
    update_user_role,
)
from .discovery import SupervisorDiscovery
from .integrations import IntegrationTester, integration_configs
from .settings import (
    APP_DATA,
    load_options,
    public_integration_settings,
    save_integration_settings,
)
from .web import INDEX_HTML

DATABASE_FILE = APP_DATA / "mediahub.db"

app = FastAPI(title="MediaHub", version="0.4.0-dev")


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
    "sonarr_url",
    "sonarr_api_key",
    "qbittorrent_url",
    "qbittorrent_username",
    "qbittorrent_password",
]
SecretField = Literal[
    "tmdb_api_key",
    "prowlarr_api_key",
    "radarr_api_key",
    "sonarr_api_key",
    "qbittorrent_password",
]


class IntegrationSettingsUpdate(BaseModel):
    updates: dict[IntegrationField, str] = Field(default_factory=dict)
    clear_secrets: list[SecretField] = Field(default_factory=list)


class UserRoleUpdate(BaseModel):
    role: Role


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def connect_db() -> sqlite3.Connection:
    APP_DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
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

            CREATE INDEX IF NOT EXISTS idx_users_role_active
            ON users (role, active);
            """
        )


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
    x_remote_user_id: str | None = Header(default=None, alias="X-Remote-User-Id"),
    x_remote_user_name: str | None = Header(default=None, alias="X-Remote-User-Name"),
    x_remote_user_display_name: str | None = Header(
        default=None,
        alias="X-Remote-User-Display-Name",
    ),
) -> Principal:
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
                details={"role": principal.role},
            )
        db.commit()

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


@app.on_event("startup")
def startup() -> None:
    initialise_database()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return INDEX_HTML


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "MediaHub", "version": app.version}


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
        return [dict(row) for row in rows]


@app.get("/api/audit")
def list_audit_events(_: Administrator) -> list[dict]:
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM audit_events ORDER BY occurred_at DESC, id DESC LIMIT 500"
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/api/users/me")
def get_current_user(principal: CurrentUser) -> dict[str, str | bool]:
    return principal.public_dict()


@app.get("/api/users")
def get_users(_: Administrator) -> list[dict[str, str | bool]]:
    with connect_db() as db:
        return list_users(db)


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
