from pathlib import Path


def test_mobile_ux_does_not_delete_release_area_status_container() -> None:
    source = Path("mediahub/app/mobile_ux_ui.py").read_text()

    assert "document.querySelectorAll('#release-area .release-rules,.release-rules[data-request-rules]" not in source
    assert "document.querySelectorAll('#release-area .release-rules[data-request-rules],#release-area [data-rule-field]')" in source


def test_release_search_renders_terminal_success_and_error_states() -> None:
    source = Path("mediahub/app/release_lifecycle.py").read_text()

    assert "<h2>Available releases</h2>" in source
    assert "No releases were returned." in source
    assert "Release search timed out. Prowlarr or an indexer is taking too long to respond." in source
