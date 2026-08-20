from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace

import httpx

from mediahub.app import enhanced_main
from mediahub.app.main import ReleaseRules
from mediahub.app.media_services import TmdbClient


class RecentReleaseFallbackTests(unittest.TestCase):
    def test_movie_released_within_one_year_is_recent(self) -> None:
        movie = {"release_date": "2026-02-01"}
        self.assertTrue(
            enhanced_main.is_recent_movie(movie, today=date(2026, 8, 20))
        )

    def test_movie_older_than_one_year_is_not_recent(self) -> None:
        movie = {"release_date": "2025-07-01"}
        self.assertFalse(
            enhanced_main.is_recent_movie(movie, today=date(2026, 8, 20))
        )

    def test_cam_release_can_be_fallback_candidate(self) -> None:
        release = {
            "title": "Example.Movie.2026.CAM.x264",
            "quality": "Unknown",
            "size_gb": 1.2,
            "seeders": 8,
            "download_allowed": True,
            "rejections": ["Quality is not wanted in profile"],
            "approved": False,
            "flags": [],
            "guid": "secret-guid",
            "info_hash": "secret-hash",
        }
        result = enhanced_main.recent_fallback_policy(
            release,
            ReleaseRules(maximum_size_gb=3, minimum_seeders=1),
        )
        self.assertTrue(result["eligible"])
        self.assertTrue(result["recent_quality_fallback"])
        self.assertNotIn("guid", result)
        self.assertNotIn("info_hash", result)

    def test_non_cam_low_resolution_release_is_not_automatically_allowed(self) -> None:
        release = {
            "title": "Example.Movie.2026.480p.WEB-DL",
            "quality": "WEBDL-480p",
            "size_gb": 1.0,
            "seeders": 8,
            "download_allowed": True,
            "rejections": ["Quality is not wanted in profile"],
            "approved": False,
            "flags": [],
        }
        result = enhanced_main.recent_fallback_policy(
            release,
            ReleaseRules(maximum_size_gb=3, minimum_seeders=1),
        )
        self.assertFalse(result["eligible"])


class DuplicateDisplayTests(unittest.TestCase):
    def test_duplicate_download_rows_collapse_to_available_record(self) -> None:
        rows = [
            {
                "id": 20,
                "external_id": "123",
                "status": "queued",
                "created_at": "2026-08-20T01:00:00+00:00",
                "updated_at": "2026-08-20T01:00:00+00:00",
            },
            {
                "id": 19,
                "external_id": "123",
                "status": "available",
                "created_at": "2026-08-19T01:00:00+00:00",
                "updated_at": "2026-08-19T02:00:00+00:00",
            },
        ]
        result = enhanced_main._choose_download_rows(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(dict(result[0])["id"], 19)

    def test_different_tmdb_movies_remain_separate(self) -> None:
        rows = [
            {"id": 1, "external_id": "111", "status": "queued", "created_at": "1"},
            {"id": 2, "external_id": "222", "status": "queued", "created_at": "2"},
        ]
        self.assertEqual(len(enhanced_main._choose_download_rows(rows)), 2)


class ActorSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_actor_name_falls_back_to_person_search_and_cast_discovery(self) -> None:
        seen_paths: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen_paths.append(request.url.path)
            if request.url.path == "/3/search/movie":
                return httpx.Response(
                    200,
                    json={"page": 1, "total_pages": 1, "total_results": 0, "results": []},
                )
            if request.url.path == "/3/search/person":
                return httpx.Response(
                    200,
                    json={"results": [{"id": 42, "name": "Test Actor"}]},
                )
            if request.url.path == "/3/discover/movie":
                self.assertEqual(request.url.params["with_cast"], "42")
                return httpx.Response(
                    200,
                    json={
                        "page": 1,
                        "total_pages": 1,
                        "total_results": 1,
                        "results": [
                            {
                                "id": 99,
                                "title": "Actor Movie",
                                "release_date": "2026-05-01",
                            }
                        ],
                    },
                )
            self.fail(f"Unexpected TMDb request: {request.url}")

        client = TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(query="Test Actor")

        self.assertEqual(result["search_mode"], "actor")
        self.assertEqual(result["movies"][0]["title"], "Actor Movie")
        self.assertEqual(
            seen_paths,
            ["/3/search/movie", "/3/search/person", "/3/discover/movie"],
        )


if __name__ == "__main__":
    unittest.main()
