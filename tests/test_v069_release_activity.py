from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from mediahub.app import main, release_activity


def ingress_headers(user_id: str, username: str, display_name: str) -> dict[str, str]:
    return {
        "X-Remote-User-Id": user_id,
        "X-Remote-User-Name": username,
        "X-Remote-User-Display-Name": display_name,
    }


class ReleaseSortingTests(unittest.TestCase):
    def test_downloadable_releases_are_always_before_rejected_releases(self) -> None:
        rejected = {
            "title": "Rejected 1080p",
            "quality": "1080p",
            "eligible": False,
            "seeders": 500,
            "size_gb": 1.0,
            "age_hours": 1,
            "policy_rejections": ["Rejected by policy"],
        }
        eligible_720 = {
            "title": "Good 720p",
            "quality": "720p",
            "eligible": True,
            "seeders": 5,
            "size_gb": 1.5,
            "age_hours": 4,
            "policy_rejections": [],
        }
        eligible_1080 = {
            "title": "Best 1080p",
            "quality": "1080p",
            "eligible": True,
            "seeders": 2,
            "size_gb": 2.0,
            "age_hours": 8,
            "policy_rejections": [],
        }

        ordered = release_activity.sort_release_results(
            [rejected, eligible_720, eligible_1080]
        )

        self.assertEqual(
            [item["title"] for item in ordered],
            ["Best 1080p", "Good 720p", "Rejected 1080p"],
        )
        self.assertEqual(ordered[-1]["policy_rejections"], ["Rejected by policy"])

    def test_eligible_results_keep_sensible_health_order_within_quality(self) -> None:
        releases = [
            {
                "title": "1080p low seeders",
                "quality": "1080p",
                "eligible": True,
                "seeders": 2,
                "size_gb": 2.0,
                "age_hours": 4,
                "policy_rejections": [],
            },
            {
                "title": "1080p high seeders",
                "quality": "1080p",
                "eligible": True,
                "seeders": 20,
                "size_gb": 2.5,
                "age_hours": 5,
                "policy_rejections": [],
            },
        ]

        ordered = release_activity.sort_release_results(releases)
        self.assertEqual(ordered[0]["title"], "1080p high seeders")


class UserActivityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        app_data = Path(self.temporary_directory.name)
        database_file = app_data / "mediahub.db"
        self.app_data_patch = patch.object(main, "APP_DATA", app_data)
        self.database_patch = patch.object(main, "DATABASE_FILE", database_file)
        self.app_data_patch.start()
        self.database_patch.start()
        main.initialise_database()
        self.client = TestClient(release_activity.app)
        self.admin_headers = ingress_headers("ha-admin", "stu", "Stu")
        self.requester_headers = ingress_headers("ha-requester", "lee", "Lee")
        self.manager_headers = ingress_headers("ha-manager", "manager", "Manager")

        self.client.get("/api/users/me", headers=self.admin_headers)
        self.client.get("/api/users/me", headers=self.requester_headers)
        self.client.get("/api/users/me", headers=self.manager_headers)
        promoted = self.client.put(
            "/api/users/ha-manager/role",
            headers=self.admin_headers,
            json={"role": "manager"},
        )
        self.assertEqual(promoted.status_code, 200, promoted.text)

    def tearDown(self) -> None:
        self.client.close()
        self.database_patch.stop()
        self.app_data_patch.stop()
        self.temporary_directory.cleanup()

    def _insert_activity(self) -> int:
        with main.connect_db() as db:
            cursor = db.execute(
                """
                INSERT INTO requests (
                    media_type, title, external_id, requested_by_id, requested_by_name,
                    estimated_size_gb, reserved_size_gb, status, rejection_reason,
                    progress, status_message, created_at, updated_at
                ) VALUES (
                    'movie', 'Resident Evil', '123', 'ha-requester', 'Lee',
                    2.1, 0, 'available', NULL, 100, 'Available in the media library',
                    '2026-08-23T22:00:00+00:00', '2026-08-24T00:42:00+00:00'
                )
                """
            )
            request_id = int(cursor.lastrowid)
            db.execute(
                """
                INSERT INTO audit_events (
                    occurred_at, actor_id, actor_name, action, request_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-08-23T22:00:00+00:00",
                    "ha-requester",
                    "Lee",
                    "movie_request_created",
                    request_id,
                    '{"title":"Resident Evil"}',
                ),
            )
            db.execute(
                """
                INSERT INTO audit_events (
                    occurred_at, actor_id, actor_name, action, request_id, details_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-08-24T00:42:00+00:00",
                    "system",
                    "MediaHub",
                    "movie_available",
                    request_id,
                    '{"source":"radarr_library","secret":"do-not-return"}',
                ),
            )
            db.commit()
        return request_id

    def test_admin_can_view_user_activity_newest_first_without_sensitive_fields(self) -> None:
        self._insert_activity()

        response = self.client.get(
            "/api/users/ha-requester/activity",
            headers=self.admin_headers,
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["user"]["display_name"], "Lee")
        self.assertEqual(
            [item["action"] for item in payload["activity"][:2]],
            ["available", "requested"],
        )
        self.assertEqual(payload["activity"][0]["title"], "Resident Evil")
        self.assertEqual(payload["activity"][0]["media_type"], "movie")
        self.assertEqual(payload["activity"][0]["occurred_at"], "2026-08-24T00:42:00+00:00")
        for item in payload["activity"]:
            self.assertNotIn("details_json", item)
            self.assertNotIn("download_id", item)
            self.assertNotIn("selected_release_guid", item)
            self.assertNotIn("secret", item)

    def test_requester_and_manager_cannot_view_other_user_activity(self) -> None:
        self._insert_activity()

        requester = self.client.get(
            "/api/users/ha-requester/activity",
            headers=self.requester_headers,
        )
        manager = self.client.get(
            "/api/users/ha-requester/activity",
            headers=self.manager_headers,
        )

        self.assertEqual(requester.status_code, 403)
        self.assertEqual(manager.status_code, 403)
        self.assertEqual(requester.json()["detail"], "Administrator access is required")
        self.assertEqual(manager.json()["detail"], "Administrator access is required")

    def test_unknown_user_returns_not_found(self) -> None:
        response = self.client.get(
            "/api/users/not-a-user/activity",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "MediaHub user not found")

    def test_transition_audit_is_recorded_only_once(self) -> None:
        request_id = self._insert_activity()
        with main.connect_db() as db:
            release_activity._record_transition_once(
                db,
                request_id=request_id,
                action="movie_download_started",
                previous_status="queued",
                status="downloading",
            )
            release_activity._record_transition_once(
                db,
                request_id=request_id,
                action="movie_download_started",
                previous_status="queued",
                status="downloading",
            )
            db.commit()
            count = db.execute(
                """
                SELECT COUNT(*) AS count
                FROM audit_events
                WHERE request_id = ? AND action = 'movie_download_started'
                """,
                (request_id,),
            ).fetchone()["count"]
        self.assertEqual(count, 1)

    def test_users_page_contains_activity_ui_and_release_grouping(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("View activity", response.text)
        self.assertIn('id="activity-modal"', response.text)
        self.assertIn("Other unavailable releases", response.text)
        self.assertIn("formatActivityTime", response.text)


if __name__ == "__main__":
    unittest.main()
