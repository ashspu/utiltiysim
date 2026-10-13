import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const id='a'.repeat(32),revision='1'.repeat(64),world={id,available:true,name:'Owned city',sourceRevision:revision,through:'2026-10-13',days:0,connectedClock:{configured:true}};
const geometry={premises:[{id:'first',address:'First'},{id:'second',address:'Second'}]};
class Node{constructor(){this.children=[];this.dataset={};this.checked=false;this.hidden=false;this.value='';}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}setAttribute(k,v){this[k]=v;}removeAttribute(k){delete this[k];}}
function harness(){
 const nodes=new Map(),scenes=[],queue=[];
 class Scene{constructor(){this.ready=Promise.resolve(true);scenes.push(this);}load(value,options){this.geometry=value;assert.equal(options.demo,false);}destroy(){this.destroyed=true;}setLayers(){}select(){}home(){}zoom(){}rotate(){}}
 const context=vm.createContext({URL,URLSearchParams,location:{href:'https://shell.example/city.html?id='+id},history:{replaceState(){}},window:{addEventListener(){}},document:{getElementById(key){if(!nodes.has(key))nodes.set(key,new Node());return nodes.get(key);},createElement(){return new Node();}},IsoScene:Scene,TownScene:Scene,inspectSnapshot(){},fetch:async()=>{const value=queue.shift();if(!value)throw Error('Unexpected request');const result=await value;return{ok:result.status===200,json:async()=>result.data};}});
 queue.push({status:200,data:world},{status:200,data:{worldId:id,sourceRevision:revision,geometry}});
 const source=fs.readFileSync(new URL('../../prototypes/civic-atlas/web/city.js',import.meta.url),'utf8').replace(/^import.*\r?\n/gm,'').replace('void load();','globalThis.ready=load();');
 vm.runInContext(source+'\nglobalThis.app={load,inspect};',context);
 return {context,nodes,scenes,queue};
}
test('optional city rejects stale premise responses and clears every old record on failed refresh',async()=>{
 const h=harness();await h.context.ready;assert.equal(h.nodes.get('refresh').disabled,false);
 let release;h.queue.push(new Promise(resolve=>{release=resolve;}));const older=h.context.app.inspect('first',false);
 h.queue.push({status:200,data:{worldId:id,sourceRevision:revision,premise:{premiseId:'second'}}});await h.context.app.inspect('second',false);
 assert.equal(h.nodes.get('vs').hidden,false);assert.match(h.nodes.get('vs').href,/premiseId=second$/);
 h.queue.push({status:403,data:{detail:'Current world access revoked.'}});await h.context.app.load();
 assert.equal(h.scenes[0].destroyed,true);assert.equal(h.nodes.get('vs').hidden,true);assert.equal(h.nodes.get('vs').href,undefined);assert.equal(h.nodes.get('details').children.length,0);assert.equal(h.nodes.get('premise').children.length,0);assert.equal(h.nodes.get('refresh').disabled,false);assert.equal(h.nodes.get('inspect').disabled,true);
 release({status:200,data:{worldId:id,sourceRevision:revision,premise:{premiseId:'first'}}});await older;assert.equal(h.nodes.get('vs').hidden,true);assert.equal(h.nodes.get('details').children.length,0);assert.equal(h.nodes.get('status').textContent,'Current world access revoked.');
});
