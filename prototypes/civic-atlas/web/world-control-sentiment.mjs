import { addDays } from './world-control-core.mjs';
export const commandPanelsLocked=(...panels)=>panels.some(panel=>panel.locked);
export class NewsCommandState {
  constructor(account,world,storage){if(!account)throw new Error('Sign in to retain news commands.');this.key=`utilitysim:news:${account}:${world}`;this.storage=storage;this.pending=JSON.parse(storage.getItem(this.key)||'null');this.busy=false;}
  get locked(){return this.busy||!!this.pending;}
  async send(command,request){
    if(this.busy)throw new Error('A news command is already being sent.');
    if(!this.pending){this.storage.setItem(this.key,JSON.stringify(command));this.pending=structuredClone(command);}
    this.busy=true;
    try{const receipt=await request(this.pending);this.storage.removeItem(this.key);this.pending=null;return receipt;}
    catch(error){if(error.rejected){this.storage.removeItem(this.key);this.pending=null;}throw error;}
    finally{this.busy=false;}
  }
}
const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
export function createSentimentPanel(container,request,changed,accountPromise){
  let world,record,state,busy=false,clockBusy=false,dateCursor,newsCursor;
  const notice=make('p');notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
  const summary=make('p'),form=make('form'),fields=make('fieldset');fields.append(make('legend','Schedule public confidence news'));
  const inputs={};
  function input(name,title,type,value,min,max){const label=make('label',title),node=make('input');node.id=`news-${name}`;label.htmlFor=node.id;node.type=type;node.value=value;node.required=true;if(min!==undefined)node.min=min;if(max!==undefined)node.max=max;if(type==='number')node.step='any';fields.append(label,node);inputs[name]=node;}
  input('date','Event UTC date','date','');input('change','Confidence change (−100 to +100 points)','number',-10,-100,100);input('headline','Scenario headline','text','');input('reason','Schedule or cancellation reason','text','');
  inputs.headline.maxLength=512;inputs.reason.maxLength=512;
  const submit=make('button','Schedule news');submit.type='submit';fields.append(submit);form.append(fields);
  const retry=make('button','Retry retained news command'),refresh=make('button','Latest confidence history'),olderDays=make('button','Older confidence days'),olderNews=make('button','Older news');
  const news=make('div'),history=make('div');
  function controls(){fields.disabled=clockBusy||busy||state?.locked||!record?.enabled||!state;retry.hidden=!state?.pending;retry.disabled=clockBusy||busy;refresh.disabled=clockBusy||busy||!!state?.pending;olderDays.disabled=refresh.disabled||!record?.nextBefore;olderNews.disabled=refresh.disabled||!record?.nextNewsBefore;container.querySelectorAll('[data-news-cancel]').forEach(button=>button.disabled=fields.disabled);}
  function mount(){container.replaceChildren(notice,summary,make('p','Manually entered scenario news changes community confidence; this is not a live news feed. Contact amplification requires separately enabled customer contacts and a real experienced service symptom.'),form,retry,refresh,make('h3','Scheduled and historical news'),news,olderNews,make('h3','Daily confidence history'),history,olderDays);}
  async function inspect(){
    const next=await request('sentiment',{id:world.id,limit:'25',...(dateCursor?{before:dateCursor}:{}),...(newsCursor?{newsBefore:String(newsCursor)}:{})});
    if(next.worldInstanceId!==world.id)throw new Error('The confidence adapter returned another instance.');record=next;
    summary.textContent=next.enabled?`Community confidence: ${next.communityTrust??'unavailable'} · household confidence: ${next.householdTrust??'unavailable'}.`:'Sentiment was not enabled in this world’s starting settings. Inspection does not activate it.';
    inputs.date.min=next.through;inputs.date.max=addDays(next.through,3650);if(!inputs.date.value||inputs.date.value<next.through)inputs.date.value=next.through;
    news.replaceChildren();history.replaceChildren();
    for(const item of next.news||[]){const article=make('article');const phase=item.cancelled?'Cancelled':item.applied?'Applied':'Scheduled';article.append(make('h4',`${phase} · ${item.day} · ${item.headline}`),make('p',`${item.change>0?'+':''}${item.change} confidence points`));
      if(!item.cancelled&&!item.applied&&item.day>=next.through){const cancel=make('button','Cancel before processing');cancel.dataset.newsCancel=item.id;cancel.onclick=()=>{try{send({...base('cancel'),newsId:item.id});}catch(error){notice.textContent=error.message;}};article.append(cancel);}news.append(article);}
    if(!(next.news||[]).length)news.append(make('p','No news records on this page.'));
    for(const item of next.history||[]){const details=make('details');details.append(make('summary',item.day),make('pre',JSON.stringify(item,null,2)));history.append(details);}
    if(!(next.history||[]).length)history.append(make('p','No confidence days recorded on this page.'));
    controls();
  }
  function base(action){if(!inputs.reason.value.trim()){inputs.reason.focus();throw new Error('Enter a reason before recording a news command.');}return{commandId:crypto.randomUUID(),expectedRevision:record.revision,effectiveDate:record.through,action,reason:inputs.reason.value.trim(),causalReference:'hosted-confidence-controls'};}
  async function send(command){if(busy||clockBusy||!state)return;busy=true;controls();changed();
    try{await state.send(command,payload=>request('sentiment',{id:world.id},payload));dateCursor=newsCursor=null;await inspect();notice.textContent='News command recorded. Scheduled effects apply only when physical time advances.';}
    catch(error){notice.textContent=`${error.message}${state.pending?' Outcome uncertain; retry the retained exact command before advancing.':' Refresh history before another edit.'}`;}
    finally{busy=false;controls();changed();}}
  form.onsubmit=event=>{event.preventDefault();try{send({...base('schedule'),eventDate:inputs.date.value,trustChange:Number(inputs.change.value),headline:inputs.headline.value.trim()});}catch(error){notice.textContent=error.message;}};
  retry.onclick=()=>send();
  async function page(kind){if(busy||clockBusy||state?.pending)return;busy=true;controls();changed();try{if(kind==='date')dateCursor=record.nextBefore;else if(kind==='news')newsCursor=record.nextNewsBefore;else dateCursor=newsCursor=null;await inspect();}catch(error){notice.textContent=error.message;}finally{busy=false;controls();changed();}}
  refresh.onclick=()=>page('latest');olderDays.onclick=()=>page('date');olderNews.onclick=()=>page('news');
  return{get locked(){return busy||!!state?.locked;},get busy(){return busy;},setClockBusy(value){clockBusy=value;controls();},clear(){world=record=state=null;dateCursor=newsCursor=null;inputs.date.value='';summary.textContent='';news.replaceChildren();history.replaceChildren();container.replaceChildren(make('p','Open a saved world to inspect confidence history.'));},async load(value){world=value;record=null;dateCursor=newsCursor=null;mount();try{state=new NewsCommandState(await accountPromise,value.id,sessionStorage);await inspect();notice.textContent=state.pending?'A retained news command needs an exact retry before advancing.':'Review the date and confidence effect before scheduling.';}catch(error){notice.textContent=`Confidence controls unavailable: ${error.message}`;}controls();changed();}};
}
