from pathlib import Path


def test_direct_release_discovery_has_one_global_deadline() -> None:
    source = Path("mediahub/app/runtime.py").read_text()

    assert "async with asyncio.timeout(18):" in source
    assert "Release search timed out." in source
    assert "status_code=504" in source


def test_choose_release_ui_has_client_side_escape_hatch() -> None:
    source = Path("mediahub/app/web.py").read_text()

    assert "const controller=new AbortController()" in source
    assert "setTimeout(()=>controller.abort(),22000)" in source
    assert "signal:controller.signal" in source
    assert "error?.name==='AbortError'" in source
    assert "finally{clearTimeout(deadline);" in source
    assert "if(activeReleaseSearch===controller)activeReleaseSearch=null" in source
