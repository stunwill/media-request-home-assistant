from mediahub.app import main


def test_mobile_filters_use_active_catalogue_controller():
    html = main.INDEX_HTML
    assert "window.MEDIAHUB_APPLY_MOVIE_FILTERS=function(filters)" in html
    assert "window.MEDIAHUB_APPLY_MOVIE_FILTERS({genres" in html
    assert "genres.forEach(id=>p.append('genre_id',id))" in html


def test_mobile_apply_does_not_use_disabled_legacy_loader():
    html = main.INDEX_HTML
    apply_section = html[html.index("mobile-filter-apply"):]
    assert "if(typeof window.loadMovies==='function')window.loadMovies()" not in apply_section
