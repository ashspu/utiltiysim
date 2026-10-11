import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {createSetupsHandler} from '../../api/setups.js';
import {draftStore,validateSetupAction,lifecycleScript,saveScript,publicSetup} from '../../server/setup-drafts.mjs';

const env={WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'test',WORKOS_COOKIE_PASSWORD:'x'.repeat(40),WORKOS_REDIRECT_URI:'https://example.com/api/auth/callback'};
const action=(changes={})=>({action:'delete',id:randomUUID(),revision:4,commandId:randomUUID(),...changes});
const record={id:randomUUID(),revision:4,status:'setup',grantTownId:'town-a',sourceId:'pinned',sourceRevision:'source-sha',snapshotSha256:'snapshot-sha',configuration:{world:{weather:{winter_mean_c:2}}},updatedAt:'2026-10-11',commandId:'private-save',requestHash:'private-hash'};
function apiHarness({user='owner-a',verified=true,authenticated=true,grants=[{role:'owner',town:'town-a'}],storageError=false,current=record}={}){
  const calls=[];
  const handler=createSetupsHandler({env:{...env,UTILITYSIM_ROLE_GRANTS:JSON.stringify({[user]:grants})},client:()=>({userManagement:{loadSealedSession:()=>({authenticate:async()=>({authenticated,user:{id:user,emailVerified:verified}}),refresh:async()=>({authenticated:false})})}}),store:()=>({
    get:async(actor,id)=>{calls.push(['get',actor,id]);if(storageError)throw Error('private-provider-token');return current&&id===current.id?current:null;},
    list:async(actor,options)=>{calls.push(['list',actor,options]);if(storageError)throw Error('private-provider-token');return [{...record,status:options.trash?'deleted':'setup'}];},
    transition:async(actor,input,town)=>{calls.push(['transition',actor,input,town]);if(storageError)throw Error('private-provider-token');return {...record,revision:5,status:input.action==='delete'?'deleted':'setup'};}
  })});
  return {calls,async request({method='POST',body=action({id:record.id}),url='/api/setups',origin='https://example.com'}={}){let data;const headers={};const res={setHeader:(k,v)=>headers[k]=v,getHeader:k=>headers[k],end:value=>data=JSON.parse(value)};await handler({method,body,url,headers:{origin,cookie:'utilitysim-session=test'}},res);return {status:res.statusCode,data};}};
}

test('delete/restore DTO rejects unknown fields, unsafe revisions and invalid UUIDs',()=>{
  for(const body of [action({action:'purge'}),action({revision:0}),action({revision:1.2}),action({revision:Number.MAX_SAFE_INTEGER+1}),action({id:'other-owner/setup'}),action({commandId:'not-uuid'}),action({configuration:{}}),action({sourceId:'foreign'})])assert.throws(()=>validateSetupAction(body),e=>e.status===422);
  assert.deepEqual(validateSetupAction(action({action:'restore'})).action,'restore');
});

test('fresh verified owner and exact town access precede every lifecycle write',async()=>{
  for(const options of [{authenticated:false},{verified:false},{grants:[{role:'operator',town:'town-a'}]},{grants:[{role:'owner',town:'other'}]}]){
    const h=apiHarness(options),r=await h.request();assert.ok([401,403].includes(r.status));assert.equal(h.calls.filter(c=>c[0]==='transition').length,0);
  }
  const h=apiHarness();assert.equal((await h.request({origin:'https://foreign.example'})).status,403);assert.equal(h.calls.length,0);
  assert.equal((await apiHarness({current:null}).request()).status,404);
  const allowed=apiHarness();const r=await allowed.request();assert.equal(r.status,200);assert.deepEqual(allowed.calls[1].slice(0,2),['transition','owner-a']);assert.equal(allowed.calls[1][3],'town-a');assert.equal(r.data.setup.status,'deleted');assert.equal(r.data.setup.commandId,undefined);assert.equal(r.data.setup.requestHash,undefined);
});

