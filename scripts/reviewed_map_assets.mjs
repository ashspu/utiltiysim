import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
const sourceRevision='62bd251fba957150799feed2743b5026da6d4dcac1bdb839231ea0c2be64a4f0';
const manifestSha256='2d0fc16bad61463ab7a2471e46fcb629d68ab0a40cf7534110d0d701070be6c4';
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
export function verifyReviewedMap(folder){
  const manifest=fs.readFileSync(path.join(folder,'manifest.json'));
  if(digest(manifest)!==manifestSha256)throw Error('Reviewed map manifest changed.');
  const proof=JSON.parse(manifest);
  if(proof.sourceRevision!==sourceRevision||Object.keys(proof.files).length!==11)throw Error('Reviewed map source was not confirmed.');
  for(const [file,expected]of Object.entries(proof.files)){
    if(!/^(?:panels\/[0-9]+(?:-v2)?\.png|properties\.geojson|scene\.json)$/.test(file)||digest(fs.readFileSync(path.join(folder,file)))!==expected)throw Error('Reviewed map asset changed: '+file);
  }
  const scene=JSON.parse(fs.readFileSync(path.join(folder,'scene.json'))),geometry=JSON.parse(fs.readFileSync(path.join(folder,'properties.geojson')));
  if(scene.panels.length!==9||geometry.features.length!==436||new Set(geometry.features.map(f=>f.id)).size!==436)throw Error('Reviewed map count changed.');
  return proof;
}
