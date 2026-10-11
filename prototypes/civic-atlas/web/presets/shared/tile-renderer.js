// Every tile is drawn in world metres. No tile-local random generation or geometry.
export const assets={};
export async function loadAssets(){await Promise.all(['roofs','civic','trees','ground','church','market','school'].map(async name=>{const im=new Image();im.src=new URL(`assets/${name}.png`,import.meta.url);try{await im.decode();assets[name]=im}catch{if(name!=='trees')throw Error(`Missing ${name} materials`)}}));if(assets.ground){assets.swatches=[];for(let i=0;i<4;i++){const c=document.createElement('canvas');c.width=768;c.height=512;c.getContext('2d').drawImage(assets.ground,(i%2)*768,Math.floor(i/2)*512,768,512,0,0,768,512);assets.swatches.push(c)}}}
const patterns=new WeakMap();
function material(ctx,index){if(!assets.swatches)return null;if(!patterns.has(ctx))patterns.set(ctx,assets.swatches.map((c,i)=>{const p=ctx.createPattern(c,'repeat');p.setTransform(new DOMMatrix().scale((i===2?32:i===3?6:12)/768));return p}));return patterns.get(ctx)[index]}
function texture(ctx,rings,index,alpha){const m=material(ctx,index);if(!m)return;ctx.save();ctx.globalAlpha=alpha;fill(ctx,rings,m);ctx.restore()}
export function hash(s){let n=2166136261;for(const c of String(s)){n^=c.charCodeAt(0);n=Math.imul(n,16777619)}return n>>>0}
export function path(ctx,rings){ctx.beginPath();for(const r of rings){if(!r.length)continue;ctx.moveTo(...r[0]);for(let i=1;i<r.length;i++)ctx.lineTo(...r[i]);ctx.closePath()}}
function fill(ctx,rings,color){path(ctx,rings);ctx.fillStyle=color;ctx.fill('evenodd')}
function line(ctx,pts,width,color){if(!pts.length)return;ctx.beginPath();ctx.moveTo(...pts[0]);for(const p of pts.slice(1))ctx.lineTo(...p);ctx.lineWidth=width;ctx.strokeStyle=color;ctx.stroke()}
function tree(ctx,x,y,r,key,detail){ctx.fillStyle='#24382435';ctx.beginPath();ctx.ellipse(x+r*.26,y+r*.36,r*.98,r*.8,0,0,Math.PI*2);ctx.fill();if(assets.trees&&detail>.3){let i=key%12;ctx.drawImage(assets.trees,(i%4)*384,Math.floor(i/4)*341,384,341,x-r,y-r,r*2,r*2)}else{ctx.fillStyle=['#567545','#647f4a','#789158','#486c43','#84985c'][key%5];ctx.beginPath();ctx.arc(x,y,r,0,Math.PI*2);ctx.fill()}}
const roofCrops=Array.from({length:12},(_,i)=>[i%4*384+40,Math.floor(i/4)*341+42,315,244]);
const civicCrops={church:[35,45,485,410],market_hall:[545,45,478,403],school:[1060,72,433,377],industrial:[42,505,551,455],commercial:[642,552,333,399],pump_station:[1010,505,511,464]};
function roof(ctx,f,ppu){
 const p=f.record,q=f.roof;if(q.length<4)return;const n=hash(p.uid||p.id),res=p.premiseType==='residential';
 const specific={church:'church',market_hall:'market',school:'school'}[p.buildingType];
 ctx.save();path(ctx,f.rings);ctx.clip('evenodd');
 if(!specific){ctx.save();ctx.translate(1.3,1.9);fill(ctx,[q],'#18282560');ctx.restore();fill(ctx,[q],'#65665f')}
 if(ppu>.18){
  const a=q[0],b=q[1],d=q[q.length===5?3:q.length-1];ctx.save();path(ctx,[q]);ctx.clip();
  ctx.transform(b[0]-a[0],b[1]-a[1],d[0]-a[0],d[1]-a[1],a[0],a[1]);
  const crop=res?roofCrops[n%12]:(civicCrops[p.buildingType]||civicCrops[p.premiseType]||civicCrops.commercial);
  if(specific)ctx.drawImage(assets[specific],0,0,1,1);else ctx.drawImage(res?assets.roofs:assets.civic,...crop,0,0,1,1);
  ctx.restore();
 }
 if(!specific){path(ctx,[q]);ctx.strokeStyle='#333d32';ctx.lineWidth=.16;ctx.stroke()}
 ctx.restore();
}
function garden(ctx,f,ppu){const p=f.record,n=hash(p.uid||p.id),res=p.premiseType==='residential';fill(ctx,f.rings,res?['#a3b57c','#98ae75','#a7b980','#8fa775','#a6b780','#99af75'][n%6]:p.premiseType==='industrial'?'#b3b0a3':'#c3b8a3');if(ppu<.45)return;texture(ctx,f.rings,res?0:3,res?.48:.24);ctx.save();path(ctx,f.rings);ctx.clip('evenodd');const [a,b,c,d]=f.bbox;if(res){ctx.lineWidth=1.8;ctx.strokeStyle='#bed09a35';for(let y=Math.floor(b/5)*5;y<d;y+=5)line(ctx,[[a,y],[c,y]],1.8,'#bfd19a28');path(ctx,f.rings);ctx.lineWidth=.4;ctx.strokeStyle='#5e744d99';ctx.stroke()}else{for(let x=a+5;x<c-4;x+=4){line(ctx,[[x,b+3],[x,b+8]],.14,'#f4e5c6');if(hash(`${x}${n}`)%3===0){ctx.fillStyle=['#e3dfd2','#617681','#526166','#baa494'][Math.floor(x)%4];ctx.fillRect(x+.7,b+4,1.7,3.2)}}if(p.buildingType==='school'){ctx.fillStyle='#789584';ctx.fillRect(a+8,d-26,28,16);ctx.strokeStyle='#e7e4c7';ctx.lineWidth=.2;ctx.strokeRect(a+8,d-26,28,16);line(ctx,[[a+22,d-26],[a+22,d-10]],.2,'#e7e4c7')}}

if(p.poolPolygon){const pts=p.poolPolygon.map(q=>[q.x,q.z]);path(ctx,[pts]);ctx.strokeStyle='#e4d8b7';ctx.lineWidth=1.7;ctx.stroke();fill(ctx,[pts],'#499dab');line(ctx,[pts[0],pts[1]],.3,'#c3f1ef');if(ppu>2){ctx.save();path(ctx,[pts]);ctx.clip();for(let y=b;y<d;y+=1.5)line(ctx,[[a,y],[c,y]],.1,'#a7dddd70');ctx.restore()}}
ctx.restore()}
function yardTrees(ctx,f,ppu){
 if(ppu<.4)return;
 const p=f.record,n=hash(p.uid||p.id),[a,b,c,d]=f.bbox;
 const obstacles=[f.roof,...(p.poolPolygon?[p.poolPolygon.map(q=>[q.x,q.z])]:[]),...f.drive.map(rings=>rings[0])];
 ctx.save();path(ctx,f.rings);ctx.clip('evenodd');
 for(let i=0;i<2+(n%2);i++){
  const h=hash(`${p.uid}:${i}`),x=a+2+(h%997)/997*(c-a-4),y=b+2+((h>>>10)%997)/997*(d-b-4),radius=2.5+(h%12)/10;
  if(!hitProperty(f,x,y))continue;
  if(obstacles.some(ring=>hitProperty({rings:[ring]},x,y)||roadDistance({points:[...ring,ring[0]]},x,y)<radius+1))continue;
  tree(ctx,x,y,radius,h,ppu);
 }
 ctx.restore();
}
export function drawFeatures(ctx,features,{ppu=1,boundaries=false,roads=false,pools=false,names=false,stage='art',view=null}={}){
 ctx.lineJoin='round';ctx.lineCap='round';
 const land=features.filter(f=>f.type==='land');
 for(const f of land){const colors={water:'#7ca9af',environmental:'#769262',parks:'#9caf78',agricultural:'#c1b57e'};fill(ctx,f.rings,colors[f.kind]||'#a6b67f');if(ppu>.3&&f.kind!=='water')texture(ctx,f.rings,f.kind==='agricultural'?2:0,f.kind==='agricultural'?.48:.3);if(f.kind==='agricultural'&&ppu>.3){ctx.save();path(ctx,f.rings);ctx.clip('evenodd');const [a,b,c,d]=f.bbox;for(let x=Math.floor(a/7)*7;x<c;x+=7)line(ctx,[[x,b],[x,d]],.65,'#95875035');ctx.restore()}}
 const rr=features.filter(f=>f.type==='road');
 for(const r of rr)line(ctx,r.points,r.rowWidthM,'#8e9f70');
 for(const r of rr)line(ctx,r.points,r.pavementWidthM+2,'#ccc9b4');
 for(const r of rr)line(ctx,r.points,r.pavementWidthM,'#929892');
 if(ppu>.45)for(const r of rr){line(ctx,r.points,Math.max(.15,r.pavementWidthM-.65),'#a1a39a');ctx.save();ctx.globalAlpha=.34;line(ctx,r.points,Math.max(.15,r.pavementWidthM-.65),material(ctx,1)||'#969991');ctx.restore();if(r.roadClass!=='local'){ctx.setLineDash([3,5]);line(ctx,r.points,.16,'#e8d1a0');ctx.setLineDash([])}}
 const props=features.filter(f=>f.type==='property');
 for(const f of props)garden(ctx,f,ppu);
 for(const f of props)for(const dr of f.drive)fill(ctx,dr,'#c9c5b5');
 if(stage==='art'){for(const f of props)roof(ctx,f,ppu);for(const f of props)yardTrees(ctx,f,ppu)}
 else for(const f of props)fill(ctx,[f.roof],f.record.premiseType==='residential'?'#685f54':'#94616f');
 for(const f of land)if(['environmental','parks'].includes(f.kind)&&stage==='art'){
  ctx.save();path(ctx,f.rings);ctx.clip('evenodd');let [a,b,c,d]=f.bbox;const step=f.kind==='parks'?31:11;if(view){a=Math.max(a,view[0]-step);b=Math.max(b,view[1]-step);c=Math.min(c,view[0]+view[2]+step);d=Math.min(d,view[1]+view[3]+step)}
  for(let xx=Math.floor((a-step)/step)*step;xx<c+step;xx+=step)for(let yy=Math.floor((b-step)/step)*step;yy<d+step;yy+=step){const h=hash(`${xx},${yy}`),x=xx+(h%997)/997*step,y=yy+((h>>>10)%997)/997*step;if(f.kind==='parks'&&h%7<3)continue;tree(ctx,x,y,f.kind==='parks'?3.5+(h%25)/10:5+(h%30)/10,h,ppu)}ctx.restore()
 }
 for(const f of features)if(f.type==='publicGreen'){const [a,b,c,d]=f.designBounds||f.bbox,x=(a+c)/2,y=(b+d)/2,rx=(c-a)*.38,ry=(d-b)*.38;ctx.save();path(ctx,f.rings);ctx.clip('evenodd');ctx.beginPath();ctx.ellipse(x,y,rx,ry,0,0,Math.PI*2);ctx.strokeStyle='#d1c3a4';ctx.lineWidth=4;ctx.stroke();line(ctx,[[a,y],[c,y]],5,'#d1c3a4');line(ctx,[[x,b],[x,d]],4,'#d1c3a4');ctx.beginPath();ctx.arc(x,y,12,0,Math.PI*2);ctx.fillStyle=material(ctx,3)||'#d1c3a4';ctx.fill();ctx.beginPath();ctx.arc(x,y,5,0,Math.PI*2);ctx.fillStyle='#81a9a7';ctx.fill();ctx.strokeStyle='#e2d7bb';ctx.lineWidth=1;ctx.stroke();ctx.restore()}
 if(ppu>.5)for(const f of features)if(f.type==='equipment'){const x=f.x,y=f.z;if(f.kind==='pole'){line(ctx,[[x,y],[x+3,y+5]],.5,'#28342660');line(ctx,[[x,y],[x,y-3]],.65,'#755c3e');line(ctx,[[x-1.2,y-2.5],[x+1.2,y-2.5]],.4,'#635239')}else{line(ctx,[[x,y],[x,y-1.2]],.7,'#a84631');line(ctx,[[x-.6,y-.7],[x+.6,y-.7]],.55,'#c3563c')}}
 if(boundaries||stage!=='art')for(const f of props){path(ctx,f.rings);ctx.lineWidth=Math.max(.18,.6/ppu);ctx.strokeStyle='#39503285';ctx.stroke()}
 if(roads)for(const r of rr)line(ctx,r.points,r.pavementWidthM,'#eab24785');
 if(pools)for(const f of props)if(f.record.poolPolygon){path(ctx,[f.record.poolPolygon.map(p=>[p.x,p.z])]);ctx.strokeStyle='#00efff';ctx.lineWidth=1;ctx.stroke()}
 if(names&&ppu>.35){ctx.font=`${Math.max(4,11/ppu)}px system-ui`;ctx.textAlign='center';ctx.textBaseline='middle';for(const r of rr){if(r.lengthM<80)continue;const p=r.points[Math.floor(r.points.length/2)];ctx.lineWidth=2/ppu;ctx.strokeStyle='#f5f0d8';ctx.strokeText(r.name,...p);ctx.fillStyle='#304438';ctx.fillText(r.name,...p)}}
}
export function hitProperty(f,x,y){let inside=false;for(const ring of f.rings){let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if(((a[1]>y)!==(b[1]>y))&&x<(b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0])yes=!yes}if(yes)inside=!inside}return inside}
export function roadDistance(f,x,y){let best=Infinity;for(let i=1;i<f.points.length;i++){const a=f.points[i-1],b=f.points[i],dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(y-a[1])*dy)/(dx*dx+dy*dy||1)));best=Math.min(best,Math.hypot(x-a[0]-t*dx,y-a[1]-t*dy))}return best}
