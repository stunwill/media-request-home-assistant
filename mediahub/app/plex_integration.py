from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from . import main, plex_library, rich_details

app = rich_details.app
app.version = "0.9.0-dev"


def plex_config(options: dict[str, Any] | None = None) -> plex_library.PlexConfig:
    values = (options or main.load_options()).get("integrations", {})
    return plex_library.PlexConfig(
        url=str(values.get("plex_url") or ""),
        token=str(values.get("plex_token") or ""),
        library_key=str(values.get("plex_library_key") or ""),
        machine_identifier=str(values.get("plex_machine_identifier") or ""),
    )


async def plex_status_payload() -> dict[str, Any]:
    config = plex_config()
    if not config.configured:
        return {"name": "plex", "status": "not_configured", "configured": False}
    client = plex_library.PlexClient(config)
    try:
        identity = await client.identity()
        libraries = await client.movie_libraries()
    except plex_library.PlexError as error:
        message = str(error)
        status = "authentication_failed" if "authentication" in message.lower() else "unavailable"
        return {"name": "plex", "status": status, "configured": True, "message": message}
    configured_library = config.library_key
    if configured_library and not any(item["key"] == configured_library for item in libraries):
        return {
            "name": "plex",
            "status": "library_unavailable",
            "configured": True,
            "details": {"machine_identifier": identity.get("machine_identifier", ""), "libraries": libraries},
        }
    return {
        "name": "plex",
        "status": "connected",
        "configured": True,
        "details": {
            "machine_identifier": identity.get("machine_identifier", ""),
            "version": identity.get("version", ""),
            "libraries": libraries,
            "selected_library_key": configured_library,
        },
    }


async def plex_library_state(movie: dict[str, Any]) -> dict[str, Any]:
    config = plex_config()
    if not config.configured:
        return {"configured": False, "available": False, "matched": False}
    client = plex_library.PlexClient(config)
    try:
        items, stale = await plex_library.PLEX_CACHE.items(client)
    except plex_library.PlexError:
        return {"configured": True, "available": False, "matched": False, "status": "unavailable"}
    matched = plex_library.match_movie(movie, items)
    item = matched.get("match")
    if not item:
        return {
            "configured": True,
            "available": False,
            "matched": False,
            "confidence": matched.get("confidence"),
            "match_method": matched.get("match_method"),
            "stale": stale,
        }
    machine_identifier = config.machine_identifier
    if not machine_identifier:
        try:
            machine_identifier = (await client.identity()).get("machine_identifier", "")
        except plex_library.PlexError:
            machine_identifier = ""
    watch_url = plex_library.plex_web_url(machine_identifier, str(item.get("rating_key") or ""))
    return {
        "configured": True,
        "available": True,
        "matched": True,
        "confidence": matched.get("confidence"),
        "match_method": matched.get("match_method"),
        "watch_url": watch_url,
        "stale": stale,
    }


async def movie_details_with_plex(
    tmdb_id: int,
    principal: main.CurrentUser,
    context: str = "browse",
) -> dict[str, Any]:
    movie = await rich_details.rich_movie_details(tmdb_id, principal, context=context)
    plex_state = await plex_library_state(movie)
    movie["plex"] = plex_state
    library = movie.get("library") or {}
    movie["library"] = {
        **library,
        "radarr": {"available": str(library.get("status") or "") == "available"},
        "plex": plex_state,
    }
    return movie


