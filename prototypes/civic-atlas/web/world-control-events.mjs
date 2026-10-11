import { addDays } from './world-control-core.mjs';
const families = ['electric', 'gas', 'water', 'sewer'];
function element(tag, text) { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; }
export function createStormPanel(container, request, changed) {
  let world, record, pending, busy = false, clockBusy = false, key, storageReady = true;
  let dayCursor, eventCursor, journalCursor;
  const notice = element('p'); notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite');
  const form = element('form'), fields = element('fieldset'); fields.append(element('legend', 'Schedule temperature and infrastructure stress'));
  const inputs = {};
  function input(name, title, type, value, min, max) {
    const label = element('label', title), node = element('input'); node.id = `storm-${name}`; label.htmlFor = node.id;
    node.type = type; node.value = value; node.required = true;
    if (min !== undefined) node.min = min; if (max !== undefined) node.max = max;
    if (type === 'number') node.step = 'any'; fields.append(label, node); inputs[name] = node;
  }
  input('start', 'Start UTC date (inclusive)', 'date', ''); input('end', 'End UTC date (exclusive)', 'date', '');
  input('temperature', 'Temperature offset °C', 'number', -5, -40, 40);
  families.forEach(name => input(name, `${name} risk multiplier (1–100)`, 'number', 1, 1, 100));
  input('reason', 'Schedule or cancellation reason', 'text', '');
  const submit = element('button', 'Schedule event'); submit.type = 'submit'; fields.append(submit); form.append(fields);
  const retry = element('button', 'Retry retained command'), refresh = element('button', 'Refresh event history');
  const schedules = element('div'), history = element('div'), journal = element('div');
  const olderEvents = element('button', 'Older schedules'), olderDays = element('button', 'Older storm outcomes'), olderJournal = element('button', 'Older physical events');
  function controls() {
    fields.disabled = busy || clockBusy || !!pending || !record || !storageReady;
    retry.hidden = !pending; retry.disabled = busy || clockBusy;
    refresh.disabled = busy || clockBusy || !!pending;
    container.querySelectorAll('[data-cancel]').forEach(button => { button.disabled = fields.disabled; });
    olderEvents.disabled = busy || clockBusy || !!pending || !record?.nextEventsBefore;
    olderDays.disabled = busy || clockBusy || !!pending || !record?.nextBefore;
    olderJournal.disabled = busy || clockBusy || !!pending || !journalCursor;
  }
  function mount() {
    container.replaceChildren(notice, element('p', 'A finite temperature/risk scenario uses the existing daily physical engine. It does not model rainfall, flooding, wind or automatic repairs. Risk multipliers do not enable an inactive fault model.'), form, retry, refresh,
      element('h3', 'Scheduled events'), schedules, olderEvents, element('h3', 'Effective storm days'), history, olderDays,
      element('h3', 'Physical event journal'), journal, olderJournal);
  }
  async function journalPage(before) {
    const value = await request('events', { id: world.id, limit: '25', ...(before ? { before: String(before) } : {}) });
    journal.replaceChildren(); journalCursor = value.nextBefore;
    for (const event of value.events) {
      const details = element('details'), summary = element('summary', `${event.day} · ${event.type} · ${event.subject || event.id}`);
      details.append(summary, element('pre', JSON.stringify(event, null, 2))); journal.append(details);
    }
    if (!value.events.length) journal.append(element('p', 'No physical events on this page.'));
  }
  async function inspect() {
    const value = await request('storms', { id: world.id, limit: '25', ...(dayCursor ? { before: dayCursor } : {}), ...(eventCursor ? { eventsBefore: String(eventCursor) } : {}) });
    if (value.worldInstanceId !== world.id) throw new Error('The event adapter returned another instance.');
    record = value; schedules.replaceChildren(); history.replaceChildren();
    inputs.start.min = record.through; inputs.end.min = addDays(record.through, 1);
    if (!inputs.start.value || inputs.start.value < record.through) { inputs.start.value = record.through; inputs.end.value = addDays(record.through, 3); }
    for (const event of record.events) {
      const state = event.cancelledEventId ? 'Cancelled' : event.endDate <= record.through ? 'Finished' : event.startDate < record.through ? 'Active' : 'Scheduled';
      const row = element('article'); row.append(element('h4', `${state} · ${event.startDate} → ${event.endDate} exclusive`), element('p', event.reason),
        element('p', `${event.temperatureOffsetC} °C offset · ${families.map(f => `${f} ${event.multipliers[f]}×`).join(' · ')}`), element('p', `Storm ${event.stormId} · event ${event.eventId}`));
      if (state === 'Scheduled') { const cancel = element('button', 'Cancel before start'); cancel.dataset.cancel = event.stormId; cancel.onclick = () => { try { send({ ...base('cancel'), stormId: event.stormId }); } catch (error) { notice.textContent = error.message; } }; row.append(cancel); }
      schedules.append(row);
    }
    if (!record.events.length) schedules.append(element('p', 'No scheduled storms on this page.'));
    for (const day of record.history) {
      const details = element('details'); details.append(element('summary', `${day.day} · baseline ${day.baselineTemperatureC} °C → actual ${day.temperatureC} °C`), element('pre', JSON.stringify(day, null, 2))); history.append(details);
    }
    if (!record.history.length) history.append(element('p', 'No storm days processed on this page. Advance across a scheduled date to record its actual effect.'));
    controls();
  }
  function base(action) {
    if (!inputs.reason.value.trim()) { inputs.reason.focus(); throw new Error('Enter a reason before recording a command.'); }
    return { commandId: crypto.randomUUID(), expectedRevision: record.revision, effectiveDate: record.through, action, reason: inputs.reason.value.trim(), causalReference: 'hosted-world-controls' };
  }
  async function send(command) {
    if (busy || clockBusy) return;
    try {
      if (!pending) {
        try { sessionStorage.setItem(key, JSON.stringify(command)); }
        catch { storageReady = false; throw new Error('Cannot retain an exact retry; command was not sent.'); }
        pending = command;
      }
      busy = true; controls(); changed(); notice.textContent = 'Recording physical event…';
      const result = await request('storms', { id: world.id }, pending);
      pending = null; sessionStorage.removeItem(key); dayCursor = eventCursor = null;
      await inspect(); await journalPage(); notice.textContent = `Command recorded · revision ${result.revision}. Physical effects occur only when time advances.`;
    } catch (error) {
      if (error.rejected) { pending = null; sessionStorage.removeItem(key); }
      notice.textContent = `${error.message}${pending ? ' Outcome uncertain; retry the retained exact command.' : ' Refresh event history before editing again.'}`;
    } finally { busy = false; controls(); changed(); }
  }
  async function page(kind) {
    if (busy || clockBusy || pending) return; busy = true; controls(); changed();
    try {
      if (kind === 'days') dayCursor = record.nextBefore;
      if (kind === 'schedules') eventCursor = record.nextEventsBefore;
      if (kind === 'journal') await journalPage(journalCursor);
      else { if (kind === 'latest') dayCursor = eventCursor = null; await inspect(); if (kind === 'latest') await journalPage(); }
    } catch (error) { notice.textContent = error.message; } finally { busy = false; controls(); changed(); }
  }
  form.onsubmit = event => { event.preventDefault(); try { send({ ...base('schedule'), startDate: inputs.start.value, endDate: inputs.end.value, temperatureOffsetC: Number(inputs.temperature.value), multipliers: Object.fromEntries(families.map(f => [f, Number(inputs[f].value)])) }); } catch (error) { notice.textContent = error.message; } };
  retry.onclick = () => send(); refresh.onclick = () => page('latest'); olderEvents.onclick = () => page('schedules'); olderDays.onclick = () => page('days'); olderJournal.onclick = () => page('journal');
  return {
    get locked() { return busy || !!pending; },
    setClockBusy(value) { clockBusy = value; controls(); },
    clear() { world = record = pending = null; inputs.start.value = inputs.end.value = ''; container.replaceChildren(element('p', 'Open a saved simulation to inspect its supported physical events.')); },
    async load(value) {
      world = value; dayCursor = eventCursor = null; key = `utilitysim-storm-command:${world.id}`; storageReady = true;
      try { pending = JSON.parse(sessionStorage.getItem(key) || 'null'); sessionStorage.setItem(`${key}:probe`, '1'); sessionStorage.removeItem(`${key}:probe`); } catch { storageReady = false; pending = null; }
      mount();
      try { await inspect(); await journalPage(); notice.textContent = pending ? 'A retained command needs an exact retry before advancing time.' : storageReady ? `Storm revision ${record.revision}. Review dates and assumptions before scheduling.` : 'Session storage is unavailable. Event commands require retained exact retries; inspection remains available.'; }
      catch (error) { record = null; notice.textContent = `Physical event adapter unavailable: ${error.message} Time controls remain available.`; }
      controls(); changed();
    }
  };
}
