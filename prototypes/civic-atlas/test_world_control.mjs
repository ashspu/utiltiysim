import test from 'node:test';
import assert from 'node:assert/strict';
import { addDays, dateValue, validateAdvance, AdvanceController } from './web/world-control-core.mjs';
test('UTC boundaries include leap days and year rollover', () => {
  assert.equal(addDays('2028-02-28', 1), '2028-02-29');
  assert.equal(addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(addDays('2026-03-08', 1), '2026-03-09');
  assert.throws(() => dateValue('2026-02-29'));
  assert.throws(() => dateValue('2026-1-01'));
  assert.equal(validateAdvance('2026-01-01', '2026-02-01'), 31);
  assert.throws(() => validateAdvance('2026-01-01', '2026-02-02'));
  assert.throws(() => validateAdvance('2026-01-01', '2026-01-01'));
});
test('concurrent click sends one absolute target, recovered cursor resumes', async () => {
  let finish, calls = [];
  const control = new AdvanceController((action, params, body) => {
    calls.push({ action, params, body }); return new Promise(resolve => { finish = resolve; });
  });
  const pending = control.advance('instance', '2026-01-01', '2026-01-02');
  await assert.rejects(control.advance('instance', '2026-01-01', '2026-01-02'), /already/);
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0].body, { through: '2026-01-02' });
  finish({ through: '2026-01-02' }); await pending;
  assert.equal(control.busy, false);
});
test('ambiguous request prevents a duplicate advance until persisted status recovers', async () => {
  let calls = 0;
  const control = new AdvanceController(async () => { calls++; throw new Error('Connection lost'); });
  await assert.rejects(control.advance('instance', '2026-01-01', '2026-01-02'), /Connection/);
  await assert.rejects(control.advance('instance', '2026-01-01', '2026-01-02'), /Refresh/);
  assert.equal(calls, 1);
  control.recovered();
  // Status recovery after server restart reads Jan 2: subsequent next day is Jan 3.
  control.request = async (_, __, body) => body;
  assert.deepEqual(await control.advance('instance', '2026-01-02', '2026-01-03'), { through: '2026-01-03' });
});
