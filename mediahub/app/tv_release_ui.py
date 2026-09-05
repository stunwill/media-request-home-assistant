from __future__ import annotations

from . import main, tv_release_selection, tv_ui

app = tv_release_selection.app

_RELEASE_UI = r"""
<style>
  .season-action-card{border:1px solid var(--border);border-radius:14px;background:#0c1018;padding:14px;display:grid;gap:10px}.season-action-card .actions{margin:0}.episode-list{display:grid;gap:10px}.episode-row{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;padding:12px;border:1px solid var(--border);border-radius:13px;background:#0c1018}.episode-number{font-weight:900}.episode-status{font-size:.76rem;color:var(--muted)}.episode-status.available{color:var(--success)}.episode-status.downloading{color:var(--warning)}.episode-status.unaired{color:#aeb8c7}.release-summary{padding:11px 13px;border:1px solid var(--border);border-radius:12px;background:#0d1119;color:var(--muted)}
  @media(max-width:760px){.episode-row{grid-template-columns:1fr}}
</style>
<script>
  let tvSeasonContext=null;

  const originalRenderTvDetail=renderTvDetail;
  renderTvDetail=function(show){
    const seasons=(show.seasons||[]).map(season=>`<div class="season-action-card"><div><strong>${esc(season.name)}</strong><div class="muted">${season.episode_count} episodes${season.air_date?` · ${esc(season.air_date)}`:''}</div></div><div class="actions"><button class="button primary" data-open-season="${season.season_number}">View season</button></div></div>`).join('');
    const genres=(show.genres||[]).map(g=>g.name).join(' · ');
    document.getElementById('detail').innerHTML=`<div class="detail-hero" style="${show.backdrop_url?`background-image:url('${esc(show.backdrop_url)}')`:''}"><div class="detail-copy"><div class="eyebrow">TV Show</div><h2>${esc(show.name)}</h2><div class="muted">${esc(show.year||'')} · ${show.number_of_seasons||0} seasons · ${show.number_of_episodes||0} episodes</div><div class="actions">${show.trailer_url?`<a class="button" href="${esc(show.trailer_url)}" target="_blank" rel="noopener noreferrer">Watch trailer</a>`:''}<button class="button" id="request-tv-series">Request entire series (advanced)</button></div></div></div><div class="detail-body"><p class="muted">${esc(show.overview||'No synopsis is available.')}</p><div class="muted">${esc(genres)}</div><div class="section-title">Seasons</div><div class="season-grid">${seasons}</div></div>`;
    document.querySelectorAll('[data-open-season]').forEach(btn=>btn.addEventListener('click',()=>openSeason(show,Number(btn.dataset.openSeason))));
    document.getElementById('request-tv-series')?.addEventListener('click',()=>submitTvRequest(show.tmdb_id,'series',[]));
  };

  async function openSeason(show,seasonNumber){
    try{
      const season=await api(`catalog/tv/${show.tmdb_id}/seasons/${seasonNumber}`);
      tvSeasonContext={show,season};
      renderSeason(season);
    }catch(error){toast(error.message);}
  }
  function renderSeason(season){
    document.getElementById('detail').innerHTML=`<div class="detail-body" style="padding-top:34px"><button class="button" id="back-to-tv">← Back to ${esc(season.series_title)}</button><div class="heading"><div><h2>${esc(season.season_name)}</h2><p>${season.available_episode_count}/${season.total_episode_count} available · ${season.downloading_episode_count} downloading · ${season.missing_episode_count} missing</p></div></div><div class="release-summary">Household download presets applied · season pack max ${Number(season.policy.maximum_season_size_gb).toFixed(1)} GB · episode max ${Number(season.policy.maximum_episode_size_gb).toFixed(1)} GB</div><div class="actions"><button class="button primary" id="find-season-packs">Find season packs</button><button class="button" id="show-episodes">View episodes</button></div><div id="season-content"></div></div>`;
    document.getElementById('back-to-tv').addEventListener('click',()=>originalRenderTvDetail(tvSeasonContext.show));
    document.getElementById('find-season-packs').addEventListener('click',()=>findSeasonPacks(season));
    document.getElementById('show-episodes').addEventListener('click',()=>renderEpisodes(season));
  }
  function renderEpisodes(season){
    const rows=(season.episodes||[]).map(ep=>`<div class="episode-row"><div class="episode-number">S${String(ep.season_number).padStart(2,'0')}E${String(ep.episode_number).padStart(2,'0')}</div><div><strong>${esc(ep.title)}</strong><div class="episode-status ${esc(ep.status)}">${esc(ep.status.replaceAll('_',' '))}${ep.air_date?` · ${esc(ep.air_date)}`:''}</div></div><div>${ep.status==='missing'?`<button class="button" data-find-episode="${ep.episode_number}">Find releases</button>`:''}</div></div>`).join('');
    document.getElementById('season-content').innerHTML=`<div class="section-title">Episodes</div><div class="episode-list">${rows||'<div class="empty">No episodes returned by Sonarr.</div>'}</div>`;
    document.querySelectorAll('[data-find-episode]').forEach(btn=>btn.addEventListener('click',()=>findEpisodeReleases(season,Number(btn.dataset.findEpisode))));
  }
  function rejectionBlock(rel){const primary=rel.primary_rejection;const details=(rel.rejection_details||[]).slice(1);if(!primary)return '';return `<div class="release-reasons"><strong>${esc(rel.rejection_label||'Unavailable')}</strong><br>${esc(primary.message||'Release unavailable')}${details.length?`<details><summary>Details</summary>${details.map(item=>`<div>${esc(item.message||'')}</div>`).join('')}</details>`:''}</div>`;}
  function releaseRows(data){return (data.releases||[]).map(rel=>`<article class="release" data-eligible="${rel.eligible?'true':'false'}"><div><h4>${esc(rel.title)}</h4><div class="release-meta"><span>${rel.size_gb.toFixed(2)} GB</span><span>${esc(rel.quality)}</span>${rel.source?`<span>${esc(rel.source)}</span>`:''}${rel.codec?`<span>${esc(rel.codec)}</span>`:''}<span>${rel.seeders??'?'} seeders</span><span>${esc(rel.indexer)}</span></div>${rejectionBlock(rel)}</div><button class="button ${rel.eligible?'primary':''}" data-tv-release-token="${rel.eligible?esc(rel.release_token||''):''}" ${rel.eligible?'':'disabled'}>${rel.eligible?'Download':esc(rel.rejection_label||'Unavailable')}</button></article>`).join('')||'<div class="empty">No releases were returned.</div>';}
  async function findSeasonPacks(season){
    const area=document.getElementById('season-content');area.innerHTML='<div class="empty">Searching Sonarr for season packs...</div>';
    try{const data=await api(`catalog/tv/${season.tmdb_id}/seasons/${season.season_number}/releases`);area.innerHTML=`<div class="section-title">Season pack releases</div><div class="release-summary">Household presets · maximum ${Number(data.maximum_size_gb).toFixed(1)} GB</div><div class="releases">${releaseRows(data)}</div>`;bindTvReleaseButtons();}catch(error){area.innerHTML=`<div class="empty">${esc(error.message)}</div>`;}
  }
  async function findEpisodeReleases(season,episodeNumber){
    const area=document.getElementById('season-content');area.innerHTML='<div class="empty">Searching Sonarr for episode releases...</div>';
    try{const data=await api(`catalog/tv/${season.tmdb_id}/seasons/${season.season_number}/episodes/${episodeNumber}/releases`);area.innerHTML=`<button class="button" id="back-to-episodes">← Back to ${esc(season.season_name)}</button><div class="section-title">S${String(season.season_number).padStart(2,'0')}E${String(episodeNumber).padStart(2,'0')} · ${esc(data.episode_title)}</div><div class="release-summary">Household presets · maximum ${Number(data.maximum_size_gb).toFixed(1)} GB</div><div class="releases">${releaseRows(data)}</div>`;document.getElementById('back-to-episodes').addEventListener('click',()=>renderEpisodes(season));bindTvReleaseButtons();}catch(error){area.innerHTML=`<div class="empty">${esc(error.message)}</div>`;}
  }
  function bindTvReleaseButtons(){document.querySelectorAll('[data-tv-release-token]').forEach(btn=>{if(btn.disabled||!btn.dataset.tvReleaseToken)return;btn.addEventListener('click',()=>grabTvRelease(btn.dataset.tvReleaseToken,btn));});}
  async function grabTvRelease(token,button){button.disabled=true;button.textContent='Sending to Sonarr...';try{await api('tv/releases/grab',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({release_token:token})});toast('TV release sent to Sonarr.');if(tvSeasonContext){const refreshed=await api(`catalog/tv/${tvSeasonContext.season.tmdb_id}/seasons/${tvSeasonContext.season.season_number}`);tvSeasonContext.season=refreshed;renderEpisodes(refreshed);}}catch(error){toast(error.message);button.disabled=false;button.textContent='Download';}}
</script>
"""

if "season-action-card" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _RELEASE_UI + "\n</body>")
