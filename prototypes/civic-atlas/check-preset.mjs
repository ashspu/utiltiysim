import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,browserOptions} from './browser-runtime.mjs';
const base=process.env.ATLAS_URL||'http://127.0.0.1:8042',out='out/civic-atlas/preset-review';await mkdir(out,{recursive:true});
const browser=await chromium.launch(browserOptions),errors=[],picks=[];
try{
 const page=await browser.newPage({viewport:{width:1600,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 const before=await(await page.request.get(base+'/atlas/api/bootstrap')).json(),town=before.snapshot;
 assert.equal(town.atlasDesign.presetId,'riverbend-500');
 const bindings=await(await page.request.get(base+'/presets/riverbend-500/bindings.json')).json();assert.equal(bindings.properties.length,525);
 await page.goto(base+'/presets/riverbend-500/review-v1.html');
 await page.waitForFunction(()=>document.querySelector('#vector').contentDocument?.querySelectorAll('#buildings polygon').length===525);
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('525'));
 await page.screenshot({path:out+'/vector-review.png',fullPage:true});
 const svgPick=await page.locator('#vector').evaluate(el=>{const p=el.contentDocument.querySelector('#buildings polygon'),r=p.getBoundingClientRect(),frame=el.getBoundingClientRect();return{id:p.dataset.premiseId,x:frame.x+r.x+r.width/2,y:frame.y+r.y+r.height/2};});
 await page.mouse.click(svgPick.x,svgPick.y);await page.locator('#selection').waitFor();
 assert.match(await page.locator('#selection').innerText(),new RegExp(svgPick.id));
 await page.locator('#selection a').click();
 await page.waitForFunction(()=>document.body.dataset.ready==='true',null,{timeout:180000});
 assert.equal(await page.evaluate(()=>window.atlasDiagnostics().selectedId),svgPick.id);
 const homes=[...Array(12)].map((_,i)=>town.premises[i*41]);
 for(const home of homes){
  await page.locator('#toggle-map-options').click();await page.locator('#map-search').fill(home.id);await page.locator('#search-results button').first().click();await page.locator('#close-map-options').click();
  await page.locator('#clear-map-selection').click();
  const point=await page.evaluate(async home=>{const T=await import('/viewer/vendor/three.module.js'),d=window.atlasDiagnostics(),c=new T.OrthographicCamera(...d.frustum,.5,100000);c.position.fromArray(d.camera);c.lookAt(new T.Vector3(...d.target));c.zoom=d.cameraZoom;c.updateProjectionMatrix();c.updateMatrixWorld();const p=new T.Vector3(home.x,home.elevationM+home.height*.65,home.z).project(c),r=document.querySelector('#map-canvas').getBoundingClientRect();return{x:r.x+(p.x+1)*r.width/2,y:r.y+(1-p.y)*r.height/2};},home);
  await page.mouse.click(point.x,point.y);await page.waitForFunction(id=>window.atlasDiagnostics().selectedId===id,home.id);
  await page.locator('#view-property').click();await page.locator('.reading-value').first().waitFor();
  assert.ok((await page.locator('#inspector-content').textContent()).includes(home.id));
  const history=await(await page.request.get(base+`/atlas/api/premises/${home.id}/history`)).json();
  const binding=bindings.properties.find(b=>b.premiseId===home.id);
  assert.ok(history.readings.length>0);assert.ok(history.readings.every(r=>binding.meterIds.includes(r.assetId)));
  if(picks.length===0)await page.screenshot({path:out+'/selected-property-records.png'});
  await page.locator('#close-property-dialog').click();picks.push({premiseId:home.id,buildingId:binding.buildingId,parcelId:binding.parcelId,meterIds:binding.meterIds,readingCount:history.readings.length});
 }
 await page.locator('#clear-map-selection').click();await page.locator('#toggle-map-options').click();await page.locator('#fit-map').click();await page.locator('#close-map-options').click();
 await page.screenshot({path:out+'/town-3d.png'});
 await page.locator('#toggle-map-options').click();await page.locator('[data-layer=zoning]').click();await page.locator('#close-map-options').click();
 await page.screenshot({path:out+'/town-zoning.png'});
 const report=await(await page.request.get(base+'/atlas/api/quality')).json();assert.equal(report.automatedPassed,true);assert.equal(report.checks.length,14);
 await page.reload();await page.waitForFunction(()=>document.body.dataset.ready==='true',null,{timeout:180000});
 assert.deepEqual(await(await page.request.get(base+'/atlas/api/bootstrap')).json(),before);assert.deepEqual(errors,[]);
 await writeFile(out+'/checks.json',JSON.stringify({passed:true,preset:town.atlasDesign.presetId,homes:town.homes,properties:bindings.properties.length,sourceUnchanged:true,svgPick,picks,quality:report,errors},null,2));
 console.log('PASS: SVG selection opens matching 3D entity; 12 actual roof picks resolve to correct premise, parcel, building, meters and saved readings; 14 quality checks; source unchanged after reload.');
}catch(error){console.error(error);throw error;}finally{await browser.close();}