async def download_details_with_plex(
    request_id: int,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    movie = await rich_details.download_movie_details(request_id, principal)
    plex_state = await plex_library_state(movie)
    library = movie.get("library") or {}
    movie["plex"] = plex_state
    movie["library"] = {
        **library,
        "radarr": {"available": str(library.get("status") or "") == "available"},
        "plex": plex_state,
    }
    return movie


async def plex_setup_options(_: main.Administrator) -> dict[str, Any]:
    status = await plex_status_payload()
    return status


async def request_movie_with_plex(
    tmdb_id: int,
    payload: main.MovieRequestCreate,
    principal: main.CurrentUser,
) -> dict[str, Any]:
    tmdb, _, _ = main.configured_clients(main.load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except Exception:
        movie = {"tmdb_id": tmdb_id}
    plex_state = await plex_library_state(movie)
    if plex_state.get("available") and plex_state.get("confidence") == "exact_identifier":
        raise HTTPException(status_code=409, detail="This movie is already available in Plex.")
    return await main.request_movie(tmdb_id, payload, principal)


rich_details.runtime.enhanced_main._replace_route("/api/catalog/movies/{tmdb_id}", "GET", movie_details_with_plex)
rich_details.runtime.enhanced_main._replace_route("/api/downloads/{request_id}/details", "GET", download_details_with_plex)
rich_details.runtime.enhanced_main._replace_route("/api/movies/{tmdb_id}/request", "POST", request_movie_with_plex)
app.add_api_route("/api/setup/plex", plex_setup_options, methods=["GET"])


_PLEX_UI = r"""
<style>
  .plex-badge{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;background:rgba(229,160,13,.14);color:#ffd56a;font-size:.76rem;font-weight:850}.plex-card{padding:14px;border:1px solid var(--border);border-radius:14px;background:#0c1018}.plex-card strong{display:block;margin-bottom:4px}.plex-setup-note{margin-top:8px}.plex-filter-row{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
</style>
<script>
  function plexSection(movie){const plex=movie.plex||{};if(!plex.configured)return '';if(!plex.available)return plex.status==='unavailable'?'<div class="section-title">Plex</div><div class="plex-card"><strong>Plex temporarily unavailable</strong><span class="muted">Movie details remain available from MediaHub.</span></div>':'';const watch=plex.watch_url?`<a class="button primary" href="${esc(plex.watch_url)}" target="_blank" rel="noopener noreferrer">Watch in Plex</a>`:'';return `<div class="section-title">Plex</div><div class="plex-card"><span class="plex-badge">Available in Plex</span><div class="actions">${watch}</div></div>`;}
  const previousRenderDetail=renderDetail;
  renderDetail=function(){previousRenderDetail();const movie=state.movie;if(!movie)return;const plex=movie.plex||{};if(plex.available){document.getElementById('auto-request')?.remove();document.getElementById('choose-release')?.remove();document.getElementById('watch-release')?.remove();document.getElementById('search-anyway')?.remove();}const body=document.querySelector('#detail .detail-grid');if(body&&!document.getElementById('plex-library-section')){const holder=document.createElement('div');holder.id='plex-library-section';holder.innerHTML=plexSection(movie);body.insertBefore(holder,body.querySelector('#release-area'));}};
  const setupGrid=document.querySelector('#setup-form .setup-grid');
  if(setupGrid&&!document.querySelector('[data-service="plex"]'))setupGrid.insertAdjacentHTML('beforeend',`<article class="service" data-service="plex"><div class="service-head"><span>Plex <small class="muted">Optional</small></span><span class="badge" data-status>Not configured</span></div><div class="fields"><label class="field">Server URL<input id="plex_url" type="url" placeholder="http://homeassistant.local:32400"></label><label class="field">Plex token<input id="plex_token" type="password" autocomplete="new-password" placeholder="Saved token is never displayed"></label><label class="field">Movie library key<input id="plex_library_key" placeholder="Optional until connected"></label><label class="field">Machine identifier<input id="plex_machine_identifier" placeholder="Optional, discovered when possible"></label><div class="hint plex-setup-note">Optional. MediaHub matches Plex movies by TMDb or IMDb GUID first and never places the Plex token in browser links.</div></div></article>`);
  if(typeof serviceNames!=='undefined'&&!serviceNames.includes('plex'))serviceNames.push('plex');
  if(typeof secretFields!=='undefined'&&!secretFields.includes('plex_token'))secretFields.push('plex_token');
  const originalLoadSetup=loadSetup;
  loadSetup=async function(){await originalLoadSetup();try{const status=await api('setup/plex');const card=document.querySelector('[data-service="plex"]');if(!card)return;const badge=card.querySelector('[data-status]');badge.textContent=({connected:'Connected',not_configured:'Optional',authentication_failed:'Check token',unavailable:'Unavailable',library_unavailable:'Select library'})[status.status]||status.status;badge.className=`badge ${status.status==='connected'?'connected':''}`;const settings=(await api('setup')).settings.plex||{};document.getElementById('plex_url').value=settings.url||'';document.getElementById('plex_library_key').value=settings.library_key||'';document.getElementById('plex_machine_identifier').value=settings.machine_identifier||'';if(settings.token_set)document.getElementById('plex_token').placeholder='Saved, enter a new token to replace';}catch(error){/* Plex is optional. */}};
  const setupForm=document.getElementById('setup-form');
  setupForm.addEventListener('submit',()=>{['plex_url','plex_library_key','plex_machine_identifier'].forEach(id=>{const input=document.getElementById(id);if(input)input.dataset.mediahubValue=input.value;});},{capture:true});
</script>
"""

if "plex-badge" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _PLEX_UI + "\n</body>")
