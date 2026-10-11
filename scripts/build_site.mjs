// The static town shell lives at /; the desktop downloads remain at /download/.
// Physical worlds and billing databases stay in the separate persistent runtime.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const repo = fileURLToPath(new URL('../', import.meta.url));
const out = path.join(repo, 'public');
const web = path.join(repo, 'prototypes/civic-atlas/web');
const catalog = JSON.parse(fs.readFileSync(path.join(web, 'presets/catalog.json'), 'utf8'));
const townIds = new Set(catalog.presets.map(p => p.id));
const presetFiles = new Set(['tiles.json', 'premise-index.json', 'landmarks.json', 'overview.webp', 'overview.json', 'geometry-overview.webp']);
const shellFiles = new Set(['library.html', 'library.js', 'library.css', 'world-builder.js', 'virtual-systems.js', 'landing.html', 'landing.js', 'landing.css', 'shell-session.js']);
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
  if (relative[0] !== 'presets') return relative.length === 1 && shellFiles.has(relative[0]);
  if (relative.length === 1 || relative[1] === 'catalog.json' || relative[1] === 'shared') return true;
  if (!townIds.has(relative[1])) return false;
  return relative.length === 2 || relative[2] === 'tiles' || presetFiles.has(relative[2]);
}});
fs.copyFileSync(path.join(web, 'landing.html'), path.join(out, 'index.html'));
// Only the hosted build uses WorkOS. The offline launcher retains its own runtime boundary.
for (const file of ['index.html', 'library.html']) {
  const target = path.join(out, file);
  fs.writeFileSync(target, fs.readFileSync(target, 'utf8').replace('<head>', '<head><meta name="utilitysim-hosted" content="true">'));
}
fs.cpSync(path.join(repo, 'site'), path.join(out, 'download'), {recursive: true});
fs.cpSync(path.join(repo, 'packages/town-viewer/dist/brand'), path.join(out, 'brand'), {recursive: true});
fs.cpSync(path.join(repo, 'packages/town-viewer/dist/brand'), path.join(out, 'download/brand'), {recursive: true});
fs.cpSync(path.join(repo, 'packages/town-viewer/dist'), path.join(out, 'viewer'), {recursive: true});
const files = fs.readdirSync(out, {recursive: true}).filter(f => fs.statSync(path.join(out, f)).isFile());
const bytes = files.reduce((sum, f) => sum + fs.statSync(path.join(out, f)).size, 0);
console.log(`public/: ${files.length} files, ${(bytes / 1e6).toFixed(1)} MB, ${townIds.size} towns; no world databases.`);
