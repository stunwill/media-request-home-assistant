from __future__ import annotations

import tempfile
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from mediahub.app import main
from mediahub.app.media_services import RadarrClient, TmdbClient


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


class FakeTmdb:
    async def details(self, tmdb_id: int) -> dict:
        return {"tmdb_id": tmdb_id, "title": "Example Movie", "year": "2026"}


class FakeRadarr:
    grabbed: list[tuple[str, int]]

    def __init__(self) -> None:
        self.grabbed = []

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
        return [{"id": 88, "tmdbId": 123, "title": "Example Movie", "hasFile": True}]


class FakeQbittorrent:
    async def torrents(self) -> list[dict]:
        return []


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
        self.clients_patch = patch.object(
            main,
            "configured_clients",
            return_value=(FakeTmdb(), self.fake_radarr, FakeQbittorrent()),
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
            json={"maximum_size_gb": 3, "minimum_seeders": 1, "require_1080p": True},
        )

        self.assertEqual(response.status_code, 200)
        result = response.json()["releases"][0]
        self.assertTrue(result["eligible"])
        self.assertGreaterEqual(len(result["release_token"]), 16)
        self.assertNotIn("guid", result)
        self.assertNotIn("info_hash", result)
        self.assertNotIn("private-indexer-guid", response.text)

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
