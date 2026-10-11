import {fail} from './compute-connector.mjs';
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const id=/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/;
export const actions=Object.freeze({premise:[],job:['jobId'],'release-read':['commandId','exceptionId','note'],bill:['commandId','cycleId','contractId'],invoice:['commandId','cycleId','accountId'],'retry-job':['commandId','jobId']});
export const readAction=action=>['premise','job'].includes(action);
export function validateOperatorRequest(value) {
 if(!value||typeof value!=='object'||Array.isArray(value)||!Object.hasOwn(actions,value.action||''))fail(422,'Choose a supported commercial action.');
 const expected=['action','premiseId',...actions[value.action]];
 if(Object.keys(value).length!==expected.length||Object.keys(value).some(key=>!expected.includes(key))||!id.test(value.premiseId||''))fail(422,'Use only the exact scoped commercial request fields.');
 for(const key of actions[value.action])if(key==='note'?typeof value.note!=='string'||!value.note.trim()||value.note.length>200:key==='commandId'?!uuid.test(value[key]||''):!id.test(value[key]||''))fail(422,'Provide valid commercial identifiers and a bounded review note.');
 return structuredClone(value);
}
const fields={
 accounts:['id','name'],premises:['id','address_line1','address_line2','city','region','postal_code','country','premise_type','status'],
 contracts:['id','account_id','installation_id','tariff_id','start','end','bill_cycle_id','billing_block','move_in_reading'],
 installations:['id','premise_id','meter_id','commodity','unit','source_installation_id','derivation_factor'],
 reads:['id','source_id','installation_id','start','end','kwh','quantity','commodity','unit','status','source_read_id'],
 bills:['id','cycle_id','contract_id','account_id','tariff_id','kwh','quantity','commodity','unit','energy_minor','fixed_minor','total_minor','currency','service_start','service_end','service_days','period_days','kind','created_at'],
 invoices:['id','cycle_id','account_id','total_minor','currency','status','posting_status','issue_date','due_date','created_at'],
 exceptions:['id','code','subject','cycle_id','read_id','message','status','resolution','created_at','resolved_at','job_id'],
 cycles:['id','label','start','end','status','bill_cycle_id','kind','contract_id'],
 receivables:['id','invoice_id','account_id','cycle_id','currency','original_minor','paid_minor','written_off_minor','open_minor','status','issue_date','due_date']
};
const jobFields=['id','type','cycle_id','status','stage','total','processed','succeeded','skipped','exceptions','failed','requested_at','started_at','completed_at','updated_at','parent_job_id','elapsed_seconds'];
function object(value){if(!value||typeof value!=='object'||Array.isArray(value))fail(502,'Invalid commercial response.');}
function project(value,allowed){object(value);const result={};for(const key of allowed)if(Object.hasOwn(value,key)){const item=value[key];if(item!==null&&!(typeof item==='string'&&item.length<=2000&&!/(?:https?:\/\/|Bearer\s)/i.test(item)||typeof item==='number'&&Number.isFinite(item)||typeof item==='boolean'))fail(502,'Invalid commercial field.');result[key]=item;}if(!id.test(result.id||''))fail(502,'Invalid commercial record identifier.');return result;}
function rows(value,allowed){if(!Array.isArray(value)||value.length>200)fail(502,'Commercial collection exceeds its bound.');const result=value.map(row=>project(row,allowed));if(new Set(result.map(row=>row.id)).size!==result.length)fail(502,'Duplicate commercial record.');return result;}
function requireRelation(value,known){if(!known.has(value))fail(502,'Commercial response contains a foreign record.');}
function premiseResult(value,premiseId){object(value);if(value.physicalPremiseId!==premiseId||Object.keys(value).some(key=>!['physicalPremiseId',...Object.keys(fields)].includes(key)))fail(502,'Commercial premise was not confirmed.');const result={physicalPremiseId:premiseId};for(const [table,allowed]of Object.entries(fields))result[table]=rows(value[table],allowed);
 if(!result.accounts.length||!result.premises.length||!result.contracts.length||!result.installations.length)fail(502,'Commercial premise mapping was not confirmed.');
 const sets=Object.fromEntries(Object.entries(fields).map(([table])=>[table,new Set(result[table].map(row=>row.id))]));
 for(const row of result.contracts){requireRelation(row.account_id,sets.accounts);requireRelation(row.installation_id,sets.installations);}
 for(const row of result.installations)requireRelation(row.premise_id,sets.premises);
 for(const row of result.reads)requireRelation(row.installation_id,sets.installations);
 for(const row of result.bills){requireRelation(row.account_id,sets.accounts);requireRelation(row.contract_id,sets.contracts);if(result.contracts.find(contract=>contract.id===row.contract_id).account_id!==row.account_id)fail(502,'Commercial bill account does not match its contract.');}
 for(const row of [...result.invoices,...result.receivables])requireRelation(row.account_id,sets.accounts);
 for(const row of result.exceptions)if(row.read_id!=null)requireRelation(row.read_id,sets.reads);else if(!sets.contracts.has(row.subject)&&!sets.installations.has(row.subject))fail(502,'Commercial exception is outside this premise.');
 return result;
}
function jobResult(value){object(value);const result=project(value,jobFields);if(!['billing','invoicing'].includes(result.type)||!['queued','running','completed','completed_with_exceptions','failed','interrupted'].includes(result.status))fail(502,'Commercial job was not confirmed.');for(const field of ['total','processed','succeeded','skipped','exceptions','failed'])if(Object.hasOwn(result,field)&&(!Number.isSafeInteger(result[field])||result[field]<0))fail(502,'Invalid commercial job progress.');return result;}
export function publicOperatorResponse(value,request,marker){object(value);if(value.schemaVersion!=='connected-operator-response/1'||value.runId!==marker.runId||value.controllerId!==marker.controllerId||value.premiseId!==request.premiseId||value.action!==request.action||value.commandId!==(request.commandId??null))fail(502,'The selected commercial action was not confirmed.');let result;if(request.action==='premise')result=premiseResult(value.result,request.premiseId);else if(request.action==='release-read'){object(value.result);if(value.result.status!=='resolved'||value.result.replayed!==undefined&&typeof value.result.replayed!=='boolean')fail(502,'Reading review was not confirmed.');result={status:'resolved',...(value.result.replayed!==undefined?{replayed:value.result.replayed}:{})};}else {result=jobResult(value.result);if(request.action==='job'&&result.id!==request.jobId)fail(502,'The selected commercial job was not confirmed.');}
 if(['bill','invoice'].includes(request.action)&&(result.type!==(request.action==='bill'?'billing':'invoicing')||result.cycle_id!==request.cycleId))fail(502,'The requested scoped commercial job was not confirmed.');
 const response={schemaVersion:value.schemaVersion,runId:marker.runId,controllerId:marker.controllerId,premiseId:request.premiseId,action:request.action,commandId:request.commandId??null,result};if(Buffer.byteLength(JSON.stringify(response))>2000000)fail(502,'Commercial response exceeds its size bound.');return response;
}
