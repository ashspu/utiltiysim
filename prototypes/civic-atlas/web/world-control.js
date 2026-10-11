import { addDays, dateValue, AdvanceController } from './world-control-core.mjs';
import { createStormPanel } from './world-control-events.mjs';
import { createSentimentPanel, commandPanelsLocked, coordinateCommandPanels } from './world-control-sentiment.mjs';
import { readSession } from './shell-session.js';
import { createConnectedPanel } from './world-control-connected.mjs';
import { ConnectedCommandController } from './world-control-connected-state.mjs';
import { clockIsManaged, connectedView } from './world-control-connected-view.mjs';
const $ = id => document.getElementById(id);
let status = null, offset = 0, total = 0, reading = false;
let connectedStatus = null, connectedCommands = null, connectedActor = null, canControl = false;
let connectedRefreshing = false, pollTimer = null, pollRemaining = 0;
let connectedPreflight = false;
const catalogSources = fetch('/api/setups?view=catalog',{cache:'no-store'}).then(async response => response.ok ? (await response.json()).sources : []).catch(()=>[]);
async function request(action, params = {}, body) {
  const response = await fetch(`/api/compute?${new URLSearchParams({ action, ...params })}`, {
    method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
    ...(body ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {})
  });
  let value;
  try { value = await response.json(); } catch { throw new Error('The runtime returned an unreadable response. Refresh saved status.'); }
  if (!response.ok) { const error = new Error(value.detail || value.error || `Runtime request failed (${response.status}).`); error.rejected = response.status >= 400 && response.status < 500 && (action !== 'connected-command' || value.commandRejected === true); error.status = response.status; throw error; }
  return value;
}
const controller = new AdvanceController(request);
const events = createStormPanel($('event-panel'), request, () => controls());
const sentiment = createSentimentPanel($('sentiment-panel'), request, () => controls(), readSession().then(value=>value.user?.id).catch(()=>null));
const connected = createConnectedPanel($('connected-panel'), connectedAction);
function message(value) { $('message').textContent = value; }
function controls() {
  const managed = clockIsManaged(status), sending = controller.busy || connectedCommands?.busy || connectedPreflight;
  const uncertain = controller.uncertain || Boolean(connectedCommands?.pending);
  const executing = managed && (!connectedStatus || connectedStatus.phase === 'running');
  $('controls').disabled = !status?.available || reading || sending || uncertain || commandPanelsLocked(events,sentiment)
    || managed && (!canControl || !connectedStatus?.physicalThrough || connectedStatus.producerAvailable === false || !connectedStatus.supportedActions.includes('advance'));
  $('observations').disabled = !status?.available || reading || controller.busy || !status.days;
  $('open').disabled = reading || sending || events.locked || sentiment.locked;
  $('world').disabled = reading || sending || events.locked || sentiment.locked;
  $('refresh').disabled = reading || controller.busy || events.locked || sentiment.locked;
  coordinateCommandPanels(events,sentiment,reading || sending || uncertain || executing);
  $('connected-section').hidden = !managed;
  $('operation-help').textContent = managed
    ? 'This world shares its simulation clock with Virtual Systems. The connected controller owns advancement, including while paused.'
    : 'Time and observations work independently of Virtual Systems.';
  $('advance-legend').textContent = managed ? 'Request connected advancement' : 'Advance physical time';
  $('clock-help').textContent = managed
    ? 'Requests are accepted durably and execute in the background. Pause requests stop at a safe processing boundary. Refresh shows the reported clocks; an uncertain command must be retried with its original identity.'
    : 'Requests run synchronously for at most 31 new days. Refresh saved status after an uncertain response. Committed days remain saved.';
  if (managed) {
    if (connectedStatus) {
      $('through').min = addDays(connectedStatus.clock.slice(0,10),1);
      $('through').max = new Date(Date.parse(connectedStatus.clock) + 31*86400000).toISOString().slice(0,10);
      if ($('through').value < $('through').min || $('through').value > $('through').max) $('through').value = $('through').min;
    }
    connected.render(connectedView(status,connectedStatus,connectedCommands,canControl,commandPanelsLocked(events,sentiment)));
    connected.setBusy(reading || Boolean(sending) || events.busy || sentiment.busy);
  }
}
function render(value) {
  // Never show a previously selected world's state beneath another identity.
  status = value;
  $('profile-summary').textContent='';
  const profile=value?.physicalProfiles;
  if(value?.available&&profile?.enabled){
    const housing=profile.housing;
    $('profile-summary').textContent=[profile.meterChannelsEnabled?`Applied meter collections: AMI ${profile.meterCounts?.AMI??0}, AMR ${profile.meterCounts?.AMR??0}, manual ${profile.meterCounts?.MANUAL??0}.`:'',profile.housingAgeEnabled&&housing?.count?`Applied housing: ${housing.count} homes, ages ${housing.minAgeYears}–${housing.maxAgeYears} years, realised mean ${housing.meanAgeYears} years; ${housing.retrofittedCount} retrofitted (${housing.retrofittedPercent}%).`:''].filter(Boolean).join(' ');
  }
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
    const cursor = clockIsManaged(value) && connectedStatus ? connectedStatus.clock.slice(0,10) : value.through;
    $('through').min = addDays(cursor, 1);
    $('through').max = addDays(cursor, 31);
    $('through').value = addDays(cursor, 1);
  }
  controls();
}
async function loadWorld(id) {
  if (!id || reading || controller.busy || connectedCommands?.busy || connectedPreflight || commandPanelsLocked(events,sentiment)) return;
  clearTimeout(pollTimer); pollRemaining = 0;
  events.clear();
  sentiment.clear();
  connected.clear(); connectedStatus = null; connectedCommands = null; connectedActor = null; canControl = false;
  reading = true; render(null); controls();
  try {
    const value = await request('status', { id });
    controller.recovered(); render(value);
    if (clockIsManaged(value)) {
      try {
        const session = await readSession();
        connectedActor = session.user?.id;
        canControl = (session.grants || []).some(grant => ['owner','operator'].includes(grant.role) && [value.grantTownId,'*'].includes(grant.town));
        if (connectedActor) connectedCommands = new ConnectedCommandController({storage:localStorage,request,actorId:connectedActor,worldId:id});
        // Browser storage failure disables mutation but still permits reading.
      } catch (error) { canControl = false; message(error.message); }
      try { connectedStatus = await request('connected',{id}); render(value); } catch (error) { message(error.message); }
    }
    if (value.available) {await events.load(value);await sentiment.load(value);}
    const url = new URL(location.href); url.searchParams.set('id', id); history.replaceState(null, '', url);
    if (!value.available) message(value.error || 'Saved world is unavailable.');
    else if (!clockIsManaged(value)) message('Saved physical world loaded. Virtual Systems is not required.');
    else if (connectedCommands?.pending) message('A previous connected request needs confirmation. Retry its saved identity; refreshing status does not replace it.');
    else if (connectedStatus) message('Connected world loaded. The reported clock and command status determine its available controls.');
    else message('Connected controller status is unavailable. Physical advancement remains controlled by that controller.');
    if (connectedStatus?.phase === 'running') { pollRemaining = 24; scheduleConnectedPoll(); }
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
  if (clockIsManaged(status)) return connectedAction('advance',target);
  if (!status || reading || controller.busy || controller.uncertain || commandPanelsLocked(events,sentiment)) return;
  const saved = status;
  try {
    const pending = controller.advance(saved.id, saved.through, target);
    controls(); $('progress').textContent = `Advancing to ${target} (exclusive). Last confirmed cursor: ${saved.through}.`;
    const value = await pending;
    render(value); $('progress').textContent = `Saved cursor: ${value.through}.`;
    await events.load(value);
    await sentiment.load(value);
    message('Physical time advanced and committed.');
  } catch (error) {
    $('progress').textContent = error.message;
    message(controller.uncertain ? 'The result is uncertain. Refresh saved status before another advance; committed days remain saved.' : error.message);
  } finally { controls(); }
}
function scheduleConnectedPoll() {
  clearTimeout(pollTimer);
  if (pollRemaining <= 0 || document.hidden || !clockIsManaged(status)) return;
  pollTimer = setTimeout(async () => {
    pollRemaining--;
    try { await refreshConnected(); } catch { return; }
    if (connectedStatus?.phase === 'running' || connectedStatus?.lastCommand?.status === 'accepted') scheduleConnectedPoll();
  },2500);
}
async function refreshConnected() {
  if (!status || connectedRefreshing) return;
  const id = status.id, previousThrough = status.through;
  connectedRefreshing = true;
  try {
    const value = await request('status',{id});
    const reported = await request('connected',{id});
    if (status?.id !== id) return;
    connectedStatus = reported; render(value);
    connectedCommands?.recovered(reported);
    if (previousThrough !== value.through && reported.phase !== 'running' && !commandPanelsLocked(events,sentiment)) {
      await events.load(value); await sentiment.load(value);
    }
  } catch (error) {
    if (status?.id === id) { connectedStatus = null; message(error.message); controls(); }
    throw error;
  } finally { connectedRefreshing = false; controls(); }
}
async function connectedAction(action,target) {
  if (action === 'refresh') return refreshConnected();
  if (!status || !clockIsManaged(status) || reading || !connectedCommands || connectedCommands.busy || connectedPreflight
      || (action === 'retry' ? events.busy || sentiment.busy : commandPanelsLocked(events,sentiment))) return;
  if (!canControl) throw new Error('Current operator or owner access is required.');
  const id = status.id, commands = connectedCommands;
  connectedPreflight = true; controls();
  try {
    const session = await readSession();
    if (status?.id !== id || connectedCommands !== commands) throw new Error('The selected world changed. Reload its status before sending a command.');
    if (session.user?.id !== connectedActor) throw new Error('Your signed-in account changed. Reload this world before sending a command.');
    let pending;
    if (action === 'retry') pending = connectedCommands.retry();
    else {
      if (!connectedStatus?.supportedActions.includes(action)) throw new Error('Refresh the controller status to see its supported actions.');
      let through;
      if (action === 'advance') {
        if (connectedStatus.producerAvailable === false || !connectedStatus.physicalThrough) throw new Error('Physical producer status is unavailable. Refresh before requesting advancement.');
        const day = target || addDays(connectedStatus.clock.slice(0,10),1);
        dateValue(day); through = `${day}T00:00:00Z`;
        const seconds = (Date.parse(through) - Date.parse(connectedStatus.clock))/1000;
        if (seconds <= 0 || seconds > 31*86400) throw new Error('Choose a target after the Virtual Systems clock and within 31 days.');
      }
      pending = connectedCommands.execute(action,connectedStatus.revision,through);
    }
    controls();
    const receipt = await pending;
    if (status?.id !== id) return;
    message(`Command accepted durably (${receipt.commandId}). Reported processing determines completion.`);
    await refreshConnected();
    pollRemaining = 24; scheduleConnectedPoll();
  } catch (error) {
    if (status?.id === id) {
      message(connectedCommands?.pending ? 'The request is uncertain. Retry the retained command with the same identity and target.' : error.message);
      // A definitive rejection releases identity, but its old status/revision
      // is no longer sufficient authority to issue a new command.
      if (error.rejected) connectedStatus = null;
    }
    throw error;
  } finally { connectedPreflight = false; controls(); }
}
$('open').onclick = () => loadWorld($('world').value);
$('refresh').onclick = () => clockIsManaged(status) ? refreshConnected().catch(()=>{}) : loadWorld(status?.id || new URL(location.href).searchParams.get('id'));
$('more').onclick = async () => { $('more').disabled = true; await list(); $('more').disabled = false; };
$('day').onclick = () => advance(addDays(clockIsManaged(status) ? connectedStatus.clock.slice(0,10) : status.through, 1)).catch(()=>{});
$('fast').onclick = () => advance(addDays(clockIsManaged(status) ? connectedStatus.clock.slice(0,10) : status.through, Number($('batch').value))).catch(()=>{});
$('advance').onclick = () => advance($('through').value).catch(()=>{});
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
