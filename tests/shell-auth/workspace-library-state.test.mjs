import test from 'node:test';
import assert from 'node:assert/strict';
import {lifecycleKey,readLifecycle,retainLifecycle,settleLifecycle,dismissRejectedLifecycle,deletionBlocked} from '../../prototypes/civic-atlas/web/workspace-library-state.mjs';
const command={action:'delete',id:'a15e8f33-98b9-4077-a1ca-3254fc662feb',revision:4,commandId:'b15e8f33-98b9-4077-a1ca-3254fc662feb'};
const store=()=>{const map=new Map();return {getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,value),removeItem:key=>map.delete(key)};};
test('lost delete response survives reload and cannot be replaced by restore or another owner',()=>{
  const storage=store();retainLifecycle(storage,'owner',command);
  assert.deepEqual(readLifecycle(storage,'owner'),command);assert.equal(readLifecycle(storage,'other'),null);
  assert.throws(()=>retainLifecycle(storage,'owner',{...command,action:'restore'}),/previous library action/);
  retainLifecycle(storage,'owner',command);
  assert.throws(()=>settleLifecycle(storage,'owner',command,{setup:{id:command.id,status:'setup',revision:5}}),/not been confirmed/);
  assert.deepEqual(readLifecycle(storage,'owner'),command);
  settleLifecycle(storage,'owner',command,{setup:{id:command.id,status:'deleted',revision:5}});
  assert.equal(readLifecycle(storage,'owner'),null);
});
test('invalid journal and unavailable storage refuse a new action before transport',()=>{
  const storage=store();storage.setItem(lifecycleKey('owner'),JSON.stringify({...command,endpoint:'https://untrusted.invalid'}));
  assert.throws(()=>readLifecycle(storage,'owner'),/needs recovery/);
  assert.throws(()=>retainLifecycle({getItem:()=>null,setItem:()=>{throw Error('Storage unavailable');}},'owner',command),/Storage unavailable/);
});
test('unfinished or uncertain creation prevents deleting its setup; completed worlds do not',()=>{
  assert.equal(deletionBlocked(null),false);
  assert.equal(deletionBlocked({payload:{commandId:'retained'}}),true);
  assert.equal(deletionBlocked({pendingWorldId:'a'.repeat(32),payload:{}}),true);
  assert.equal(deletionBlocked({worldId:'a'.repeat(32),payload:{}}),false);
});
test('explicit stale dismissal never clears permission or unknown outcomes',()=>{
  const storage=store();retainLifecycle(storage,'owner',command);
  for(const status of [401,403,404,500,503,undefined])assert.throws(()=>dismissRejectedLifecycle(storage,'owner',command,status),/Recover the original/);
  assert.deepEqual(readLifecycle(storage,'owner'),command);
  assert.throws(()=>dismissRejectedLifecycle(storage,'owner',{...command,revision:3},409),/changed before/);
  dismissRejectedLifecycle(storage,'owner',command,409);assert.equal(readLifecycle(storage,'owner'),null);
});
