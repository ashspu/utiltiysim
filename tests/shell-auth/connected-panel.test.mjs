import test from 'node:test';
import assert from 'node:assert/strict';
import {createConnectedPanel} from '../../prototypes/civic-atlas/web/world-control-connected.mjs';
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.attributes={};}
  append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
  setAttribute(name,value){this.attributes[name]=value;}
  set innerHTML(value){throw new Error('Untrusted content must never be inserted as HTML');}
  all(predicate){return[...(predicate(this)?[this]:[]),...this.children.flatMap(child=>child.all(predicate))];}
}
const reported=()=>({supported:true,connected:true,state:'accepted',phase:'recipient-running',physicalThrough:'2026-10-12',recipientThrough:'2026-10-11',recipientClock:'2026-10-11T06:00:00Z',lastCompletedDay:'2026-10-11',revision:3,allowedActions:['pause','resume','advance'],transport:{state:'accepted'},processing:{state:'running'},business:{state:'unknown'}});
function harness(onAction=async()=>{}){
  globalThis.document={createElement:tag=>new Node(tag)};
  const root=new Node('root'),panel=createConnectedPanel(root,onAction);
  const button=label=>root.all(node=>node.tag==='button'&&node.textContent===label)[0];
  const value=label=>{const list=root.all(node=>node.tag==='dl')[0].children,index=list.findIndex(node=>node.tag==='dt'&&node.textContent===label);return list[index+1].textContent;};
  return{root,panel,button,value};
}
test('pause remains requestable during accepted running advance; acceptance never claims quiescence',async()=>{
  const calls=[],h=harness(async action=>{calls.push(action);return{status:'accepted'};});
  h.panel.render(reported());assert.equal(h.button('Pause').disabled,false);
  assert.equal(h.button('Start connected operation').hidden,true);
  await h.button('Pause').onclick();assert.deepEqual(calls,['pause']);
  assert.equal(h.value('Current phase'),'recipient-running');
  assert.equal(h.value('Last physical day committed'),'2026-10-11');
  assert.ok(h.root.all(node=>node.tag==='p').some(node=>node.textContent==='running'));
  assert.ok(h.root.all(node=>node.tag==='p').some(node=>node.textContent==='unknown'));
  h.panel.render({...reported(),phase:'paused',state:'paused'});assert.equal(h.value('Current phase'),'paused');
});
test('read-only refresh remains available while uncertainty and external busy block mutations',async()=>{
  const calls=[],h=harness(async action=>calls.push(action));
  h.panel.render({...reported(),locked:true,pendingCommand:{id:'retained'},allowedActions:['pause','resume','retry']});
  assert.equal(h.button('Pause').disabled,true);assert.equal(h.button('Retry retained command').hidden,false);assert.equal(h.button('Retry retained command').disabled,false);
  assert.equal(h.button('Refresh reported status').disabled,false);
  h.panel.setBusy(true);assert.equal(h.button('Retry retained command').disabled,true);assert.equal(h.button('Refresh reported status').disabled,false);
  await h.button('Refresh reported status').onclick();assert.deepEqual(calls,['refresh']);
});
test('full UTC timestamp preserves within-day barriers and invalid dates never become valid clocks',()=>{
  const h=harness();h.panel.render(reported());assert.equal(h.value('Virtual Systems UTC clock'),'2026-10-11T06:00:00Z');
  h.panel.render({...reported(),recipientClock:'2026-10-11T12:00:00+00:00'});assert.equal(h.value('Virtual Systems UTC clock'),'2026-10-11T12:00:00+00:00');
  h.panel.render({...reported(),physicalThrough:'2026-02-29',recipientClock:'2026-02-29T06:00:00Z'});
  assert.equal(h.value('Next physical UTC day'),'Unavailable');assert.equal(h.value('Virtual Systems UTC clock'),'Unavailable');assert.equal(h.button('Advance connected day').disabled,true);
  h.panel.render({...reported(),recipientClock:'2026-10-11T25:00:00Z'});assert.equal(h.value('Virtual Systems UTC clock'),'Unavailable');assert.equal(h.button('Advance connected day').disabled,true);
});
test('pause and resume require a verified connected revision even when explicitly advertised',()=>{
  const h=harness();
  for(const invalid of [{connected:false},{revision:undefined},{revision:-1},{revision:1.5}]) {
    h.panel.render({...reported(),...invalid});
    assert.equal(h.button('Pause').disabled,true);assert.equal(h.button('Resume').disabled,true);
    assert.equal(h.button('Refresh reported status').disabled,false);
  }
});
test('untrusted reported labels use text; callback errors do not expose payloads or secrets',async()=>{
  const unsafe='<img src=x onerror=alert(1)>',h=harness(async()=>{throw Error('https://private.example/token=secret '+unsafe);});
  h.panel.render({...reported(),phase:unsafe,business:{state:'held',label:unsafe}});
  assert.equal(h.value('Current phase'),unsafe);await h.button('Pause').onclick();
  assert.equal(h.root.all(node=>node.textContent.includes('private.example')).length,0);
  assert.equal(h.root.all(node=>node.textContent.includes('token=secret')).length,0);
  h.panel.clear();assert.equal(h.value('Current phase'),'Unknown');assert.equal(h.value('Virtual Systems UTC clock'),'Unavailable');
});
test('refresh can inspect during a mutation request without duplicating mutations',async()=>{
  let finish;const calls=[],h=harness(action=>{calls.push(action);if(action==='pause')return new Promise(resolve=>{finish=resolve;});return Promise.resolve();});
  h.panel.render(reported());const pending=h.button('Pause').onclick();
  assert.equal(h.button('Pause').disabled,true);assert.equal(h.button('Refresh reported status').disabled,false);
  await h.button('Pause').onclick();await h.button('Refresh reported status').onclick();assert.deepEqual(calls,['pause','refresh']);
  finish();await pending;assert.equal(h.value('Current phase'),'recipient-running');
});
