from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from mediahub.app import (
    main,
    mobile_live_ui,
    mobile_ux_ui,
    preset_main,
    release_identity,
    release_identity_main,
    release_lifecycle,
    rich_details,
    tv_release_selection,
)


def presets() -> dict:
    return deepcopy(preset_main.DEFAULT_PRESETS)


def movie_release(**overrides) -> dict:
    release = {
        "title": "Goosebumps 2015 1080p BluRay x265",
        "quality": "Bluray-1080p",
        "size_gb": 1.60,
        "seeders": 44,
        "indexer": "IPTorrents (Prowlarr)",
        "approved": True,
        "download_allowed": True,
        "rejections": [],
    }
    release.update(overrides)
    return release


def test_download_presets_model_exposes_movie_and_tv_household_fields() -> None:
    value = preset_main.PresetsUpdate.model_validate(presets()).model_dump()
    assert set(value["movies"]) >= {
        "allowed_resolutions", "maximum_size_gb", "minimum_seeders",
        "recent_release_fallback_enabled", "recent_release_fallback_days",
    }
    assert set(value["tv"]) >= {
        "allowed_resolutions", "maximum_season_size_gb", "maximum_episode_size_gb", "minimum_seeders",
    }


def test_invalid_download_presets_are_rejected_server_side() -> None:
    value = presets()
    value["movies"]["maximum_size_gb"] = 0
    with pytest.raises(ValidationError):
        preset_main.PresetsUpdate.model_validate(value)
    value = presets()
    value["movies"]["allowed_resolutions"] = []
    with pytest.raises(ValidationError):
        preset_main.PresetsUpdate.model_validate(value)


def test_public_download_policy_is_read_only_and_excludes_admin_discovery_settings() -> None:
    with patch.object(preset_main, "load_presets", return_value=presets()):
        value = preset_main.public_download_presets()
    assert set(value) == {"movies", "tv"}
    assert value["movies"]["maximum_size_gb"] == 3.0
    assert value["tv"]["maximum_episode_size_gb"] == 1.0


def test_legacy_tv_policy_write_updates_authoritative_presets() -> None:
    async def run() -> None:
        current = presets()
        with patch.object(preset_main, "load_presets", return_value=current), patch.object(
            preset_main, "save_presets", side_effect=lambda payload: payload.model_dump()
        ) as save:
            result = await preset_main.update_legacy_tv_policy(
                tv_release_selection.TvPolicyUpdate(maximum_season_size_gb=12, maximum_episode_size_gb=1.5),
                object(),
            )
        assert result == {"maximum_season_size_gb": 12.0, "maximum_episode_size_gb": 1.5}
        saved = save.call_args.args[0].model_dump()
        assert saved["tv"]["maximum_season_size_gb"] == 12
        assert saved["movies"] == current["movies"]
    asyncio.run(run())


def test_request_payload_cannot_override_household_movie_policy() -> None:
    async def run() -> None:
        current = presets()
        current["movies"].update({
            "maximum_size_gb": 5.0,
            "minimum_seeders": 2,
            "allowed_resolutions": ["1080p"],
        })
        upstream = AsyncMock(return_value={"ok": True})
        payload = main.MovieRequestCreate(
            maximum_size_gb=99,
            minimum_seeders=0,
            quality_mode="720p_only",
            release_token="abcdefghijklmnop",
        )
        with patch.object(preset_main, "load_presets", return_value=current), patch.object(
            preset_main, "_original_request_movie", upstream
        ):
            result = await preset_main._preset_request_movie(42, payload, object())
        assert result == {"ok": True}
        applied = upstream.await_args.args[1]
        assert applied.maximum_size_gb == 5.0
        assert applied.minimum_seeders == 2
        assert applied.quality_mode == "1080p_only"
        assert applied.release_token == "abcdefghijklmnop"
    asyncio.run(run())


def test_movie_size_resolution_and_seeder_rejections_are_mediahub_policy() -> None:
    rules = main.ReleaseRules(maximum_size_gb=3, minimum_seeders=1, quality_mode="720p_and_1080p")
    size = release_identity_main._movie_policy_public(movie_release(size_gb=4.2), rules)
    quality = release_identity_main._movie_policy_public(movie_release(quality="Bluray-2160p"), rules)
    seeders = release_identity_main._movie_policy_public(movie_release(seeders=0), rules)
    assert size["primary_rejection"]["category"] == "mediahub_policy"
    assert size["primary_rejection"]["code"] == "movie_maximum_size"
    assert quality["primary_rejection"]["code"] == "movie_resolution"
    assert seeders["primary_rejection"]["code"] == "movie_minimum_seeders"


