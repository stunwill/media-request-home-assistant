"""Install the final Movie route once all preset/identity/lifecycle patches exist."""
from __future__ import annotations

import asyncio
from time import monotonic

from fastapi import Query, Request

from . import enhanced_main, main, preset_main, release_lifecycle, release_search_control as control


async def movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    principal: main.CurrentUser,
    request: Request,
    expanded: bool = Query(default=False),
    manual_override: bool = Query(default=False),
):
    async def discover():
        token = control.metadata_cache.set({})
        try:
            async with asyncio.timeout(control.SERVER_SECONDS):
                effective_rules = await asyncio.to_thread(preset_main.movie_rules)
                return await release_lifecycle.release_search(
                    tmdb_id, effective_rules, principal, expanded=expanded, manual_override=manual_override)
        except TimeoutError as error:
            raise control.timeout_error() from error
        finally:
            control.metadata_cache.reset(token)

    finished = asyncio.Event()

    async def disconnected():
        while not finished.is_set():
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    started = monotonic()
    work = asyncio.create_task(discover())
    watcher = asyncio.create_task(disconnected())
    outcome = 'success'
    try:
        await asyncio.wait((work, watcher), return_when=asyncio.FIRST_COMPLETED)
        if watcher.done():
            watcher.result()
            outcome = 'disconnected'
            work.cancel()
            # No response will reach a disconnected client.
            raise asyncio.CancelledError()
        return await work
    except asyncio.CancelledError:
        if outcome != 'disconnected':
            outcome = 'cancelled'
        raise
    except Exception as error:
        outcome = 'timeout' if getattr(error, 'status_code', None) == 504 else 'error'
        raise
    finally:
        finished.set()
        for task in (work, watcher):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)  # drain cancelled children only
        control.logger.info('release_search tmdb_id=%s provider=endpoint outcome=%s elapsed_ms=%s',
                            tmdb_id, outcome, round((monotonic()-started)*1000))


enhanced_main._replace_route('/api/movies/{tmdb_id}/releases', 'POST', movie_releases)

# This script is appended last so wrappers target the effective UI functions.
_NAVIGATION_UI = r"""
<script>
(function(){
  const previousShowView=showView;showView=function(name){cancelReleaseSearch();if(!document.getElementById('modal').classList.contains('hidden'))closeModal();return previousShowView(name);};
  const previousOpenMovie=openMovie;openMovie=function(...args){cancelReleaseSearch();return previousOpenMovie(...args);};
  if(typeof openTv==='function'){const previousOpenTv=openTv;openTv=function(...args){cancelReleaseSearch();return previousOpenTv(...args);};}
  if(typeof openDownloadDetails==='function'){const previousOpenDownloadDetails=openDownloadDetails;openDownloadDetails=function(...args){cancelReleaseSearch();return previousOpenDownloadDetails(...args);};}
  window.addEventListener('pagehide',()=>cancelReleaseSearch());
})();
</script>
"""
main.INDEX_HTML = main.INDEX_HTML.replace('</body>', _NAVIGATION_UI + '\n</body>')
