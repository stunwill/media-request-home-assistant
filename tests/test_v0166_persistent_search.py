from mediahub.app import main


def test_search_query_persists_across_media_type_switches():
    html = main.INDEX_HTML
    assert "const sharedQuery=document.getElementById('search').value.trim()" in html
    assert "catalogueState[browseMedia].query=sharedQuery" in html
    assert "browseMedia=type;catalogueState[browseMedia].query=sharedQuery" in html
