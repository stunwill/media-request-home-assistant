from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mediahub.app import main


def ingress_headers(
    user_id: str,
    username: str,
    display_name: str,
) -> dict[str, str]:
    return {
        "X-Remote-User-Id": user_id,
        "X-Remote-User-Name": username,
        "X-Remote-User-Display-Name": display_name,
    }


class AuthenticationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        app_data = Path(self.temporary_directory.name)
        database_file = app_data / "mediahub.db"
        self.app_data_patch = patch.object(main, "APP_DATA", app_data)
        self.database_patch = patch.object(main, "DATABASE_FILE", database_file)
        self.app_data_patch.start()
        self.database_patch.start()
        main.initialise_database()
        self.client = TestClient(main.app)
        self.admin_headers = ingress_headers("ha-admin", "stu", "Stu")
        self.requester_headers = ingress_headers("ha-requester", "lee", "Lee")

    def tearDown(self) -> None:
        self.client.close()
        self.database_patch.stop()
        self.app_data_patch.stop()
        self.temporary_directory.cleanup()

    def test_ingress_identity_is_required(self) -> None:
        response = self.client.get("/api/users/me")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Home Assistant Ingress authentication is required",
        )

    def test_first_user_is_bootstrap_admin_and_later_users_are_requesters(self) -> None:
        admin = self.client.get("/api/users/me", headers=self.admin_headers)
        requester = self.client.get("/api/users/me", headers=self.requester_headers)

        self.assertEqual(admin.status_code, 200)
        self.assertEqual(admin.json()["role"], "admin")
        self.assertEqual(requester.status_code, 200)
        self.assertEqual(requester.json()["role"], "requester")

        forbidden = self.client.get("/api/setup", headers=self.requester_headers)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["detail"], "Administrator access is required")

    def test_admin_can_assign_roles_but_cannot_remove_last_admin(self) -> None:
        self.client.get("/api/users/me", headers=self.admin_headers)
        self.client.get("/api/users/me", headers=self.requester_headers)

        promoted = self.client.put(
            "/api/users/ha-requester/role",
            headers=self.admin_headers,
            json={"role": "manager"},
        )
        self.assertEqual(promoted.status_code, 200)
        self.assertEqual(promoted.json()["role"], "manager")

        demoted = self.client.put(
            "/api/users/ha-admin/role",
            headers=self.admin_headers,
            json={"role": "requester"},
        )
        self.assertEqual(demoted.status_code, 409)
        self.assertEqual(
            demoted.json()["detail"],
            "MediaHub must retain at least one active administrator",
        )

    def test_requesters_see_only_their_requests(self) -> None:
        self.client.get("/api/users/me", headers=self.admin_headers)
        self.client.get("/api/users/me", headers=self.requester_headers)
        now = main.utc_now()
        with main.connect_db() as db:
            for external_id, user_id, user_name in (
                ("movie-1", "ha-admin", "Stu"),
                ("movie-2", "ha-requester", "Lee"),
            ):
                db.execute(
                    """
                    INSERT INTO requests (
                        media_type, title, external_id, requested_by_id,
                        requested_by_name, estimated_size_gb, reserved_size_gb,
                        status, rejection_reason, created_at, updated_at
                    ) VALUES ('movie', ?, ?, ?, ?, 1, 0, 'available', NULL, ?, ?)
                    """,
                    (external_id, external_id, user_id, user_name, now, now),
                )
            db.commit()

        requester_response = self.client.get(
            "/api/requests",
            headers=self.requester_headers,
        )
        admin_response = self.client.get("/api/requests", headers=self.admin_headers)

        self.assertEqual(requester_response.status_code, 200)
        self.assertEqual(
            [item["requested_by_id"] for item in requester_response.json()],
            ["ha-requester"],
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(len(admin_response.json()), 2)

    def test_identity_changes_are_synchronised_without_changing_role(self) -> None:
        first = self.client.get("/api/users/me", headers=self.admin_headers)
        renamed_headers = ingress_headers("ha-admin", "stuart", "Stuart")
        renamed = self.client.get("/api/users/me", headers=renamed_headers)

        self.assertEqual(first.json()["role"], "admin")
        self.assertEqual(renamed.json()["username"], "stuart")
        self.assertEqual(renamed.json()["display_name"], "Stuart")
        self.assertEqual(renamed.json()["role"], "admin")

    def create_local_account(
        self,
        *,
        username: str = "lee",
        display_name: str = "Lee",
        password: str = "correct horse battery staple",
        role: str = "requester",
    ) -> dict:
        self.client.get("/api/users/me", headers=self.admin_headers)
        response = self.client.post(
            "/api/users",
            headers=self.admin_headers,
            json={
                "username": username,
                "display_name": display_name,
                "password": password,
                "role": role,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_external_listener_ignores_spoofed_ingress_headers(self) -> None:
        with patch.dict(os.environ, {"MEDIAHUB_AUTH_MODE": "external"}):
            response = self.client.get("/api/users/me", headers=self.admin_headers)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Sign in to MediaHub to continue")

    def test_local_login_uses_session_cookie_and_csrf_protection(self) -> None:
        self.create_local_account()
        with patch.dict(os.environ, {"MEDIAHUB_AUTH_MODE": "external"}):
            login = self.client.post(
                "/api/auth/login",
                json={
                    "username": "LEE",
                    "password": "correct horse battery staple",
                },
            )
            me = self.client.get("/api/users/me")
            missing_csrf = self.client.post("/api/auth/logout")
            logout = self.client.post(
                "/api/auth/logout",
                headers={"X-CSRF-Token": login.json()["csrf_token"]},
            )
            signed_out = self.client.get("/api/users/me")

        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["auth_source"], "mediahub")
        self.assertIn("mediahub_session", login.headers.get("set-cookie", ""))
        self.assertIn("HttpOnly", login.headers.get("set-cookie", ""))
        self.assertEqual(login.headers["x-content-type-options"], "nosniff")
        self.assertEqual(login.headers["cache-control"], "no-store")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(missing_csrf.status_code, 403)
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(signed_out.status_code, 401)

    def test_password_is_hashed_and_reset_revokes_sessions(self) -> None:
        created = self.create_local_account()
        with main.connect_db() as db:
            stored = db.execute(
                "SELECT password_hash FROM local_credentials WHERE user_id = ?",
                (created["id"],),
            ).fetchone()[0]
        self.assertTrue(str(stored).startswith("scrypt$"))
        self.assertNotIn("correct horse", str(stored))

        external_client = TestClient(main.app)
        try:
            with patch.dict(os.environ, {"MEDIAHUB_AUTH_MODE": "external"}):
                login = external_client.post(
                    "/api/auth/login",
                    json={
                        "username": "lee",
                        "password": "correct horse battery staple",
                    },
                )
                self.assertEqual(login.status_code, 200)
            reset = self.client.put(
                f"/api/users/{created['id']}/password",
                headers=self.admin_headers,
                json={"password": "a newer and longer private password"},
            )
            with patch.dict(os.environ, {"MEDIAHUB_AUTH_MODE": "external"}):
                expired = external_client.get("/api/users/me")
                old_login = external_client.post(
                    "/api/auth/login",
                    json={
                        "username": "lee",
                        "password": "correct horse battery staple",
                    },
                )
                new_login = external_client.post(
                    "/api/auth/login",
                    json={
                        "username": "lee",
                        "password": "a newer and longer private password",
                    },
                )
        finally:
            external_client.close()

        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(old_login.status_code, 401)
        self.assertEqual(new_login.status_code, 200)

    def test_failed_logins_are_rate_limited(self) -> None:
        self.create_local_account()
        with patch.dict(os.environ, {"MEDIAHUB_AUTH_MODE": "external"}):
            attempts = [
                self.client.post(
                    "/api/auth/login",
                    json={"username": "lee", "password": "wrong password"},
                )
                for _ in range(6)
            ]

        self.assertTrue(all(item.status_code == 401 for item in attempts[:5]))
        self.assertEqual(attempts[5].status_code, 429)

    def test_last_active_administrator_cannot_be_disabled(self) -> None:
        local_admin = self.create_local_account(
            username="external-admin",
            display_name="External Admin",
            role="admin",
        )
        external_client = TestClient(main.app)
        try:
            with patch.dict(os.environ, {"MEDIAHUB_AUTH_MODE": "external"}):
                login = external_client.post(
                    "/api/auth/login",
                    json={
                        "username": "external-admin",
                        "password": "correct horse battery staple",
                    },
                )
                csrf = login.json()["csrf_token"]
                disabled_ingress_admin = external_client.put(
                    "/api/users/ha-admin/active",
                    headers={"X-CSRF-Token": csrf},
                    json={"active": False},
                )
                disabled_last_admin = external_client.put(
                    f"/api/users/{local_admin['id']}/active",
                    headers={"X-CSRF-Token": csrf},
                    json={"active": False},
                )
        finally:
            external_client.close()

        self.assertEqual(disabled_ingress_admin.status_code, 200)
        self.assertEqual(disabled_last_admin.status_code, 409)
        self.assertEqual(
            disabled_last_admin.json()["detail"],
            "MediaHub must retain at least one active administrator",
        )


if __name__ == "__main__":
    unittest.main()
