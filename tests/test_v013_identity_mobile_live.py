from __future__ import annotations

from mediahub.app import main, mobile_live_ui, release_identity


def movie(title: str, year: int, original_title: str = "") -> dict:
    return {"title": title, "original_title": original_title, "year": str(year)}


def test_movie_identity_exact_title_and_year() -> None:
    result = release_identity.validate_movie_release(movie("Arrival", 2016), {"title": "Arrival.2016.1080p.BluRay.x265-LAMA"})
    assert result.eligible is True
    assert result.state == "strong"


def test_movie_identity_normalises_punctuation_case_and_underscores() -> None:
    result = release_identity.validate_movie_release(movie("The Matrix", 1999), {"title": "THE_MATRIX.1999.1080p.BluRay.x265"})
    assert result.eligible is True


def test_dog_stars_rejects_stars_on_mars_episode() -> None:
    result = release_identity.validate_movie_release(movie("The Dog Stars", 2026), {"title": "Stars.on.Mars.S01E10.Downward.Dog.1080p.HULU.WEB-DL"})
    assert result.eligible is False
    assert "TV episode" in " ".join(result.reasons)


def test_dog_stars_rejects_krypto_episode() -> None:
    result = release_identity.validate_movie_release(movie("The Dog Stars", 2026), {"title": "Krypto.The.Superdog.S01E22.Bathound.Meets.The.Dog.Stars.and.A.Dogs.Life.720p.MAX.WEB-DL"})
    assert result.eligible is False


def test_buffalo_soldiers_allows_one_year_difference_for_strong_title() -> None:
    result = release_identity.validate_movie_release(movie("Buffalo Soldiers", 2002), {"title": "Buffalo.Soldiers.2001.1080p.BluRay.x265"})
    assert result.eligible is True
    assert result.release_year == 2001
    assert "Year within accepted range" in result.reasons


def test_material_year_conflict_rejected() -> None:
    result = release_identity.validate_movie_release(movie("Awake", 2007), {"title": "Awake.2021.1080p.WEBRip.x265"})
    assert result.eligible is False
    assert result.reasons == ("Conflicting release year",)


def test_unrelated_title_with_requested_words_not_prefix_match() -> None:
    result = release_identity.validate_movie_release(movie("The Dog Stars", 2026), {"title": "Circus.of.the.Dog.Stars.2026.1080p.WEBRip"})
    assert result.eligible is False


def test_tv_episode_identity() -> None:
    good = release_identity.validate_tv_release(series_title="Example Show", release={"title": "Example.Show.S02E04.1080p.WEB-DL"}, season_number=2, episode_number=4)
    bad = release_identity.validate_tv_release(series_title="Example Show", release={"title": "Example.Show.S02E05.1080p.WEB-DL"}, season_number=2, episode_number=4)
    assert good.eligible is True
    assert bad.eligible is False


def test_tv_season_identity_uses_full_season_signal() -> None:
    good = release_identity.validate_tv_release(series_title="Example Show", release={"title": "Example.Show.S03.1080p.WEB-DL"}, season_number=3, episode_number=None, structured_full_season=True)
    bad = release_identity.validate_tv_release(series_title="Example Show", release={"title": "Example.Show.S02.1080p.WEB-DL"}, season_number=3, episode_number=None, structured_full_season=False)
    assert good.eligible is True
    assert bad.eligible is False


def test_apply_identity_removes_eligibility_before_quality_can_win() -> None:
    public = {"eligible": True, "policy_rejections": []}
    identity = release_identity.validate_movie_release(movie("The Dog Stars", 2026), {"title": "Stars.on.Mars.S01E10.Downward.Dog.1080p.WEB-DL"})
    result = release_identity.apply_identity(public, identity)
    assert result["eligible"] is False
    assert result["match_state"] == "rejected"


def test_v013_mobile_ux_markers_present() -> None:
    html = main.INDEX_HTML
    major, minor, *_ = [int(part.split("-", 1)[0]) for part in mobile_live_ui.app.version.split(".")]
    assert (major, minor) >= (0, 13)
    for marker in (
        "mobile-filter-toggle", "mobile-bottom-nav", "detail-skeleton", "BEST MATCH",
        "Unavailable releases", "MutationObserver", "visibilitychange", "450",
    ):
        assert marker in html


def test_mobile_hero_hidden_and_release_cards_compact() -> None:
    html = main.INDEX_HTML
    assert "@media(max-width:760px)" in html
    assert ".hero{display:none}" in html
    assert ".release{grid-template-columns:1fr" in html


def test_existing_core_markers_preserved() -> None:
    html = main.INDEX_HTML
    assert "IntersectionObserver" in html
    assert "MEDIAHUB_INFINITE_CATALOGUE" in html
    assert "Service Connections" in html
    assert "Download Presets" in html
    assert "Request best release" in html
    assert "Find season packs" in html
