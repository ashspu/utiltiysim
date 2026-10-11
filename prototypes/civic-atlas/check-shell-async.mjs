import {chromium,browserOptions} from './browser-runtime.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const browser=await chromium.launch(browserOptions),proof=[];
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
async function fixture({configuredA=true,configuredB=true,initialized=true}={}){
 const page=await browser.newPage(),requests=[],errors=[],holds=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/presets/shared/tiled-map.html*',route=>route.fulfill({contentType:'text/html',body:'<html>Map fixture</html>'}));
 await page.route('**/atlas/api/**',async route=>{
  const req=route.request(),url=new URL(req.url()),path=url.pathname.split('/atlas/api/')[1],town=url.searchParams.get('town')||'a-town';
  requests.push({path,town,host:url.host,method:req.method(),auth:req.headers().authorization,body:req.postDataJSON()});
  const hold=holds.find(h=>!h.used&&h.path===path&&h.town===town);if(hold){hold.used=true;hold.started.resolve();await hold.release.promise;}
  const configured=town==='a-town'?configuredA:configuredB;
  const financial={configured,initialized,tariffPolicy:'Fixture',counts:{accounts:1,installations:1,reads:1,bills:0,invoices:0,exceptions:0},invoices:[],exceptions:[],exceptionTotal:0,trialBalance:{totals:{}},receivedThrough:'2026-01-08',through:'2026-01-08',fieldRequests:[],receivedReadings:[]};
  let value;
  if(path==='catalog')value={presets:['a-town','b-town'].map(id=>({id,name:id,targetHomes:500,baked:true}))};
  else if(path==='summary')value={town:{id:'WORLD-'+town,homes:500,premises:501,accounts:501},state:{through:'2026-01-08',days:7,assets:1,observations:7,manualAdvanceAllowed:true,events:[]}};
  else if(path==='integration')value={virtualSystems:{configured,initialized}};
  else if(path==='billing')value={accounts:[{id:'ACCOUNT-'+town}],customers:[{name:'Customer '+town}],documents:[],cases:[],reads:[],receivedReads:0};
  else if(path.startsWith('premises/'))value={premise:{address:town+' '+path.split('/')[1]},through:'2026-01-08',assets:[{id:'M-'+town,installation:'I-'+town,commodity:'water',condition:'working'}]};
  else if(path==='virtual-systems')value=financial;
  else if(path==='virtual-systems/repair')value={order:{id:'OLD-REPORT-'+town,status:'reported',reports:[{outcome:'not_found'}]}};
  else if(path==='billing/replace-meter')value={note:'OLD-REPLACEMENT-'+town};
  else value={...financial,imported:11};
  await route.fulfill({json:value,headers:{'Access-Control-Allow-Origin':'*'}});
 });
 const hold=(path,town='a-town')=>{const h={path,town,started:deferred(),release:deferred()};holds.push(h);return h;};
 const ready=async town=>{await page.waitForFunction(t=>document.querySelector('#town').value===t&&document.querySelector('#connection-status').textContent==='Persistent runtime connected',town);await page.getByRole('button',{name:'Receive meter reads',exact:true}).waitFor();};
 const open=async(id='P-1')=>{await page.locator('nav [data-page="map"]').click();await page.evaluate(id=>window.dispatchEvent(new MessageEvent('message',{origin:location.origin,source:document.querySelector('#town-map').contentWindow,data:{type:'atlas-premise',premiseId:id}})),id);await page.locator('[data-field]').waitFor();};
 const done=async name=>{assert.deepEqual(errors,[]);proof.push({name,passed:true});await page.close();};
 return {page,requests,hold,ready,open,done};
}
// A slow old integration response cannot turn B's local workspace into A's VS view.
{
 const f=await fixture({configuredB:false}),h=f.hold('integration');await f.page.goto('http://127.0.0.1:8044/?town=a-town#overview');await h.started.promise;
 await f.page.selectOption('#town','b-town');await f.ready('b-town');h.release.resolve();await f.page.waitForTimeout(80);
 await f.page.locator('nav [data-page="billing"]').click();assert.equal(await f.page.locator('#title').textContent(),'Local charge preview');await f.done('integration response cannot overwrite another town');
}
// Stop initialize -> ingest if the user changes towns while initialization commits.
{
 const f=await fixture({initialized:false});await f.page.goto('http://127.0.0.1:8044/?town=a-town#overview');await f.ready('a-town');const h=f.hold('virtual-systems/initialize');
 await f.page.getByRole('button',{name:'Receive meter reads',exact:true}).click();await h.started.promise;await f.page.selectOption('#town','b-town');await f.ready('b-town');h.release.resolve();await f.page.waitForTimeout(80);
 assert.equal(f.requests.filter(r=>r.path==='virtual-systems/ingest').length,0);assert.equal(await f.page.getByRole('button',{name:'Receive meter reads',exact:true}).isEnabled(),true);await f.done('town switch stops chained mutation and releases new town controls');
}
// Property IDs may be identical in different towns; old crew results must not attach to B.
{
 const f=await fixture();await f.page.goto('http://127.0.0.1:8044/?town=a-town#overview');await f.ready('a-town');await f.open();const h=f.hold('virtual-systems/repair');
 await f.page.locator('[data-field] input').fill('Fixture request');await f.page.locator('[data-field] button').click();await h.started.promise;
 await f.page.selectOption('#town','b-town');await f.page.waitForFunction(()=>document.querySelector('#connection-status').textContent==='Persistent runtime connected');await f.open();h.release.resolve();await f.page.waitForTimeout(80);
 assert.equal(await f.page.locator('#field-result').textContent(),'');assert.ok((await f.page.locator('#property-body h2').textContent()).startsWith('b-town'));
 assert.equal(f.requests.find(r=>r.path==='virtual-systems/repair').body.townId,'WORLD-a-town');await f.done('field result cannot cross town or property identity');
}
// A local replacement completing after close/reopen of the same premise is stale too.
{
 const f=await fixture();await f.page.goto('http://127.0.0.1:8044/?town=a-town#overview');await f.ready('a-town');await f.open();await f.page.locator('[data-replace]').click();const h=f.hold('billing/replace-meter');
 await f.page.locator('form input[name="note"]').fill('Fixture replacement');await f.page.getByRole('button',{name:'Record completed work'}).click();await h.started.promise;await f.page.locator('#close-property').click();await f.open();
 const before=f.requests.filter(r=>r.path==='premises/P-1').length;h.release.resolve();await f.page.waitForTimeout(80);assert.equal(f.requests.filter(r=>r.path==='premises/P-1').length,before);assert.ok(!(await f.page.locator('#notice').textContent()).includes('OLD-REPLACEMENT'));await f.done('same-premise reopen invalidates pending replacement result');
}
// Runtime reconnect invalidates mount callbacks and keeps old authorization on the old request only.
{
 const f=await fixture();await f.page.goto('http://127.0.0.1:8044/?town=a-town#overview');await f.ready('a-town');await f.page.locator('nav [data-page="billing"]').click();await f.page.locator('[data-vs="ingest"]').waitFor();const h=f.hold('virtual-systems/ingest');
 await f.page.locator('[data-vs="ingest"]').click();await h.started.promise;await f.page.locator('nav [data-page="connections"]').click();await f.page.locator('#backend').fill('http://127.0.0.1:9999');await f.page.locator('#token').fill('mock-new-runtime-token');await f.page.locator('#connection-form button').click();
 await f.page.waitForFunction(()=>document.querySelector('#connection-status').textContent==='Persistent runtime connected');h.release.resolve();await f.page.waitForTimeout(80);
 assert.equal(await f.page.locator('#title').textContent(),'Connect the runtime');const old=f.requests.find(r=>r.path==='virtual-systems/ingest');assert.equal(old.host,'127.0.0.1:8044');assert.equal(old.auth,undefined);assert.ok(f.requests.filter(r=>r.host==='127.0.0.1:9999').every(r=>r.auth==='Bearer mock-new-runtime-token'));assert.ok(!(await f.page.locator('#notice').textContent()).includes('ingest completed'));await f.done('runtime reconnect fences mounted billing callbacks and tokens');
}
await mkdir('out/release-qa/async-shell',{recursive:true});await writeFile('out/release-qa/async-shell/proof.json',JSON.stringify(proof,null,2));console.log(JSON.stringify(proof));await browser.close();
