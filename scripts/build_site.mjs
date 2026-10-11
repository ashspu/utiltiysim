// The static town shell lives at /; the desktop downloads remain at /download/.
// Physical worlds and billing databases stay in the separate persistent runtime.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {hostedWelcome} from './hosted_welcome.mjs';
const repo = fileURLToPath(new URL('../', import.meta.url));
const out = path.join(repo, 'public');
const web = path.join(repo, 'prototypes/civic-atlas/web');
const catalog = JSON.parse(fs.readFileSync(path.join(web, 'presets/catalog.json'), 'utf8'));
const townIds = new Set(catalog.presets.map(p => p.id));
const presetFiles = new Set(['tiles.json', 'premise-index.json', 'landmarks.json', 'overview.webp', 'overview.json', 'geometry-overview.webp']);
const shellFiles = new Set(['library.html', 'library.js', 'library.css', 'world-builder.js', 'virtual-systems.js', 'landing.js', 'landing.css', 'shell-session.js', 'style.css', 'welcome.css', 'welcome.js']);
for (const file of ['workspace.html','workspace.js','workspace.css','workspace-start-state.mjs']) shellFiles.add(file);
for (const file of ['physical-slider-form.mjs','physical-slider-form.css']) shellFiles.add(file);
for (const file of ['compute-connection.html','compute-connection.js','compute-connection.css','world-control.html','world-control.js','world-control.css','world-control-core.mjs','world-control-events.mjs','world-control-sentiment.mjs','world-control-connected.mjs','world-control-connected-state.mjs','world-control-connected-view.mjs']) shellFiles.add(file);
for (const file of ['world-control-premises.mjs','vs-operator.html','vs-operator.js','vs-operator.css','vs-operator-core.mjs']) shellFiles.add(file);
const welcomeHtml = hostedWelcome(fs.readFileSync(path.join(web, 'index.html'), 'utf8'));
const welcomeAssets = new Set([...welcomeHtml.matchAll(/src="\/assets\/([^"]+)"/g)].map(match => match[1]));
const workspaceAssets = new Set(['lantern-harbour-welcome.webp','lantern-harbour-welcome-small.webp']);
for (const match of welcomeHtml.matchAll(/srcset="([^"]+)"/g)) {
  for (const candidate of match[1].split(',')) {
    const asset = candidate.trim().split(/\s+/)[0];
    if (!asset.startsWith('/assets/') || asset.includes('..')) throw new Error('Invalid welcome image candidate');
    welcomeAssets.add(asset.slice('/assets/'.length));
  }
}
for (const asset of welcomeAssets) {
  if (!fs.existsSync(path.join(web, 'assets', asset))) throw new Error(`Missing welcome art: ${asset}`);
}
if (!fs.existsSync(path.join(web, 'library.html'))) throw new Error('Town-library shell is not built.');
for (const town of catalog.presets) {
  const folder = path.join(web, 'presets', town.id);
  for (const file of presetFiles) {
    if (!fs.existsSync(path.join(folder, file))) throw new Error(`${town.id}: missing ${file}`);
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(folder, 'tiles.json'), 'utf8'));
  const source = JSON.parse(fs.readFileSync(path.join(folder, 'source-package.json'), 'utf8'));
  const geometry = source.files.find(file => file.rawPath === 'geometry.json');
  if (manifest.presetId !== town.id || manifest.sourceSha256 !== geometry?.rawSha256) {
    throw new Error(`${town.id}: tiles and packaged source belong to different revisions`);
  }
  const overview = JSON.parse(fs.readFileSync(path.join(folder, 'overview.json'), 'utf8'));
  if (overview.sourceSha256 !== manifest.sourceSha256 || overview.rendererRevision !== 3) {
    throw new Error(`${town.id}: stale overview rendering`);
  }
  for (const tile of manifest.tiles) {
    if (!/^[0-9]+-[0-9]+$/.test(tile) || !fs.existsSync(path.join(folder, 'tiles', `${tile}.json`))) {
      throw new Error(`${town.id}: missing or invalid tile ${tile}`);
    }
  }
}
if (path.resolve(out) !== path.resolve(repo, 'public')) throw new Error('Unsafe output directory');
fs.rmSync(out, {recursive: true, force: true});
fs.mkdirSync(out, {recursive: true});
fs.cpSync(web, out, {recursive: true, filter(source) {
  const relative = path.relative(web, source).split(path.sep);
  if (!relative[0]) return true;
  if (relative[0] === 'assets') return relative.length === 1 || (relative.length === 2 && (welcomeAssets.has(relative[1]) || workspaceAssets.has(relative[1])));
  if (relative[0] !== 'presets') return relative.length === 1 && shellFiles.has(relative[0]);
  if (relative.length === 1 || relative[1] === 'catalog.json' || relative[1] === 'shared') return true;
  if (!townIds.has(relative[1])) return false;
  return relative.length === 2 || relative[2] === 'tiles' || presetFiles.has(relative[2]) || relative[2] === 'setup-preview.jpg';
}});
fs.writeFileSync(path.join(out, 'index.html'), welcomeHtml);
// Only the hosted build uses WorkOS. The offline launcher retains its own runtime boundary.
for (const file of ['index.html', 'library.html', 'workspace.html']) {
  const target = path.join(out, file);
  let html = fs.readFileSync(target, 'utf8').replace('<head>', '<head><meta name="utilitysim-hosted" content="true">');
  if (file === 'library.html') html = html.replace('class="brand" href="/"', 'class="brand" href="/workspace.html"');
  fs.writeFileSync(target, html);
}
fs.cpSync(path.join(repo, 'site'), path.join(out, 'download'), {recursive: true});
fs.cpSync(path.join(repo, 'packages/town-viewer/dist/brand'), path.join(out, 'brand'), {recursive: true});
fs.cpSync(path.join(repo, 'packages/town-viewer/dist/brand'), path.join(out, 'download/brand'), {recursive: true});
fs.cpSync(path.join(repo, 'packages/town-viewer/dist'), path.join(out, 'viewer'), {recursive: true});
const files = fs.readdirSync(out, {recursive: true}).filter(f => fs.statSync(path.join(out, f)).isFile());
const bytes = files.reduce((sum, f) => sum + fs.statSync(path.join(out, f)).size, 0);
console.log(`public/: ${files.length} files, ${(bytes / 1e6).toFixed(1)} MB, ${townIds.size} towns; no world databases.`);
