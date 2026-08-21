from __future__ import annotations

import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mediahub.app import main, runtime


class CurrentYearFallbackTests(unittest.TestCase):
    def test_future_current_year_movie_uses_fallback(self) -> None:
        movie = {"release_date": "2026-12-10", "year": "2026"}
        self.assertTrue(
            runtime.recent_or_current_year_movie(movie, today=date(2026, 8, 21))
        )

    def test_movie_more_than_one_year_old_does_not_use_fallback(self) -> None:
        movie = {"release_date": "2025-07-01", "year": "2025"}
        self.assertFalse(
            runtime.recent_or_current_year_movie(movie, today=date(2026, 8, 21))
        )

    def test_recent_previous_year_movie_uses_fallback(self) -> None:
        movie = {"release_date": "2025-12-01", "year": "2025"}
        self.assertTrue(
            runtime.recent_or_current_year_movie(movie, today=date(2026, 8, 21))
        )


class ProwlarrResultTests(unittest.TestCase):
    def test_title_match_rejects_wrong_franchise_year(self) -> None:
        movie = {"title": "Resident Evil", "release_date": "2026-09-18"}
        self.assertTrue(runtime._matches_movie("Resident.Evil.2026.HDCAM.x264", movie))
        self.assertFalse(runtime._matches_movie("Resident.Evil.2016.1080p.BluRay", movie))

    def test_cam_result_is_eligible_when_indexer_is_synced(self) -> None:
        raw = {
            "guid": "tracker-guid",
            "indexerId": 7,
            "indexer": "IPTorrents",
            "title": "Resident.Evil.2026.HDCAM.x264",
            "size": int(1.2 * 1024**3),
            "seeders": 14,
            "leechers": 2,
        }
        release = runtime._normalise_prowlarr_release(raw, radarr_indexer_id=21)
        public = runtime._prowlarr_policy(
            release,
            main.ReleaseRules(maximum_size_gb=3, minimum_seeders=1),
        )

        self.assertEqual(release["quality"], "CAM")
        self.assertTrue(public["eligible"])
        self.assertTrue(public["recent_quality_fallback"])
        self.assertEqual(public["search_source"], "prowlarr_direct")
        self.assertNotIn("guid", public)
        self.assertNotIn("info_hash", public)

    def test_unsynced_prowlarr_indexer_is_visible_but_not_downloadable(self) -> None:
        raw = {
            "guid": "tracker-guid",
            "indexerId": 7,
            "indexer": "IPTorrents",
            "title": "Resident.Evil.2026.HDCAM.x264",
            "size": 900 * 1024**2,
            "seeders": 8,
        }
        release = runtime._normalise_prowlarr_release(raw, radarr_indexer_id=0)
        public = runtime._prowlarr_policy(release, main.ReleaseRules())

        self.assertFalse(public["eligible"])
        self.assertIn("not synced to Radarr", str(public["policy_rejections"]))


class DirectSearchFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_zero_radarr_results_fall_back_to_prowlarr(self) -> None:
        movie = {
            "tmdb_id": 123,
            "title": "Resident Evil",
            "original_title": "Resident Evil",
            "release_date": "2026-09-18",
            "year": "2026",
        }
        radarr = SimpleNamespace()
        radarr.ensure_movie = AsyncMock(return_value={"id": 88, "tmdbId": 123})
        radarr._request = AsyncMock(
            return_value=[{"id": 21, "name": "IPTorrents"}]
        )
        raw_release = {
            "guid": "tracker-guid",
            "indexerId": 7,
            "indexer": "IPTorrents",
            "title": "Resident.Evil.2026.HDCAM.x264",
            "size": 950 * 1024**2,
            "seeders": 11,
            "leechers": 1,
        }

        async def no_radarr_results(*args, **kwargs):
            return {"id": 88, "tmdbId": 123}, [], False

        with (
            patch.object(runtime, "_original_search_movie_releases", no_radarr_results),
            patch.object(runtime, "_prowlarr_search", AsyncMock(return_value=[raw_release])),
            patch.object(
                main,
                "configured_clients",
                return_value=(SimpleNamespace(), radarr, SimpleNamespace()),
            ),
        ):
            _, releases, fallback_active = await runtime.search_movie_releases(
                123,
                main.ReleaseRules(maximum_size_gb=3, minimum_seeders=1),
                "user-1",
                movie=movie,
            )

        self.assertTrue(fallback_active)
        self.assertEqual(len(releases), 1)
        self.assertTrue(releases[0]["eligible"])
        self.assertEqual(releases[0]["quality"], "CAM")
        self.assertGreaterEqual(len(releases[0]["release_token"]), 16)

    async def test_interactive_fallback_selection_reuses_existing_request_flow(self) -> None:
        release = {
            "source": "prowlarr_direct",
            "guid": "chosen-guid",
            "prowlarr_indexer_id": 7,
            "indexer_id": 21,
            "title": "Resident.Evil.2026.HDCAM.x264",
            "quality": "CAM",
            "size_gb": 1.0,
            "seeders": 5,
        }
        token = main.cache_release(123, "user-1", release)
        payload = main.MovieRequestCreate(release_token=token)
        principal = SimpleNamespace(user_id="user-1")

        async def existing_request_flow(tmdb_id, forwarded_payload, forwarded_principal):
            self.assertEqual(tmdb_id, 123)
            self.assertIsNone(forwarded_payload.release_token)
            self.assertEqual(forwarded_principal.user_id, "user-1")
            self.assertEqual(
                runtime._selected_prowlarr_release[(123, "user-1")],
                ("chosen-guid", 7),
            )
            return {"ok": True}

        with patch.object(runtime, "_original_request_movie", existing_request_flow):
            result = await runtime.request_movie(123, payload, principal)

        self.assertEqual(result, {"ok": True})
        self.assertNotIn((123, "user-1"), runtime._selected_prowlarr_release)
        self.assertNotIn(token, main.release_cache)


if __name__ == "__main__":
    unittest.main()
