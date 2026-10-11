const $=s=>document.querySelector(s),object=$('#vector'),ns='http://www.w3.org/2000/svg';

let svg,doc,data,mode='vector',box=[0,0,1536,1024],drag=null,moved=false,three=null,selectionToken=0,activeDistrict=null;

const loaded=new Promise((resolve,reject)=>{function inspect(){try{const d=object.contentDocument;if(d?.documentElement?.localName==='svg'){resolve(d);return true;}}catch(e){reject(e);}return false;}if(!inspect())object.addEventListener('load',()=>{if(!inspect())reject(Error('Vector SVG did not load'));},{once:true});});

function view(next){box=next;svg.setAttribute('viewBox',box.join(' '));}

function zoom(f,x=box[0]+box[2]/2,y=box[1]+box[3]/2){const w=Math.max(65,Math.min(2400,box[2]*f)),ratio=w/box[2];view([x+(box[0]-x)*ratio,y+(box[1]-y)*ratio,w,box[3]*ratio]);}

function svgPoint(e){return new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());}

function setMode(next){mode=next;const isThree=['three','landscape'].includes(next);for(const b of document.querySelectorAll('[data-mode]'))b.setAttribute('aria-pressed',String(b.dataset.mode===next));$('#blend').hidden=next!=='compare';$('#three-view').hidden=!isThree;object.hidden=isThree;for(const id of ['reference-artwork','landscape-features','farm-buildings','authored-properties'])doc.getElementById(id).style.opacity=next==='concept'?0:next==='compare'?$('#opacity').value/100:1;doc.getElementById('approved-raster').style.display=['concept','compare'].includes(next)?'':'none';$('#hint').textContent=isThree?'Drag to orbit · scroll to zoom · select a building or landscape area':'Scroll to zoom · drag to pan · select a field or an authored property';if(isThree)showThree();}

function clear(){selectionToken++;$('#selection').hidden=true;for(const e of doc.querySelectorAll('.selected'))e.classList.remove('selected');three?.select(null);}

function selectLandscape(id){clear();const f=data.landscape.find(x=>x.id===id);if(!f)return;doc.getElementById(id).classList.add('selected');three?.select(id);$('#selection').hidden=false;$('#selection-kind').textContent='TRACED LANDSCAPE BOUNDARY';$('#selection-title').textContent=id.replace('-',' · ');$('#selection-description').textContent=`${(f.areaM2/10000).toFixed(2)} hectares at the town’s current scale. Boundary traced from the approved image; classification is a draft.`;$('#record-details').textContent=`${f.polygon.length-1} boundary vertices · ${f.holes.length} interior exclusions`;$('#record-link').hidden=true;}

function selectFarm(id){clear();const f=data.farmBuildings.find(x=>x.id===id);if(!f)return;doc.getElementById(id).classList.add('selected');three?.select(id);$('#selection').hidden=false;$('#selection-kind').textContent='TRACED FARM BUILDING';$('#selection-title').textContent=f.farmstead.replaceAll('-',' ');$('#selection-description').textContent='Roof boundary traced from the approved plan. Building use and height need review; no utility customer has been assigned.';$('#record-details').textContent=`${f.id} · ${f.areaM2.toFixed(0)} m² footprint · illustrative ${f.heightM} m height`;$('#record-link').hidden=true;}

async function selectProperty(id){clear();const p=data.properties.find(x=>x.premiseId===id);if(!p)return;const token=selectionToken;three?.select(id);doc.getElementById(p.binding.buildingId)?.classList.add('selected');$('#selection').hidden=false;$('#selection-kind').textContent='AUTHORED PARCEL · LINKED LIVE ID';$('#selection-title').textContent=`${p.district} ${p.id}`;$('#selection-description').textContent='Parcel, driveway and footprint share one editable geometry record. '+(p.accessType==='shared-drive'?'This rear lot reaches the public street through an authored shared driveway. ':'')+'The live simulation still uses its earlier placement.';$('#record-details').textContent=`${id} · ${p.binding.address} · ${p.binding.parcelId} · ${p.binding.buildingId} · ${p.binding.meterIds.length} linked meters`;$('#record-link').hidden=false;$('#record-link').href=`/?premise=${encodeURIComponent(id)}#map`;try{const response=await fetch(`/atlas/api/premises/${encodeURIComponent(id)}/history?limit=1`);if(!response.ok)throw Error('History unavailable');const history=await response.json();if(selectionToken!==token)return;const count=history.readings?.length||0;$('#record-details').append(document.createElement('br'),document.createTextNode(count?'Saved meter history verified for this live property.':'Live record reached; no readings returned.'));}catch{if(selectionToken===token)$('#record-details').append(document.createElement('br'),document.createTextNode('Saved history could not be loaded.'));}}

