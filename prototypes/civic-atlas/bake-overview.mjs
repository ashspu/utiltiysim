// Run after tile_pack.py against a locally served web/ directory or Atlas server.
// This draws the same native renderer used at close zoom, then freezes only the
// distant overview. Selectable geometry always remains in the vector tiles.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {chromium,browserOptions} from './browser-runtime.mjs';

const preset=process.argv[2];
assert.match(preset||'',/^[a-z0-9-]+$/,'Provide a preset ID');
const root=path.join(path.dirname(fileURLToPath(import.meta.url)),'web','presets',preset);
const base=process.env.ATLAS_URL||'http://127.0.0.1:8044';
const manifest=JSON.parse(await fs.readFile(path.join(root,'tiles.json'),'utf8'));
const width=3000,height=Math.round(width*manifest.bounds[3]/manifest.bounds[2]);
const browser=await chromium.launch(browserOptions);
const errors=[];
try {
  const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${base}/presets/shared/tiled-map.html?preset=${preset}&bake=1`,{waitUntil:'networkidle',timeout:180000});
  await page.waitForFunction(()=>window.mapReady,null,{timeout:180000});
  assert.equal(await page.evaluate(()=>window.tileManifest.sourceSha256),manifest.sourceSha256,'Server is serving a different source revision');
  for (const [stage,filename] of [['art','overview.webp'],['geometry','geometry-overview.webp']]) {
    await page.evaluate(async stage=>{
      const field=document.querySelector('#stage');field.value=stage;
      field.dispatchEvent(new Event('change'));
      await window.atlasMap.refresh();
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    },stage);
    const pixels=await page.locator('#map').evaluate(c=>c.toDataURL('image/webp',.94).split(',')[1]);
    await fs.writeFile(path.join(root,filename),Buffer.from(pixels,'base64'));
  }
  assert.deepEqual(errors,[],'Overview renderer raised browser errors');
  await fs.writeFile(path.join(root,'overview.json'),JSON.stringify({sourceSha256:manifest.sourceSha256,rendererRevision:3}));
  console.log(JSON.stringify({preset,passed:true,sourceSha256:manifest.sourceSha256,width,height}));
} finally {await browser.close();}
