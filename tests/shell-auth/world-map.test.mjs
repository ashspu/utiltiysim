import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {fileURLToPath}from'node:url';
import {parcelPaths,zoomView,SOURCE,renderReviewedArtwork,fetchReviewedMap}from'../../prototypes/civic-atlas/web/world-control-map.mjs';
import {verifyReviewedMap}from'../../scripts/reviewed_map_assets.mjs';
import {publicMapBindings}from'../../server/map-projection.mjs';
import {createComputeHandler}from'../../api/compute.js';import{sealCredential}from'../../server/compute-connector.mjs';
const id='a'.repeat(32),secret='k'.repeat(40),world={id,available:true,sourceId:'lantern-harbour',sourceRevision:SOURCE,grantTownId:'lantern-bay-500',counts:{premises:1}};
const binding={worldInstanceId:id,sourceRevision:SOURCE,premises:[{parcelId:'parcel-1',premiseId:'physical-1',accountId:'never-expose',meterIds:['hidden']}]};
test('map projection pins owned instance/revision, exact count and unique IDs; strips private bindings',()=>{
 assert.deepEqual(publicMapBindings(binding,world),{worldId:id,sourceRevision:SOURCE,premises:[{parcelId:'parcel-1',premiseId:'physical-1'}]});
 for(const change of [{worldInstanceId:'foreign'},{sourceRevision:'f'.repeat(64)},{premises:[]},{premises:[{parcelId:'unsafe/route',premiseId:'physical-1'}]}])assert.throws(()=>publicMapBindings({...binding,...change},world));
 assert.throws(()=>publicMapBindings({...binding,premises:[...binding.premises,...binding.premises]},{...world,counts:{premises:2}}));
});
test('all 436 approved parcels are exact polygon paths; missing or duplicate saved mapping fails closed',()=>{
 const geometry=JSON.parse(fs.readFileSync(new URL('../../prototypes/civic-atlas/web/presets/lantern-bay-500/explore/properties.geojson',import.meta.url)));
 const bindings=geometry.features.map((f,i)=>({parcelId:f.id,premiseId:'P-'+i}));const paths=parcelPaths(geometry.features,bindings);assert.equal(paths.length,436);assert.ok(paths[0].d.startsWith('M'+geometry.features[0].geometry.coordinates[0][0].join(' ')));assert.ok(paths[0].d.endsWith(' Z'));
 assert.throws(()=>parcelPaths(geometry.features,bindings.slice(1)));assert.throws(()=>parcelPaths(geometry.features,[...bindings.slice(1),bindings[1]]));
});
test('zoom preserves the pointed location and clamps to full-map/max zoom bounds',()=>{const full=[0,0,100,100];assert.deepEqual(zoomView(full,.5,[25,25],full),[12.5,12.5,50,50]);assert.deepEqual(zoomView([20,20,50,50],100,[30,30],full),full);assert.equal(zoomView(full,.001,[50,50],full)[2],100/12);});
test('immutable approved map hashes and feathered owner-polygon composition remain exact',()=>{
 const folder=new URL('../../prototypes/civic-atlas/web/presets/lantern-bay-500/explore/',import.meta.url);assert.equal(verifyReviewedMap(fileURLToPath(folder)).sourceRevision,SOURCE);
 const scene=JSON.parse(fs.readFileSync(new URL('scene.json',folder))),geometry=JSON.parse(fs.readFileSync(new URL('properties.geojson',folder))),paths=parcelPaths(geometry.features,geometry.features.map(f=>({parcelId:f.id,premiseId:f.id})));
 class Node{constructor(tag){this.tag=tag;this.attrs={};this.children=[];}setAttribute(k,v){this.attrs[k]=v;}append(...nodes){this.children.push(...nodes);}}
 const previous=globalThis.document;globalThis.document={createElementNS:(_ns,tag)=>new Node(tag)};
 try{const canvas=new Node('svg'),defs=new Node('defs');renderReviewedArtwork(canvas,defs,scene,geometry.features,paths,'/reviewed/');assert.equal(canvas.children[0].attrs.fill,'#6797a5');assert.equal(canvas.children[1].children.length,9);assert.equal(canvas.children[2].children.length,9);
  for(const panel of scene.panels){const clip=defs.children.find(n=>n.attrs.id==='map-owned-'+panel.id),expected=geometry.features.filter(f=>String(f.properties.panelId)===String(panel.id));assert.deepEqual(clip.children.map(n=>n.attrs.d),expected.map(f=>paths.find(p=>p.id===f.id).d));assert.ok(clip.children.every(n=>n.tag==='path'));assert.equal(defs.children.find(n=>n.attrs.id==='map-fade-'+panel.id).tag,'mask');}
 }finally{globalThis.document=previous;}
});
test('browser verifies manifest, scene, parcels and each original panel before using the artwork',async()=>{
 const folder=new URL('../../prototypes/civic-atlas/web/presets/lantern-bay-500/explore/',import.meta.url),calls=[];
 const run=changed=>fetchReviewedMap('/reviewed/',async(url,options)=>{const file=url.slice('/reviewed/'.length);calls.push(file);assert.equal(options.cache,'no-store');assert.equal(options.credentials,'same-origin');const bytes=fs.readFileSync(new URL(file,folder));return new Response(changed===file?Buffer.concat([bytes,Buffer.from('altered')]):bytes);});
 const result=await run();assert.equal(result.scene.panels.length,9);assert.equal(result.geometry.features.length,436);assert.equal(result.files.size,11);assert.equal(calls.length,12);
 for(const file of ['manifest.json','scene.json','properties.geojson','panels/11-v2.png'])await assert.rejects(run(file),/Reviewed map asset changed/);
});
test('live map action uses trusted user/grants, never calls bindings for foreign owner, and refuses source mismatch',async()=>{
 async function run({signed=true,status=200,revision=SOURCE}={}){let body;const calls=[];const env={WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'test',WORKOS_COOKIE_PASSWORD:secret,WORKOS_REDIRECT_URI:'https://shell.example/api/auth/callback',UTILITYSIM_ROLE_GRANTS:JSON.stringify({alice:[{role:'analyst',town:'lantern-bay-500'}]})};
 const handler=createComputeHandler({env,client:()=>({}),authenticate:async()=>signed?{user:{id:'alice',emailVerified:true}}:null,store:()=>({get:async()=>({endpoint:'https://runtime.example',secret:sealCredential('t'.repeat(40),secret,'alice')})}),call:async input=>{calls.push(input);return input.path.endsWith('/'+id)?{status,data:{...world,sourceRevision:revision}}:{status:200,data:binding};}});const res={setHeader(){},end(v){body=JSON.parse(v);}};await handler({url:'/api/compute?action=map&id='+id,method:'GET',headers:{}},res);return{status:res.statusCode,body,calls};}
 const good=await run();assert.equal(good.status,200);assert.equal(good.calls[1].actor,'alice');assert.equal(good.calls[1].path,`/hosted/worlds/${id}/map/bindings`);assert.ok(!JSON.stringify(good.body).includes('never-expose'));assert.equal((await run({signed:false})).status,401);const foreign=await run({status:404});assert.equal(foreign.status,404);assert.equal(foreign.calls.length,1);assert.equal((await run({revision:'f'.repeat(64)})).status,409);
});
