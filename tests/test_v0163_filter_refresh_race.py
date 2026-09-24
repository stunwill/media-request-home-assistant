from mediahub.app import main


def test_filter_apply_supersedes_inflight_catalogue_load():
    html = main.INDEX_HTML
    assert "s.generation=(s.generation||0)+1;s.loading=false" in html
    assert "if(generation!==(s.generation||0))return" in html
    assert "if(generation===(s.generation||0))s.loading=false" in html
