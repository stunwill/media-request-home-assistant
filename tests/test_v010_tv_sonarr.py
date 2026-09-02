from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from mediahub.app import main, tv_main, tv_ui
from mediahub.app.tv_services import SonarrClient, TmdbTvClient, normalise_tv_show


def test_normalise_tv_show() -> None:
    show = normalise_tv_show({"id": 42, "name": "Example", "first_air_date": "2024-01-02", "vote_average": 8.2, "genre_ids": [18]})
    assert show["media_type"] == "tv"
    assert show["tmdb_id"] == 42
    assert show["year"] == "2024"
    assert show["rating"] == 8.2


def test_tmdb_tv_catalogue_and_filters() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/discover/tv"
            assert request.url.params["with_genres"] == "18"
            assert float(request.url.params["vote_average.gte"]) == 7.0
            return httpx.Response(200, json={"page": 1, "total_pages": 2, "total_results": 1, "results": [{"id": 42, "name": "Example", "first_air_date": "2024-01-02", "vote_average": 8.2}]})
        client = TmdbTvClient("secret", transport=httpx.MockTransport(handler))
        data = await client.catalogue(genre_id=18, rating_from=7)
        assert data["shows"][0]["tmdb_id"] == 42
        assert data["total_pages"] == 2
    asyncio.run(run())


def test_tmdb_tv_search_uses_tv_endpoint() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/3/search/tv"
            assert request.url.params["query"] == "Example"
            return httpx.Response(200, json={"page": 1, "total_pages": 1, "total_results": 1, "results": [{"id": 42, "name": "Example"}]})
        client = TmdbTvClient("secret", transport=httpx.MockTransport(handler))
        data = await client.catalogue(query="Example")
        assert data["shows"][0]["name"] == "Example"
    asyncio.run(run())


def test_tmdb_tv_details_include_seasons_cast_and_tvdb() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={
                "id": 42,
                "name": "Example",
                "first_air_date": "2024-01-02",
                "number_of_seasons": 2,
                "number_of_episodes": 20,
                "seasons": [{"id": 1, "season_number": 1, "name": "Season 1", "episode_count": 10}],
                "credits": {"cast": [{"id": 5, "name": "Actor", "character": "Lead"}]},
                "created_by": [{"id": 8, "name": "Creator"}],
                "networks": [{"id": 9, "name": "Network"}],
                "external_ids": {"tvdb_id": 12345, "imdb_id": "tt1234567"},
                "content_ratings": {"results": [{"iso_3166_1": "AU", "rating": "M"}]},
                "videos": {"results": []},
            })
        client = TmdbTvClient("secret", transport=httpx.MockTransport(handler))
        show = await client.details(42)
        assert show["seasons"][0]["season_number"] == 1
        assert show["cast"][0]["id"] == 5
        assert show["external_ids"]["tvdb_id"] == 12345
        assert show["certification"] == "M"
    asyncio.run(run())


def test_sonarr_ensure_series_adds_selected_seasons() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []
        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path == "/api/v3/series":
                if request.method == "GET":
                    return httpx.Response(200, json=[])
                body = __import__('json').loads(request.content.decode())
                assert body["rootFolderPath"] == "/tv"
                assert body["qualityProfileId"] == 3
                assert body["seasons"][0]["monitored"] is False
                assert body["seasons"][1]["monitored"] is True
                return httpx.Response(201, json={"id": 99, **body})
            if request.url.path == "/api/v3/series/lookup":
                return httpx.Response(200, json=[{"title": "Example", "tvdbId": 12345, "seasons": [{"seasonNumber": 1}, {"seasonNumber": 2}]}])
            if request.url.path == "/api/v3/rootfolder":
                return httpx.Response(200, json=[{"path": "/tv"}])
            if request.url.path == "/api/v3/qualityprofile":
                return httpx.Response(200, json=[{"id": 3, "name": "HD"}])
            return httpx.Response(404)
        client = SonarrClient("http://sonarr", "key", transport=httpx.MockTransport(handler))
        result = await client.ensure_series({"tmdb_id": 42, "name": "Example", "external_ids": {"tvdb_id": 12345}}, selected_seasons=[2])
        assert result["id"] == 99
    asyncio.run(run())


