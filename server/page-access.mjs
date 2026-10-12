import { WorkOS } from '@workos-inc/node';
import { next } from '@vercel/functions';
import { config, identity } from './auth.mjs';
import { grantsFor, permits } from './permissions.mjs';

// Only the introduction and its assets are public. API handlers enforce their
// own authorization; static workspace files must pass this gate before cache.
const publicPaths = new Set(['/', '/index.html', '/landing.js', '/landing.css', '/welcome.js', '/welcome.css', '/style.css',
  '/brand/utility-studio-icon-color.svg', '/favicon.ico',
  ...['civic-welcome-landscape.png','civic-block-pine-willow.png','civic-city-studies.png','civic-block-maple-park.png','civic-block-main-north.png'].map(file => '/assets/' + file)]);
// The workspace must boot before it can explain missing/unverified grants.
// Only its exact static dependencies belong here; maps and owner controls keep
// their independent grant checks below.
const signedInPaths = new Set(['/workspace.html','/workspace.js','/workspace.css','/shell-session.js',
  '/viewer/setup.css','/physical-slider-form.css','/physical-slider-form.mjs','/workspace-start-state.mjs']);
const townId = /^[a-z0-9][a-z0-9-]{0,99}$/;
export function createPageAccess({ env = process.env, client = cfg => new WorkOS(cfg.apiKey, { clientId: cfg.clientId }), pass = next } = {}) {
  return async function pageAccess(request) {
    const url = new URL(request.url);
    let path;
    try { path = decodeURIComponent(url.pathname); } catch { return new Response('Invalid path', {status:400}); }
    if (publicPaths.has(path) || path.startsWith('/api/auth/') || path === '/api/runtime' || path === '/api/setups' || path === '/api/compute' || path === '/api/operator' || path.startsWith('/atlas/api/')) return pass();
    const headers = new Headers({'Cache-Control':'private, no-store','Vercel-CDN-Cache-Control':'no-store'});
    const pending = new Map();
    const res = { getHeader: key => pending.get(key), setHeader: (key,value) => pending.set(key,value) };
    const finish = response => {
      pending.forEach((values,key) => (Array.isArray(values) ? values : [values]).forEach(value => response.headers.append(key,value)));
      return response;
    };
    const respond = (status, message) => finish(new Response(message,{status,headers}));
    const redirect = target => { const h = new Headers(headers); h.set('Location',target); return finish(new Response(null,{status:303,headers:h})); };
    try {
      const cfg = config(env);
      const auth = await identity({headers:{cookie:request.headers.get('cookie') || ''}},res,cfg,client(cfg));
      let town = null;
      if (path === '/library.html') {
        if (url.searchParams.getAll('town').length > 1) return respond(400,'Choose one town.');
        town = url.searchParams.get('town');
      } else if (path.startsWith('/presets/shared/') && path.endsWith('.html')) {
        if (url.searchParams.getAll('preset').length !== 1) return auth ? redirect('/workspace.html') : redirect('/api/auth/login?returnTo=%2Fworkspace.html');
        town = url.searchParams.get('preset');
      } else if (path.startsWith('/presets/') && !path.startsWith('/presets/shared/') && path !== '/presets/catalog.json') {
        town = path.split('/')[2];
      }
      if (town !== null && !townId.test(town)) return respond(400,'Invalid town.');
      if (!auth) {
        if (path.endsWith('.html') || !path.split('/').at(-1).includes('.')) {
          const returnTo = path === '/library.html' && town ? path + url.search : town ? '/library.html?town=' + encodeURIComponent(town) : '/workspace.html';
          return redirect('/api/auth/login?returnTo=' + encodeURIComponent(returnTo));
        }
        return respond(401,'Log in to UtilitySim to access this resource.');
      }
      if (!['GET','HEAD'].includes(request.method)) return respond(405,'Method not allowed.');
      if (path === '/library.html' && !town) return redirect('/workspace.html');
      const grants = auth.user.emailVerified ? grantsFor(auth.user.id,env) : [];
      if (path.startsWith('/compute-connection.') && !grants.some(grant => grant.role === 'owner')) return respond(403,'Owner access required.');
      if (!signedInPaths.has(path) && (town ? !permits(grants,'world.view',town) : !grants.length)) return respond(403,'Workspace access required.');
      return finish(pass({headers}));
    } catch {
      return respond(503,'UtilitySim sign-in is temporarily unavailable. Please try again.');
    }
  };
}
