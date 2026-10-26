'use strict';
const $ = (selector) => document.querySelector(selector);
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const E = escapeHTML;
const bytes = (value) => {if (!value) return '0 B'; const unit = Math.min(5, Math.floor(Math.log(value)/Math.log(1024))); return `${(value/1024**unit).toFixed(unit>1?1:0)} ${['B','KB','MB','GB','TB','PB'][unit]}`;};
const ago = (date) => {const minutes = Math.max(0, (Date.now()-Date.parse(date))/60000); return minutes<1?'Just now':minutes<60?`${Math.floor(minutes)} minutes ago`:minutes<1440?`${Math.floor(minutes/60)} hours ago`:new Date(date).toLocaleDateString();};
const labels = {home:'Home',files:'Files',storage:'Storage',sharing:'Sharing',apps:'App Store',snapshots:'Snapshots',activity:'Activity',settings:'Settings',users:'Users',connections:'Connections'};
let csrf = '', username = '', route = 'home', filePath = '', setupRequired = false, health = {}, viewSerial = 0, refreshTimer, toastTimer, dialogAction;
const announcedJobs = new Set();
let desktopDragging=false, draggedLauncher='', catalogFilter='All';
let pointerDrag=null, suppressLauncherClickUntil=0;
const desktopDefaults={wallpaper:'dark',widgets:{clock:true,stats:true,storage:true,connection:true},order:[]};
function loadDesktop() {
  try {const p=JSON.parse(localStorage.getItem('harbor.desktop.v2')||'{}');return {wallpaper:p.wallpaper==='black'?'black':'dark',widgets:{clock:p.widgets?.clock!==false,stats:p.widgets?.stats!==false,storage:p.widgets?.storage!==false,connection:p.widgets?.connection!==false},order:Array.isArray(p.order)?p.order.filter(x=>typeof x==='string').slice(0,30):[]};}
  catch{return JSON.parse(JSON.stringify(desktopDefaults));}
}
let desktopPrefs=loadDesktop();
document.body.dataset.wallpaper=desktopPrefs.wallpaper;
function saveDesktop(){try{localStorage.setItem('harbor.desktop.v2',JSON.stringify(desktopPrefs));}catch{toast('This browser cannot save desktop preferences.',true);}document.body.dataset.wallpaper=desktopPrefs.wallpaper;}
const glyphs={
  home:'<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',
  files:'<path d="M3 7V5a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v1H3Z"/><path d="M3 8h18l-2 12H3Z"/>',
  apps:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  storage:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M6 6.5h.1M6 17.5h.1M11 6.5h7M11 17.5h7"/>',
  sharing:'<path d="M3 7h16m-4-4 4 4-4 4M21 17H5m4-4-4 4 4 4"/>',
  snapshots:'<path d="M3 11a9 9 0 1 1 3 8M3 4v7h7"/><path d="M12 7v6l4 2"/>',
  settings:'<path d="m9 3-1 3-3 1-2 3 2 2-1 4 3 2 3-1 2 4 4-1 1-3 3-1 1-4-3-2 1-3-3-2-3 1-2-3Z"/><circle cx="12" cy="12" r="3"/>',
  activity:'<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  cpu:'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4"/>',
  memory:'<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 10v4m5-4v4m5-4v4M7 18v3m5-3v3m5-3v3"/>',
  network:'<rect x="8" y="2" width="8" height="6" rx="1"/><path d="M12 8v6M4 18v-4h16v4"/><rect x="1" y="18" width="6" height="4" rx="1"/><rect x="17" y="18" width="6" height="4" rx="1"/>',
  arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',
  jellyfin:'<path d="M12 3 2 21h20L12 3Z"/><path d="m12 10-4 7h8l-4-7Z"/>',
  syncthing:'<circle cx="6" cy="6" r="3"/><circle cx="18" cy="8" r="3"/><circle cx="10" cy="19" r="3"/><path d="m9 6 6 1M7 9l2 7m3 0 4-5"/>'
};
function icon(name){return `<svg viewBox="0 0 24 24" aria-hidden="true">${glyphs[name]||glyphs.apps}</svg>`;}
const builtins=[
  {id:'apps',label:'App Store',description:'Find and install apps',color:'lime'},
  {id:'files',label:'Files',description:'Browse your shared folders',color:'fern'},
  {id:'settings',label:'Settings',description:'Server settings and information',color:'sage'},
  {id:'storage',label:'Storage',description:'Disks and your data volume',color:'mint'},
  {id:'sharing',label:'Sharing',description:'Network folders and access',color:'teal'},
  {id:'snapshots',label:'Snapshots',description:'Save and restore your folders',color:'olive'},
  {id:'connections',label:'Connections',description:'Remote access, photos, transfers, and virtual machines',color:'teal'}
];
function appAddress(port){let host=location.hostname;if(host.includes(':')&&!host.startsWith('['))host='['+host+']';return 'http://'+host+':'+port;}
function launcherHTML(app){
  const external=!!app.external, id=external?'app-'+app.id:app.id;
  const inside=`<span class="launcher-icon ${E(app.color||app.id)}">${appImage(app)}</span><span class="launcher-name">${E(app.label||app.name)}</span>${external&&app.state!=='running'?'<span class="launcher-state">Stopped</span>':''}`;
  const attrs=external?(app.state==='running'?`href="${E(storeAddress(app))}" target="_blank" rel="noopener noreferrer"`:`data-action="app" data-id="${E(app.id)}" data-operation="start"`):`data-route="${E(app.id)}"`;
  const tag=external&&app.state==='running'?'a':'button';
  return `<div class="launcher-tile" draggable="false" data-launcher="${E(id)}" data-search="${E((app.label||app.name)+' '+(app.description||''))}"><${tag} class="launcher-button" draggable="false" aria-keyshortcuts="Alt+ArrowLeft Alt+ArrowRight" ${attrs} title="${E(app.description||app.name)}">${inside}</${tag}></div>`;
}
function orderedLaunchers(apps){const map=new Map(apps.map(a=>[a.external?'app-'+a.id:a.id,a]));return [...new Set([...desktopPrefs.order,...map.keys()])].filter(id=>map.has(id)).map(id=>map.get(id));}
function tickClock(){const now=new Date();document.querySelectorAll('.desktop-clock').forEach(el=>el.textContent=new Intl.DateTimeFormat(undefined,{hour:'2-digit',minute:'2-digit',hour12:harbourAppearance.timeFormat==='12'}).format(now));document.querySelectorAll('.desktop-date').forEach(el=>el.textContent=new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric'}).format(now));}
function applySearch(){
  if(route==='apps'){storeSearch();return;}
  const query=($('#app-search')?.value||'').trim().toLocaleLowerCase();let visible=0;
  document.querySelectorAll('#content [data-search]').forEach(el=>{el.hidden=!el.dataset.search.toLocaleLowerCase().includes(query)||(route==='apps'&&catalogFilter!=='All'&&el.dataset.category!==catalogFilter);if(!el.hidden)visible++;});
  const empty=$('#search-empty');if(empty)empty.hidden=visible>0;
}
function renderContent(html,keepFocus=false){
  const focused=keepFocus?document.activeElement.closest?.('[data-launcher]')?.dataset.launcher:null;
  const advisoryOpen=keepFocus&&document.querySelector('.drive-advisory')?.open;
  const widgetPrefsOpen=keepFocus&&document.querySelector('#widget-preferences')?.open;
  $('#content').innerHTML=html;applySearch();tickClock();windowChrome();
  if(widgetPrefsOpen&&document.querySelector('#widget-preferences'))document.querySelector('#widget-preferences').open=true;
  if(advisoryOpen&&document.querySelector('.drive-advisory'))document.querySelector('.drive-advisory').open=true;
  if(focused){const tile=[...document.querySelectorAll('[data-launcher]')].find(el=>el.dataset.launcher===focused);tile?.querySelector('button,a')?.focus({preventScroll:true});}
}
document.querySelectorAll('.desktop-dock [data-route]').forEach(el=>{el.querySelector('.nav-icon').innerHTML=icon(el.dataset.route);});
setInterval(tickClock,1000);

async function api(path, data, options={}) {
  const init = {...options, credentials:'same-origin', headers:{...options.headers}};
  if (data !== undefined) {init.method='POST'; init.headers['Content-Type']='application/json'; init.body=JSON.stringify(data);}
  if (init.method === 'POST') init.headers['X-Harbor-CSRF']=csrf;
  const response = await fetch(path, init);
  let result;
  try {result = await response.json();} catch {throw new Error('The server returned an unreadable response.');}
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login' && path !== '/api/setup') showAuth();
    throw new Error(result.error || `Request failed (${response.status}).`);
  }
  return result;
}
function toast(message, failed=false) {$('#toast').textContent=message; $('#toast').classList.toggle('failure',failed); $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,6000);}
function head(title, description, action='') {return `<div class="page-head"><div><h1>${E(title)}</h1><p>${E(description)}</p></div>${action}</div>`;}
function empty(title, description, action='', compact=false) {return `<div class="empty ${compact?'compact':''}"><div class="empty-icon">⌁</div><h3>${E(title)}</h3><p>${E(description)}</p>${action}</div>`;}
function button(label, action, extra='', type='primary') {const ownerOnly=['new-share','storage-wizard','snapshot','choose-snapshot','restore','smart','member-add'].includes(action);return `<button class="button ${type} ${ownerOnly?'owner-only':''}" data-action="${E(action)}" ${extra}>${E(label)}</button>`;}
function eventsHTML(events) {return events.map(event=>`<div class="event"><span class="event-symbol">${event.level==='error'?'!':'↗'}</span><div><p>${E(event.message)}</p><small>${E(ago(event.time))}</small></div></div>`).join('');}
function metric(label, value, detail, percent, cls='') {return `<section class="card ${cls}"><div class="card-label"><span>${E(label)}</span><span aria-hidden="true">↗</span></div><div class="metric-value">${value}</div><progress max="100" value="${Math.min(100,Math.max(0,percent||0))}" aria-label="${E(label)}"></progress><div class="metric-foot">${detail}</div></section>`;}
function showAuth() {if(typeof resetProcesses==='function')resetProcesses();clearTimeout(refreshTimer); viewSerial++; csrf=''; $('#shell').hidden=true; $('#modal').close();if(setupRequired){welcomeScreen();return;}$('#onboarding').hidden=true;$('#auth').hidden=false;}
function signedIn(session) {$('#onboarding').hidden=true;csrf=session.csrf;username=session.username;sessionRole=session.role||'owner';$('#auth').hidden=true;$('#shell').hidden=false;$('#account-avatar').textContent=username.slice(0,1).toUpperCase();$('#account-name').textContent=username;$('#account-role').textContent=sessionRole==='owner'?'Server owner':'Member';if(typeof loadProcesses==='function')loadProcesses();$('#preview-label').hidden=!(health.demo||health.live);$('#preview-label').textContent=health.live?'LIVE SESSION':'PREVIEW';$('#sidebar-version').textContent=health.version;$('#footer-version').textContent=health.version;$('#auth-form').reset();navigate(labels[location.hash.slice(1)]?location.hash.slice(1):'home');}
async function navigate(next) {
  clearTimeout(refreshTimer); route=next; location.hash=next;
  if(sessionRole!=='owner'&&ownerRoutes.has(next)){route='files';next='files';location.hash=next;}
  document.body.dataset.route=next;
  document.querySelectorAll('button[data-route],a[data-route]').forEach(el=>{el.classList.toggle('active',el.dataset.route===route);if(el.dataset.route===route)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  $('#breadcrumb').textContent=labels[route];
  const serial=++viewSerial;
  $('#content').innerHTML='<div class="loading" role="status">Connecting to your Harbour…</div>';
  try {if(route!=='home'&&!desktopBackdrop){desktopBackdrop=(await views.home()).replace(/\sid="[^"]*"/g,'').replace(/\sdata-route="[^"]*"/g,'').replace(/\sdata-action="[^"]*"/g,'');}const html=await views[route](); if(serial!==viewSerial)return;renderContent(html);window.scrollTo(0,0);}
  catch(error) {if(serial===viewSerial)$('#content').innerHTML=head(labels[route],'')+`<div class="notice warning">${E(error.message)}</div>`;}
  if(serial===viewSerial && csrf)refreshTimer=setTimeout(refresh,8000);
}
async function refresh() {
  if(!csrf)return;
  try {
    const jobs=await api('/api/jobs');
    if(typeof acceptProcessJobs==='function')acceptProcessJobs(jobs);
    let jobsChanged=false;
    for(const job of jobs)if(['completed','failed'].includes(job.state)&&!announcedJobs.has(job.id)){announcedJobs.add(job.id);jobsChanged=true;toast(job.state==='failed'?`${job.title}: ${job.error}`:`${job.title} completed.`,job.state==='failed');}
    // Update completed jobs without disturbing file selections or open forms.
    if(!$('#modal').open && !desktopDragging && (['home','activity','storage'].includes(route)||(jobsChanged&&['apps','snapshots','sharing','storage','files','settings','users'].includes(route)))){const serial=viewSerial;const html=await views[route]();if(serial===viewSerial&&!desktopDragging)renderContent(html,true);}
  } catch(error){toast(error.message,true);}
  if(csrf)refreshTimer=setTimeout(refresh,8000);
}

const networkHistory=[];
const views = {
  async home() {
    const [s,apps]=await Promise.all([api('/api/summary'),api('/api/apps')]);storeApps=apps;$('#server-name').textContent=s.hostname;
    const launchers=orderedLaunchers([...builtins.filter(a=>sessionRole==='owner'||!ownerRoutes.has(a.id)),...apps.filter(a=>a.installed).map(a=>({...a,external:true}))]);
    return `<div class="desktop-layout">${refinedWidgets(s)}<section class="desktop-workspace" aria-label="Your desktop"><div class="desktop-section-title"><h2>Apps</h2><button class="add-app" data-route="apps" aria-label="Add app" title="App Store">+</button></div><div class="launcher-grid">${launchers.map(launcherHTML).join('')}</div><div id="search-empty" class="search-empty" hidden>No matching apps. <button data-action="clear-search" class="text-button">Clear search</button></div></section></div>`;
  },
  async files() {return filesView();},
  async storage() {return storageView();},
  async sharing() {return sharingView();},
  async apps() {return storeView();},
  async snapshots() {
    const snapshots=await api('/api/snapshots');
    return head('Snapshots','Save a point in time. Restore it into a new folder when you need it.',button('Create snapshot +','choose-snapshot'))+
      '<div class="notice warning">Snapshots live on the same data volume. They help recover changes, but they do not protect against losing that volume. Keep a separate backup of anything important.</div>'+
      (snapshots.length?`<div class="table-wrap"><table><thead><tr><th>FOLDER</th><th>CREATED</th><th>SNAPSHOT</th><th></th></tr></thead><tbody>${snapshots.map(s=>`<tr><td>${E(s.share)}</td><td>${E(new Date(s.created).toLocaleString())}</td><td class="mono truncate">${E(s.id)}</td><td>${button('Restore to new folder','restore',`data-id="${E(s.id)}"`,'subtle small-button')}</td></tr>`).join('')}</tbody></table></div>`:empty('Keep your first moment.','Create a snapshot of a shared folder on your Btrfs data volume.',button('Create a snapshot','choose-snapshot')));
  },
  async activity() {
    const [events,jobs]=await Promise.all([api('/api/events'),api('/api/jobs')]);
    return head('Activity','What has happened, and what is working in the background.')+
      (jobs.length?`<section class="card"><h2>System jobs</h2>${jobs.map(j=>`<div class="detail"><span>${E(j.title)}${j.error?`<br><small class="error">${E(j.error)}</small>`:''}</span><span class="pill ${j.state==='failed'?'error':''}">${E(j.state)}</span></div>`).join('')}</section><div class="space-top"></div>`:'')+
      (events.length?`<section class="card">${eventsHTML(events)}</section>`:empty('All quiet, for now.','Your file, app, and snapshot activity will appear here.'));
  },
  async users() {return membersView();},
  async connections() {return connectionsView();},
  async settings() {return settingsView();}

};

function dialog(title, body, submit, action) {$('#modal-title').textContent=title;$('#modal-body').innerHTML=body;$('#modal-submit').textContent=submit;$('#modal-error').textContent='';$('#modal-submit').disabled=false;dialogAction=action;if(!$('#modal').open)$('#modal').showModal();}
function closeDialog(){$('#modal').close();$('#modal').classList.remove('wide-dialog');$('#modal-submit').hidden=false;dialogAction=null;}
$('#modal-close').addEventListener('click',closeDialog);$('#modal-cancel').addEventListener('click',closeDialog);
$('#modal-form').addEventListener('submit',async event=>{event.preventDefault();const action=dialogAction;if(!action)return;$('#modal-submit').disabled=true;$('#modal-error').textContent='';try{const result=await action(new FormData(event.target));if(result===false)return;closeDialog();await navigate(route);}catch(error){$('#modal-error').textContent=error.message;}finally{$('#modal-submit').disabled=false;}});
$('#auth-form').addEventListener('submit',async event=>{event.preventDefault();$('#auth-submit').disabled=true;$('#auth-error').textContent='';const data=Object.fromEntries(new FormData(event.target));try{const session=await api('/api/login',data);if(!health.onboarding_complete&&session.role==='owner'){csrf=session.csrf;username=session.username;featureTour();}else signedIn(session);}catch(error){$('#auth-error').textContent=error.message;}finally{$('#auth-submit').disabled=false;}});
$('#logout').addEventListener('click',async()=>{try{await api('/api/logout',{});showAuth();}catch(error){toast(error.message,true);}});
document.addEventListener('click',async event=>{
  const nav=event.target.closest('button[data-route],a[data-route]');if(nav){if($('#app-search'))$('#app-search').value='';navigate(nav.dataset.route);return;}
  const target=event.target.closest('[data-action]');if(!target)return;
  const action=target.dataset.action;
  try {
    if(action==='copy-address'){await navigator.clipboard.writeText(location.origin);toast('Server address copied.');}
    if(action==='clear-search'){$('#app-search').value='';applySearch();$('#app-search').focus();}
    if(action==='catalog-filter'){catalogFilter=target.dataset.filter;document.querySelectorAll('.filter-tab').forEach(el=>el.classList.toggle('active',el.dataset.filter===catalogFilter));applySearch();}
    if(action==='customize-desktop')dialog('Widget settings',`<label class="pref-row"><span>Time</span><input type="checkbox" name="clock" ${desktopPrefs.widgets.clock!==false?'checked':''}></label><label class="pref-row"><span>System<small>CPU, memory, and temperature</small></span><input type="checkbox" name="stats" ${desktopPrefs.widgets.stats?'checked':''}></label><label class="pref-row"><span>Storage<small>Capacity and drive advisories</small></span><input type="checkbox" name="storage" ${desktopPrefs.widgets.storage?'checked':''}></label><label class="pref-row"><span>Network<small>Live upload and download traffic</small></span><input type="checkbox" name="connection" ${desktopPrefs.widgets.connection?'checked':''}></label><label>Wallpaper<select name="wallpaper"><option value="dark" ${desktopPrefs.wallpaper==='dark'?'selected':''}>Dark waves</option><option value="black" ${desktopPrefs.wallpaper==='black'?'selected':''}>Solid black</option></select></label><button type="button" class="text-button reset-desktop" data-action="reset-desktop">Reset desktop layout</button>`,'Save',async data=>{desktopPrefs.widgets={clock:data.has('clock'),stats:data.has('stats'),storage:data.has('storage'),connection:data.has('connection')};desktopPrefs.wallpaper=data.get('wallpaper')==='black'?'black':'dark';saveDesktop();toast('Desktop updated.');});
    if(action==='reset-desktop'){desktopPrefs=JSON.parse(JSON.stringify(desktopDefaults));saveDesktop();closeDialog();await navigate('home');toast('Desktop layout reset.');}
    if(action==='new-share')dialog('A new shared folder.','<p class="small">Give it a simple name. Only your NAS account can access it.</p><label>Folder name<input name="name" placeholder="Documents" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,47}" maxlength="48" required autofocus></label>','Create folder',async data=>{await api('/api/shares',{name:data.get('name')});toast('Your shared folder is ready.');});
    if(action==='open-folder'){filePath=target.dataset.path;await navigate('files');}
    if(action==='browse-share'){filePath=target.dataset.name;await navigate('files');}
    if(action==='download')location.assign('/api/download?path='+encodeURIComponent(target.dataset.path));
    if(action==='new-folder')dialog('A little more organized.','<label>Folder name<input name="name" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,47}" maxlength="48" required autofocus></label>','Create folder',async data=>{await api('/api/folders',{path:filePath,name:data.get('name')});toast('Folder created.');});
    if(action==='upload')dialog('Bring something home.','<p class="small">Upload up to 64 MB per file. For larger files, connect through SMB.</p><label>Choose a file<input name="file" type="file" required></label>','Upload file',async data=>{const file=data.get('file');if(file.size>64*1024*1024)throw new Error('Choose a file under 64 MB, or transfer it through SMB.');await api('/api/upload?path='+encodeURIComponent(filePath)+'&name='+encodeURIComponent(file.name),undefined,{method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'}});toast('File uploaded.');});
    if(action==='snapshot'){await api('/api/snapshots',{share:target.dataset.name});toast('Snapshot job started. Follow it in Activity.');}
    if(action==='choose-snapshot'){const shares=await api('/api/shares');if(!shares.length)throw new Error('Create a shared folder first.');dialog('Keep this moment.','<label>Shared folder<select name="share">'+shares.map(s=>`<option>${E(s.name)}</option>`).join('')+'</select></label>','Create snapshot',async data=>{await api('/api/snapshots',{share:data.get('share')});toast('Snapshot job started. Follow it in Activity.');});}
    if(action==='restore')dialog('Bring a moment back.','<p class="small">Your current files stay in place. The snapshot becomes a new shared folder.</p><label>New folder name<input name="name" pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,47}" required maxlength="48"></label>','Restore folder',async data=>{await api('/api/restore',{snapshot:target.dataset.id,name:data.get('name')});toast('Restore job started. Follow it in Activity.');});
    if(action==='app')await showStoreApp(target.dataset.id,target.dataset.operation);
    if(action==='storage-wizard')await openStorageWizard();
    if(action==='storage-mode'){storageWizard.level=target.dataset.mode==='basic'?'basic':'1';if(storageWizard.level==='basic')storageDisks();else storageLevels();}
    if(action==='storage-back'){if(storageWizard.stage==='confirm'||storageWizard.stage==='name')storageDisks();else if(storageWizard.level==='basic')await openStorageWizard();else storageLevels();}
    if(action==='clear-store-search'){storeQuery='';if($('#store-search'))$('#store-search').value='';storeSearch();}
    if(action==='smart'){target.disabled=true;try{const result=await api('/api/smart',{path:target.dataset.path});const status=result.smart_status;dialog('Drive health.',`<p>${result.harbor_assessment?E(result.harbor_assessment):status?status.passed?'SMART reports that this drive passed its health assessment.':'SMART reports a health problem. Replace this drive and check your backup.':'This drive did not return an overall SMART assessment.'}</p><div class="detail"><span>Model</span><span>${E(result.model_name||result.device?.name||'Unknown')}</span></div><div class="detail"><span>Temperature</span><span>${E(result.temperature?.current??'Unavailable')}${result.temperature?' °C':''}</span></div><div class="detail"><span>Power-on hours</span><span>${E(result.power_on_time?.hours??'Unavailable')}</span></div>`,'Done',async()=>{});}finally{target.disabled=false;}}
  }catch(error){toast(error.message,true);}
});
$('#app-search')?.addEventListener('input',event=>{if(!['home','apps'].includes(route))navigate('home');else {if(route==='apps'){storeQuery=event.target.value;if($('#store-search'))$('#store-search').value=storeQuery;}applySearch();}});
$('#app-search')?.addEventListener('keydown',event=>{if(event.key==='Escape'){event.target.value='';applySearch();}if(event.key==='Enter'&&route==='home'){event.preventDefault();document.querySelector('.launcher-tile:not([hidden]) .launcher-button')?.click();}});
document.addEventListener('keydown',event=>{if(event.key==='/'&&!$('#modal').open&&!event.target.matches('input,textarea,select')){event.preventDefault();$('#app-search')?.focus();}});
document.addEventListener('keydown',async event=>{
  const tile=event.target.closest('[data-launcher]');
  if(!tile||!event.altKey||!['ArrowLeft','ArrowRight'].includes(event.key))return;
  event.preventDefault();
  const id=tile.dataset.launcher,order=[...document.querySelectorAll('[data-launcher]')].map(el=>el.dataset.launcher);
  const from=order.indexOf(id),to=from+(event.key==='ArrowRight'?1:-1);
  if(to<0||to>=order.length)return;
  order.splice(to,0,order.splice(from,1)[0]);desktopPrefs.order=order;saveDesktop();
  await navigate('home');
  [...document.querySelectorAll('[data-launcher]')].find(el=>el.dataset.launcher===id)?.querySelector('button,a')?.focus({preventScroll:true});
});
function clearPointerDrag(){pointerDrag=null;desktopDragging=false;draggedLauncher='';document.body.classList.remove('rearranging');document.querySelectorAll('.drag-over,.dragging-source').forEach(el=>el.classList.remove('drag-over','dragging-source'));}
document.addEventListener('pointerdown',event=>{
  const tile=event.target.closest('[data-launcher]');
  if(!tile||event.button!==0||event.pointerType!=='mouse')return;
  pointerDrag={id:tile.dataset.launcher,x:event.clientX,y:event.clientY,element:tile,pointerId:event.pointerId};
});
document.addEventListener('pointermove',event=>{
  if(!pointerDrag)return;
  if(!desktopDragging&&Math.hypot(event.clientX-pointerDrag.x,event.clientY-pointerDrag.y)<8)return;
  desktopDragging=true;draggedLauncher=pointerDrag.id;document.body.classList.add('rearranging');pointerDrag.element.classList.add('dragging-source');
  if(event.cancelable)event.preventDefault();
  const target=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-launcher]');
  document.querySelectorAll('.drag-over').forEach(el=>el.classList.remove('drag-over'));
  if(target&&target.dataset.launcher!==draggedLauncher)target.classList.add('drag-over');
});
document.addEventListener('pointerup',event=>{
  if(!pointerDrag)return;
  if(!desktopDragging){clearPointerDrag();return;}
  const id=pointerDrag.id,target=document.elementFromPoint(event.clientX,event.clientY)?.closest('[data-launcher]');
  suppressLauncherClickUntil=performance.now()+400;
  const order=[...document.querySelectorAll('[data-launcher]')].map(el=>el.dataset.launcher),from=order.indexOf(id),to=order.indexOf(target?.dataset.launcher);
  clearPointerDrag();
  if(from>=0&&to>=0&&from!==to){order.splice(to,0,order.splice(from,1)[0]);desktopPrefs.order=order;saveDesktop();navigate('home');}
});
document.addEventListener('pointercancel',clearPointerDrag);
document.addEventListener('click',event=>{if(performance.now()<suppressLauncherClickUntil&&event.target.closest('[data-launcher]')){event.preventDefault();event.stopImmediatePropagation();}},true);
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(csrf&&labels[next]&&next!==route)navigate(next);});
document.addEventListener('DOMContentLoaded',async()=>{try{health=await api('/api/health');setupRequired=health.setup_required;if(setupRequired){welcomeScreen();return;}try{const session=await api('/api/session');if(!health.onboarding_complete&&session.role==='owner'){csrf=session.csrf;username=session.username;featureTour();}else signedIn(session);}catch{showAuth();}}catch(error){showAuth();$('#auth-error').textContent=error.message;}},{once:true});
