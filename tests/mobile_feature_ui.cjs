const assert = require('node:assert/strict');
const fs = require('node:fs');
const {JSDOM, VirtualConsole} = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const errors = [], observers = [];
const vc = new VirtualConsole();
vc.on('jsdomError', e => { if (!/Could not parse CSS/.test(e.message)) errors.push(e); });
const pending = [], deadlines = new Map();
let timerId = 100000, requests = 0; const calls=[];const pendingTV=[];
const movie = {tmdb_id:653574,title:'The Donut King',original_title:'The Donut King',year:'2020',rating:7,
  release_date:'2020-10-30',genres:[],cast:[],overview:'Documentary',context:'browse',lifecycle:{state:'released_unknown'},lifecycle_message:{},library:{}};
const release = {title:'The Donut King 2020 1080p WEBRip',quality:'1080p',indexer:'IPTorrents',size_gb:1.53,seeders:169,eligible:true,release_token:'opaque',flags:[],policy_rejections:[]};
let win, releaseScrolls=0;
const dom = new JSDOM(html, {url:'https://ha.test/api/hassio_ingress/test-token/', runScripts:'dangerously', pretendToBeVisual:true, virtualConsole:vc,
  beforeParse(w) {
    Object.defineProperty(w,'innerWidth',{value:Number(process.argv[3]||390)});Object.defineProperty(w,'innerHeight',{value:Number(process.argv[4]||844)});win=w;const Observer=w.MutationObserver;w.MutationObserver=class extends Observer{constructor(fn){super(fn);observers.push(this);}};w.IntersectionObserver=class{observe(){} unobserve(){} disconnect(){}};w.Headers=Headers;w.AbortController=AbortController;
    w.matchMedia=()=>({matches:w.innerWidth<=760,addEventListener(){},removeEventListener(){}});
    w.scrollTo=()=>{};
    w.HTMLElement.prototype.scrollIntoView=function(){};
    w.HTMLElement.prototype.scrollTo=function(options){if(this.classList?.contains('dialog')){this.scrollTop=Number(options?.top||0);releaseScrolls++;}};
    const set=w.setTimeout.bind(w), clear=w.clearTimeout.bind(w);
    w.setTimeout=(fn,ms,...args)=>{if(ms===22000){const id=timerId++;deadlines.set(id,fn);return id;}return set(fn,ms,...args);};
    w.clearTimeout=id=>{if(deadlines.has(id))deadlines.delete(id);else clear(id);};
    w.fetch=async (url, options={})=>{
      calls.push({url:String(url),options});assert(!String(url).startsWith('/'), 'API must remain relative for HA ingress');
      if (/movies\/\d+\/releases/.test(url)) {
        requests++;
        return await new Promise((resolve,reject)=>pending.push({url,options,resolve:data=>resolve({ok:true,json:async()=>data}),reject,
          fail:status=>resolve({ok:false,status,json:async()=>({detail:'Provider failed'})})}));
      }
      if (/catalog\/tv\/\d+\/seasons\/\d+\/releases/.test(url))return await new Promise((resolve,reject)=>pendingTV.push({options,resolve:data=>resolve({ok:true,json:async()=>data}),reject}));
      let body={};
      if(String(url).startsWith('api/download-history'))body={items:[{id:1,title:'Movie',display_title:'Movie',media_type:'movie',requested_by_name:'Stuart',status:'queued',display_status:'Queued',display_timestamp:'2026-10-11T22:24:00Z',size_bytes:1610612736,size_is_estimate:true,display_progress:null},{id:2,display_title:'Series · S02E03',media_type:'tv',requested_by_name:'Lee',status:'failed',display_status:'Failed',status_message:'Actual indexer failure',display_timestamp:'2026-10-10T11:00:00Z'}],page:1,total_pages:1,total:2};
      else if(url==='api/critic-ratings')body={scores:{'653574':87,'42':70},configured:true};
      else if(url==='api/users/me')body={id:'test',role:'admin',display_name:'Test',auth_source:'ingress'};
      else if(/catalog\/movies\/\d+$/.test(url))body={...movie,tmdb_id:Number(String(url).split('/').at(-1))};
      else if(/catalog\/tv\/\d+$/.test(url))body={...movie,tmdb_id:42,id:42,name:'TV',media_type:'tv',seasons:[{season_number:1,name:'Season 1',air_date:'2020-01-01'}]};
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

(async()=>{
 await wait(30);
 const downloads=calls.filter(c=>c.options.method==='POST'&&/request|grab/.test(c.url));
 await evaluate('openMovie(653574)');await wait(20);
 assert.equal(requests,1,'Opening details automatically discovers once');
 assert(!q('choose-release'));
 assert(!q('detail').querySelector('.lifecycle-card'),'Old movies have no availability warning');
 assert(q('auto-request').closest('.release-actions-bottom'));
 assert(!q('auto-request').classList.contains('primary'));
 assert(q('auto-request').compareDocumentPosition(q('release-area')) & win.Node.DOCUMENT_POSITION_PRECEDING);
 assert.equal(q('modal').querySelectorAll('[data-detail-view]').length,3);
 assert(q('mobile-modal-back').closest('.detail-controls'));
 assert(q('close-modal').closest('.detail-controls'));
 await evaluate('findReleases(false,true)');assert.equal(requests,1,'Duplicate concurrent discovery is suppressed');
 pending[0].resolve({releases:[release],search_message:'1 match'});await wait(35);
 assert(q('detail').textContent.includes('Rotten Tomatoes: 87%'));
 assert.equal(q('release-area').querySelectorAll('.best-badge').length,1);
 assert.equal(calls.filter(c=>c.options.method==='POST'&&/request|grab/.test(c.url)).length,downloads.length,'Discovery never submits downloads');
 win.document.querySelector('.toast-region').replaceChildren();evaluate("toast('Request sent.');toast('Request sent.');toast('Provider failed.','error')");
 assert.equal(win.document.querySelectorAll('.toast').length,2,'Repeated notification is deduplicated');
 assert(!win.document.querySelector('.toast-region').closest('nav'));
 win.document.querySelector('.toast-dismiss').click();assert.equal(win.document.querySelectorAll('.toast').length,1);
 q('close-modal').click();await wait(20);assert(q('modal').classList.contains('hidden'));
 // Invalid RT bounds leave the sheet open without committing values.
 q('mobile-filter-toggle').click();q('mobile-rt-min').value='90';q('mobile-rt-max').value='10';q('mobile-filter-apply').click();
 assert.equal(q('mobile-filter-sheet').getAttribute('aria-hidden'),'false');
 q('mobile-rt-min').value='70';q('mobile-rt-max').value='100';q('mobile-filter-apply').click();await wait(20);
 assert.equal(q('mobile-filter-sheet').getAttribute('aria-hidden'),'true');
 assert(calls.some(c=>/catalog\/movies\?/.test(c.url)&&/rt_min=70/.test(c.url)&&/rt_max=100/.test(c.url)));
 q('mobile-filter-toggle').click();assert.equal(q('mobile-rt-min').value,'70');
 q('mobile-filter-clear').click();q('mobile-filter-apply').click();await wait(20);
 assert.equal(q('rt-min').value,'');assert.equal(q('rt-max').value,'');
 await evaluate("switchMedia('tv')");q('mobile-filter-toggle').click();q('mobile-rt-min').value='0';q('mobile-filter-apply').click();await wait(20);
 assert(calls.some(c=>/catalog\/tv\?/.test(c.url)&&/rt_min=0/.test(c.url)),'TV supports independent score bound including zero');
 await evaluate('openTv(42)');await wait(15);assert.equal(pendingTV.length,1,'TV details automatically search the selected season');
 assert.equal(q('auto-tv-releases').getAttribute('aria-busy'),'true');
 q('auto-tv-season').dispatchEvent(new win.Event('change'));await wait(5);assert.equal(pendingTV.length,1,'Duplicate TV searches are suppressed');
 pendingTV[0].resolve({releases:[{...release,release_token:'tv-opaque'}]});await wait(20);
 assert.equal(q('auto-tv-releases').getAttribute('aria-busy'),'false');assert(q('auto-tv-releases').querySelector('.best-tv-request'));
 q('auto-tv-releases').querySelector('[data-tv-refresh]').click();await wait(5);assert.equal(pendingTV.length,2);
 q('close-modal').click();await wait(5);assert(pendingTV[1].options.signal.aborted,'Closing TV details cancels discovery');
 pendingTV[1].resolve({releases:[release]});await wait(10);assert(q('modal').classList.contains('hidden'));
 evaluate("showView('downloads')");await wait(25);
 assert.equal(q('downloads').querySelectorAll('th').length,6);
 assert.equal(q('downloads').querySelectorAll('[data-history-id]').length,2);
 assert.equal(q('downloads').querySelectorAll('.panel.download').length,0);
 assert(!q('downloads').textContent.includes('0%'),'Unknown progress is not 0%');
 q('downloads').querySelectorAll('.history-title')[1].click();
 assert(!q('history-details-2').classList.contains('hidden'));
 assert(q('history-details-2').textContent.includes('Actual indexer failure'));
 assert(q('history-details-2').textContent.includes('TV Show'));
 assert.equal(q('downloads').querySelector('.history-title').getAttribute('aria-expanded'),'false');
 observers.forEach(o=>o.disconnect());await wait(20);
 assert.equal(errors.length,0,errors.map(e=>e.stack||String(e)).join('\n'));
 console.log('Mobile feature UI passed: automatic discovery, dark bottom action, navigation, notifications, RT filters for movies/TV and expanded history.');
 dom.window.close();
})().catch(error=>{console.error(error.stack);observers.forEach(o=>o.disconnect());dom.window.close();process.exitCode=1;});
