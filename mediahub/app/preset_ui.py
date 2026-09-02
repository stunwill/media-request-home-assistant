from __future__ import annotations

from . import main, preset_main

app = preset_main.app

_PRESET_UI = r"""
<style>
  .setup-section-title{grid-column:1/-1;margin:8px 0 0;padding:4px 2px}.setup-section-title h3{margin:0;font-size:1.15rem}.setup-section-title p{margin:5px 0 0;color:var(--muted);font-size:.82rem}
  .preset-card{grid-column:1/-1}.preset-groups{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.preset-group{border:1px solid var(--border);border-radius:14px;background:#0c1018;padding:14px;display:grid;gap:11px}.preset-group h4{margin:0}.check-row{display:flex;align-items:center;gap:8px;color:#c8d0dd;font-size:.8rem}.check-row input{width:auto}.preset-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.preset-note{font-size:.76rem;color:var(--muted);line-height:1.5}
  @media(max-width:900px){.preset-groups{grid-template-columns:1fr}}
</style>
<script>
  let adminPresets=null;

  const setupHeading=document.querySelector('#setup-view>.heading h2');
  const setupCopy=document.querySelector('#setup-view>.heading p');
  if(setupHeading)setupHeading.textContent='Setup';
  if(setupCopy)setupCopy.textContent='Administrator-only service connections and household search/download presets.';

  const setupGrid=document.querySelector('#setup-view .setup-grid');
  if(setupGrid&&!document.getElementById('service-connections-heading')){
    setupGrid.insertAdjacentHTML('afterbegin','<div class="setup-section-title" id="service-connections-heading"><h3>Service Connections</h3><p>Connect MediaHub to metadata, request, download and library services. Credentials remain private.</p></div>');
    document.getElementById('tv-download-policy')?.remove();
    setupGrid.insertAdjacentHTML('beforeend',`<div class="setup-section-title" id="presets-heading"><h3>Presets</h3><p>Global defaults applied to every household search and release decision. Only administrators can edit these rules.</p></div><section class="service preset-card" id="mediahub-presets"><div class="service-head"><span>Search & Download Presets</span><span class="badge">Admin only</span></div><div class="preset-groups"><div class="preset-group"><h4>Discovery</h4><label class="field">Catalogue language<select id="preset-language"><option value="en">English only</option><option value="all">Any original language</option></select></label><div class="preset-note">English only filters Movies and TV Shows by TMDb original language, including search and infinite-scroll catalogue results.</div></div><div class="preset-group"><h4>Movies</h4><label class="check-row"><input id="movie-1080" type="checkbox">1080p allowed</label><label class="check-row"><input id="movie-720" type="checkbox">720p allowed</label><label class="field">Maximum movie size (GB)<input id="movie-max-size" type="number" min="0.1" max="100" step="0.1"></label><label class="field">Minimum seeders<input id="movie-min-seeders" type="number" min="0" max="10000"></label><label class="check-row"><input id="movie-recent-fallback" type="checkbox">Allow recent-release low-quality fallback</label><label class="field">Recent-release window (days)<input id="movie-recent-days" type="number" min="1" max="730"></label></div><div class="preset-group"><h4>TV Shows</h4><label class="check-row"><input id="tv-1080" type="checkbox">1080p allowed</label><label class="check-row"><input id="tv-720" type="checkbox">720p allowed</label><label class="field">Maximum season pack (GB)<input id="tv-season-max-preset" type="number" min="0.1" max="100" step="0.1"></label><label class="field">Maximum episode (GB)<input id="tv-episode-max-preset" type="number" min="0.1" max="20" step="0.1"></label><label class="field">Minimum seeders<input id="tv-min-seeders" type="number" min="0" max="10000"></label></div></div><div class="preset-actions"><button class="button primary" id="save-presets" type="button">Save presets</button><button class="button" id="reset-presets" type="button">Reset to defaults</button></div><div class="message" id="preset-message"></div><div class="preset-note">Security controls such as duplicate protection, opaque release tokens, credential redaction and role enforcement are intentionally not configurable.</div></section>`);
  }

  function setPresetMessage(message,error=false){const el=document.getElementById('preset-message');if(!el)return;el.textContent=message;el.classList.toggle('error',error);el.classList.toggle('success',!error&&!!message);}
  function presetRes(prefix){const values=[];if(document.getElementById(`${prefix}-1080`)?.checked)values.push('1080p');if(document.getElementById(`${prefix}-720`)?.checked)values.push('720p');return values;}
  function fillPresets(p){adminPresets=p;document.getElementById('preset-language').value=p.discovery.original_language;document.getElementById('movie-1080').checked=p.movies.allowed_resolutions.includes('1080p');document.getElementById('movie-720').checked=p.movies.allowed_resolutions.includes('720p');document.getElementById('movie-max-size').value=p.movies.maximum_size_gb;document.getElementById('movie-min-seeders').value=p.movies.minimum_seeders;document.getElementById('movie-recent-fallback').checked=p.movies.recent_release_fallback_enabled;document.getElementById('movie-recent-days').value=p.movies.recent_release_fallback_days;document.getElementById('tv-1080').checked=p.tv.allowed_resolutions.includes('1080p');document.getElementById('tv-720').checked=p.tv.allowed_resolutions.includes('720p');document.getElementById('tv-season-max-preset').value=p.tv.maximum_season_size_gb;document.getElementById('tv-episode-max-preset').value=p.tv.maximum_episode_size_gb;document.getElementById('tv-min-seeders').value=p.tv.minimum_seeders;}
  async function loadPresets(){try{fillPresets(await api('setup/presets'));setPresetMessage('');}catch(error){if(error.status!==403)setPresetMessage(error.message,true);}}
  async function savePresets(){const movieRes=presetRes('movie'),tvRes=presetRes('tv');if(!movieRes.length||!tvRes.length){setPresetMessage('Select at least one allowed resolution for Movies and TV Shows.',true);return;}const payload={discovery:{original_language:document.getElementById('preset-language').value},movies:{allowed_resolutions:movieRes,maximum_size_gb:Number(document.getElementById('movie-max-size').value),minimum_seeders:Number(document.getElementById('movie-min-seeders').value),recent_release_fallback_enabled:document.getElementById('movie-recent-fallback').checked,recent_release_fallback_days:Number(document.getElementById('movie-recent-days').value)},tv:{allowed_resolutions:tvRes,maximum_season_size_gb:Number(document.getElementById('tv-season-max-preset').value),maximum_episode_size_gb:Number(document.getElementById('tv-episode-max-preset').value),minimum_seeders:Number(document.getElementById('tv-min-seeders').value)}};try{fillPresets(await api('setup/presets',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}));setPresetMessage('Presets saved. New searches use these rules immediately.');toast('MediaHub presets saved.');}catch(error){setPresetMessage(error.message,true);}}
  async function resetPresets(){try{fillPresets(await api('setup/presets/reset',{method:'POST'}));setPresetMessage('Defaults restored.');toast('MediaHub presets reset to defaults.');}catch(error){setPresetMessage(error.message,true);}}
  document.getElementById('save-presets')?.addEventListener('click',savePresets);
  document.getElementById('reset-presets')?.addEventListener('click',resetPresets);
  document.querySelector('nav button[data-view="setup"]')?.addEventListener('click',()=>setTimeout(loadPresets,0));

  // Movie release rules are global administrator presets in v0.12. Requesters no longer
  // receive editable per-request size/seeder/quality controls that could contradict them.
  if(typeof rules==='function')rules=function(){return{maximum_size_gb:3,minimum_seeders:1,quality_mode:'720p_and_1080p'};};
  if(typeof rulesHtml==='function')rulesHtml=function(){return'<div class="release-summary">Household Movie download presets from Setup are applied automatically.</div>';};
</script>
"""

if "mediahub-presets" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _PRESET_UI + "\n</body>")
