const NS='http://www.w3.org/2000/svg';
export const SOURCE='62bd251fba957150799feed2743b5026da6d4dcac1bdb839231ea0c2be64a4f0';
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
export function createWorldMap(root,request,selectPremise){
  let generation=0,world=null,selected=null;
  function clear(){generation++;world=null;selected=null;root.replaceChildren();root.hidden=true;}
  async function load(value){clear();if(!value?.available)return;world=value;const version=generation;root.hidden=false;root.append(make('p','Opening your saved town map…'));
    try{
      if(value.sourceRevision!==SOURCE||value.sourceId!=='lantern-harbour')throw Error('This town has no reviewed interactive map.');
      const base='/presets/lantern-bay-500/explore/';
      const get=async file=>{const r=await fetch(base+file,{cache:'no-store',credentials:'same-origin'});if(!r.ok)throw Error('The reviewed map could not be loaded.');return r.json();};
      const [scene,geometry,bindings]=await Promise.all([get('scene.json'),get('properties.geojson'),request('map',{id:value.id})]);
      if(version!==generation)return;
      if(bindings.worldId!==value.id||bindings.sourceRevision!==value.sourceRevision)throw Error('Map belongs to another saved world.');
      const paths=parcelPaths(geometry.features,bindings.premises),full=scene.viewBox;
      if(full?.length!==4||full.some(n=>!Number.isFinite(n))||full[2]<=0||full[3]<=0)throw Error('Invalid reviewed map bounds.');
      const toolbar=make('div');toolbar.className='map-toolbar';const plus=make('button','+'),minus=make('button','−'),reset=make('button','Fit town'),outlines=make('button','Hide property boundaries');plus.setAttribute('aria-label','Zoom in');minus.setAttribute('aria-label','Zoom out');outlines.setAttribute('aria-pressed','true');toolbar.append(plus,minus,reset,outlines);
      const help=make('p','Scroll to zoom, drag to move, and click a property to inspect it. Keyboard: focus a property and press Enter.');help.className='map-help';
      const canvas=svgNode('svg',{viewBox:full.join(' '),role:'group','aria-label':'Explore Lantern Harbour properties',tabindex:'0'});canvas.classList.add('explore-map');
      const defs=svgNode('defs');canvas.append(defs);
      for(const panel of scene.panels){if(!/^panels\/[a-zA-Z0-9-]+\.png$/.test(panel.image))throw Error('Invalid reviewed artwork path.');const clip=svgNode('clipPath',{id:'map-core-'+panel.id});const[cx,cy,cw,ch]=panel.coreBounds;clip.append(svgNode('rect',{x:cx,y:cy,width:cw,height:ch}));defs.append(clip);const[x,y,w,h]=panel.contextBounds;canvas.append(svgNode('image',{href:base+panel.image,x,y,width:w,height:h,preserveAspectRatio:'none','clip-path':`url(#map-core-${panel.id})`}));}
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
      const choose=async(path,node)=>{if(version!==generation)return;if(selected)selected.classList.remove('selected');selected=node;node.classList.add('selected');notice.textContent='Selected property '+path.id+'. Reading its saved premise…';await selectPremise(path.premiseId);if(version===generation)notice.textContent='Selected property '+path.id+' · '+path.premiseId+'. Details appear below the map.';};
      for(const path of paths){const n=svgNode('path',{d:path.d,'fill-rule':'evenodd',role:'button',tabindex:'0','aria-label':`Inspect property ${path.id}`,'data-parcel-id':path.id,'data-premise-id':path.premiseId});n.append(svgNode('title'));n.firstChild.textContent='Property '+path.id;n.addEventListener('click',()=>{if(!suppress)void choose(path,n);suppress=false;});n.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();void choose(path,n);}});parcels.append(n);}
      const caption=make('figcaption','Lantern Harbour · 300 homes · 436 premises. Reviewed illustrative boundaries; not a cadastral survey.');root.replaceChildren(toolbar,help,canvas,notice,caption);
    }catch(error){if(version===generation)root.replaceChildren(make('p',error.message));}
  }
  clear();return{clear,load};
}
