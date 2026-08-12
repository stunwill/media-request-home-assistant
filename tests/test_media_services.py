from __future__ import annotations

import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from mediahub.app import main
from mediahub.app.media_services import (
    MediaServiceError,
    QBittorrentClient,
    RadarrClient,
    TmdbClient,
    analyse_download_workflow,
)


def headers() -> dict[str, str]:
    return {
        "X-Remote-User-Id": "ha-admin",
        "X-Remote-User-Name": "stu",
        "X-Remote-User-Display-Name": "Stu",
    }


def release() -> dict:
    return {
        "guid": "private-indexer-guid",
        "indexer_id": 7,
        "indexer": "IPTorrents",
        "title": "Example.Movie.2026.1080p.WEB-DL",
        "quality": "WEBDL-1080p",
        "size_bytes": 2 * 1024**3,
        "size_gb": 2.0,
        "seeders": 18,
        "leechers": 2,
        "age_hours": 4.5,
        "publish_date": "2026-08-05T01:00:00Z",
        "approved": True,
        "download_allowed": True,
        "rejections": [],
        "flags": ["FreeLeech"],
        "info_hash": "ABC123",
    }


class TmdbClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalogue_normalises_movie_images(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/3/movie/popular")
            self.assertEqual(request.url.params["api_key"], "secret")
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 1,
                    "results": [
                        {
                            "id": 123,
                            "title": "Example Movie",
                            "release_date": "2026-08-05",
                            "vote_average": 7.55,
                            "poster_path": "/poster.jpg",
                        }
                    ],
                },
            )

        client = TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue()

        self.assertEqual(result["movies"][0]["tmdb_id"], 123)
        self.assertEqual(result["movies"][0]["rating"], 7.5)
        self.assertEqual(
            result["movies"][0]["poster_url"],
            "https://image.tmdb.org/t/p/w500/poster.jpg",
        )
        self.assertNotIn("secret", str(result))

    async def test_catalogue_uses_discover_for_genre_and_year_filters(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/3/discover/movie")
            self.assertEqual(request.url.params["with_genres"], "18")
            self.assertEqual(request.url.params["primary_release_date.gte"], "1990-01-01")
            self.assertEqual(request.url.params["primary_release_date.lte"], "1999-12-31")
            self.assertEqual(request.url.params["vote_average.gte"], "6.5")
            self.assertEqual(request.url.params["vote_average.lte"], "8.9")
            self.assertEqual(request.url.params["sort_by"], "popularity.desc")
            return httpx.Response(
                200,
                json={
                    "page": 2,
                    "total_pages": 7,
                    "total_results": 121,
                    "results": [
                        {
                            "id": 456,
                            "title": "Filtered Movie",
                            "release_date": "1995-03-10",
                            "genre_ids": [18],
                        }
                    ],
                },
            )

        client = TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(
            page=2,
            genre_id=18,
            year_from=1990,
            year_to=1999,
            rating_from=6.5,
            rating_to=8.9,
        )

        self.assertEqual(result["page"], 2)
        self.assertEqual(result["total_pages"], 7)
        self.assertEqual(result["movies"][0]["title"], "Filtered Movie")
        self.assertTrue(result["filters_applied"])

    async def test_catalogue_post_filters_search_results_by_rating(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/3/search/movie")
            self.assertNotIn("vote_average.gte", request.url.params)
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 2,
                    "results": [
                        {"id": 11, "title": "Included", "vote_average": 7.4},
                        {"id": 12, "title": "Excluded", "vote_average": 5.9},
                    ],
                },
            )

        client = TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(query="example", rating_from=7.0, rating_to=8.0)

        self.assertEqual([movie["title"] for movie in result["movies"]], ["Included"])
        self.assertTrue(result["post_filtered_search"])

    async def test_catalogue_rejects_reversed_rating_range(self) -> None:
        client = TmdbClient("secret")

        with self.assertRaises(MediaServiceError) as raised:
            await client.catalogue(rating_from=8.1, rating_to=7.9)

        self.assertEqual(raised.exception.status_code, 422)

    async def test_genres_are_normalised_and_sorted(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/3/genre/movie/list")
            return httpx.Response(
                200,
                json={"genres": [{"id": 35, "name": "Comedy"}, {"id": 28, "name": "Action"}]},
            )

        client = TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.genres()

        self.assertEqual(
            result,
            {"genres": [{"id": 28, "name": "Action"}, {"id": 35, "name": "Comedy"}]},
        )


class RadarrClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_movie_is_added_without_automatic_search(self) -> None:
        seen_post: dict = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v3/movie" and request.method == "GET":
                return httpx.Response(200, json=[])
            if request.url.path == "/api/v3/movie/lookup/tmdb":
                return httpx.Response(200, json={"tmdbId": 123, "title": "Example Movie"})
            if request.url.path == "/api/v3/rootfolder":
                return httpx.Response(200, json=[{"path": "/movies", "freeSpace": 1000}])
            if request.url.path == "/api/v3/qualityprofile":
                return httpx.Response(200, json=[{"id": 4, "name": "HD-1080p"}])
            if request.url.path == "/api/v3/movie" and request.method == "POST":
                seen_post.update(__import__("json").loads(request.content))
                return httpx.Response(201, json={"id": 88, **seen_post})
            self.fail(f"Unexpected Radarr request: {request.method} {request.url}")

        client = RadarrClient(
            "http://radarr:7878",
            "secret",
            transport=httpx.MockTransport(handler),
        )
        movie = await client.ensure_movie(123)

        self.assertEqual(movie["id"], 88)
        self.assertEqual(seen_post["rootFolderPath"], "/movies")
        self.assertEqual(seen_post["qualityProfileId"], 4)
        self.assertFalse(seen_post["addOptions"]["searchForMovie"])

    async def test_download_settings_include_selected_library_and_hardlinks(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v3/rootfolder":
                return httpx.Response(200, json=[{"path": "/media/Movies", "freeSpace": 1000}])
            if request.url.path == "/api/v3/qualityprofile":
                return httpx.Response(200, json=[{"id": 4, "name": "HD-1080p"}])
            if request.url.path == "/api/v3/config/mediamanagement":
                return httpx.Response(200, json={"copyUsingHardlinks": True})
            self.fail(f"Unexpected Radarr request: {request.method} {request.url}")

        client = RadarrClient(
            "http://radarr:7878",
            "secret",
            root_folder_path="/media/Movies",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(
            await client.download_settings(),
            {"library_path": "/media/Movies", "hardlinks_enabled": True},
        )

    def test_release_response_is_sanitised_and_useful(self) -> None:
        result = RadarrClient.normalise_release(
            {
                "guid": "tracker-guid",
                "indexerId": 7,
                "indexer": "IPTorrents",
                "title": "Example.1080p",
                "quality": {"quality": {"name": "Bluray-1080p"}},
                "size": 2147483648,
                "seeders": 12,
                "leechers": 3,
                "approved": True,
                "downloadAllowed": True,
                "rejections": [],
                "downloadUrl": "https://tracker.invalid/secret-passkey",
            }
        )

        self.assertEqual(result["size_gb"], 2.0)
        self.assertEqual(result["quality"], "Bluray-1080p")
        self.assertEqual(result["seeders"], 12)
        self.assertNotIn("downloadUrl", result)
        self.assertNotIn("secret-passkey", str(result))


class QBittorrentClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_password_login_and_torrent_progress_share_authenticated_session(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            self.assertEqual(request.headers["Origin"], "http://qbittorrent:8080")
            self.assertEqual(request.headers["Referer"], "http://qbittorrent:8080/")
            if request.url.path == "/api/v2/auth/login":
                return httpx.Response(
                    200,
                    text="Unexpected but authenticated response",
                    headers={"Set-Cookie": "SID=session; path=/"},
                )
            self.assertEqual(request.headers.get("Cookie"), "SID=session")
            if request.url.path == "/api/v2/app/version":
                return httpx.Response(200, text="v5.2.0")
            if request.url.path == "/api/v2/torrents/info":
                return httpx.Response(200, json=[{"hash": "private", "progress": 0.5}])
            self.fail(f"Unexpected qBittorrent request: {request.url}")

        client = QBittorrentClient(
            "http://qbittorrent:8080",
            "mediahub",
            "secret",
            transport=httpx.MockTransport(handler),
        )

        torrents = await client.torrents()

        self.assertEqual(torrents[0]["progress"], 0.5)
        self.assertEqual(seen_paths, [
            "/api/v2/auth/login",
            "/api/v2/app/version",
            "/api/v2/torrents/info",
        ])

    async def test_api_key_authenticates_version_and_torrent_requests(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertNotEqual(request.url.path, "/api/v2/auth/login")
            self.assertEqual(request.headers["Authorization"], "Bearer qbt_example")
            if request.url.path == "/api/v2/app/version":
                return httpx.Response(200, text="v5.2.0")
            if request.url.path == "/api/v2/torrents/info":
                return httpx.Response(200, json=[])
            self.fail(f"Unexpected qBittorrent request: {request.url}")

        client = QBittorrentClient(
            "http://qbittorrent:8080",
            "",
            "",
            api_key="qbt_example",
            auth_method="api_key",
            transport=httpx.MockTransport(handler),
        )

        self.assertEqual(await client.torrents(), [])

    async def test_download_settings_return_only_safe_path_fields(self) -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v2/app/version":
                return httpx.Response(200, text="v5.2.0")
            if request.url.path == "/api/v2/app/preferences":
                return httpx.Response(
                    200,
                    json={
                        "save_path": "/media/completed",
                        "temp_path_enabled": True,
                        "temp_path": "/media/incomplete",
                        "web_ui_username": "must-not-leak",
                    },
                )
            if request.url.path == "/api/v2/torrents/categories":
                return httpx.Response(
                    200,
                    json={"radarr": {"name": "radarr", "savePath": "/media/completed/radarr"}},
                )
            self.fail(f"Unexpected qBittorrent request: {request.url}")

        client = QBittorrentClient(
            "http://qbittorrent:8080",
            "",
            "",
            api_key="qbt_example",
            auth_method="api_key",
            transport=httpx.MockTransport(handler),
        )

        result = await client.download_settings()

        self.assertEqual(
            result,
            {
                "completed_path": "/media/completed",
                "incomplete_enabled": True,
                "incomplete_path": "/media/incomplete",
                "radarr_category_path": "/media/completed/radarr",
            },
        )
        self.assertNotIn("must-not-leak", str(result))


class DownloadWorkflowAnalysisTests(unittest.TestCase):
    def test_separate_paths_and_hardlinks_are_healthy(self) -> None:
        result = analyse_download_workflow(
            {"library_path": "/media/Movies", "hardlinks_enabled": True},
            {
                "completed_path": "/media/completed",
                "incomplete_enabled": True,
                "incomplete_path": "/media/incomplete",
                "radarr_category_path": "radarr",
            },
        )

        self.assertEqual(result["status"], "healthy")
        self.assertTrue(result["hardlinks_enabled"])
        self.assertEqual(result["radarr_category_path"], "/media/completed/radarr")
        self.assertTrue(all(check["level"] == "ok" for check in result["checks"]))

    def test_download_path_inside_library_is_unsafe(self) -> None:
        result = analyse_download_workflow(
            {"library_path": "/media/Movies", "hardlinks_enabled": False},
            {
                "completed_path": "/media/Movies/downloads",
                "incomplete_enabled": False,
                "incomplete_path": "",
                "radarr_category_path": "",
            },
        )

        self.assertEqual(result["status"], "error")
        self.assertIn("must not be inside", str(result["checks"]))

    def test_missing_library_path_requires_review(self) -> None:
        result = analyse_download_workflow(
            {"library_path": "", "hardlinks_enabled": True},
            {
                "completed_path": "/media/completed",
                "incomplete_enabled": False,
                "incomplete_path": "",
                "radarr_category_path": "",
            },
        )

        self.assertEqual(result["status"], "warning")
        self.assertIn("Select a Radarr movie root folder", str(result["checks"]))


class FakeTmdb:
    async def details(self, tmdb_id: int) -> dict:
        return {"tmdb_id": tmdb_id, "title": "Example Movie", "year": "2026"}


class FakeRadarr:
    grabbed: list[tuple[str, int]]

    def __init__(self) -> None:
        self.grabbed = []
        self.library_movie_id = 88

    async def ensure_movie(self, tmdb_id: int) -> dict:
        return {"id": 88, "tmdbId": tmdb_id, "title": "Example Movie", "hasFile": False}

    async def releases(self, radarr_movie_id: int) -> list[dict]:
        return [release()]

    async def grab(self, *, guid: str, indexer_id: int) -> dict:
        self.grabbed.append((guid, indexer_id))
        return {"infoHash": "ABC123"}

    async def queue(self) -> list[dict]:
        return []

    async def movies(self) -> list[dict]:
        return [
            {
                "id": self.library_movie_id,
                "tmdbId": 123,
                "title": "Example Movie",
                "hasFile": True,
            }
        ]

    async def download_settings(self) -> dict:
        return {"library_path": "/media/Movies", "hardlinks_enabled": True}


class FakeQbittorrent:
    def __init__(self) -> None:
        self.items: list[dict] = []

    async def torrents(self) -> list[dict]:
        return self.items

    async def download_settings(self) -> dict:
        return {
            "completed_path": "/media/completed",
            "incomplete_enabled": True,
            "incomplete_path": "/media/incomplete",
            "radarr_category_path": "/media/completed/radarr",
        }


class MovieRequestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.data_path = Path(self.temp.name)
        self.database_patch = patch.object(main, "DATABASE_FILE", self.data_path / "mediahub.db")
        self.app_data_patch = patch.object(main, "APP_DATA", self.data_path)
        self.options_patch = patch.object(
            main,
            "load_options",
            return_value={
                "storage": {
                    "media_path": str(self.data_path),
                    "minimum_free_gb": 0,
                    "safety_margin_gb": 0,
                    "reservation_multiplier": 1,
                },
                "integrations": {},
            },
        )
        self.fake_radarr = FakeRadarr()
        self.fake_qbittorrent = FakeQbittorrent()
        self.clients_patch = patch.object(
            main,
            "configured_clients",
            return_value=(FakeTmdb(), self.fake_radarr, self.fake_qbittorrent),
        )
        for active_patch in (
            self.database_patch,
            self.app_data_patch,
            self.options_patch,
            self.clients_patch,
        ):
            active_patch.start()
        main.release_cache.clear()
        main.initialise_database()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        for active_patch in (
            self.clients_patch,
            self.options_patch,
            self.app_data_patch,
            self.database_patch,
        ):
            active_patch.stop()
        self.temp.cleanup()

    def test_release_search_uses_opaque_tokens(self) -> None:
        response = self.client.post(
            "/api/movies/123/releases",
            headers=headers(),
            json={
                "maximum_size_gb": 3,
                "minimum_seeders": 1,
                "quality_mode": "720p_and_1080p",
            },
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["releases"][0]
        self.assertTrue(result["eligible"])
        self.assertGreaterEqual(len(result["release_token"]), 16)
        self.assertNotIn("guid", result)
        self.assertNotIn("info_hash", result)
        self.assertNotIn("private-indexer-guid", response.text)

    def test_release_policy_accepts_720p_and_1080p_by_default(self) -> None:
        release_720p = {**release(), "quality": "WEBDL-720p"}
        release_2160p = {**release(), "quality": "WEBDL-2160p"}
        rules = main.ReleaseRules(maximum_size_gb=3, minimum_seeders=1)

        self.assertTrue(main.release_with_policy(release_720p, rules)["eligible"])
        self.assertTrue(main.release_with_policy(release(), rules)["eligible"])
        self.assertFalse(main.release_with_policy(release_2160p, rules)["eligible"])

    def test_release_policy_can_select_one_hd_resolution(self) -> None:
        release_720p = {**release(), "quality": "WEBDL-720p"}
        only_720p = main.ReleaseRules(quality_mode="720p_only")
        only_1080p = main.ReleaseRules(quality_mode="1080p_only")

        self.assertTrue(main.release_with_policy(release_720p, only_720p)["eligible"])
        self.assertFalse(main.release_with_policy(release(), only_720p)["eligible"])
        self.assertFalse(main.release_with_policy(release_720p, only_1080p)["eligible"])

    def test_legacy_1080p_rule_remains_supported(self) -> None:
        release_720p = {**release(), "quality": "WEBDL-720p"}
        rules = main.ReleaseRules(require_1080p=True)

        result = main.release_with_policy(release_720p, rules)

        self.assertFalse(result["eligible"])
        self.assertIn("MediaHub requires a 1080p release", result["policy_rejections"])

    def test_download_workflow_endpoint_is_healthy_for_safe_paths(self) -> None:
        response = self.client.get("/api/setup/download-workflow", headers=headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")
        self.assertEqual(response.json()["library_path"], "/media/Movies")

    def test_automatic_request_grabs_eligible_release_and_tracks_status(self) -> None:
        requested = self.client.post(
            "/api/movies/123/request",
            headers=headers(),
            json={"maximum_size_gb": 3, "minimum_seeders": 1, "require_1080p": True},
        )

        self.assertEqual(requested.status_code, 200)
        self.assertEqual(requested.json()["request"]["status"], "queued")
        self.assertEqual(self.fake_radarr.grabbed, [("private-indexer-guid", 7)])
        self.assertNotIn("private-indexer-guid", requested.text)

        downloads = self.client.get("/api/downloads", headers=headers())
        self.assertEqual(downloads.status_code, 200)
        self.assertEqual(downloads.json()[0]["status"], "available")
        self.assertEqual(downloads.json()[0]["progress"], 100.0)

    def test_completed_import_recovers_changed_radarr_id_and_reports_seeding(self) -> None:
        requested = self.client.post(
            "/api/movies/123/request",
            headers=headers(),
            json={"maximum_size_gb": 3, "minimum_seeders": 1, "require_1080p": True},
        )
        self.assertEqual(requested.status_code, 200)
        self.fake_radarr.library_movie_id = 99
        self.fake_qbittorrent.items = [
            {"hash": "abc123", "progress": 1.0, "state": "uploading"}
        ]

        downloads = self.client.get("/api/downloads", headers=headers())

        self.assertEqual(downloads.status_code, 200)
        result = downloads.json()[0]
        self.assertEqual(result["status"], "available")
        self.assertIn("retains the seeding data", result["status_message"])
        with main.connect_db() as db:
            row = db.execute(
                "SELECT radarr_movie_id FROM requests WHERE id = ?",
                (result["id"],),
            ).fetchone()
            audit = db.execute(
                "SELECT action FROM audit_events WHERE request_id = ? AND action = 'movie_available'",
                (result["id"],),
            ).fetchone()
        self.assertEqual(row["radarr_movie_id"], 99)
        self.assertEqual(audit["action"], "movie_available")

    def test_completed_download_with_radarr_warning_needs_attention(self) -> None:
        status, progress, message = main._download_status(
            {"trackedDownloadStatus": "warning"},
            {"progress": 1.0, "state": "uploading"},
        )

        self.assertEqual(status, "processing")
        self.assertEqual(progress, 100.0)
        self.assertEqual(message, "Radarr import needs attention")


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_request_table_receives_download_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "mediahub.db"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """
                    CREATE TABLE requests (
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
                    )
                    """
                )
            with (
                patch.object(main, "DATABASE_FILE", database),
                patch.object(main, "APP_DATA", Path(directory)),
            ):
                main.initialise_database()
                with main.connect_db() as connection:
                    columns = {
                        row["name"] for row in connection.execute("PRAGMA table_info(requests)")
                    }

            self.assertTrue(
                {
                    "radarr_movie_id",
                    "selected_release_guid",
                    "selected_release_title",
                    "download_id",
                    "progress",
                    "status_message",
                }.issubset(columns)
            )


if __name__ == "__main__":
    unittest.main()
