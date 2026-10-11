import { WorkOS } from '@workos-inc/node';
import { config, identity, reply, sameOrigin } from '../server/auth.mjs';
import { grantsFor, permits } from '../server/permissions.mjs';
import { catalog } from '../server/setup-drafts.mjs';
import { fail, connectionStore, publicConnection, unsealCredential, runtimeRequest } from '../server/compute-connector.mjs';
const worldId=/^[0-9a-f]{32}$/;
export function createComputeHandler({env=process.env,client=cfg=>new WorkOS(cfg.apiKey,{clientId:cfg.clientId}),store=()=>connectionStore(env),authenticate=identity,call=runtimeRequest}={}) {
 return async(req,res)=>{try{
  const cfg=config(env), url=new URL(req.url,cfg.origin), action=url.searchParams.get('action'), post=['connection','test','create','advance'].includes(action)||(action==='storms'&&req.method==='POST');
  if(req.method!==(post?'POST':'GET') && !(action==='connection'&&req.method==='GET')) fail(405,'Method not allowed.');
  if(req.method==='POST'&&!sameOrigin(req,cfg)) fail(403,'Request origin refused.');
  if(Buffer.byteLength(JSON.stringify(req.body||{}))>65536) fail(413,'Request body exceeds 64 KiB.');
  const auth=await authenticate(req,res,cfg,client(cfg));if(!auth) fail(401,'Sign in to connect a runtime.');
  const actor=auth.user.id, grants=auth.user.emailVerified?grantsFor(actor,env):[];
  if(!grants.length) fail(403,'Current workspace access required.');
  const owner=town=>grants.some(g=>g.role==='owner'&&(g.town==='*'||!town||g.town===town));
  const storage=store();
  if(action==='connection') {if(!owner())fail(403,'Owner access required.');return reply(res,200,{connection:publicConnection(req.method==='GET'?await storage.get(actor):await storage.save(actor,req.body))});}
  if(!['test','worlds','create','status','advance','observations','storms','events'].includes(action))fail(404,'Unknown compute action.');
  if(action==='test'&&!owner())fail(403,'Owner access required.');
  const connection=await storage.get(actor); if(!connection?.secret)fail(503,'Configure your runtime endpoint and credential first.');
  const token=unsealCredential(connection.secret,env.WORKOS_COOKIE_PASSWORD,actor);
  const invoke=(path,method='GET',body)=>call({endpoint:connection.endpoint,token,actor,grants,path,method,body});
  let path,body=req.body;
  if(action==='test')path='/hosted/sources';
  if(action==='worlds') {const offset=url.searchParams.get('offset')||'0',limit=url.searchParams.get('limit')||'25';if(!/^\d{1,8}$/.test(offset)||!/^\d{1,2}$/.test(limit)||+limit<1||+limit>50)fail(422,'Invalid world pagination.');path=`/hosted/worlds?offset=${offset}&limit=${limit}`;}
  if(action==='create') {const source=catalog.sources.find(s=>s.id===body?.sourceId);if(!source||source.sourceRevision!==body.sourceRevision)fail(409,'Select the current approved source revision.');if(!owner(source.grantTownId))fail(403,'Owner access to this source required.');path='/hosted/worlds';}
  if(['status','advance','observations','storms','events'].includes(action)) {
    const id=url.searchParams.get('id');if(!worldId.test(id||''))fail(422,'Invalid world identifier.');
    const status=await invoke('/hosted/worlds/'+id);if(status.status!==200)return reply(res,status.status,status.data);
    const world=status.data, source=catalog.sources.find(s=>s.id===world.sourceId);
    if(!source||world.sourceRevision!==source.sourceRevision||world.grantTownId!==source.grantTownId)fail(409,'World source revision is not supported by this shell.');
    if(!permits(grants,(action==='advance'||action==='storms'&&req.method==='POST')?'world.advance':'world.view',source.grantTownId))fail(403,'Current world permission required.');
    if(action==='status')return reply(res,200,world);
    path='/hosted/worlds/'+id+'/'+(action==='storms'?'events/storms':action);
    if(['events','storms'].includes(action)&&req.method==='GET') {const query=new URLSearchParams();for(const field of action==='storms'?['before','eventsBefore','limit']:['before','limit']){const value=url.searchParams.get(field);if(value!==null){const date=field==='before'&&action==='storms';if(!(date?/^\d{4}-\d{2}-\d{2}$/:/^[1-9]\d{0,18}$/).test(value)||!date&&BigInt(value)>9223372036854775807n||(field==='limit'&&+value>50))fail(422,'Invalid event pagination.');query.set(field,value);}}path+='?'+query;}
    if(action==='observations'){const start=url.searchParams.get('start'),end=url.searchParams.get('end');if(!/^\d{4}-\d{2}-\d{2}$/.test(start||'')||!/^\d{4}-\d{2}-\d{2}$/.test(end||''))fail(422,'Observation dates required.');path+=`?start=${start}&end=${end}`;}
  }
  const result=await invoke(path,action==='test'?'GET':req.method,req.method==='POST'&&action!=='test'?body:undefined);
  if(action==='test') {if(result.status!==200||!Array.isArray(result.data?.sources)||!result.data.sources.length||!result.data.sources.every(s=>typeof s.sourceId==='string'&&/^[a-f0-9]{64}$/.test(s.sourceRevision||'')&&typeof s.ready==='boolean')||!result.data.sources.some(s=>s.ready&&catalog.sources.some(c=>c.id===s.sourceId&&c.sourceRevision===s.sourceRevision&&c.grantTownId===s.grantTownId&&owner(c.grantTownId))))fail(502,'Runtime did not confirm an available approved source.');return reply(res,200,{connected:true,sources:result.data.sources});}
  return reply(res,result.status,result.data);
 }catch(error){const status=[401,403,404,405,409,413,422,502,503,504].includes(error.status)?error.status:503;const detail=error.status?error.message:'Compute connection is unavailable.';return reply(res,status,{detail,error:detail});}};
}
export default createComputeHandler();
