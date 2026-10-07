from pathlib import Path


def test_mobile_detail_resets_dialog_scroll_after_render() -> None:
    source = Path("mediahub/app/mobile_ux_ui.py").read_text()
    assert "function modalTop(){if(dialog)requestAnimationFrame(()=>{dialog.scrollTop=0;});}" in source


def test_mobile_detail_suspends_bottom_navigation_while_modal_is_open() -> None:
    source = Path("mediahub/app/mobile_ux_ui.py").read_text()
    assert "nav?.classList.toggle('is-suspended',!!value)" in source
    assert "nav?.classList.remove('is-suspended')" not in source


def test_mobile_detail_reserves_bottom_safe_space() -> None:
    source = Path("mediahub/app/mobile_ux_ui.py").read_text()
    assert ".detail-body{padding:0 16px calc(112px + env(safe-area-inset-bottom))}" in source
