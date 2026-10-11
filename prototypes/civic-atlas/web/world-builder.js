const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderWorldBuilder(entry={}) {
  const budget=entry.featureBudget||{}, readiness=entry.readiness||{};
  const actual=entry.actualHomes??budget.homes;
  const state=value=>value===true?'Ready':value===false?'Pending':'Not reported';
  const fields=[['homes','Target homes',entry.targetHomes||500,450,50000],['pools','Pools',budget.pools||0,0,45000],
    ['schools','Schools',budget.school||1,1,100],['church','Churches',budget.church||1,1,1],
    ['shops','Commercial premises',budget.commercial||16,1,2000],['industry','Industrial premises',budget.industrial||6,1,600],
    ['seed','Layout seed',427,0,2147483647]];
  return `<div class="panel"><h2>Feature budget & release readiness</h2><div class="cards">
    <div class="card"><small>Target homes</small><strong>${esc(entry.targetHomes||'—')}</strong><small>Acceptable range ${Math.ceil((entry.targetHomes||0)*.9)}–${Math.floor((entry.targetHomes||0)*1.1)}</small></div>
    <div class="card"><small>Mapped homes</small><strong>${esc(actual??'Pending')}</strong><small>Other feature counts are explicit budgets</small></div>
    <div class="card"><small>Measured source</small><strong>${state(readiness.sourceBaked)}</strong><small>Zoom tiles: ${state(readiness.zoomTiles)}</small></div>
    <div class="card"><small>Internal visual QA</small><strong>${entry.internalVisualReview?.status==='passed'?'Passed':entry.internalVisualReview?.status==='outdated'?'Source changed':'Pending'}</strong><small>${entry.userVisualApproval?'User accepted':'Optional user acceptance pending'}</small></div></div>
    <p class="subtle">Saved runtime: ${state(readiness.savedWorld)}. External Virtual Systems installation: ${state(readiness.externalVirtualSystems)}.</p></div>
    <div class="panel"><h2>Start with the world inputs</h2><p>Export a new version's configuration before making the map. The local factory builds zoning, roads, property ownership and utility identities from this budget. Artwork and visual review follow the measured geometry.</p>
    <form id="world-draft"><div class="builder-grid"><label>New preset ID<input name="id" required pattern="[a-z][a-z0-9-]{2,79}" value="${esc(entry.id||'new-town')}-custom"></label>
    <label>Town name<input name="name" required maxlength="120" value="${esc(entry.name||'New Town')} Custom"></label>
    ${fields.map(([name,label,value,min,max])=>`<label>${label}<input name="${name}" type="number" required min="${min}" max="${max}" step="1" value="${value}"></label>`).join('')}
    <label>District style<select name="palette">${['forest','orchard','coastal','ash','copper','wetland','foxglove'].map(p=>`<option ${entry.palette===p?'selected':''}>${p}</option>`).join('')}</select></label>
    <label class="builder-wide">Town character<input name="character" required maxlength="500" value="${esc(entry.character||'A leafy town with connected streets and a public green')}"></label></div>
    <p class="subtle">Home allowance: ±10%. Solar: zero. Pools, schools, churches and other uses are specified separately. New IDs are required; the factory refuses to overwrite an existing map.</p>
    <button class="primary">Download world configuration</button></form>
    <div id="builder-result" hidden><h3>Build & inspect locally</h3><pre id="builder-commands"></pre><p class="subtle">These commands are instructions for your local checkout. Exporting the configuration does not run a build or change the active saved world. Review density, road access, artwork and seams before adding a new map to the curated catalog.</p></div></div>`;
}

export function bindWorldBuilder(notice) {
  const form=document.getElementById('world-draft');
  if(!form)return;
  form.onsubmit=event=>{
    event.preventDefault();
    if(!form.reportValidity())return;
    const values=Object.fromEntries(new FormData(form));
    for(const key of ['homes','pools','schools','church','shops','industry','seed'])values[key]=Number(values[key]);
    if(values.pools>Math.floor(values.homes*.9)){notice('Pools must fit within the minimum accepted home count.');return;}
    if(values.schools>Math.ceil(values.homes/500)){notice('Use at most one school per 500 target homes, rounded up.');return;}
    const data={...values,solar:0,homeTolerance:0.1};
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=values.id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),3000);
    document.getElementById('builder-result').hidden=false;
    document.getElementById('builder-commands').textContent=
      `python prototypes/civic-atlas/build-town.py --config ${values.id}.json`;
    notice('World inputs exported. The active town and its billing history were not changed.');
  };
}
