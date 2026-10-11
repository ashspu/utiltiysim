import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createPageAccess } from '../../server/page-access.mjs';
import { hostedWelcome } from '../../scripts/hosted_welcome.mjs';
const env = {WORKOS_API_KEY:'test',WORKOS_CLIENT_ID:'client_test',WORKOS_COOKIE_PASSWORD:'x'.repeat(40),WORKOS_REDIRECT_URI:'https://example.com/api/auth/callback',UTILITYSIM_ROLE_GRANTS:JSON.stringify({u:[{role:'analyst',town:'town-a'}]})};
function gate({verified = true, granted = true, failure = false} = {}) {
  return createPageAccess({env:granted ? env : {...env,UTILITYSIM_ROLE_GRANTS:'{}'},client:() => ({userManagement:{loadSealedSession({sessionData}) {
    if (failure) throw new Error('Invalid session');
    return {authenticate:async()=>({authenticated:sessionData === 'valid',user:{id:'u',emailVerified:verified}}),refresh:async()=>({authenticated:false})};
  }}})});
}
const request = (path,cookie,method='GET') => new Request('https://example.com'+path,{method,headers:cookie ? {cookie:'utilitysim-session='+cookie} : {}});
test('only introduction assets and independently protected API handlers bypass the page gate',async()=>{
  const run=gate();
  for(const path of ['/','/index.html','/landing.js','/welcome.css','/assets/lantern-harbour-welcome.webp','/assets/lantern-harbour-welcome-small.webp','/brand/utility-studio-icon-color.svg','/api/auth/login','/atlas/api/state','/api/runtime']) {
    const result=await run(request(path));assert.equal(result.headers.get('x-middleware-next'),'1',path);
  }
  for(const path of ['/workspace.html','/library.html?town=town-a','/viewer/','/presets/shared/tiled-map.html?preset=town-a']) {
    const result=await run(request(path));assert.equal(result.status,303,path);assert.match(result.headers.get('location'),/^\/api\/auth\/login\?/);assert.equal(result.headers.get('x-middleware-next'),null);
  }
  for(const path of ['/presets/catalog.json','/presets/town-a/premise-index.json','/presets/town-a/tiles/1-1.json','/library.js']) assert.equal((await run(request(path))).status,401,path);
});
test('forged or revoked sessions cannot unlock static maps or workspace data',async()=>{
  for(const run of [gate(),gate({failure:true})]) for(const path of ['/workspace.html','/presets/catalog.json','/presets/town-a/tiles/1-1.json']) {
    const result=await run(request(path,'forged'));assert.ok([303,401].includes(result.status));assert.equal(result.headers.get('x-middleware-next'),null);
  }
});
test('authenticated static requests enforce verified, current, town-scoped grants before cache',async()=>{
  const run=gate();
  for(const path of ['/library.html?town=town-a','/presets/shared/tiled-map.html?preset=town-a','/presets/town-a/tiles/1-1.json']) {
    const result=await run(request(path,'valid'));assert.equal(result.headers.get('x-middleware-next'),'1');assert.equal(result.headers.get('cache-control'),'private, no-store');
  }
  for(const path of ['/library.html?town=town-b','/presets/shared/tiled-map.html?preset=town-b','/presets/town-b/overview.webp','/%70resets/town-b/premise-index.json']) assert.equal((await run(request(path,'valid'))).status,403,path);
  for(const run of [gate({verified:false}),gate({granted:false})]) {
    assert.equal((await run(request('/workspace.html','valid'))).headers.get('x-middleware-next'),'1');
    for(const path of ['/library.html?town=town-a','/presets/catalog.json','/viewer/']) assert.equal((await run(request(path,'valid'))).status,403,path);
  }
});
test('entry never chooses a default town and rejects ambiguous town requests',async()=>{
  const run=gate();
  for(const path of ['/library.html','/presets/shared/tiled-map.html']) assert.equal((await run(request(path,'valid'))).headers.get('location'),'/workspace.html');
  for(const path of ['/library.html?town=town-a&town=town-b','/library.html?town=../private','/presets/shared/tiled-map.html?preset=bad%2Ftown']) assert.equal((await run(request(path,'valid'))).status,400,path);
  assert.equal((await run(request('/workspace.html','valid','POST'))).status,405);
});
test('missing auth configuration fails closed for protected files',async()=>{
  const run=createPageAccess({env:{}});
  assert.equal((await run(request('/'))).headers.get('x-middleware-next'),'1');
  assert.equal((await run(request('/library.html?town=town-a','valid'))).status,503);
});
test('public welcome exposes only login while retaining artwork and four story chapters',()=>{
  const html=hostedWelcome(fs.readFileSync(new URL('../../prototypes/civic-atlas/web/index.html',import.meta.url),'utf8'));
  assert.equal([...html.matchAll(/<(?:a|button)\b/g)].length,1);
  assert.match(html,/id="sign-in"[^>]+href="\/api\/auth\/login/);
  assert.match(html,/utility-studio-icon-color.svg/);
  assert.match(html,/lantern-harbour-welcome.webp/);
  assert.equal([...html.matchAll(/data-story-chapter=/g)].length,4);
  assert.doesNotMatch(html,/Civic Atlas|Discover UtilitySim|Choose a world|A WORLD READY TO EXPLORE|welcome-masthead|welcome-account|saved-world-section|data-page=/i);
});
