import test from 'node:test';import assert from 'node:assert/strict';import {randomUUID} from 'node:crypto';
import {OperatorCommandState,canOperate,validateOperatorResponse} from '../../prototypes/civic-atlas/web/vs-operator-core.mjs';
const world='a'.repeat(32);function store(){const data=new Map();return{data,getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};}
const response=body=>({schemaVersion:'connected-operator-response/1',runId:'actual-run',controllerId:'actual-controller',premiseId:body.premiseId,action:body.action,commandId:body.commandId??null,result:body.action==='release-read'?{status:'resolved'}:{status:'queued',id:'actual-job',type:body.action==='invoice'?'invoicing':'billing',cycle_id:'actual-cycle'}});
const create=(storage,request,extra={})=>new OperatorCommandState({actorId:'actor',worldId:world,premiseId:'actual-premise',storage,request,uuid:randomUUID,...extra});
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
