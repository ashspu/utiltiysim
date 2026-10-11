import { createHash, randomBytes, createCipheriv, createDecipheriv } from 'node:crypto';
import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';
import https from 'node:https';
import { Redis } from '@upstash/redis';
import { setupStorageConfig } from './setup-storage.mjs';

export const fail = (status, message) => { throw Object.assign(new Error(message), {status}); };
export function endpointURL(value) {
  let url; try { url = new URL(value); } catch { fail(422,'Enter a public HTTPS runtime origin.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.port && url.port !== '443' || url.pathname !== '/' || url.search || url.hash || isIP(url.hostname.replace(/^\[|\]$/g,'')) || !url.hostname.includes('.') || /(?:^|\.)(localhost|local|internal|test|invalid)$/.test(url.hostname)) fail(422,'Enter a public HTTPS runtime origin.');
  return url.origin;
}
export function publicAddress(address) {
  if (isIP(address) === 4) {
    const [a,b] = address.split('.').map(Number);
    return !(a===0 || a===10 || a===127 || a>=224 || a===169&&b===254 || a===172&&b>=16&&b<=31 || a===192&&(b===168||b===0) || a===100&&b>=64&&b<=127 || a===198&&(b===18||b===19||b===51) || a===203&&b===0);
  }
  // Reject mapped/transition/link-local/ULA IPv6; only global unicast is allowed.
  return isIP(address)===6 && /^[23][0-9a-f]{3}:/i.test(address) && !/^2001:(?:0:|db8:|10:|20:)/i.test(address) && !/^2002:/i.test(address);
}
function encryptionKey(secret) {
  if (typeof secret !== 'string' || secret.length<32) fail(503,'Connector encryption unavailable.');
  return createHash('sha256').update('utilitysim.compute.credentials.v1\0'+secret).digest();
}
export function sealCredential(value, secret, actor) {
  const iv=randomBytes(12), cipher=createCipheriv('aes-256-gcm',encryptionKey(secret),iv);
  cipher.setAAD(Buffer.from(actor));
  const ciphertext=Buffer.concat([cipher.update(value,'utf8'),cipher.final()]);
  return [iv,cipher.getAuthTag(),ciphertext].map(x=>x.toString('base64url')).join('.');
}
export function unsealCredential(value, secret, actor) {
  const [iv,tag,data]=value.split('.').map(x=>Buffer.from(x,'base64url'));
  const cipher=createDecipheriv('aes-256-gcm',encryptionKey(secret),iv); cipher.setAAD(Buffer.from(actor)); cipher.setAuthTag(tag);
  return Buffer.concat([cipher.update(data),cipher.final()]).toString('utf8');
}
export function publicConnection(record) { return record ? {revision:record.revision,endpoint:record.endpoint,credentialConfigured:Boolean(record.secret),updatedAt:record.updatedAt} : null; }
export const connectionScript=`local old=redis.call('GET',KEYS[1])
local revision=0
if old then revision=cjson.decode(old).revision end
if revision~=tonumber(ARGV[1]) then return redis.error_reply('CONNECTOR_CONFLICT') end
redis.call('SET',KEYS[1],ARGV[2])
return ARGV[2]`;
export function connectionStore(env=process.env, redis) {
  if (!redis) redis=new Redis(setupStorageConfig(env));
  const key=actor=>'utilitysim:compute:v1:'+createHash('sha256').update(actor).digest('hex');
  const decode=x=>typeof x==='string'?JSON.parse(x):x;
  return {get:async actor=>decode(await redis.get(key(actor))), async save(actor,input) {
    if(!input||Object.keys(input).some(k=>!['revision','endpoint','credential'].includes(k))||!Number.isSafeInteger(input.revision)||input.revision<0) fail(422,'Invalid connector revision.');
    const endpoint=endpointURL(input.endpoint), old=await this.get(actor), credential=input.credential;
    if(!credential||Object.keys(credential).some(k=>!['operation','value'].includes(k))||!['keep','replace','clear'].includes(credential.operation)) fail(422,'Choose an explicit credential update.');
    let secret=old?.secret||null;
    if(credential.operation==='replace') { if(typeof credential.value!=='string'||credential.value.length<32||credential.value.length>4096||/[\r\n]/.test(credential.value)) fail(422,'Runtime bearer credential must contain 32–4096 characters.'); secret=sealCredential(credential.value,env.WORKOS_COOKIE_PASSWORD,actor); }
    else if(credential.value!==undefined) fail(422,'Credential value only allowed when replacing.');
    if(credential.operation==='clear') secret=null;
    if(old?.endpoint!==endpoint&&credential.operation==='keep'&&secret) fail(422,'Replace or clear the credential when changing endpoint.');
    const record={endpoint,secret,revision:input.revision+1,updatedAt:new Date().toISOString()};
    try { return decode(await redis.eval(connectionScript,[key(actor)],[input.revision,JSON.stringify(record)])); }
    catch(error) { if(/CONNECTOR_CONFLICT/.test(error.message)) fail(409,'Connection changed elsewhere. Reload before saving.'); throw error; }
  }};
}
export async function runtimeRequest({endpoint,token,actor,grants,path,method='GET',body}, {resolve=lookup, request=https.request, timeout=20000,maxBytes=3000000}={}) {
  endpointURL(endpoint);
  if(!token) fail(503,'Configure a runtime credential first.');
  const url=new URL(path,endpoint), addresses=await resolve(url.hostname,{all:true,verbatim:true});
  if(!addresses.length||addresses.some(x=>!publicAddress(x.address))) fail(422,'Runtime resolves to a restricted network address.');
  const target=addresses[0], payload=body===undefined?null:JSON.stringify(body);
  return new Promise((resolveResult,reject)=>{
    const req=request(url,{method,agent:false,lookup:(_host,opts,cb)=>cb(null,...(opts?.all?[[target]]:[target.address,target.family])),headers:{Authorization:'Bearer '+token,'X-UtilitySim-User-Id':actor,'X-UtilitySim-Grants':JSON.stringify(grants),Accept:'application/json',...(payload?{'Content-Type':'application/json','Content-Length':Buffer.byteLength(payload)}:{})}},res=>{
      if(res.statusCode>=300&&res.statusCode<400){res.destroy();return reject(Object.assign(new Error('Runtime redirects are refused.'),{status:502}));}
      if(!/^application\/json(?:;|$)/i.test(res.headers['content-type']||'')){res.destroy();return reject(Object.assign(new Error('Runtime did not return JSON.'),{status:502}));}
      let size=0;const chunks=[]; res.on('data',chunk=>{size+=chunk.length;if(size>maxBytes){res.destroy(Object.assign(new Error('Runtime response exceeds gateway limit.'),{status:502}));}else chunks.push(chunk);});
      res.on('error',reject);res.on('end',()=>{try{const data=JSON.parse(Buffer.concat(chunks));resolveResult({status:res.statusCode,data});}catch{reject(Object.assign(new Error('Invalid runtime response.'),{status:502}));}});
    });
    const timer=setTimeout(()=>req.destroy(Object.assign(new Error('Runtime request timed out.'),{status:504})),timeout);req.on('close',()=>clearTimeout(timer));req.on('error',reject);req.end(payload);
  });
}
