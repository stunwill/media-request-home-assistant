from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal


Role = Literal["admin", "manager", "requester"]
AuthSource = Literal["home_assistant", "mediahub"]
ROLES: tuple[Role, ...] = ("admin", "manager", "requester")
SESSION_LIFETIME = timedelta(days=7)
LOGIN_WINDOW = timedelta(minutes=15)
LOGIN_FAILURE_LIMIT = 5
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1


class AuthenticationRequiredError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class LoginRateLimitedError(ValueError):
    pass


class LastAdministratorError(ValueError):
    pass


class UsernameUnavailableError(ValueError):
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
    auth_source: AuthSource = "home_assistant"

    def public_dict(self) -> dict[str, str | bool]:
        return {
            "id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "active": self.active,
            "auth_source": self.auth_source,
        }


@dataclass(frozen=True)
class Session:
    principal: Principal
    csrf_token: str
    session_hash: str


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


def normalise_username(value: str) -> str:
    return " ".join(value.replace("\x00", "").strip().lower().split())


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters")
    if len(password) > 1024:
        raise ValueError("Password must contain 1024 characters or fewer")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(expected)),
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (TypeError, ValueError):
        return False


DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(24))


def create_local_user(
    db: sqlite3.Connection,
    *,
    username: str,
    display_name: str,
    role: Role,
    password: str,
    now: str,
) -> Principal:
    normalized = normalise_username(username)
    clean_username = " ".join(username.replace("\x00", "").split()).strip()
    clean_display_name = " ".join(display_name.replace("\x00", "").split()).strip()
    if len(normalized) < 3 or len(clean_username) > 100:
        raise ValueError("Username must contain 3 to 100 characters")
    if not clean_display_name or len(clean_display_name) > 250:
        raise ValueError("Display name must contain 1 to 250 characters")
    if role not in ROLES:
        raise ValueError("Unsupported MediaHub role")
    password_hash = hash_password(password)

    db.execute("BEGIN IMMEDIATE")
    collision = db.execute(
        "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE LIMIT 1",
        (clean_username,),
    ).fetchone()
    if collision:
        raise UsernameUnavailableError("That username is already in use")

    user_id = f"local:{secrets.token_hex(16)}"
    db.execute(
        """
        INSERT INTO users (
            id, username, display_name, role, active, created_at, updated_at,
            last_seen_at
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (user_id, clean_username, clean_display_name, role, now, now, now),
    )
    db.execute(
        """
        INSERT INTO local_credentials (
            user_id, username_normalized, password_hash, password_changed_at
        ) VALUES (?, ?, ?, ?)
        """,
        (user_id, normalized, password_hash, now),
    )
    row = db.execute(
        "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    return _principal_from_row(row, auth_source="mediahub")


def authenticate_local_user(
    db: sqlite3.Connection,
    *,
    username: str,
    password: str,
    remote_address: str,
    now: datetime,
) -> Principal:
    normalized = normalise_username(username)
    failure_key = _failure_key(normalized, remote_address)
    cutoff = (now - LOGIN_WINDOW).isoformat()
    db.execute("DELETE FROM login_failures WHERE attempted_at < ?", (cutoff,))
    failures = int(
        db.execute(
            "SELECT COUNT(*) FROM login_failures WHERE failure_key = ?",
            (failure_key,),
        ).fetchone()[0]
    )
    if failures >= LOGIN_FAILURE_LIMIT:
        raise LoginRateLimitedError("Too many failed attempts. Try again in 15 minutes.")

    row = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.role, u.active,
               c.password_hash
        FROM local_credentials c
        JOIN users u ON u.id = c.user_id
        WHERE c.username_normalized = ?
        """,
        (normalized,),
    ).fetchone()
    password_hash = str(row["password_hash"]) if row else DUMMY_PASSWORD_HASH
    valid = verify_password(password, password_hash) and bool(row)
    if not valid or not bool(row["active"]):
        db.execute(
            "INSERT INTO login_failures (failure_key, attempted_at) VALUES (?, ?)",
            (failure_key, now.isoformat()),
        )
        raise InvalidCredentialsError("Incorrect username or password")

    db.execute("DELETE FROM login_failures WHERE failure_key = ?", (failure_key,))
    db.execute(
        "UPDATE users SET last_seen_at = ?, updated_at = ? WHERE id = ?",
        (now.isoformat(), now.isoformat(), row["id"]),
    )
    return _principal_from_row(row, auth_source="mediahub")


