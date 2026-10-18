const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const html=execFileSync(process.env.MEDIAHUB_TEST_PYTHON||'python',['-c','from mediahub.app.watchlist_main import main; print(main.INDEX_HTML)'],{encoding:'utf8',maxBuffer:2e6});
const items=[{id:12,external_id:'123',media_type:'movie',display_title:'A very long movie title with a substantial descriptive subtitle for mobile layout testing',title:'Example',created_at:'2026-10-12T01:00:00Z',requested_by_name:'Stuart',requested_by_id:'stu',status:'failed',display_status:'Failed',attempt_count:3,size_bytes:1600000000,size_is_estimate:true,failure:{explanation:'Radarr rejected this release. Review quality preferences.',integration:'Radarr',category:'rejected'},retry_supported:true,lifecycle:{manager:'Not confirmed',client:'Not confirmed',import:'Not confirmed',library:'Not confirmed'}},
 {id:13,media_type:'tv',display_title:'Series · S02E03',created_at:'2026-10-11T01:00:00Z',requested_by_name:'Lee',status:'downloading',display_status:'Downloading',display_progress:64,attempt_count:1}];
const movie={tmdb_id:123,title:'Example',year:'2020',rating:8,genres:[],cast:[],overview:'Test movie',context:'browse',lifecycle:{},lifecycle_message:{},library:{}};
async function fixture(page,viewport,configured=true){
 await page.setViewportSize(viewport);const errors=[],calls=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('http://mediahub.test/**',async route=>{
  const request=route.request(),url=new URL(request.url()),path=url.pathname;calls.push({path,search:url.search,method:request.method()});
  if(path==='/host')return route.fulfill({contentType:'text/html',body:'<style>body{margin:0}header{height:56px}iframe{width:100%;height:calc(100dvh - 56px);border:0;display:block}</style><header>Home Assistant</header><iframe src="/api/hassio_ingress/test/"></iframe>'});
  if(path==='/api/hassio_ingress/test/')return route.fulfill({contentType:'text/html',body:html});
  if(path.endsWith('.png'))return route.fulfill({contentType:'image/png',body:Buffer.from(fs.readFileSync('mediahub/app/assets/'+(path.includes('logo')?'mediahub-logo':'mediahub-icon')+'.png.b64','utf8'),'base64')});
  let body={};
  if(path.endsWith('users/me'))body={id:'stu',role:'admin',display_name:'Stuart',auth_source:'home_assistant'};
  else if(path.endsWith('/users')&&request.method()==='POST')return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Username already in use'})});
  else if(path.endsWith('/users'))body=[{id:'stu',username:'stu',display_name:'Stuart',role:'admin',active:true,auth_source:'home_assistant',home_assistant_identity:true,mediahub_login_enabled:false,last_seen_at:'2026-10-12T01:00:00Z'}];
  else if(path.endsWith('/ratings/availability'))body={sources:Object.fromEntries(['tmdb','imdb','rt_critic','rt_audience','metacritic','letterboxd','trakt'].map(id=>[id,{enabled:id==='tmdb'||configured,verified_cached:0,reason:id==='tmdb'?'':configured?'Configured; awaiting enrichment.':'MDBList is required for this source.'}]))};
  else if(path.endsWith('/download-management'))body={items,page:1,total:2,total_pages:1,requesters:[{id:'stu',name:'Stuart'},{id:'lee',name:'Lee'}]};
  else if(path.endsWith('/attempts'))body={items:[items[0],{...items[0],id:11},{...items[0],id:10}],page:1,total:3,total_pages:1};
  else if(path.includes('/genres'))body={genres:[{id:18,name:'Drama'}]};
  else if(path.includes('/discovery/')||path.endsWith('/catalog/movies'))body={movies:[movie],shows:[],page:1,total_results:1,total_pages:1};
  else if(path.endsWith('catalog/movies/123'))body=movie;
  else if(path.includes('/movies/123/releases'))body={releases:[{title:'Oversized release',eligible:false,indexer:'Example',quality:'1080p',seeders:8,size_gb:8,policy_rejections:['Exceeds maximum size'],flags:[]}],search_message:'One rejected release'};
  else if(path.endsWith('/ratings'))body={configured,ratings:{'123':{tmdb:{status:'verified',value:8,provider:'tmdb'}}}};
  else if(path.endsWith('download-presets')||path.endsWith('setup/presets'))body={movies:{allowed_resolutions:['1080p'],maximum_size_gb:3,minimum_seeders:1},tv:{allowed_resolutions:['1080p']},discovery:{}};
  else if(path.endsWith('/setup'))body={connections:{services:[]},settings:{},discovery:{services:[]}};
  else if(path.endsWith('/watchlist'))body=[];
  return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto('http://mediahub.test/host');const app=page.frameLocator('iframe');
 try{await expect(app.locator('.movie').first()).toBeVisible();}catch(error){throw new Error(error.message+'\n'+JSON.stringify({errors,calls}));}
 return {app,errors,calls};
}
async function navigate(app,name){await app.locator('.mobile-menu>summary').click();await app.locator('.mobile-menu-items button').filter({hasText:new RegExp('^'+name+'$')}).click();}
for(const viewport of [{width:375,height:667},{width:390,height:844},{width:393,height:852},{width:430,height:932},{width:768,height:1024},{width:1920,height:1080}]){
 test(`Downloads and Users ${viewport.width}x${viewport.height}`,async({page})=>{
  const {app,errors,calls}=await fixture(page,viewport);await navigate(app,'Downloads');
  if(viewport.width<=760){await expect(app.locator('.management-mobile')).toBeVisible();await expect(app.locator('.management-desktop')).toBeHidden();
   const item=app.locator('[data-group="12"]');expect(await item.evaluate(el=>el.getBoundingClientRect().height)).toBeLessThan(185);
   await item.locator('summary').first().click();await expect(item.locator('.attempt-entry')).toHaveCount(3);
   await expect(item).toContainText('Radarr rejected');await expect(item).toContainText('3 recorded attempts');
  }else{await expect(app.locator('.management-desktop')).toBeVisible();await expect(app.locator('.management-mobile')).toBeHidden();await expect(app.locator('.management-table th')).toHaveCount(8);await app.locator('[data-desktop-group="12"]').click();await expect(app.locator('[data-desktop-details="12"] .attempt-entry')).toHaveCount(3);}
  await app.locator('#history-sort').selectOption('oldest');await expect.poll(()=>calls.some(c=>c.path.endsWith('/download-management')&&c.search.includes('sort=oldest'))).toBe(true);
  expect(await app.locator('body').evaluate(el=>el.scrollWidth>innerWidth)).toBe(false);
  await page.screenshot({path:`test-results/screenshots/downloads-${viewport.width}x${viewport.height}.png`});
  await navigate(app,'Users');await expect(app.locator('.user-card')).toHaveCount(1);await expect(app.locator('#create-user-form')).toBeHidden();
  const rewrites=await app.locator('#user-list').evaluate(async el=>{let count=0;const observer=new MutationObserver(()=>count++);observer.observe(el,{childList:true,subtree:true});for(let i=0;i<5;i++)decorateDualLoginUsers();await new Promise(resolve=>setTimeout(resolve,20));observer.disconnect();return count;});
  expect(rewrites).toBe(0);
  await app.locator('.account-create-panel>summary').click();await app.locator('#new-display-name').fill('Lee');await app.locator('#new-username').fill('lee');await app.locator('#new-password').fill('longpassword123');await app.locator('#create-user-form button').click();await expect(app.locator('#user-message')).toContainText('Username already in use');
  await expect(app.locator('#create-user-form button')).toBeEnabled();expect(calls.filter(c=>c.path.endsWith('/users')&&c.method==='POST').length).toBe(1);
  await app.locator('.account-create-panel>summary').click();await page.screenshot({path:`test-results/screenshots/users-${viewport.width}x${viewport.height}.png`});
  expect(await app.locator('body').evaluate(el=>el.scrollWidth>innerWidth)).toBe(false);expect(errors).toEqual([]);expect(page.url()).toBe('http://mediahub.test/host');
 });
}
test('Unavailable rating source is disabled and does not turn into no matches',async({page})=>{
 const {app,calls}=await fixture(page,{width:390,height:844},false);await app.locator('#mobile-filter-toggle').click();
 await expect(app.locator('[data-rating-source="rt_audience"] [data-rating-enabled]')).toBeDisabled();await expect(app.locator('[data-rating-source="rt_audience"]')).toContainText('MDBList is required');
 await app.locator('[data-rating-source="tmdb"] [data-rating-enabled]').check();await app.locator('[data-rating-source="tmdb"] [data-rating-min]').fill('7');await app.locator('#mobile-filter-apply').click();await expect(app.locator('#mobile-filter-sheet')).toHaveAttribute('aria-hidden','true');
 expect(calls.filter(c=>c.path.includes('/discovery/')).some(c=>c.search.includes('rt_audience'))).toBe(false);
 await app.locator('#mobile-filter-toggle').click();await expect(app.locator('[data-rating-source="tmdb"] [data-rating-min]')).toHaveValue('7');
 await app.locator('#mobile-filter-clear').click();await app.locator('#mobile-filter-apply').click();await expect(app.locator('#mobile-filter-toggle')).not.toContainText('1');
});
test('Keyboard reduced viewport and rejected releases stay usable',async({page})=>{
 const {app,errors}=await fixture(page,{width:390,height:844});await app.locator('#mobile-filter-toggle').click();
 await app.locator('body').evaluate(()=>{const vv=new EventTarget();vv.height=330;vv.offsetTop=0;Object.defineProperty(window,'visualViewport',{value:vv,configurable:true});window.dispatchEvent(new Event('resize'));});
 await app.locator('[data-rating-source="tmdb"] [data-rating-min]').focus();
 const geometry=await app.locator('.mobile-filter-panel').evaluate(el=>({height:el.getBoundingClientRect().height,footer:el.querySelector('.mobile-filter-actions').getBoundingClientRect().bottom}));
 expect(geometry.height).toBeLessThanOrEqual(330);expect(geometry.footer).toBeLessThanOrEqual(330);
 await app.locator('.filter-keyboard-dismiss').click();expect(await app.locator('body').evaluate(()=>document.activeElement.tagName)).not.toBe('INPUT');
 await app.locator('#mobile-filter-close').click();await app.locator('[data-id="123"]').click();await expect(app.locator('#release-area')).toHaveAttribute('data-outcome','NONE_ELIGIBLE');await expect(app.locator('#auto-request')).toBeDisabled();
 await expect(app.locator('.release-state-summary')).toContainText('0 eligible · 1 rejected');await app.locator('.unavailable-releases summary').click();await expect(app.locator('.unavailable-releases')).toContainText('Exceeds maximum size');
 await app.locator('#close-modal').click();expect(errors).toEqual([]);expect(page.url()).toBe('http://mediahub.test/host');
});

test('Birdman eligible releases and safe discovery diagnostics on iPhone',async({page})=>{
 const {app,errors}=await fixture(page,{width:390,height:844});
 await page.route('**/catalog/movies/123',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({...movie,title:'Birdman or (The Unexpected Virtue of Ignorance)',year:'2014'})}));
 const releases=[['Birdman 2014 1080p BluRay x265',1.8,74],['Birdman 2014 1080p BluRay x265-LAMA',1.8,13],['Birdman 2014 1080p BluRay DDP5.1 x265 10bit-LAMA',2.7,31]].map(([title,size_gb,seeders],i)=>({title,size_gb,seeders,eligible:true,quality:'1080p',indexer:'Fixture',release_token:'opaque-'+i}));
 await page.route('**/movies/123/releases**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({releases,search_message:'3 qualifying releases found.',discovery_diagnostics:{raw_results:3,title_mismatches:0,category_exclusions:0,metadata_exclusions:0,duplicates_removed:0,household_exclusions:0,eligible_releases:3,indexers_returned:1,queries:[{query:'Birdman 2014',scope:'broad',category_ids:[],pages:1,raw:3,outcome:'success'}],prowlarr_status:'success'}})}));
 await app.locator('[data-id="123"]').click();await expect(app.locator('#release-area [data-eligible="true"]')).toHaveCount(3);await expect(app.locator('#auto-request')).toBeEnabled();
 await app.locator('.discovery-diagnostics>summary').click();await app.locator('.discovery-diagnostics details>summary').filter({hasText:'Query plan'}).click();await expect(app.locator('.discovery-diagnostics')).toContainText('Birdman 2014');await expect(app.locator('.discovery-diagnostics')).toContainText('Eligible releases');
 expect(await app.locator('#detail').evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(false);
 await page.screenshot({path:'test-results/screenshots/birdman-discovery-390x844.png'});await app.locator('#close-modal').click();expect(errors).toEqual([]);
});

test('Partial documentary search stays explicit and diagnostics remain collapsed on iPhone',async({page})=>{
 const {app,errors}=await fixture(page,{width:390,height:844});
 const release={title:'Beyond Utopia (2023) 1080p WEBRip 5 1-LAMA',size_gb:2.13,seeders:5,quality:'1080p',indexer:'Fixture',eligible:true,release_token:'opaque-doc'};
 await page.route('**/movies/123/releases**',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({releases:[release],search_complete:false,search_status:'partial',search_state:'partial_results',search_message:'Partial results. 1 eligible releases found so far. Search coverage is incomplete; refresh to retry.',discovery_diagnostics:{bounded:true,failed_queries:1,raw_results:1,queries:[{query:'Verified Alias 2023',scope:'broad',outcome:'timeout',pages:0,raw:0,elapsed_ms:3000,attempts:1}],release_exclusions:[{release:release.title,source:'Fixture',category:[{id:5070,name:'TV/Documentary'}],quality:'1080p',size_bytes:2.13*1024**3,seeders:5,identity:'strong',status:'eligible',reasons:[]}]}})}));
 await app.locator('[data-id="123"]').click();
 await expect(app.locator('#release-area .release-state-summary')).toContainText('Partial results.');
 await expect(app.locator('#release-area .release-state-summary')).toBeVisible();
 await expect(app.locator('.discovery-diagnostics')).not.toHaveAttribute('open','');
 await expect(app.locator('#release-area [data-eligible="true"]')).toHaveCount(1);
 await app.locator('.discovery-diagnostics>summary').click();
 await app.locator('.discovery-diagnostics details>summary').filter({hasText:'Individual release'}).click();
 await expect(app.locator('.discovery-diagnostics')).toContainText('TV/Documentary');
 await expect(app.locator('.discovery-diagnostics')).toContainText('eligible');
 expect(await app.locator('#detail').evaluate(el=>el.scrollWidth>el.clientWidth)).toBe(false);
 await page.screenshot({path:'test-results/screenshots/documentary-partial-390x844.png'});
 expect(errors).toEqual([]);
});