test('trash is explicit and owner scoped; default collection stays active',async()=>{
  const h=apiHarness();assert.equal((await h.request({method:'GET',body:undefined})).status,200);assert.deepEqual(h.calls[0],['list','owner-a',{trash:false}]);
  const r=await h.request({method:'GET',url:'/api/setups?view=trash'});assert.equal(r.data.setups[0].status,'deleted');assert.deepEqual(h.calls[1],['list','owner-a',{trash:true}]);
  const viewer=apiHarness({grants:[{role:'viewer',town:'town-a'}]});assert.equal((await viewer.request({method:'GET',url:'/api/setups?view=trash'})).status,403);assert.equal(viewer.calls.length,0);
});

test('storage outage returns explicit503 without false deletion or empty trash success',async()=>{
  const h=apiHarness({storageError:true});for(const options of [{},{method:'GET',url:'/api/setups?view=trash'}]){const r=await h.request(options);assert.equal(r.status,503);assert.equal(r.data.setup,undefined);assert.equal(r.data.setups,undefined);assert.doesNotMatch(JSON.stringify(r.data),/private-provider-token/);assert.match(r.data.detail,/No save, delete or restore has been confirmed/);}
});

test('owner hash carries lifecycle command receipts atomically and excludes journal from lists',async()=>{
  const calls=[],deleted={...record,status:'deleted',deletedAt:'2026-10-12',updatedAt:'2026-10-12',revision:5};
  const redis={hget:async(key,id)=>{calls.push(['get',key,id]);return JSON.stringify(record);},hvals:async key=>{calls.push(['list',key]);return [record,deleted,{requestHash:'journal',setup:deleted}];},eval:async(script,keys,args)=>{calls.push(['eval',script,keys,args]);return JSON.stringify(deleted);}};
  const store=draftStore({},redis),input=validateSetupAction(action({id:record.id}));
  assert.deepEqual((await store.list('owner-a')).map(r=>r.status),['setup']);assert.deepEqual((await store.list('owner-a',{trash:true})).map(r=>r.status),['deleted']);
  await store.get('owner-b',record.id);assert.notEqual(calls[0][1],calls[2][1]);
  const receipt=await store.transition('owner-a',input,'town-a');assert.deepEqual(receipt,deleted);const call=calls.at(-1);assert.equal(call[1],lifecycleScript);assert.deepEqual(call[2],[calls[0][1]]);assert.deepEqual(JSON.parse(call[3][0]),input);assert.equal(call[3][1],createHash('sha256').update(JSON.stringify(input)).digest('hex'));assert.equal(call[3][3],'town-a');assert.deepEqual(receipt.configuration,record.configuration);assert.equal(receipt.sourceRevision,record.sourceRevision);assert.equal(publicSetup(receipt).requestHash,undefined);
  // A retained Lua receipt is returned as-is; JS does not recompute its revision/configuration.
  assert.deepEqual(await store.transition('owner-a',input,'town-a'),receipt);
});

test('atomic stale/body/identity/state guards are conflicts; missing records stay404',async()=>{
  for(const code of ['REVISION_CONFLICT','COMMAND_CONFLICT','SOURCE_CONFLICT','STATE_CONFLICT','NOT_FOUND']){
    const store=draftStore({}, {eval:async()=>{throw Error('SETUP_'+code);}});
    await assert.rejects(store.transition('owner',action(),'town-a'),e=>e.status===(code==='NOT_FOUND'?404:409));
  }
});

