(function () {
  'use strict';
  const q = id => document.getElementById(id);
  const jsonOptions = body => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const date = value => {
    const parsed = value ? new Date(value) : null;
    return parsed && !Number.isNaN(parsed.getTime()) ? parsed.toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}) : 'Not recorded';
  };
  const size = item => item.size_bytes ? `${item.size_is_estimate?'~':''}${(item.size_bytes/(item.size_bytes>=1024**3?1024**3:1024**2)).toFixed(1)} ${item.size_bytes>=1024**3?'GB':'MB'}` : 'Size not recorded';
  const type = item => item.media_type==='tv'?'TV':'Movie';
  const status = item => `${item.display_status||item.status}${item.display_progress==null?'':` ${Math.round(item.display_progress)}%`}`;
  const boundedBefore = api;
  api = async function(path, options={}) {
    if(options.signal || !/^(download-management|ratings\/availability|users(?:\/|$))/.test(path))return boundedBefore(path,options);
    const controller=new AbortController();
    const deadline=setTimeout(()=>controller.abort(),22000);
    try{return await boundedBefore(path,{...options,signal:controller.signal});}
    catch(error){if(error.name==='AbortError')throw new Error('Request timed out. Refresh or review before retrying.');throw error;}
    finally{clearTimeout(deadline);}
  };

  // Group summaries are paginated server-side; expanding only fetches that group's history.
  let page=1, latest=null, generation=0, controller=null;
  const openGroups=new Set(), controls=document.createElement('div');
  controls.className='management-controls';
  controls.innerHTML=[['sort','Sort',[['newest','Newest first'],['oldest','Oldest first'],['title','Title'],['requester','Requested by'],['type','Media type'],['status','Status']]],
    ['media','Type',[['all','All media'],['movie','Movies'],['tv','TV shows']]],
    ['status','Status',[['all','All statuses'],['completed','Transfer completed / imported'],['downloading','Downloading'],['failed','Failed / rejected'],['available','Available']]]].map(([id,label,values])=>
      `<label>${label}<select id="history-${id}">${values.map(([value,text])=>`<option value="${value}">${text}</option>`).join('')}</select></label>`).join('')+
      '<label>Requested by<select id="history-requester"><option value="">All users</option></select></label>';
  q('downloads').before(controls);
  q('downloads-view').querySelector('.heading h2').textContent='Downloads';
  controls.addEventListener('change',()=>{page=1;loadDownloads();});
  function details(item) {
    const fields=[['Full title',item.display_title||item.title],['Requested by',item.requested_by_name],['Type',type(item)],['Requested',date(item.created_at)],
      ['Release',item.selected_release_title],['Source',item.selected_release_source],['Size',size(item)],['Quality',item.selected_release_quality],['Seeders',item.selected_release_seeders],
      ['Status',item.status_message||status(item)],['Manager acceptance',item.lifecycle?.manager],['Client',item.lifecycle?.client],['Import',item.lifecycle?.import],['Library',item.lifecycle?.library],
      ['Progress',item.display_progress==null?null:`${Math.round(item.display_progress)}%`],['Sent',item.sent_at?date(item.sent_at):null],
      ['Download started',item.download_started_at?date(item.download_started_at):null],['Transfer completed',item.download_completed_at?date(item.download_completed_at):null],
      ['Imported',item.imported_at?date(item.imported_at):null],['Available observed',item.available_observed_at?date(item.available_observed_at):null],
      ['Failure',item.failure?.explanation],['Integration',item.failure?.integration],['Error category',item.failure?.category],
      ['Response code',item.failure?.response_code],['Error time',item.failure?.timestamp?date(item.failure.timestamp):null]];
    return `<div class="management-details"><dl>${fields.filter(([,v])=>v!=null&&v!=='').map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>
      ${item.retry_supported?`<button class="button" data-review-retry="${item.external_id}">Review current releases for a new attempt</button><p class="hint">Uses current preferences. Nothing downloads until you confirm an eligible release.</p>`:''}</div>`;
  }
  function bindRetries(root) {
    root.querySelectorAll('[data-review-retry]').forEach(button=>button.onclick=async()=>{if(button.disabled)return;button.disabled=true;try{await openMovie(Number(button.dataset.reviewRetry),button);}finally{if(button.isConnected)button.disabled=false;}});
  }
  async function expand(item,root,attemptPage=1) {
    root.innerHTML=details(item)+'<div role="status">Loading attempts…</div>';bindRetries(root);
    try {
      const data=await api(`download-management/${item.id}/attempts?page=${attemptPage}`);
      if(!root.isConnected)return;
      root.innerHTML=details(item)+`<div class="attempt-count">${data.total} recorded attempts</div>`+data.items.map(attempt=>
        `<details class="attempt-entry"><summary>Attempt #${attempt.id} · ${esc(date(attempt.created_at))} · ${esc(status(attempt))} · ${esc(attempt.requested_by_name)}</summary>${details(attempt)}</details>`).join('')+
        (data.total_pages>1?`<div class="management-pagebar"><button class="button" data-attempt-prev ${attemptPage===1?'disabled':''}>Previous attempts</button><span>${attemptPage} / ${data.total_pages}</span><button class="button" data-attempt-next ${attemptPage>=data.total_pages?'disabled':''}>More attempts</button></div>`:'');
      root.querySelector('[data-attempt-prev]')?.addEventListener('click',()=>expand(item,root,attemptPage-1));
      root.querySelector('[data-attempt-next]')?.addEventListener('click',()=>expand(item,root,attemptPage+1));bindRetries(root);
    }catch(error){if(root.isConnected)root.innerHTML=details(item)+`<p class="management-error">${esc(error.message)}</p>`;bindRetries(root);}
  }
  function render(data) {
    const user=q('history-requester'),selected=user.value;
    user.innerHTML='<option value="">All users</option>'+data.requesters.map(u=>`<option value="${esc(u.id)}">${esc(u.name||u.id)}</option>`).join('');user.value=selected;
    q('downloads').innerHTML=`${data.warning?`<p role="status" class="catalogue-notice">${esc(data.warning)}</p>`:''}
      <p class="hint">Latest attempt per media item. Earlier attempts are preserved in expanded history.</p>
      <div class="management-mobile">${data.items.map(item=>`<details class="management-mobile-item" data-group="${item.id}" ${openGroups.has(item.id)?'open':''}>
        <summary><div class="management-mobile-title">${esc(item.display_title||item.title)}</div>
        <div class="management-mobile-meta"><span>${type(item)}</span><span>${esc(item.requested_by_name||'Requester not recorded')}</span><time>${esc(date(item.created_at))}</time></div>
        <div class="management-mobile-state"><span class="status ${esc(item.status)}">${esc(status(item))}</span><span>${esc(size(item))}</span>${item.attempt_count>1?`<span class="attempt-count">${item.attempt_count} attempts</span>`:''}<span aria-hidden="true">⌄</span></div></summary><div data-expanded></div></details>`).join('')||'<p class="empty">No requests match these filters.</p>'}</div>
      <div class="history-wrap management-desktop"><table class="management-table"><thead><tr>${['Title','Type','Requested by','Requested','Size','Quality','Status','Actions'].map(label=>`<th scope="col">${label}</th>`).join('')}</tr></thead><tbody>${data.items.map(item=>`<tr><td>${esc(item.display_title||item.title)}${item.attempt_count>1?`<div class="attempt-count">${item.attempt_count} attempts</div>`:''}</td><td>${type(item)}</td><td>${esc(item.requested_by_name)}</td><td>${esc(date(item.created_at))}</td><td>${esc(size(item))}</td><td>${esc(item.selected_release_quality||'Not recorded')}</td><td><span class="status ${esc(item.status)}">${esc(status(item))}</span></td><td><button class="button" data-desktop-group="${item.id}" aria-expanded="${openGroups.has(item.id)}">Details</button></td></tr><tr data-desktop-details="${item.id}" class="${openGroups.has(item.id)?'':'hidden'}"><td colspan="8"><div data-expanded></div></td></tr>`).join('')||'<tr><td colspan="8">No requests match these filters.</td></tr>'}</tbody></table></div>
      <div class="management-pagebar"><button class="button" id="management-prev" ${data.page<=1?'disabled':''}>Previous</button><span>${data.total} groups · Page ${data.page} of ${data.total_pages}</span><button class="button" id="management-next" ${data.page>=data.total_pages?'disabled':''}>Next</button></div>`;
    q('management-prev').onclick=()=>{page--;loadDownloads();};q('management-next').onclick=()=>{page++;loadDownloads();};
    for(const item of data.items){
      const mobile=q('downloads').querySelector(`[data-group="${item.id}"]`),desktop=q('downloads').querySelector(`[data-desktop-group="${item.id}"]`),row=q('downloads').querySelector(`[data-desktop-details="${item.id}"]`);
      mobile.addEventListener('toggle',()=>{if(mobile.open){openGroups.add(item.id);if(!mobile.querySelector('[data-expanded]').children.length)expand(item,mobile.querySelector('[data-expanded]'));}else openGroups.delete(item.id);});
      desktop.onclick=()=>{const opening=row.classList.contains('hidden');row.classList.toggle('hidden',!opening);desktop.setAttribute('aria-expanded',String(opening));opening?openGroups.add(item.id):openGroups.delete(item.id);if(opening)expand(item,row.querySelector('[data-expanded]'));};
      if(openGroups.has(item.id)&&innerWidth>760)expand(item,row.querySelector('[data-expanded]'));
    }
  }
  loadDownloads=async function(silent=false) {
    if(silent&&(state.downloadLoading||openGroups.size||document.hidden))return;
    controller?.abort();controller=new AbortController();const own=controller,gen=++generation;
    state.downloadLoading=true;let deadline=setTimeout(()=>own.abort(),22000);
    try{
      const params=new URLSearchParams({page:String(page)});for(const field of ['sort','media','status','requester'])params.set(field,q('history-'+field).value);
      const data=await api(`download-management?${params}`,{signal:own.signal});if(gen!==generation||state.view!=='downloads')return;latest=data;render(data);
    }catch(error){if(gen===generation&&state.view==='downloads'){toast(error.name==='AbortError'?'History refresh timed out; saved entries retained.':error.message,'error');if(!latest)q('downloads').innerHTML='<div class="empty">History could not load. Use Refresh to retry.</div>';}}
    finally{clearTimeout(deadline);if(gen===generation)state.downloadLoading=false;}
  };

  // Rating capabilities are fetched once on modal opening, not one provider call per input.
  let capabilities=null, capabilitiesGeneration=0;
  window.MEDIAHUB_VALIDATE_RATING_CAPABILITIES=()=>{
    for(const field of document.querySelectorAll('[data-rating-source]'))if(field.querySelector('[data-rating-enabled]').checked&&!capabilities?.[field.dataset.ratingSource]?.enabled)
      throw new Error('This rating source is unavailable. Clear it or configure the supported provider in Setup.');
  };
  function applyCapabilities(data){capabilities=data.sources||{};
    for(const option of q('ratings-sort').options)if(capabilities[option.value])option.disabled=!capabilities[option.value].enabled;
    document.querySelectorAll('[data-rating-source]').forEach(field=>{
    const source=capabilities[field.dataset.ratingSource];if(!source)return;
    field.classList.toggle('source-disabled',!source.enabled);field.querySelectorAll('input').forEach(input=>input.disabled=!source.enabled);
    let note=field.querySelector('.source-availability');if(!note){note=document.createElement('div');note.className='source-availability';field.append(note);}
    note.innerHTML=source.enabled?`${source.verified_cached} verified cached titles${source.reason?'. '+esc(source.reason):''}`:esc(source.reason)+ (state.user?.role==='admin'?'<br><button type="button" class="button" data-rating-setup>Configure in Setup</button>':' Ask an administrator to configure this source.');
    note.querySelector('[data-rating-setup]')?.addEventListener('click',()=>{q('mobile-filter-close').click();showView('setup');q('ratings-provider-panel').scrollIntoView({block:'start'});});
  });}
  q('mobile-filter-toggle').addEventListener('click',()=>{
    const own=++capabilitiesGeneration;capabilities=null;q('mobile-filter-apply').disabled=true;
    api(`ratings/availability?media_type=${browseMedia}`).then(data=>{if(own===capabilitiesGeneration)applyCapabilities(data);}).catch(()=>{if(own!==capabilitiesGeneration)return;q('rating-filter-error').textContent='Ratings availability could not be checked. Try again; TMDb remains available.';capabilities={tmdb:{enabled:true}};}).finally(()=>{if(own===capabilitiesGeneration)q('mobile-filter-apply').disabled=false;});
  });
  q('mobile-filter-apply').addEventListener('click',event=>{
    for(const field of document.querySelectorAll('[data-rating-source]'))if(field.querySelector('[data-rating-enabled]').checked&&!capabilities?.[field.dataset.ratingSource]?.enabled){event.stopImmediatePropagation();q('rating-filter-error').textContent='This rating source is unavailable. Clear it or configure the supported provider in Setup.';return;}
    document.activeElement?.blur();setTimeout(()=>q('mobile-filter-toggle').focus(),0);
  },true);
  // VisualViewport models keyboard-reduced space. Do not manipulate parent HA history.
  const sheet=q('mobile-filter-sheet'),panel=sheet.querySelector('.mobile-filter-panel');
  const dismiss=document.createElement('button');dismiss.type='button';dismiss.className='button filter-keyboard-dismiss';dismiss.textContent='Done typing';dismiss.onclick=()=>document.activeElement?.blur();sheet.querySelector('.mobile-filter-head').insertBefore(dismiss,q('mobile-filter-close'));
  sheet.querySelectorAll('input[type=number]').forEach(input=>input.inputMode=input.step==='1'?'numeric':'decimal');
  function viewport(){const vv=window.visualViewport;panel.style.setProperty('--filter-viewport',`${vv?.height||innerHeight}px`);panel.style.setProperty('--filter-offset',`${vv?.offsetTop||0}px`);}
  window.visualViewport?.addEventListener('resize',viewport);window.visualViewport?.addEventListener('scroll',viewport);window.addEventListener('resize',viewport);viewport();
  sheet.addEventListener('focusin',event=>{if(event.target.matches('input,select'))setTimeout(()=>event.target.scrollIntoView({block:'nearest',behavior:'smooth'}),100);});
  q('mobile-filter-close').addEventListener('click',()=>document.activeElement?.blur());

  // Persist only Browse preferences, scoped to the current user, never passwords/API keys.
  function storageKey(){return `mediahub-browse-v019:${state.user?.id||state.user?.user_id||'session'}`;}
  function saveBrowse(){try{const copy={};for(const kind of ['movie','tv']){const s=catalogueState[kind];copy[kind]=Object.fromEntries(['query','collection','genres','genre','yearFrom','yearTo','multiRatings','ratingSort','missingRatings','advancedDiscovery'].map(key=>[key,s[key]]));}localStorage.setItem(storageKey(),JSON.stringify(copy));}catch(_){}}
  let restored=false;const userBefore=applyUser;applyUser=function(user){userBefore(user);if(restored)return;restored=true;try{const saved=JSON.parse(localStorage.getItem(storageKey())||'null');if(saved){for(const kind of ['movie','tv'])if(saved[kind])Object.assign(catalogueState[kind],saved[kind]);restoreControls();renderCollections();resetCatalogue({remember:false});}}catch(_){}};
  q('mobile-filter-apply').addEventListener('click',()=>setTimeout(saveBrowse,0));q('search').addEventListener('change',saveBrowse);window.addEventListener('pagehide',saveBrowse);

  // Release search eligibility is based on evaluated candidates, never handoff/completion.
  const releaseAreaObserver=new MutationObserver(()=>{
    const area=q('release-area');if(!area)return;
    const stage=area.dataset.searchState,button=q('auto-request');
    const eligible=area.querySelectorAll('[data-eligible="true"]').length;
    const excluded=area.querySelectorAll('[data-eligible="false"]').length;
    if(button){button.disabled=stage!=='SUCCESS'||!eligible;button.title=button.disabled?'Wait for an eligible release, or refresh the search.':'Request the best currently eligible release';}
    if(stage==='SUCCESS'||stage==='NO_RESULTS'){
      const value=area.dataset.discoveryStatus==='partial'||area.dataset.discoveryStatus==='indexer_unavailable'?'PARTIAL':eligible?'RESULTS':excluded?'NONE_ELIGIBLE':'NO_RESULTS';area.dataset.outcome=value;
      let summary=area.querySelector('.release-state-summary');if(!summary){summary=document.createElement('div');summary.className='release-state-summary';summary.setAttribute('role','status');area.prepend(summary);}
      const text=area.dataset.discoveryMessage||`${eligible} eligible · ${excluded} rejected${!eligible?(excluded?' (Releases found, but none meet the requirements.)':' (No releases were returned.)'):''}`;
      if(summary.textContent!==text)summary.textContent=text;
      const best=area.querySelector('[data-eligible="true"]');if(best&&!best.querySelector('.best-badge'))best.insertAdjacentHTML('afterbegin','<span class="best-badge">BEST MATCH</span>');
    }
  });releaseAreaObserver.observe(q('detail'),{childList:true,subtree:true});

  // Move creation into an explicitly opened panel and replace its submit listener.
  const oldForm=q('create-user-form'),form=oldForm.cloneNode(true),createPanel=document.createElement('details');createPanel.className='account-create-panel';createPanel.innerHTML='<summary>Create MediaHub account</summary>';oldForm.replaceWith(createPanel);createPanel.append(form);
  let creating=false;
  form.addEventListener('submit',async event=>{event.preventDefault();if(creating||!form.reportValidity())return;creating=true;const button=form.querySelector('button'),message=q('user-message');button.disabled=true;message.textContent='Creating account…';message.className='message';
    try{await api('users',jsonOptions({display_name:q('new-display-name').value,username:q('new-username').value,password:q('new-password').value,role:q('new-role').value}));form.reset();message.textContent='Account created. Share the credentials privately.';message.className='message success';toast('Account created.');await loadUsers();}
    catch(error){message.textContent=error.message;message.className='message error';}
    finally{creating=false;button.disabled=false;}
  });
  let usersLoading=false;
  loadUsers=async function(){if(usersLoading||state.user?.role!=='admin')return;usersLoading=true;const list=q('user-list');list.setAttribute('aria-busy','true');
    try{
      const users=await api('users');dualLoginUsers=users;
      list.innerHTML=users.map(user=>`<article class="panel user-card" data-user-id="${esc(user.id)}"><div><h3>${esc(user.display_name)} <span class="account-source">${esc(dualLoginSourceLabel(user))}</span></h3><div class="user-meta">${esc(user.username)} · ${user.active?'Active':'Disabled'} · Last seen ${esc(date(user.last_seen_at))}</div><div class="stack hidden" data-reset-panel><label class="field">New password<input type="password" minlength="12" autocomplete="new-password" data-reset-password></label><button class="button" data-save-password>Save password</button></div></div><div class="user-controls"><select aria-label="Role" data-role>${['requester','manager','admin'].map(role=>`<option value="${role}" ${role===user.role?'selected':''}>${role}</option>`).join('')}</select><button class="button" data-active>${user.active?'Disable':'Enable'}</button>${user.auth_source==='mediahub'?'<button class="button" data-reset>Reset password</button>':''}</div><p class="management-error" data-user-feedback role="status"></p></article>`).join('')||'<p>No users registered.</p>';
      for(const card of list.querySelectorAll('[data-user-id]')){
        const user=users.find(item=>item.id===card.dataset.userId);let busy=false;
        const change=async(path,body)=>{if(busy)return;busy=true;card.querySelectorAll('button,select').forEach(el=>el.disabled=true);const feedback=card.querySelector('[data-user-feedback]');feedback.textContent='Saving…';
          try{await api(`users/${encodeURIComponent(user.id)}/${path}`,{...jsonOptions(body),method:'PUT'});toast('Account updated.');usersLoading=false;await loadUsers();}
          catch(error){feedback.textContent=error.message;card.querySelector('[data-role]').value=user.role;}
          finally{busy=false;if(card.isConnected)card.querySelectorAll('button,select').forEach(el=>el.disabled=false);}
        };
        card.querySelector('[data-role]').onchange=event=>change('role',{role:event.target.value});card.querySelector('[data-active]').onclick=()=>change('active',{active:!user.active});
        card.querySelector('[data-reset]')?.addEventListener('click',()=>card.querySelector('[data-reset-panel]').classList.toggle('hidden'));
        card.querySelector('[data-save-password]').onclick=()=>{const input=card.querySelector('[data-reset-password]');if(input.value.length<12){card.querySelector('[data-user-feedback]').textContent='Password must contain at least 12 characters.';return;}change('password',{password:input.value});};
      }decorateDualLoginUsers();
    }catch(error){if(!list.querySelector('[data-user-id]'))list.innerHTML=`<p class="management-error">${esc(error.message)}</p>`;else toast(error.message,'error');}
    finally{usersLoading=false;list.setAttribute('aria-busy','false');}
  };
  // Local-only bounded diagnostics: no URLs, credentials, titles or user identities.
  const events=[];window.MEDIAHUB_NAVIGATION_DIAGNOSTICS=()=>events.map(item=>({...item}));
  function record(event){events.push({event,view:state.view,at:new Date().toISOString(),detailOpen:!q('modal').classList.contains('hidden')});if(events.length>30)events.shift();}
  for(const name of ['pagehide','pageshow','popstate'])window.addEventListener(name,()=>record(name));
  window.addEventListener('error',()=>record('frontend_error'));window.addEventListener('unhandledrejection',()=>record('unhandled_rejection'));
  const showBefore=showView;showView=function(name){if(state.view==='downloads'&&name!=='downloads'){controller?.abort();generation++;state.downloadLoading=false;}record('view_change');return showBefore(name);};
})();