def create_session(
    db: sqlite3.Connection,
    *,
    principal: Principal,
    now: datetime,
) -> tuple[str, Session]:
    raw_token = secrets.token_urlsafe(32)
    session_hash = _token_hash(raw_token)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = (now + SESSION_LIFETIME).isoformat()
    db.execute(
        """
        INSERT INTO sessions (
            token_hash, user_id, csrf_token, created_at, expires_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session_hash,
            principal.user_id,
            csrf_token,
            now.isoformat(),
            expires_at,
            now.isoformat(),
        ),
    )
    return raw_token, Session(principal, csrf_token, session_hash)


def session_from_token(
    db: sqlite3.Connection,
    *,
    raw_token: str,
    now: datetime,
) -> Session | None:
    if not raw_token or len(raw_token) > 200:
        return None
    token_hash = _token_hash(raw_token)
    db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
    row = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.role, u.active,
               s.csrf_token, s.token_hash
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        JOIN local_credentials c ON c.user_id = u.id
        WHERE s.token_hash = ? AND s.expires_at > ?
        """,
        (token_hash, now.isoformat()),
    ).fetchone()
    if row is None or not bool(row["active"]):
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        return None
    db.execute(
        "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
        (now.isoformat(), token_hash),
    )
    return Session(
        _principal_from_row(row, auth_source="mediahub"),
        str(row["csrf_token"]),
        str(row["token_hash"]),
    )


def revoke_session(db: sqlite3.Connection, *, session_hash: str) -> None:
    db.execute("DELETE FROM sessions WHERE token_hash = ?", (session_hash,))


def reset_local_password(
    db: sqlite3.Connection,
    *,
    user_id: str,
    password: str,
    now: str,
) -> bool:
    password_hash = hash_password(password)
    cursor = db.execute(
        """
        UPDATE local_credentials
        SET password_hash = ?, password_changed_at = ?
        WHERE user_id = ?
        """,
        (password_hash, now, user_id),
    )
    if not cursor.rowcount:
        return False
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    db.execute("UPDATE users SET updated_at = ? WHERE id = ?", (now, user_id))
    return True


def list_users(db: sqlite3.Connection) -> list[dict[str, str | bool]]:
    rows = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.role, u.active, u.created_at,
               u.updated_at, u.last_seen_at,
               CASE WHEN c.user_id IS NULL THEN 'home_assistant' ELSE 'mediahub' END
                   AS auth_source
        FROM users u
        LEFT JOIN local_credentials c ON c.user_id = u.id
        ORDER BY u.display_name COLLATE NOCASE, u.id
        """
    ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "username": str(row["username"]),
            "display_name": str(row["display_name"]),
            "role": str(row["role"]),
            "active": bool(row["active"]),
            "auth_source": str(row["auth_source"]),
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

    _protect_last_administrator(db, row=row, next_role=role, next_active=bool(row["active"]))
    db.execute(
        "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
        (role, now, user_id),
    )
    refreshed = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.role, u.active,
               CASE WHEN c.user_id IS NULL THEN 'home_assistant' ELSE 'mediahub' END
                   AS auth_source
        FROM users u LEFT JOIN local_credentials c ON c.user_id = u.id
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    return _principal_from_row(
        refreshed,
        auth_source=str(refreshed["auth_source"]),
    )


def update_user_active(
    db: sqlite3.Connection,
    *,
    user_id: str,
    active: bool,
    now: str,
) -> Principal | None:
    db.execute("BEGIN IMMEDIATE")
    row = db.execute(
        "SELECT id, username, display_name, role, active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    _protect_last_administrator(db, row=row, next_role=str(row["role"]), next_active=active)
    db.execute(
        "UPDATE users SET active = ?, updated_at = ? WHERE id = ?",
        (int(active), now, user_id),
    )
    if not active:
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    refreshed = db.execute(
        """
        SELECT u.id, u.username, u.display_name, u.role, u.active,
               CASE WHEN c.user_id IS NULL THEN 'home_assistant' ELSE 'mediahub' END
                   AS auth_source
        FROM users u LEFT JOIN local_credentials c ON c.user_id = u.id
        WHERE u.id = ?
        """,
        (user_id,),
    ).fetchone()
    return _principal_from_row(
        refreshed,
        auth_source=str(refreshed["auth_source"]),
    )


def _protect_last_administrator(
    db: sqlite3.Connection,
    *,
    row: sqlite3.Row,
    next_role: str,
    next_active: bool,
) -> None:
    removes_active_admin = (
        str(row["role"]) == "admin"
        and bool(row["active"])
        and (next_role != "admin" or not next_active)
    )
    if not removes_active_admin:
        return
    active_admins = int(
        db.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1"
        ).fetchone()[0]
    )
    if active_admins <= 1:
        raise LastAdministratorError("MediaHub must retain at least one active administrator")


def _failure_key(username: str, remote_address: str) -> str:
    return hashlib.sha256(f"{username}\x00{remote_address}".encode("utf-8")).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_header(value: str | None, *, maximum: int) -> str:
    if value is None:
        return ""
    cleaned = " ".join(value.replace("\x00", "").split()).strip()
    return cleaned[:maximum]


def _principal_from_row(
    row: sqlite3.Row,
    *,
    auth_source: AuthSource | str = "home_assistant",
) -> Principal:
    role = str(row["role"])
    if role not in ROLES:
        raise ValueError(f"Unsupported user role: {role}")
    if auth_source not in {"home_assistant", "mediahub"}:
        raise ValueError(f"Unsupported authentication source: {auth_source}")
    return Principal(
        user_id=str(row["id"]),
        username=str(row["username"]),
        display_name=str(row["display_name"]),
        role=role,
        active=bool(row["active"]),
        auth_source=auth_source,
    )
