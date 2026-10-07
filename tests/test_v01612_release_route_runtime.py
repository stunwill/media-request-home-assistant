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
