from pathlib import Path

from mediahub.app import main, watchlist_main


def test_watchlist_availability_states():
    assert watchlist_main._availability("theatrical_upcoming", found=False) == "upcoming"
    assert watchlist_main._availability("in_cinemas", found=False) == "waiting"
    assert watchlist_main._availability("digital_available", found=False) == "no_eligible_release"
    assert watchlist_main._availability("digital_available", found=True) == "available"
    assert watchlist_main._availability("digital_available", found=True, request_status="downloading") == "downloading"
    assert watchlist_main._availability("digital_available", found=True, request_status="available") == "downloaded"


def test_watchlist_schema_migrates_existing_database(tmp_path, monkeypatch):
    database = tmp_path / "mediahub.db"
    monkeypatch.setattr(main, "DATABASE_FILE", database)
    watchlist_main.initialise_watchlist_database()
    with main.connect_db() as db:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(movie_watches)")}
    assert {"poster_path", "availability_state", "first_available_at", "notification_sent_at"} <= columns


def test_watchlist_routes_are_registered():
    routes = {(getattr(route, "path", ""), tuple(sorted(getattr(route, "methods", set())))) for route in watchlist_main.app.routes}
    assert ("/api/watchlist", ("GET",)) in routes
    assert ("/api/watchlist/{tmdb_id}", ("DELETE",)) in routes
    assert ("/api/watchlist/{tmdb_id}/refresh", ("POST",)) in routes


def test_watchlist_ui_and_mobile_contract_present():
    html = main.INDEX_HTML
    assert "MEDIAHUB_WATCHLIST_V0150" in html
    assert "Add to Watchlist" in html
    assert "Check now" in html
    assert "data-watch-filter=\"upcoming\"" in html
    assert "data-watch-filter=\"available\"" in html
    assert "watchlist-grid" in html


def test_deployed_entrypoint_is_watchlist():
    run = Path("mediahub/run.sh").read_text()
    assert run.count("app.watchlist_main:app") == 2
    config = Path("mediahub/config.yaml").read_text()
    assert 'version: "0.16.4-dev"' in config


def test_ambiguous_titles_remain_identity_validated():
    # Watchlist monitoring deliberately reuses runtime.search_movie_releases, which is
    # patched by release_identity_main before watchlist_main is imported. This guards
    # short titles such as "Below" and same-title/different-year releases.
    source = Path("mediahub/app/watchlist_main.py").read_text()
    assert "runtime.search_movie_releases" in source
    assert "preset_main.movie_rules()" in source