async function showThree(){if(!three){$('#loading').hidden=false;$('#loading').textContent=`Building ${data.properties.length} property drafts and the surrounding landscape…`;try{const {createStudy}=await import('./review-three.js?v=12');three=await createStudy($('#three-view'),data,selectProperty,selectLandscape,selectFarm);}catch(e){$('#loading').textContent=e.message;return;}$('#loading').hidden=true;}three.frame(mode==='landscape'?[0,0,1536,1024]:activeDistrict?data.districts.find(d=>d.id===activeDistrict).viewBox:data.reviewBounds);}

try{

const results=await Promise.all([loaded,fetch('reconstruction.json?v=12').then(r=>{if(!r.ok)throw Error('Geometry unavailable');return r.json();})]);[doc,data]=results;svg=doc.documentElement;for(const el of document.querySelectorAll('[data-property-count]'))el.textContent=data.properties.length;$('#status').textContent=`Whole-image vector artwork · ${data.properties.length} authored property drafts · saved town unchanged`;

const ref=doc.createElementNS(ns,'image');ref.id='approved-raster';ref.setAttribute('href','concept.png');ref.setAttribute('width','1536');ref.setAttribute('height','1024');ref.style.display='none';svg.insertBefore(ref,svg.firstChild);

svg.style.touchAction='none';svg.style.userSelect='none';

svg.addEventListener('wheel',e=>{e.preventDefault();const p=svgPoint(e);zoom(e.deltaY>0?1.13:1/1.13,p.x,p.y);},{passive:false});

svg.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,point:svgPoint(e),target:e.target};moved=false;svg.setPointerCapture(e.pointerId);});

svg.addEventListener('pointermove',e=>{if(!drag)return;if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)>4)moved=true;if(moved){const p=svgPoint(e);view([box[0]+drag.point.x-p.x,box[1]+drag.point.y-p.y,box[2],box[3]]);}});

svg.addEventListener('pointerup',e=>{const t=drag?.target;drag=null;if(svg.hasPointerCapture(e.pointerId))svg.releasePointerCapture(e.pointerId);if(moved||!t||mode==='concept')return;const property=t.closest('[data-premise-id]'),land=t.closest('[data-landscape-id]');if(property)selectProperty(property.dataset.premiseId);else if(t.closest('[data-farm-id]'))selectFarm(t.closest('[data-farm-id]').dataset.farmId);else if(land)selectLandscape(land.dataset.landscapeId);});

svg.addEventListener('pointercancel',()=>{drag=null;});

doc.addEventListener('keydown',e=>{if(e.key==='Escape')clear();if(e.key==='Enter'||e.key===' '){const p=e.target.closest('[data-premise-id]'),l=e.target.closest('[data-landscape-id]'),f=e.target.closest('[data-farm-id]');if(p||l||f){e.preventDefault();if(p)selectProperty(p.dataset.premiseId);else if(f)selectFarm(f.dataset.farmId);else selectLandscape(l.dataset.landscapeId);}}});

for(const b of document.querySelectorAll('[data-mode]'))b.onclick=()=>setMode(b.dataset.mode);

$('#fit').onclick=()=>{activeDistrict=null;setMode('vector');view([0,0,1536,1024]);};for(const district of data.districts)$(`#${district.id}`).onclick=()=>{activeDistrict=district.id;setMode('vector');view(district.viewBox);};$('#fields').onclick=()=>{activeDistrict=null;if(['three','landscape'].includes(mode))three?.frame([0,620,540,405]);else{setMode('vector');view([0,620,540,405]);}};$('#zoom-in').onclick=()=>['three','landscape'].includes(mode)?three?.zoom(.8):zoom(.8);$('#zoom-out').onclick=()=>['three','landscape'].includes(mode)?three?.zoom(1.25):zoom(1.25);

$('#opacity').oninput=()=>setMode('compare');$('#clear-selection').onclick=clear;

$('#landscape-toggle').onchange=e=>{for(const f of doc.querySelectorAll('[data-landscape-id]')){f.style.stroke=e.target.checked?({field:'#a07840',woodland:'#406348',greenspace:'#71983c',water:'#418faa'}[f.dataset.kind]):'';f.style.strokeWidth=e.target.checked?'.8':'';f.style.fill=e.target.checked?(f.dataset.baseFill||'#ffffff0b'):'';}};

$('#hide-tools').onclick=()=>{$('#tools').hidden=true;$('#show-tools').hidden=false;};$('#show-tools').onclick=()=>{$('#tools').hidden=false;$('#show-tools').hidden=true;};$('#about-toggle').onclick=()=>{$('#about').hidden=!$('#about').hidden;$('#about-toggle').setAttribute('aria-expanded',String(!$('#about').hidden));};document.addEventListener('keydown',e=>{if(e.key==='Escape'){clear();$('#about').hidden=true;$('#about-toggle').setAttribute('aria-expanded','false');}});

$('#loading').hidden=true;document.body.dataset.ready='true';window.reconstructionDiagnostics=()=>({mode,viewBox:[...box],properties:data.properties.length,landscape:data.landscape.length,three:three?.stats||null});

}catch(e){$('#loading').textContent=`Could not load reconstruction: ${e.message}`;}
