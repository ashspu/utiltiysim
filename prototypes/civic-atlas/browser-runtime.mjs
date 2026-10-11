// Shared local browser discovery. Explicit paths always take precedence.
import {existsSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {isAbsolute,join} from 'node:path';

const modulePath=process.env.PLAYWRIGHT_MODULE||process.env.ATLAS_PLAYWRIGHT_MODULE;
const specifier=modulePath
  ? (isAbsolute(modulePath)?pathToFileURL(modulePath.endsWith('.mjs')||modulePath.endsWith('.js')?modulePath:join(modulePath,'index.mjs')).href:modulePath)
  : new URL('../../out/civic-atlas/browser/node_modules/playwright-core/index.mjs',import.meta.url).href;
export const {chromium}=await import(specifier);
const candidates=process.platform==='win32'
  ? [join(process.env['PROGRAMFILES(X86)']||'C:/Program Files (x86)','Microsoft/Edge/Application/msedge.exe'),join(process.env.PROGRAMFILES||'C:/Program Files','Google/Chrome/Application/chrome.exe')]
  : process.platform==='darwin'
    ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
    : ['/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome'];
export const executablePath=process.env.CHROMIUM_PATH||process.env.ATLAS_CHROMIUM||candidates.find(path=>existsSync(path));
if(!executablePath)throw new Error('Chromium/Chrome/Edge was not found. Set CHROMIUM_PATH to its executable.');
export const browserOptions={executablePath,headless:true,args:[...(process.getuid?.()===0?['--no-sandbox']:[]),'--disable-dev-shm-usage','--enable-unsafe-swiftshader','--no-proxy-server']};
