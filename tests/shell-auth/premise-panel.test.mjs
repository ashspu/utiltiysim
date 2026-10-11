import test from 'node:test';
import assert from 'node:assert/strict';
import {createPremisePanel} from '../../prototypes/civic-atlas/web/world-control-premises.mjs';
class Node{constructor(tag){this.tag=tag;this.children=[];this.attributes={};this.value='';}append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=[...nodes];}setAttribute(key,value){this.attributes[key]=value;}removeAttribute(key){delete this[key];}async click(){if(!this.disabled)await this.onclick?.();}}
const a={id:'a'.repeat(32),sourceRevision:'1'.repeat(64),available:true,connectedClock:{configured:true}},b={...a,id:'b'.repeat(32)};
async function harness(run){const saved=Object.getOwnPropertyDescriptor(globalThis,'document');Object.defineProperty(globalThis,'document',{configurable:true,value:{createElement:tag=>new Node(tag)}});try{await run(new Node('section'));}finally{if(saved)Object.defineProperty(globalThis,'document',saved);else delete globalThis.document;}}
test('selector inspects actual physical ID and links same saved instance, without derived commercial IDs',async()=>harness(async root=>{
 const calls=[],request=async(action,args)=>{calls.push({action,args});return action==='premises'?{worldId:a.id,sourceRevision:a.sourceRevision,total:1,offset:0,premises:[{premiseId:'physical-maple-12',address:'12 Maple'}]}:{worldId:a.id,sourceRevision:a.sourceRevision,premise:{premiseId:args.premiseId,occupied:true}};};
 const panel=createPremisePanel(root,request);await panel.load(a);const [,,,select,inspect,,,detail,link]=root.children;await inspect.click();assert.deepEqual(calls[1],{action:'premise',args:{id:a.id,premiseId:'physical-maple-12'}});assert.equal(link.hidden,false);assert.equal(link.href,`/vs-operator.html?id=${a.id}&premiseId=physical-maple-12`);assert.equal(detail.children[1].textContent,'physical-maple-12');select.onchange();assert.equal(link.hidden,true);
}));
test('late response for old world cannot populate new selection or link',async()=>harness(async root=>{
 let release;const gate=new Promise(resolve=>{release=resolve;});const panel=createPremisePanel(root,async(action,args)=>{if(args.id===a.id){await gate;return {worldId:a.id,sourceRevision:a.sourceRevision,total:1,premises:[{premiseId:'old'}]};}return {worldId:b.id,sourceRevision:b.sourceRevision,total:1,premises:[{premiseId:'new'}]};});
 const old=panel.load(a);await panel.load(b);release();await old;assert.deepEqual(root.children[3].children.map(node=>node.value),['new']);assert.equal(root.children[8].hidden,true);
}));
