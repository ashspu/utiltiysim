import test from 'node:test';
import assert from 'node:assert/strict';
import { physicalFields, physicalDefaults, validatePhysicalValues, restorePhysicalPreset, sliderExtent, configurationFormSchema, upgradePhysicalConfiguration, physicalChoiceLabel } from './web/physical-slider-form.mjs';
const share = { type: 'number', minimum: 0, maximum: 100, multipleOf: .1 };
const schema = { type: 'object', properties: {
  meters: { type: 'object', properties: { ami: { ...share, default: 60 }, amr: { ...share, default: 30 }, manual: { ...share, default: 10 }, invented: { type: 'number', default: 7, 'x-supported': false } } },
  housingAge: { type: 'integer', minimum: 0, maximum: 300, default: 35 },
  locked: { type: 'number', readOnly: true, default: 1 },
}, 'x-distributions': [{ title: 'Meter technology mix', paths: ['meters.ami', 'meters.amr', 'meters.manual'], total: 100 }] };
test('only server-supported writable numeric fields appear', () => {
  assert.deepEqual(physicalFields(schema).map(field => field.path), ['meters.ami', 'meters.amr', 'meters.manual', 'housingAge']);
  assert.deepEqual(physicalDefaults(schema), { meters: { ami: 60, amr: 30, manual: 10 }, housingAge: 35 });
});
test('linked percentages require 100 without reallocating siblings', () => {
  const valid = physicalDefaults(schema); assert.deepEqual(validatePhysicalValues(schema, valid), []);
  valid.meters.ami = 61;
  assert.match(validatePhysicalValues(schema, valid)[0].message, /current total 101/);
  assert.equal(valid.meters.amr, 30);
  valid.meters = { ami: 33.3, amr: 33.3, manual: 33.4 };
  assert.deepEqual(validatePhysicalValues(schema, valid), []);
});
test('numeric bounds, precision, integer and finite constraints reject invalid drafts', () => {
  const value = physicalDefaults(schema); value.meters.ami = 100.05; value.housingAge = 3.5;
  const errors = validatePhysicalValues(schema, value);
  assert.ok(errors.some(error => /Maximum/.test(error.message)));
  assert.ok(errors.some(error => /multiples/.test(error.message)));
  assert.ok(errors.some(error => /whole/.test(error.message)));
  value.housingAge = NaN;
  assert.ok(validatePhysicalValues(schema, value).some(error => /finite/.test(error.message)));
});
test('preset restore replaces prior draft with defaults plus supported preset fields', () => {
  const defaults = physicalDefaults(schema), original = structuredClone(defaults);
  const preset = restorePhysicalPreset(schema, defaults, { meters: { ami: 100, amr: 0, manual: 0, invented: 88 }, unknown: 8 });
  assert.deepEqual(preset, { meters: { ami: 100, amr: 0, manual: 0 }, housingAge: 35 });
  assert.deepEqual(validatePhysicalValues(schema, preset), []);
  assert.deepEqual(restorePhysicalPreset(schema, defaults), original);
  assert.deepEqual(defaults, original);
});
test('slider display extents expand unbounded weather without inventing validation limits', () => {
  const field = { type: 'number', default: 2, 'x-slider': { min: -20, max: 40 }, 'x-step': .1 };
  assert.deepEqual(sliderExtent(field, -45), { min: -45, max: 40, step: .1 });
  assert.deepEqual(validatePhysicalValues({ properties: { weather: field } }, { weather: -45 }), []);
  assert.equal(sliderExtent({ ...field, minimum: 0, maximum: 1 }, 5).max, 1);
});
test('exclusive JSON-schema bounds are authoritative', () => {
  const bounded = { properties: { rate: { type: 'number', exclusiveMinimum: 0, exclusiveMaximum: 1 } } };
  assert.match(validatePhysicalValues(bounded, { rate: 0 })[0].message, /exceed/);
  assert.match(validatePhysicalValues(bounded, { rate: 1 })[0].message, /below/);
});
const configuration={schemas:{world:{type:'object',properties:{weather:{type:'object',properties:{winter:{type:'number',default:2}}}}},physical:{type:'object',properties:{
  householdFinance:{type:'object',properties:{enabled:{type:'boolean',default:false},cash:{type:'integer',minimum:0,default:200000}}},
  householdCashflow:{type:'object',properties:{enabled:{type:'boolean',default:false},policy:{type:'string',enum:['available-cash','all-or-nothing'],default:'available-cash'}}},
}}},defaults:{schemaVersion:'physical-setup/2',world:{weather:{winter:2}},physical:{householdFinance:{enabled:false,cash:200000},householdCashflow:{enabled:false,policy:'available-cash'}}}};
test('v1 draft stays legacy until explicit upgrade, preserving exact weather',()=>{
  const legacy={world:{weather:{winter:-37.123}}},original=structuredClone(legacy);
  const schema=configurationFormSchema(configuration,legacy);
  assert.deepEqual(physicalFields(schema).map(field=>field.path),['world.weather.winter']);
  assert.deepEqual(restorePhysicalPreset(schema,configuration.defaults,legacy),legacy);
  const upgraded=upgradePhysicalConfiguration(legacy,configuration.defaults);
  assert.equal(upgraded.world.weather.winter,-37.123);assert.equal(upgraded.schemaVersion,'physical-setup/2');
  assert.equal(upgraded.physical.householdFinance.enabled,false);assert.equal(upgraded.physical.householdCashflow.enabled,false);
  assert.deepEqual(legacy,original);
});
test('booleans and enums survive edit/preset/default round trips and validate dependencies',()=>{
  const schema=configurationFormSchema(configuration,configuration.defaults);
  const values=restorePhysicalPreset(schema,configuration.defaults,{physical:{householdFinance:{enabled:true},householdCashflow:{enabled:true,policy:'all-or-nothing'}}});
  assert.equal(values.physical.householdFinance.enabled,true);assert.equal(values.physical.householdCashflow.policy,'all-or-nothing');
  assert.deepEqual(validatePhysicalValues(schema,values),[]);
  values.physical.householdFinance.enabled=false;
  assert.match(validatePhysicalValues(schema,values)[0].message,/requires household finances/);
  values.physical.householdCashflow.policy='invented';
  assert.ok(validatePhysicalValues(schema,values).some(error=>/supported option/.test(error.message)));
  const restored=restorePhysicalPreset(schema,configuration.defaults);
  assert.equal(restored.physical.householdCashflow.enabled,false);assert.equal(restored.physical.householdCashflow.policy,'available-cash');
});
test('x-control display limits never constrain exact engine-valid input',()=>{
  const field={type:'number',minimum:0,maximum:1,default:.01,'x-control':{displayMinimum:0,displayMaximum:.2,step:.001}};
  assert.equal(sliderExtent(field,.03).max,.2);assert.equal(sliderExtent(field,.72).max,.72);
  assert.equal(sliderExtent(field,.03).step,.001);
  assert.deepEqual(validatePhysicalValues({properties:{rate:field}},{rate:.1234567}),[]);
});
test('range never snaps an exact value onto a different presentation step',()=>{
  const payment={type:'integer',minimum:1,maximum:100000000,'x-control':{step:100}};
  assert.equal(sliderExtent(payment,50000).step,'any');
  assert.equal(sliderExtent(payment,50001).step,100);
  const probability={type:'number',minimum:0,maximum:1,'x-control':{step:.001}};
  assert.equal(sliderExtent(probability,.0153).step,'any');
  assert.equal(sliderExtent(probability,.015).step,.001);
  assert.deepEqual(validatePhysicalValues({properties:{payment}}, {payment:50000}),[]);
});
test('cashflow choices use engine labels and server labels take precedence',()=>{
  assert.equal(physicalChoiceLabel('physical.householdCashflow.insufficientCashPolicy',{},'available-cash'),'Spend available cash; record remainder');
  assert.equal(physicalChoiceLabel('insufficientCashPolicy',{},'all-or-nothing'),'Spend only if the whole expense is covered');
  assert.equal(physicalChoiceLabel('insufficientCashPolicy',{'x-control':{optionLabels:{'available-cash':'Server label'}}},'available-cash'),'Server label');
  assert.equal(physicalChoiceLabel('otherChoice',{},'available-cash'),'available-cash');
});
