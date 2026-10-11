import test from 'node:test';
import assert from 'node:assert/strict';
import { createAuthHandler, safeReturn } from '../../server/auth.mjs';
import { grantsFor, permits, capabilityFor } from '../../server/permissions.mjs';
const env = { WORKOS_API_KEY: 'test-key', WORKOS_CLIENT_ID: 'client_test', WORKOS_COOKIE_PASSWORD: 'x'.repeat(40), WORKOS_REDIRECT_URI: 'https://example.com/api/auth/callback', UTILITYSIM_ROLE_GRANTS: JSON.stringify({ user_allowed: [{role:'analyst', town:'town-a'}] }) };
function response(){return { headers:{}, getHeader(k){return this.headers[k]}, setHeader(k,v){this.headers[k]=v}, end(v){this.body=v} };}
function fixture(){
  const calls=[];
  const client = { userManagement: {
    getAuthorizationUrl(input){calls.push(input);return 'https://auth.example/login';},
    async authenticateWithCode(input){calls.push(input);return {sealedSession:'sealed-session'};},
    loadSealedSession(){return { async authenticate(){return {authenticated:true,user:{id:'user_allowed',email:'allowed@example.com',emailVerified:true}}}, async getLogoutUrl(){return 'https://auth.example/logout';} };},
  } };
  return {calls, handler:createAuthHandler({env,client:()=>client})};
}
test('login binds the browser with expiring HttpOnly secure state and PKCE', async()=>{
  const {handler,calls}=fixture(), res=response();
  await handler({method:'GET',url:'/api/auth/login?returnTo=%2Flibrary.html%3Ftown%3Dtown-a%23billing',headers:{}},res);
  assert.equal(res.statusCode,303);
  assert.match(res.headers['Set-Cookie'][0],/HttpOnly; SameSite=Lax; Max-Age=600; Secure/);
  assert.equal(calls[0].redirectUri,env.WORKOS_REDIRECT_URI);
  assert.equal(calls[0].codeChallengeMethod,'S256');
  assert.equal(calls[0].codeChallenge.length,43);
  const callback=response();
  await handler({method:'GET',url:'/api/auth/callback?code=single-use&state='+calls[0].state,headers:{cookie:res.headers['Set-Cookie'][0].split(';')[0]}},callback);
  assert.equal(callback.headers.Location,'/library.html?town=town-a#billing');
  assert.equal(calls[1].codeVerifier.length,43);
  assert.match(callback.headers['Set-Cookie'][1],/utilitysim-session=sealed-session/);
});
test('forged state is rejected without exchanging a code',async()=>{
  const {handler,calls}=fixture(), start=response();
  await handler({method:'GET',url:'/api/auth/login',headers:{}},start);
  const res=response();
  await handler({method:'GET',url:'/api/auth/callback?code=bad&state=wrong',headers:{cookie:start.headers['Set-Cookie'][0].split(';')[0]}},res);
  assert.equal(res.statusCode,400);assert.equal(calls.length,1);
});
test('default login returns to the authenticated world chooser',async()=>{
  const {handler,calls}=fixture(), start=response();
  await handler({method:'GET',url:'/api/auth/login',headers:{}},start);
  const done=response();
  await handler({method:'GET',url:'/api/auth/callback?code=single-use&state='+calls[0].state,headers:{cookie:start.headers['Set-Cookie'][0].split(';')[0]}},done);
  assert.equal(done.headers.Location,'/workspace.html');
});
test('an existing valid session enters through login without choosing a map',async()=>{
  const {handler,calls}=fixture(), res=response();
  await handler({method:'GET',url:'/api/auth/login',headers:{cookie:'utilitysim-session=valid'}},res);
  assert.equal(res.headers.Location,'/workspace.html');assert.equal(calls.length,0);
});
test('session response never returns tokens and is not cached',async()=>{
  const {handler}=fixture(), res=response();
  await handler({method:'GET',url:'/api/auth/session',headers:{cookie:'utilitysim-session=test'}},res);
  const data=JSON.parse(res.body);
  assert.equal(data.user.id,'user_allowed');assert.deepEqual(data.grants,[{role:'analyst',town:'town-a'}]);
  assert.equal(data.accessToken,undefined);assert.equal(res.headers['Cache-Control'],'private, no-store');
});
test('signed out session and cross-origin logout',async()=>{
  const {handler}=fixture(), session=response(), logout=response();
  await handler({method:'GET',url:'/api/auth/session',headers:{}},session);
  assert.deepEqual(JSON.parse(session.body),{authenticated:false});
  await handler({method:'POST',url:'/api/auth/logout',headers:{origin:'https://evil.example'}},logout);
  assert.equal(logout.statusCode,403);
  const good=response();await handler({method:'POST',url:'/api/auth/logout',headers:{origin:'https://example.com',cookie:'utilitysim-session=test'}},good);
  assert.equal(JSON.parse(good.body).url,'https://auth.example/logout');
  assert.match(good.headers['Set-Cookie'][0],/Max-Age=0/);
});
test('redirects allow only shell paths, never external or auth-loop destinations',()=>{
  for(const target of ['https://evil.example','//evil.example','/\\evil.example','/api/auth/logout','/%2f%2fevil.example']) assert.equal(safeReturn(target),'/');
  assert.equal(safeReturn('/library.html?town=town-a#billing'),'/library.html?town=town-a#billing');
});
test('new users have no privileges; grants expire and remain town scoped',()=>{
  assert.deepEqual(grantsFor('new',env),[]);
  assert.equal(permits(grantsFor('user_allowed',env),'world.view','town-a'),true);
  assert.equal(permits(grantsFor('user_allowed',env),'world.view','town-b'),false);
  assert.equal(permits(grantsFor('user_allowed',env),'billing.run','town-a'),false);
  const bad={UTILITYSIM_ROLE_GRANTS:JSON.stringify({u:[{role:'owner',town:'*',revoked:true},{role:'owner',town:'*',expiresAt:'2000-01-01'},{role:'owner',town:'*',expiresAt:'bad'},{role:'inherited_admin',town:'*'}]})};
  assert.deepEqual(grantsFor('u',bad),[]);
  assert.equal(permits([{role:'owner',town:'*'}],'field.review','town-b'),true);
});
test('runtime actions are explicitly classified and unknown endpoints denied',()=>{
  assert.equal(capabilityFor('POST','virtual-systems/run'),'billing.run');
  assert.equal(capabilityFor('POST','virtual-systems/accept-report'),'field.review');
  assert.equal(capabilityFor('GET','premises/a/history'),'world.view');
  assert.equal(capabilityFor('POST','unknown'),null);
  assert.equal(capabilityFor('GET','../secrets'),null);
  assert.equal(capabilityFor('GET','premises/%2e%2e%2fvirtual-systems'),null);
  assert.equal(capabilityFor('GET','premises/..'),null);
});
test('missing callback state is a 400, not a provider exchange',async()=>{
  const {handler,calls}=fixture(),res=response();
  await handler({method:'GET',url:'/api/auth/callback?code=bad',headers:{}},res);
  assert.equal(res.statusCode,400);assert.equal(calls.length,0);
});
