import {fail} from './compute-connector.mjs';
const identifier=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;
export function premiseQuery(url,action) {
  const allowed=action==='premises'?['action','id','offset','limit']:['action','id','premiseId'];
  if([...url.searchParams.keys()].some(key=>!allowed.includes(key)||url.searchParams.getAll(key).length!==1))fail(422,'Use one fixed premise query.');
  if(action==='premise') {const premiseId=url.searchParams.get('premiseId');if(!identifier.test(premiseId||''))fail(422,'Choose an actual premise identifier.');return {premiseId};}
  const offset=url.searchParams.get('offset')||'0',limit=url.searchParams.get('limit')||'50';
  if(!/^\d{1,8}$/.test(offset)||!/^\d{1,2}$/.test(limit)||+limit<1||+limit>50)fail(422,'Invalid premise pagination.');
  return {offset:Number(offset),limit:Number(limit)};
}
function row(value,summary=false) {
  if(!value||typeof value!=='object'||Array.isArray(value)||!identifier.test(value.premiseId||''))fail(502,'The runtime returned an invalid premise.');
  const result={premiseId:value.premiseId};
  for(const key of ['address','parcelId',...(summary?['type']:[])])if(Object.hasOwn(value,key)){
    if(typeof value[key]!=='string'||!value[key].trim()||value[key].length>500||/(?:https?:\/\/|Bearer\s)/i.test(value[key])||key==='parcelId'&&!identifier.test(value[key]))fail(502,'The runtime returned invalid premise details.');result[key]=value[key];
  }
  if(summary&&Object.hasOwn(value,'occupied')){if(typeof value.occupied!=='boolean')fail(502,'Invalid premise occupancy.');result.occupied=value.occupied;}
  return result;
}
export function publicPremises(value,world,query,action) {
  if(!value||value.worldId!==world.id||value.sourceRevision!==world.sourceRevision)fail(502,'The selected world premises were not confirmed.');
  const result={worldId:world.id,sourceRevision:world.sourceRevision};
  if(action==='premise'){result.premise=row(value.premise,true);if(result.premise.premiseId!==query.premiseId)fail(502,'The selected premise was not confirmed.');return result;}
  if(!Number.isSafeInteger(value.total)||value.total<0||value.offset!==query.offset||!Array.isArray(value.premises)||value.premises.length>query.limit||value.premises.length!==Math.min(query.limit,Math.max(0,value.total-query.offset)))fail(502,'The premise page was not confirmed.');
  result.total=value.total;result.offset=query.offset;result.premises=value.premises.map(value=>row(value));
  if(new Set(result.premises.map(value=>value.premiseId)).size!==result.premises.length)fail(502,'Duplicate premise identifiers.');
  return result;
}
