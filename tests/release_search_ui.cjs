const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const errors = [], observers = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if (!/Could not parse CSS/.test(e.message)) errors.push(e); });
const pending = [], deadlines = new Map();
let timerId = 100000, requests = 0;
const movie = {tmdb_id:653574,title:'The Donut King',original_title:'The Donut King',year:'2020',rating:7,
  release_date:'2020-10-30',genres:[],cast:[],overview:'Documentary',context:'browse',lifecycle:{state:'released_unknown'},lifecycle_message:{},library:{}};
const release = {title:'The Donut King 2020 1080p WEBRip',quality:'1080p',indexer:'IPTorrents',size_gb:1.53,seeders:169,eligible:true,release_token:'opaque',flags:[],policy_rejections:[]};
let win, releaseScrolls=0;
const dom = new JSDOM(html, {url:'https://ha.test/api/hassio_ingress/test-token/', runScripts:'dangerously', pretendToBeVisual:true, virtualConsole:vc,
  beforeParse(w) {
    win=w;const Observer=w.MutationObserver;w.MutationObserver=class extends Observer{constructor(fn){super(fn);observers.push(this);}};w.IntersectionObserver=class{observe(){} unobserve(){} disconnect(){}};w.Headers=Headers;w.AbortController=AbortController;
    w.matchMedia=()=>({matches:true,addEventListener(){},removeEventListener(){}});
    w.scrollTo=()=>{};
    w.HTMLElement.prototype.scrollIntoView=function(){};
    w.HTMLElement.prototype.scrollTo=function(options){if(this.classList?.contains('dialog')){this.scrollTop=Number(options?.top||0);releaseScrolls++;}};
    const set=w.setTimeout.bind(w), clear=w.clearTimeout.bind(w);
    w.setTimeout=(fn,ms,...args)=>{if(ms===22000){const id=timerId++;deadlines.set(id,fn);return id;}return set(fn,ms,...args);};
    w.clearTimeout=id=>{if(deadlines.has(id))deadlines.delete(id);else clear(id);};
    w.fetch=async (url, options={})=>{
      assert(!String(url).startsWith('/'), 'API must remain relative for HA ingress');
      if (/movies\/\d+\/releases/.test(url)) {
        requests++;
        return await new Promise((resolve,reject)=>pending.push({url,options,resolve:data=>resolve({ok:true,json:async()=>data}),reject,
          fail:status=>resolve({ok:false,status,json:async()=>({detail:'Provider failed'})})}));
      }
      let body={};
      if(url==='api/users/me')body={id:'test',role:'admin',display_name:'Test',auth_source:'ingress'};
      else if(/catalog\/movies\/\d+$/.test(url))body={...movie,tmdb_id:Number(String(url).split('/').at(-1))};
      else if(/catalog\/tv\/\d+$/.test(url))body={...movie,tmdb_id:42,id:42,name:'TV',media_type:'tv',seasons:[]};
      else if(/genres/.test(url))body=[];
      else if(/download-presets/.test(url))body={movies:{allowed_resolutions:['1080p','720p'],maximum_size_gb:3,minimum_seeders:1}};
      else if(/catalog\/(movies|tv)/.test(url))body={movies:[],shows:[],page:1,total_pages:1,total_results:0};
      else if(/setup$/.test(url))body={connections:{services:[],connected:0},settings:{},discovery:{services:[]}};
      else if(/presets/.test(url))body={movies:{allowed_resolutions:['1080p'],maximum_size_gb:3,minimum_seeders:1},tv:{allowed_resolutions:['1080p'],maximum_season_size_gb:10,maximum_episode_size_gb:1,minimum_seeders:1},discovery:{original_language:'en'}};
      else if(/downloads|users|options/.test(url))body=[];
      return {ok:true,json:async()=>body};
    };
    w.addEventListener('error',e=>errors.push(e.error||e.message));
    w.addEventListener('unhandledrejection',e=>errors.push(e.reason));
  }
});
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const evaluate=source=>win.eval(source);
const q=id=>win.document.getElementById(id);
async function open(id=653574){await evaluate(`openMovie(${id})`);await wait(25);assert(!q('choose-release'));assert(q('auto-request'));evaluate('cancelReleaseSearch()');await wait(5);}
function start(){evaluate('cancelReleaseSearch()');const before=releaseScrolls,promise=evaluate('findReleases(false)');assert.equal(q('release-area').dataset.searchState,'SEARCHING');assert(q('cancel-release-search'));return {promise,request:pending.at(-1),area:q('release-area'),beforeScrolls:before};}
function terminal(area,status){assert.equal(area.dataset.searchState,status);assert.equal(area.getAttribute('aria-busy'),'false');assert(!area.textContent.includes('Searching Radarr'));}
(async()=>{
  await wait(30);
  await open();
  // Successful results and observer settling: a self-mutating observer would
  // starve this timer and CI's subprocess timeout would fail the test.
  let job=start();await wait(5);assert(releaseScrolls>job.beforeScrolls,'Choose a release must scroll the dialog to the release area');const resultScrolls=releaseScrolls;job.request.resolve({releases:[release],search_message:'1 qualifying release found.'});await job.promise;await wait(30);
  assert(releaseScrolls>resultScrolls,'Rendered release results must remain anchored in the release area');terminal(job.area,'SUCCESS');assert.equal(job.area.querySelectorAll('.best-badge').length,1);
  const observer=new win.MutationObserver(list=>{changes+=list.length;});let changes=0;observer.observe(job.area,{subtree:true,childList:true});await wait(40);assert.equal(changes,0);observer.disconnect();assert.equal(deadlines.size,0);
  // Identity evidence remains distinct from final household eligibility in ingress.
  job=start();job.request.resolve({releases:[release],search_complete:false,discovery_diagnostics:{
    prowlarr_status:'partial',failed_queries:1,final_unique_candidates:2,
    final_candidate_counts:{eligible:1,mediahub_policy:1},release_exclusions:[
      {release:'The Killing of Two Lovers 2020 1080p',identity:'accepted',identity_confidence:100,
       identity_evidence:['Strong title match','Alternate release year (2020 vs 2021)'],
       selected_movie_year:2021,torrent_release_year:2020,year_tolerated:true,
       status:'excluded',reasons:['Exceeds 3 GB Movie limit']},
      {release:'Uncertain movie',identity:'uncertain',identity_confidence:65,
       identity_evidence:['Year differs by 2','Additional verification required'],
       selected_movie_year:2021,torrent_release_year:2019,year_tolerated:false,status:'excluded'}]}});
  await job.promise;const diagnosticText=job.area.querySelector('.discovery-diagnostics').textContent;
  for(const text of ['Identity: accepted','Strong title match','Alternate release year (2020 vs 2021)',
    'Selected year: 2021','Torrent year: 2020','Year difference tolerated: Yes',
    'Final eligibility: excluded','Exceeds 3 GB Movie limit','Identity: uncertain',
    'Additional verification required','Partial coverage','Final decisions per unique candidate'])assert(diagnosticText.includes(text),text);
  // Zero releases.
  job=start();job.request.resolve({releases:[],search_message:'No matching releases.'});await job.promise;terminal(job.area,'NO_RESULTS');
  // Final browser deadline must abort even if fetch ignores abort and never settles.
  job=start();assert.equal(deadlines.size,1);[...deadlines.values()][0]();await job.promise;terminal(job.area,'TIMED_OUT');assert(job.request.options.signal.aborted);assert(q('retry-release-search'));assert(q('release-check-setup'));assert.equal(deadlines.size,0);
  job.request.resolve({releases:[release]});await wait(10);terminal(job.area,'TIMED_OUT');
  // Visible Cancel, Back, Close, navigation, page departure.
  for(const action of ['cancel','back','close','navigation','pagehide']){
    await open();job=start();await wait(5);assert(releaseScrolls>job.beforeScrolls);
    if(action==='cancel')q('cancel-release-search').click();
    if(action==='back')q('mobile-modal-back').click();
    if(action==='close')q('close-modal').click();
    if(action==='navigation')evaluate("showView('browse')");
    if(action==='pagehide')win.dispatchEvent(new win.Event('pagehide'));
    await job.promise;assert(job.request.options.signal.aborted,action);terminal(job.area,'CANCELLED');assert.equal(deadlines.size,0);
    if(['back','close','navigation'].includes(action)){assert(q('modal').classList.contains('hidden'));await wait(25);assert(!win.document.body.classList.contains('modal-open'));assert(!win.document.querySelector('.mobile-bottom-nav').classList.contains('is-suspended'));}
    job.request.resolve({releases:[release]});await wait(10);terminal(job.area,'CANCELLED');
  }
  // Replacement search must ignore stale results on the very same DOM node.
  await open();const old=start(),newer=start();await old.promise;assert(old.request.options.signal.aborted);old.request.resolve({releases:[release]});await wait(10);assert.equal(newer.area.dataset.searchState,'SEARCHING');newer.request.resolve({releases:[]});await newer.promise;terminal(newer.area,'NO_RESULTS');
  // Close A/open B and the old response completes late.
  const a=start();q('close-modal').click();await open(999);await a.promise;const bArea=q('release-area');a.request.resolve({releases:[release]});await wait(10);assert(!bArea.textContent.includes(release.title));assert.equal(evaluate('state.movie.tmdb_id'),999);
  // Opening another Movie directly also cancels a pending search.
  const switching=start();await open(123);await switching.promise;assert(switching.request.options.signal.aborted);
  // Movie-to-TV navigation cancels and cannot receive the late Movie result.
  await open();const tvSwitch=start();await evaluate('openTv(42)');await tvSwitch.promise;assert(tvSwitch.request.options.signal.aborted);tvSwitch.request.resolve({releases:[release]});await wait(20);assert.equal(evaluate('state.movie.media_type'),'tv');assert(!q('detail').textContent.includes(release.title));
  // Restored parent detail cannot be overwritten by the departed request.
  await open();const restoring=start();evaluate("window.MEDIAHUB_PARENT_DETAIL_RESTORE=()=>{document.getElementById('detail').innerHTML='<p id=restored-parent>Parent detail</p>';window.MEDIAHUB_PARENT_DETAIL_RESTORE=null;}");q('mobile-modal-back').click();await restoring.promise;restoring.request.resolve({releases:[release]});await wait(20);assert(q('restored-parent'));assert(restoring.request.options.signal.aborted);
  // All relevant HTTP terminal statuses.
  for(const status of [504,500,502,503]){await open();job=start();job.request.fail(status);await job.promise;terminal(job.area,status===504?'TIMED_OUT':'ERROR');assert(q('retry-release-search'));assert.equal(deadlines.size,0);}
  // Retry uses the current movie and ingress-relative route.
  q('retry-release-search').click();await wait(1);const retry=pending.at(-1);assert(retry.url.startsWith('api/movies/653574/releases'));evaluate('cancelReleaseSearch()');await wait(10);assert(retry.options.signal.aborted);
  observers.forEach(o=>o.disconnect());await wait(40);
  assert.equal(errors.length,0,errors.map(e=>e.stack||String(e)).join('\n'));
  console.log(`Composed mobile UI passed: ${requests} release requests, all terminal states, cancellation, stale responses, ingress URLs and observer settling.`);
  dom.window.close();
})().catch(error=>{console.error(error.stack);dom.window.close();process.exitCode=1;});
