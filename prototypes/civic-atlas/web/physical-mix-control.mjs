const clean=value=>Math.round(value*1e10)/1e10;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
export function validMix(values,total=100){return Array.isArray(values)&&values.length===3&&values.every(value=>Number.isFinite(value)&&value>=0&&value<=total)&&Math.abs(values.reduce((sum,value)=>sum+value,0)-total)<1e-8;}
export function moveMixHandle(values,handle,position,total=100){
  if(!validMix(values,total)||![0,1].includes(handle)||!Number.isFinite(position))throw Error('Use a valid three-part distribution.');
  let first=values[0],second=values[0]+values[1];if(handle===0)first=clamp(position,0,second);else second=clamp(position,first,total);
  return[clean(first),clean(second-first),clean(total-second)];
}
export function setMixShare(values,index,next,total=100){
  if(!validMix(values,total)||![0,1,2].includes(index)||!Number.isFinite(next)||next<0||next>total)throw Error('Enter a share from 0 to 100.');
  const result=[...values],neighbor=index===0?1:index===1?2:1,remaining=3-index-neighbor;
  const difference=next-result[index];result[index]=next;result[neighbor]-=difference;
  if(result[neighbor]<0){result[remaining]+=result[neighbor];result[neighbor]=0;}else if(result[neighbor]>total-next){result[remaining]+=result[neighbor]-(total-next);result[neighbor]=total-next;}
  result[remaining]=clamp(total-result[index]-result[neighbor],0,total);return result;
}
let sequence=0;
export function createPhysicalMix(container,{labels=['AMI','AMR','Manual'],values=[80,15,5],onChange,total=100}={}){
  let current=[...values],invalid=null;const id=`physical-mix-${++sequence}`;
  const make=(tag,text)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;return node;};
  const block=make('div');block.className='physical-mix';const track=make('div');track.className='physical-mix-track';
  const segments=labels.map((label,index)=>{const segment=make('span');segment.className=`mix-segment mix-${index}`;track.append(segment);return segment;});
  const handles=[0,1].map(index=>{const node=make('input');node.type='range';node.min=0;node.max=total;node.step=.1;node.className=`mix-handle mix-handle-${index}`;node.setAttribute('aria-label',`${labels[index]} boundary`);node.oninput=()=>change(moveMixHandle(current,index,Number(node.value),total));track.append(node);return node;});
  const exact=make('div');exact.className='physical-mix-exact';
  const inputs=labels.map((label,index)=>{const wrapper=make('label',label),input=make('input');input.type='number';input.min=0;input.max=total;input.step='any';input.required=true;input.id=`${id}-${index}`;wrapper.htmlFor=input.id;wrapper.append(input,make('span','%'));exact.append(wrapper);input.oninput=()=>{try{if(input.value==='')throw Error();change(setMixShare(current,index,Number(input.value),total));}catch{invalid=index;input.setAttribute('aria-invalid','true');notice.textContent='Enter a share between 0 and 100. The last valid total remains 100%.';onChange?.([...current],false);}};return input;});
  const notice=make('p');notice.className='physical-mix-note';notice.setAttribute('role','status');
  block.append(track,exact,notice,make('p','Move either boundary, or type an exact share. Editing one share adjusts its neighbouring segment so the total stays 100%.'));container.append(block);
  function update(){
    if(!validMix(current,total)){notice.textContent='This saved mix does not total 100%. Its values are preserved; restore defaults to use the combined control.';handles.forEach(handle=>handle.disabled=true);inputs.forEach(input=>input.disabled=true);return;}
    segments.forEach((segment,index)=>{segment.style.width=`${current[index]/total*100}%`;segment.title=`${labels[index]} ${current[index]}%`;});
    const points=[current[0],current[0]+current[1]];handles.forEach((handle,index)=>{handle.min=0;handle.max=total;handle.step=Math.abs(points[index]*10-Math.round(points[index]*10))<1e-8?.1:'any';handle.value=points[index];handle.disabled=false;handle.setAttribute('aria-valuemin',String(index===0?0:points[0]));handle.setAttribute('aria-valuemax',String(index===0?points[1]:total));handle.setAttribute('aria-valuetext',`${labels[0]} ${current[0]}%, ${labels[1]} ${current[1]}%, ${labels[2]} ${current[2]}%`);});
    inputs.forEach((input,index)=>{input.disabled=false;input.value=current[index];input.setAttribute('aria-invalid','false');});notice.textContent=`Total ${total}%`;
  }
  function change(next){current=next;invalid=null;update();onChange?.([...current],true);}
  update();return{setValues(next){current=[...next];if(invalid===null)update();},reset(next){invalid=null;current=[...next];update();},validate(){return invalid!==null?['Complete the exact meter share.']:validMix(current,total)?[]:['Meter shares must total 100%.'];},get values(){return [...current];}};
}