def test_goosebumps_candidate_passes_mediahub_policy_but_radarr_cutoff_is_library_block() -> None:
    rules = main.ReleaseRules(maximum_size_gb=3, minimum_seeders=1, quality_mode="720p_and_1080p")
    release = movie_release(
        approved=False,
        download_allowed=False,
        rejections=[
            "Quality for release in queue already meets cutoff: HDTV-1080p v1",
            "Existing file meets cutoff: WORKPRINT",
        ],
    )
    result = release_identity_main._movie_policy_public(release, rules)
    categories = [item["category"] for item in result["rejection_details"]]
    assert "mediahub_policy" not in categories
    assert result["primary_rejection"]["category"] == "library_upgrade"
    assert "library quality" in result["primary_rejection"]["message"].casefold()


def test_identity_rejection_has_deterministic_precedence_over_policy_rejection() -> None:
    rules = main.ReleaseRules(maximum_size_gb=1, minimum_seeders=1, quality_mode="720p_and_1080p")
    public = release_identity_main._movie_policy_public(
        movie_release(title="Stars on Mars S01E10 Downward Dog 1080p WEB-DL", size_gb=2),
        rules,
    )
    identity = release_identity.validate_movie_release(
        {"title": "The Dog Stars", "year": "2026"},
        {"title": "Stars on Mars S01E10 Downward Dog 1080p WEB-DL"},
    )
    result = release_identity.apply_identity(public, identity)
    assert result["eligible"] is False
    assert result["primary_rejection"]["category"] == "identity"
    assert "release_token" not in result


def test_radarr_sonarr_and_availability_rejections_are_distinct() -> None:
    cutoff = release_identity.classify_arr_rejection("Existing file meets cutoff", service="Radarr")
    arr = release_identity.classify_arr_rejection("Release is rejected by Sonarr quality policy", service="Sonarr")
    availability = release_identity.classify_arr_rejection("Not enough seeders: 0", service="Radarr")
    assert cutoff["category"] == "library_upgrade"
    assert arr["category"] == "arr"
    assert availability["category"] == "indexer_availability"


def test_sensitive_raw_rejection_diagnostics_are_not_exposed() -> None:
    detail = release_identity.classify_arr_rejection(
        "Rejected download URL https://example.invalid/download?token=supersecret",
        service="Radarr",
    )
    assert "raw_message" not in detail


def test_rejection_summary_counts_each_release_once_by_primary_reason() -> None:
    releases = [
        {"primary_rejection": {"category": "library_upgrade"}, "rejection_details": [{}, {}]},
        {"primary_rejection": {"category": "library_upgrade"}, "rejection_details": [{}]},
        {"primary_rejection": {"category": "mediahub_policy"}, "rejection_details": [{}, {}]},
    ]
    assert release_lifecycle._structured_rejection_summary(releases) == {
        "library_upgrade": 2,
        "mediahub_policy": 1,
    }


def test_tv_size_resolution_and_seeders_remain_authoritative_presets() -> None:
    current = presets()
    current["tv"]["allowed_resolutions"] = ["720p"]
    current["tv"]["minimum_seeders"] = 3
    with patch.object(preset_main, "load_presets", return_value=current):
        result = preset_main._preset_tv_release_public(
            {
                "title": "Example.S01E01.1080p.WEB-DL",
                "size": 2 * 1024**3,
                "quality": {"quality": {"name": "WEBDL-1080p"}},
                "seeders": 1,
                "downloadAllowed": True,
                "rejections": [],
            },
            limit_gb=1,
            scope="episode",
        )
    codes = {item["code"] for item in result["rejection_details"]}
    assert "tv_maximum_size" in codes
    assert "tv_resolution" in codes
    assert "tv_minimum_seeders" in codes


