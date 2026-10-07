from pathlib import Path


def test_release_search_javascript_does_not_contain_literal_escape_between_statements() -> None:
    source = Path("mediahub/app/web.py").read_text()

    assert "window.cancelReleaseSearch=cancelReleaseSearch;\\\\n    async function findReleases" not in source
    assert "window.cancelReleaseSearch=cancelReleaseSearch;\n    async function findReleases" in source
