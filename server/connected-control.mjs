import { fail } from './compute-connector.mjs';

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const publicId = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
export const connectedActions = Object.freeze(['pause', 'resume', 'advance']);
export function canonicalDay(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
}
export function canonicalInstant(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(value)
    && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().replace('.000Z', 'Z') === value;
}
export function managedClock(world) {
  if (!Object.hasOwn(world, 'connectedClock')) return false;
  const marker = world.connectedClock;
  if (!marker || typeof marker !== 'object' || Array.isArray(marker) || typeof marker.configured !== 'boolean') {
    fail(502, 'Runtime clock ownership could not be verified.');
  }
  return marker.configured || marker.manualAdvanceAllowed === false;
}
export function validateConnectedCommand(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).some(key => !['commandId', 'expectedRevision', 'action', 'through'].includes(key))
      || !uuid.test(value.commandId || '') || !Number.isSafeInteger(value.expectedRevision) || value.expectedRevision < 0
      || !connectedActions.includes(value.action)
      || (value.action === 'advance' ? !canonicalInstant(value.through) : Object.hasOwn(value, 'through'))) {
    fail(422, 'Use a retained command identity, current revision and supported connected action.');
  }
  return value;
}

// Browser output is a projection, never a generic controller response proxy.
// Machine capabilities, controller URLs and private job payloads cannot escape.
export function publicConnectedStatus(value, marker) {
  if (!marker?.configured || typeof marker.runId !== 'string' || typeof marker.controllerId !== 'string'
      || !publicId.test(marker.runId) || !publicId.test(marker.controllerId)
      || !value || value.schemaVersion !== 'connected-status/1'
      || value.runId !== marker.runId || value.controllerId !== marker.controllerId
      || !(canonicalDay(value.physicalThrough) || value.physicalThrough === null && value.producerAvailable === false)
      || value.producerAvailable !== undefined && typeof value.producerAvailable !== 'boolean'
      || !canonicalInstant(value.clock)
      || !['paused', 'idle', 'running', 'failed'].includes(value.phase)
      || !Number.isSafeInteger(value.revision) || value.revision < 0
      || !Array.isArray(value.supportedActions) || value.supportedActions.some(action => !connectedActions.includes(action))
      || value.target != null && !canonicalInstant(value.target)
      || value.activeCommandId != null && (typeof value.activeCommandId !== 'string' || !publicId.test(value.activeCommandId))) {
    fail(502, 'The controller did not confirm this connected world.');
  }
  const counts = {};
  for (const key of ['pending', 'failed', 'missing', 'unmapped', 'held']) {
    const count = value.counts?.[key];
    if (!Number.isSafeInteger(count) || count < 0) fail(502, 'The controller returned invalid progress counts.');
    counts[key] = count;
  }
  if (value.counts?.unmappedInvoices !== undefined) {
    if (!Number.isSafeInteger(value.counts.unmappedInvoices) || value.counts.unmappedInvoices < 0) fail(502, 'The controller returned invalid invoice progress.');
    counts.unmappedInvoices = value.counts.unmappedInvoices;
  }
  const result = { schemaVersion: value.schemaVersion, runId: value.runId, controllerId: value.controllerId,
    physicalThrough: value.physicalThrough, clock: value.clock, phase: value.phase,
    revision: value.revision, target: value.target ?? null, activeCommandId: value.activeCommandId ?? null,
    technicalError: Boolean(value.technicalError), counts, supportedActions: [...value.supportedActions] };
  if (typeof value.errorJobId === 'string' && /^[A-Za-z0-9_.:-]{1,200}$/.test(value.errorJobId)) result.errorJobId = value.errorJobId;
  if (value.producerAvailable !== undefined) result.producerAvailable = value.producerAvailable;
  if (value.lastCommand != null) {
    const command = value.lastCommand;
    if (typeof command.commandId !== 'string' || !publicId.test(command.commandId) || !['accepted','completed','failed'].includes(command.status)
        || !connectedActions.includes(command.action) || !Number.isSafeInteger(command.acceptedRevision)
        || command.acceptedRevision < 1 || command.acceptedRevision > value.revision
        || (command.action === 'advance' ? !canonicalInstant(command.target) : command.target != null)) {
      fail(502, 'The controller returned invalid command progress.');
    }
    result.lastCommand = {commandId: command.commandId, status: command.status, action: command.action,
      target: command.target ?? null, acceptedRevision: command.acceptedRevision};
  }
  return result;
}
export function publicConnectedReceipt(value, command) {
  if (!value || value.commandId !== command.commandId || !['accepted', 'completed'].includes(value.status)
      || !Number.isSafeInteger(value.revision) || value.revision !== command.expectedRevision + 1) {
    fail(502, 'The controller did not confirm the retained command. Retry its original identity.');
  }
  return {commandId: value.commandId, status: value.status, revision: value.revision};
}
