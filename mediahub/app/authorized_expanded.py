from __future__ import annotations

from datetime import date
from typing import Any, Awaitable, Callable

from fastapi import Query

from . import enhanced_main, main, runtime

app = runtime.app
app.version = "0.6.8-dev"

AuthorizedProvider = Callable[[dict[str, Any]], Awaitable[list[dict[str, Any]]]]
AUTHORIZED_RELEASE_PROVIDERS: list[AuthorizedProvider] = []
EXPANDED_MAX_SIZE_GB = 10.0


def released_within_last_12_months(
    movie: dict[str, Any],
    *,
    today: date | None = None,
) -> bool:
    today = today or date.today()
    released = runtime._release_date(movie)
    if released is None:
        return False
    age_days = (today - released).days
    return 0 <= age_days <= 365


def register_authorized_release_provider(provider: AuthorizedProvider) -> None:
    if provider not in AUTHORIZED_RELEASE_PROVIDERS:
        AUTHORIZED_RELEASE_PROVIDERS.append(provider)


def _expanded_policy(release: dict[str, Any]) -> dict[str, Any]:
    result = dict(release)
    rejections: list[str] = []
    size_gb = float(release.get("size_gb") or 0)

    if str(release.get("source_type") or "") not in {"authorized", "user_owned", "local"}:
        rejections.append("Expanded options are limited to authorized or user-owned sources")
    if not size_gb:
        rejections.append("Release size is unavailable")
    elif size_gb > EXPANDED_MAX_SIZE_GB:
        rejections.append(f"Release exceeds the {EXPANDED_MAX_SIZE_GB:g} GB expanded-search limit")

    result["policy_rejections"] = list(dict.fromkeys(rejections))
    result["eligible"] = not result["policy_rejections"]
    result["expanded_recent_search"] = True
    result["quality_warning"] = (
        "Expanded recent-release option. This result is outside MediaHub's normal preferred "
        "quality or size rules and comes from an explicitly authorized or user-owned source."
    )
    result.pop("info_hash", None)
    result.pop("guid", None)
    return result


async def _authorized_expanded_results(movie: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for provider in AUTHORIZED_RELEASE_PROVIDERS:
        provider_results = await provider(movie)
        for item in provider_results:
            if isinstance(item, dict):
                results.append(dict(item))
    return results


async def movie_releases(
    tmdb_id: int,
    rules: main.ReleaseRules,
    principal: main.CurrentUser,
    expanded: bool = Query(default=False),
) -> dict[str, Any]:
    tmdb, _, _ = main.configured_clients(main.load_options())
    try:
        movie = await tmdb.details(tmdb_id)
    except runtime.media_services.MediaServiceError as error:
        raise main.service_http_error(error) from error

    eligible_for_expanded = released_within_last_12_months(movie)

    if not expanded:
        result = await enhanced_main.movie_releases(tmdb_id, rules, principal)
        result["can_expand_recent_search"] = bool(
            eligible_for_expanded and not result.get("releases")
        )
        result["expanded_recent_search"] = False
        result["expanded_maximum_size_gb"] = EXPANDED_MAX_SIZE_GB
        return result

    if not eligible_for_expanded:
        return {
            "radarr_movie_id": 0,
            "rules": rules.model_dump(),
            "recent_quality_fallback": False,
            "expanded_recent_search": False,
            "can_expand_recent_search": False,
            "expanded_maximum_size_gb": EXPANDED_MAX_SIZE_GB,
            "releases": [],
            "expanded_source_message": "Expanded options are only available for movies released within the last 12 months.",
        }

    releases = [_expanded_policy(item) for item in await _authorized_expanded_results(movie)]
    releases.sort(
        key=lambda item: (
            bool(item.get("eligible")),
            int(item.get("seeders") or 0),
            -float(item.get("size_gb") or 0),
        ),
        reverse=True,
    )

    with main.connect_db() as db:
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action="movie_authorized_expanded_search",
            request_id=None,
            details={
                "tmdb_id": tmdb_id,
                "result_count": len(releases),
                "maximum_size_gb": EXPANDED_MAX_SIZE_GB,
            },
        )
        db.commit()

    return {
        "radarr_movie_id": 0,
        "rules": rules.model_dump(),
        "recent_quality_fallback": False,
        "expanded_recent_search": True,
        "can_expand_recent_search": False,
        "expanded_maximum_size_gb": EXPANDED_MAX_SIZE_GB,
        "releases": releases,
        "expanded_source_message": (
            "No authorized or user-owned release providers are configured."
            if not AUTHORIZED_RELEASE_PROVIDERS
            else ""
        ),
    }


