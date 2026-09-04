from __future__ import annotations

from mediahub.app import main, mobile_ux_ui


def test_v014_version_and_entrypoint_markers() -> None:
    assert mobile_ux_ui.app.version == "0.14.0-dev"
    html = main.INDEX_HTML
    for marker in (
        "MEDIAHUB_MOBILE_UX_V014",
        "mobile-filter-sheet",
        "mobile-search-clear",
        "mobile-modal-back",
        "household-policy-summary",
        "safe-area-inset-bottom",
        "prefers-reduced-motion",
        "visualViewport",
    ):
        assert marker in html


def test_mobile_filter_sheet_is_staged_and_has_unique_clone_ids() -> None:
    html = main.INDEX_HTML
    assert "mobile-filter-apply" in html
    assert "mobile-filter-clear" in html
    assert "aria-modal=\"true\"" in html
    assert "el.id='mobile-'+el.id" in html
    assert "dispatchEvent(new Event('change'" in html


def test_search_has_single_capture_owner_marker_and_clear_action() -> None:
    html = main.INDEX_HTML
    assert "stopImmediatePropagation" in html
    assert "searchGeneration" in html
    assert "450" in html
    assert "Clear search" in html


def test_modal_owns_mobile_viewport_and_suspends_bottom_navigation() -> None:
    html = main.INDEX_HTML
    assert "height:100dvh" in html
    assert "body.modal-open{overflow:hidden}" in html
    assert "mobile-bottom-nav.is-suspended" in html
    assert "suspendNav(mobile())" in html
    assert "overscroll-behavior:contain" in html


def test_detail_loading_uses_structured_skeleton_and_resets_scroll() -> None:
    html = main.INDEX_HTML
    assert "aria-label=\"Loading details\"" in html
    assert "skeleton cast" in html
    assert "modalTop()" in html
    assert "detailGeneration" in html
    assert "detailCache" in html


def test_parent_detail_and_browse_scroll_state_are_preserved() -> None:
    html = main.INDEX_HTML
    assert "browseState.detailScroll=dialog.scrollTop" in html
    assert "MEDIAHUB_PARENT_DETAIL_RESTORE" in html
    assert "browseState.scrollY=window.scrollY" in html
    assert "window.scrollTo({top:browseState.scrollY" in html


def test_requester_movie_policy_is_read_only_at_v014_ownership_layer() -> None:
    html = main.INDEX_HTML
    assert "window.rules=function()" in html
    assert "window.rulesHtml=function()" in html
    assert "Household download presets applied" in html
    assert "MEDIAHUB_CURRENT_MOVIE_PRESETS" in html
    assert "removeLegacyRules" in html
    assert "#release-area .release-rules" in html


def test_mobile_collection_chips_and_safe_area_are_preserved() -> None:
    html = main.INDEX_HTML
    assert "scroll-snap-type:x proximity" in html
    assert ".filters .chip{flex:0 0 auto" in html
    assert "calc(92px + env(safe-area-inset-bottom))" in html


def test_existing_v013_safety_and_live_download_markers_remain() -> None:
    html = main.INDEX_HTML
    for marker in (
        "BEST MATCH",
        "Unavailable releases",
        "visibilitychange",
        "IntersectionObserver",
        "MEDIAHUB_INFINITE_CATALOGUE",
        "Service Connections",
        "Search & Download Presets",
    ):
        assert marker in html
