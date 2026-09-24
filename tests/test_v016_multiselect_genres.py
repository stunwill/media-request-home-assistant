from mediahub.app import main


def test_catalogue_api_accepts_repeated_genre_ids():
    route = next(route for route in main.app.routes if getattr(route, "path", "") == "/api/catalog/movies")
    assert route is not None


def test_mobile_genre_picker_is_multiselect_and_resynchronises_options():
    html = main.INDEX_HTML
    assert "mobile-genre-list" in html
    assert 'type="checkbox"' in html
    assert "function syncGenres()" in html
    assert "source.options" in html
    assert "mobileGenreIds=genres" in html


def test_catalogue_requests_emit_each_selected_genre():
    html = main.INDEX_HTML
    assert "activeGenres.forEach(id=>params.append('genre_id',id))" in html
