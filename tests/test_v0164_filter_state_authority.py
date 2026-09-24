from mediahub.app import main


def test_multi_genre_state_is_not_overwritten_by_single_genre_control():
    html = main.INDEX_HTML
    assert "if(!(browseMedia==='movie'&&s.genres?.length))s.genre=controlGenre" in html
    assert "function resetCatalogue({remember=true}={})" in html
