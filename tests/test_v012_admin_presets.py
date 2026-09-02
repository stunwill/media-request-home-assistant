from __future__ import annotations

import asyncio
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx

from mediahub.app import main, media_services, preset_main, preset_ui, settings, tv_release_selection, tv_services


def defaults() -> dict:
    return deepcopy(preset_main.DEFAULT_PRESETS)


def test_default_presets_match_existing_mediahub_policy() -> None:
    with patch.object(main, "load_options", return_value={"tv_downloads": {}}):
        value = preset_main.load_presets()
    assert value["discovery"]["original_language"] == "en"
    assert value["movies"]["allowed_resolutions"] == ["1080p", "720p"]
    assert value["movies"]["maximum_size_gb"] == 3.0
    assert value["movies"]["minimum_seeders"] == 1
    assert value["movies"]["recent_release_fallback_enabled"] is True
    assert value["movies"]["recent_release_fallback_days"] == 365
    assert value["tv"]["allowed_resolutions"] == ["1080p", "720p"]
    assert value["tv"]["maximum_season_size_gb"] == 10.0
    assert value["tv"]["maximum_episode_size_gb"] == 1.0
    assert value["tv"]["minimum_seeders"] == 1


def test_v011_tv_sizes_are_upgrade_source_until_presets_saved() -> None:
    with patch.object(main, "load_options", return_value={"tv_downloads": {"maximum_season_size_gb": 8, "maximum_episode_size_gb": 0.8}}):
        value = preset_main.load_presets()
    assert value["tv"]["maximum_season_size_gb"] == 8
    assert value["tv"]["maximum_episode_size_gb"] == 0.8


def test_save_presets_persists_and_keeps_legacy_tv_sizes_in_sync() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mediahub-settings.json"
        payload = preset_main.PresetsUpdate.model_validate({
            "discovery": {"original_language": "all"},
            "movies": {
                "allowed_resolutions": ["1080p"],
                "maximum_size_gb": 2.5,
                "minimum_seeders": 3,
                "recent_release_fallback_enabled": False,
                "recent_release_fallback_days": 180,
            },
            "tv": {
                "allowed_resolutions": ["720p"],
                "maximum_season_size_gb": 9,
                "maximum_episode_size_gb": 0.75,
                "minimum_seeders": 2,
            },
        })
        with patch.object(settings, "SETTINGS_FILE", path):
            saved = preset_main.save_presets(payload)
            stored = settings._read_json(path)
        assert saved["movies"]["maximum_size_gb"] == 2.5
        assert stored["presets"]["discovery"]["original_language"] == "all"
        assert stored["tv_downloads"] == {"maximum_season_size_gb": 9.0, "maximum_episode_size_gb": 0.75}
        assert path.stat().st_mode & 0o777 == 0o600


def test_reset_presets_restores_safe_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "mediahub-settings.json"
        settings._atomic_write({"presets": {"discovery": {"original_language": "all"}}}, path)
        with patch.object(settings, "SETTINGS_FILE", path):
            reset = preset_main.reset_presets()
            stored = settings._read_json(path)
        assert reset == preset_main.DEFAULT_PRESETS
        assert stored["presets"] == preset_main.DEFAULT_PRESETS
        assert stored["tv_downloads"]["maximum_season_size_gb"] == 10.0


def test_movie_policy_uses_admin_preset_not_request_override() -> None:
    value = defaults()
    value["movies"]["maximum_size_gb"] = 3.0
    value["movies"]["allowed_resolutions"] = ["1080p"]
    with patch.object(preset_main, "load_presets", return_value=value):
        result = main.release_with_policy(
            {"title": "Too large", "quality": "WEBDL-1080p", "size_gb": 4.0, "seeders": 20, "approved": True, "download_allowed": True, "rejections": []},
            main.ReleaseRules(maximum_size_gb=99, minimum_seeders=0),
        )
    assert result["eligible"] is False
    assert any("3 GB" in reason for reason in result["policy_rejections"])


