import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import os from 'node:os';
import {chromium,browserOptions} from './browser-runtime.mjs';

const base=process.env.ATLAS_URL||'http://127.0.0.1:8041',output='out/civic-atlas/workspace-review';
await mkdir(output,{recursive:true});
const started=performance.now(),browser=await chromium.launch(browserOptions),errors=[];
try{
 const page=await browser.newPage({viewport:{width:1600,height:1000},acceptDownloads:true});
 page.on('pageerror',e=>errors.push(e.message));
 const before=await(await page.request.get(base+'/atlas/api/bootstrap')).json();
 await page.goto(base+'/#quality');
 await page.waitForFunction(()=>document.body.dataset.ready==='true',null,{timeout:180000});
 await page.locator('#export-quality').waitFor();
 const expectedChecks=before.snapshot.atlasDesign?.presetId?14:12;
 assert.equal(await page.locator('.quality-result').count(),expectedChecks);
 assert.equal(await page.locator('.quality-result.status-good').count(),expectedChecks);
 assert.match(await page.locator('#quality-page').innerText(),/Visual acceptance remains a separate review/);
 const reportResponse=await page.request.get(base+'/atlas/api/quality'),report=await reportResponse.json();
 assert.equal(reportResponse.status(),200);assert.equal(report.automatedPassed,true);
 const downloadPromise=page.waitForEvent('download');await page.locator('#export-quality').click();
 const download=await downloadPromise,exported=JSON.parse(await readFile(await download.path(),'utf8'));
 assert.equal(exported.snapshotSha256,report.snapshotSha256);assert.equal(exported.townId,before.snapshot.id);
 await page.screenshot({path:output+'/quality-1600.png',fullPage:true});
 await page.locator('#quality-map').click();
 await page.locator('#toggle-map-options').click();await page.locator('#map-search').fill(before.snapshot.premises[0].id);await page.locator('#search-results button').first().click();await page.locator('#close-map-options').click();await page.locator('#view-property').click();await page.locator('#property-history').waitFor();
 const selected=await page.evaluate(()=>window.atlasDiagnostics());
 const history=await(await page.request.get(base+`/atlas/api/premises/${selected.selectedId}/history`)).json();
 await page.locator('#property-history').click();await page.locator('#history-map').waitFor();
 assert.equal(await page.locator('[data-observation]').count(),history.readings.length);
 assert.equal(history.premise.id,selected.selectedId);
 for(const reading of history.readings){
  const row=page.locator(`[data-observation="${reading.observationId}"]`);
  assert.match(await row.innerText(),new RegExp(reading.assetId));
  assert.ok((await row.innerText()).includes(reading.observedQuantity===null?'Not recorded':new Intl.NumberFormat('en').format(Number(reading.observedQuantity))));
 }
 const readingDownloadPromise=page.waitForEvent('download');await page.locator('#export-history').click();
 assert.deepEqual(JSON.parse(await readFile(await(await readingDownloadPromise).path(),'utf8')),history);
 await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:output+'/property-history-1600.png',fullPage:true});
 await page.locator('#history-map').click();await page.locator('#view-property').click();await page.locator('#property-history').waitFor();
 assert.deepEqual((await page.evaluate(()=>window.atlasDiagnostics())).camera,selected.camera);
 assert.equal((await page.evaluate(()=>window.atlasDiagnostics())).selectedId,selected.selectedId);
 // Missing records stay unknown, even when the API otherwise succeeds.
 await page.route('**/atlas/api/premises/*/history?*',async route=>{
  const response=await route.fetch(),data=await response.json();data.readings[0].observedQuantity=null;
  await route.fulfill({response,json:data});
 });
 await page.locator('#property-history').click();await page.locator('#history-map').waitFor();
 assert.match(await page.locator('[data-observation]').first().innerText(),/Not recorded/);
 await page.unroute('**/atlas/api/premises/*/history?*');
 await page.locator('#history-world').click();await page.locator('[data-filter=events]').click();
 assert.match(await page.locator('#activity-page').innerText(),/physical event journal/);
 // A failed check request cannot leave a stale green success panel.
 await page.route('**/atlas/api/quality',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Quality service unavailable for this test.'})}));
 await page.locator('.sidebar [data-page=quality]').click();await page.locator('#retry-quality').waitFor();
 assert.equal(await page.locator('.quality-result').count(),0);
 await page.unroute('**/atlas/api/quality');await page.locator('#retry-quality').click();await page.locator('#export-quality').waitFor();
 await page.setViewportSize({width:1024,height:850});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:output+'/quality-1024.png',fullPage:true});
 const after=await(await page.request.get(base+'/atlas/api/bootstrap')).json();assert.deepEqual(after,before);
 assert.deepEqual(errors,[]);
 const evidence={passed:true,worldId:before.snapshot.id,quality:report,sourceUnchanged:true,property:history.premise.id,readings:history.readings.length,
  checks:['quality report and export','property readings agree with API','reading export','map selection/camera preserved','missing quantity remains unknown','world activity restored','quality failure/retry','1024 layout'],
  environment:{platform:os.platform(),cpu:os.cpus()[0]?.model,logicalCpus:os.cpus().length,memoryGB:Math.round(os.totalmem()/1024**3),browser:browser.version()},elapsedSeconds:Math.round((performance.now()-started)/1000),errors};
 await writeFile(output+'/checks.json',JSON.stringify(evidence,null,2));
 console.log(`PASS: ${expectedChecks} live source checks, property history/export, source fidelity, unknown readings, preserved map context, failure/retry and responsive layout.`);
}finally{await browser.close();}
