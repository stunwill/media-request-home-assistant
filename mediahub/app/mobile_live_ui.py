from __future__ import annotations

from . import main, release_identity_main

app = release_identity_main.app
app.version = "0.13.0-dev"

_MOBILE_UI = r"""
<style>
  .mobile-filter-toggle{display:none}.mobile-bottom-nav{display:none}.release.best-match{border-color:rgba(124,92,255,.7);box-shadow:0 0 0 1px rgba(124,92,255,.25)}.best-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 8px;border-radius:999px;background:rgba(124,92,255,.16);color:#c8bdff;font-size:.68rem;font-weight:900;letter-spacing:.05em}.download-group{display:grid;gap:12px;margin-bottom:22px}.download-group h3{margin:0 0 2px;font-size:1rem}.download-live-meta{font-size:.78rem;color:var(--muted);margin-top:6px}.detail-skeleton{padding:28px;display:grid;gap:16px}.skeleton{border-radius:12px;background:linear-gradient(90deg,#171d28,#252c38,#171d28);background-size:200% 100%;animation:mediahub-shimmer 1.2s infinite}.skeleton.hero{height:210px}.skeleton.line{height:18px}.skeleton.line.short{width:55%}.skeleton.actions{height:50px}@keyframes mediahub-shimmer{to{background-position:-200% 0}}
  @media(max-width:760px){
    body{padding-bottom:78px}.hero{display:none}.shell{padding-top:14px}.searchbar{margin:12px 0}.searchbar input{min-height:46px}.discovery-tools{display:none}.mobile-filter-toggle{display:inline-flex;width:100%;justify-content:center;margin:-8px 0 16px}.detail-body{padding-top:8px}.actions{gap:8px}.actions .button:not(.primary){flex:1 1 auto;padding:9px 12px}.release{grid-template-columns:1fr;gap:10px;padding:12px}.release .button{width:100%;min-height:44px}.release-meta{gap:7px}.cast-grid,.cast-list{display:flex!important;overflow-x:auto;gap:10px;scroll-snap-type:x proximity;padding-bottom:6px}.cast-grid>* ,.cast-list>*{min-width:132px;scroll-snap-align:start}.topbar nav{display:none}.mobile-bottom-nav{display:flex;position:fixed;left:12px;right:12px;bottom:max(10px,env(safe-area-inset-bottom));z-index:70;background:rgba(16,20,29,.96);backdrop-filter:blur(18px);border:1px solid var(--border);border-radius:18px;padding:8px;gap:6px}.mobile-bottom-nav button{flex:1;border:0;border-radius:12px;padding:11px 8px;background:transparent;color:var(--muted);font-weight:800}.mobile-bottom-nav button.active{background:#252b38;color:white}.movies{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.poster{border-radius:12px}
  }
</style>
<script>
(function(){
  if(window.MEDIAHUB_MOBILE_LIVE_V013)return;window.MEDIAHUB_MOBILE_LIVE_V013=true;
  const search=document.getElementById('search');
  const searchForm=document.getElementById('search-form');
  let debounceTimer=null;
  let searchGeneration=0;
  const runDebounced=()=>{clearTimeout(debounceTimer);const generation=++searchGeneration;debounceTimer=setTimeout(()=>{if(generation!==searchGeneration)return;searchForm?.requestSubmit();},450);};
  search?.addEventListener('input',runDebounced);

  const discovery=document.querySelector('.discovery-tools');
  if(discovery&&!document.getElementById('mobile-filter-toggle')){
    discovery.insertAdjacentHTML('beforebegin','<button type="button" class="button mobile-filter-toggle" id="mobile-filter-toggle">Filters</button>');
    document.getElementById('mobile-filter-toggle')?.addEventListener('click',()=>{discovery.style.display=discovery.style.display==='grid'?'none':'grid';});
  }

  const originalOpenMovie=window.openMovie;
  if(typeof originalOpenMovie==='function'){
    window.openMovie=async function(id){const modal=document.getElementById('modal');modal.classList.remove('hidden');document.getElementById('detail').innerHTML='<div class="detail-skeleton"><div class="skeleton hero"></div><div class="skeleton line short"></div><div class="skeleton line"></div><div class="skeleton actions"></div><div class="skeleton line"></div><div class="skeleton line"></div></div>';return originalOpenMovie(id);};
  }

  function compactReleaseArea(){
    const area=document.getElementById('release-area');if(!area)return;
    const releases=[...area.querySelectorAll('.release')];
    releases.forEach(el=>{el.classList.remove('best-match');el.querySelector('.best-badge')?.remove();});
    const eligible=releases.filter(el=>el.dataset.eligible==='true'&&!el.querySelector('button[disabled]'));
    if(eligible.length){eligible[0].classList.add('best-match');const h=eligible[0].querySelector('h4');if(h)h.insertAdjacentHTML('beforebegin','<span class="best-badge">BEST MATCH</span>');}
  }
  const observer=new MutationObserver(compactReleaseArea);observer.observe(document.body,{subtree:true,childList:true});

  let downloadPoll=null;
  function scheduleDownloads(delay=4000){clearTimeout(downloadPoll);if(state?.view!=='downloads'||document.hidden)return;downloadPoll=setTimeout(async()=>{try{await loadDownloads(true);}finally{scheduleDownloads(4000);}},delay);}
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(downloadPoll);else if(state?.view==='downloads')scheduleDownloads(500);});
  document.querySelector('nav button[data-view="downloads"]')?.addEventListener('click',()=>scheduleDownloads(500));

  const nav=document.createElement('div');nav.className='mobile-bottom-nav';nav.innerHTML='<button data-mobile-view="browse">Browse</button><button data-mobile-view="downloads">Downloads</button><button data-mobile-view="setup" id="mobile-setup">Setup</button>';
  document.body.appendChild(nav);
  nav.querySelectorAll('button[data-mobile-view]').forEach(button=>button.addEventListener('click',()=>{showView(button.dataset.mobileView);nav.querySelectorAll('button').forEach(b=>b.classList.toggle('active',b===button));if(button.dataset.mobileView==='downloads')scheduleDownloads(300);}));
  const role=state?.user?.role; if(role&&role!=='admin')document.getElementById('mobile-setup')?.remove();
})();
</script>
"""

if "MEDIAHUB_MOBILE_LIVE_V013" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _MOBILE_UI + "\n</body>")
