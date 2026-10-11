import test from 'node:test';
import assert from 'node:assert/strict';
import { physicalFields, physicalDefaults, validatePhysicalValues, restorePhysicalPreset, sliderExtent } from './web/physical-slider-form.mjs';
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
