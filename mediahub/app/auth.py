from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal


Role = Literal["admin", "manager", "requester"]
ROLES: tuple[Role, ...] = ("admin", "manager", "requester")


class AuthenticationRequiredError(ValueError):
    pass


class LastAdministratorError(ValueError):
    pass


@dataclass(frozen=True)
class IngressIdentity:
    user_id: str
    username: str
    display_name: str


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    display_name: str
    role: Role
    active: bool

    def public_dict(self) -> dict[str, str | bool]:
        return {
            "id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "active": self.active,
        }


def ingress_identity(
    *,
    user_id: str | None,
    username: str | None,
    display_name: str | None,
) -> IngressIdentity:
    normalized_id = _clean_header(user_id, maximum=128)
    if not normalized_id:
        raise AuthenticationRequiredError("Home Assistant Ingress authentication is required")

    normalized_username = _clean_header(username, maximum=250) or normalized_id
    normalized_display_name = (
        _clean_header(display_name, maximum=250) or normalized_username
    )
    return IngressIdentity(
        user_id=normalized_id,
        username=normalized_username,
        display_name=normalized_display_name,
    )


def sync_user(
    db: sqlite3.Connection,
    *,
    identity: IngressIdentity,
    now: str,
) -> tuple[Principal, bool]:
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
        (identity.user_id,),
    ).fetchone()
    created = row is None

    if created:
        user_count = int(db.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        role: Role = "admin" if user_count == 0 else "requester"
        db.execute(
            """
            INSERT INTO users (
                id, username, display_name, role, active, created_at, updated_at,
                last_seen_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                identity.user_id,
                identity.username,
                identity.display_name,
                role,
                now,
                now,
                now,
            ),
        )
    else:
        db.execute(
            """
            UPDATE users
            SET username = ?, display_name = ?, updated_at = ?, last_seen_at = ?
            WHERE id = ?
            """,
            (
                identity.username,
                identity.display_name,
                now,
                now,
                identity.user_id,
            ),
        )

    refreshed = db.execute(
        "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
        (identity.user_id,),
    ).fetchone()
    return _principal_from_row(refreshed), created


def list_users(db: sqlite3.Connection) -> list[dict[str, str | bool]]:
    rows = db.execute(
        """
        SELECT id, username, display_name, role, active, created_at, updated_at,
               last_seen_at
        FROM users
        ORDER BY display_name COLLATE NOCASE, id
        """
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "username": str(row["username"]),
            "display_name": str(row["display_name"]),
            "role": str(row["role"]),
            "active": bool(row["active"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "last_seen_at": str(row["last_seen_at"]),
        }
        for row in rows
    ]


def update_user_role(
    db: sqlite3.Connection,
    *,
    user_id: str,
    role: Role,
    now: str,
) -> Principal | None:
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None

    if row["role"] == "admin" and role != "admin":
        active_admins = int(
            db.execute(
                "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
            ).fetchone()[0]
        )
        if bool(row["active"]) and active_admins <= 1:
            raise LastAdministratorError("MediaHub must retain at least one active administrator")

    db.execute(
        "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
        (role, now, user_id),
    )
    refreshed = db.execute(
        "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return _principal_from_row(refreshed)


def _clean_header(value: str | None, *, maximum: int) -> str:
    if value is None:
        return ""
    cleaned = " ".join(value.replace("\x00", "").split()).strip()
    return cleaned[:maximum]


def _principal_from_row(row: sqlite3.Row) -> Principal:
    role = str(row["role"])
    if role not in ROLES:
        raise ValueError(f"Unsupported user role: {role}")
    return Principal(
        user_id=str(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=role,
        active=bool(row["active"]),
    )
