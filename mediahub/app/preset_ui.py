from __future__ import annotations

from . import main, preset_main

app = preset_main.app

_PRESET_UI = r"""
<style>
  .setup-section-title{grid-column:1/-1;margin:8px 0 0;padding:4px 2px}.setup-section-title h3{margin:0;font-size:1.15rem}.setup-section-title p{margin:5px 0 0;color:var(--muted);font-size:.82rem}
  .preset-card{grid-column:1/-1}.preset-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.preset-group{border:1px solid var(--border);border-radius:14px;background:#0c1018;padding:14px;display:grid;gap:11px}.preset-group h4{margin:0}.check-row{display:flex;align-items:center;gap:8px;color:#c8d0dd;font-size:.8rem}.check-row input{width:auto}.preset-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.preset-note{font-size:.76rem;color:var(--muted);line-height:1.45}.preset-help{font-size:.72rem;color:var(--muted);margin-top:-5px}.preset-message{min-height:20px;margin-top:8px}.preset-message.success{color:var(--success)}.preset-message.error{color:#ef6c83}
  @media(max-width:900px){.preset-groups{grid-template-columns:1fr}}@media(max-width:760px){.preset-actions{display:grid}.preset-actions .button{width:100%}.preset-group{padding:13px}.preset-card{margin-bottom:12px}}
</style>
<script>
(function(){
  if(window.MEDIAHUB_DOWNLOAD_PRESETS_UI)return;window.MEDIAHUB_DOWNLOAD_PRESETS_UI=true;
  let adminPresets=null;
  const q=id=>document.getElementById(id);

  const setupHeading=document.querySelector('#setup-view>.heading h2');
  const setupCopy=document.querySelector('#setup-view>.heading p');
  if(setupHeading)setupHeading.textContent='Setup';
  if(setupCopy)setupCopy.textContent='Administrator-only service connections and household download policy.';

  const setupGrid=document.querySelector('#setup-view .setup-grid');
  if(setupGrid&&!q('service-connections-heading')){
    setupGrid.insertAdjacentHTML('afterbegin','<div class="setup-section-title" id="service-connections-heading"><h3>Service Connections</h3><p>Connect MediaHub to metadata, request, download and library services.</p></div>');
  }
  q('tv-download-policy')?.remove();
  if(setupGrid&&!q('mediahub-presets')){
    setupGrid.insertAdjacentHTML('beforeend',`<div class="setup-section-title" id="presets-heading"><h3>Download Presets</h3><p>Household rules used by MediaHub for every release search and acquisition.</p></div><section class="service preset-card" id="mediahub-presets"><div class="service-head"><span>Download Presets</span><span class="badge">Admin only</span></div><div class="preset-groups"><div class="preset-group"><h4>Movies</h4><div class="preset-note">Allowed quality</div><label class="check-row"><input id="movie-1080" type="checkbox">1080p</label><label class="check-row"><input id="movie-720" type="checkbox">720p</label><label class="field">Maximum Movie release size (GB)<input id="movie-max-size" type="number" min="0.1" max="100" step="0.1" inputmode="decimal"></label><div class="preset-help">Larger releases are excluded by MediaHub before acquisition.</div><label class="field">Minimum seeders<input id="movie-min-seeders" type="number" min="0" max="10000" inputmode="numeric"></label><div class="preset-help">Releases with fewer known seeders are excluded.</div><label class="check-row"><input id="movie-recent-fallback" type="checkbox">Allow temporary lower-quality releases for recent titles</label><label class="field">Fallback window (days)<input id="movie-recent-days" type="number" min="1" max="730" inputmode="numeric"></label></div><div class="preset-group"><h4>TV Shows</h4><div class="preset-note">Allowed quality</div><label class="check-row"><input id="tv-1080" type="checkbox">1080p</label><label class="check-row"><input id="tv-720" type="checkbox">720p</label><label class="field">Maximum season pack (GB)<input id="tv-season-max-preset" type="number" min="0.1" max="100" step="0.1" inputmode="decimal"></label><label class="field">Maximum episode (GB)<input id="tv-episode-max-preset" type="number" min="0.1" max="20" step="0.1" inputmode="decimal"></label><label class="field">Minimum seeders<input id="tv-min-seeders" type="number" min="0" max="10000" inputmode="numeric"></label><div class="preset-help">Sonarr may still reject a release because of its own quality profile or library state.</div></div></div><details style="margin-top:14px"><summary>Discovery preset</summary><div style="margin-top:12px"><label class="field">Catalogue language<select id="preset-language"><option value="en">English only</option><option value="all">Any original language</option></select></label></div></details><div class="preset-actions"><button class="button primary" id="save-presets" type="button">Save download presets</button><button class="button" id="reset-presets" type="button">Reset download presets to defaults</button></div><div class="preset-message" id="preset-message" aria-live="polite"></div><div class="preset-note">Reset only affects download/discovery presets. Service Connections, credentials and users are not changed.</div></section>`);
  }

  function setPresetMessage(message,error=false){const el=q('preset-message');if(!el)return;el.textContent=message;el.classList.toggle('error',error);el.classList.toggle('success',!error&&!!message);}
  function presetRes(prefix){const values=[];if(q(`${prefix}-1080`)?.checked)values.push('1080p');if(q(`${prefix}-720`)?.checked)values.push('720p');return values;}
  function fillPresets(p){adminPresets=p;if(q('preset-language'))q('preset-language').value=p.discovery.original_language;q('movie-1080').checked=p.movies.allowed_resolutions.includes('1080p');q('movie-720').checked=p.movies.allowed_resolutions.includes('720p');q('movie-max-size').value=p.movies.maximum_size_gb;q('movie-min-seeders').value=p.movies.minimum_seeders;q('movie-recent-fallback').checked=p.movies.recent_release_fallback_enabled;q('movie-recent-days').value=p.movies.recent_release_fallback_days;q('tv-1080').checked=p.tv.allowed_resolutions.includes('1080p');q('tv-720').checked=p.tv.allowed_resolutions.includes('720p');q('tv-season-max-preset').value=p.tv.maximum_season_size_gb;q('tv-episode-max-preset').value=p.tv.maximum_episode_size_gb;q('tv-min-seeders').value=p.tv.minimum_seeders;window.MEDIAHUB_CURRENT_MOVIE_PRESETS=p.movies;}
  async function loadPresets(){if(!state?.user||state.user.role!=='admin')return;try{fillPresets(await api('setup/presets'));setPresetMessage('');}catch(error){setPresetMessage(error.message,true);}}
  function positiveNumber(id,label){const value=Number(q(id)?.value);if(!Number.isFinite(value)||value<=0)throw new Error(`${label} must be greater than 0.`);return value;}
  function wholeNumber(id,label){const value=Number(q(id)?.value);if(!Number.isInteger(value)||value<0)throw new Error(`${label} must be 0 or greater.`);return value;}
  async function savePresets(){try{const movieRes=presetRes('movie'),tvRes=presetRes('tv');if(!movieRes.length)throw new Error('At least one Movie resolution must be selected.');if(!tvRes.length)throw new Error('At least one TV resolution must be selected.');const payload={discovery:{original_language:q('preset-language')?.value||'en'},movies:{allowed_resolutions:movieRes,maximum_size_gb:positiveNumber('movie-max-size','Maximum Movie release size'),minimum_seeders:wholeNumber('movie-min-seeders','Movie minimum seeders'),recent_release_fallback_enabled:q('movie-recent-fallback').checked,recent_release_fallback_days:positiveNumber('movie-recent-days','Fallback window')},tv:{allowed_resolutions:tvRes,maximum_season_size_gb:positiveNumber('tv-season-max-preset','Maximum TV season size'),maximum_episode_size_gb:positiveNumber('tv-episode-max-preset','Maximum TV episode size'),minimum_seeders:wholeNumber('tv-min-seeders','TV minimum seeders')}};fillPresets(await api('setup/presets',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}));setPresetMessage('✓ Download presets saved');toast('Download presets saved.');}catch(error){setPresetMessage(error.message,true);}}
  async function resetPresets(){try{fillPresets(await api('setup/presets/reset',{method:'POST'}));setPresetMessage('✓ Download preset defaults restored');toast('Download presets reset to defaults.');}catch(error){setPresetMessage(error.message,true);}}
  q('save-presets')?.addEventListener('click',savePresets);q('reset-presets')?.addEventListener('click',resetPresets);
  document.querySelectorAll('nav button[data-view="setup"],.mobile-bottom-nav button[data-mobile-view="setup"]').forEach(button=>button.addEventListener('click',()=>setTimeout(loadPresets,0)));
  if(state?.user?.role==='admin')setTimeout(loadPresets,0);
})();
</script>
"""

if "MEDIAHUB_DOWNLOAD_PRESETS_UI" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _PRESET_UI + "\n</body>")
