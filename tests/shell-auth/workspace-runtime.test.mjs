import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { randomUUID } from 'node:crypto';
import { initializationProgress, retainCreationResult } from '../../prototypes/civic-atlas/web/workspace-start-state.mjs';

function harness() {
  const source=readFileSync(new URL('../../prototypes/civic-atlas/web/workspace.js',import.meta.url),'utf8')
    .replace(/^import .*;\r?\n/gm,'').replace(/start\(\);\s*$/,'');
  const storage=new Map(), requests=[], queue=[];
  const element=()=>({textContent:'',innerHTML:'',disabled:false,isConnected:false,append(){}});
  const ctx={console,crypto:{randomUUID},structuredClone,URL,URLSearchParams,Date,JSON,
    esc:String,initializationProgress,retainCreationResult,status:element(),root:element(),window:{addEventListener(){}},
    document:{getElementById:element,createElement:element},
    sessionStorage:{getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)},
    fetch:async(url,options)=>{requests.push({url,options});const response=queue.shift();if(response instanceof Error)throw response;return {ok:response.status===200,status:response.status,json:async()=>response.data};}};
  vm.createContext(ctx);
  vm.runInContext(source+`;globalThis.actions={startSetup,loadWorlds,canStart,readStart,worldLink};session={user:{id:'owner'},grants:[{role:'owner',town:'harbour-grant'}]};catalog={sources:[{id:'harbour',grantTownId:'harbour-grant',canConfigure:true,canSave:true,sourceRevision:'r1'}]};`,ctx);
  const setup={id:'setup-1',revision:1,sourceId:'harbour',sourceRevision:'r1',name:'Original',start:'2026-10-11',configuration:{world:{weather:{winter_mean_c:2}}}};
  return {ctx,storage,requests,queue,setup,element};
}

test('lost creation response and reload replay the original command and immutable payload',async()=>{
  const h=harness(),button=h.element(),feedback=h.element(),runtime=h.element();
  h.queue.push(Error('Response lost'));
  await h.ctx.actions.startSetup(h.setup,button,feedback,runtime);
  assert.equal(button.textContent,'Retry original start');
  const first=JSON.parse(h.requests[0].options.body);
  assert.equal(h.storage.size,1);
  const reloaded=harness();for(const [k,v] of h.storage)reloaded.storage.set(k,v);
  reloaded.setup.name='Edited';reloaded.setup.revision=2;
  reloaded.setup.configuration.world.weather.winter_mean_c=9;
  reloaded.queue.push({status:200,data:{id:'a'.repeat(32),available:true,state:'ready',initialization:{state:'complete',appliedCommands:0,totalCommands:0}}});
  await reloaded.ctx.actions.startSetup(reloaded.setup,button,feedback,runtime);
  assert.deepEqual(JSON.parse(reloaded.requests[0].options.body),first);
  assert.match(feedback.innerHTML,/world-control\.html\?id=aaaaaaaa/);
  assert.doesNotMatch(feedback.innerHTML,/template/);
  await reloaded.ctx.actions.startSetup(reloaded.setup,button,feedback,runtime);
  assert.equal(reloaded.requests.length,1);
});

test('configuring response survives reload and continues exact original payload before ready completion',async()=>{
  const h=harness(),button=h.element(),feedback=h.element(),runtime=h.element();
  const identity='b'.repeat(32);
  h.queue.push({status:200,data:{id:identity,available:false,state:'configuring',initialization:{state:'pending',appliedCommands:25,totalCommands:601}}});
  await h.ctx.actions.startSetup(h.setup,button,feedback,runtime);
  assert.equal(button.textContent,'Continue setup');assert.equal(button.disabled,false);
  assert.match(feedback.textContent,/25 of 601 setup commands committed/);
  assert.doesNotMatch(feedback.innerHTML,/Open simulation/);
  const original=JSON.parse(h.requests[0].options.body),pending=h.ctx.actions.readStart(h.setup);
  assert.equal(pending.worldId,undefined);assert.equal(pending.pendingWorldId,identity);
  const reloaded=harness();for(const [key,value] of h.storage)reloaded.storage.set(key,value);
  reloaded.setup.name='Changed after reload';reloaded.setup.revision=99;
  reloaded.queue.push({status:200,data:{id:identity,available:true,state:'ready',initialization:{state:'complete',appliedCommands:601,totalCommands:601}}});
  await reloaded.ctx.actions.startSetup(reloaded.setup,button,feedback,runtime);
  assert.deepEqual(JSON.parse(reloaded.requests[0].options.body),original);
  assert.match(feedback.innerHTML,/world-control\.html\?id=bbbbbbbb/);
  const completed=reloaded.ctx.actions.readStart(reloaded.setup);
  assert.equal(completed.worldId,identity);assert.equal(completed.pendingWorldId,undefined);
  await reloaded.ctx.actions.startSetup(reloaded.setup,button,feedback,runtime);
  assert.equal(reloaded.requests.length,1);
});

test('unreviewed, stale and non-owner sources cannot start',()=>{
  const h=harness();
  assert.equal(h.ctx.actions.canStart(h.setup),true);
  assert.equal(h.ctx.actions.canStart({...h.setup,sourceId:'ashtown'}),false);
  assert.equal(h.ctx.actions.canStart({...h.setup,sourceRevision:'old'}),false);
  vm.runInContext(`session.grants=[{role:'operator',town:'harbour-grant'}]`,h.ctx);
  assert.equal(h.ctx.actions.canStart(h.setup),false);
});

test('compute503 stays disconnected rather than claiming an empty library',async()=>{
  const h=harness(),container=h.element();container.isConnected=true;
  h.queue.push({status:503,data:{detail:'Configure runtime first.'}});
  await h.ctx.actions.loadWorlds(container);
  assert.match(container.textContent,/disconnected or unavailable/);
  assert.doesNotMatch(container.textContent,/No online simulations/);
  assert.equal(h.ctx.actions.worldLink('../template'),null);
});

test('storage failure prevents sending an unrecoverable creation command',async()=>{
  const h=harness(),button=h.element(),feedback=h.element();
  h.ctx.sessionStorage.setItem=()=>{throw Error('Storage unavailable');};
  await h.ctx.actions.startSetup(h.setup,button,feedback,h.element());
  assert.equal(h.requests.length,0);
  assert.match(feedback.textContent,/Storage unavailable/);
});
