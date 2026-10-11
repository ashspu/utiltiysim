import {chromium,browserOptions} from './browser-runtime.mjs';
import {mkdir,writeFile} from 'node:fs/promises';
const browser=await chromium.launch(browserOptions),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
await page.goto('http://127.0.0.1:8044/?town=two-river-forest-500&premise=P-00001#map');
await page.waitForSelector('#property-body #property-vs',{timeout:180000});
await page.locator('#close-property').click();
await page.locator('nav [data-page="billing"]').click();
for(const operation of ['initialize','ingest']){
 await page.locator(`[data-vs="${operation}"]`).click();
 await page.waitForFunction(()=>document.querySelector('[data-vs="initialize"]')?.disabled===false,undefined,{timeout:180000});
}
for(const operation of ['run','invoice-eligible']){
 await page.locator('#vs-start').fill('2026-01-01');
 await page.locator('#vs-end').fill('2026-01-08');
 await page.locator(`[data-vs="${operation}"]`).click();
 await page.waitForFunction(()=>document.querySelector('[data-vs="run"]')?.disabled===false,undefined,{timeout:180000});
}
const result=await page.evaluate(async()=>await(await fetch('/atlas/api/virtual-systems?town=two-river-forest-500')).json());
if(!result.counts.invoices||!result.trialBalance.totals.CAD.balanced)throw new Error('Live real recipient proof did not produce a balanced posted invoice');
await mkdir('out/release-qa/live-shell',{recursive:true});
await page.screenshot({path:'out/release-qa/live-shell/billing.png',fullPage:true});
await page.reload();await page.waitForSelector('[data-vs="invoice-eligible"]',{timeout:180000});
const after=await page.evaluate(async()=>await(await fetch('/atlas/api/virtual-systems?town=two-river-forest-500')).json());
if(after.counts.invoices!==result.counts.invoices)throw new Error('Invoices changed on reload');
const proof={errors,url:page.url(),counts:result.counts,disposition:result.lastBillingBatch,receivedThrough:result.receivedThrough,balanced:result.trialBalance.totals.CAD.balanced,reloadPreserved:true};
await writeFile('out/release-qa/live-shell/proof.json',JSON.stringify(proof,null,2));
console.log(JSON.stringify(proof));await browser.close();
