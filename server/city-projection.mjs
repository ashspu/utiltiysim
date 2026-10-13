import {inspectSnapshot,UTILITIES} from '../packages/town-viewer/dist/adapter.js';
export const CITY_UPSTREAM_MAX_BYTES=12000000;
export const CITY_PUBLIC_MAX_BYTES=4200000;
const refuse=()=>{throw Object.assign(new Error('Saved city geometry could not be confirmed.'),{status:502});};
// Rebuild every level from physical fields: nested truth or commercial records
// must not escape inside a node, terrain, property or network object.
function scalar(value){if(value===null||typeof value==='boolean'||typeof value==='number'&&Number.isFinite(value)||typeof value==='string'&&value.length<=500)return value;refuse();}
function pick(value,fields){if(!value||typeof value!=='object'||Array.isArray(value))refuse();return Object.fromEntries(fields.filter(k=>value[k]!==undefined).map(k=>[k,scalar(value[k])]));}
const point=value=>pick(value,['x','z','elevationM']);
function list(values,project){if(!Array.isArray(values))refuse();return values.map(project);}
const optionalList=(value,key,project)=>value[key]===undefined?{}:{[key]:list(value[key],project)};
function polygon(value,fields){return {...pick(value,fields),...optionalList(value,'polygon',point)};}
function home(value){return {...pick(value,['id','uid','buildingId','parcelId','address','street','x','z','width','depth','height','angle','side','roofTone','solarKW','solar','occupied','elevationM','premiseType','buildingType','stories','roof','era','districtId','facilityId']),services:pick(value.services,UTILITIES),...(value.connections===undefined?{}:{connections:list(value.connections,scalar)}),...(value.front===undefined?{}:{front:point(value.front)})};}
function network(value){return {...pick(value,['commodity','sourceId','stationId','unit']),...(value.sourceIds===undefined?{}:{sourceIds:list(value.sourceIds,scalar)}),
  nodes:list(value.nodes,n=>pick(n,['id','kind','x','z','label','elevationM','parentEdgeId','facilityId','premiseId','servicePointId','transformerId','mount','subkind','ratingKVA','ratingMVA','primaryKV','secondaryKV','phase','phases','feeder','zone','heightM','overflowElevationM'])),
  edges:list(value.edges,e=>({...pick(e,['id','commodity','from','to','kind','lengthM','placement','tier','enabled','normallyOpen','voltageKV','secondaryVoltageKV','conductor','phase','phases','feeder','feederId','switch','switchId','sizeMm','nominalLabel','diameterIn','material','depthM','pressureTier','corridorId','roadEdge','loop']),points:list(e.points,point)})),
  ...optionalList(value,'equipment',e=>pick(e,['id','kind','nodeId','edgeId','feeder','x','z','elevationM','chainageM','mount','from','to','heightM']))};}
function terrain(value){const map=value.heightmap||value;const heightmap={...pick(map,['cols','rows','cellSizeM','originX','originZ','order','reliefM','synthetic']),values:list(map.values,scalar)};return value.heightmap?{heightmap}:heightmap;}
export function publicCity(value,world){
  if(value?.id!==world.townId||value.count!==world.counts?.premises||!Array.isArray(value.premises))refuse();
  let snapshot;
  try{snapshot={...pick(value,['schemaVersion','generatorVersion','id','topologyRevision','indexRevision','seed','count','homes']),
    bounds:pick(value.bounds,['minX','maxX','minZ','maxZ']),...(value.center===undefined?{}:{center:point(value.center)}),terrain:terrain(value.terrain),
    roads:list(value.roads,r=>({...pick(r,['id','a','b','name','class','roadClass','length','lengthM','rowWidthM','pavementWidthM','origin','corridorId']),points:list(r.points,point)})),
    ...optionalList(value,'parcels',p=>polygon(p,['id','premiseId','areaM2'])),...optionalList(value,'parks',p=>polygon(p,['id','kind','label'])),
    ...optionalList(value,'facilities',p=>polygon(p,['id','kind','label','x','z','elevationM','premiseId','roadId','t','angle','widthM','depthM','heightM'])),
    ...optionalList(value,'poles',p=>pick(p,['id','x','z','elevationM','edgeId','heightM','lamp'])),
    networks:Object.fromEntries(UTILITIES.map(u=>[u,network(value.networks[u])])),premises:value.premises.map(home),source:{utilityOffsets:scalar(value.source?.utilityOffsets),label:world.name}};
    inspectSnapshot(snapshot);
  }catch{refuse();}
  const result={worldId:world.id,sourceRevision:world.sourceRevision,geometry:snapshot};
  if(Buffer.byteLength(JSON.stringify(result))>CITY_PUBLIC_MAX_BYTES)refuse();
  return result;
}
