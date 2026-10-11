import { addDays, dateValue, AdvanceController } from './world-control-core.mjs';
import { createStormPanel } from './world-control-events.mjs';
const $ = id => document.getElementById(id);
let status = null, offset = 0, total = 0, reading = false;
const catalogSources = fetch('/api/setups?view=catalog',{cache:'no-store'}).then(async response => response.ok ? (await response.json()).sources : []).catch(()=>[]);
async function request(action, params = {}, body) {
  const response = await fetch(`/api/compute?${new URLSearchParams({ action, ...params })}`, {
    method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
    ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
  });
  let value;
  try { value = await response.json(); } catch { throw new Error('The runtime returned an unreadable response. Refresh saved status.'); }
  if (!response.ok) { const error = new Error(value.detail || value.error || `Runtime request failed (${response.status}).`); error.rejected = response.status >= 400 && response.status < 500; throw error; }
  return value;
}
const controller = new AdvanceController(request);
const events = createStormPanel($('event-panel'), request, () => controls());
function message(value) { $('message').textContent = value; }
function controls() {
  $('controls').disabled = !status?.available || reading || controller.busy || controller.uncertain || events.locked;
  $('observations').disabled = !status?.available || reading || controller.busy || !status.days;
  $('open').disabled = reading || controller.busy || events.locked;
  $('world').disabled = reading || controller.busy || events.locked;
  $('refresh').disabled = reading || controller.busy || events.locked;
  events.setClockBusy(reading || controller.busy || controller.uncertain);
}
function render(value) {
  // Never show a previously selected world's state beneath another identity.
  status = value;
  $('world-map').hidden = true;
  if(value) void catalogSources.then(sources=>{
    const source=sources.find(source=>source.id===value.sourceId&&source.sourceRevision===value.sourceRevision&&source.snapshotSha256===value.snapshotSha256);
    if(status?.id!==value.id||!source?.preview)return;
    $('world-map-image').src=source.previewSmall||source.preview;
    $('world-map-image').alt=`${source.name} · pinned town illustration`;
    $('world-map-caption').textContent=`${source.name} · ${source.homes} homes · ${source.premises} premises. This illustration belongs to your saved world's map revision.`;
    $('world-map').hidden=false;
  });
  $('name').textContent = value?.name || 'Open a simulation';
  const option=[...$('world').options].find(option=>option.value===value?.id);
  if(option)option.textContent=`${value.name}${value.available?' · '+value.through:' · unavailable'}`;
  $('identity').textContent = value?.id || '—';
  $('revision').textContent = value?.sourceRevision || '—';
  $('state').textContent = value ? `${value.state || 'Unknown'}${value.available ? '' : ' · unavailable'}` : 'Unknown';
  $('next').textContent = value?.through || '—';
  $('last').textContent = value?.through && value.days > 0 ? addDays(value.through, -1) : 'No days committed';
  if (value?.through) {
    $('through').min = addDays(value.through, 1);
    $('through').max = addDays(value.through, 31);
    $('through').value = addDays(value.through, 1);
  }
  controls();
}
async function loadWorld(id) {
  if (!id || reading || controller.busy || events.locked) return;
  events.clear();
  reading = true; render(null); controls();
  try {
    const value = await request('status', { id });
    controller.recovered(); render(value);
    if (value.available) await events.load(value);
    const url = new URL(location.href); url.searchParams.set('id', id); history.replaceState(null, '', url);
    message(value.available ? 'Saved physical world loaded. Virtual Systems is not required.' : value.error || 'Saved world is unavailable.');
  } catch (error) { message(error.message); }
  finally { reading = false; controls(); }
}
async function list() {
  try {
    const value = await request('worlds', { offset: String(offset), limit: '25' });
    total = value.total; offset += value.worlds.length;
    for (const world of value.worlds) {
      if ([...$('world').options].some(option => option.value === world.id)) continue;
      const option = document.createElement('option'); option.value = world.id;
      option.textContent = `${world.name}${world.available ? ' · '+world.through : ' · unavailable'}`;
      $('world').append(option);
    }
    $('more').hidden = offset >= total;
    if (!status) message(total ? 'Choose an existing runtime instance.' : 'No saved simulation instances. Online setup drafts are separate from running worlds.');
  } catch (error) { message(`${error.message} Configure the compute connection to open persistent simulations.`); }
}
async function advance(target) {
  if (!status || reading || controller.busy || controller.uncertain || events.locked) return;
  const saved = status;
  try {
    const pending = controller.advance(saved.id, saved.through, target);
    controls(); $('progress').textContent = `Advancing to ${target} (exclusive). Last confirmed cursor: ${saved.through}.`;
    const value = await pending;
    render(value); $('progress').textContent = `Saved cursor: ${value.through}.`;
    await events.load(value);
    message('Physical time advanced and committed.');
  } catch (error) {
    $('progress').textContent = error.message;
    message(controller.uncertain ? 'The result is uncertain. Refresh saved status before another advance; committed days remain saved.' : error.message);
  } finally { controls(); }
}
$('open').onclick = () => loadWorld($('world').value);
$('refresh').onclick = () => loadWorld(status?.id || new URL(location.href).searchParams.get('id'));
$('more').onclick = async () => { $('more').disabled = true; await list(); $('more').disabled = false; };
$('day').onclick = () => advance(addDays(status.through, 1));
$('fast').onclick = () => advance(addDays(status.through, Number($('batch').value)));
$('advance').onclick = () => advance($('through').value);
$('observations').onclick = async () => {
  const saved = status;
  $('observations').disabled = true;
  try {
    const start = dateValue(saved.start) > dateValue(addDays(saved.through, -31)) ? saved.start : addDays(saved.through, -31);
    const value = await request('observations', { id: saved.id, start, end: saved.through });
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = `world-${saved.id}-${start}-${saved.through}.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); message('Recorded observations downloaded.');
  } catch (error) { message(error.message); } finally { controls(); }
};
await list();
const selected = new URL(location.href).searchParams.get('id');
if (selected) { $('world').value = selected; await loadWorld(selected); }
