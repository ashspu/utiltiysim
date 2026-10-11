const $=s=>document.querySelector(s),NS='http://www.w3.org/2000/svg',S=1.7;
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const geom=await fetch('geometry.json').then(r=>{if(!r.ok)throw Error('Geometry unavailable');return r.json()});
window.sampleData=geom;
const byId=new Map(geom.properties.map(p=>[p.id,p])),roadById=new Map(geom.roads.map(r=>[r.id,r]));
const path=(pts,close=true)=>'M'+pts.map(p=>`${p.x/S},${p.z/S}`).join('L')+(close?'Z':'');
function add(parent,attrs){const node=document.createElementNS(NS,'path');for(const [k,v]of Object.entries(attrs))node.setAttribute(k,v);$(parent).append(node);return node}
for(const p of geom.parcels){const d=path(p.polygon);add('#boundaries',{d,class:'boundaries'});const node=add('#properties',{d,class:'hits','data-id':p.premiseId,tabindex:0,role:'button','aria-label':`${p.premiseId} ${byId.get(p.premiseId).buildingType}`});node.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selectProperty(p.premiseId)}})}
for(const r of geom.roads){const node=add('#roads',{d:path(r.points,false),class:'road-hit','stroke-width':r.pavementWidthM/S,'data-road':r.id,tabindex:0,role:'button','aria-label':r.name});node.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();selectRoad(r.id)}});const q=r.points[Math.floor(r.points.length/2)],t=document.createElementNS(NS,'text');t.setAttribute('x',q.x/S);t.setAttribute('y',q.z/S);t.setAttribute('class','labels');t.textContent=r.name;$('#labels').append(t)}
for(const p of geom.properties)if(p.poolPolygon)add('#poolMarks',{d:path(p.poolPolygon),class:'pool-mark'});
for(const r of geom.roads)add('#roadAudit',{d:path(r.points,false),fill:'none',stroke:'#ecbe58','stroke-width':r.pavementWidthM/S,opacity:.5,'stroke-linejoin':'round','stroke-linecap':'round'});
$('#status').textContent=`${geom.budget.homes} homes · 100 pools · 0 solar · ${geom.properties.length} mapped premises`;
let bounds=[0,0,1536,1024],selection=0;
function detailLayer(){const hybrid=$('#stage').value==='hybrid';$('#pilotArt').style.display=hybrid&&bounds[2]<700?'':'none';$('#furnitureArt').style.display=hybrid?'':'none'}
function frame(b){bounds=b;$('#map').setAttribute('viewBox',b.join(' '));detailLayer()}
window.mapView={get:()=>bounds,frame};
function zoom(f,c=[.5,.5]){const w=Math.min(2100,Math.max(75,bounds[2]*f)),h=w*2/3;frame([bounds[0]+(bounds[2]-w)*c[0],bounds[1]+(bounds[3]-h)*c[1],w,h])}
$('#plus').onclick=()=>zoom(.7);$('#minus').onclick=()=>zoom(1/.7);
$('#whole').onclick=()=>frame([0,0,1536,1024]);$('#pilot').onclick=()=>frame([420,90,240,160]);$('#mainStreet').onclick=()=>frame([605,274,300,200]);$('#industry').onclick=()=>frame([936,563,270,180]);
$('#menu').onclick=()=>{const t=$('#tools');t.hidden=!t.hidden;$('#menu').setAttribute('aria-expanded',String(!t.hidden))};
$('#parcels').onchange=()=>$('#boundaries').style.display=$('#parcels').checked?'':'none';
$('#pools').onchange=()=>$('#poolMarks').style.display=$('#pools').checked?'':'none';$('#pools').onchange();
$('#roadNames').onchange=()=>$('#labels').style.display=$('#roadNames').checked?'':'none';$('#roadNames').onchange();
$('#roadAlignment').onchange=()=>$('#roadAudit').style.display=$('#roadAlignment').checked?'':'none';$('#roadAlignment').onchange();
const notes={
 '01-generative-zoning.png':'Generative concept only. Its drawn parcel marks are not counted or linked.',
 '02-measured-zoning.svg':'Authored interpretation of the concept. Connected roads, reserved river corridors and 451 fitted homes.',
 '03-parcels-buildings.svg':'Every visible building is mapped. All 100 pools are explicit, contained backyard polygons.',
 '04-system-bindings.svg':`${geom.properties.length} premises join to saved parcels, buildings, accounts and utility services. Labels show premise IDs.`,
 '05-controlled-map.svg':'Geometry-controlled reference. Crisp at any zoom; architectural finish remains schematic.',
 '06-ai-illustration.png':'Raw AI trial. Attractive detail is not proof of matching footprints or exact feature counts.',
 'hybrid':'Experimental AI underlay with authoritative vector boundaries. Use pool outlines and zoom to inspect drift.'
};
$('#stage').onchange=()=>{const s=$('#stage').value;$('#art').setAttribute('href',s==='hybrid'?'06-ai-illustration-v2.png':s);const selectable=!['01-generative-zoning.png','06-ai-illustration.png'].includes(s);$('#properties').style.display=selectable?'':'none';$('#roads').style.display=selectable?'':'none';$('#boundaries').style.display=selectable&&$('#parcels').checked?'':'none';$('#stageNote').textContent=notes[s];$('#poolMarks').style.display=selectable&&$('#pools').checked?'':'none';$('#labels').style.display=selectable&&$('#roadNames').checked?'':'none';detailLayer()};$('#stage').onchange();
function list(obj){return '<dl>'+Object.entries(obj).map(([k,v])=>`<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')+'</dl>'}
function highlight(q){document.querySelectorAll('.selected').forEach(n=>n.classList.remove('selected'));document.querySelector(q)?.classList.add('selected')}
async function selectProperty(id){const ticket=++selection,p=byId.get(id);highlight(`[data-id="${id}"]`);$('#title').textContent=p.address||`${id} · ${p.buildingType}`;$('#details').innerHTML=list({'Premise':id,'Use':p.buildingType,'Block':p.atlasBlockId,'Parcel':p.parcelId,'Building':p.buildingId,'Account':p.accountId,'Pool':p.hasPool?'Yes · mapped backyard':'No','Solar':'None','Residents':p.occupied?p.occupants:0})+'<p id="history">Checking saved simulation…</p>';$('#inspector').show();try{const response=await fetch(`/atlas/api/premises/${id}/history?limit=1`);if(!response.ok)throw Error('Unavailable');const h=await response.json();if(ticket!==selection)return;$('#history').textContent=`Live record verified · ${h.totalDays} saved days · ${h.readings.length} readings on ${h.days[0]||'no saved date'}.`;$('#details').insertAdjacentHTML('beforeend',`<p><a href="/?premise=${encodeURIComponent(id)}#map">Open simulation record</a></p>`)}catch{if(ticket===selection)$('#history').textContent='Live history unavailable. Geometry remains linked to the baked source snapshot.'}}
function selectRoad(id){selection++;const r=roadById.get(id);highlight(`[data-road="${id}"]`);$('#title').textContent=r.name;$('#details').innerHTML=list({'Road segment':r.id,'Class':r.roadClass,'Length':`${r.lengthM} m`,'Pavement':`${r.pavementWidthM} m`,'Right of way':`${r.rowWidthM} m`,'Graph ends':`${r.a} → ${r.b}`})+'<p>The rendered road and this click target use the same saved centreline and pavement width.</p>';$('#inspector').show()}
$('#inspector .close').onclick=()=>{$('#inspector').close();selection++};
const map=$('#map');let down=null,moved=false;const active=new Map();let pinch=null;
function point(e){return new DOMPoint(e.clientX,e.clientY).matrixTransform(map.getScreenCTM().inverse())}
map.addEventListener('wheel',e=>{e.preventDefault();const p=point(e);zoom(e.deltaY>0?1.14:1/1.14,[(p.x-bounds[0])/bounds[2],(p.y-bounds[1])/bounds[3]])},{passive:false});
map.addEventListener('pointerdown',e=>{active.set(e.pointerId,[e.clientX,e.clientY]);down={x:e.clientX,y:e.clientY,b:[...bounds],target:e.target};moved=false;map.setPointerCapture(e.pointerId);if(active.size===2){const a=[...active.values()];pinch=Math.hypot(a[0][0]-a[1][0],a[0][1]-a[1][1])}});
map.addEventListener('pointermove',e=>{if(!active.has(e.pointerId))return;active.set(e.pointerId,[e.clientX,e.clientY]);if(active.size===2){const a=[...active.values()],d=Math.hypot(a[0][0]-a[1][0],a[0][1]-a[1][1]);if(pinch)zoom(pinch/d);pinch=d;moved=true;return}if(!down)return;const dx=e.clientX-down.x,dy=e.clientY-down.y;if(Math.hypot(dx,dy)>5)moved=true;if(moved){const k=1/map.getScreenCTM().a;frame([down.b[0]-dx*k,down.b[1]-dy*k,down.b[2],down.b[3]])}});
map.addEventListener('pointerup',e=>{active.delete(e.pointerId);if(!moved&&down){const t=down.target;if(t.dataset.id)selectProperty(t.dataset.id);else if(t.dataset.road)selectRoad(t.dataset.road)}down=null;pinch=null});map.addEventListener('pointercancel',()=>{active.clear();down=null;pinch=null});
document.addEventListener('keydown',e=>{if(e.target.matches('select,input'))return;if(e.key==='Escape'){$('#inspector').close();selection++}else if(e.key==='+'||e.key==='=')zoom(.8);else if(e.key==='-')zoom(1.25)});
const initial=new URLSearchParams(location.search);
if([...$('#stage').options].some(o=>o.value===initial.get('stage'))){$('#stage').value=initial.get('stage');$('#stage').onchange()}
if(initial.get('view')==='pilot')frame([420,90,240,160]);
