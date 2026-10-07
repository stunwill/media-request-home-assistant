from pathlib import Path


def test_movie_release_search_can_be_cancelled_by_navigation() -> None:
    source = Path("mediahub/app/web.py").read_text()

    assert "let activeReleaseSearch=null" in source
    assert "window.cancelReleaseSearch=cancelReleaseSearch" in source
    assert "findReleases(){cancelReleaseSearch();" in source
    assert "closeModal(){cancelReleaseSearch();" in source
    assert "if(activeReleaseSearch===controller)activeReleaseSearch=null" in source


def test_mobile_back_cancels_search_and_navigation_is_not_suspended() -> None:
    source = Path("mediahub/app/mobile_ux_ui.py").read_text()

    assert "window.cancelReleaseSearch?.();" in source
    assert "nav?.classList.remove('is-suspended')" in source
    assert "nav?.classList.toggle('is-suspended',keyboard||!!(modal&&!modal.classList.contains('hidden')))" not in source
    assert "nav?.classList.toggle('is-suspended',keyboard)" in source
