import test from 'node:test';
import assert from 'node:assert/strict';
import { NewsCommandState,commandPanelsLocked } from './web/world-control-sentiment.mjs';
function storage(){const values=new Map();return{getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};}
test('unknown news outcome locks clock and reload retries exact command in account/world scope',async()=>{
  const store=storage(),state=new NewsCommandState('alice','world-one',store),command={commandId:'original',eventDate:'2026-12-31',trustChange:-20,expectedRevision:2};
  await assert.rejects(state.send(command,async()=>{throw Error('Lost response');}),/Lost/);
  assert.equal(commandPanelsLocked({locked:false},state),true);
  const reload=new NewsCommandState('alice','world-one',store);let sent;
  await reload.send({commandId:'changed'},async value=>{sent=structuredClone(value);return{status:'completed'};});
  assert.deepEqual(sent,command);assert.equal(reload.locked,false);
  assert.equal(commandPanelsLocked({locked:true},reload),true);
  assert.equal(new NewsCommandState('bob','world-one',store).pending,null);
  assert.equal(new NewsCommandState('alice','world-two',store).pending,null);
});
test('concurrent news send suppresses duplication and rejected stale revisions release retained lock',async()=>{
  const state=new NewsCommandState('alice','world',storage());let finish;
  const pending=state.send({commandId:'one'},()=>new Promise(resolve=>{finish=resolve;}));
  await assert.rejects(state.send({commandId:'two'},async()=>{}),/already/);
  finish({status:'completed'});await pending;
  await assert.rejects(state.send({commandId:'stale'},async()=>{const error=Error('Revision changed');error.rejected=true;throw error;}),/Revision/);
  assert.equal(state.locked,false);
});
test('storage failure sends no unrecoverable command',async()=>{
  const state=new NewsCommandState('alice','world',{getItem:()=>null,setItem:()=>{throw Error('No storage');}});let calls=0;
  await assert.rejects(state.send({},async()=>{calls++;}),/No storage/);assert.equal(calls,0);assert.equal(state.locked,false);
});
