import {readSession} from './shell-session.js';
import {OperatorCommandState,canOperate,safeOperatorId,validateOperatorResponse} from './vs-operator-core.mjs';
const $=id=>document.getElementById(id),make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);return node;};
const args=new URL(location.href).searchParams,worldId=args.get('id'),premiseId=args.get('premiseId');
let session,world,projection,commands,jobId=null,loading=false,mutating=false,job=null,jobKey=null;
const scalar=value=>value===undefined||value===null?'Unavailable':String(value);
const say=text=>{$('message').textContent=text;};
function clearScope(){projection=job=null;jobId=null;for(const id of ['mapping','records','exceptions','job'])$(id).replaceChildren();for(const id of ['exception','contract','account','bill-cycle','invoice-cycle'])$(id).replaceChildren();$('clock').textContent='Unavailable';}
function safeError(error){return{401:'Sign in to view commercial records.',403:'Current commercial permission is required. No new changes are allowed.',404:'This premise or record is unmapped or outside your permitted scope. No commercial records were shown.',409:'The mapping or shared-run boundary could not be confirmed. No change is confirmed.',413:'This premise exceeds the bounded view. No records were silently omitted.'}[error?.status]||'Commercial records could not be confirmed. Preserve any retained request for an exact retry.';}
async function operatorRequest(body){
  const response=await fetch(`/api/operator?id=${worldId}`,{method:'POST',credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(!response.ok){const error=Error('Commercial request unconfirmed');error.status=response.status;throw error;}
  let value;try{value=await response.json();}catch{throw Error('Unconfirmed commercial response');}
  return validateOperatorResponse(value,body);
}
async function compute(action){const response=await fetch(`/api/compute?${new URLSearchParams({action,id:worldId})}`,{cache:'no-store',credentials:'same-origin'});if(!response.ok){const error=Error('Runtime unavailable');error.status=response.status;throw error;}return response.json();}
function options(id,rows,label){const target=$(id);target.replaceChildren();for(const row of rows){if(!safeOperatorId(row.id))continue;const option=make('option',label(row));option.value=row.id;target.append(option);}if(rows.length)target.value=rows[0].id;}
function table(container,title,rows,columns){
  container.append(make('h3',title));if(!rows.length){container.append(make('p','No scoped records reported.'));return;}
  const wrap=make('div'),table=make('table'),head=make('thead'),heading=make('tr'),body=make('tbody');wrap.className='table-wrap';
  for(const [,label] of columns)heading.append(make('th',label));head.append(heading);
  for(const row of rows){const line=make('tr');for(const [key]of columns)line.append(make('td',scalar(row[key])));body.append(line);}table.append(head,body);wrap.append(table);container.append(wrap);
}
function validateProjection(value){
  const collections=['accounts','premises','contracts','installations','reads','bills','invoices','exceptions','cycles','receivables'];
  if(value?.physicalPremiseId!==premiseId||collections.some(key=>!Array.isArray(value[key])||value[key].some(row=>!safeOperatorId(row?.id))))throw Error('Premise scope was not confirmed');
  return value;
}
function renderProjection(value){
  projection=validateProjection(value);$('mapping').replaceChildren();$('records').replaceChildren();$('exceptions').replaceChildren();
  $('mapping').append(make('p',`Physical premise: ${premiseId}`));
  table($('mapping'),'Mapped accounts',value.accounts,[['id','Account ID'],['name','Account name']]);
  table($('mapping'),'Commercial premises',value.premises,[['id','Commercial premise ID'],['address_line1','Address'],['city','City'],['status','Status']]);
  table($('records'),'Contracts',value.contracts,[['id','Contract'],['account_id','Account'],['installation_id','Installation'],['start','Start'],['end','End'],['billing_block','Billing block']]);
  table($('records'),'Installations',value.installations,[['id','Installation'],['meter_id','Meter'],['commodity','Commodity'],['unit','Unit']]);
  table($('records'),'Collected reads',value.reads,[['id','Read'],['installation_id','Installation'],['start','Interval start'],['end','Interval end'],['quantity','Quantity'],['kwh','kWh'],['status','Status']]);
  table($('records'),'Bills',value.bills,[['id','Bill'],['cycle_id','Cycle'],['contract_id','Contract'],['total_minor','Total (minor units)'],['currency','Currency']]);
  table($('records'),'Invoices',value.invoices,[['id','Invoice'],['account_id','Account'],['total_minor','Total (minor units)'],['currency','Currency'],['status','Status'],['posting_status','Posting status']]);
  table($('records'),'Receivables',value.receivables,[['id','Receivable'],['account_id','Account'],['original_minor','Original (minor units)'],['paid_minor','Paid (minor units)'],['written_off_minor','Written off (minor units)'],['open_minor','Open (minor units)'],['currency','Currency'],['status','Status']]);
  table($('exceptions'),'Actual open exceptions',value.exceptions,[['id','Exception'],['code','Code'],['read_id','Read'],['message','Reported reason'],['status','Status']]);
  const held=value.exceptions.filter(exception=>exception.status==='open'&&exception.code==='HIGH_CONSUMPTION'&&value.reads.some(read=>read.id===exception.read_id&&read.status==='held'&&(!read.source_read_id||value.reads.some(source=>source.id===read.source_read_id&&source.status==='accepted'))));
  options('exception',held,row=>`${row.id} · ${row.code}`);options('contract',value.contracts,row=>row.id);options('account',value.accounts,row=>`${row.id} · ${row.name}`);
  for(const id of ['bill-cycle','invoice-cycle'])options(id,value.cycles,row=>`${row.id} · ${row.label} · ${row.start} → ${row.end}`);
  $('note').maxLength=200;controls();
}
function controls(){
  const permitted=canOperate(session,world?.grantTownId)&&session?.user?.id===commands?.actorId,locked=loading||mutating||!commands||commands.locked||!permitted||!projection;
  $('release-fields').disabled=locked||!$('exception').options.length;
  $('bill-fields').disabled=locked||!$('contract').options.length||!$('bill-cycle').options.length;
  $('invoice-fields').disabled=locked||!$('account').options.length||!$('invoice-cycle').options.length;
  $('retry').hidden=!commands?.pending;$('retry').disabled=loading||mutating||!permitted||commands?.pending?.premiseId!==premiseId;
  $('refresh').disabled=loading||mutating;$('refresh-job').disabled=loading||mutating||!jobId;
  $('retry-job').disabled=locked||!jobId||!['failed','interrupted'].includes(job?.status);
}
function renderJob(value,reported=false){
  if(!safeOperatorId(value?.id)||!['billing','invoicing'].includes(value.type)||typeof value.status!=='string')throw Error('Actual job was not confirmed');
  job=reported?value:null;jobId=value.id;$('job').replaceChildren();
  table($('job'),reported?'Actual job status':'Accepted job snapshot',[value],[['id','Job'],['type','Type'],['status','Status'],['stage','Stage'],['processed','Processed'],['total','Total'],['succeeded','Succeeded'],['exceptions','Exceptions'],['failed','Failed']]);
  $('job').append(make('p',reported?'These are reported job counters. They do not by themselves confirm invoices, delivery or settlement.':'This snapshot came with the command receipt. Refresh actual job status to read execution progress; acceptance alone does not confirm processing.'));controls();
}
async function refreshJob(){if(!jobId||loading||mutating)return;loading=true;controls();try{const response=await operatorRequest({action:'job',premiseId,jobId});renderJob(response.result,true);}catch(error){$('job').replaceChildren(make('p',safeError(error)));job=null;}finally{loading=false;controls();}}
async function refresh(){
  if(loading||mutating)return;loading=true;controls();
  try{
    const current=await readSession();if(!current.authenticated||!current.user?.id)throw Object.assign(Error('Sign in'),{status:401});
    if(session&&session.user.id!==current.user.id){clearScope();commands=null;throw Object.assign(Error('Account changed'),{status:401});}
    session=current;world=await compute('status');if(world.id!==worldId)throw Error('World identity unconfirmed');
    try{commands=new OperatorCommandState({actorId:session.user.id,worldId,premiseId,storage:localStorage,request:operatorRequest});}catch{commands=null;}
    const value=await operatorRequest({action:'premise',premiseId});renderProjection(value.result);
    try{const context=await compute('connected');$('clock').textContent=`Reported phase: ${scalar(context.phase)} · Virtual Systems UTC clock: ${scalar(context.clock)} · next physical day: ${scalar(context.physicalThrough)}`;}catch{$('clock').textContent='Shared clock status unavailable.';}
    jobKey=`utilitysim:operator-job:v1:${encodeURIComponent(session.user.id)}:${worldId}:${premiseId}`;
    const confirmed=commands?.lastReceipt;
    if(confirmed?.request.premiseId===premiseId&&safeOperatorId(confirmed.response.result.id))jobId=confirmed.response.result.id;
    else try{const retained=localStorage.getItem(jobKey);if(safeOperatorId(retained))jobId=retained;}catch{}
    if(commands?.pending){say(commands.pending.premiseId===premiseId?'An earlier operator request needs exact retry confirmation. New changes are blocked.':'An operator request for another premise is retained. Open its original premise before retrying.');if(commands.pending.premiseId!==premiseId){const link=make('a','Open original premise');link.href=`/vs-operator.html?${new URLSearchParams({id:worldId,premiseId:commands.pending.premiseId})}`;$('message').append(link);}}
    else say(!commands?'Command recovery storage is unavailable. Records remain read-only.':canOperate(session,world.grantTownId)?'Actual scoped commercial records loaded.':'Read-only commercial records loaded. Current billing permission is required for changes.');
  }catch(error){projection=null;$('mapping').replaceChildren(make('p',safeError(error)));$('records').replaceChildren();$('exceptions').replaceChildren();for(const id of ['exception','contract','account','bill-cycle','invoice-cycle'])$(id).replaceChildren();say(safeError(error));}
  finally{loading=false;controls();}
  if(jobId)await refreshJob();
}
async function mutate(action,fields){
  if(loading||mutating||!commands)return;const state=commands;mutating=true;controls();
  try{const current=await readSession();session=current;if(current.user?.id!==state.actorId){clearScope();commands=null;throw Object.assign(Error('Account changed'),{status:403});}if(!canOperate(current,world?.grantTownId))throw Object.assign(Error('Permission changed'),{status:403});
    const receipt=action==='retry'?await state.retry():await state.execute(action,fields);
    if(receipt.result.status==='resolved')say('The read review was confirmed. Refresh the actual records to inspect its effect.');
    else{renderJob(receipt.result);say('The request identity was confirmed. A queued job is not completed billing, invoicing or settlement.');try{localStorage.setItem(jobKey,jobId);}catch{}}
  }catch(error){say(state.pending?'The operator request is unconfirmed. Its original identity is retained; retry it before another change.':safeError(error));}
  finally{mutating=false;controls();}
}
$('refresh').onclick=refresh;$('retry').onclick=()=>mutate('retry');$('refresh-job').onclick=refreshJob;$('retry-job').onclick=()=>mutate('retry-job',{jobId});
$('release-form').onsubmit=event=>{event.preventDefault();if(!$('release-fields').disabled)return mutate('release-read',{exceptionId:$('exception').value,note:$('note').value.trim()});};
$('bill-form').onsubmit=event=>{event.preventDefault();if(!$('bill-fields').disabled)return mutate('bill',{cycleId:$('bill-cycle').value,contractId:$('contract').value});};
$('invoice-form').onsubmit=event=>{event.preventDefault();if(!$('invoice-fields').disabled)return mutate('invoice',{cycleId:$('invoice-cycle').value,accountId:$('account').value});};
if(!/^[0-9a-f]{32}$/.test(worldId||'')||!safeOperatorId(premiseId)||[...args.keys()].some(key=>!['id','premiseId'].includes(key))||args.getAll('id').length!==1||args.getAll('premiseId').length!==1){say('Choose an actual premise from your saved physical world.');controls();}
else{$('world-link').href=`/world-control.html?id=${worldId}`;await refresh();}
