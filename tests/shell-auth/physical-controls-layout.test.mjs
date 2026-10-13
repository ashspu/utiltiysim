import test from 'node:test';import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {moveMixHandle,setMixShare,validMix} from '../../prototypes/civic-atlas/web/physical-mix-control.mjs';
import {renderPhysicalSliderForm,formatPhysicalUnit,humanSettingLabel,configurationFormSchema,physicalFields} from '../../prototypes/civic-atlas/web/physical-slider-form.mjs';
test('combined handles preserve a total of 100 at crossings, fractional values and all-or-nothing edges',()=>{
  for(const start of [[80,15,5],[100,0,0],[0,100,0],[0,0,100],[33.3333333333,33.3333333333,33.3333333334]])for(const handle of [0,1])for(const next of [-10,0,.125,50,100,130]){const actual=moveMixHandle(start,handle,next);assert.equal(validMix(actual),true);assert.ok(actual.every(value=>value>=0));}
  assert.deepEqual(moveMixHandle([80,15,5],0,100),[95,0,5]);assert.deepEqual(moveMixHandle([80,15,5],1,0),[80,0,20]);
});
test('exact mix edits preserve requested precision, conserve shares and handle zero/100 transitions',()=>{
  const precise=.123456789012345;assert.equal(setMixShare([80,15,5],0,precise)[0],precise);
  let values=[80,15,5];for(let step=0;step<1000;step++){const index=step%3,next=((step*731)%10000)/100;values=setMixShare(values,index,next);assert.equal(values[index],next);assert.equal(validMix(values),true);}
  assert.deepEqual(setMixShare([80,15,5],2,100),[0,0,100]);assert.deepEqual(setMixShare([0,0,100],0,100),[100,0,0]);
  assert.throws(()=>setMixShare(values,1,NaN));assert.throws(()=>setMixShare(values,1,101));
});
class Node{constructor(tag){this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.value='';this.classList={add:()=>{}};this.style={setProperty:()=>{}};}append(...nodes){for(const node of nodes){if(node.parent)node.parent.children=node.parent.children.filter(child=>child!==node);node.parent=this;this.children.push(node);}}replaceChildren(...nodes){this.children=[];this.append(...nodes);}setAttribute(key,value){this.attributes[key]=value;}all(fn){return[...(fn(this)?[this]:[]),...this.children.flatMap(child=>child.all(fn))];}}
test('group layout keeps saved numeric precision/types, exposes header toggles without enabling and restores combined mix',()=>{
  globalThis.document={createElement:tag=>new Node(tag)};
  const mixField={type:'number',minimum:0,maximum:100};
  const configuration={schemas:{world:{type:'object',properties:{weather:{type:'object',title:'Daily weather',properties:{winter_mean_c:{type:'number',default:2,'x-unit':'°C'}}}}},physical:{type:'object',properties:{meterChannels:{type:'object',title:'Meter technology','x-control':{kind:'linked-percentages',fields:['amiPercent','amrPercent','manualPercent'],total:100},properties:{enabled:{type:'boolean',default:false},amiPercent:{...mixField,default:80},amrPercent:{...mixField,default:15},manualPercent:{...mixField,default:5}}}}}},defaults:{schemaVersion:'physical-setup/4',world:{weather:{winter_mean_c:2}},physical:{meterChannels:{enabled:false,amiPercent:80,amrPercent:15,manualPercent:5}}}};
  const saved=structuredClone(configuration.defaults);saved.world.weather.winter_mean_c=-37.12345;let changes=0;const root=new Node('div');
  const schema=configurationFormSchema(configuration,saved),form=renderPhysicalSliderForm(root,schema,{values:saved,defaults:configuration.defaults,onChange:()=>changes++});
  assert.equal(form.values.world.weather.winter_mean_c,-37.12345);assert.equal(form.values.physical.meterChannels.enabled,false);assert.equal(changes,0);
  const group=root.all(node=>node.tag==='details'&&node.dataset.group==='meterChannels')[0];assert.equal(group.open,false);assert.equal(group.all(node=>node.tag==='label'&&node.textContent==='Off').length,1);
  const toggle=group.all(node=>node.type==='checkbox')[0];assert.equal(toggle.attributes['aria-label'],'Enable this behavior');toggle.checked=true;toggle.onchange();assert.equal(group.open,true);assert.equal(form.values.physical.meterChannels.enabled,true);assert.equal(group.all(node=>node.tag==='label'&&node.textContent==='On').length,1);
  const exact=root.all(node=>node.id?.startsWith('physical-mix-')&&node.type==='number')[0];exact.value='';exact.oninput();assert.ok(form.validate().length);form.restoreDefaults();assert.equal(form.validate().length,0);assert.equal(form.values.physical.meterChannels.enabled,false);
  assert.equal(physicalFields(schema).length,5);assert.equal(formatPhysicalUnit('UTC days'),'days');assert.equal(humanSettingLabel('world.weather.winter_mean_c',{title:'Winter average'}),'Winter temperature');
});
test('actual catalog renders every supported control and round-trips all saved versions without migration',()=>{
  globalThis.document={createElement:tag=>new Node(tag)};
  const configuration=JSON.parse(readFileSync(new URL('../../server/setup-catalog.json',import.meta.url),'utf8')).configuration;
  const versions=configuration.supportedVersions||{[configuration.defaults.schemaVersion]:configuration};
  for(const [version,entry]of Object.entries(versions)){
    const saved=structuredClone(entry.defaults),root=new Node('div'),schema=configurationFormSchema(configuration,saved);
    const form=renderPhysicalSliderForm(root,schema,{values:saved,defaults:entry.defaults});const {schemaVersion,...expected}=saved;
    assert.deepEqual(form.values,expected,`Preserve ${version}`);assert.equal(form.validate().length,0);
    const editable=root.all(node=>node.tag==='select'||node.type==='number'||node.type==='checkbox');
    assert.equal(editable.length,physicalFields(schema).length,`Every field rendered for ${version}`);
    assert.equal(root.all(node=>String(node.textContent).includes('Engine starting value')).length,0);
  }
});
