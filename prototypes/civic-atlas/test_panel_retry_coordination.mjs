import test from 'node:test';
import assert from 'node:assert/strict';
import { createStormPanel } from './web/world-control-events.mjs';
import { createSentimentPanel,coordinateCommandPanels,commandPanelsLocked } from './web/world-control-sentiment.mjs';
// Component test doubles; no browser or production UI is automated here.
class Node {
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.value='';this.textContent='';}
  append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=[...nodes];}
  setAttribute(){} querySelectorAll(){return [];} focus(){}
  find(predicate){if(predicate(this))return this;for(const child of this.children){const found=child.find?.(predicate);if(found)return found;}}
}
test('two retained commands after reload permit one exact retry at a time while new commands and clock stay blocked',async()=>{
  const previousDocument=globalThis.document,previousStorage=globalThis.sessionStorage;
  globalThis.document={createElement:tag=>new Node(tag)};
  const retained=new Map();globalThis.sessionStorage={getItem:key=>retained.get(key)||null,setItem:(key,value)=>retained.set(key,value),removeItem:key=>retained.delete(key)};
  const stormCommand={commandId:'storm-original',action:'schedule'},newsCommand={commandId:'news-original',action:'schedule'};
  retained.set('utilitysim-storm-command:world',JSON.stringify(stormCommand));
  retained.set('utilitysim:news:account:world',JSON.stringify(newsCommand));
  let storm,news,resolveSend;const sent=[];
  const changed=()=>{if(storm&&news)coordinateCommandPanels(storm,news);};
  const request=async(action,params,body)=>{
    if(body){sent.push({action,body:structuredClone(body)});return new Promise(resolve=>{resolveSend=resolve;});}
    if(action==='events')return{events:[]};
    return{worldInstanceId:'world',enabled:true,through:'2026-01-01',revision:2,events:[],news:[],history:[]};
  };
  try{
    const stormRoot=new Node('div'),newsRoot=new Node('div');
    storm=createStormPanel(stormRoot,request,changed);news=createSentimentPanel(newsRoot,request,changed,Promise.resolve('account'));
    await storm.load({id:'world'});await news.load({id:'world'});changed();
    const stormRetry=stormRoot.find(node=>node.textContent==='Retry retained command'),newsRetry=newsRoot.find(node=>node.textContent==='Retry retained news command');
    assert.equal(stormRetry.disabled,false);assert.equal(newsRetry.disabled,false);assert.equal(commandPanelsLocked(storm,news),true);
    assert.equal(stormRoot.find(node=>node.tag==='fieldset').disabled,true);assert.equal(newsRoot.find(node=>node.tag==='fieldset').disabled,true);
    const first=stormRetry.onclick();assert.equal(newsRetry.disabled,true);assert.deepEqual(sent,[{action:'storms',body:stormCommand}]);
    await newsRetry.onclick();assert.equal(sent.length,1);
    resolveSend({revision:3});await first;assert.equal(newsRetry.disabled,false);assert.equal(commandPanelsLocked(storm,news),true);
    const second=newsRetry.onclick();assert.equal(stormRetry.disabled,true);assert.deepEqual(sent[1],{action:'sentiment',body:newsCommand});
    resolveSend({revision:3});await second;assert.equal(commandPanelsLocked(storm,news),false);
  }finally{globalThis.document=previousDocument;globalThis.sessionStorage=previousStorage;}
});
