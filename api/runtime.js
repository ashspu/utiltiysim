import { WorkOS } from '@workos-inc/node';
import { config, identity, reply, sameOrigin } from '../server/auth.mjs';
import { grantsFor, permits, capabilityFor } from '../server/permissions.mjs';

export function createRuntimeHandler({env=process.env, client=cfg=>new WorkOS(cfg.apiKey,{clientId:cfg.clientId}), fetcher=fetch}={}) {
return async function handler(req, res) {
  try {
    const cfg = config(env);
    if (req.method !== 'GET' && !sameOrigin(req, cfg)) return reply(res, 403, { detail: 'Request origin refused' });
    const auth = await identity(req, res, cfg, client(cfg));
    if (!auth) return reply(res, 401, { detail: 'Sign in to open this workspace.' });
    const url = new URL(req.url, cfg.origin);
    const path = url.searchParams.get('path') || '';
    const town = url.searchParams.get('town');
    if (url.searchParams.getAll('path').length !== 1 || url.searchParams.getAll('town').length !== 1 || !/^[a-z0-9][a-z0-9-]{0,99}$/.test(town || '')) {
      return reply(res, 400, { detail: 'Choose exactly one valid world and action.' });
    }
    const capability = capabilityFor(req.method, path);
    const grants = auth.user.emailVerified ? grantsFor(auth.user.id,env) : [];
    if (!capability || !permits(grants, capability, town)) return reply(res, 403, { detail: 'Your account does not have permission for this action in this world.' });
    const base = env.UTILITYSIM_RUNTIME_URL;
    const token = env.UTILITYSIM_RUNTIME_TOKEN;
    if (!base || !token) return reply(res, 503, { detail: 'The hosted runtime is not connected yet. Your saved local worlds are unchanged.' });
    const target = new URL(base);
    if (target.protocol !== 'https:' || target.username || target.password || target.search || target.hash) throw new Error('Invalid runtime');
    target.pathname = target.pathname.replace(/\/$/, '') + '/atlas/api/' + path;
    for (const [key, value] of url.searchParams) if (key !== 'path') target.searchParams.append(key, value);
    const body = req.body;
    // The runtime verifies its internal townId against the selected catalog slug.
    // These are different identifiers; authorization is bound to the URL's town.
    const upstream = await fetcher(target, { method: req.method, redirect: 'error', signal: AbortSignal.timeout(25000),
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      ...(req.method === 'POST' ? { body: JSON.stringify(body || {}) } : {}) });
    const data = await upstream.json();
    return reply(res, upstream.status, data);
  } catch {
    console.error('UtilitySim runtime gateway request failed');
    return reply(res, 503, { detail: 'The hosted runtime is temporarily unavailable.' });
  }
};
}
export default createRuntimeHandler();
