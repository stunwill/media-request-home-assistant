const {test,expect}=require('@playwright/test');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const html=process.env.MEDIAHUB_TEST_HTML?fs.readFileSync(process.env.MEDIAHUB_TEST_HTML,'utf8'):execFileSync(process.env.MEDIAHUB_TEST_PYTHON||'python',['-c','from mediahub.app.watchlist_main import main; print(main.INDEX_HTML)'],{encoding:'utf8',maxBuffer:2e6});
test.use({viewport:{width:393,height:852},isMobile:true,hasTouch:true});
const movie={tmdb_id:123,title:'The Weight',year:'2026',rating:8,genres:[],cast:[],overview:'Synopsis '.repeat(120),context:'browse',lifecycle:{},lifecycle_message:{},library:{}};
async function fixture(page,{outcome='success',delay=0,searchDelay=0,count=25}={}){
 let releaseBatch=0;const calls=[],errors=[],paths=[];page.on('pageerror',e=>errors.push(e.message));
 if(process.env.MEDIAHUB_BASELINE_TRACE){
  page.on('console',msg=>{if(msg.text().startsWith('BASELINE_'))console.log(msg.text());});
  page.on('request',req=>{if(/movies\/123\/request$/.test(req.url()))console.log('BASELINE_network_request_observed');});
  await page.addInitScript(()=>{
   const before=window.fetch;window.fetch=function(url,...args){if(/movies\/123\/request$/.test(String(url)))console.log('BASELINE_fetch_invoked');return before.call(this,url,...args);};
   document.addEventListener('click',e=>{if(e.target.closest('[data-token]'))console.log('BASELINE_button_click_received');},true);
   for(const name of ['touchstart','touchend','pointerdown','pointerup','click'])document.addEventListener(name,e=>console.log('BASELINE_event_'+name+'_'+e.target.tagName+'_'+e.target.className),true);
   let mutations=0,reported=false;new MutationObserver(rows=>{if(!document.querySelector('[data-token]:disabled'))return;mutations+=rows.length;if(mutations>1000&&!reported){reported=true;console.log('BASELINE_pending_child_mutations_exceeded_1000');}}).observe(document,{subtree:true,childList:true});
  });
 }
 await page.route('http://mediahub.test/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname;
  paths.push(path);if(path==='/host')return route.fulfill({contentType:'text/html',body:'<meta name="viewport" content="width=device-width, initial-scale=1"><style>body{margin:0}header{height:56px}iframe{display:block;width:100%;height:calc(100dvh - 56px);border:0}</style><header>Home Assistant</header><iframe src="/api/hassio_ingress/test/"></iframe>'});
  if(path==='/api/hassio_ingress/test/')return route.fulfill({contentType:'text/html',body:html});
  if(path.endsWith('.png'))return route.fulfill({status:204});
  let body={};
  if(path.endsWith('users/me'))body={id:'test',role:'admin',display_name:'Tester',auth_source:'home_assistant',csrf_token:'fixture-csrf'};
  else if(path.includes('/genres'))body={genres:[]};
  else if(path.includes('/discovery/')||path.endsWith('/catalog/movies'))body={movies:[movie],shows:[],page:1,total_pages:1,total_results:1};
  else if(path.endsWith('catalog/movies/123'))body=movie;
  else if(path.endsWith('catalog/movies/124'))body={...movie,tmdb_id:124,title:'Another Movie'};
  else if(path.includes('/movies/123/releases')){await new Promise(r=>setTimeout(r,searchDelay));const batch=releaseBatch++;body={releases:Array.from({length:count},(_,i)=>({title:`The.Weight.2026.1080p.WEB-${i}`,eligible:true,release_token:batch?`fresh-release-token-${batch}-${i}`:`exact-release-token-${i}`,indexer:'Fixture',quality:'1080p',size_gb:2,seeders:12})),search_message:'Eligible releases'};}
  else if(path.endsWith('/movies/123/request')){
   calls.push({body:req.postDataJSON(),headers:req.headers()});
   if(outcome==='network')return route.abort('failed');
   if(outcome.startsWith('http'))return route.fulfill({status:Number(outcome.slice(4)),contentType:'application/json',body:JSON.stringify({detail:'secret-provider-url?apikey=private'})});await new Promise(r=>setTimeout(r,delay));
   return route.fulfill({status:outcome==='rejected'?409:200,contentType:'application/json',body:JSON.stringify(outcome==='rejected'?{detail:'Release selection expired. Refresh releases.'}:outcome==='storage'?{request:{status:'rejected'},storage:{accepted:false}}:outcome==='malformed'?{}:{request:{status:'queued',id:12}})});
  }
  else if(path.endsWith('/download-management'))body={items:calls.length?[{id:12,media_type:'movie',display_title:'The Weight',status:'queued',display_status:'Queued',attempt_count:1}]:[],page:1,total:calls.length,total_pages:1,requesters:[]};
  else if(path.endsWith('/ratings/availability'))body={sources:{}};
  else if(path.endsWith('/ratings'))body={configured:false,ratings:{}};
  else if(path.endsWith('download-presets')||path.endsWith('setup/presets'))body={movies:{allowed_resolutions:['1080p'],maximum_size_gb:3,minimum_seeders:1},tv:{allowed_resolutions:['1080p']},discovery:{}};
  else if(path.endsWith('/setup'))body={connections:{services:[]},settings:{},discovery:{services:[]}};
  return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 await page.goto('http://mediahub.test/host');const app=page.frameLocator('iframe');try{await app.locator('.movie').first().click({timeout:5000});}catch(e){throw Error(JSON.stringify({errors,paths})+e.message);}
 return {app,calls,errors};
}

async function titleTop(app){
 await app.locator('#modal .dialog').evaluate(el=>el.scrollTop=0);
 await expect(app.locator('#detail-title')).toBeInViewport();
 const geometry=await app.locator('#modal .dialog').evaluate(el=>({scroll:el.scrollTop,width:el.clientWidth,contentWidth:el.scrollWidth,title:document.getElementById('detail-title').getBoundingClientRect().top,toolbar:el.querySelector('.detail-toolbar').getBoundingClientRect().bottom}));
 expect(geometry.scroll).toBe(0);expect(geometry.contentWidth).toBeLessThanOrEqual(geometry.width);expect(geometry.title).toBeGreaterThanOrEqual(geometry.toolbar);
}
async function hit(button){return button.evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));});}
for(const viewport of [{width:393,height:852},{width:852,height:393},{width:320,height:740},{width:768,height:1024},{width:1440,height:900}]){
 test.describe(`${viewport.width}x${viewport.height}`,()=>{
 test.use({viewport,isMobile:viewport.width<768,hasTouch:viewport.width<1024});
 test(`eligible tap, repeated taps, scroll and rejection ${viewport.width}x${viewport.height}`,async({page,browserName})=>{
  await page.setViewportSize(viewport);const {app,calls,errors}=await fixture(page,{outcome:'rejected',delay:700});
  const b=app.locator('[data-token]').first();await expect(b).toBeVisible();await b.scrollIntoViewIfNeeded();expect(await hit(b)).toBe(true);
  await (viewport.width<1024?b.tap():b.click());await expect(b).toContainText('Sending');await expect(b).toHaveAttribute('aria-busy','true');await expect(b).toBeDisabled();
  // Dispatch bypasses the native disabled guard to exercise the shared submission guard as well.
  await b.evaluate(el=>{for(let i=0;i<6;i++)el.dispatchEvent(new MouseEvent('click',{bubbles:true}));});
  await expect.poll(()=>calls.length).toBe(1);expect(calls[0].body.release_token).toBe('exact-release-token-0');expect(calls[0].headers['x-csrf-token']).toBe('fixture-csrf');expect(calls[0].headers['x-mediahub-correlation-id']).toBeTruthy();
  await expect(app.locator('.release-feedback[role="alert"]')).toContainText('selection expired');await expect(b).toBeEnabled();await expect(b).not.toHaveAttribute('aria-busy','true');
  // Pending UI must never change policy eligibility, the best card, or its badge.
  await expect(app.locator('.best-badge')).toHaveCount(1);await expect(app.locator('.release').first()).toHaveAttribute('data-eligible','true');
  const changes=await app.locator('#detail').evaluate(async el=>{let n=0;const o=new MutationObserver(rows=>n+=rows.length);o.observe(el,{childList:true,subtree:true});await new Promise(r=>setTimeout(r,100));o.disconnect();return n;});expect(changes).toBe(0);
  await titleTop(app);fs.mkdirSync('test-results/screenshots',{recursive:true});await page.screenshot({path:`test-results/screenshots/release-${browserName}-${viewport.width}x${viewport.height}.png`});const browse=app.locator('[data-detail-view="browse"]');expect(await hit(browse)).toBe(true);await browse.click();await expect(app.locator('#modal')).toHaveClass(/hidden/);expect(errors).toEqual([]);expect(page.url()).toBe('http://mediahub.test/host');
 });
 });
}
test('accepted exact request appears in Downloads',async({page})=>{
 const {app,calls,errors}=await fixture(page,{delay:300});await app.locator('[data-token]').first().click();
 await expect(app.locator('#downloads-view')).toBeVisible();await expect(app.locator('#downloads')).toContainText('The Weight');await expect(app.locator('#downloads')).toContainText('Queued');await expect(app.locator('.toast')).toContainText('request accepted');expect(calls).toHaveLength(1);expect(errors).toEqual([]);
 const trace=await app.locator('body').evaluate(()=>window.MEDIAHUB_DOWNLOAD_DIAGNOSTICS());expect(trace.map(x=>x.event)).toEqual(['interaction_received','request_started','request_completed','state_cleanup']);expect(JSON.stringify(trace)).not.toMatch(/exact-token|fixture-csrf|Tester/);
});
for(const outcome of ['storage','malformed'])test(`HTTP 200 ${outcome} is not false success`,async({page})=>{
 const {app,calls}=await fixture(page,{outcome});const b=app.locator('[data-token]').first();await b.click();await expect(app.locator('.release-feedback[role="alert"]')).toBeVisible();await expect(app.locator('.toast')).not.toContainText('request accepted');await expect(app.locator('#modal')).not.toHaveClass(/hidden/);await expect(b).toBeEnabled();expect(calls).toHaveLength(1);
});
test('expired release recovery discovers fresh choices before explicit retry',async({page})=>{
 const {app,calls}=await fixture(page,{outcome:'rejected'});await app.locator('[data-token]').first().click();await app.locator('.release-feedback button').filter({hasText:'Refresh releases'}).click();await expect(app.locator('[data-token]').first()).toHaveText('Download');expect(calls).toHaveLength(1);
 await app.locator('[data-token]').first().click();await expect.poll(()=>calls.length).toBe(2);expect(calls[1].body.release_token).not.toBe(calls[0].body.release_token);await expect(app.locator('.release-feedback[role="alert"]')).toBeVisible();
});
test('timeout cleans processing, keeps navigation live and never silently retries',async({page})=>{
 const {app,calls,errors}=await fixture(page,{delay:4000});await page.clock.install();const b=app.locator('[data-token]').first();await b.click();await expect(b).toHaveAttribute('aria-busy','true');await expect.poll(()=>calls.length).toBe(1);
 await page.clock.fastForward(22001);await expect(b).toBeEnabled();await expect(app.locator('.release-feedback[role="alert"]')).toContainText('not confirmed');await b.click();expect(calls).toHaveLength(1);
 await titleTop(app);await app.locator('[data-detail-view="setup"]').click();await expect(app.locator('#setup-view')).toBeVisible();await page.waitForTimeout(4200);await expect(app.locator('#setup-view')).toBeVisible();expect(errors).toEqual([]);
});
for(const phase of ['search','submission','rejection','cancelled','scrolled'])for(const target of ['browse','downloads','setup','back','close']){
 test(`navigation ${target} during ${phase}`,async({page})=>{
  await page.setViewportSize({width:393,height:852});const {app,calls,errors}=await fixture(page,{outcome:'rejected',delay:phase==='submission'?2000:0,searchDelay:phase==='search'||phase==='cancelled'?1500:0});
  if(phase==='cancelled'){await app.locator('#cancel-release-search').click();await expect(app.locator('#release-area')).toContainText('cancelled');}
  if(phase==='submission'||phase==='rejection'){await app.locator('[data-token]').first().click();if(phase==='rejection')await expect(app.locator('.release-feedback[role="alert"]')).toBeVisible();}
  if(phase==='scrolled'){await expect(app.locator('[data-token]').first()).toBeVisible();await app.locator('#modal .dialog').evaluate(el=>el.scrollTop=el.scrollHeight);}
  const control=app.locator(target==='back'?'#mobile-modal-back':target==='close'?'#close-modal':`[data-detail-view="${target}"]`);await expect(control).toBeInViewport();expect(await hit(control)).toBe(true);await control.click();await expect(app.locator('#modal')).toHaveClass(/hidden/);await expect(app.locator(`#${['back','close'].includes(target)?'browse':target}-view`)).toBeVisible();
  await page.waitForTimeout(2100);await expect(app.locator('#modal')).toHaveClass(/hidden/);expect(errors).toEqual([]);expect(calls).toHaveLength(['submission','rejection'].includes(phase)?1:0);expect(page.url()).toBe('http://mediahub.test/host');
 });
}
test('late submission cannot replace a different movie or navigate it away',async({page})=>{
 const {app,calls}=await fixture(page,{delay:1500});await app.locator('[data-token]').first().click();await expect.poll(()=>calls.length).toBe(1);await app.locator('#close-modal').click();
 await app.locator('body').evaluate(()=>openMovie(124));await expect(app.locator('#detail-title')).toHaveText('Another Movie');await page.waitForTimeout(1700);await expect(app.locator('#modal')).not.toHaveClass(/hidden/);await expect(app.locator('#detail-title')).toHaveText('Another Movie');expect(calls).toHaveLength(1);
});

