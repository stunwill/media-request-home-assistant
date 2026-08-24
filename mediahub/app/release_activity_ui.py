from __future__ import annotations

from . import main, release_activity

app = release_activity.app
app.version = "0.6.9-dev"

_DYNAMIC_RELEASE_DECORATION = r"""
<script>
  let mediaHubReleaseDecorationPending=false;
  new MutationObserver(()=>{
    if(mediaHubReleaseDecorationPending)return;
    mediaHubReleaseDecorationPending=true;
    queueMicrotask(()=>{
      mediaHubReleaseDecorationPending=false;
      if(typeof decorateReleaseResults==='function')decorateReleaseResults();
    });
  }).observe(document.body,{childList:true,subtree:true});
</script>
"""

if "mediaHubReleaseDecorationPending" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace(
        "</body>",
        _DYNAMIC_RELEASE_DECORATION + "\n</body>",
    )
