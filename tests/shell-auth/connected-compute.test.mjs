import test from 'node:test';
import assert from 'node:assert/strict';
import {createComputeHandler} from '../../api/compute.js';
import {sealCredential} from '../../server/compute-connector.mjs';
import {catalog} from '../../server/setup-drafts.mjs';

const id='a'.repeat(32), commandId='b13c037a-d05a-47ac-b583-9f7d01f5e244',source=catalog.sources[0],secret='k'.repeat(40);
const marker={configured:true,active:false,controllerId:'controller-one',runId:'run-one',revision:1,manualAdvanceAllowed:false};
const world={id,sourceId:source.id,sourceRevision:source.sourceRevision,grantTownId:source.grantTownId,through:'2026-01-01',connectedClock:marker};
const progress={schemaVersion:'connected-status/1',runId:'run-one',controllerId:'controller-one',physicalThrough:'2026-01-01',clock:'2026-01-01T00:00:00Z',phase:'paused',revision:3,target:null,activeCommandId:null,counts:{pending:1,failed:0,missing:2,unmapped:1,held:3},supportedActions:['pause','resume','advance']};
async function call({action='connected',body,role='owner',verified=true,origin='https://shell.example',selected=world,reply=progress,status=200,extra='',signedIn=true,grant={}}={}) {
  const calls=[],env={WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'test',WORKOS_COOKIE_PASSWORD:secret,WORKOS_REDIRECT_URI:'https://shell.example/api/auth/callback',UTILITYSIM_ROLE_GRANTS:JSON.stringify({alice:[{role,town:source.grantTownId,...grant}]})};
  const handler=createComputeHandler({env,client:()=>({}),authenticate:async()=>signedIn?{user:{id:'alice',emailVerified:verified}}:null,
    store:()=>({get:async()=>({endpoint:'https://runtime.example',secret:sealCredential('t'.repeat(40),secret,'alice')})}),
    call:async input=>{calls.push(input);return input.path.endsWith('/'+id)?{status:200,data:selected}:{status,data:reply};}});
  let data;const res={setHeader(){},end(value){data=JSON.parse(value);}};
  await handler({url:`/api/compute?action=${action}&id=${id}${extra}`,method:body?'POST':'GET',body,headers:{origin,'x-utilitysim-user-id':'mallory'}},res);
  return {status:res.statusCode,data,calls};
}
test('paused connected worlds cannot bypass controller with raw manual advance',async()=>{
  const result=await call({action:'advance',body:{through:'2026-01-02'}});assert.equal(result.status,409);assert.equal(result.calls.length,1);
  assert.equal((await call({action:'advance',body:{through:'2026-01-02'},selected:{...world,connectedClock:'unverified'}})).status,502);
});
test('legacy independent advancement remains available',async()=>{const {connectedClock,...legacy}=world;const result=await call({action:'advance',body:{through:'2026-01-02'},selected:legacy});assert.equal(result.status,200);assert.equal(result.calls[1].path,`/hosted/worlds/${id}/advance`);});
test('connected status is bound to world, run and controller and masks private fields',async()=>{
  const result=await call({reply:{...progress,token:'machine-secret',controllerUrl:'http://private',jobPayload:{credential:'secret'}}});assert.equal(result.status,200);assert.deepEqual(result.data,{...progress,technicalError:false});
  assert.equal(result.calls[1].path,`/hosted/worlds/${id}/connected`);assert.equal(result.calls[1].actor,'alice');
  for(const reply of [{...progress,runId:'foreign'},{...progress,controllerId:'foreign'},{...progress,counts:{...progress.counts,held:-1}}])assert.equal((await call({reply})).status,502);
  assert.equal((await call({selected:{...world,id:'f'.repeat(32)}})).status,502);
});
test('actual UTC targets and matching command execution are projected without private errors',async()=>{
  const lastCommand={commandId,status:'failed',action:'advance',target:'2026-01-02T06:00:00Z',acceptedRevision:3,error:'https://private.invalid?token=secret'};
  const reply={...progress,phase:'failed',target:lastCommand.target,activeCommandId:commandId,lastCommand,technicalError:'private failure details',counts:{...progress.counts,unmappedInvoices:2}};
  const result=await call({reply});assert.equal(result.status,200);assert.equal(result.data.clock,progress.clock);assert.equal(result.data.target,lastCommand.target);assert.equal(result.data.technicalError,true);assert.equal(result.data.counts.unmappedInvoices,2);assert.equal(result.data.lastCommand.status,'failed');assert.ok(!JSON.stringify(result.data).includes('private'));
  for(const invalid of [{...reply,clock:'2026-02-30T00:00:00Z'},{...reply,target:'2026-01-02'},{...reply,lastCommand:{...lastCommand,acceptedRevision:4}},{...reply,lastCommand:{...lastCommand,action:'start'}}])assert.equal((await call({reply:invalid})).status,502);
});
test('an explicit producer outage preserves the local clock without inventing a physical cursor',async()=>{
  const reply={...progress,physicalThrough:null,producerAvailable:false,technicalError:'private connection failure',supportedActions:['pause']};
  const result=await call({reply});assert.equal(result.status,200);assert.equal(result.data.physicalThrough,null);assert.equal(result.data.producerAvailable,false);assert.deepEqual(result.data.supportedActions,['pause']);assert.equal(result.data.technicalError,true);
  for(const invalid of [{...reply,producerAvailable:true},{...reply,producerAvailable:undefined},{...reply,producerAvailable:'false'}])assert.equal((await call({reply:invalid})).status,502);
});
test('current verified view grant can read but cannot control',async()=>{
  assert.equal((await call({role:'analyst'})).status,200);
  assert.equal((await call({role:'analyst',action:'connected-command',body:{commandId,expectedRevision:3,action:'pause'}})).status,403);
  for(const options of [{signedIn:false},{verified:false},{grant:{revoked:true}},{grant:{town:'foreign-town'}}])assert.ok([401,403].includes((await call(options)).status));
});
test('operator control forwards exact retained command with server-derived identity',async()=>{
  const body={commandId,expectedRevision:3,action:'advance',through:'2026-01-02T00:00:00Z'},reply={commandId,status:'accepted',revision:4,token:'never-return'};
  const result=await call({role:'operator',action:'connected-command',body,reply,status:202});assert.equal(result.status,202);assert.deepEqual(result.calls[1].body,body);assert.equal(result.calls[1].path,`/hosted/worlds/${id}/connected/commands`);assert.equal(result.calls[1].actor,'alice');assert.deepEqual(result.data,{commandId,status:'accepted',revision:4});
});
test('controller commands reject CSRF, duplicate selection and browser authority fields',async()=>{
  const body={commandId,expectedRevision:3,action:'pause'};
  const csrf=await call({action:'connected-command',body,origin:'https://evil.example'});assert.equal(csrf.status,403);assert.equal(csrf.calls.length,0);
  for(const input of [{...body,token:'unsafe'},{...body,controllerUrl:'https://evil.example'},{...body,actor:'owner'},{...body,action:'start'},{...body,through:'2026-01-02'},{...body,expectedRevision:-1},{...body,action:'advance',through:'2026-02-30'}]){
    const result=await call({action:'connected-command',body:input});assert.equal(result.status,422);assert.equal(result.calls.length,1);
  }
  assert.equal((await call({extra:'&action=advance'})).status,422);assert.equal((await call({extra:`&id=${id}`})).status,502);
});
test('unconfigured worlds and controller failures never pretend a successful connection',async()=>{
  assert.equal((await call({selected:{...world,connectedClock:{configured:false,manualAdvanceAllowed:true}}})).status,409);
  const failed=await call({status:503,reply:{detail:'https://private?token=secret'}});assert.equal(failed.status,503);assert.ok(!JSON.stringify(failed.data).includes('token'));
  assert.equal((await call({action:'connected-command',body:{commandId,expectedRevision:3,action:'pause'},reply:{commandId:'foreign',status:'accepted',revision:4}})).status,502);
  assert.equal((await call({action:'connected-command',body:{commandId,expectedRevision:3,action:'pause'},reply:{commandId,status:'accepted',revision:5}})).status,502);
});
test('rejection proof is command-bound and never inferred from upstream HTTP status',async()=>{
  const body={commandId,expectedRevision:3,action:'pause'};
  for(const reply of [{detail:'preflight failed'},{commandRejected:true,commandId:'foreign'},{commandRejected:false,commandId}]) {
    const result=await call({action:'connected-command',body,reply,status:409});assert.equal(result.status,409);assert.equal(result.data.commandRejected,undefined);
  }
  const definitive=await call({action:'connected-command',body,status:409,reply:{commandId,commandRejected:true,error:'private URL'}});
  assert.equal(definitive.data.commandRejected,true);assert.ok(!JSON.stringify(definitive.data).includes('private'));
  assert.equal((await call({action:'connected-command',body,status:503,reply:{commandId,commandRejected:true}})).data.commandRejected,undefined);
});
