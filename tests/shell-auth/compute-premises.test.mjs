import test from 'node:test';
import assert from 'node:assert/strict';
import {createComputeHandler} from '../../api/compute.js';
import {sealCredential} from '../../server/compute-connector.mjs';
import {catalog} from '../../server/setup-drafts.mjs';
const source=catalog.sources[0],id='a'.repeat(32),password='k'.repeat(40);
const world={id,sourceId:source.id,sourceRevision:source.sourceRevision,grantTownId:source.grantTownId};
const page={worldId:id,sourceRevision:world.sourceRevision,total:1,offset:0,premises:[{premiseId:'actual-premise',address:'22 Maple Road',parcelId:'parcel-actual'}]};
async function run(query,{role='analyst',grant={},verified=true,status=world,result=page}={}){
 const calls=[],env={WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'test',WORKOS_COOKIE_PASSWORD:password,WORKOS_REDIRECT_URI:'https://shell.example/api/auth/callback',UTILITYSIM_ROLE_GRANTS:JSON.stringify({actor:[{role,town:world.grantTownId,...grant}]})};
 const handler=createComputeHandler({env,client:()=>({}),authenticate:async()=>({user:{id:'actor',emailVerified:verified}}),store:()=>({get:async()=>({endpoint:'https://runtime.example',secret:sealCredential('s'.repeat(40),password,'actor')})}),call:async input=>{calls.push(input);return {status:200,data:calls.length===1?status:result};}});
 let data;const res={setHeader(){},end:raw=>{data=JSON.parse(raw);}};await handler({method:'GET',url:'/api/compute?'+query,headers:{}},res);return {status:res.statusCode,data,calls};
}
test('owned premise list is bounded, fixed-route and strips physical/private fields',async()=>{
 const result=await run(`action=premises&id=${id}`,{result:{...page,premises:[{...page.premises[0],true_quantity:42,credential:'private'}]}});
 assert.equal(result.status,200);assert.deepEqual(result.data,page);assert.equal(result.calls[1].path,`/hosted/worlds/${id}/premises?offset=0&limit=50`);assert.equal(result.calls[1].actor,'actor');
});
test('actual premise summary uses fixed safe suffix and exact returned identity',async()=>{
 const result=await run(`action=premise&id=${id}&premiseId=actual-premise`,{result:{worldId:id,sourceRevision:world.sourceRevision,premise:{premiseId:'actual-premise',occupied:true,type:'residential',assets:[{truth:42}]}}});
 assert.equal(result.status,200);assert.equal(result.calls[1].path,`/hosted/worlds/${id}/premises/actual-premise/summary`);assert.equal(result.data.premise.occupied,true);assert.equal(result.data.premise.assets,undefined);
});
test('stale grants/source and selected-world substitutions prevent premise reads',async()=>{
 for(const options of [{verified:false},{grant:{revoked:true}},{grant:{town:'foreign'}},{status:{...world,sourceRevision:'0'.repeat(64)}},{status:{...world,id:'b'.repeat(32)}}]){const result=await run(`action=premises&id=${id}`,options);assert.ok([403,409,502].includes(result.status));assert.ok(result.calls.length<=1);}
});
test('duplicate queries, caller paths and traversal never reach premise endpoint',async()=>{
 for(const extra of ['&limit=51','&offset=-1','&id='+id,'&path=/private','&limit=10&limit=20']){const result=await run(`action=premises&id=${id}${extra}`);assert.equal(result.status,422);assert.equal(result.calls.length,1);}
 const result=await run(`action=premise&id=${id}&premiseId=..%2Fprivate`);assert.equal(result.status,422);assert.equal(result.calls.length,1);
});
test('foreign or inconsistent pages and summaries fail closed',async()=>{
 for(const result of [{...page,worldId:'b'.repeat(32)},{...page,sourceRevision:'0'.repeat(64)},{...page,total:2},{...page,offset:50},{...page,premises:[{premiseId:'bad/id'}]}])assert.equal((await run(`action=premises&id=${id}`,{result})).status,502);
 assert.equal((await run(`action=premise&id=${id}&premiseId=actual-premise`,{result:{worldId:id,sourceRevision:world.sourceRevision,premise:{premiseId:'foreign'}}})).status,502);
});
