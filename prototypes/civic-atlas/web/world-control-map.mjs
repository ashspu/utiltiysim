const NS='http://www.w3.org/2000/svg';
export const SOURCE='62bd251fba957150799feed2743b5026da6d4dcac1bdb839231ea0c2be64a4f0';
const MANIFEST='2d0fc16bad61463ab7a2471e46fcb629d68ab0a40cf7534110d0d701070be6c4';
export async function fetchReviewedMap(base,fetcher=fetch){
  const digest=async bytes=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  const get=async(file,expected)=>{const r=await fetcher(base+file,{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw Error('The reviewed map could not be loaded.');const bytes=await r.arrayBuffer();if(await digest(bytes)!==expected)throw Error('Reviewed map asset changed: '+file);return bytes;};
  const proof=JSON.parse(new TextDecoder().decode(await get('manifest.json',MANIFEST)));
  if(proof.sourceRevision!==SOURCE||Object.keys(proof.files).length!==11)throw Error('The reviewed map source was not confirmed.');
  const files=new Map(await Promise.all(Object.entries(proof.files).map(async([file,hash])=>[file,await get(file,hash)])));
  return {scene:JSON.parse(new TextDecoder().decode(files.get('scene.json'))),geometry:JSON.parse(new TextDecoder().decode(files.get('properties.geojson'))),files};
}
export function parcelPaths(features,bindings){
  const ids=new Map(bindings.map(b=>[b.parcelId,b.premiseId]));
  if(ids.size!==bindings.length||features.length!==bindings.length)throw Error('Map properties do not match the saved world.');
  const seen=new Set();
  return features.map(f=>{const id=f.id||f.properties?.id,premiseId=ids.get(id);if(!premiseId||seen.has(id)||f.geometry?.type!=='Polygon')throw Error('Map property identity was not confirmed.');seen.add(id);
    const d=f.geometry.coordinates.map(ring=>{if(ring.length<4||ring.some(p=>p.length!==2||p.some(n=>!Number.isFinite(n))))throw Error('Invalid reviewed parcel geometry.');return ring.map((p,i)=>(i?'L':'M')+p.join(' ')).join(' ')+' Z';}).join(' ');
    return {id,premiseId,d};});
}
export function zoomView(view,factor,point,full){const width=Math.min(full[2],Math.max(full[2]/12,view[2]*factor)),height=width*full[3]/full[2];return boundView([point[0]-(point[0]-view[0])*width/view[2],point[1]-(point[1]-view[1])*height/view[3],width,height],full);}
export function boundView(v,full){return [Math.max(full[0],Math.min(full[0]+full[2]-v[2],v[0])),Math.max(full[1],Math.min(full[1]+full[3]-v[3],v[1])),v[2],v[3]];}
const make=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
const svgNode=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,String(v));return n;};
// Preserve the approved scene compositor: feather contexts, then restore each
// property from its owner panel using the exact global polygon.
export function renderReviewedArtwork(canvas,defs,scene,features,paths,base,images=new Map()){
  const [bx,by,bw,bh]=scene.viewBox;
  canvas.append(svgNode('rect',{x:bx,y:by,width:bw,height:bh,fill:'#6797a5'}));
  const artwork=svgNode('g'),parcelArtwork=svgNode('g');canvas.append(artwork,parcelArtwork);
  const byId=new Map(paths.map(path=>[path.id,path]));
  for(const panel of scene.panels){
    if(!/^panels\/[a-zA-Z0-9-]+\.png$/.test(panel.image))throw Error('Invalid reviewed artwork path.');
    const [x,y,w,h]=panel.contextBounds,[cx,cy,cw,ch]=panel.coreBounds,id='map-fade-'+panel.id;
    for(const [axis,start,size,lo,hi]of [['x',x,w,cx,cx+cw],['y',y,h,cy,cy+ch]]){
      const grad=svgNode('linearGradient',{id:id+axis,x1:0,y1:0,x2:axis==='x'?1:0,y2:axis==='y'?1:0});
      for(const [offset,value]of [[0,lo>start?0:1],[(lo-start)/size,1],[(hi-start)/size,1],[1,hi<start+size?0:1]])grad.append(svgNode('stop',{offset:Math.max(0,Math.min(1,offset)),'stop-color':value?'white':'black'}));
      defs.append(grad);
    }
    const mx=svgNode('mask',{id:id+'mx',maskUnits:'userSpaceOnUse',x,y,width:w,height:h});mx.append(svgNode('rect',{x,y,width:w,height:h,fill:`url(#${id}x)`}));defs.append(mx);
    const mask=svgNode('mask',{id,maskUnits:'userSpaceOnUse',x,y,width:w,height:h});mask.append(svgNode('rect',{x,y,width:w,height:h,fill:`url(#${id}y)`,mask:`url(#${id}mx)`}));defs.append(mask);
    const image=attrs=>svgNode('image',{href:images.get(panel.image)||base+panel.image,x,y,width:w,height:h,preserveAspectRatio:'none',...attrs});artwork.append(image({mask:`url(#${id})`,'data-panel':panel.id}));
    const clip=svgNode('clipPath',{id:'map-owned-'+panel.id,clipPathUnits:'userSpaceOnUse'});
    for(const f of features.filter(f=>String(f.properties?.panelId)===String(panel.id)&&f.properties?.kind!=='unresolved_zoning_area'))clip.append(svgNode('path',{d:byId.get(f.id||f.properties.id).d,'clip-rule':'evenodd'}));
    defs.append(clip);parcelArtwork.append(image({'clip-path':`url(#map-owned-${panel.id})`}));
  }
}
export function createWorldMap(root,request,selectPremise){
  let generation=0,selection=0,world=null,selected=null,imageURLs=[];
  function clear(){generation++;selection++;world=null;selected=null;for(const url of imageURLs)URL.revokeObjectURL(url);imageURLs=[];root.replaceChildren();root.hidden=true;}
  async function load(value){clear();if(!value?.available)return;world=value;const version=generation;root.hidden=false;root.append(make('p','Opening your saved town map…'));
    try{
      if(value.sourceRevision!==SOURCE||value.sourceId!=='lantern-harbour')throw Error('This town has no reviewed interactive map.');
      const base='/presets/lantern-bay-500/explore/';
      const [reviewed,bindings]=await Promise.all([fetchReviewedMap(base),request('map',{id:value.id})]);
      if(version!==generation)return;
      const {scene,geometry,files}=reviewed;
      if(bindings.worldId!==value.id||bindings.sourceRevision!==value.sourceRevision)throw Error('Map belongs to another saved world.');
      const paths=parcelPaths(geometry.features,bindings.premises),full=scene.viewBox;
      if(full?.length!==4||full.some(n=>!Number.isFinite(n))||full[2]<=0||full[3]<=0)throw Error('Invalid reviewed map bounds.');
      const toolbar=make('div');toolbar.className='map-toolbar';const plus=make('button','+'),minus=make('button','−'),reset=make('button','Fit town'),outlines=make('button','Hide property boundaries');plus.setAttribute('aria-label','Zoom in');minus.setAttribute('aria-label','Zoom out');outlines.setAttribute('aria-pressed','true');toolbar.append(plus,minus,reset,outlines);
      const help=make('p','Scroll to zoom, drag to move, and click a property to inspect it. Keyboard: focus a property and press Enter.');help.className='map-help';
      const canvas=svgNode('svg',{viewBox:full.join(' '),role:'group','aria-label':'Explore Lantern Harbour properties',tabindex:'0'});canvas.classList.add('explore-map');
      const defs=svgNode('defs');canvas.append(defs);
      const images=new Map(scene.panels.map(panel=>{const url=URL.createObjectURL(new Blob([files.get(panel.image)],{type:'image/png'}));imageURLs.push(url);return [panel.image,url];}));
      renderReviewedArtwork(canvas,defs,scene,geometry.features,paths,base,images);
      const parcels=svgNode('g');parcels.classList.add('map-parcels');canvas.append(parcels);const notice=make('p',`${paths.length} properties linked to this saved world.`);notice.setAttribute('role','status');
      let view=[...full],drag=null,suppress=false;
      const paint=()=>canvas.setAttribute('viewBox',view.join(' '));
      const point=e=>{const p=canvas.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform(canvas.getScreenCTM().inverse());return[q.x,q.y];};
      const zoom=factor=>{view=zoomView(view,factor,[view[0]+view[2]/2,view[1]+view[3]/2],full);paint();};
      plus.onclick=()=>zoom(.7);minus.onclick=()=>zoom(1/.7);reset.onclick=()=>{view=[...full];paint();};
      outlines.onclick=()=>{const hidden=parcels.classList.toggle('boundaries-hidden');outlines.textContent=hidden?'Show property boundaries':'Hide property boundaries';outlines.setAttribute('aria-pressed',String(!hidden));};
      canvas.addEventListener('wheel',e=>{e.preventDefault();view=zoomView(view,e.deltaY<0?.85:1/.85,point(e),full);paint();},{passive:false});
      canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;drag={x:e.clientX,y:e.clientY,point:point(e),view:[...view],moved:false};suppress=false;});
      canvas.addEventListener('pointermove',e=>{if(!drag)return;if(Math.hypot(e.clientX-drag.x,e.clientY-drag.y)<5&&!drag.moved)return;drag.moved=true;if(!canvas.hasPointerCapture(e.pointerId))canvas.setPointerCapture(e.pointerId);const p=point(e);view=boundView([view[0]+drag.point[0]-p[0],view[1]+drag.point[1]-p[1],view[2],view[3]],full);paint();});
      canvas.addEventListener('pointerup',e=>{suppress=Boolean(drag?.moved);drag=null;if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);});canvas.addEventListener('pointercancel',()=>{drag=null;suppress=true;});
      const choose=async(path,node)=>{if(version!==generation)return;const requestVersion=++selection;if(selected)selected.classList.remove('selected');selected=node;node.classList.add('selected');notice.textContent='Selected property '+path.id+'. Reading its saved premise…';const confirmed=await selectPremise(path.premiseId);if(version!==generation||requestVersion!==selection)return;notice.textContent=confirmed?'Selected property '+path.id+' · '+path.premiseId+'. Details appear below the map.':'Property details could not be confirmed. Select it again to retry.';};
      for(const path of paths){const n=svgNode('path',{d:path.d,'fill-rule':'evenodd',role:'button',tabindex:'0','aria-label':`Inspect property ${path.id}`,'data-parcel-id':path.id,'data-premise-id':path.premiseId});n.append(svgNode('title'));n.firstChild.textContent='Property '+path.id;n.addEventListener('click',()=>{if(!suppress)void choose(path,n);suppress=false;});n.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();void choose(path,n);}});parcels.append(n);}
      const caption=make('figcaption','Lantern Harbour · 300 homes · 436 premises. Reviewed illustrative boundaries; not a cadastral survey.');root.replaceChildren(toolbar,help,canvas,notice,caption);
    }catch(error){if(version===generation)root.replaceChildren(make('p',error.message));}
  }
  clear();return{clear,load};
}
