const ACTIONS = ['start', 'pause', 'resume', 'advance', 'retry', 'refresh'];
const text = value => typeof value === 'string' && value.trim() ? value : null;
function canonicalDay(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return false;
  const time = Date.parse(`${value}T00:00:00Z`);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0, 10) === value;
}
function utcTimestamp(value){
  if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)$/.test(value))return false;
  return canonicalDay(value.slice(0,10))&&Number(value.slice(11,13))<24&&Number(value.slice(14,16))<60&&Number(value.slice(17,19))<60&&Number.isFinite(Date.parse(value));
}
function completeClockView(view) {
  return view?.supported === true && view.connected === true
    && !!text(view.state) && !!text(view.phase)
    && canonicalDay(view.physicalThrough) && canonicalDay(view.recipientThrough) && utcTimestamp(view.recipientClock)
    && Number.isInteger(view.revision) && view.revision >= 0
    && ['transport', 'processing', 'business'].every(key => !!text(view[key]?.state))
    && !view.pendingCommand && view.locked !== true;
}

let sequence = 0;
export function createConnectedPanel(container, onAction) {
  if (typeof onAction !== 'function') throw new TypeError('Connected controls require a shell action callback.');
  const make = (tag, value) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = value;
    return node;
  };
  const panel = make('div'); panel.className = 'connected-panel';
  const heading = make('h2', 'Connected operation'); heading.id = `connected-title-${++sequence}`;
  panel.setAttribute('role', 'region'); panel.setAttribute('aria-labelledby', heading.id);
  const connection = make('p'), progress = make('dl'), outcomes = make('div'); outcomes.className = 'connected-outcomes';
  const cells = {};
  for (const [key, label] of [
    ['physicalThrough', 'Next physical UTC day'], ['recipientThrough', 'Virtual Systems UTC day'], ['recipientClock','Virtual Systems UTC clock'],
    ['phase', 'Current phase'], ['lastCompletedDay', 'Last physical day committed'],
  ]) {
    const definition = make('dd', 'Unavailable'); cells[key] = definition;
    progress.append(make('dt', label), definition);
  }
  const stages = {};
  for (const [key, title] of [
    ['transport', 'Delivery receipt'], ['processing', 'Recipient processing'], ['business', 'Business outcome'],
  ]) {
    const stage = make('div'); stage.className = 'connected-outcome';
    const reported = make('p', 'Unknown'); stages[key] = reported;
    stage.append(make('h3', title), reported); outcomes.append(stage);
  }
  const explanation = make('p', 'Delivery acceptance confirms receipt only. It does not confirm recipient processing or business completion. Business exceptions may remain after processing.');
  explanation.className = 'connected-help';
  const actions = make('div'); actions.className = 'connected-actions';
  const notice = make('p'); notice.setAttribute('role', 'status'); notice.setAttribute('aria-live', 'polite');
  const buttons = {};
  let view = null, busy = false, acting = false, refreshing = false, generation = 0;
  function updateButtons() {
    const allowed = Array.isArray(view?.allowedActions) ? view.allowedActions : [];
    const locked = !!view?.pendingCommand || view?.locked === true;
    for (const action of ACTIONS) {
      let enabled = allowed.includes(action);
      buttons[action].hidden = action === 'start' ? !allowed.includes('start') : action === 'retry' ? !(view?.pendingCommand && allowed.includes('retry')) : false;
      if (action === 'start' || action === 'advance') enabled = enabled && completeClockView(view);
      else if (action === 'retry') enabled = enabled && !!view?.pendingCommand;
      else if (action !== 'refresh') enabled = enabled && view?.supported === true && view.connected === true
        && Number.isSafeInteger(view.revision) && view.revision >= 0 && !locked;
      // Refresh can resolve a retained command; it never sends a new command.
      buttons[action].disabled = action==='refresh' ? refreshing : busy || acting || !enabled;
    }
    panel.setAttribute('aria-busy', String(busy || acting));
  }
  for (const action of ACTIONS) {
    const button = make('button', { start: 'Start connected operation', pause: 'Pause', resume: 'Resume', advance: 'Advance connected day', retry: 'Retry retained command', refresh: 'Refresh reported status' }[action]);
    button.type = 'button'; buttons[action] = button;
    button.onclick = async () => {
      if(action==='refresh'){
        if(refreshing)return;const current=generation;refreshing=true;updateButtons();
        try{await onAction('refresh');if(current===generation&&!acting)notice.textContent='';}
        catch{if(current===generation&&!acting)notice.textContent='Reported status is unavailable. Try refreshing again.';}
        finally{refreshing=false;updateButtons();}return;
      }
      if (button.disabled || acting || busy) return;
      const current = generation; acting = true; notice.textContent = 'Request in progress…'; updateButtons();
      try { await onAction(action); if (current === generation) notice.textContent = ''; }
      catch { if (current === generation) notice.textContent = 'The request could not be confirmed. Retry the retained request for confirmation, or refresh the reported status.'; }
      finally { acting = false; updateButtons(); }
    };
    actions.append(button);
  }
  panel.append(heading, connection, progress, outcomes, explanation, actions, notice);
  container.replaceChildren(panel);
  function render(next) {
    view = next || null;
    connection.textContent = !view ? 'Connected status unavailable.' : view.supported !== true
      ? 'Connected operation is unavailable for this world.'
      : `${view.connected === true ? 'Connected' : 'Disconnected'} · Reported state: ${text(view.state) || 'Unknown'}`;
    for (const key of ['physicalThrough', 'recipientThrough', 'lastCompletedDay']) cells[key].textContent = canonicalDay(view?.[key]) ? view[key] : 'Unavailable';
    cells.recipientClock.textContent=utcTimestamp(view?.recipientClock)?view.recipientClock:'Unavailable';
    cells.phase.textContent = text(view?.phase) || 'Unknown';
    for (const key of ['transport', 'processing', 'business']) {
      const state = text(view?.[key]?.state), label = text(view?.[key]?.label);
      stages[key].textContent = [state || 'Unknown', label].filter(Boolean).join(' · ');
    }
    if (!acting) notice.textContent = view?.pendingCommand ? 'A previous request needs confirmation. Retry the original request for confirmation, or refresh the reported status.' : '';
    updateButtons();
  }
  render(null);
  return {
    render,
    setBusy(value) { busy = value === true; updateButtons(); },
    clear() { generation++; render(null); notice.textContent = ''; },
  };
}
