from __future__ import annotations

from mediahub.app import main, mobile_ux_ui


def _mobile_layer(html: str) -> str:
    marker = "if(window.MEDIAHUB_MOBILE_UX_V0141)return"
    return html.split(marker, 1)[1] if marker in html else html


def test_v014_version_and_entrypoint_markers() -> None:
    assert mobile_ux_ui.app.version.startswith("0.14.")
    html = main.INDEX_HTML
    for marker in (
        "MEDIAHUB_MOBILE_UX_V0141",
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


def test_requester_movie_policy_is_read_only_at_mobile_ownership_layer() -> None:
    html = main.INDEX_HTML
    mobile_html = _mobile_layer(html)
    assert "window.rulesHtml=function()" in mobile_html
    assert "Household download presets applied" in mobile_html
    assert "MEDIAHUB_CURRENT_MOVIE_PRESETS" in mobile_html
    assert "removeLegacyRules" in mobile_html
    assert "#release-area .release-rules" in mobile_html
    # Admin Setup legitimately reads /api/setup/presets. The requester/mobile
    # bootstrap must not perform that setup request during ingress startup.
    assert "api('setup/presets')" not in mobile_html


def test_mobile_bootstrap_guards_optional_dom_and_throttles_mutations() -> None:
    html = main.INDEX_HTML
    mobile_html = _mobile_layer(html)
    assert "if(modal)new MutationObserver" in mobile_html
    assert "requestAnimationFrame(()=>{mutationPending=false" in mobile_html
    assert "q('mobile-filter-close')?.addEventListener" in mobile_html
    assert "typeof searchForm.requestSubmit==='function'" in mobile_html


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
