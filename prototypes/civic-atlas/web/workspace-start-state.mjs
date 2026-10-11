export function initializationProgress(record) {
  if (!Number.isInteger(record.appliedCommands) || record.appliedCommands < 0) return '';
  return Number.isInteger(record.totalCommands) && record.totalCommands >= record.appliedCommands
    ? `${record.appliedCommands} of ${record.totalCommands} setup commands committed.`
    : `${record.appliedCommands} setup commands committed.`;
}
export function retainCreationResult(record, world) {
  if (!/^[0-9a-f]{32}$/.test(world.id || '')) throw new Error('The runtime returned an invalid simulation identifier.');
  if (record.pendingWorldId && record.pendingWorldId !== world.id) throw new Error('The original start request returned a different simulation. Keep the retained request for recovery.');
  const next = structuredClone(record);
  if (world.available === true) {
    delete next.pendingWorldId; delete next.appliedCommands; delete next.totalCommands;
    next.worldId = world.id;
  } else {
    next.pendingWorldId = world.id;
    if (Number.isInteger(world.initialization?.appliedCommands)) next.appliedCommands = world.initialization.appliedCommands;
    if (Number.isInteger(world.initialization?.totalCommands)) next.totalCommands = world.initialization.totalCommands;
  }
  return next;
}
