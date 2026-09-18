from __future__ import annotations

from mediahub.app import main


def test_movie_release_search_has_terminal_timeout_and_retry_state() -> None:
    html = main.INDEX_HTML
    assert "Promise.race([request,timeout])" in html
    assert "45000" in html
    assert "Release search could not be completed." in html
    assert "retry-release-search" in html
    assert "Release search is taking too long." in html


def test_inline_movie_release_search_does_not_snapshot_parent_detail() -> None:
    html = main.INDEX_HTML
    mobile = html.split("if(window.MEDIAHUB_MOBILE_UX_V0142)return", 1)[1]
    snapshot_owner = mobile.split("browseState.detailScroll=dialog.scrollTop", 1)[0].rsplit("document.addEventListener('click'", 1)[-1]
    assert "#choose-release" not in snapshot_owner
    assert "[data-find-season-releases]" in snapshot_owner
    assert "[data-find-episode-releases]" in snapshot_owner


def test_stale_release_response_does_not_write_into_replaced_detail() -> None:
    html = main.INDEX_HTML
    assert "if(!document.body.contains(area))return;" in html
