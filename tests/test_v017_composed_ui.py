import subprocess

import pytest

from mediahub.app import watchlist_main, main  # noqa: F401


@pytest.mark.parametrize('width,height',[(390,844),(844,390),(768,1024),(1440,900)])
def test_all_features_in_effective_ui(tmp_path,width,height):
    html=tmp_path/'index.html'
    html.write_text(main.INDEX_HTML)
    result=subprocess.run(['node','tests/mobile_feature_ui.cjs',str(html),str(width),str(height)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
