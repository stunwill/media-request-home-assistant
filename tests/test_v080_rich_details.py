from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from mediahub.app import main, rich_details
from mediahub.app.media_services import TmdbClient


def headers() -> dict[str, str]:
    return {
        "X-Remote-User-Id": "ha-admin",
        "X-Remote-User-Name": "stu",
        "X-Remote-User-Display-Name": "Stu",
    }


def test_rating_cards_are_source_labelled_and_safe() -> None:
    movie = {"tmdb_id": 123, "rating": 7.4, "imdb_id": "tt1234567"}
    ratings = rich_details._rating_cards(movie)
    assert ratings[0]["source"] == "TMDb"
    assert ratings[0]["value"] == "7.4 / 10"
    assert ratings[1]["source"] == "IMDb"
    assert ratings[1]["external_only"] is True
    assert "secret" not in str(ratings)


def test_rating_cards_omit_unavailable_sources() -> None:
    assert rich_details._rating_cards({"tmdb_id": 1, "rating": 0, "imdb_id": ""}) == []


async def test_tmdb_details_retains_actor_ids_profiles_director_and_certification() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/movie/123"
        return httpx.Response(
            200,
            json={
                "id": 123,
                "title": "Example",
                "release_date": "2026-08-01",
                "vote_average": 7.4,
                "credits": {
                    "cast": [
                        {
                            "id": 99,
                            "name": "Example Actor",
                            "character": "Hero",
                            "profile_path": "/actor.jpg",
                        }
                    ],
                    "crew": [{"id": 77, "name": "Example Director", "job": "Director"}],
                },
                "videos": {"results": []},
                "external_ids": {"imdb_id": "tt1234567"},
                "release_dates": {
                    "results": [
                        {
                            "iso_3166_1": "AU",
                            "release_dates": [
                                {
                                    "type": 3,
                                    "release_date": "2026-08-01T00:00:00Z",
                                    "certification": "M",
                                }
                            ],
                        }
                    ]
                },
            },
        )

    client = TmdbClient("secret", transport=httpx.MockTransport(handler))
    movie = await client.details(123)
    assert movie["cast"][0]["id"] == 99
    assert movie["cast"][0]["profile_url"].endswith("/actor.jpg")
    assert movie["director"] == {"id": 77, "name": "Example Director"}
    assert movie["certification"] == "M"
    assert movie["imdb_id"] == "tt1234567"


async def test_actor_id_discovery_uses_tmdb_person_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/3/discover/movie"
        assert request.url.params["with_cast"] == "99"
        return httpx.Response(
            200,
            json={
                "page": 1,
                "total_pages": 1,
                "total_results": 1,
                "results": [{"id": 123, "title": "Example", "release_date": "2026-08-01"}],
            },
        )

    client = TmdbClient("secret", transport=httpx.MockTransport(handler))
    result = await client.actor_movies(99)
    assert result["person_id"] == 99
    assert result["search_mode"] == "actor_id"
    assert result["movies"][0]["tmdb_id"] == 123


def test_rich_details_ui_has_shared_cast_ratings_and_download_context() -> None:
    html = main.INDEX_HTML
    assert "Ratings & reviews" in html
    assert "data-person-id" in html
    assert "Download & library" in html
    assert "downloads/${item.id}/details" in html
    assert "if(!downloads)" in html
    assert 'rel="noopener noreferrer"' in html


def test_download_detail_api_hides_request_actions_in_download_context() -> None:
    assert "const downloads=movie.context==='downloads'" in main.INDEX_HTML
    assert "if(!downloads)" in main.INDEX_HTML


def test_download_detail_lookup_returns_library_context() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        database = Path(tmp) / "mediahub.db"
        with patch.object(main, "DATABASE_FILE", database):
            main.initialise_database()
            with main.connect_db() as db:
                db.execute(
                    """
                    INSERT INTO requests (
                        media_type,title,external_id,requested_by_id,requested_by_name,
                        estimated_size_gb,reserved_size_gb,status,progress,status_message,
                        selected_release_title,created_at,updated_at
                    ) VALUES ('movie','Example','123','ha-admin','Stu',2.1,0,'available',100,
                              'Available in the media library','Example.1080p.WEB-DL',
                              '2026-08-20T10:00:00+00:00','2026-08-21T10:00:00+00:00')
                    """
                )
                db.commit()
            principal = main.Principal(
                user_id="ha-admin",
                username="stu",
                display_name="Stu",
                role="admin",
                active=True,
            )
            context = rich_details._download_context(123, principal)
            assert context is not None
            assert context["status"] == "available"
            assert context["selected_release_title"] == "Example.1080p.WEB-DL"


def test_rich_detail_routes_are_registered() -> None:
    paths = {route.path for route in rich_details.app.routes}
    assert "/api/catalog/people/{person_id}/movies" in paths
    assert "/api/downloads/{request_id}/details" in paths


def test_rich_movie_details_keeps_release_lifecycle() -> None:
    movie = {
        "tmdb_id": 123,
        "title": "Example",
        "rating": 7.4,
        "lifecycle": {"state": "digital_available"},
    }
    with patch.object(rich_details.release_lifecycle, "movie_details", AsyncMock(return_value=movie.copy())):
        principal = main.Principal(
            user_id="ha-admin",
            username="stu",
            display_name="Stu",
            role="admin",
            active=True,
        )
        import asyncio

        result = asyncio.run(rich_details.rich_movie_details(123, principal, context="browse"))
    assert result["lifecycle"]["state"] == "digital_available"
    assert result["context"] == "browse"
