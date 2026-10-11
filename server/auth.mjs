import { WorkOS } from '@workos-inc/node';
import { sealData, unsealData } from 'iron-session';
import { randomBytes, timingSafeEqual, createHash } from 'node:crypto';
import { grantsFor } from './permissions.mjs';

export function config(env = process.env) {
  for (const key of ['WORKOS_API_KEY', 'WORKOS_CLIENT_ID', 'WORKOS_COOKIE_PASSWORD', 'WORKOS_REDIRECT_URI']) {
    if (!env[key]) throw new Error('Authentication configuration missing');
  }
  if (env.WORKOS_COOKIE_PASSWORD.length < 32) throw new Error('Invalid cookie password');
  const callback = new URL(env.WORKOS_REDIRECT_URI);
  const local = ['localhost', '127.0.0.1'].includes(callback.hostname);
  if (callback.pathname !== '/api/auth/callback' || (!local && callback.protocol !== 'https:') || callback.search || callback.hash) throw new Error('Invalid callback');
  return { apiKey: env.WORKOS_API_KEY, clientId: env.WORKOS_CLIENT_ID, password: env.WORKOS_COOKIE_PASSWORD,
    callback: callback.href, origin: callback.origin, secure: !local };
}
export function cookies(req) {
  return Object.fromEntries((req.headers.cookie || '').split(';').flatMap(part => {
    const i = part.indexOf('=');
    if (i < 1) return [];
    try { return [[part.slice(0, i).trim(), decodeURIComponent(part.slice(i + 1))]]; } catch { return []; }
  }));
}
export function setCookie(res, name, value, cfg, age = 604800) {
  const cookie = `${name}=${encodeURIComponent(value)}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${age}${cfg.secure ? '; Secure' : ''}`;
  const previous = res.getHeader('Set-Cookie') || [];
  res.setHeader('Set-Cookie', [...(Array.isArray(previous) ? previous : [previous]), cookie]);
}
export function safeReturn(value) {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || /[\\\r\n]/.test(value)) return '/';
  const url = new URL(value, 'https://utilitysim.invalid');
  if (!['/', '/workspace.html', '/library.html'].includes(url.pathname)) return '/';
  return url.pathname + url.search + url.hash;
}
export function sameOrigin(req, cfg) { return req.headers.origin === cfg.origin; }
export function reply(res, status, data) {
  res.statusCode = status;
  res.setHeader('Cache-Control', 'private, no-store');
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(data));
}
function redirect(res, target) { res.statusCode = 303; res.setHeader('Location', target); res.end(); }
export async function identity(req, res, cfg, workos) {
  const raw = cookies(req)['utilitysim-session'];
  if (!raw) return null;
  try {
    const session = workos.userManagement.loadSealedSession({ sessionData: raw, cookiePassword: cfg.password });
    let result = await session.authenticate();
    if (!result.authenticated) {
      result = await session.refresh();
      if (result.authenticated && result.sealedSession) setCookie(res, 'utilitysim-session', result.sealedSession, cfg);
    }
    if (result.authenticated) return { user: result.user, session };
  } catch { /* A corrupt or revoked cookie must not trap the browser in a failed session. */ }
  setCookie(res, 'utilitysim-session', '', cfg, 0);
  return null;
}
export function createAuthHandler({ env = process.env, client = cfg => new WorkOS(cfg.apiKey, { clientId: cfg.clientId }) } = {}) {
  return async function handler(req, res) {
    res.setHeader('Cache-Control', 'private, no-store');
    res.setHeader('Referrer-Policy', 'no-referrer');
    let cfg;
    try {
      cfg = config(env);
      const url = new URL(req.url, cfg.origin);
      const action = url.pathname.split('/').at(-1);
      const workos = client(cfg);
      if (action === 'login' && req.method === 'GET') {
        const returnTo = safeReturn(url.searchParams.get('returnTo') || '/workspace.html');
        // Existing valid sessions enter the workspace through the same login
        // endpoint, without creating another identity or selecting a town.
        if (await identity(req, res, cfg, workos)) return redirect(res, returnTo);
        const nonce = randomBytes(32).toString('base64url');
        const verifier = randomBytes(32).toString('base64url');
        const state = await sealData({ nonce, verifier, returnTo }, { password: cfg.password, ttl: 600 });
        setCookie(res, 'utilitysim-login', state, cfg, 600);
        return redirect(res, workos.userManagement.getAuthorizationUrl({ provider: 'authkit', clientId: cfg.clientId,
          redirectUri: cfg.callback, state: nonce, codeChallenge: createHash('sha256').update(verifier).digest('base64url'), codeChallengeMethod: 'S256' }));
      }
      if (action === 'callback' && req.method === 'GET') {
        let state = {};
        try { state = await unsealData(cookies(req)['utilitysim-login'] || '', { password: cfg.password, ttl: 600 }); } catch { /* Treat malformed state as an expired login. */ }
        setCookie(res, 'utilitysim-login', '', cfg, 0);
        const actual = Buffer.from(url.searchParams.get('state') || '');
        const expected = Buffer.from(state.nonce || '');
        if (!expected.length || actual.length !== expected.length || !timingSafeEqual(actual, expected) || !url.searchParams.get('code')) {
          return reply(res, 400, { error: 'The sign-in request expired or could not be verified. Start sign-in again.' });
        }
        const result = await workos.userManagement.authenticateWithCode({ clientId: cfg.clientId, code: url.searchParams.get('code'), codeVerifier: state.verifier,
          session: { sealSession: true, cookiePassword: cfg.password } });
        if (!result.sealedSession) throw new Error('Session not sealed');
        setCookie(res, 'utilitysim-session', result.sealedSession, cfg);
        return redirect(res, safeReturn(state.returnTo));
      }
      if (action === 'session' && req.method === 'GET') {
        const auth = await identity(req, res, cfg, workos);
        if (!auth) return reply(res, 200, { authenticated: false });
        const grants = auth.user.emailVerified ? grantsFor(auth.user.id, env) : [];
        return reply(res, 200, { authenticated: true, user: { id: auth.user.id, email: auth.user.email, name: [auth.user.firstName, auth.user.lastName].filter(Boolean).join(' ') }, grants, runtimeConfigured: Boolean(env.UTILITYSIM_RUNTIME_URL && env.UTILITYSIM_RUNTIME_TOKEN) });
      }
      if (action === 'logout' && req.method === 'POST') {
        if (!sameOrigin(req, cfg)) return reply(res, 403, { error: 'Request origin refused' });
        const auth = await identity(req, res, cfg, workos);
        setCookie(res, 'utilitysim-session', '', cfg, 0);
        setCookie(res, 'utilitysim-login', '', cfg, 0);
        return reply(res, 200, { url: auth ? await auth.session.getLogoutUrl({ returnTo: cfg.origin + '/' }) : '/' });
      }
      return reply(res, 405, { error: 'Method or route not allowed' });
    } catch {
      // Never log codes, cookies, provider responses or API keys.
      console.error('UtilitySim authentication request failed');
      return reply(res, 503, { error: cfg ? 'Sign-in is temporarily unavailable. Please try again.' : 'Sign-in is not configured on this deployment.' });
    }
  };
}
