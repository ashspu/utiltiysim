import test from 'node:test';import assert from 'node:assert/strict';import {randomUUID} from 'node:crypto';
import {OperatorCommandState,canOperate,validateOperatorResponse,canonicalOperatorRequest,operatorRequestHash} from '../../prototypes/civic-atlas/web/vs-operator-core.mjs';
const world='a'.repeat(32);function store(){const data=new Map();return{data,getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};}
const response=body=>({schemaVersion:'connected-operator-response/1',runId:'actual-run',controllerId:'actual-controller',premiseId:body.premiseId,action:body.action,commandId:body.commandId??null,result:body.action==='release-read'?{status:'resolved'}:{status:'queued',id:'actual-job',type:body.action==='invoice'?'invoicing':'billing',cycle_id:'actual-cycle'}});
const create=(storage,request,extra={})=>new OperatorCommandState({actorId:'actor',worldId:world,premiseId:'actual-premise',storage,request,uuid:randomUUID,...extra});
test('browser Unicode UTF8 hash matches settled producer contract and differs from private trusted ASCII hash',async()=>{const request={action:'release-read',premiseId:'P1',commandId:'123e4567-e89b-42d3-a456-426614174000',exceptionId:'E1',note:'Reviewed – café 漢字 😀'};assert.equal(await operatorRequestHash(request),'ca01be6f6314916dc1fd0ca7925d531b5e2b22e91c7f889ca0ba444ec25a92e8');assert.equal(canonicalOperatorRequest(request).includes('😀'),true);assert.equal(await operatorRequestHash(Object.fromEntries(Object.entries(request).reverse())),await operatorRequestHash(request));assert.notEqual(await operatorRequestHash({...request,note:request.note+' '}),await operatorRequestHash(request));assert.equal(canonicalOperatorRequest({...request,note:'\ud800'}).includes('\\ud800'),true);});
test('lost permanent refusal reply replays exact immutable body and only proved nonacceptance releases identity',async()=>{const storage=store(),state=create(storage,async()=>{throw Error('Lost reply');});await assert.rejects(state.execute('release-read',{exceptionId:'actual-exception',note:'Reviewed – café 漢字 😀'}));const original=structuredClone(state.pending);const restored=create(storage,async body=>{assert.deepEqual(body,original);throw Object.assign(Error('Known permanent refusal'),{status:404,rejection:{commandId:body.commandId,requestHash:await operatorRequestHash(body),status:404,disposition:'permanently-rejected'}});});let rejected;try{await restored.retry();}catch(error){rejected=error;}assert.equal(rejected.permanentlyRejected,true);assert.equal(restored.pending,null);assert.equal(create(storage,()=>{}).pending,null);assert.equal(restored.lastReceipt,null);});
test('generic and mismatched permanent claims retain uncertainty, including private ASCII digest substitution',async()=>{for(const change of [error=>delete error.rejection,error=>error.status=401,error=>error.status=409,error=>error.status=503,error=>error.rejection.commandId=randomUUID(),error=>error.rejection.status=404,error=>error.rejection.requestHash='0'.repeat(64),error=>error.rejection.disposition='retryable',error=>error.rejection.extra='private']){const state=create(store(),async body=>{const error=Object.assign(Error('Refusal'),{status:403,rejection:{commandId:body.commandId,requestHash:await operatorRequestHash(body),status:403,disposition:'permanently-rejected'}});change(error);throw error;});await assert.rejects(state.execute('invoice',{cycleId:'actual-cycle',accountId:'actual-account'}));assert.ok(state.pending);}const state=create(store(),async()=>{throw Object.assign(Error('Wrong digest'),{status:404,rejection:{commandId:'123e4567-e89b-42d3-a456-426614174000',requestHash:'af79355b091ae6c9c3e3733bd09c503e20d54a51aab1ee30139535bde59a6d1a',status:404,disposition:'permanently-rejected'}});},{premiseId:'P1',uuid:()=> '123e4567-e89b-42d3-a456-426614174000'});await assert.rejects(state.execute('release-read',{exceptionId:'E1',note:'Reviewed – café 漢字 😀'}));assert.ok(state.pending);});
test('proven refusal removal storage fault retains original request and previous accepted receipt',async()=>{const memory=store(),state=create(memory,async body=>response(body));await state.execute('bill',{cycleId:'actual-cycle',contractId:'actual-contract'});const accepted=structuredClone(state.lastReceipt);memory.removeItem=()=>{throw Error('Storage removal failed');};state.request=async body=>{throw Object.assign(Error('Permanently refused'),{status:403,rejection:{commandId:body.commandId,requestHash:await operatorRequestHash(body),status:403,disposition:'permanently-rejected'}});};await assert.rejects(state.execute('invoice',{cycleId:'actual-cycle',accountId:'actual-account'}),/Storage removal failed/);assert.ok(state.pending);assert.deepEqual(state.lastReceipt,accepted);});
test('lost response and auth rejection preserve exact UUID/action/premise for reload retry',async()=>{
  const storage=store();let sent;
  const initial=create(storage,async body=>{sent=structuredClone(body);throw Error('Response lost');});
  await assert.rejects(initial.execute('bill',{cycleId:'actual-cycle',contractId:'actual-contract'}),/lost/);
  const original=structuredClone(sent);assert.equal(initial.locked,true);
  const reloaded=create(storage,async body=>{sent=structuredClone(body);const error=Error('Authentication expired');error.status=401;throw error;});
  await assert.rejects(reloaded.retry(),/expired/);assert.deepEqual(sent,original);assert.deepEqual(reloaded.pending,original);
  reloaded.request=async body=>{sent=structuredClone(body);return response(body);};const receipt=await reloaded.retry();
  assert.deepEqual(sent,original);assert.equal(reloaded.locked,false);assert.equal(receipt.result.status,'queued');assert.notEqual(receipt.result.status,'invoiced');
});
test('storage accounts/worlds isolate commands and another premise cannot replay or replace one',async()=>{
  const storage=store(),state=create(storage,async()=>{throw Error('Uncertain');});await assert.rejects(state.execute('invoice',{cycleId:'cycle',accountId:'account'}));
  assert.equal(create(storage,async()=>{}, {actorId:'another'}).pending,null);assert.equal(create(storage,async()=>{}, {worldId:'b'.repeat(32)}).pending,null);
  const other=create(storage,async()=>{}, {premiseId:'another-premise'});await assert.rejects(other.retry(),/original premise/);await assert.rejects(other.execute('retry-job',{jobId:'job'}),/retained/);
  assert.equal(other.pending.premiseId,'actual-premise');
});
test('failed storage sends nothing; mismatched receipt cannot clear uncertain command',async()=>{
  let calls=0;const state=create({getItem:()=>null,setItem:()=>{throw Error('Unavailable');}},async()=>{calls++;});await assert.rejects(state.execute('retry-job',{jobId:'actual-job'}),/Unavailable/);assert.equal(calls,0);
  const storage=store(),bad=create(storage,async body=>({...response(body),premiseId:'foreign'}));await assert.rejects(bad.execute('retry-job',{jobId:'actual-job'}),/did not confirm/);assert.ok(bad.pending);
});
test('mutations cannot override immutable body scope and duplicate sends are suppressed',async()=>{
  let finish;const state=create(store(),body=>new Promise(resolve=>{finish=()=>resolve(response(body));}));
  await assert.rejects(state.execute('retry-job',{jobId:'job',premiseId:'foreign'}),/supported fields/);
  const pending=state.execute('release-read',{exceptionId:'actual-exception',note:'Reviewed actual read'});
  await assert.rejects(state.retry(),/already/);finish();await pending;
});
test('current billing.run UI permission is scoped to billing/owner and exact town',()=>{
  const session={authenticated:true,grants:[{role:'billing',town:'town'}]};assert.equal(canOperate(session,'town'),true);assert.equal(canOperate(session,'other'),false);assert.equal(canOperate({...session,grants:[{role:'operator',town:'town'}]},'town'),false);assert.equal(canOperate({...session,authenticated:false},'town'),false);
  assert.throws(()=>validateOperatorResponse({...response({premiseId:'actual-premise',action:'premise'}),commandId:randomUUID()},{premiseId:'actual-premise',action:'premise'}),/did not confirm/);
});
test('accepted receipt write failure retains original command, then reload exact retry durably recovers job before clearing',async()=>{
  const memory=store();let rejectReceipt=true,sent=[];
  const durable={...memory,setItem:(key,value)=>{if(rejectReceipt&&key.includes(':receipt:'))throw Error('Receipt storage failed');memory.setItem(key,value);}};
  const state=create(durable,async body=>{sent.push(structuredClone(body));return response(body);});
  await assert.rejects(state.execute('bill',{cycleId:'actual-cycle',contractId:'actual-contract'}),/Receipt storage failed/);
  const original=structuredClone(state.pending);assert.ok(original);assert.equal(state.locked,true);
  rejectReceipt=false;const restored=create(durable,async body=>{sent.push(structuredClone(body));return response(body);});await restored.retry();
  assert.deepEqual(sent[1],original);assert.equal(restored.pending,null);
  const reopened=create(durable,async()=>{});assert.equal(reopened.lastReceipt.response.result.id,'actual-job');assert.deepEqual(reopened.lastReceipt.request,original);
});
test('accepted job receipts remain premise-scoped after another premise completes without pointer storage',async()=>{
  const memory=store(),durable={...memory,setItem:(key,value)=>{if(key.startsWith('utilitysim:operator-job:'))throw Error('Optional pointer unavailable');memory.setItem(key,value);}};
  const request=async body=>({...response(body),result:{id:body.premiseId==='actual-premise'?'accepted-job-one':'accepted-job-two',type:'billing',status:'queued',cycle_id:'actual-cycle'}});
  const first=create(durable,request);await first.execute('bill',{cycleId:'actual-cycle',contractId:'contract-one'});
  const second=create(durable,request,{premiseId:'second-premise'});await second.execute('bill',{cycleId:'actual-cycle',contractId:'contract-two'});
  const reopenedFirst=create(durable,request),reopenedSecond=create(durable,request,{premiseId:'second-premise'});
  assert.equal(reopenedFirst.lastReceipt.response.result.id,'accepted-job-one');assert.equal(reopenedSecond.lastReceipt.response.result.id,'accepted-job-two');
  assert.notEqual(reopenedFirst.receiptKey,reopenedSecond.receiptKey);assert.equal(reopenedFirst.key,reopenedSecond.key);
  durable.setItem(reopenedFirst.receiptKey,JSON.stringify(reopenedSecond.lastReceipt));assert.throws(()=>create(durable,request),/could not be verified/);
});
