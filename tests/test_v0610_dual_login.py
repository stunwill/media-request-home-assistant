from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mediahub.app import auth, dual_login, main


def ingress_headers(user_id: str, username: str, display_name: str) -> dict[str, str]:
    return {
        "X-Remote-User-Id": user_id,
        "X-Remote-User-Name": username,
        "X-Remote-User-Display-Name": display_name,
    }


def test_home_assistant_user_can_be_given_mediahub_login_without_duplicate_account():
    with tempfile.TemporaryDirectory() as directory:
        app_data = Path(directory)
        database_file = app_data / "mediahub.db"
        with patch.object(main, "APP_DATA", app_data), patch.object(main, "DATABASE_FILE", database_file):
            main.initialise_database()
            client = TestClient(dual_login.app)
            headers = ingress_headers("ha-stu", "stunwill", "Stuart")
            assert client.get("/api/users/me", headers=headers).status_code == 200

            response = client.put(
                "/api/users/ha-stu/mediahub-login",
                headers=headers,
                json={"username": "stunwill", "password": "correct horse battery staple"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["mediahub_login_enabled"] is True
            assert response.json()["auth_source"] == "home_assistant_and_mediahub"

            with main.connect_db() as db:
                assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
                assert db.execute("SELECT COUNT(*) FROM local_credentials").fetchone()[0] == 1
                principal = auth.authenticate_local_user(
                    db,
                    username="stunwill",
                    password="correct horse battery staple",
                    remote_address="127.0.0.1",
                    now=datetime.now(UTC),
                )
                assert principal.user_id == "ha-stu"
                assert principal.role == "admin"
            client.close()


def test_password_reset_reuses_existing_credential_and_revokes_sessions():
    with tempfile.TemporaryDirectory() as directory:
        app_data = Path(directory)
        database_file = app_data / "mediahub.db"
        with patch.object(main, "APP_DATA", app_data), patch.object(main, "DATABASE_FILE", database_file):
            main.initialise_database()
            client = TestClient(dual_login.app)
            headers = ingress_headers("ha-stu", "stunwill", "Stuart")
            client.get("/api/users/me", headers=headers)
            first = client.put(
                "/api/users/ha-stu/mediahub-login",
                headers=headers,
                json={"username": "stunwill", "password": "first password value"},
            )
            assert first.status_code == 200

            with main.connect_db() as db:
                principal = auth.authenticate_local_user(
                    db,
                    username="stunwill",
                    password="first password value",
                    remote_address="127.0.0.1",
                    now=datetime.now(UTC),
                )
                raw_token, _ = auth.create_session(db, principal=principal, now=datetime.now(UTC))
                db.commit()
                assert raw_token
                assert db.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'ha-stu'").fetchone()[0] == 1

            reset = client.put(
                "/api/users/ha-stu/mediahub-login",
                headers=headers,
                json={"username": "stunwill", "password": "second password value"},
            )
            assert reset.status_code == 200
            with main.connect_db() as db:
                assert db.execute("SELECT COUNT(*) FROM local_credentials WHERE user_id = 'ha-stu'").fetchone()[0] == 1
                assert db.execute("SELECT COUNT(*) FROM sessions WHERE user_id = 'ha-stu'").fetchone()[0] == 0
                principal = auth.authenticate_local_user(
                    db,
                    username="stunwill",
                    password="second password value",
                    remote_address="127.0.0.1",
                    now=datetime.now(UTC),
                )
                assert principal.user_id == "ha-stu"
            client.close()


def test_non_admin_cannot_enable_mediahub_login_for_another_user():
    with tempfile.TemporaryDirectory() as directory:
        app_data = Path(directory)
        database_file = app_data / "mediahub.db"
        with patch.object(main, "APP_DATA", app_data), patch.object(main, "DATABASE_FILE", database_file):
            main.initialise_database()
            client = TestClient(dual_login.app)
            admin_headers = ingress_headers("ha-admin", "admin", "Admin")
            requester_headers = ingress_headers("ha-user", "lee", "Lee")
            client.get("/api/users/me", headers=admin_headers)
            client.get("/api/users/me", headers=requester_headers)

            response = client.put(
                "/api/users/ha-user/mediahub-login",
                headers=requester_headers,
                json={"username": "lee", "password": "correct horse battery staple"},
            )
            assert response.status_code == 403
            with main.connect_db() as db:
                assert db.execute("SELECT COUNT(*) FROM local_credentials WHERE user_id = 'ha-user'").fetchone()[0] == 0
            client.close()


def test_login_username_collision_is_rejected():
    with tempfile.TemporaryDirectory() as directory:
        app_data = Path(directory)
        database_file = app_data / "mediahub.db"
        with patch.object(main, "APP_DATA", app_data), patch.object(main, "DATABASE_FILE", database_file):
            main.initialise_database()
            client = TestClient(dual_login.app)
            admin_headers = ingress_headers("ha-admin", "admin", "Admin")
            other_headers = ingress_headers("ha-other", "other", "Other")
            client.get("/api/users/me", headers=admin_headers)
            client.get("/api/users/me", headers=other_headers)
            assert client.put(
                "/api/users/ha-admin/mediahub-login",
                headers=admin_headers,
                json={"username": "shared-login", "password": "correct horse battery staple"},
            ).status_code == 200

            response = client.put(
                "/api/users/ha-other/mediahub-login",
                headers=admin_headers,
                json={"username": "shared-login", "password": "another secure password"},
            )
            assert response.status_code == 409
            client.close()


def test_users_api_and_page_expose_dual_login_controls_without_secrets():
    with tempfile.TemporaryDirectory() as directory:
        app_data = Path(directory)
        database_file = app_data / "mediahub.db"
        with patch.object(main, "APP_DATA", app_data), patch.object(main, "DATABASE_FILE", database_file):
            main.initialise_database()
            client = TestClient(dual_login.app)
            headers = ingress_headers("ha-stu", "stunwill", "Stuart")
            client.get("/api/users/me", headers=headers)
            enabled = client.put(
                "/api/users/ha-stu/mediahub-login",
                headers=headers,
                json={"username": "stunwill", "password": "correct horse battery staple"},
            )
            assert enabled.status_code == 200

            users = client.get("/api/users", headers=headers)
            assert users.status_code == 200
            payload = users.json()[0]
            assert payload["auth_source"] == "home_assistant_and_mediahub"
            assert payload["mediahub_login_enabled"] is True
            assert "password" not in payload
            assert "password_hash" not in payload

            page = client.get("/")
            assert page.status_code == 200
            assert "Enable MediaHub login" in page.text
            assert "Reset MediaHub password" in page.text
            assert "credential-modal" in page.text
            client.close()
