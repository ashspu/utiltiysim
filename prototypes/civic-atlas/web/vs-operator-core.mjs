const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
export const safeOperatorId=value=>typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/.test(value);
const required={ 'release-read':['exceptionId','note'],bill:['cycleId','contractId'],invoice:['cycleId','accountId'],'retry-job':['jobId'] };
function validateCommand(body){
  const fields=required[body?.action];
  if(!fields||!UUID.test(body.commandId||'')||!safeOperatorId(body.premiseId)||Object.keys(body).some(key=>!['action','commandId','premiseId',...fields].includes(key)))throw Error('The retained operator command could not be verified. Preserve it for recovery.');
  for(const field of fields)if(field==='note'?(typeof body[field]!=='string'||!body[field].trim()||body[field].length>200):!safeOperatorId(body[field]))throw Error('Choose actual scoped records and enter a review note of at most 200 characters.');
  return Object.freeze(structuredClone(body));
}
export function validateOperatorResponse(value,body){
  if(!value||value.schemaVersion!=='connected-operator-response/1'||value.premiseId!==body.premiseId||value.action!==body.action||value.commandId!==(body.commandId??null)||typeof value.runId!=='string'||typeof value.controllerId!=='string'||!value.result||typeof value.result!=='object'||Array.isArray(value.result))throw Error('The operator service did not confirm this request. Preserve its identity and retry.');
  return value;
}
export const canOperate=(session,town)=>session?.authenticated===true&&(session.grants||[]).some(grant=>['owner','billing'].includes(grant.role)&&[town,'*'].includes(grant.town));
export class OperatorCommandState{
  constructor({actorId,worldId,premiseId,storage,request,uuid=()=>crypto.randomUUID()}){
    if(typeof actorId!=='string'||!actorId||!/^[0-9a-f]{32}$/.test(worldId||'')||!safeOperatorId(premiseId))throw Error('A signed-in account and an actual world premise are required.');
    this.actorId=actorId;this.worldId=worldId;this.premiseId=premiseId;this.storage=storage;this.request=request;this.uuid=uuid;this.key=`utilitysim:operator-command:v1:${encodeURIComponent(actorId)}:${worldId}`;this.receiptKey=`${this.key}:receipt:${encodeURIComponent(premiseId)}`;this.busy=false;this.pending=this.read();this.lastReceipt=this.readReceipt();
  }
  read(){let raw;try{raw=this.storage.getItem(this.key);}catch{throw Error('Retained operator commands are unavailable. Restore browser storage before making changes.');}if(raw===null)return null;try{return validateCommand(JSON.parse(raw));}catch{throw Error('The retained operator command could not be verified. Preserve it for recovery.');}}
  readReceipt(){const raw=this.storage.getItem(this.receiptKey);if(raw===null)return null;try{const saved=JSON.parse(raw);validateCommand(saved.request);if(saved.request.premiseId!==this.premiseId)throw Error('Premise mismatch');validateOperatorResponse(saved.response,saved.request);return saved;}catch{throw Error('The accepted operator receipt could not be verified. Preserve it for recovery.');}}
  get locked(){return this.busy||!!this.pending;}
  async execute(action,fields){
    if(this.busy)throw Error('An operator request is already being sent.');this.pending=this.read();if(this.pending)throw Error('Confirm the retained operator command before making another change.');
    if(!required[action]||!fields||Object.keys(fields).some(key=>!required[action].includes(key)))throw Error('Use only the supported fields for this operator action.');
    const body=validateCommand({action,premiseId:this.premiseId,commandId:this.uuid(),...fields});
    this.storage.setItem(this.key,JSON.stringify(body));this.pending=body;return this.send(body);
  }
  async retry(){if(this.busy)throw Error('An operator request is already being sent.');this.pending=this.read();if(!this.pending)throw Error('No retained operator request is available.');if(this.pending.premiseId!==this.premiseId)throw Error('Open the original premise to confirm its retained command.');return this.send(this.pending);}
  async send(body){this.busy=true;try{const receipt=validateOperatorResponse(await this.request(body),body);const current=this.read();if(current?.commandId===body.commandId){
    const saved={request:body,response:receipt};
    // Persist the accepted job reference before releasing the original identity.
    // If this write or removal fails, its exact request remains recoverable.
    this.storage.setItem(this.receiptKey,JSON.stringify(saved));this.lastReceipt=structuredClone(saved);
    this.storage.removeItem(this.key);this.pending=null;
  }else this.pending=current;return receipt;}finally{this.busy=false;}}
}
