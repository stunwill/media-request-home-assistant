from __future__ import annotations

import asyncio

import httpx

from mediahub.app import catalogue_fixes, main, media_services, tv_services, tv_ui


def test_legacy_movie_loader_is_disabled_before_infinite_scroll_runs() -> None:
    html = main.INDEX_HTML
    assert "window.MEDIAHUB_INFINITE_CATALOGUE=true" in html
    assert (
        "async function loadMovies(append=false){if(window.MEDIAHUB_INFINITE_CATALOGUE)return;"
        in html
    )
    assert "oldLoadMore.remove()" in html
    assert "catalogue-sentinel" in html
    assert tv_ui.app.version == "0.10.0-dev"


def test_movie_search_keeps_only_english_original_language() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/search/movie"
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 3,
                    "results": [
                        {"id": 1, "title": "Ballistic", "original_language": "en"},
                        {"id": 2, "title": "彈道", "original_language": "zh"},
                        {"id": 3, "title": "Balística", "original_language": "es"},
                    ],
                },
            )

        client = media_services.TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(query="ballistic")
        assert [movie["tmdb_id"] for movie in result["movies"]] == [1]

    asyncio.run(run())


def test_movie_discover_requests_english_and_filters_defensively() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/discover/movie"
            assert request.url.params["with_original_language"] == "en"
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 2,
                    "results": [
                        {"id": 10, "title": "English Movie", "original_language": "en"},
                        {"id": 11, "title": "Film Français", "original_language": "fr"},
                    ],
                },
            )

        client = media_services.TmdbClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(genre_id=28)
        assert [movie["tmdb_id"] for movie in result["movies"]] == [10]

    asyncio.run(run())


def test_tv_search_keeps_only_english_original_language() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/search/tv"
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 3,
                    "results": [
                        {"id": 20, "name": "English Show", "original_language": "en"},
                        {"id": 21, "name": "한국 드라마", "original_language": "ko"},
                        {"id": 22, "name": "Serie", "original_language": "de"},
                    ],
                },
            )

        client = tv_services.TmdbTvClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(query="show")
        assert [show["tmdb_id"] for show in result["shows"]] == [20]

    asyncio.run(run())


def test_tv_discover_requests_english_and_filters_defensively() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/discover/tv"
            assert request.url.params["with_original_language"] == "en"
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total_pages": 1,
                    "total_results": 2,
                    "results": [
                        {"id": 30, "name": "English TV", "original_language": "en"},
                        {"id": 31, "name": "日本語", "original_language": "ja"},
                    ],
                },
            )

        client = tv_services.TmdbTvClient("secret", transport=httpx.MockTransport(handler))
        result = await client.catalogue(rating_from=7)
        assert [show["tmdb_id"] for show in result["shows"]] == [30]

    asyncio.run(run())


def test_person_search_is_not_filtered_as_media() -> None:
    payload = {
        "results": [
            {"id": 99, "name": "English Actor"},
        ]
    }
    assert catalogue_fixes._english_results(payload, allowed_path=False) is payload
