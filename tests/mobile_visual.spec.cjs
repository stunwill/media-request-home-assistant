const {test,expect}=require('@playwright/test');
const fs=require('node:fs');
const {execFileSync}=require('node:child_process');
const python=process.env.MEDIAHUB_TEST_PYTHON||'python';
const html=execFileSync(python,['-c','from mediahub.app.watchlist_main import main; print(main.INDEX_HTML)'],{encoding:'utf8',maxBuffer:2e6});
const matrix={tmdb:{status:'verified',value:8,provider:'tmdb',votes:2000},imdb:{status:'verified',value:8.2,provider:'mdblist',votes:3000},rt_critic:{status:'verified',value:91,provider:'mdblist'},metacritic:{status:'verified',value:79,provider:'omdb'}};
const movie={tmdb_id:123,title:'Example Movie',year:'2024',rating:8,vote_count:2000,genres:[],cast:[],overview:'A representative synopsis for testing the compact detail layout.',context:'browse',lifecycle:{},lifecycle_message:{},library:{},ratings_data:matrix};
for(const viewport of [{width:320,height:740},{width:375,height:812},{width:390,height:844},{width:430,height:932},{width:844,height:390},{width:768,height:1024},{width:1440,height:900}]){
 test(`ingress layout ${viewport.width}x${viewport.height}`,async({page})=>{
  await page.setViewportSize(viewport);const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('http://mediahub.test/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/host')return route.fulfill({contentType:'text/html',body:`<style>body{margin:0}header{height:56px;background:#ddd}iframe{display:block;width:100%;height:calc(100dvh - 56px);border:0}</style><header>Home Assistant</header><iframe src="/api/hassio_ingress/test/"></iframe>`});
   if(path==='/api/hassio_ingress/test/')return route.fulfill({contentType:'text/html',body:html});
   if(path.endsWith('.png'))return route.fulfill({contentType:'image/png',body:Buffer.from(fs.readFileSync('mediahub/app/assets/'+(path.includes('logo')?'mediahub-logo':'mediahub-icon')+'.png.b64','utf8'),'base64')});
   let body={};
   if(path.endsWith('users/me'))body={id:'stu',display_name:'Stuart',role:'admin',auth_source:'home_assistant'};
   else if(path.endsWith('/ratings'))body={ratings:{'123':matrix},configured:true};
   else if(path.endsWith('/ratings/availability'))body={sources:Object.fromEntries(['tmdb','imdb','rt_critic','rt_audience','metacritic','letterboxd','trakt'].map(id=>[id,{enabled:true,verified_cached:10}]))};
   else if(path.includes('/genres'))body={genres:[{id:18,name:'Drama'},{id:99,name:'Documentary'}]};
   else if(path.includes('/discovery/')||/catalog\/movies\?/.test(route.request().url()))body={movies:Array.from({length:8},(_,i)=>({...movie,tmdb_id:123+i})),shows:[],page:1,total_pages:1,total_results:8};
   else if(path.endsWith('catalog/movies/123'))body=movie;
   else if(path.includes('/movies/123/releases'))body={releases:[],search_message:'No eligible releases in this fixture.'};
   else if(path.endsWith('download-presets'))body={movies:{allowed_resolutions:['1080p','720p'],maximum_size_gb:3,minimum_seeders:1}};
   else if(path.endsWith('setup/presets'))body={movies:{allowed_resolutions:['1080p'],maximum_size_gb:3,minimum_seeders:1},tv:{allowed_resolutions:['1080p']},discovery:{original_language:'en'}};
   return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
  });
  await page.goto('http://mediahub.test/host');const app=page.frameLocator('iframe');
  await expect(app.locator('.movie').first()).toBeVisible();
  const measurements=await app.locator('body').evaluate(body=>({overflow:body.scrollWidth>innerWidth,header:document.querySelector('.topbar').getBoundingClientRect(),grid:document.getElementById('movies').getBoundingClientRect(),width:innerWidth}));
  expect(measurements.overflow).toBe(false);
  expect(measurements.header.height).toBeLessThan(64);
  expect(measurements.header.top).toBeLessThanOrEqual(1);
  expect(measurements.grid.top).toBeLessThan(350);
  expect(await app.locator('.mobile-bottom-nav:visible').count()).toBe(0);
  await app.locator('#mobile-filter-toggle').click();await expect(app.locator('#mobile-filter-sheet')).toHaveAttribute('aria-hidden','false');
  const panel=app.locator('.mobile-filter-panel');await expect(panel).toBeVisible();
  await app.locator('#mobile-filter-fields').evaluate(el=>el.scrollTop=el.scrollHeight);
  const geometry=await panel.evaluate(el=>{const r=el.getBoundingClientRect(),actions=el.querySelector('.mobile-filter-actions').getBoundingClientRect();return {height:r.height,viewport:innerHeight,actionsBottom:actions.bottom,overflow:el.scrollWidth>el.clientWidth};});
  expect(geometry.height).toBeLessThanOrEqual(geometry.viewport);
  expect(geometry.actionsBottom).toBeLessThanOrEqual(geometry.viewport+1);
  expect(geometry.overflow).toBe(false);
  for(const [source,min,votes] of [['imdb','7.5','1000'],['rt_critic','85',null],['metacritic','75',null]]){
   const group=app.locator(`[data-rating-source="${source}"]`);await group.locator('[data-rating-enabled]').check();await group.locator('[data-rating-min]').fill(min);if(votes)await group.locator('[data-rating-votes]').fill(votes);
  }
  await app.locator('#mobile-filter-apply').click();await expect(app.locator('#mobile-filter-sheet')).toHaveAttribute('aria-hidden','true');
  await expect(app.locator('#mobile-filter-toggle .filter-count')).toHaveText('3');
  await app.locator('#media-switch [data-media="tv"]').click();
  await app.locator('#mobile-filter-toggle').click();
  await app.locator('#mobile-genre-list label').filter({has:app.locator('input[value="18"]')}).click();
  await app.locator('#mobile-genre-list label').filter({has:app.locator('input[value="99"]')}).click();
  await app.locator('#mobile-filter-apply').click();
  const genreParams=await app.locator('body').evaluate(()=>[...catalogueParams(1).getAll('genre_id')]);
  expect(genreParams).toEqual(['18','99']);
  await app.locator('#media-switch [data-media="movie"]').click();
  await app.locator('[data-id="123"]').click();await expect(app.locator('.multi-ratings')).toBeVisible();
  await expect(app.locator('.multi-ratings .rating-indicator')).toHaveCount(4);
  const row=await app.locator('.multi-ratings').evaluate(el=>{const rects=[...el.querySelectorAll('.rating-indicator')].map(e=>e.getBoundingClientRect());return {height:el.getBoundingClientRect().height,overflow:el.scrollWidth>el.clientWidth,rows:new Set(rects.map(r=>Math.round(r.top))).size};});
  expect(row.overflow).toBe(false);expect(row.rows).toBeLessThanOrEqual(viewport.width===320?2:1);
  expect(row.height).toBeLessThan(65);
  await page.screenshot({path:`test-results/screenshots/detail-${viewport.width}x${viewport.height}.png`});
  await app.locator('#close-modal').click();await expect(app.locator('#modal')).toHaveClass(/hidden/);
  fs.mkdirSync('test-results/screenshots',{recursive:true});await page.screenshot({path:`test-results/screenshots/ingress-${viewport.width}x${viewport.height}.png`,fullPage:true});
  expect(errors).toEqual([]);
 });
}