def test_tv_policy_enforces_admin_resolution_and_seeders() -> None:
    value = defaults()
    value["tv"]["allowed_resolutions"] = ["720p"]
    value["tv"]["minimum_seeders"] = 5
    with patch.object(preset_main, "load_presets", return_value=value):
        result = tv_release_selection._release_public(
            {
                "title": "Example.S01E01.1080p.WEB-DL.x265",
                "size": 600 * 1024 * 1024,
                "quality": {"quality": {"name": "WEBDL-1080p"}},
                "seeders": 2,
                "downloadAllowed": True,
                "rejections": [],
            },
            limit_gb=1,
            scope="episode",
        )
    assert result["eligible"] is False
    assert "Release resolution is not enabled in MediaHub Presets" in result["policy_rejections"]
    assert "Release has fewer than 5 seeders" in result["policy_rejections"]


def test_recent_release_fallback_can_be_disabled() -> None:
    value = defaults()
    value["movies"]["recent_release_fallback_enabled"] = False
    with patch.object(preset_main, "load_presets", return_value=value):
        assert preset_main._preset_is_recent_movie({"release_date": "2026-08-01"}) is False


def test_catalogue_language_can_be_changed_from_english_to_all() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"page": 1, "total_pages": 1, "total_results": 2, "results": [
                {"id": 1, "title": "English", "original_language": "en"},
                {"id": 2, "title": "Français", "original_language": "fr"},
            ]})
        client = media_services.TmdbClient("secret", transport=httpx.MockTransport(handler))
        all_languages = defaults(); all_languages["discovery"]["original_language"] = "all"
        with patch.object(preset_main, "load_presets", return_value=all_languages):
            result = await client.catalogue(query="film")
        assert {item["tmdb_id"] for item in result["movies"]} == {1, 2}
        english = defaults()
        with patch.object(preset_main, "load_presets", return_value=english):
            result = await client.catalogue(query="film")
        assert [item["tmdb_id"] for item in result["movies"]] == [1]
    asyncio.run(run())


def test_tv_catalogue_language_uses_same_household_preset() -> None:
    async def run() -> None:
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"page": 1, "total_pages": 1, "total_results": 2, "results": [
                {"id": 10, "name": "English Show", "original_language": "en"},
                {"id": 11, "name": "한국 드라마", "original_language": "ko"},
            ]})
        client = tv_services.TmdbTvClient("secret", transport=httpx.MockTransport(handler))
        english = defaults()
        with patch.object(preset_main, "load_presets", return_value=english):
            result = await client.catalogue(query="show")
        assert [item["tmdb_id"] for item in result["shows"]] == [10]
    asyncio.run(run())


def test_presets_routes_are_admin_dependencies() -> None:
    routes = [route for route in preset_ui.app.routes if route.path.startswith("/api/setup/presets")]
    assert {route.path for route in routes} == {"/api/setup/presets", "/api/setup/presets/reset"}
    assert {method for route in routes for method in route.methods} >= {"GET", "PUT", "POST"}
    for route in routes:
        dependency_names = {getattr(dep.call, "__name__", "") for dep in route.dependant.dependencies}
        assert "administrator" in dependency_names


def test_setup_is_split_into_service_connections_and_presets() -> None:
    html = main.INDEX_HTML
    assert "Service Connections" in html
    assert "Search & Download Presets" in html
    assert "Catalogue language" in html
    assert "English only" in html
    assert "Maximum movie size (GB)" in html
    assert "Maximum season pack (GB)" in html
    assert "Maximum episode (GB)" in html
    assert "Reset to defaults" in html
    assert "Admin only" in html
    assert "Household Movie download presets from Setup are applied automatically" in html


def test_v012_version_and_routes_registered() -> None:
    assert preset_ui.app.version == "0.12.0-dev"
    paths = {route.path for route in preset_ui.app.routes}
    assert "/api/setup/presets" in paths
    assert "/api/setup/presets/reset" in paths
    assert "/api/tv/releases/grab" in paths
    assert "/api/movies/{tmdb_id}/releases" in paths
    assert "/api/setup/plex" in paths
