import assert from 'node:assert/strict';
import {chromium,browserOptions} from './browser-runtime.mjs';

const browser=await chromium.launch(browserOptions);
const targets=[{url:process.env.ATLAS_STATIC_URL||'http://127.0.0.1:8058',connected:false}];
if(process.env.ATLAS_CONNECTED_URL)targets.push({url:process.env.ATLAS_CONNECTED_URL,connected:true});
const results=[];
try {
  for(const target of targets){
    const page=await browser.newPage({viewport:{width:1440,height:960}});
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto(target.url+'/?town=two-river-forest-500#map');
    await page.waitForFunction(connected=>document.querySelector('#connection-status')?.textContent===(connected?'Persistent runtime connected':'Runtime unavailable'),target.connected);
    await page.frameLocator('#town-map').locator('#map').waitFor();
    const map=page.frames().find(frame=>frame.url().includes('tiled-map.html'));
    await map.waitForFunction(()=>window.mapReady,null,{timeout:60000});
    // Frame a known parcel, then exercise a real canvas pointer selection.
    await map.evaluate(()=>window.atlasMap.selectPremise('P-00001'));
    if(target.connected){
      await page.locator('#property[open]').waitFor();
      await page.locator('#close-property').click();
    }
    await map.locator('#inspector .close').click();
    const canvas=map.locator('#map');
    const size=await canvas.boundingBox();
    await canvas.click({position:{x:size.width/2,y:size.height/2}});
    await map.locator('#inspector[open]').waitFor();
    assert.match(await map.locator('#details').innerText(),/P-00001/);
    assert.equal(await map.locator('#openRecord').getAttribute('target'),'_top');
    if(target.connected){
      await page.waitForFunction(()=>document.querySelector('#property-body')?.textContent.includes('Physical meter records'));
      assert.match(await page.locator('#property-body').innerText(),/P-00001/);
    }else{
      await map.waitForFunction(()=>document.querySelector('#history')?.textContent.includes('Connect the simulation runtime'));
      assert.equal(await page.locator('#property').evaluate(element=>element.open),false);
      assert.match(await map.locator('#details').innerText(),/Account/);
    }
    assert.deepEqual(errors,[]);
    results.push({url:target.url,connected:target.connected,property:'P-00001',pointerSelection:true,correctInspector:true,topLevelAccountLink:true,errors});
    await page.close();
  }
  console.log(JSON.stringify({passed:true,results}));
}finally{await browser.close();}
