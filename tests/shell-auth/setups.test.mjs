import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { createSetupsHandler } from '../../api/setups.js';
import { catalog, validateSetup, draftStore, saveScript } from '../../server/setup-drafts.mjs';
const env={WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'test',WORKOS_COOKIE_PASSWORD:'x'.repeat(40),WORKOS_REDIRECT_URI:'https://example.com/api/auth/callback',UTILITYSIM_ROLE_GRANTS:JSON.stringify({u:[{role:'owner',town:'lantern-bay-500'}]})};
const input=()=>({id:randomUUID(),commandId:randomUUID(),revision:0,name:'Isolated test setup',start:'2026-10-11',sourceId:catalog.sources[0].id,sourceRevision:catalog.sources[0].sourceRevision,snapshotSha256:catalog.sources[0].snapshotSha256,configuration:structuredClone(catalog.configuration.defaults)});
function harness({authenticated=true,verified=true,grants,storageFailure=false}={}){
  const calls=[];
  const handler=createSetupsHandler({env:grants?{...env,UTILITYSIM_ROLE_GRANTS:JSON.stringify({u:grants})}:env,client:()=>({userManagement:{loadSealedSession:()=>({authenticate:async()=>({authenticated,user:{id:'u',emailVerified:verified}}),refresh:async()=>({authenticated:false})})}}),store:()=>({list:async actor=>{calls.push(['list',actor]);if(storageFailure)throw Error('private upstream details');return [{...validateSetup(input()),status:'setup',requestHash:'private',commandId:'private'}];},save:async(actor,value)=>{calls.push(['save',actor,value]);return {...value,revision:1,status:'setup'};}})});
  return {calls,async request({method='GET',body,url='/api/setups',origin='https://example.com'}={}){let data;const headers={};const res={setHeader:(k,v)=>headers[k]=v,getHeader:k=>headers[k],end:value=>data=JSON.parse(value)};await handler({method,body,url,headers:{origin,cookie:'utilitysim-session=test'}},res);return {status:res.statusCode,data,headers};}};
}
test('setup API rejects signed-out, unverified and wrong-town writes before storage',async()=>{
  for(const options of [{authenticated:false},{verified:false},{grants:[{role:'owner',town:'other'}]},{grants:[{role:'analyst',town:'lantern-bay-500'}]}]){
    const h=harness(options);const r=await h.request({method:'POST',body:input()});assert.ok([401,403].includes(r.status));assert.equal(h.calls.length,0);
  }
  const h=harness();assert.equal((await h.request({method:'POST',origin:'https://attacker.invalid',body:input()})).status,403);assert.equal(h.calls.length,0);
});
test('catalog is grant filtered; saved setup records are owner scoped and exclude internal retry data',async()=>{
  const h=harness();const c=await h.request({url:'/api/setups?view=catalog'});assert.equal(c.status,200);assert.equal(c.data.sources.length,1);assert.equal(c.data.sources[0].id,'lantern-harbour');assert.equal(h.calls.length,0);
  const r=await h.request();assert.deepEqual(h.calls,[['list','u']]);assert.equal(r.data.setups[0].status,'setup');assert.equal(r.data.setups[0].commandId,undefined);assert.equal(r.data.setups[0].requestHash,undefined);assert.match(r.headers['Cache-Control'],/no-store/);
});
test('only accepted pinned physical setup is saved, with server-derived world and grant identities',async()=>{
  const h=harness(),body=input();const r=await h.request({method:'POST',body});assert.equal(r.status,200);assert.equal(h.calls[0][1],'u');assert.equal(r.data.setup.townId,'town-47ecb8e861787476');assert.equal(r.data.setup.grantTownId,'lantern-bay-500');assert.equal(r.data.setup.revision,1);
  for(const mutate of [x=>x.sourceRevision='old',x=>x.sourceId='ashtown',x=>x.ownerId='other',x=>x.configuration.run={billing:{}},x=>x.configuration.world.weather.extra=1,x=>x.configuration.world.meters.annual_meter_failure=2,x=>x.configuration.world.weather.winter_mean_c='3',x=>x.start='2026-02-30',x=>delete x.configuration.world.meters,x=>x.name=' ']){
    const bad=input();mutate(bad);assert.throws(()=>validateSetup(bad));
  }
});
test('storage failures return a recoverable error, never an empty saved library or upstream secrets',async()=>{
  const h=harness({storageFailure:true});const r=await h.request();assert.equal(r.status,503);assert.equal(r.data.setups,undefined);assert.doesNotMatch(JSON.stringify(r.data),/private upstream/);
});
test('store isolates owner keys, sends expected revision atomically, and maps stale writes to conflict',async()=>{
  const calls=[];const redis={hvals:async key=>{calls.push(key);return [];},eval:async(script,keys,args)=>{assert.equal(script,saveScript);calls.push({keys,args});return args[2];}};
  const store=draftStore({},redis);await store.list('owner-a');await store.list('owner-b');assert.notEqual(calls[0],calls[1]);assert.match(calls[0],/^utilitysim:setup:v1:[0-9a-f]{64}$/);
  const value=validateSetup(input());const record=await store.save('owner-a',value);assert.equal(record.revision,1);assert.equal(calls[2].args[1],0);assert.equal(calls[2].keys[0],calls[0]);assert.equal(record.status,'setup');assert.equal(record.configuration.world.weather.winter_mean_c,value.configuration.world.weather.winter_mean_c);
  const conflict=draftStore({}, {...redis,eval:async()=>{throw Error('SETUP_REVISION_CONFLICT');}});await assert.rejects(conflict.save('owner-a',value),e=>e.status===409);
});
