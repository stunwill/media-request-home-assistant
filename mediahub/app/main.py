from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

APP_DATA = Path("/data")
OPTIONS_FILE = Path("/data/options.json")
DATABASE_FILE = APP_DATA / "mediahub.db"

app = FastAPI(title="MediaHub", version="0.1.1-dev")


class MediaRequest(BaseModel):
    media_type: Literal["movie", "tv"]
    title: str = Field(min_length=1, max_length=250)
    external_id: str = Field(min_length=1, max_length=100)
    estimated_size_gb: float = Field(gt=0, le=500)


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def load_options() -> dict:
    if not OPTIONS_FILE.exists():
        return {
            "storage": {
                "media_path": "/media",
                "minimum_free_gb": 50,
                "safety_margin_gb": 10,
                "reservation_multiplier": 1.5,
            },
            "approvals": {"auto_approve": True},
        }
    return json.loads(OPTIONS_FILE.read_text(encoding="utf-8"))


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
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MediaHub</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #111827; color: #f9fafb; }
    main { max-width: 980px; margin: 0 auto; padding: 32px 20px; }
    h1 { margin: 0 0 8px; font-size: 2rem; }
    p { color: #cbd5e1; line-height: 1.55; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 24px; }
    .card { background: #1f2937; border: 1px solid #374151; border-radius: 14px; padding: 18px; }
    .label { color: #94a3b8; font-size: .8rem; text-transform: uppercase; letter-spacing: .08em; }
    .value { margin-top: 8px; font-size: 1.15rem; font-weight: 700; }
    .ok { color: #4ade80; }
    .muted { color: #94a3b8; }
    code { background: #0f172a; border-radius: 6px; padding: 2px 6px; }
  </style>
</head>
<body>
  <main>
    <h1>MediaHub</h1>
    <p>The MediaHub backend is running through Home Assistant Ingress. This is the initial foundation interface. Search, discovery, integrations and request management are being added next.</p>
    <div class="grid">
      <section class="card">
        <div class="label">Service status</div>
        <div class="value ok" id="service-status">Checking...</div>
      </section>
      <section class="card">
        <div class="label">Version</div>
        <div class="value" id="version">0.1.1-dev</div>
      </section>
      <section class="card">
        <div class="label">Storage</div>
        <div class="value" id="storage">Checking...</div>
      </section>
    </div>
    <p class="muted">API endpoints are available relative to this page, including <code>api/health</code>, <code>api/storage</code>, <code>api/requests</code> and <code>api/audit</code>.</p>
  </main>
  <script>
    async function loadStatus() {
      try {
        const health = await fetch('api/health').then(r => r.json());
        document.getElementById('service-status').textContent = health.status === 'ok' ? 'Running' : 'Unavailable';
        document.getElementById('version').textContent = health.version;
      } catch (error) {
        document.getElementById('service-status').textContent = 'Unavailable';
      }

      try {
        const storage = await fetch('api/storage').then(async r => {
          const body = await r.json();
          if (!r.ok) throw new Error(body.detail || 'Storage unavailable');
          return body;
        });
        document.getElementById('storage').textContent = `${storage.free_gb} GB free`;
      } catch (error) {
        document.getElementById('storage').textContent = 'Not configured';
      }
    }
    loadStatus();
  </script>
</body>
</html>
"""


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "MediaHub", "version": app.version}


@app.get("/api/storage")
def get_storage() -> dict:
    with connect_db() as db:
        return storage_snapshot(db, 0.001)


@app.post("/api/requests")
def create_request(
    payload: MediaRequest,
    x_ingress_user_id: str | None = Header(default=None),
    x_ingress_user_name: str | None = Header(default=None),
) -> dict:
    actor_id = x_ingress_user_id or "local-development-user"
    actor_name = x_ingress_user_name or "Local Development User"
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
                actor_id,
                actor_name,
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
            actor_id=actor_id,
            actor_name=actor_name,
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
def list_requests() -> list[dict]:
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM requests ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [dict(row) for row in rows]


@app.get("/api/audit")
def list_audit_events() -> list[dict]:
    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM audit_events ORDER BY occurred_at DESC, id DESC LIMIT 500"
        ).fetchall()
        return [dict(row) for row in rows]
