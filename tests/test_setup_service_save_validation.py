from pathlib import Path


def test_download_presets_are_inserted_outside_service_connection_form() -> None:
    source = Path("mediahub/app/preset_ui.py").read_text()

    assert "setupGrid.insertAdjacentHTML('afterend'" in source
    assert "setupGrid.insertAdjacentHTML('beforeend'" not in source


def test_service_connection_form_keeps_independent_save_action() -> None:
    source = Path("mediahub/app/web.py").read_text()

    assert '<form id="setup-form"><div class="setup-grid">' in source
    assert 'id="save-setup"' in source
    assert "setup/integrations" in source


def test_presets_keep_their_own_explicit_save_action() -> None:
    source = Path("mediahub/app/preset_ui.py").read_text()

    assert 'id="save-presets" type="button"' in source
    assert "setup/presets" in source
