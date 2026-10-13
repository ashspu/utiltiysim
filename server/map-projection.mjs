export function publicMapBindings(value, world) {
  if(value?.worldInstanceId!==world.id||value.sourceRevision!==world.sourceRevision||!Array.isArray(value.premises)||value.premises.length!==world.counts?.premises||value.premises.length>10000)throw Object.assign(new Error('Saved map bindings were not confirmed.'),{status:502});
  const parcels=new Set(),premises=new Set();
  const rows=value.premises.map(row=>{
    if(!row||![row.parcelId,row.premiseId].every(id=>typeof id==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/.test(id))||parcels.has(row.parcelId)||premises.has(row.premiseId))throw Object.assign(new Error('Saved map bindings were not confirmed.'),{status:502});
    parcels.add(row.parcelId);premises.add(row.premiseId);return {parcelId:row.parcelId,premiseId:row.premiseId};
  });
  return {worldId:world.id,sourceRevision:world.sourceRevision,premises:rows};
}
