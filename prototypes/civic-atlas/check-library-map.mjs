import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
import {chromium,browserOptions} from './browser-runtime.mjs';

const base=process.env.ATLAS_URL||'http://127.0.0.1:8044';
const ids=process.argv.slice(2);
assert.ok(ids.length,'Provide one or more preset IDs');
const out=process.env.ATLAS_QA_OUTPUT||'out/release-qa/browser';
await mkdir(out,{recursive:true});
const browser=await chromium.launch(browserOptions),results=[];
try{
 for(const id of ids){
  const errors=[],picks=[];
  const page=await browser.newPage({viewport:{width:1440,height:960},deviceScaleFactor:2});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${base}/presets/shared/tiled-map.html?preset=${id}`);
  await page.waitForFunction(()=>window.mapReady,null,{timeout:180000});
  await page.screenshot({path:`${out}/${id}-overview.png`});
  const index=await (await page.request.get(`${base}/presets/${id}/premise-index.json`)).json();
  const manifest=await page.evaluate(()=>window.tileManifest);
  assert.equal(Object.keys(index).length,manifest.premises);
  const sample=[];
  const seen=new Set();
  // Scan the compact chunks rather than downloading a 50k-home engine snapshot.
  for(const key of manifest.tiles){
   const chunk=await(await page.request.get(`${base}/presets/${id}/tiles/${key}.json`)).json();
   for(const f of chunk.features){
    const kind=f.type==='property'?f.record.buildingType:f.type==='road'?'road':null;
    if(kind&&!seen.has(kind)){seen.add(kind);sample.push(f);}
   }
   if(['detached','storefront','school','church','industrial','road'].every(k=>seen.has(k)))break;
  }
  for(const f of sample){
   const point=f.type==='property'?index[f.id].slice(0,2):f.points[Math.floor(f.points.length/2)];
   await page.evaluate(([x,y])=>window.mapView.frame([x-70,y-40,140,90]),point);
   await page.waitForFunction(()=>window.renderStats?.visibleFeatures>0);
   await page.waitForTimeout(100);
   const pixel=await page.locator('#map').evaluate((canvas,[x,y])=>{const b=window.mapView.get(),r=canvas.getBoundingClientRect();return{x:r.left+(x-b[0])/b[2]*r.width,y:r.top+(y-b[1])/b[3]*r.height};},point);
   await page.mouse.click(pixel.x,pixel.y);
   await page.waitForFunction(id=>document.querySelector('#details').textContent.includes(id),f.id);
   picks.push({id:f.id,type:f.type,kind:f.record?.buildingType});
   if(f.type==='property'&&f.record.buildingType==='detached'){
    const dimensions=await page.locator('#map').evaluate(c=>({width:c.width,client:c.clientWidth,ratio:devicePixelRatio,stats:window.renderStats}));
    assert.equal(dimensions.width,dimensions.client*2,'Canvas was not rendered at device resolution');
    assert.ok(dimensions.stats.visibleFeatures>0,'Zoomed view is only a raster overview');
    await page.screenshot({path:`${out}/${id}-detail.png`});
   }
   await page.keyboard.press('Escape');
  }
  // Frame a four-way tile corner: duplicated features must have one stable shape.
  const corner=[manifest.tileSize,manifest.tileSize];
  await page.evaluate(([x,y])=>window.mapView.frame([x-90,y-60,180,120]),corner);
  await page.waitForTimeout(200);
  await page.screenshot({path:`${out}/${id}-tile-junction.png`});
  const stats=await page.evaluate(()=>window.renderStats);
  assert.deepEqual(errors,[]);
  results.push({id,passed:true,premises:manifest.premises,tiles:manifest.tiles.length,picks,deviceScaleFactor:2,stats,errors,
    visualReview:'Screenshots captured; automated tests do not certify aesthetic quality.'});
  await page.close();
  console.log(`${id}: ${picks.length} actual pointer picks; ${manifest.tiles.length} tiles; device-scale rendering passed.`);
 }
 await writeFile(`${out}/map-checks.json`,JSON.stringify({passed:true,towns:results},null,2));
} finally {await browser.close();}
