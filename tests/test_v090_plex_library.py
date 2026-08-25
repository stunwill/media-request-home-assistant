from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mediahub.app import main, plex_integration, plex_library, plex_main, settings


def principal(role: str = "admin") -> main.Principal:
    return main.Principal(
        user_id="ha-admin",
        username="stu",
        display_name="Stu",
        role=role,
        active=True,
    )


def test_guid_normalisation() -> None:
    assert plex_library.normalise_guid("tmdb://12345") == {"tmdb_id": "12345"}
    assert plex_library.normalise_guid("imdb://tt1234567") == {"imdb_id": "tt1234567"}
    assert plex_library.normalise_guid("local://abc") == {}


def test_identifier_matching_prefers_tmdb_then_imdb() -> None:
    items = [
        {"rating_key": "1", "title": "Example", "year": 2026, "tmdb_id": "123", "imdb_id": "tt111"},
        {"rating_key": "2", "title": "Other", "year": 2026, "tmdb_id": "999", "imdb_id": "tt222"},
    ]
    result = plex_library.match_movie({"tmdb_id": 123, "imdb_id": "tt222", "title": "Example", "year": "2026"}, items)
    assert result["match"]["rating_key"] == "1"
    assert result["confidence"] == "exact_identifier"
    assert result["match_method"] == "tmdb"


def test_title_year_fallback_is_conservative_and_rejects_ambiguity() -> None:
    items = [
        {"rating_key": "1", "title": "The Example", "year": 2026},
        {"rating_key": "2", "title": "The Example", "year": 2026},
    ]
    ambiguous = plex_library.match_movie({"title": "The Example", "year": "2026"}, items)
    assert ambiguous["match"] is None
    assert ambiguous["confidence"] == "ambiguous"
    wrong_year = plex_library.match_movie({"title": "The Example", "year": "2025"}, items)
    assert wrong_year["confidence"] == "not_found"


def test_safe_plex_url_contains_no_token() -> None:
    url = plex_library.plex_web_url("machine-123", "456")
    assert url is not None
    assert "machine-123" in url
    assert "456" in url
    assert "token" not in url.lower()
    assert "X-Plex-Token" not in url


def test_public_settings_redact_plex_token() -> None:
    public = settings.public_integration_settings(
        {"integrations": {"plex_url": "http://plex:32400", "plex_token": "super-secret", "plex_library_key": "1"}}
    )
    assert public["plex"]["url"] == "http://plex:32400"
    assert public["plex"]["token_set"] is True
    assert "super-secret" not in str(public)


def test_save_plex_settings_keeps_token_private() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        settings.save_integration_settings(
            {"plex_url": "http://plex:32400", "plex_token": "secret", "plex_library_key": "1"},
            settings_file=path,
        )
        options = settings.load_options(options_file=Path(tmp) / "none.json", settings_file=path)
        assert options["integrations"]["plex_token"] == "secret"
        assert settings.public_integration_settings(options)["plex"]["token_set"] is True


def test_plex_client_identity_and_library_discovery() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("X-Plex-Token") == "secret"
            if request.url.path == "/identity":
                return httpx.Response(200, json={"MediaContainer": {"machineIdentifier": "machine", "version": "1.2.3"}})
            if request.url.path == "/library/sections":
                return httpx.Response(200, json={"MediaContainer": {"Directory": [{"key": "1", "title": "Movies", "type": "movie"}]}})
            raise AssertionError(request.url)

        client = plex_library.PlexClient(
            plex_library.PlexConfig(url="http://plex:32400", token="secret"),
            transport=httpx.MockTransport(handler),
        )
        assert (await client.identity())["machine_identifier"] == "machine"
        assert (await client.movie_libraries())[0]["key"] == "1"

    asyncio.run(run())


def test_plex_client_parses_movie_guids() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"MediaContainer": {"Metadata": [{
                    "ratingKey": "42",
                    "title": "Example",
                    "year": 2026,
                    "Guid": [{"id": "tmdb://123"}, {"id": "imdb://tt1234567"}],
                }]}}
            )

        client = plex_library.PlexClient(
            plex_library.PlexConfig(url="http://plex:32400", token="secret", library_key="1"),
            transport=httpx.MockTransport(handler),
        )
        movie = (await client.movies())[0]
        assert movie["tmdb_id"] == "123"
        assert movie["imdb_id"] == "tt1234567"

    asyncio.run(run())


def test_plex_authentication_failure_is_sanitised() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "token=secret"})

        client = plex_library.PlexClient(
            plex_library.PlexConfig(url="http://plex:32400", token="secret"),
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(plex_library.PlexError) as caught:
            await client.identity()
        assert str(caught.value) == "Plex authentication failed"
        assert "secret" not in str(caught.value)

    asyncio.run(run())


def test_plex_unavailable_does_not_break_movie_details() -> None:
    movie = {"tmdb_id": 123, "title": "Example", "rating": 7.1, "lifecycle": {"state": "digital_available"}}
    with patch.object(plex_integration.rich_details, "rich_movie_details", AsyncMock(return_value=movie.copy())), patch.object(
        plex_integration, "plex_library_state", AsyncMock(return_value={"configured": True, "available": False, "matched": False, "status": "unavailable"})
    ):
        result = asyncio.run(plex_integration.movie_details_with_plex(123, principal(), context="browse"))
    assert result["title"] == "Example"
    assert result["plex"]["status"] == "unavailable"


def test_plex_request_protection_blocks_exact_identifier_only() -> None:
    fake_tmdb = AsyncMock()
    fake_tmdb.details.return_value = {"tmdb_id": 123, "title": "Example"}
    with patch.object(main, "configured_clients", return_value=(fake_tmdb, object(), object())), patch.object(
        plex_integration, "plex_library_state", AsyncMock(return_value={"available": True, "confidence": "exact_identifier"})
    ):
        with pytest.raises(main.HTTPException) as caught:
            asyncio.run(plex_integration.request_movie_with_plex(123, main.MovieRequestCreate(), principal()))
    assert caught.value.status_code == 409
    assert "Plex" in str(caught.value.detail)


def test_plex_routes_and_shared_ui_are_registered() -> None:
    paths = {route.path for route in plex_main.app.routes}
    assert "/api/setup/plex" in paths
    assert "/api/catalog/movies/{tmdb_id}" in paths
    assert "/api/downloads/{request_id}/details" in paths
    assert "Available in Plex" in main.INDEX_HTML
    assert "Watch in Plex" in main.INDEX_HTML
    assert "rel=\"noopener noreferrer\"" in main.INDEX_HTML


def test_plex_setup_requires_admin_route_dependency() -> None:
    route = next(route for route in plex_main.app.routes if route.path == "/api/setup/plex")
    dependant_names = {dependency.call.__name__ for dependency in route.dependant.dependencies if dependency.call}
    assert "administrator" in dependant_names
