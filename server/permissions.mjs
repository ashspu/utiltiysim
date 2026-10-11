// Identity comes from WorkOS; application grants are deployment-owned, as in GolfyGolf.
// A new identity has no grants. No email-domain or first-arrival owner bootstrap.
export const roles = Object.freeze({
  owner: ['world.view', 'world.advance', 'billing.view', 'billing.run', 'field.dispatch', 'field.review'],
  operator: ['world.view', 'world.advance', 'billing.view', 'field.dispatch'],
  billing: ['world.view', 'billing.view', 'billing.run'],
  support: ['world.view', 'billing.view', 'field.dispatch'],
  analyst: ['world.view', 'billing.view'],
});

export function grantsFor(userId, env = process.env, now = Date.now()) {
  const registry = JSON.parse(env.UTILITYSIM_ROLE_GRANTS || '{}');
  const entries = registry[userId];
  if (!Array.isArray(entries)) return [];
  return entries.filter(g => g && Object.hasOwn(roles, g.role) &&
    (g.town === '*' || /^[a-z0-9][a-z0-9-]{0,99}$/.test(g.town || '')) &&
    !g.revoked && (!g.expiresAt || Date.parse(g.expiresAt) > now));
}

export function permits(grants, capability, town) {
  return grants.some(g => (g.town === '*' || g.town === town) && roles[g.role]?.includes(capability));
}

export function capabilityFor(method, path) {
  if (method === 'GET') {
    if (['catalog', 'summary', 'state', 'quality', 'integration', 'observations'].includes(path)) return 'world.view';
    if (/^premises\/[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}(?:\/history)?$/.test(path)) return 'world.view';
    if (['billing', 'virtual-systems'].includes(path)) return 'billing.view';
  }
  if (method === 'POST') {
    if (path === 'advance') return 'world.advance';
    if (['billing/ingest', 'billing/run', 'virtual-systems/initialize', 'virtual-systems/ingest', 'virtual-systems/run', 'virtual-systems/invoice-eligible', 'virtual-systems/resolve'].includes(path)) return 'billing.run';
    if (['billing/replace-meter', 'virtual-systems/repair'].includes(path)) return 'field.dispatch';
    if (path === 'virtual-systems/accept-report') return 'field.review';
  }
  return null;
}