def test_sonarr_search_uses_series_and_season_commands() -> None:
    async def run() -> None:
        names: list[str] = []
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/v3/command":
                body = __import__('json').loads(request.content.decode())
                names.append(body["name"])
                return httpx.Response(201, json={"id": 1})
            return httpx.Response(404)
        client = SonarrClient("http://sonarr", "key", transport=httpx.MockTransport(handler))
        await client.search(99, [1, 2])
        await client.search(99, None)
        assert names == ["SeasonSearch", "SeasonSearch", "SeriesSearch"]
    asyncio.run(run())


def test_tv_duplicate_protection_is_season_aware() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "mediahub.db"
        with patch.object(main, "DATABASE_FILE", database):
            main.initialise_database()
            tv_main.initialise_tv_database()
            with main.connect_db() as db:
                db.execute("""
                    INSERT INTO requests (
                        media_type,title,external_id,requested_by_id,requested_by_name,
                        estimated_size_gb,reserved_size_gb,status,progress,status_message,
                        created_at,updated_at,requested_scope,requested_seasons_json
                    ) VALUES ('tv','Example','42','u','User',0.01,0,'searching',0,'Searching','now','now','seasons','[1]')
                """)
                db.commit()
            assert tv_main._tv_duplicate(42, [1]) is not None
            assert tv_main._tv_duplicate(42, [2]) is None


def test_tv_request_entire_series_and_selected_seasons() -> None:
    show = {"tmdb_id": 42, "name": "Example", "seasons": [{"season_number": 1}, {"season_number": 2}], "external_ids": {"tvdb_id": 12345}}
    principal = main.Principal(user_id="u", username="user", display_name="User", role="admin", active=True)
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "mediahub.db"
        with patch.object(main, "DATABASE_FILE", database), patch.object(tv_main, "tv_clients") as clients:
            tmdb = AsyncMock()
            tmdb.details.return_value = show
            sonarr = AsyncMock()
            sonarr.ensure_series.return_value = {"id": 99}
            clients.return_value = (tmdb, sonarr)
            main.initialise_database()
            result = asyncio.run(tv_main.request_tv(42, tv_main.TvRequestCreate(scope="seasons", seasons=[2]), principal))
            assert result["seasons"] == [2]
            sonarr.search.assert_awaited_once_with(99, [2])


def test_tv_routes_and_version_registered() -> None:
    assert tv_ui.app.version.endswith("-dev")
    paths = {route.path for route in tv_ui.app.routes}
    assert "/api/catalog/tv" in paths
    assert "/api/catalog/tv/{tmdb_id}" in paths
    assert "/api/tv/{tmdb_id}/request" in paths
    assert "/api/sonarr/options" in paths
    assert "/api/downloads/tv/{request_id}/details" in paths


def test_infinite_scroll_replaces_manual_load_more() -> None:
    html = main.INDEX_HTML
    assert "IntersectionObserver" in html
    assert "catalogue-sentinel" in html
    assert "rootMargin:'600px 0px'" in html
    assert "appendUnique" in html
    assert "s.loading" in html
    assert "s.seen" in html
    assert "oldLoadMore.remove()" in html
    assert "Load more TV Shows" not in html


def test_movies_and_tv_have_independent_state() -> None:
    html = main.INDEX_HTML
    assert "catalogueState" in html
    assert "movie:{page:1" in html
    assert "tv:{page:1" in html
    assert "browseMedia='movie'" in html
    assert "Movies</button><button" in html
    assert "TV Shows" in html


def test_existing_movie_routes_remain_present() -> None:
    paths = {route.path for route in tv_ui.app.routes}
    assert "/api/catalog/movies/{tmdb_id}" in paths
    assert "/api/movies/{tmdb_id}/request" in paths
    assert "/api/movies/{tmdb_id}/releases" in paths
    assert "/api/movies/{tmdb_id}/watch" in paths
    assert "/api/setup/plex" in paths
