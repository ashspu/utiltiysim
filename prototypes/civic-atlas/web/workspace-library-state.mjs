const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
export const lifecycleKey = actor => `utilitysim:setup-actions:${actor}`;
export function readLifecycle(storage, actor) {
  const value = storage.getItem(lifecycleKey(actor));
  if (!value) return null;
  const command = JSON.parse(value);
  if (!command || !['delete', 'restore'].includes(command.action) || !uuid.test(command.id)
      || !uuid.test(command.commandId) || !Number.isSafeInteger(command.revision) || command.revision < 1
      || Object.keys(command).some(key => !['action', 'id', 'revision', 'commandId'].includes(key))) {
    throw new Error('A saved library action needs recovery. No new action has been sent.');
  }
  return command;
}
export function retainLifecycle(storage, actor, command) {
  const pending = readLifecycle(storage, actor);
  if (pending && JSON.stringify(pending) !== JSON.stringify(command)) throw new Error('Recover the previous library action first.');
  storage.setItem(lifecycleKey(actor), JSON.stringify(command));
}
export function settleLifecycle(storage, actor, command, result) {
  const expected = command.action === 'delete' ? 'deleted' : 'setup';
  if (result?.setup?.id !== command.id || result.setup.revision !== command.revision + 1
      || result.setup.status !== expected) throw new Error('The library action has not been confirmed. Retry its original request.');
  const pending = readLifecycle(storage, actor);
  if (!pending || JSON.stringify(pending) !== JSON.stringify(command)) throw new Error('The library action changed before confirmation.');
  storage.removeItem(lifecycleKey(actor));
}
export function dismissRejectedLifecycle(storage, actor, command, status) {
  // This dedicated lifecycle API checks exact receipts before its conflict/DTO
  // rejection. Never discard on permission errors or uncertain transport/5xx.
  if (![409,422].includes(status)) throw new Error('Recover the original action before dismissing it.');
  const pending=readLifecycle(storage,actor);
  if (!pending || JSON.stringify(pending)!==JSON.stringify(command)) throw new Error('The library action changed before dismissal.');
  storage.removeItem(lifecycleKey(actor));
}
export function deletionBlocked(start) {
  return Boolean(start && (!start.worldId || start.pendingWorldId));
}