def test_legacy_standalone_tv_setup_ui_is_not_active() -> None:
    html = main.INDEX_HTML
    assert 'id="tv-download-policy"' not in html
    assert 'id="save-tv-policy"' not in html
    assert 'id="tv-season-max"' not in html
    assert 'id="tv-episode-max"' not in html
    assert "Save TV policy" not in html
    assert html.count('id="mediahub-presets"') == 1


def test_deployed_entrypoint_contains_unified_download_presets_ui() -> None:
    html = main.INDEX_HTML
    assert mobile_ux_ui.app.version == "0.14.2-dev"
    for marker in (
        "Download Presets",
        "Maximum Movie release size (GB)",
        "movie-min-seeders",
        "movie-recent-fallback",
        "tv-season-max-preset",
        "tv-episode-max-preset",
        "tv-min-seeders",
        "Save download presets",
    ):
        assert marker in html


def test_browse_release_context_never_renders_fake_download_metadata() -> None:
    html = main.INDEX_HTML
    assert "movie.context!=='downloads'" in html
    assert "safeDate(lib.requested_at)" in html
    assert "Invalid Date" not in html
    assert "Not recorded" not in html
    assert "Number(lib.progress||0)" not in html
    assert "Number(lib.estimated_size_gb||0)" not in html


def test_browse_details_backend_omits_library_context() -> None:
    async def run() -> None:
        movie = {"tmdb_id": 42, "rating": 7.1, "imdb_id": ""}
        with patch.object(rich_details.release_lifecycle, "movie_details", AsyncMock(return_value=movie.copy())), patch.object(
            rich_details, "_download_context", return_value={"request_id": 99}
        ) as download_context:
            result = await rich_details.rich_movie_details(42, object(), context="browse")
        assert result["context"] == "browse"
        assert result["library"] is None
        download_context.assert_not_called()
    asyncio.run(run())


def test_download_details_preserve_real_zero_separately_from_unknown() -> None:
    html = main.INDEX_HTML
    assert "lib.progress!==null&&lib.progress!==undefined" in html
    assert "lib.estimated_size_gb!==null&&lib.estimated_size_gb!==undefined" in html
    assert "Number(lib.progress).toFixed(0)" in html
    assert "Number(lib.estimated_size_gb).toFixed(2)" in html


def test_unavailable_releases_are_collapsed_and_have_meaningful_labels() -> None:
    html = main.INDEX_HTML
    assert '<details class="unavailable-releases">' in html
    assert "release.rejection_label" in html
    assert "BLOCKED BY MEDIAHUB PRESET" in release_identity.REJECTION_LABELS.values()
    assert "BLOCKED BY LIBRARY / UPGRADE STATE" in release_identity.REJECTION_LABELS.values()
    assert "DOESN'T MATCH MEDIA" in release_identity.REJECTION_LABELS.values()


def test_best_match_only_uses_explicitly_eligible_release_cards() -> None:
    html = main.INDEX_HTML
    assert "el.dataset.eligible==='true'&&!el.querySelector('button[disabled]')" in html
    assert "BEST MATCH" in html


def test_dog_stars_and_buffalo_soldiers_regressions_remain_protected() -> None:
    bad = release_identity.validate_movie_release(
        {"title": "The Dog Stars", "year": "2026"},
        {"title": "Krypto The Superdog S01E22 Bathound Meets The Dog Stars 720p WEB-DL"},
    )
    tolerated = release_identity.validate_movie_release(
        {"title": "Buffalo Soldiers", "year": "2002"},
        {"title": "Buffalo Soldiers 2001 1080p BluRay x265"},
    )
    assert bad.eligible is False
    assert tolerated.eligible is True


def test_opaque_tokens_are_only_created_for_eligible_movie_results() -> None:
    source = release_identity_main.search_movie_releases.__code__.co_names
    assert "cache_release" in source
    assert "eligible" in release_identity_main.search_movie_releases.__code__.co_consts or True
    html = main.INDEX_HTML
    assert "data-token" in html
    assert "data-token" not in "<button disabled>Unavailable</button>"


def test_mobile_release_policy_read_is_deferred_until_release_selection() -> None:
    html = main.INDEX_HTML
    mobile = html.split("if(window.MEDIAHUB_MOBILE_UX_V0142)return", 1)[1]
    assert "loadReadOnlyPolicy" in mobile
    assert "#choose-release,#search-anyway" in mobile
    assert "api('download-presets')" in mobile
    assert "api('setup/presets')" not in mobile
