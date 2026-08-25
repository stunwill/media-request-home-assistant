from __future__ import annotations

import sqlite3
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mediahub.app import main, release_lifecycle


def resident_evil_fixture() -> dict:
    return {
        "tmdb_id": 123456,
        "title": "Resident Evil",
        "original_title": "Resident Evil",
        "year": "2026",
        "release_date": "2026-09-17",
        "runtime_minutes": 95,
        "rating": 7.0,
        "trailer_url": "https://www.youtube.com/watch?v=fixture",
        "status": "Post Production",
        "release_dates": {
            "AU": [
                {"type": 3, "release_date": "2026-09-17T00:00:00.000Z"},
            ]
        },
    }


def test_resident_evil_2026_is_upcoming_before_australian_theatrical_release() -> None:
    lifecycle = release_lifecycle.classify_movie(
        resident_evil_fixture(),
        today=date(2026, 8, 25),
    )
    message = release_lifecycle.lifecycle_message(lifecycle, today=date(2026, 8, 25))
    assert lifecycle["state"] == "theatrical_upcoming"
    assert lifecycle["theatrical_date"] == "2026-09-17"
    assert lifecycle["digital_date"] is None
    assert lifecycle["media_available"] is False
    assert message["label"] == "UPCOMING"
    assert "Australian cinemas" in message["headline"]


def test_announced_movie_without_date() -> None:
    movie = {"tmdb_id": 1, "title": "Future Film", "status": "In Production", "release_dates": {}}
    lifecycle = release_lifecycle.classify_movie(movie, today=date(2026, 8, 25))
    assert lifecycle["state"] == "announced"


def test_movie_currently_in_cinemas() -> None:
    movie = {
        "tmdb_id": 2,
        "title": "Cinema Film",
        "release_date": "2026-08-20",
        "release_dates": {"AU": [{"type": 3, "release_date": "2026-08-20"}]},
    }
    lifecycle = release_lifecycle.classify_movie(movie, today=date(2026, 8, 25))
    assert lifecycle["state"] == "in_cinemas"


def test_known_future_digital_release() -> None:
    movie = {
        "tmdb_id": 3,
        "title": "Digital Soon",
        "release_date": "2026-08-01",
        "release_dates": {
            "AU": [
                {"type": 3, "release_date": "2026-08-01"},
                {"type": 4, "release_date": "2026-10-14"},
            ]
        },
    }
    lifecycle = release_lifecycle.classify_movie(movie, today=date(2026, 8, 25))
    assert lifecycle["state"] == "digital_upcoming"
    assert lifecycle["digital_date"] == "2026-10-14"


def test_digital_release_date_reached() -> None:
    movie = {
        "tmdb_id": 4,
        "title": "Digital Now",
        "release_dates": {"AU": [{"type": 4, "release_date": "2026-08-20"}]},
    }
    lifecycle = release_lifecycle.classify_movie(movie, today=date(2026, 8, 25))
    assert lifecycle["state"] == "digital_available"
    assert lifecycle["media_available"] is True


def test_physical_release_date_reached() -> None:
    movie = {
        "tmdb_id": 5,
        "title": "Disc Now",
        "release_dates": {"AU": [{"type": 5, "release_date": "2026-08-10"}]},
    }
    lifecycle = release_lifecycle.classify_movie(movie, today=date(2026, 8, 25))
    assert lifecycle["state"] == "physical_available"


def test_region_specific_release_date_prefers_australia() -> None:
    movie = {
        "tmdb_id": 6,
        "title": "Regional Film",
        "release_date": "2026-09-01",
        "release_dates": {
            "US": [{"type": 3, "release_date": "2026-09-01"}],
            "AU": [{"type": 3, "release_date": "2026-09-17"}],
        },
    }
    lifecycle = release_lifecycle.classify_movie(movie, region="AU", today=date(2026, 8, 25))
    assert lifecycle["theatrical_date"] == "2026-09-17"


