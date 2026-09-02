from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from mediahub.app import main, settings, tv_release_selection
from mediahub.app.auth import Principal
from mediahub.app.tv_services import SonarrClient


def principal(role: str = "admin") -> Principal:
    return Principal(user_id="user-1", username="user", display_name="User", role=role, active=True)


def test_default_tv_policy() -> None:
    assert settings.DEFAULT_OPTIONS["tv_downloads"]["maximum_season_size_gb"] == 10.0
    assert settings.DEFAULT_OPTIONS["tv_downloads"]["maximum_episode_size_gb"] == 1.0


def test_save_tv_policy_validation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "settings.json"
        saved = settings.save_tv_download_settings(maximum_season_size_gb=9.5, maximum_episode_size_gb=0.8, settings_file=path)
        assert saved == {"maximum_season_size_gb": 9.5, "maximum_episode_size_gb": 0.8}
        with pytest.raises(ValueError):
            settings.save_tv_download_settings(maximum_season_size_gb=0, maximum_episode_size_gb=1, settings_file=path)


def test_size_policy_exact_limit_and_rejection() -> None:
    gib = 1024 ** 3
    at_limit = tv_release_selection._release_public(
        {"title": "Show.S01.1080p.WEB-DL.x265", "size": 10 * gib, "quality": {"quality": {"name": "WEBDL-1080p"}}, "downloadAllowed": True},
        limit_gb=10,
        scope="season",
    )
    over = tv_release_selection._release_public(
        {"title": "Show.S01.1080p.WEB-DL.x265", "size": 10 * gib + 1, "quality": {"quality": {"name": "WEBDL-1080p"}}, "downloadAllowed": True},
        limit_gb=10,
        scope="season",
    )
    assert at_limit["eligible"] is True
    assert over["eligible"] is False
    assert any("10 GB" in reason for reason in over["policy_rejections"])


def test_release_metadata_parsing() -> None:
    item = tv_release_selection._release_public(
        {"title": "Example.S02E04.1080p.WEB-DL.x265", "size": 700 * 1024 ** 2, "quality": {"quality": {"name": "WEBDL-1080p"}}, "seeders": 12, "indexer": "IPT", "downloadAllowed": True},
        limit_gb=1,
        scope="episode",
    )
    assert item["source"] == "WEB-DL"
    assert item["codec"] == "x265/HEVC"
    assert item["seeders"] == 12
    assert item["eligible"] is True


def test_opaque_tv_release_token_is_single_use() -> None:
    token = tv_release_selection._cache_release(user_id="u", series_id=1, season_number=2, episode_id=3, release={"guid": "secret-guid"})
    assert "secret-guid" not in token
    series_id, season, episode, release = tv_release_selection._consume_release(token, user_id="u")
    assert (series_id, season, episode) == (1, 2, 3)
    assert release["guid"] == "secret-guid"
    with pytest.raises(HTTPException):
        tv_release_selection._consume_release(token, user_id="u")


def test_episode_status_available_downloading_unaired_missing() -> None:
    assert tv_release_selection._episode_status({"id": 1, "hasFile": True}, set()) == "available"
    assert tv_release_selection._episode_status({"id": 2, "hasFile": False}, {2}) == "downloading"
    assert tv_release_selection._episode_status({"id": 3, "hasFile": False, "airDateUtc": "2999-01-01T00:00:00Z"}, set()) == "unaired"
    assert tv_release_selection._episode_status({"id": 4, "hasFile": False}, set()) == "missing"


def test_sonarr_interactive_release_endpoints_and_grab() -> None:
    seen: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/api/v3/release":
            return httpx.Response(200, json=[{"title": "Release", "guid": "g", "indexerId": 9}])
        if request.method == "POST" and request.url.path == "/api/v3/release":
            body = __import__("json").loads(request.content)
            assert body == {"guid": "g", "indexerId": 9}
            return httpx.Response(200, json={})
        raise AssertionError(request.url)

    async def run() -> None:
        client = SonarrClient("http://sonarr", "secret", transport=httpx.MockTransport(handler))
        season = await client.season_releases(5, 2)
        episode = await client.episode_releases(42)
        await client.grab_release("g", 9)
        assert season[0]["title"] == "Release"
        assert episode[0]["title"] == "Release"

    asyncio.run(run())
    assert seen.count(("GET", "/api/v3/release")) == 2
    assert ("POST", "/api/v3/release") in seen


def test_v011_routes_and_version_registered() -> None:
    assert tv_release_selection.app.version == "0.11.0-dev"
    paths = {route.path for route in tv_release_selection.app.routes}
    for path in {
        "/api/catalog/tv/{tmdb_id}/seasons/{season_number}",
        "/api/catalog/tv/{tmdb_id}/seasons/{season_number}/releases",
        "/api/catalog/tv/{tmdb_id}/seasons/{season_number}/episodes/{episode_number}/releases",
        "/api/tv/releases/grab",
        "/api/setup/tv-downloads",
    }:
        assert path in paths


def test_release_ui_prefers_season_and_hides_completed_episode_action() -> None:
    from mediahub.app import main as main_module
    from mediahub.app import tv_release_ui  # noqa: F401

    html = main_module.INDEX_HTML
    assert "View season" in html
    assert "Request entire series (advanced)" in html
    assert "Find season packs" in html
    assert "Find releases" in html
    assert "ep.status==='missing'" in html
    assert "tv/releases/grab" in html


def test_movie_and_catalogue_regression_markers_remain() -> None:
    from mediahub.app import main as main_module
    from mediahub.app import tv_release_ui  # noqa: F401

    html = main_module.INDEX_HTML
    assert "IntersectionObserver" in html
    assert "MEDIAHUB_INFINITE_CATALOGUE" in html
    assert "Request best release" in html
    assert "Choose a release" in html


def test_public_release_never_exposes_download_url() -> None:
    public = tv_release_selection._release_public(
        {"title": "Show.S01E01.720p.WEBRip", "size": 500 * 1024 ** 2, "quality": {"quality": {"name": "WEBRip-720p"}}, "downloadAllowed": True, "downloadUrl": "https://tracker/private", "guid": "secret"},
        limit_gb=1,
        scope="episode",
    )
    assert "downloadUrl" not in public
    assert "guid" not in public
