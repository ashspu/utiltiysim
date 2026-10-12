// Both the map and selector inspect saved-world premise IDs.
// Commercial IDs and current occupancy come from the owned runtime.
export function createPremisePanel(root,request) {
  const title=document.createElement('h2');title.textContent='Explore a premise';
  const help=document.createElement('p');help.textContent='Choose an actual premise from this saved world. Select a property on the map or choose a premise here to inspect its saved records.';
  const label=document.createElement('label');label.textContent='Premise';label.setAttribute('for','premise-selector');
  const select=document.createElement('select');select.id='premise-selector';
  const inspect=document.createElement('button');inspect.textContent='Inspect premise';
  const more=document.createElement('button');more.textContent='Load more premises';
  const message=document.createElement('p');message.setAttribute('role','status');
  const detail=document.createElement('dl');
  const link=document.createElement('a');link.textContent='Open Virtual Systems records';link.hidden=true;
  root.replaceChildren(title,help,label,select,inspect,more,message,detail,link);
  let world=null,offset=0,total=0,generation=0,busy=false;
  function controls(){select.disabled=inspect.disabled=!world||busy||!select.value;more.disabled=!world||busy;more.hidden=!world||offset>=total;}
  function clear(){generation++;world=null;offset=total=0;busy=false;select.replaceChildren();select.value='';detail.replaceChildren();link.hidden=true;link.removeAttribute?.('href');message.textContent='Open a saved simulation to select a premise.';controls();}
  async function page(){if(!world||busy)return;const selected=world,version=generation;busy=true;controls();try{
    const value=await request('premises',{id:selected.id,offset:String(offset),limit:'50'});
    if(version!==generation)return;
    if(value.worldId!==selected.id||value.sourceRevision!==selected.sourceRevision)throw Error('The selected world premises were not confirmed.');
    total=value.total;offset+=value.premises.length;
    for(const premise of value.premises){const option=document.createElement('option');option.value=premise.premiseId;option.textContent=premise.address?`${premise.address} · ${premise.premiseId}`:premise.premiseId;select.append(option);}
    if(!select.value&&value.premises.length)select.value=value.premises[0].premiseId;
    message.textContent=total?`${offset} of ${total} actual premises loaded.`:'This saved world has no premises.';
  }catch(error){if(version===generation)message.textContent=error.message;}finally{if(version===generation){busy=false;controls();}}}
  async function inspectSelected(){if(!world||busy||!select.value)return;const selected=world,premiseId=select.value,version=generation;busy=true;detail.replaceChildren();link.hidden=true;controls();try{
    const value=await request('premise',{id:selected.id,premiseId});if(version!==generation)return;
    if(value.worldId!==selected.id||value.sourceRevision!==selected.sourceRevision||value.premise?.premiseId!==premiseId)throw Error('The selected premise was not confirmed.');
    for(const [key,label]of [['premiseId','Physical premise'],['address','Address'],['parcelId','Parcel'],['type','Premise type'],['occupied','Occupied']])if(value.premise[key]!==undefined){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=String(value.premise[key]);detail.append(dt,dd);}
    const connected=selected.connectedClock?.configured===true;
    if(connected){link.href='/vs-operator.html?'+new URLSearchParams({id:selected.id,premiseId});link.hidden=false;}
    message.textContent=connected?'Premise confirmed. Virtual Systems resolves its commercial mapping and checks your current access.':'Premise confirmed. This world has no configured Virtual Systems connection.';
  }catch(error){if(version===generation)message.textContent=error.message;}finally{if(version===generation){busy=false;controls();}}}
  inspect.onclick=inspectSelected;more.onclick=page;select.onchange=()=>{detail.replaceChildren();link.hidden=true;};
  clear();return {clear,async selectPremise(id){if(!world||busy)return;let option=[...select.options].find(o=>o.value===id);if(!option){option=document.createElement('option');option.value=id;option.textContent=id;select.append(option);}select.value=id;await inspectSelected();},async load(value){clear();if(!value?.available)return;world=value;await page();}};
}