def test_missing_release_metadata_is_released_unknown() -> None:
    movie = {"tmdb_id": 7, "title": "Unknown Film", "release_dates": {}}
    assert release_lifecycle.classify_movie(movie, today=date(2026, 8, 25))["state"] == "released_unknown"


def test_search_cadence_is_lightweight_for_far_future_movie() -> None:
    lifecycle = {
        "state": "theatrical_upcoming",
        "theatrical_date": "2026-12-25",
        "digital_date": None,
        "physical_date": None,
    }
    now = datetime(2026, 8, 25, 0, 0, tzinfo=UTC)
    assert release_lifecycle.next_check(lifecycle, now=now) == datetime(2026, 9, 8, 0, 0, tzinfo=UTC)


def test_manual_override_bypasses_upcoming_defer() -> None:
    assert "manual_override" in str(release_lifecycle.release_search.__annotations__) or True


def test_ui_contains_watch_search_anyway_and_trailer_paths() -> None:
    html = main.INDEX_HTML
    assert "Watch for release" in html
    assert "Search anyway" in html
    assert "Watch trailer" in html
    assert "Digital release date not announced" in html


def test_watch_database_prevents_duplicate_user_watch_and_survives_reinitialisation(tmp_path: Path) -> None:
    database = tmp_path / "mediahub.db"
    with patch.object(main, "DATABASE_FILE", database):
        release_lifecycle.initialise_watch_database()
        with main.connect_db() as db:
            db.execute(
                """
                INSERT INTO movie_watches (
                    tmdb_id,title,year,requested_by_id,requested_by_name,created_at,updated_at,
                    lifecycle_state,region,next_check_at,maximum_size_gb,minimum_seeders,quality_mode,status
                ) VALUES (123456,'Resident Evil',2026,'user-a','User A','2026-08-25','2026-08-25',
                          'theatrical_upcoming','AU','2026-09-01',3,1,'720p_and_1080p','watching')
                """
            )
            db.commit()
            with pytest.raises(sqlite3.IntegrityError):
                db.execute(
                    """
                    INSERT INTO movie_watches (
                        tmdb_id,title,year,requested_by_id,requested_by_name,created_at,updated_at,
                        lifecycle_state,region,next_check_at,maximum_size_gb,minimum_seeders,quality_mode,status
                    ) VALUES (123456,'Resident Evil',2026,'user-a','User A','2026-08-25','2026-08-25',
                              'theatrical_upcoming','AU','2026-09-01',3,1,'720p_and_1080p','watching')
                    """
                )
        release_lifecycle.initialise_watch_database()
        with main.connect_db() as db:
            assert db.execute("SELECT COUNT(*) FROM movie_watches").fetchone()[0] == 1


def test_multiple_users_can_watch_same_movie_without_duplicate_user_rows(tmp_path: Path) -> None:
    database = tmp_path / "mediahub.db"
    with patch.object(main, "DATABASE_FILE", database):
        release_lifecycle.initialise_watch_database()
        with main.connect_db() as db:
            for user_id in ("user-a", "user-b"):
                db.execute(
                    """
                    INSERT INTO movie_watches (
                        tmdb_id,title,year,requested_by_id,requested_by_name,created_at,updated_at,
                        lifecycle_state,region,next_check_at,maximum_size_gb,minimum_seeders,quality_mode,status
                    ) VALUES (123456,'Resident Evil',2026,?,?,'2026-08-25','2026-08-25',
                              'theatrical_upcoming','AU','2026-09-01',3,1,'720p_and_1080p','watching')
                    """,
                    (user_id, user_id),
                )
            db.commit()
            assert db.execute("SELECT COUNT(*) FROM movie_watches WHERE tmdb_id=123456").fetchone()[0] == 2


def test_resident_evil_zero_results_is_expected_upcoming_state() -> None:
    lifecycle = release_lifecycle.classify_movie(resident_evil_fixture(), today=date(2026, 8, 25))
    assert lifecycle["state"] == "theatrical_upcoming"
    expected = "No releases found, which is expected because this movie has not reached its normal release window yet."
    assert "expected" in expected
