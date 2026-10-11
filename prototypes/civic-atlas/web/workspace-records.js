// Read-only views of durable records; no browser-calculated simulation values.
export function createRecordsViews({api,esc,fmt,day,route,getTown,getArtwork,onMap}){
 let qualityVersion=0,historyVersion=0,home=null,offset=0;
 const qualityHost=document.getElementById('quality-page'),activityHost=document.getElementById('activity-page');
 const download=(name,data)=>{
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 };
 const button=(id,text)=>`<button id="${id}" class="inspector-button">${text}</button>`;
 async function quality(){
  const version=++qualityVersion;
  qualityHost.innerHTML='<div class="content-heading"><div><span class="eyebrow">TOWN QUALITY</span><h1>Checking the saved world…</h1><p role="status">Reading source geometry and durable records.</p></div></div>';
  try{
   const report=await api('quality');if(version!==qualityVersion)return;
   const passed=report.checks.filter(c=>c.status==='pass').length,art=getArtwork();
   const artSummary=getTown().atlasDesign?.presetId?'<p>This preset renders buildings and parcels from its baked geometry. The concept image is a design reference; painted houses do not create system records.</p>':`<p>${fmt(art.readyCount||0)} of ${fmt(art.totalBlocks||0)} source-compatible placements are ready. ${fmt(art.fallbackCount||0)} use native fallback.</p><p>${fmt(art.textureCount||0)} shared textures. These are reusable block illustrations, not unique images for every home.</p>`;
   qualityHost.innerHTML=`<div class="content-heading"><div><span class="eyebrow">TOWN QUALITY · SAVED RECORDS</span><h1>${report.automatedPassed?'Source checks passed.':'Source checks need attention.'}</h1><p>${passed} of ${report.checks.length} automated checks pass. Visual acceptance remains a separate review.</p></div><button id="run-quality" class="primary">Run checks again</button></div>
    <div class="quality-summary"><span class="pill">${esc(getTown().atlasDesign?.name||'Saved town')}</span><span>Next physical day: ${day(report.through)}</span><span>Checked ${esc(new Date(report.generatedAt).toLocaleString())}</span></div>
    <div class="panel"><h2>Source geometry and saved state</h2><div class="quality-checks">${report.checks.map(c=>`<article class="quality-check" data-check="${esc(c.id)}"><span class="quality-result ${c.status==='pass'?'status-good':'status-warn'}">${c.status==='pass'?'PASS':c.status==='blocked'?'BLOCKED':'FAIL'}</span><div><h3>${esc(c.title)}</h3><p>${esc(c.detail)}</p>${c.failureCount?`<p class="status-warn">${fmt(c.failureCount)} issue(s): ${c.examples.map(esc).join(', ')}</p>`:''}</div></article>`).join('')}</div></div>
    <div class="config-grid quality-review"><div class="panel"><h2>Artwork in this browser</h2>${artSummary}${button('quality-map','Review the live town →')}</div><div class="panel"><h2>Still requires review</h2><ul>${report.reviewRequired.map(item=>`<li>${esc(item)}</li>`).join('')}</ul></div></div>
    <div class="panel"><h2>Reproducible evidence</h2><p>This report identifies the exact source snapshot and saved day. Browser interaction tests are run separately; a source pass does not certify the artwork.</p><details><summary>Source identity</summary><p>${esc(report.townId)}</p><code class="source-hash">${esc(report.snapshotSha256)}</code></details>${button('export-quality','Download quality report (JSON)')}</div>`;
   document.getElementById('run-quality').onclick=quality;
   document.getElementById('quality-map').onclick=()=>route('map');
   document.getElementById('export-quality').onclick=()=>download((getTown().atlasDesign?.presetId||'fairhaven')+'-quality.json',report);
  }catch(error){
   if(version!==qualityVersion)return;
   qualityHost.innerHTML=`<div class="panel"><h1>Quality checks unavailable</h1><p role="alert">${esc(error.message)}</p>${button('retry-quality','Retry checks')}</div>`;
   document.getElementById('retry-quality').onclick=quality;
  }
 }
 async function history(){
  if(!home)return;
  const version=++historyVersion,current=home;
  activityHost.innerHTML=`<div class="content-heading"><div><span class="eyebrow">PROPERTY HISTORY</span><h1>${esc(current.address)}</h1><p role="status">Opening saved daily readings…</p></div></div>`;
  try{
   const data=await api(`premises/${encodeURIComponent(current.id)}/history?offset=${offset}&limit=14`);
   if(version!==historyVersion||home?.id!==current.id)return;
   activityHost.innerHTML=`<div class="content-heading"><div><span class="eyebrow">PROPERTY HISTORY · ADMINISTRATOR</span><h1>${esc(data.premise.address)}</h1><p>Daily meter observations and physical use from saved records. ${esc(data.premise.id)}</p></div><button id="history-map" class="primary">Return to property</button></div>
    <div class="activity-filter"><button id="history-world">All world activity</button><span>${data.days.length?`${day(data.days.at(-1))} – ${day(data.days[0])}`:'No completed days'}</span></div>
    <div class="panel"><h2>Recorded utility use</h2><p>Missing quantities are shown as “Not recorded”. Physical use and observed use can differ when a meter drifts or fails.</p><div class="table-scroll"><table class="activity-table"><thead><tr><th>PHYSICAL DATE</th><th>SERVICE</th><th>OBSERVED USE</th><th>PHYSICAL USE</th><th>OBSERVATION</th></tr></thead><tbody>${data.readings.map(r=>`<tr data-observation="${esc(r.observationId||'')}"><td>${day(r.day)}</td><td>${esc(r.commodity==='electric'?'Electricity':r.commodity[0].toUpperCase()+r.commodity.slice(1))}<small class="record-id">${esc(r.assetId)}</small></td><td>${fmt(r.observedQuantity)} ${esc(r.unit==='m3'?'m³':r.unit)}</td><td>${fmt(r.physicalQuantity)} ${esc(r.unit==='m3'?'m³':r.unit)}</td><td>${esc(r.status||'Not recorded')}</td></tr>`).join('')||'<tr><td colspan="5">No saved readings in this period.</td></tr>'}</tbody></table></div>
    <div class="history-pagination"><button id="history-newer" ${offset===0?'disabled':''}>← Newer days</button><span>${fmt(data.totalDays)} completed days · up to 14 per page</span><button id="history-older" ${offset+data.limit>=data.totalDays?'disabled':''}>Older days →</button></div></div>
    <div class="notice">These are saved physical records. They do not establish delivery to an external application or live flow/pressure measurements.</div>${button('export-history','Download these readings (JSON)')}`;
   document.getElementById('history-map').onclick=()=>{route('map');onMap(current);};
   document.getElementById('history-world').onclick=()=>{home=null;++historyVersion;document.dispatchEvent(new Event('atlas-world-activity'));};
   document.getElementById('history-newer').onclick=()=>{offset=Math.max(0,offset-14);history();};
   document.getElementById('history-older').onclick=()=>{offset+=14;history();};
   document.getElementById('export-history').onclick=()=>download(`${current.id}-readings.json`,data);
  }catch(error){
   if(version!==historyVersion)return;
   activityHost.innerHTML=`<div class="panel"><h1>Property history unavailable</h1><p role="alert">${esc(error.message)}</p>${button('retry-history','Retry history')}${button('history-map','Return to property')}</div>`;
   document.getElementById('retry-history').onclick=history;
   document.getElementById('history-map').onclick=()=>{route('map');onMap(current);};
  }
 }
 return {quality,history,get activeHistory(){return Boolean(home);},showHistory(property){home=property;offset=0;route('activity');history();}};
}