for(const outcome of ['http401','http422','http500','network'])test(`categorised ${outcome} failure is actionable and navigation remains available`,async({page})=>{
 const {app,calls,errors}=await fixture(page,{outcome});const b=app.locator('[data-token]').first();await b.click();await expect(app.locator('.release-feedback[role="alert"]')).toBeVisible();await expect(b).toBeEnabled();await expect(app.locator('.toast')).not.toContainText('private');await expect(app.locator('.toast')).not.toContainText('request accepted');
 const trace=await app.locator('body').evaluate(()=>window.MEDIAHUB_DOWNLOAD_DIAGNOSTICS());expect(JSON.stringify(trace)).not.toContain('private');expect(trace.at(-1).event).toBe('state_cleanup');await titleTop(app);await app.locator('[data-detail-view="downloads"]').click();await expect(app.locator('#downloads-view')).toBeVisible();expect(calls).toHaveLength(1);expect(errors).toEqual([]);
});
test('repeated automatic discovery does not move the scroll or replace the movie header',async({page})=>{
 const {app,errors}=await fixture(page,{searchDelay:500});await expect(app.locator('#detail-title')).toBeVisible();
 const before=await app.locator('#detail-title').evaluate(el=>{window.savedTitle=el;el.closest('.dialog').scrollTop=180;return el.closest('.dialog').scrollTop;});await expect(app.locator('[data-token]')).toHaveCount(25);
 const after=await app.locator('#detail-title').evaluate(el=>({same:el===window.savedTitle,scroll:el.closest('.dialog').scrollTop}));expect(after).toEqual({same:true,scroll:before});expect(errors).toEqual([]);
});