// Optional isolated Lua interpreter: exercises the actual scripts with an in-memory
// Redis command surface, never the configured account store or network provider.
test('actual Lua preserves undo and old command receipts across later changes', {skip:!process.env.UTILITYSIM_LUA_PYTHON},()=>{
  const python=String.raw`
import hashlib,json,os,sys
if os.environ.get('UTILITYSIM_LUA_MODULES'): sys.path.insert(0,os.environ['UTILITYSIM_LUA_MODULES'])
from lupa import LuaRuntime
scripts=json.load(sys.stdin);lua=LuaRuntime(unpack_returned_tuples=True);hashes={}
def table(value):
    if isinstance(value,dict): return lua.table_from({k:table(v) for k,v in value.items()})
    if isinstance(value,list): return lua.table_from([table(v) for v in value])
    return value
def value(item):
    if hasattr(item,'items'): return {k:value(v) for k,v in item.items()}
    return item
def call(operation,key,*args):
    data=hashes.setdefault(key,{})
    if operation=='HGET': return data.get(args[0])
    if operation=='HSET': data[args[0]]=args[1];return 1
    if operation=='HKEYS': return lua.table_from(list(data))
    if operation=='HLEN': return len(data)
    raise AssertionError(operation)
def reject(code): raise RuntimeError(code)
lua.globals().redis=lua.table_from({'call':call,'error_reply':reject})
lua.globals().cjson=lua.table_from({'decode':lambda text:table(json.loads(text)),'encode':lambda obj:json.dumps(value(obj),sort_keys=True)})
def execute(script,key,args):
    lua.globals().KEYS=lua.table_from([key]);lua.globals().ARGV=lua.table_from(args)
    return json.loads(lua.execute(scripts[script]))
def save(key,id,revision,command):
    obj={'id':id,'revision':revision+1,'commandId':command,'requestHash':command,'sourceId':'source','sourceRevision':'pinned','snapshotSha256':'snapshot','grantTownId':'town','configuration':{'world':{'exact':2.123}},'status':'setup','createdAt':'original','updatedAt':'save'}
    return execute('saveScript',key,[id,revision,json.dumps(obj)])
def action(key,kind,revision,command,id='draft'):
    obj={'action':kind,'id':id,'revision':revision,'commandId':command};encoded=json.dumps(obj,sort_keys=True)
    return execute('lifecycleScript',key,[encoded,hashlib.sha256(encoded.encode()).hexdigest(),'later','town'])
def conflict(code,fn):
    try: fn()
    except Exception as error: assert code in str(error),str(error)
    else: raise AssertionError('Missing '+code)
original=save('owner-a','draft',0,'save-one')
deleted=action('owner-a','delete',1,'delete-one');assert deleted['status']=='deleted' and deleted['revision']==2
assert deleted['configuration']==original['configuration'] and deleted['sourceRevision']==original['sourceRevision']
conflict('SETUP_DELETED',lambda:save('owner-a','draft',2,'edit-deleted'))
restored=action('owner-a','restore',2,'restore-one');assert restored['revision']==3 and 'deletedAt' not in restored
assert restored['configuration']==original['configuration'] and restored['createdAt']==original['createdAt']
assert action('owner-a','delete',1,'delete-one')==deleted
assert json.loads(hashes['owner-a']['draft'])==restored
conflict('SETUP_COMMAND_CONFLICT',lambda:action('owner-a','restore',1,'delete-one'))
conflict('SETUP_COMMAND_CONFLICT',lambda:action('owner-a','delete',1,'delete-one','different-draft'))
conflict('SETUP_NOT_FOUND',lambda:action('owner-b','delete',1,'delete-one'))
conflict('SETUP_REVISION_CONFLICT',lambda:action('owner-a','delete',1,'stale-command'))
conflict('SETUP_STATE_CONFLICT',lambda:action('owner-a','restore',3,'already-restored'))
conflict('SETUP_COMMAND_CONFLICT',lambda:save('owner-a','draft',3,'delete-one'))
updated=save('owner-a','draft',3,'save-two');assert updated['revision']==4
assert action('owner-a','delete',1,'delete-one')==deleted
assert json.loads(hashes['owner-a']['draft'])==updated
for index in range(99): hashes['owner-a']['other-'+str(index)]='{}'
conflict('SETUP_LIMIT',lambda:save('owner-a','new-draft',0,'new-save'))
assert len(hashes['owner-b'])==0
print('Lua delete/restore/replay/isolation/stale/state/edit/quota checks passed')
`;
  const result=spawnSync(process.env.UTILITYSIM_LUA_PYTHON,['-c',python],{input:JSON.stringify({saveScript,lifecycleScript}),encoding:'utf8',env:process.env});
  assert.equal(result.status,0,result.stderr||result.stdout);assert.match(result.stdout,/Lua delete\/restore\/replay/);
});
