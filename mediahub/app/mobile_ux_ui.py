from __future__ import annotations

from . import main, mobile_live_ui, preset_main

app = mobile_live_ui.app
app.version = "0.14.0-dev"

_MOBILE_UX_UI = r"""
<style>
  .mobile-filter-sheet{display:none}
  .mobile-filter-sheet[aria-hidden="false"]{display:block;position:fixed;inset:0;z-index:95;background:rgba(0,0,0,.68)}
  .mobile-filter-panel{position:absolute;left:0;right:0;bottom:0;max-height:min(78dvh,720px);overflow:auto;background:#111620;border:1px solid var(--border);border-radius:22px 22px 0 0;padding:18px 18px calc(18px + env(safe-area-inset-bottom));box-shadow:0 -24px 70px rgba(0,0,0,.5)}
  .mobile-filter-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.mobile-filter-head h3{margin:0}.mobile-filter-actions{display:flex;gap:10px;position:sticky;bottom:0;background:#111620;padding-top:14px}
  .mobile-filter-fields{display:grid;grid-template-columns:1fr 1fr;gap:11px}.mobile-filter-fields .genre-field{grid-column:1/-1}
  .mobile-filter-toggle{align-items:center;gap:8px}.filter-count{min-width:22px;height:22px;border-radius:99px;display:inline-grid;place-items:center;background:#2c3445;font-size:.7rem}
  .detail-skeleton{min-height:70dvh}.detail-skeleton .skeleton.hero{aspect-ratio:16/9;height:auto}.detail-skeleton .skeleton.cast{height:132px}
  .mobile-modal-back{display:none}.mobile-modal-title{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:850}
  .household-policy-summary{margin:10px 0 14px;padding:10px 12px;border:1px solid var(--border);border-radius:12px;background:#0d1119;color:var(--muted);font-size:.78rem;line-height:1.45}
  .mobile-bottom-nav.is-suspended{display:none!important}
  body.modal-open{overflow:hidden}
  @media(max-width:760px){
    body{min-height:100dvh;padding-bottom:calc(88px + env(safe-area-inset-bottom))}
    .topbar{min-height:54px;padding-block:7px}.topbar .brand img{width:124px}.shell{padding-top:8px;padding-bottom:calc(92px + env(safe-area-inset-bottom))}
    #browse-view>.hero{display:none!important}.media-switch{margin-top:6px;width:100%}.media-switch button{flex:1;padding:8px 10px}
    .searchbar{position:relative;margin:10px 0 8px}.searchbar input{padding-right:42px}.searchbar .button.primary{display:none}.mobile-search-clear{position:absolute;right:8px;top:50%;transform:translateY(-50%);width:34px;height:34px;border:0;border-radius:50%;background:transparent;color:var(--muted);font-size:1.1rem}
    .filters{margin:0 -2px 10px;padding:0 2px 4px;scrollbar-width:none;overscroll-behavior-inline:contain;scroll-snap-type:x proximity}.filters::-webkit-scrollbar{display:none}.filters .chip{flex:0 0 auto;scroll-snap-align:start;padding:7px 11px}
    .discovery-tools{display:none!important}.mobile-filter-toggle{display:inline-flex!important;width:auto;margin:0 0 12px;padding:9px 13px}
    .heading{margin:14px 0 12px}.heading p{display:none}.movies{gap:11px}.movie-title{margin-top:7px;font-size:.92rem}
    .modal{padding:0;place-items:stretch;background:#080a0f}.dialog{width:100%;height:100dvh;max-height:100dvh;border:0;border-radius:0;overflow:auto;padding-top:48px;overscroll-behavior:contain}.close{position:fixed;right:10px;top:max(8px,env(safe-area-inset-top));z-index:110}.mobile-modal-back{display:inline-flex;position:fixed;left:10px;top:max(8px,env(safe-area-inset-top));z-index:110;border:1px solid var(--border);border-radius:999px;background:rgba(8,10,15,.88);color:white;padding:8px 11px;align-items:center;gap:6px}.detail-hero{min-height:250px;padding:20px}.detail-body{padding:0 16px calc(24px + env(safe-area-inset-bottom))}.detail-copy h2{font-size:2rem}.actions{margin:12px 0}.cast-grid,.cast-list,.cast-strip{display:flex!important;overflow-x:auto;gap:10px;scroll-snap-type:x proximity;padding-bottom:8px;scrollbar-width:none}.cast-grid::-webkit-scrollbar,.cast-list::-webkit-scrollbar,.cast-strip::-webkit-scrollbar{display:none}.cast-grid>* ,.cast-list>* ,.cast-strip>*{min-width:124px;max-width:124px;scroll-snap-align:start}.cast-card img{aspect-ratio:2/3;width:100%;object-fit:cover;border-radius:10px}
    .release{padding:11px}.release h4{font-size:.87rem;line-height:1.35}.release-meta{font-size:.74rem}.release .button{min-height:42px}.unavailable-releases summary{padding:10px 0;font-weight:850}
    .mobile-bottom-nav{bottom:max(8px,env(safe-area-inset-bottom));left:10px;right:10px}.mobile-bottom-nav button{min-height:44px}
    .setup-grid,.preset-groups,.user-layout{grid-template-columns:1fr!important}.service,.panel{min-width:0}.field input,.field select{min-width:0}
  }
  @media(max-width:760px) and (orientation:landscape){.dialog{height:100dvh;max-height:100dvh}.detail-hero{min-height:210px}.mobile-filter-panel{max-height:86dvh}}
  @media(prefers-reduced-motion:reduce){*,*:before,*:after{scroll-behavior:auto!important;animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important}}
</style>
<script>
(function(){
  if(window.MEDIAHUB_MOBILE_UX_V014)return;window.MEDIAHUB_MOBILE_UX_V014=true;
  const q=id=>document.getElementById(id);
  const mobile=()=>matchMedia('(max-width:760px)').matches;
  const modal=q('modal'),dialog=modal?.querySelector('.dialog'),detail=q('detail'),nav=document.querySelector('.mobile-bottom-nav');
  const browseState={scrollY:0,detailScroll:0,detailKind:null,detailId:null};
  let detailGeneration=0;
  const detailCache=new Map();

  // Remove duplicate mobile branding while retaining a compact app identity in the sticky header.
  document.querySelectorAll('#browse-view .brand,.mobile-brand,.secondary-brand').forEach(el=>el.remove());

  // Search has one debounced owner in v0.14. Stop propagation from the input before older bubble listeners can fire.
  const search=q('search'),searchForm=q('search-form');
  let searchTimer=null,searchGeneration=0;
  if(search){
    const clear=document.createElement('button');clear.type='button';clear.className='mobile-search-clear';clear.setAttribute('aria-label','Clear search');clear.textContent='×';searchForm?.appendChild(clear);
    clear.addEventListener('click',()=>{search.value='';search.dispatchEvent(new Event('input',{bubbles:true}));search.focus();});
    search.addEventListener('input',event=>{
      if(!window.MEDIAHUB_MOBILE_UX_V014)return;
      event.stopImmediatePropagation();clearTimeout(searchTimer);const generation=++searchGeneration;
      searchTimer=setTimeout(()=>{if(generation===searchGeneration)searchForm?.requestSubmit();},450);
    },true);
  }

  // Proper staged mobile filter sheet: edit locally, apply once.
  const discovery=document.querySelector('.discovery-tools');
  const filterToggle=q('mobile-filter-toggle');
  let staged=null,filterOrigin=null;
  function currentFilters(){return{genre:q('genre-filter')?.value||'',yearFrom:q('year-from')?.value||'',yearTo:q('year-to')?.value||'',ratingFrom:q('rating-from')?.value||'',ratingTo:q('rating-to')?.value||''};}
  function filterCount(v=currentFilters()){return Object.values(v).filter(Boolean).length;}
  function updateFilterButton(){if(!filterToggle)return;const count=filterCount();filterToggle.innerHTML=`Filters${count?` <span class="filter-count">${count}</span>`:''}`;}
  if(discovery&&filterToggle&&!q('mobile-filter-sheet')){
    const sheet=document.createElement('div');sheet.id='mobile-filter-sheet';sheet.className='mobile-filter-sheet';sheet.setAttribute('aria-hidden','true');sheet.innerHTML='<div class="mobile-filter-panel" role="dialog" aria-modal="true" aria-labelledby="mobile-filter-title"><div class="mobile-filter-head"><h3 id="mobile-filter-title">Filters</h3><button type="button" class="button" id="mobile-filter-close">Close</button></div><div class="mobile-filter-fields" id="mobile-filter-fields"></div><div class="mobile-filter-actions"><button type="button" class="button" id="mobile-filter-clear">Clear filters</button><button type="button" class="button primary" id="mobile-filter-apply">Apply filters</button></div></div>';
    document.body.appendChild(sheet);const fields=q('mobile-filter-fields');
    [...discovery.querySelectorAll('label.field')].forEach(label=>fields.appendChild(label.cloneNode(true)));
    function fillStaged(){staged=currentFilters();[['genre-filter','genre'],['year-from','yearFrom'],['year-to','yearTo'],['rating-from','ratingFrom'],['rating-to','ratingTo']].forEach(([id,key])=>{const el=fields.querySelector('#'+id);if(el)el.value=staged[key];});}
    function closeSheet(){sheet.setAttribute('aria-hidden','true');document.body.classList.remove('modal-open');filterOrigin?.focus();}
    filterToggle.addEventListener('click',()=>{filterOrigin=filterToggle;fillStaged();sheet.setAttribute('aria-hidden','false');document.body.classList.add('modal-open');setTimeout(()=>q('mobile-filter-close')?.focus(),0);});
    q('mobile-filter-close').addEventListener('click',closeSheet);sheet.addEventListener('click',e=>{if(e.target===sheet)closeSheet();});
    q('mobile-filter-clear').addEventListener('click',()=>{fields.querySelectorAll('select,input').forEach(el=>el.value='');});
    q('mobile-filter-apply').addEventListener('click',()=>{[['genre-filter'],['year-from'],['year-to'],['rating-from'],['rating-to']].forEach(([id])=>{const source=fields.querySelector('#'+id),target=q(id);if(source&&target)target.value=source.value;});updateFilterButton();q('genre-filter')?.dispatchEvent(new Event('change',{bubbles:true}));closeSheet();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&sheet.getAttribute('aria-hidden')==='false'){e.preventDefault();closeSheet();}});
  }
  updateFilterButton();

  function suspendNav(value){nav?.classList.toggle('is-suspended',!!value);document.body.classList.toggle('modal-open',!!value);}
  function modalTop(){if(dialog)dialog.scrollTop=0;}
  function ensureBack(){if(!modal||q('mobile-modal-back'))return;const back=document.createElement('button');back.type='button';back.id='mobile-modal-back';back.className='mobile-modal-back';back.innerHTML='‹ <span>Back</span>';back.addEventListener('click',()=>{if(window.MEDIAHUB_PARENT_DETAIL_RESTORE){window.MEDIAHUB_PARENT_DETAIL_RESTORE();return;}q('close-modal')?.click();});modal.appendChild(back);}
  ensureBack();
  new MutationObserver(()=>{const open=modal&&!modal.classList.contains('hidden');if(mobile())suspendNav(open);if(!open)window.MEDIAHUB_PARENT_DETAIL_RESTORE=null;}).observe(modal||document.body,{attributes:true,attributeFilter:['class']});

  // Structured detail shell is first meaningful loading UI and owns scroll state.
  function skeleton(){return '<div class="detail-skeleton" aria-busy="true" aria-label="Loading details"><div class="skeleton hero"></div><div class="skeleton line short"></div><div class="skeleton line"></div><div class="skeleton actions"></div><div class="skeleton line"></div><div class="skeleton line"></div><div class="skeleton cast"></div></div>';}
  const nativeOpenMovie=window.openMovie;
  if(typeof nativeOpenMovie==='function')window.openMovie=async function(id,trigger){const generation=++detailGeneration;browseState.scrollY=window.scrollY;browseState.detailId=id;browseState.detailKind='movie';if(detail){detail.innerHTML=skeleton();}modal?.classList.remove('hidden');suspendNav(mobile());modalTop();try{if(detailCache.has('movie:'+id)&&generation===detailGeneration){state.movie=detailCache.get('movie:'+id);renderMovieDetail(state.movie);modalTop();return;}await nativeOpenMovie(id,trigger);if(generation!==detailGeneration)return;if(state?.movie)detailCache.set('movie:'+id,state.movie);modalTop();}catch(error){if(generation===detailGeneration)throw error;}};
  const nativeOpenTv=window.openTv;
  if(typeof nativeOpenTv==='function')window.openTv=async function(id,trigger){const generation=++detailGeneration;browseState.scrollY=window.scrollY;browseState.detailId=id;browseState.detailKind='tv';if(detail)detail.innerHTML=skeleton();modal?.classList.remove('hidden');suspendNav(mobile());modalTop();try{await nativeOpenTv(id,trigger);if(generation!==detailGeneration)return;if(state?.movie)detailCache.set('tv:'+id,state.movie);modalTop();}catch(error){if(generation===detailGeneration)throw error;}};

  // Parent detail scroll is preserved when entering a release selector and restored on Back.
  document.addEventListener('click',event=>{const target=event.target.closest('#choose-release,[data-find-season-releases],[data-find-episode-releases],.choose-release');if(!target||!dialog)return;browseState.detailScroll=dialog.scrollTop;const snapshot=detail?.innerHTML;const title=browseState.detailKind;window.MEDIAHUB_PARENT_DETAIL_RESTORE=()=>{if(snapshot&&detail){detail.innerHTML=snapshot;dialog.scrollTop=browseState.detailScroll;}window.MEDIAHUB_PARENT_DETAIL_RESTORE=null;};},true);

  const nativeClose=window.closeModal;
  if(typeof nativeClose==='function')window.closeModal=function(){detailGeneration++;window.MEDIAHUB_PARENT_DETAIL_RESTORE=null;const result=nativeClose();suspendNav(false);requestAnimationFrame(()=>window.scrollTo({top:browseState.scrollY||0,behavior:'instant'}));return result;};

  // Requester release policy is read-only. Replace legacy rule markup at source and read current preset values dynamically.
  window.rules=function(){const p=window.MEDIAHUB_CURRENT_MOVIE_PRESETS||{};const allowed=p.allowed_resolutions||['1080p','720p'];return{maximum_size_gb:Number(p.maximum_size_gb||3),minimum_seeders:Number(p.minimum_seeders??1),quality_mode:allowed.length===1?(allowed[0]==='1080p'?'1080p_only':'720p_only'):'720p_and_1080p'};};
  window.rulesHtml=function(){const p=window.MEDIAHUB_CURRENT_MOVIE_PRESETS;const summary=p?`${(p.allowed_resolutions||[]).join(' / ')} · max ${Number(p.maximum_size_gb||0):g} GB · minimum ${Number(p.minimum_seeders||0)} seeder${Number(p.minimum_seeders||0)===1?'':'s'}`:'Household download presets applied';return `<div class="household-policy-summary"><strong>Household download presets applied</strong><br>${summary}</div>`;};
  async function loadMoviePresetSummary(){try{const data=await api('setup/presets');window.MEDIAHUB_CURRENT_MOVIE_PRESETS=data.movies||null;}catch(_){window.MEDIAHUB_CURRENT_MOVIE_PRESETS=null;}}
  loadMoviePresetSummary();

  // Legacy requester rule containers must never remain active in release selection.
  function removeLegacyRules(){document.querySelectorAll('#release-area .release-rules,.release-rules[data-request-rules],#release-area [data-rule-field]').forEach(el=>el.remove());}
  new MutationObserver(()=>{removeLegacyRules();updateFilterButton();document.querySelectorAll('.poster img,.cast-card img').forEach(img=>{if(!img.loading)img.loading='lazy';});}).observe(document.body,{subtree:true,childList:true});removeLegacyRules();

  // Disable competing release buttons while one grab is submitting.
  document.addEventListener('click',event=>{const button=event.target.closest('#release-area .button,[data-release-token]');if(!button)return;const area=q('release-area');if(!area||button.disabled)return;requestAnimationFrame(()=>{if(/requesting|download/i.test(button.textContent||'')){area.querySelectorAll('button').forEach(other=>{if(other!==button)other.disabled=true;});}});},true);

  // Avoid bottom-nav/keyboard collision on iOS dynamic visual viewport.
  const vv=window.visualViewport;function keyboardState(){if(!vv||!mobile())return;const keyboard=Math.max(0,window.innerHeight-vv.height-vv.offsetTop)>120;nav?.classList.toggle('is-suspended',keyboard||(!modal?.classList.contains('hidden')));document.documentElement.style.setProperty('--mediahub-vvh',`${vv.height}px`);}vv?.addEventListener('resize',keyboardState);vv?.addEventListener('scroll',keyboardState);keyboardState();
})();
</script>
"""

# Fix the one Python-format-looking token in the raw JS before injection.
_MOBILE_UX_UI = _MOBILE_UX_UI.replace("${Number(p.maximum_size_gb||0):g}", "${Number(p.maximum_size_gb||0).toLocaleString(undefined,{maximumFractionDigits:2})}")

if "MEDIAHUB_MOBILE_UX_V014" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _MOBILE_UX_UI + "\n</body>")
