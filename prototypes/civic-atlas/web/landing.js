import { readSession, signOut, loginUrl, escapeHtml as esc } from './shell-session.js';
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
// Existing explicit deep links survive; a bare root never restores or chooses a map.
const deepLink = params.has('town') ? '/library.html' + location.search + location.hash : null;
const requested = params.get('returnTo');
const returnTo = deepLink || (requested?.startsWith('/library.html?') && !requested.includes('\\') ? requested : '/');
$('sign-in').href = $('primary-sign-in').href = loginUrl(returnTo);
$('sign-out').onclick = () => signOut().catch(() => { $('account-status').textContent = 'Could not sign out. Please try again.'; });

async function start() {
  let session;
  try {
    session = await readSession();
    if (session.authenticated) {
      $('sign-in').hidden = $('primary-sign-in').hidden = true;
      $('sign-out').hidden = false;
      $('account-status').textContent = session.grants.length
        ? `Signed in as ${session.user.name || session.user.email}. ${session.runtimeConfigured ? 'Your runtime is connected.' : 'Map exploration is available. The hosted runtime is not connected yet.'}`
        : `Signed in as ${session.user.email}. Your account is awaiting workspace access from an administrator.`;
      if (deepLink && session.grants.some(g => g.town === '*' || g.town === params.get('town'))) { location.replace(deepLink); return; }
    }
  } catch { $('account-status').textContent = 'Sign-in is temporarily unavailable. Please try again shortly.'; }
  try {
    const response = await fetch('/presets/catalog.json');
    if (!response.ok) throw new Error('Catalog unavailable');
    const { presets } = await response.json();
    $('worlds').innerHTML = presets.map(town => {
      const target = '/library.html?town=' + encodeURIComponent(town.id) + '#overview';
      const allowed = session?.authenticated && session.grants.some(g => g.town === '*' || g.town === town.id);
      const action = allowed ? `<a class="button" href="${esc(target)}">Open workspace <span aria-hidden="true">↗</span></a>`
        : session?.authenticated ? '<span class="count">WORKSPACE ACCESS REQUIRED</span>'
        : `<a class="button" href="${esc(loginUrl(target))}">Sign in to open <span aria-hidden="true">↗</span></a>`;
      return `<article class="world"><img src="/presets/${encodeURIComponent(town.id)}/overview.webp" alt="${esc(town.name)} town overview" loading="lazy"><div class="world-body"><span class="count">${Number(town.targetHomes).toLocaleString()} HOMES</span><h3>${esc(town.name)}</h3><p>${esc(town.character || 'A persistent town and its utility network.')}</p>${action}</div></article>`;
    }).join('');
  } catch { $('worlds').textContent = 'The town library could not be loaded. Please reload the page.'; }
}
start();
