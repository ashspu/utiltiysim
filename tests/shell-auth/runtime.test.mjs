import test from 'node:test';
import assert from 'node:assert/strict';
import {createRuntimeHandler} from '../../api/runtime.js';
const env={WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'client_test',WORKOS_COOKIE_PASSWORD:'x'.repeat(40),WORKOS_REDIRECT_URI:'https://shell.example/api/auth/callback',UTILITYSIM_RUNTIME_URL:'https://runtime.example',UTILITYSIM_RUNTIME_TOKEN:'server-only-test-token',UTILITYSIM_ROLE_GRANTS:JSON.stringify({u:[{role:'analyst',town:'town-a'}]})};
const client=()=>({userManagement:{loadSealedSession:()=>({authenticate:async()=>({authenticated:true,user:{id:'u',emailVerified:true}})})}});
function res(){return {headers:{},setHeader(k,v){this.headers[k]=v},getHeader(k){return this.headers[k]},end(body){this.body=JSON.parse(body)}};}
test('gateway refuses signed-out, wrong-town, mutation and duplicate-town requests before contacting runtime',async()=>{
 let calls=0;const handler=createRuntimeHandler({env,client,fetcher:async()=>{calls++;throw Error('Must not run')}});
 for(const [method,url,headers,expected] of [
  ['GET','/api/runtime?path=summary&town=town-a',{},401],
  ['GET','/api/runtime?path=summary&town=town-b',{cookie:'utilitysim-session=test'},403],
  ['POST','/api/runtime?path=billing/run&town=town-a',{cookie:'utilitysim-session=test',origin:'https://shell.example'},403],
  ['GET','/api/runtime?path=summary&town=town-a&town=town-b',{cookie:'utilitysim-session=test'},400],
  ['POST','/api/runtime?path=advance&town=town-a',{cookie:'utilitysim-session=test',origin:'https://evil.example'},403],
 ]){const response=res();await handler({method,url,headers},response);assert.equal(response.statusCode,expected);}
 assert.equal(calls,0);
});
test('allowed read forwards only the server token to the configured runtime',async()=>{
 let request;const handler=createRuntimeHandler({env,client,fetcher:async(url,options)=>{request={url:String(url),options};return {status:200,json:async()=>({town:'town-a'})}}});
 const response=res();await handler({method:'GET',url:'/atlas/api/summary?path=summary&town=town-a',headers:{cookie:'utilitysim-session=test',authorization:'Bearer attacker'}},response);
 assert.equal(response.statusCode,200);assert.equal(request.url,'https://runtime.example/atlas/api/summary?town=town-a');
 assert.equal(request.options.headers.Authorization,'Bearer server-only-test-token');assert.equal(request.options.redirect,'error');
 assert.equal(response.headers['Cache-Control'],'private, no-store');assert.equal(JSON.stringify(response.body).includes('token'),false);
});
