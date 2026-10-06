from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from mediahub.app import main, release_identity_main, runtime


class DocumentaryMovieDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_older_movie_uses_direct_prowlarr_when_radarr_returns_nothing(self) -> None:
        movie = {
            "tmdb_id": 653574,
            "title": "The Donut King",
            "original_title": "The Donut King",
            "release_date": "2020-10-30",
            "year": "2020",
        }
        radarr = SimpleNamespace()
        radarr._request = AsyncMock(return_value=[{"id": 21, "name": "IPTorrents"}])
        raw_release = {
            "guid": "donut-guid",
            "indexerId": 1,
            "indexer": "IPTorrents",
            "title": "The Donut King 2020 1080p WEBRip x265",
            "size": int(1.53 * 1024**3),
            "seeders": 169,
            "leechers": 9,
        }

        async def no_radarr_results(*args, **kwargs):
            return {"id": 88, "tmdbId": movie["tmdb_id"]}, [], False

        with (
            patch.object(runtime, "_original_search_movie_releases", no_radarr_results),
            patch.object(runtime, "_prowlarr_search", AsyncMock(return_value=[raw_release])),
            patch.object(
                main,
                "configured_clients",
                return_value=(SimpleNamespace(), radarr, SimpleNamespace()),
            ),
        ):
            _, releases, _ = await runtime.search_movie_releases(
                movie["tmdb_id"],
                main.ReleaseRules(
                    maximum_size_gb=3,
                    minimum_seeders=1,
                    quality_mode="720p_and_1080p",
                ),
                "user-1",
                movie=movie,
            )

        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["title"], raw_release["title"])
        self.assertTrue(releases[0]["eligible"])
        self.assertEqual(releases[0]["quality"], "1080p")
        self.assertEqual(releases[0]["search_source"], "prowlarr_direct")

    async def test_identity_layer_keeps_documentary_movie_and_rejects_tv_episode(self) -> None:
        movie = {
            "tmdb_id": 653574,
            "title": "The Donut King",
            "original_title": "The Donut King",
            "release_date": "2020-10-30",
            "year": "2020",
        }
        releases = [
            {
                "source": "prowlarr_direct",
                "title": "The Donut King 2020 1080p WEBRip x265",
                "quality": "1080p",
                "size_gb": 1.53,
                "seeders": 169,
                "eligible": True,
                "policy_rejections": [],
                "release_token": "movie-token",
            },
            {
                "source": "prowlarr_direct",
                "title": "The Donut King S01E01 1080p WEB-DL x265",
                "quality": "1080p",
                "size_gb": 0.95,
                "seeders": 84,
                "eligible": True,
                "policy_rejections": [],
                "release_token": "tv-token",
            },
        ]

        async def discovered(*args, **kwargs):
            return {"id": 88, "tmdbId": movie["tmdb_id"]}, releases, False

        with patch.object(
            release_identity_main,
            "_original_search_movie_releases",
            discovered,
        ):
            _, evaluated, _ = await release_identity_main.search_movie_releases(
                movie["tmdb_id"],
                main.ReleaseRules(),
                "user-1",
                movie=movie,
            )

        self.assertTrue(evaluated[0]["eligible"])
        self.assertEqual(evaluated[0]["release_token"], "movie-token")
        self.assertFalse(evaluated[1]["eligible"])
        self.assertNotIn("release_token", evaluated[1])
        self.assertEqual(evaluated[1]["primary_rejection"]["category"], "identity")

    def test_old_movie_low_quality_fallback_remains_blocked(self) -> None:
        release = {
            "source": "prowlarr_direct",
            "guid": "cam-guid",
            "indexer_id": 21,
            "title": "The Donut King 2020 HDCAM x264",
            "quality": "CAM",
            "size_gb": 1.0,
            "seeders": 10,
        }

        public = runtime._prowlarr_policy(
            release,
            main.ReleaseRules(),
            allow_low_quality=False,
        )

        self.assertFalse(public["eligible"])
        self.assertTrue(
            any("Low-quality fallback" in reason for reason in public["policy_rejections"])
        )


if __name__ == "__main__":
    unittest.main()
