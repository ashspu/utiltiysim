import { readSession, signOut, loginUrl, escapeHtml as esc } from './shell-session.js';
import { renderSchemaForm } from '/viewer/schema-form.js';
const status = document.getElementById('account-status'), root = document.getElementById('workspace-content');
let catalog, selected, draft, form, session, dirty = false, saveCommand = null;
const isOwner = () => session.grants.some(g => g.role === 'owner');
const worldLink = id => /^[0-9a-f]{32}$/.test(id || '') ? `/world-control.html?id=${id}` : null;
const startKey = setup => `utilitysim:start:${session.user.id}:${setup.id}`;
function readStart(setup) {
  const value = sessionStorage.getItem(startKey(setup));
  if (!value) return null;
  const record = JSON.parse(value);
  if (!record.payload?.commandId || record.payload.sourceId !== setup.sourceId) throw new Error('The saved start request needs recovery before starting this setup.');
  return record;
}
const canStart = setup => {
  const source = sourceFor(setup.sourceId);
  return Boolean(source?.canConfigure && source.canSave && source.sourceRevision === setup.sourceRevision
    && session.grants.some(g => g.role === 'owner' && (g.town === '*' || g.town === source.grantTownId)));
};
const sourceFor = id => catalog.sources.find(s => s.id === id);
async function api(url, options) {
  const response = await fetch(url,{cache:'no-store',...options});
  const value = await response.json();
  if (!response.ok) { const error=new Error(value.detail || 'Your workspace could not be loaded.');error.status=response.status;throw error; }
  return value;
}
const message = text => { status.textContent = text; };
const markDirty = () => { dirty = true; saveCommand = null; };
const mayLeave = () => !dirty || confirm('Leave this unsaved setup? Your last online save will be kept.');
window.addEventListener('beforeunload',event => { if(dirty) { event.preventDefault();event.returnValue=''; } });
document.getElementById('sign-out').onclick = () => { if(mayLeave()) { dirty=false;signOut().catch(()=>message('Could not log out. Please try again.')); } };
function home() {
  if (!mayLeave()) return;
  dirty=false; draft=null; selected=null;
  root.innerHTML=`<p class="eyebrow">YOUR WORKSPACE</p><h1>A world to make your own.</h1><p class="intro">Start with a town, or pick up where you left off.</p><div class="entry-choices"><button class="entry-choice" id="create-world"><span class="choice-symbol">＋</span><h2>Create a world</h2><p>Choose an illustrated town, then fine-tune its physical world settings.</p><strong>Choose a town →</strong></button><button class="entry-choice" id="open-simulation"><span class="choice-symbol">↗</span><h2>Open existing simulation</h2><p>Find saved setups and see which simulation worlds are available to resume.</p><strong>Open your library →</strong></button></div><p class="workspace-note">Online setup is available separately from simulation compute. Existing offline worlds stay in your offline library.</p>`;
  root.querySelector('#create-world').onclick=chooseTown;
  root.querySelector('#open-simulation').onclick=openLibrary;
}
const backButton = () => '<button class="back-button" id="workspace-back">← Your workspace</button>';
function chooseTown() {
  root.innerHTML=`${backButton()}<p class="eyebrow">CREATE A WORLD · 1 / 3</p><h1>First, choose your town.</h1><p class="intro">Preview a town with your pointer or keyboard. Select it to keep its map and population for your setup.</p><div class="town-picker"><div class="town-options" role="group" aria-label="Town templates">${catalog.sources.map(s=>`<button class="town-option" data-source="${esc(s.id)}" aria-pressed="${selected===s.id}"><strong>${esc(s.name)}</strong><span>${s.canConfigure?`${s.homes} mapped homes · accepted illustration`:'Illustrated zoning preview · in progress'}</span><small>${esc(s.description)}</small></button>`).join('')}<p class="workspace-note">Further illustrated presets are being prepared. Unfinished maps are not offered as playable worlds.</p></div><figure class="town-preview"><img id="town-preview-image" alt=""><figcaption><strong id="town-preview-name"></strong><span id="town-preview-caption"></span></figcaption></figure></div><div class="setup-actions"><p id="town-choice-status" role="status">Select a town to continue.</p><button class="primary" id="configure-world" disabled>Fine-tune this world →</button></div>`;
  root.querySelector('#workspace-back').onclick=home;
  const preview=id=>{const s=sourceFor(id);root.querySelector('#town-preview-image').src=s.previewSmall||s.preview;root.querySelector('#town-preview-image').alt=`${s.name} illustrated overhead view`;root.querySelector('#town-preview-name').textContent=s.name;root.querySelector('#town-preview-caption').textContent=s.previewLabel;};
  const select=id=>{selected=id;const s=sourceFor(id);root.querySelectorAll('[data-source]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.source===id)));root.querySelector('#town-choice-status').textContent=!s.canSave?'Owner access is required to save a setup.':s.canConfigure?`${s.name} selected. Geography and population stay fixed.`:`${s.name} is a preview. Setup opens when its map and property records are ready.`;root.querySelector('#configure-world').disabled=!s.canConfigure||!s.canSave;preview(id);};
  root.querySelectorAll('[data-source]').forEach(b=>{b.onmouseenter=()=>{if(!selected)preview(b.dataset.source);};b.onfocus=()=>{if(!selected)preview(b.dataset.source);};b.onclick=()=>select(b.dataset.source);});
  if(selected)select(selected);else if(catalog.sources.length)preview(catalog.sources[0].id);
  root.querySelector('#configure-world').onclick=()=>{const s=sourceFor(selected);draft={id:crypto.randomUUID(),revision:0,sourceId:s.id,sourceRevision:s.sourceRevision,snapshotSha256:s.snapshotSha256,name:`${s.name} world`,start:new Date().toISOString().slice(0,10),configuration:structuredClone(catalog.configuration.defaults)};dirty=false;saveCommand=null;configure();};
}
function configure() {
  const source=sourceFor(draft.sourceId);
  root.innerHTML=`${backButton()}<p class="eyebrow">CREATE A WORLD · 2 / 3</p><h1>Give your world its starting conditions.</h1><div class="setup-layout"><aside class="selected-town"><img src="${esc(source.previewSmall||source.preview)}" alt="${esc(source.name)} whole map"><h2>${esc(source.name)}</h2><p>${source.homes} homes · ${source.premises} premises · ${source.meters.toLocaleString()} meters</p><p>Population, properties and utility geography belong to this preset and stay fixed.</p><small>Physical settings only. Operational workflows and billing belong in Virtual Systems.</small></aside><form id="setup-form"><div class="identity-fields"><label>World name<input id="world-name" maxlength="120" required value="${esc(draft.name)}"></label><label>Start date<input id="world-start" type="date" required value="${esc(draft.start)}"></label></div><p class="workspace-note">The first online controls cover daily weather and meter condition. More physical-world settings are being brought into this wizard. Dates use the engine’s daily UTC clock.</p><div id="physical-settings"></div><div class="setup-actions"><button type="button" id="change-town" ${draft.revision?'hidden':''}>← Town selection</button><button class="primary" type="submit">Review setup →</button></div></form></div>`;
  root.querySelector('#workspace-back').onclick=home;
  root.querySelector('#change-town').onclick=()=>{if(mayLeave()){dirty=false;draft=null;chooseTown();}};
  for(const [id,key] of [['world-name','name'],['world-start','start']])root.querySelector('#'+id).oninput=e=>{draft[key]=e.target.value;markDirty();};
  form=renderSchemaForm(root.querySelector('#physical-settings'),catalog.configuration.schemas.world,{values:draft.configuration.world,base:catalog.configuration.defaults.world,showAdvanced:true,baseLabel:'Default',onChange:()=>{draft.configuration.world=structuredClone(form.values);markDirty();}});
  root.querySelector('#setup-form').onsubmit=e=>{e.preventDefault();if(form.invalid()||!e.target.reportValidity())return;draft.configuration.world=structuredClone(form.values);review();};
}
function review() {
  const source=sourceFor(draft.sourceId),schema=catalog.configuration.schemas.world;
  root.innerHTML=`${backButton()}<p class="eyebrow">CREATE A WORLD · 3 / 3</p><h1>Ready to save your setup.</h1><p class="intro">Save these starting conditions to your account. Running the simulation will become available when online compute is connected.</p><section class="setup-review"><h2>${esc(draft.name)}</h2><dl><div><dt>Town</dt><dd>${esc(source.name)} · fixed population and geography</dd></div><div><dt>Start date</dt><dd>${esc(draft.start)}</dd></div>${Object.entries(schema.properties).flatMap(([group,s])=>Object.entries(s.properties).map(([key,f])=>`<div><dt>${esc(f.title)}</dt><dd>${esc(draft.configuration.world[group][key])}${f['x-unit']?' '+esc(f['x-unit']):''}</dd></div>`)).join('')}</dl><p class="workspace-note">This creates a saved setup, with no simulated days or bill processing.</p><div class="setup-actions"><button id="edit-setup">← Edit settings</button><button class="primary" id="save-setup">Save setup online</button></div><p id="save-status" role="status"></p></section>`;
  root.querySelector('#workspace-back').onclick=home;root.querySelector('#edit-setup').onclick=configure;
  root.querySelector('#save-setup').onclick=async()=>{
    const button=root.querySelector('#save-setup'), feedback=root.querySelector('#save-status');button.disabled=true;feedback.textContent='Saving to your account…';
    saveCommand ||= crypto.randomUUID();
    const {id,revision,name,start,sourceId,sourceRevision,snapshotSha256,configuration}=draft;
    try{const {setup}=await api('/api/setups',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,revision,name,start,sourceId,sourceRevision,snapshotSha256,configuration,commandId:saveCommand})});draft=setup;dirty=false;saveCommand=null;message('Setup saved online. No simulation has been started.');await openLibrary();}
    catch(error){feedback.textContent=error.message;button.disabled=false;}
  };
}
async function openLibrary() {
  if(!mayLeave())return;
  dirty=false;
  root.innerHTML=`${backButton()}<p class="eyebrow">YOUR LIBRARY</p><h1>Pick up where you left off.</h1><h2>Saved setups</h2><p class="workspace-note">Starting conditions saved to your account. Starting a simulation pins these values; its initial settings cannot be edited afterward.</p><div id="saved-setups" class="saved-setups" role="status">Loading saved setups…</div><section class="runtime-note"><h2>Existing simulations</h2>${isOwner()?'<p><a href="/compute-connection.html">Manage compute connection →</a></p>':''}<div id="runtime-library" role="status">Loading your simulation worlds…</div><p class="workspace-note">Existing offline simulations and their history remain in the offline app.</p></section>`;
  root.querySelector('#workspace-back').onclick=home;
  const list=root.querySelector('#saved-setups');
  const runtime=root.querySelector('#runtime-library');
  void loadWorlds(runtime);
  try{const {setups}=await api('/api/setups');if(!list.isConnected)return;list.removeAttribute('role');list.innerHTML=setups.length?setups.map(s=>`<article class="saved-setup"><span class="eyebrow">SAVED STARTING CONDITIONS</span><h3>${esc(s.name)}</h3><p>${esc(sourceFor(s.sourceId)?.name||s.sourceId)} · starts ${esc(s.start)}</p><small>Saved ${esc(new Date(s.updatedAt).toLocaleString())}</small><div class="saved-setup-actions"><button data-open-setup="${esc(s.id)}">Review setup →</button>${canStart(s)?`<button class="primary" data-start-setup="${esc(s.id)}">Start simulation</button>`:''}</div><p class="start-feedback" role="status"></p></article>`).join(''):'<p>No online setups saved yet. Create a world to choose its starting conditions.</p>';list.querySelectorAll('[data-open-setup]').forEach(b=>b.onclick=()=>{const saved=setups.find(s=>s.id===b.dataset.openSetup),source=sourceFor(saved.sourceId);if(!source||!source.canConfigure||source.sourceRevision!==saved.sourceRevision){message('This saved setup uses an unavailable map revision. Its values have been preserved; migration is required before editing.');return;}draft=structuredClone(saved);dirty=false;saveCommand=null;configure();});
    list.querySelectorAll('[data-start-setup]').forEach(button=>{
      const setup=setups.find(s=>s.id===button.dataset.startSetup),feedback=button.closest('article').querySelector('.start-feedback');
      try { const pending=readStart(setup); if(pending?.worldId){showStarted(button,feedback,pending.worldId);return;} if(pending){button.textContent='Retry original start';feedback.textContent='A previous start has not been confirmed. Retry uses its original saved conditions.';} }
      catch(error){button.disabled=true;feedback.textContent=error.message;return;}
      button.onclick=()=>startSetup(setup,button,feedback,runtime);
    });
  }
  catch(error){list.textContent=error.message;const retry=document.createElement('button');retry.textContent='Retry saved setups';retry.onclick=openLibrary;list.append(retry);}
}
function showStarted(button,feedback,id) {
  const href=worldLink(id);
  if(!href)throw new Error('The runtime returned an invalid simulation identifier. Retry the original start request.');
  button.disabled=true;button.textContent='Simulation started';
  feedback.innerHTML=`<a href="${href}">Open simulation →</a><br>Its initial settings are fixed. Editing the saved setup does not change this world.`;
}
async function startSetup(setup,button,feedback,runtime) {
  if(!canStart(setup))return;
  button.disabled=true;feedback.textContent='Starting your simulation…';
  try {
    let record=readStart(setup);
    if(record?.worldId){showStarted(button,feedback,record.worldId);return;}
    if(!record){const {sourceId,sourceRevision,name,start,configuration}=setup;record={setupRevision:setup.revision,payload:{commandId:crypto.randomUUID(),sourceId,sourceRevision,name,start,configuration:structuredClone(configuration)}};}
    // Persist before sending. A lost response or reload must replay exactly this command and payload.
    sessionStorage.setItem(startKey(setup),JSON.stringify(record));
    const world=await api('/api/compute?action=create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(record.payload)});
    if(!worldLink(world.id))throw new Error('The runtime returned an invalid simulation identifier.');
    record.worldId=world.id;sessionStorage.setItem(startKey(setup),JSON.stringify(record));
    showStarted(button,feedback,world.id);
    if(runtime.isConnected)void loadWorlds(runtime);
  }catch(error){feedback.textContent=`${error.message} The original start request is retained; retry it to recover the same simulation.`;button.disabled=false;button.textContent='Retry original start';}
}
async function loadWorlds(container,offset=0) {
  container.textContent='Loading your simulation worlds…';
  try {
    const result=await api(`/api/compute?action=worlds&offset=${offset}&limit=25`);
    if(!Array.isArray(result.worlds)||!Number.isInteger(result.total)||!Number.isInteger(result.offset)||!Number.isInteger(result.limit)||result.limit<1)throw new Error('The runtime returned an invalid simulation library.');
    if(!container.isConnected)return;
    container.innerHTML=result.worlds.length?`<div class="saved-setups">${result.worlds.map(world=>{const href=worldLink(world.id);return `<article class="saved-setup"><span class="eyebrow">SIMULATION · ${esc(world.state||'STATUS UNAVAILABLE')}</span><h3>${esc(world.name||'Saved simulation')}</h3><p>${esc(sourceFor(world.sourceId)?.name||world.sourceId)}</p><p>${world.through?`Through ${esc(world.through)}`:`Starts ${esc(world.start||'date unavailable')}`}</p>${world.available===false?`<p>${esc(world.error||'This simulation is currently unavailable.')}</p>`:''}${href?`<a class="runtime-open" href="${href}">Open simulation →</a>`:'<p>Invalid simulation identity; contact the runtime owner.</p>'}</article>`;}).join('')}</div>`:'<p>No online simulations are saved on this connected runtime.</p>';
    if(result.total>result.limit){const pages=document.createElement('div');pages.className='runtime-pagination';pages.innerHTML=`<button data-page="previous" ${offset===0?'disabled':''}>← Previous</button><span>${result.total} simulations</span><button data-page="next" ${result.offset+result.limit>=result.total?'disabled':''}>Next →</button>`;pages.querySelector('[data-page="previous"]').onclick=()=>loadWorlds(container,Math.max(0,result.offset-result.limit));pages.querySelector('[data-page="next"]').onclick=()=>loadWorlds(container,result.offset+result.limit);container.append(pages);}
  }catch(error){if(!container.isConnected)return;container.textContent=error.status===503?`Online compute is disconnected or unavailable. ${error.message}`:`Simulation library could not be loaded. ${error.message}`;const retry=document.createElement('button');retry.textContent='Retry simulation library';retry.onclick=()=>loadWorlds(container,offset);container.append(retry);}
}
async function start(){
  try{session=await readSession();if(!session.authenticated){location.replace(loginUrl('/workspace.html'));return;}if(!session.grants.length){message('Your account is awaiting workspace access from an administrator.');return;}catalog=await api('/api/setups?view=catalog');message(`Welcome, ${session.user.name||session.user.email}.`);home();}
  catch(error){message(error.message);}
}
start();
