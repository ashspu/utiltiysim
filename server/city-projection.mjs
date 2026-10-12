import {inspectSnapshot} from '../packages/town-viewer/dist/adapter.js';
const fields=['schemaVersion','generatorVersion','id','topologyRevision','indexRevision','seed','count','homes','bounds','center','terrain','roads','parcels','facilities','parks','networks','poles'];
const homeFields=['id','uid','buildingId','parcelId','address','x','z','width','depth','height','angle','side','roofTone','solarKW','solar','occupied','occupants','services','connections','elevationM','front','premiseType','buildingType','stories','roof','era','districtId','facilityId'];
export function publicCity(value,world){
  const fail=()=>{throw Object.assign(new Error('Saved city geometry could not be confirmed.'),{status:502});};
  if(value?.id!==world.townId||value.count!==world.counts?.premises||!Array.isArray(value.premises))fail();
  const snapshot=Object.fromEntries(fields.filter(k=>value[k]!==undefined).map(k=>[k,value[k]]));
  snapshot.source={utilityOffsets:value.source?.utilityOffsets,label:world.name};
  snapshot.premises=value.premises.map(h=>Object.fromEntries(homeFields.filter(k=>h[k]!==undefined).map(k=>[k,h[k]])));
  try{inspectSnapshot(snapshot);}catch{fail();}
  const result={worldId:world.id,sourceRevision:world.sourceRevision,geometry:snapshot};
  if(Buffer.byteLength(JSON.stringify(result))>4200000)fail();
  return result;
}
