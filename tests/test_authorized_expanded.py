from datetime import date

from mediahub.app import authorized_expanded


def test_recent_movie_is_eligible_for_expanded_options():
    movie = {"release_date": "2026-02-23"}
    assert authorized_expanded.released_within_last_12_months(
        movie,
        today=date(2026, 8, 22),
    )


def test_future_movie_is_not_eligible_for_expanded_options():
    movie = {"release_date": "2026-12-01"}
    assert not authorized_expanded.released_within_last_12_months(
        movie,
        today=date(2026, 8, 22),
    )


def test_movie_older_than_365_days_is_not_eligible():
    movie = {"release_date": "2025-08-21"}
    assert not authorized_expanded.released_within_last_12_months(
        movie,
        today=date(2026, 8, 22),
    )


def test_expanded_policy_requires_authorized_source():
    result = authorized_expanded._expanded_policy(
        {"title": "Example", "size_gb": 2.5, "source_type": "external"}
    )
    assert not result["eligible"]
    assert "authorized or user-owned" in result["policy_rejections"][0]


def test_expanded_policy_allows_larger_authorized_file():
    result = authorized_expanded._expanded_policy(
        {
            "title": "Example",
            "size_gb": 7.5,
            "source_type": "user_owned",
            "quality": "SD",
        }
    )
    assert result["eligible"]
    assert result["expanded_recent_search"] is True


def test_expanded_policy_keeps_ten_gb_safety_cap():
    result = authorized_expanded._expanded_policy(
        {"title": "Example", "size_gb": 12.0, "source_type": "authorized"}
    )
    assert not result["eligible"]
    assert "10 GB" in result["policy_rejections"][0]


def test_expanded_button_is_in_rendered_application_html():
    assert "Show more release options" in authorized_expanded.main.INDEX_HTML
    assert "authorized or user-owned media sources" in authorized_expanded.main.INDEX_HTML