enhanced_main._replace_route(
    "/api/movies/{tmdb_id}/releases",
    "POST",
    movie_releases,
)


_EXPANDED_UI = r"""
<script>
  function renderAuthorizedReleaseResults(data, selectedRules, expanded=false){
    const area=document.getElementById('release-area');
    const cards=(data.releases||[]).map(release=>`<article class="release"><div><h4>${esc(release.title||'Release option')}</h4><div class="release-meta"><span>${esc(release.source_name||release.indexer||'Authorized source')}</span><span>${esc(release.quality||'Quality not specified')}</span><span>${Number(release.size_gb||0).toFixed(2)} GB</span></div>${release.quality_warning?`<div class="hint">${esc(release.quality_warning)}</div>`:''}${release.policy_rejections?.length?`<div class="release-reasons">${esc(release.policy_rejections.join(' · '))}</div>`:''}</div><button class="button ${release.eligible?'primary':''}" ${release.eligible?'':'disabled'}>${release.eligible?'Available':'Rejected'}</button></article>`).join('');
    const broaden=(!expanded&&data.can_expand_recent_search)?`<div class="empty"><div>No standard releases were found.</div><button class="button primary" id="expanded-release-search" type="button" style="margin-top:16px">Show more release options</button><div class="hint" style="margin-top:10px">For movies released within the last 12 months, this can show broader quality and size options from explicitly authorized or user-owned media sources.</div></div>`:'';
    const sourceMessage=data.expanded_source_message?`<div class="empty">${esc(data.expanded_source_message)}</div>`:'';
    const empty=expanded?(sourceMessage||'<div class="empty">No broader authorized release options were found.</div>'):'<div class="empty">No releases were returned.</div>';
    area.innerHTML=`${rulesHtml(selectedRules)}<div class="heading"><div><h2>${expanded?'More release options':'Available releases'}</h2><p>${(data.releases||[]).length} results.</p></div><button class="button" id="rerun-search">Search again</button></div><div class="releases">${cards||broaden||empty}</div>`;
    document.getElementById('rerun-search').addEventListener('click',findReleases);
    const expandedButton=document.getElementById('expanded-release-search');
    if(expandedButton)expandedButton.addEventListener('click',()=>findAuthorizedExpandedReleases(selectedRules,expandedButton));
  }

  async function findAuthorizedExpandedReleases(selectedRules,button){
    button.disabled=true;
    button.textContent='Searching more options...';
    try{
      const data=await api(`movies/${state.movie.tmdb_id}/releases?expanded=true`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectedRules)});
      renderAuthorizedReleaseResults(data,selectedRules,true);
    }catch(error){
      toast(error.message);
      button.disabled=false;
      button.textContent='Show more release options';
    }
  }

  findReleases=async function(){
    const area=document.getElementById('release-area');
    const selectedRules=rules();
    area.innerHTML=`${rulesHtml(selectedRules)}<div class="empty">Searching available releases...</div>`;
    try{
      const data=await api(`movies/${state.movie.tmdb_id}/releases`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(selectedRules)});
      if(data.can_expand_recent_search){
        renderAuthorizedReleaseResults(data,selectedRules,false);
        return;
      }
      area.innerHTML=`${rulesHtml(selectedRules)}<div class="heading"><div><h2>Available releases</h2><p>${data.releases.length} results from your configured sources.</p></div><button class="button" id="rerun-search">Search again</button></div><div class="releases">${data.releases.map(release=>`<article class="release"><div><h4>${esc(release.title)}</h4><div class="release-meta"><span>${esc(release.indexer)}</span><span>${esc(release.quality)}</span><span>${release.size_gb.toFixed(2)} GB</span><span>${release.seeders??'?'} seeders</span></div>${release.policy_rejections.length?`<div class="release-reasons">${esc(release.policy_rejections.join(' · '))}</div>`:''}</div><button class="button ${release.eligible?'primary':''}" data-token="${esc(release.release_token)}" ${release.eligible?'':'disabled'}>${release.eligible?'Download':'Rejected'}</button></article>`).join('')||'<div class="empty">No releases were returned.</div>'}</div>`;
      document.getElementById('rerun-search').addEventListener('click',findReleases);
      area.querySelectorAll('[data-token]').forEach(button=>button.addEventListener('click',()=>submitRequest(button.dataset.token,button)));
    }catch(error){
      area.innerHTML=`${rulesHtml(selectedRules)}<div class="empty">${esc(error.message)}</div>`;
    }
  };
</script>
"""

if "Show more release options" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _EXPANDED_UI + "\n</body>")
