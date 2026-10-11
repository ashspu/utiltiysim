import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
class Node{
  constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.textContent='';this.value='';this.disabled=false;this.attributes={};}
  append(...nodes){for(const node of nodes)node.parent=this;this.children.push(...nodes);}replaceChildren(...nodes){this.children=[];this.append(...nodes);}
  setAttribute(key,value){this.attributes[key]=value;}get options(){return this.children;}
  all(predicate){return[...(predicate(this)?[this]:[]),...this.children.flatMap(child=>child.all(predicate))];}
  querySelectorAll(selector){return this.all(node=>selector==='[data-cancel]'?node.dataset.cancel:selector==='[data-news-cancel]'?node.dataset.newsCancel:false);}
  focus(){}async click(){for(let node=this;node;node=node.parent)if(node.disabled)return;return this.onclick?.();}
}
const identity='a'.repeat(32),other='b'.repeat(32);
const store=()=>{const data=new Map();return{data,getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};};
let sequence=0;
async function harness({managed=true,phase='paused',connectedUnavailable=false,storage=store(),session=store(),clock='2026-01-01T00:00:00Z',through='2026-01-01',commandReply}={}){
  const names=['document','location','history','fetch','localStorage','sessionStorage','crypto'];const saved=Object.fromEntries(names.map(name=>[name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  const nodes=new Map();const html=readFileSync(new URL('../../prototypes/civic-atlas/web/world-control.html',import.meta.url),'utf8');
  for(const match of html.matchAll(/<(\w+)[^>]*\bid="([^"]+)"/g))nodes.set(match[2],new Node(match[1]));
  for(const id of ['day','fast','advance','through','batch'])nodes.get('controls').append(nodes.get(id));nodes.get('batch').value='7';
  const records=new Map([identity,other].map(id=>[id,{id,name:id,available:true,state:'complete',start:'2026-01-01',through,days:1,grantTownId:'town',...(managed?{connectedClock:{configured:true,manualAdvanceAllowed:false}}:{})}]));
  const reports=new Map([identity,other].map(id=>[id,{worldInstanceId:id,phase,clock,physicalThrough:through,revision:0,supportedActions:phase==='running'?['pause']:['advance','pause','resume'],counts:{pending:phase==='running'?1:0,failed:0,missing:0,unmapped:0,held:0}}]));
  const requests=[];let authGate=null,actor='actor';
  const response=(value,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(value)});
  Object.defineProperty(globalThis,'document',{configurable:true,value:{hidden:true,getElementById:id=>nodes.get(id),createElement:tag=>new Node(tag),querySelector:()=>null}});
  Object.defineProperty(globalThis,'location',{configurable:true,value:{href:`http://test/world-control.html?id=${identity}`}});
  Object.defineProperty(globalThis,'history',{configurable:true,value:{replaceState:(_,__,url)=>{globalThis.location.href=String(url);}}});
  Object.defineProperty(globalThis,'localStorage',{configurable:true,value:storage});Object.defineProperty(globalThis,'sessionStorage',{configurable:true,value:session});Object.defineProperty(globalThis,'crypto',{configurable:true,value:{randomUUID}});
  Object.defineProperty(globalThis,'fetch',{configurable:true,value:async(url,options={})=>{
    requests.push({url,body:options.body?JSON.parse(options.body):null});
    if(url==='/api/auth/session'){if(authGate){const gate=authGate;authGate=null;await gate.promise;}return response({authenticated:true,user:{id:actor},grants:[{role:'owner',town:'town'}]});}
    if(url.startsWith('/api/setups'))return response({sources:[]});
    const args=new URL(url,'http://test').searchParams,action=args.get('action'),id=args.get('id');
    if(action==='worlds')return response({worlds:[...records.values()],total:2});
    if(action==='status')return response(records.get(id));
    if(action==='connected')return connectedUnavailable?response({detail:'Unavailable'},503):response(reports.get(id));
    if(action==='connected-command'){const command=JSON.parse(options.body);if(commandReply)return commandReply(command,response);return response({commandId:command.commandId,status:'accepted',revision:1});}
    if(action==='advance'){records.get(id).through=JSON.parse(options.body).through;return response(records.get(id));}
    if(action==='events')return response({events:[]});
    if(action==='storms')return response({worldInstanceId:id,through:records.get(id).through,revision:0,events:[],history:[]});
    if(action==='sentiment')return response({worldInstanceId:id,through:records.get(id).through,enabled:false});
    throw Error(`Unexpected test action ${action}`);
  }});
  try{await import(`../../prototypes/civic-atlas/web/world-control.js?integration=${++sequence}`);}catch(error){for(const name of names){if(saved[name])Object.defineProperty(globalThis,name,saved[name]);else delete globalThis[name];}throw error;}
  return{nodes,records,reports,requests,storage,button:label=>nodes.get('connected-panel').all(node=>node.tag==='button'&&node.textContent===label)[0],deferAuth(){let release;const promise=new Promise(resolve=>{release=resolve;});authGate={promise};return release;},setActor(value){actor=value;},close(){for(const name of names){if(saved[name])Object.defineProperty(globalThis,name,saved[name]);else delete globalThis[name];}}};
}
test('legacy independent Next day still uses only physical advance',async()=>{const h=await harness({managed:false});try{await h.nodes.get('day').click();assert.equal(h.requests.filter(item=>item.url.includes('action=advance')).length,1);assert.equal(h.requests.filter(item=>item.url.includes('connected-command')).length,0);assert.equal(h.nodes.get('connected-section').hidden,true);}finally{h.close();}});
test('configured paused world requests connected advance, and live running phase permits pause',async()=>{
  const h=await harness();try{await h.nodes.get('day').click();assert.equal(h.requests.filter(item=>item.url.includes('action=advance')).length,0);assert.equal(h.requests.filter(item=>item.url.includes('connected-command')).length,1);
    h.reports.get(identity).phase='running';h.reports.get(identity).supportedActions=['pause'];await h.button('Refresh reported status').click();assert.equal(h.button('Pause').disabled,false);await h.button('Pause').click();assert.equal(h.requests.filter(item=>item.body?.action==='pause').length,1);
  }finally{h.close();}
});
test('controller unavailable fails closed, and read-only refresh preserves retained uncertain command',async()=>{
  const storage=store(),command={commandId:randomUUID(),action:'advance',expectedRevision:0,through:'2026-01-02T00:00:00Z'};const key=`utilitysim:connected-command:v1:actor:${identity}`;storage.setItem(key,JSON.stringify({pending:command,lastReceipt:null}));
  const h=await harness({connectedUnavailable:true,storage});try{assert.equal(h.nodes.get('controls').disabled,true);assert.equal(h.button('Retry retained command').hidden,false);assert.equal(h.button('Refresh reported status').disabled,false);await h.button('Refresh reported status').click();assert.deepEqual(JSON.parse(storage.getItem(key)).pending,command);assert.equal(h.requests.filter(item=>item.url.includes('connected-command')).length,0);}finally{h.close();}
});
test('connected advance rejects targets beyond 31 days from actual VS clock',async()=>{const h=await harness({clock:'2026-01-01T06:00:00Z',through:'2026-01-02'});try{h.nodes.get('through').value='2026-02-02';await h.nodes.get('advance').click();assert.equal(h.requests.filter(item=>item.url.includes('connected-command')).length,0);assert.match(h.nodes.get('message').textContent,/within 31 days/);}finally{h.close();}});
test('displayed target maximum follows the full VS clock rather than the later physical cursor',async()=>{const h=await harness({clock:'2026-01-01T06:00:00Z',through:'2026-01-02'});try{assert.equal(h.nodes.get('through').max,'2026-02-01');}finally{h.close();}});
test('account switch blocks a connected command and does not replay another account storage',async()=>{const h=await harness();try{h.setActor('different-actor');await h.nodes.get('day').click();assert.equal(h.requests.filter(item=>item.url.includes('connected-command')).length,0);assert.match(h.nodes.get('message').textContent,/signed-in account changed/);}finally{h.close();}});
test('running connected status locks physical event and news mutation panels',async()=>{const h=await harness({phase:'running'});try{assert.equal(h.nodes.get('event-panel').all(node=>node.tag==='fieldset')[0].disabled,true);assert.equal(h.nodes.get('sentiment-panel').all(node=>node.tag==='fieldset')[0].disabled,true);assert.equal(h.button('Pause').disabled,false);}finally{h.close();}});
test('coexisting retained connected and storm commands permit at least one exact recovery action',async()=>{
  const storage=store(),session=store();storage.setItem(`utilitysim:connected-command:v1:actor:${identity}`,JSON.stringify({pending:{commandId:randomUUID(),action:'advance',expectedRevision:0,through:'2026-01-02T00:00:00Z'},lastReceipt:null}));
  session.setItem(`utilitysim-storm-command:${identity}`,JSON.stringify({commandId:randomUUID(),action:'schedule'}));
  const original=JSON.parse(storage.getItem(`utilitysim:connected-command:v1:actor:${identity}`)).pending;
  const h=await harness({storage,session});try{const connectedRetry=h.button('Retry retained command'),stormRetry=h.nodes.get('event-panel').all(node=>node.tag==='button'&&node.textContent==='Retry retained command')[0];assert.equal(connectedRetry.disabled&&stormRetry.disabled,false,'Cross-domain pending commands must not mutually deadlock exact recovery');
    await connectedRetry.click();assert.deepEqual(h.requests.find(item=>item.url.includes('connected-command')).body,original);
    assert.equal(stormRetry.disabled,false,'Once connected receipt is confirmed at paused status, storm exact recovery remains available');
    assert.equal(h.nodes.get('controls').disabled,true,'Unresolved storm command continues to block new advances');
  }finally{h.close();}
});
test('world switch during session preflight cannot redirect the original connected button intent',async()=>{
  const h=await harness();try{const release=h.deferAuth();const pending=h.nodes.get('day').click();await Promise.resolve();h.nodes.get('world').value=other;await h.nodes.get('open').click();release();await pending;
    assert.equal(h.requests.filter(item=>item.url.includes('connected-command')&&item.url.includes(other)).length,0,'Preflight must not mutate the newly selected world');
  }finally{h.close();}
});
test('gateway authentication and preflight 4xx cannot erase an earlier uncertain connected command',async()=>{
  for(const code of [401,403,404,409]) {
    const storage=store(),key=`utilitysim:connected-command:v1:actor:${identity}`;
    const command={commandId:randomUUID(),action:'advance',expectedRevision:0,through:'2026-01-02T00:00:00Z'};
    storage.setItem(key,JSON.stringify({pending:command,lastReceipt:null}));
    const h=await harness({storage,commandReply:(_command,response)=>response({detail:'Gateway preflight refused'},code)});
    try{await h.button('Retry retained command').click();assert.deepEqual(JSON.parse(storage.getItem(key)).pending,command);assert.equal(h.nodes.get('controls').disabled,true);}
    finally{h.close();}
  }
});
test('only explicit controller nonacceptance releases exact identity and requires fresh status',async()=>{
  const storage=store(),key=`utilitysim:connected-command:v1:actor:${identity}`;
  storage.setItem(key,JSON.stringify({pending:{commandId:randomUUID(),action:'pause',expectedRevision:0},lastReceipt:null}));
  const h=await harness({storage,commandReply:(_command,response)=>response({detail:'Revision changed',commandRejected:true},409)});
  try{await h.button('Retry retained command').click();assert.equal(JSON.parse(storage.getItem(key)).pending,null);assert.equal(h.nodes.get('controls').disabled,true);}
  finally{h.close();}
});
test('producer outage shows no physical cursor, blocks advance and retains advertised pause',async()=>{
  const h=await harness();
  try {
    Object.assign(h.reports.get(identity),{physicalThrough:null,producerAvailable:false,supportedActions:['pause','resume','advance']});
    await h.button('Refresh reported status').click();
    assert.equal(h.nodes.get('controls').disabled,true);assert.equal(h.button('Advance connected day').disabled,true);assert.equal(h.button('Resume').disabled,true);assert.equal(h.button('Pause').disabled,false);
    const definitions=h.nodes.get('connected-panel').all(node=>node.tag==='dl')[0].children;
    const physical=definitions.findIndex(node=>node.textContent==='Next physical UTC day');assert.equal(definitions[physical+1].textContent,'Unavailable');
    await h.button('Pause').click();assert.equal(h.requests.filter(item=>item.body?.action==='pause').length,1);
  } finally { h.close(); }
});
test('page distinguishes interrupted advance from an explicitly proved reached target',async()=>{
  const h=await harness();
  try{
    await h.nodes.get('day').click();
    const command=h.requests.find(item=>item.body?.action==='advance').body;
    const reported=h.reports.get(identity);
    reported.lastCommand={commandId:command.commandId,status:'interrupted',action:'advance',
      target:command.through,acceptedRevision:1,outcome:'interrupted',targetReached:false};
    reported.revision=1;
    await h.button('Refresh reported status').click();
    let text=h.nodes.get('connected-panel').all(node=>node.tag==='p').map(node=>node.textContent).join(' ');
    assert.match(text,/Advance interrupted; requested 2026-01-02T00:00:00Z. Current clock 2026-01-01T00:00:00Z/);
    assert.doesNotMatch(text,/Advance reached/);
    Object.assign(reported.lastCommand,{status:'completed',outcome:'target-reached',targetReached:true,achievedClock:command.through});
    reported.clock=command.through;
    await h.button('Refresh reported status').click();
    text=h.nodes.get('connected-panel').all(node=>node.tag==='p').map(node=>node.textContent).join(' ');
    assert.match(text,/Advance reached 2026-01-02T00:00:00Z/);
    delete reported.lastCommand.outcome;delete reported.lastCommand.targetReached;delete reported.lastCommand.achievedClock;
    await h.button('Refresh reported status').click();
    text=h.nodes.get('connected-panel').all(node=>node.tag==='p').map(node=>node.textContent).join(' ');
    assert.doesNotMatch(text,/Advance reached/);assert.match(text,/Check the reported clock for progress/);
  }finally{h.close();}
});
