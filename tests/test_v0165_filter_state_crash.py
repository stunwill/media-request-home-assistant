from mediahub.app import main


def test_mobile_filters_do_not_reference_nonexistent_window_state():
    html = main.INDEX_HTML
    assert "window.state.genreIds" not in html
    assert "window.state.genreId" not in html
    assert "let mobileGenreIds=[]" in html
    assert "mobileGenreIds=genres" in html
