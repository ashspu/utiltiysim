import test from 'node:test';
import assert from 'node:assert/strict';
import { initializationProgress, retainCreationResult } from './web/workspace-start-state.mjs';
const id='a'.repeat(32);
test('pending creation reload retains exact command and only ready result completes',()=>{
  const initial={setupRevision:2,payload:{commandId:'original-command',sourceId:'lantern-harbour',configuration:{schemaVersion:'physical-setup/2',physical:{enabled:true}}}};
  const pending=retainCreationResult(initial,{id,available:false,state:'configuring',initialization:{appliedCommands:25,totalCommands:601}});
  assert.equal(pending.worldId,undefined);assert.equal(pending.pendingWorldId,id);
  assert.equal(initial.pendingWorldId,undefined);
  assert.equal(initializationProgress(pending),'25 of 601 setup commands committed.');
  const reloaded=JSON.parse(JSON.stringify(pending));
  assert.deepEqual(reloaded.payload,initial.payload);
  const continued=retainCreationResult(reloaded,{id,available:false,initialization:{appliedCommands:50,totalCommands:601}});
  assert.deepEqual(continued.payload,initial.payload);
  const ready=retainCreationResult(continued,{id,available:true,initialization:{appliedCommands:601,totalCommands:601}});
  assert.equal(ready.worldId,id);assert.equal(ready.pendingWorldId,undefined);assert.equal(ready.totalCommands,undefined);
  assert.deepEqual(ready.payload,initial.payload);
});
test('legacy progress falls back to committed count and invalid totals never imply progress',()=>{
  assert.equal(initializationProgress({appliedCommands:25}),'25 setup commands committed.');
  assert.equal(initializationProgress({appliedCommands:25,totalCommands:2}),'25 setup commands committed.');
  assert.equal(initializationProgress({appliedCommands:NaN,totalCommands:601}),'');
  assert.equal(initializationProgress({appliedCommands:0,totalCommands:601}),'0 of 601 setup commands committed.');
});
test('an incomplete result or changed identity cannot become a completed start',()=>{
  assert.equal(retainCreationResult({payload:{}},{id}).worldId,undefined);
  assert.throws(()=>retainCreationResult({payload:{},pendingWorldId:id},{id:'b'.repeat(32),available:true}),/different simulation/);
});
