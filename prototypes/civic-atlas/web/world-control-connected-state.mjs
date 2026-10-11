const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ACTIONS=['pause','resume','advance'];
const clone=value=>value===null?null:structuredClone(value);
const revision=value=>Number.isSafeInteger(value)&&value>=0;
const instant=value=>typeof value==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)&&Number.isFinite(Date.parse(value))&&new Date(value).toISOString().slice(0,19)+'Z'===value;
function command(value) {
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!['commandId','expectedRevision','action','through'].includes(key))||!UUID.test(value.commandId||'')||!revision(value.expectedRevision)||!ACTIONS.includes(value.action)||(value.action==='advance'?!instant(value.through):Object.hasOwn(value,'through')))throw new Error('Invalid retained connected command.');
  return Object.freeze({commandId:value.commandId,expectedRevision:value.expectedRevision,action:value.action,...(value.action==='advance'?{through:value.through}:{})});
}
function receipt(value,expected) {
  if(!value||typeof value!=='object'||Array.isArray(value)||!UUID.test(value.commandId||'')||(expected&&value.commandId!==expected.commandId)||!['accepted','completed'].includes(value.status)||!revision(value.revision)||value.revision<1||(expected&&value.revision!==expected.expectedRevision+1))throw new Error('The controller did not confirm this command. Retry its retained identity.');
  return Object.freeze({commandId:value.commandId,status:value.status,revision:value.revision});
}
// Receipt acceptance is durable transport confirmation. Execution/progress comes
// independently from GET status; an accepted advance must still permit pause.
export class ConnectedCommandController {
  constructor({storage,request,actorId,worldId,uuid=()=>globalThis.crypto.randomUUID()}) {
    if(!storage||typeof storage.getItem!=='function'||typeof storage.setItem!=='function'||typeof request!=='function'||typeof uuid!=='function'||typeof actorId!=='string'||!actorId||actorId.length>200||!/^[0-9a-f]{32}$/.test(worldId||''))throw new Error('Connected command state requires an account, world, storage and request function.');
    this.storage=storage;this.request=request;this.worldId=worldId;this.uuid=uuid;
    this.key=`utilitysim:connected-command:v1:${encodeURIComponent(actorId)}:${worldId}`;
    this.busy=false;this.state=this.read();this.restored=Boolean(this.state.pending);
  }
  read() {
    let raw;try{raw=this.storage.getItem(this.key);}catch{throw new Error('Cannot read retained connected commands. Restore browser storage before sending.');}
    if(raw===null)return {pending:null,lastReceipt:null};
    try{const value=JSON.parse(raw);if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(key=>!['pending','lastReceipt'].includes(key)))throw new Error();return {pending:value.pending===null?null:command(value.pending),lastReceipt:value.lastReceipt===null?null:receipt(value.lastReceipt)};}catch{throw new Error('Retained connected command state could not be verified. Preserve it for recovery.');}
  }
  save(state) {
    try{this.storage.setItem(this.key,JSON.stringify(state));}catch{throw new Error('Cannot durably retain connected command state. Restore browser storage and preserve the original request for retry.');}
    this.state=state;
  }
  get pending(){return clone(this.state.pending);}
  get lastReceipt(){return clone(this.state.lastReceipt);}
  // GET status is observational: changed clocks/revisions never release a lost
  // command identity. Recovered returns retained state without mutating it.
  recovered(){return this.pending;}
  settle(value,lastReceipt) {
    const current=this.read();
    // Another page may have retried this identity and then sent a new command
    // while our original reply was delayed. Never erase its retained request.
    if(current.pending?.commandId===value.commandId)this.save({pending:null,lastReceipt});
    else this.state=current;
  }
  async execute(action,expectedRevision,through) {
    if(this.busy)throw new Error('A connected command is already being sent.');
    this.state=this.read();
    if(this.state.pending)throw new Error('Retry the retained connected command before sending another.');
    const value=command({commandId:this.uuid(),expectedRevision,action,...(through!==undefined?{through}:{})});
    this.save({pending:value,lastReceipt:this.state.lastReceipt});
    return this.send(value);
  }
  async retry() {
    if(this.busy)throw new Error('A connected command is already being sent.');
    this.state=this.read();if(!this.state.pending)throw new Error('No retained connected command to retry.');
    return this.send(this.state.pending);
  }
  async send(value) {
    this.busy=true;
    try {
      const result=receipt(await this.request('connected-command',{id:this.worldId},value),value);
      this.settle(value,result);this.restored=false;return clone(result);
    }catch(error){
      // Only an explicitly trusted definitive server rejection releases identity.
      // Timeouts, network failures, invalid receipts and 5xx remain uncertain.
      if(error?.rejected===true&&Number.isInteger(error.status)&&error.status>=400&&error.status<500)this.settle(value,this.state.lastReceipt);
      throw error;
    }finally{this.busy=false;}
  }
}
