from mediahub.app import main


def test_apply_filters_closes_sheet_before_catalogue_refresh():
    html = main.INDEX_HTML
    apply = html[html.index("mobile-filter-apply"):]
    assert "updateFilterButton();closeSheet({restoreFocus:false});if(typeof window.MEDIAHUB_APPLY_MOVIE_FILTERS" in apply


def test_close_sheet_forces_hidden_display_and_releases_body_lock():
    html = main.INDEX_HTML
    assert "sheet.setAttribute('aria-hidden','true');sheet.style.display='none';document.body.classList.remove('modal-open')" in html
