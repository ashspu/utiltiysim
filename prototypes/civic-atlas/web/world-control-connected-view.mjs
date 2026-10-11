import { addDays } from './world-control-core.mjs';

export function clockIsManaged(world) {
  if (!world || !Object.hasOwn(world, 'connectedClock')) return false;
  const marker = world.connectedClock;
  return !marker || typeof marker.configured !== 'boolean' || marker.configured || marker.manualAdvanceAllowed === false;
}

// These labels describe the reported stage only. A durable command receipt is
// never promoted to recipient completion, an invoice or a balanced ledger.
export function connectedView(world, reported, commandState, canControl, locked = false) {
  const pending = commandState?.pending;
  const receipt = commandState?.lastReceipt;
  const allowedActions = ['refresh'];
  if (canControl && pending) allowedActions.push('retry');
  if (canControl && reported && !pending && !locked) allowedActions.push(...reported.supportedActions.filter(action=>
    !['advance','resume'].includes(action) || reported.producerAvailable !== false && reported.physicalThrough));
  const counts = reported?.counts;
  const last = reported?.lastCommand;
  const confirmed = receipt && last?.commandId === receipt.commandId;
  const commandProgress = last?.status === 'interrupted'
    ? ` Advance interrupted; requested ${last.target}. Current clock ${reported.clock}.`
    : confirmed && last?.outcome === 'target-reached' && last.targetReached === true
      ? ` Advance reached ${last.achievedClock}.`
      : confirmed ? ` Latest confirmed command: ${last.status}. Check the reported clock for progress.` : '';
  const transport = pending ? {state:'Confirmation needed',label:'Retry the saved command with its original identity.'}
    : receipt ? {state:'Accepted durably',label:`Command ${receipt.commandId}. Acceptance alone does not confirm execution.`}
    : {state:'No command receipt loaded',label:'Reported controller status is shown below.'};
  const processing = !reported ? {state:'Unavailable',label:'The connected controller did not confirm status.'}
    : {state:reported.phase,label:`${counts.pending} queued jobs; ${counts.failed} technical failures.${reported.producerAvailable === false ? ' Physical producer unavailable; no physical cursor is confirmed.' : ''}${commandProgress}${reported.target ? ` Target: ${reported.target}.` : ''}`};
  const business = !counts ? {state:'Not reported',label:'No business result has been confirmed.'}
    : {state:'Reported exceptions',label:`Missing: ${counts.missing}; unmapped: ${counts.unmapped}; held: ${counts.held}${counts.unmappedInvoices === undefined ? '' : `; unresolved invoices: ${counts.unmappedInvoices}`}. These counts do not confirm billing or settlement completion.`};
  return {supported:Boolean(reported),connected:clockIsManaged(world),state:reported?.phase || 'Status unavailable',
    phase:reported?.phase,physicalThrough:reported?.physicalThrough,recipientThrough:reported?.clock?.slice(0,10),
    recipientClock:reported?.clock,lastCompletedDay:reported?.physicalThrough ? addDays(reported.physicalThrough,-1) : undefined,
    revision:reported?.revision,allowedActions,transport,processing,business,pendingCommand:pending,locked};
}
