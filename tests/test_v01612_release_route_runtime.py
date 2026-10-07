from pathlib import Path


def test_movie_release_route_is_rebound_after_runtime_discovery_patch() -> None:
    source = Path("mediahub/app/runtime.py").read_text()

    assignment = source.index("enhanced_main.search_movie_releases = search_movie_releases")
    route_fix = source.index('getattr(route, "path", None) == "/api/movies/{tmdb_id}/releases"')
    assert route_fix > assignment
    assert "route.endpoint = enhanced_main.movie_releases" in source
    assert "route.dependant.call = enhanced_main.movie_releases" in source


def test_direct_prowlarr_fallback_retains_hard_deadline() -> None:
    source = Path("mediahub/app/runtime.py").read_text()
    assert "async with asyncio.timeout(18):" in source
    assert "raw_results = await prowlarr_task" in source


def test_direct_prowlarr_download_preserves_exact_selected_release() -> None:
    source = Path("mediahub/app/runtime.py").read_text()

    request = source[source.index("async def request_movie("):]
    assert 'str(cached[3].get("source") or "") != "prowlarr_direct"' in request
    assert 'guid = str(selected.get("guid") or "")' in request
    assert 'indexer_id = int(selected.get("indexer_id") or 0)' in request
    assert 'radarr.grab(guid=guid, indexer_id=indexer_id)' in request
    assert 'automatic_payload = payload.model_copy(update={"release_token": None})' not in request
    assert '_selected_prowlarr_release[selection_key] = preferred' not in request


def test_direct_prowlarr_download_does_not_require_fresh_radarr_release_match() -> None:
    source = Path("mediahub/app/runtime.py").read_text()
    request = source[source.index("async def request_movie("):source.index("# Keep the public modules consistent.")]

    assert "radarr.releases(" not in request
    assert "The selected release is no longer available. Search again." not in request
    assert '"release_source": "prowlarr_direct"' in request
