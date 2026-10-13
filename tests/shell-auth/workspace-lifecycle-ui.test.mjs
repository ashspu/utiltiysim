import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {randomUUID} from 'node:crypto';
import {readLifecycle,retainLifecycle,settleLifecycle,dismissRejectedLifecycle,deletionBlocked} from '../../prototypes/civic-atlas/web/workspace-library-state.mjs';
function harness(){
  const source=readFileSync(new URL('../../prototypes/civic-atlas/web/workspace.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/start\(\);\s*$/,'');
  const entries=new Map(),starts=new Map(),requests=[],queue=[],reloads=[],buttons=[];
  const element=()=>{let text='';return{dataset:{},disabled:false,isConnected:false,children:[],innerHTML:'',set textContent(value){text=value;this.children=[];},get textContent(){return text;},append(child){this.children.push(child);}};};
  const storage={getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v),removeItem:k=>entries.delete(k)};
  const setup={id:randomUUID(),revision:4,grantTownId:'town-a',sourceId:'harbour',sourceRevision:'r1',configuration:{world:{}}};
  const ctx={console,crypto:{randomUUID},structuredClone,URL,URLSearchParams,Date,JSON,esc:String,readLifecycle,retainLifecycle,settleLifecycle,dismissRejectedLifecycle,deletionBlocked,
    localStorage:storage,sessionStorage:{getItem:k=>starts.get(k)??null,setItem:(k,v)=>starts.set(k,v)},window:{addEventListener(){}},
    document:{getElementById:element,createElement:element},fetch:async(url,options)=>{requests.push({url,options});const result=await queue.shift();if(result instanceof Error)throw result;return{ok:result.status===200,status:result.status,json:async()=>result.data};},_setup:setup,_reloads:reloads};
  vm.createContext(ctx);vm.runInContext(source+`;root.querySelectorAll=()=>globalThis._buttons;globalThis.actions={runLifecycle,startSetup,ownsSetup};session={user:{id:'owner'},grants:[{role:'owner',town:'town-a'}]};catalog={sources:[{id:'harbour',sourceRevision:'r1',grantTownId:'town-a',canConfigure:true,canSave:true}]};librarySetups.set(_setup.id,_setup);openLibrary=async view=>_reloads.push(view);`,ctx);
  ctx._buttons=buttons;
  const command={action:'delete',id:setup.id,revision:4,commandId:randomUUID()};
  return{ctx,entries,starts,requests,queue,reloads,buttons,setup,command,feedback:element(),element,storage};
}
const accepted=h=>({status:200,data:{setup:{id:h.command.id,revision:5,status:'deleted'}}});
test('unknown result survives reload and exact receipt refreshes current records',async()=>{
  const h=harness();h.queue.push(Error('Response lost'));
  await h.ctx.actions.runLifecycle(h.command,h.feedback,'active');assert.deepEqual(readLifecycle(h.storage,'owner'),h.command);
  assert.equal(h.reloads.length,0);
  const reloaded=harness();reloaded.command=h.command;reloaded.setup.id=h.command.id;for(const[k,v]of h.entries)reloaded.entries.set(k,v);
  reloaded.queue.push(accepted(h));await reloaded.ctx.actions.runLifecycle(readLifecycle(reloaded.storage,'owner'),reloaded.feedback,'trash');
  assert.deepEqual(JSON.parse(reloaded.requests[0].options.body),JSON.parse(h.requests[0].options.body));assert.deepEqual(reloaded.reloads,['trash']);assert.equal(readLifecycle(reloaded.storage,'owner'),null);
});
test('409 retains request until explicit dismissal, then reloads without retrying stale mutation',async()=>{
  const h=harness();h.queue.push({status:409,data:{detail:'This setup changed elsewhere.'}});
  await h.ctx.actions.runLifecycle(h.command,h.feedback,'active');assert.deepEqual(readLifecycle(h.storage,'owner'),h.command);
  const dismiss=h.feedback.children.find(node=>node.textContent==='Dismiss rejected action and reload');assert.ok(dismiss);
  await dismiss.onclick();assert.equal(readLifecycle(h.storage,'owner'),null);assert.deepEqual(h.reloads,['active']);assert.equal(h.requests.length,1);
});
test('in-flight duplicate sends and new simulation starts are blocked',async()=>{
  const h=harness();let finish;h.queue.push(new Promise(resolve=>{finish=resolve;}));const button=h.element();h.buttons.push(button);
  const first=h.ctx.actions.runLifecycle(h.command,h.feedback,'active');assert.equal(button.disabled,true);
  await h.ctx.actions.runLifecycle(h.command,h.feedback,'active');const startFeedback=h.element();await h.ctx.actions.startSetup(h.setup,h.element(),startFeedback,h.element());
  assert.equal(h.requests.length,1);assert.match(startFeedback.textContent,/pending library action/);finish(accepted(h));await first;
});
test('retained delete after reload blocks a new start before transport',async()=>{
  const h=harness();retainLifecycle(h.storage,'owner',h.command);const feedback=h.element();
  await h.ctx.actions.startSetup(h.setup,h.element(),feedback,h.element());assert.equal(h.requests.length,0);assert.match(feedback.textContent,/pending library action/);
});
test('unconfirmed creation, wrong town and failed retention send no delete',async()=>{
  const pending=harness();pending.starts.set(`utilitysim:start:owner:${pending.setup.id}`,JSON.stringify({payload:{commandId:'retained',sourceId:'harbour'}}));await pending.ctx.actions.runLifecycle(pending.command,pending.feedback,'active');assert.equal(pending.requests.length,0);assert.match(pending.feedback.textContent,/Recover the original simulation start/);
  const denied=harness();denied.setup.grantTownId='other';await denied.ctx.actions.runLifecycle(denied.command,denied.feedback,'active');assert.equal(denied.requests.length,0);assert.match(denied.feedback.textContent,/Owner access/);
  const failed=harness();failed.storage.setItem=()=>{throw Error('Storage unavailable');};await failed.ctx.actions.runLifecycle(failed.command,failed.feedback,'active');assert.equal(failed.requests.length,0);assert.match(failed.feedback.textContent,/No library request was sent/);
});