test('one eligible release keeps one stable badge during submission',async({page})=>{
 const {app,calls}=await fixture(page,{count:1,delay:400});const b=app.locator('[data-token]').first();await b.tap();await expect(b).toHaveAttribute('aria-busy','true');await expect(app.locator('.best-badge')).toHaveCount(1);await expect(app.locator('#downloads-view')).toBeVisible();expect(calls).toHaveLength(1);
});

test('best-release action reports HTTP 200 storage rejection without false acceptance',async({page})=>{
 const {app,calls}=await fixture(page,{outcome:'storage'});await expect(app.locator('[data-token]')).toHaveCount(25);await app.locator('#auto-request').tap();
 await expect(app.locator('.release-feedback[role="alert"]')).toContainText('Storage policy rejected');await expect(app.locator('#modal')).not.toHaveClass(/hidden/);await expect(app.locator('.toast')).not.toContainText('request accepted');expect(calls).toHaveLength(1);expect(calls[0].body.release_token).toBeNull();
});

test('missing release identity cannot fall through to best-release acquisition',async({page})=>{
 const {app,calls}=await fixture(page);const b=app.locator('[data-token]').first();await b.evaluate(el=>el.dataset.token='');await b.tap();await expect(app.locator('.toast')).toContainText('selection is stale');await expect(b).toBeEnabled();expect(calls).toHaveLength(0);
});
