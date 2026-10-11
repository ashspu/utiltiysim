import { readSession, signOut, loginUrl, escapeHtml as esc } from './shell-session.js';
const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
// Existing explicit deep links survive; a bare root never restores or chooses a map.
const deepLink = params.has('town') ? '/library.html' + location.search + location.hash : null;
const requested = params.get('returnTo');
const returnTo = deepLink || (requested?.startsWith('/library.html?') && !requested.includes('\\') ? requested : '/');
$('sign-in').href = loginUrl(returnTo);
$('sign-out').onclick = () => signOut().catch(() => { $('account-status').textContent = 'Could not sign out. Please try again.'; });
let session, presets = [], destination = 'map';
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)');
function scrollToSection(id) {
  document.getElementById(id).scrollIntoView({ behavior: reduceMotion.matches ? 'instant' : 'smooth', block: 'start' });
}
// Introduction controls never pick an arbitrary or remembered town. The chosen
// activity is carried into the town links after the user selects their world.
document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.page === 'welcome') { scrollToSection('welcome-page'); return; }
  destination = button.dataset.page === 'activity' ? 'overview' : button.dataset.page;
  $('worlds-guidance').textContent = ({map:'Choose a town to explore its map.', configure:'Choose a town to inspect its setup.', overview:'Choose a town to review its activity.', connections:'Choose a town to view its connections.'})[destination];
  renderWorlds();
  $('welcome-account-panel').hidden = true;
  $('welcome-account-button').setAttribute('aria-expanded', 'false');
  scrollToSection('welcome-worlds');
}));
document.querySelectorAll('[data-scroll-target]').forEach(button => button.addEventListener('click', () => scrollToSection(button.dataset.scrollTarget)));

function renderWorlds() {
  if (!presets.length) return;
  $('worlds').innerHTML = presets.map(town => {
    const target = '/library.html?town=' + encodeURIComponent(town.id) + '#' + destination;
    const allowed = session?.authenticated && session.grants.some(g => g.town === '*' || g.town === town.id);
    const action = allowed ? `<a href="${esc(target)}">Open workspace <span aria-hidden="true">→</span></a>`
      : session?.authenticated ? '<span class="count">WORKSPACE ACCESS REQUIRED</span>'
      : `<a href="${esc(loginUrl(target))}">Sign in to explore <span aria-hidden="true">→</span></a>`;
    return `<article class="world"><img src="/presets/${encodeURIComponent(town.id)}/overview.webp" alt="${esc(town.name)} town overview" loading="lazy"><div class="world-body"><span class="count">${Number(town.targetHomes).toLocaleString()} HOMES · TOWN MODEL</span><h3>${esc(town.name)}</h3><p>${esc(town.character || 'A town and its utility network.')}</p>${action}</div></article>`;
  }).join('');
}

async function start() {
  try {
    session = await readSession();
    if (session.authenticated) {
      $('sign-in').hidden = true;
      $('sign-out').hidden = false;
      $('account-name').textContent = session.user.name || session.user.email;
      $('account-status').textContent = session.grants.length
        ? `Signed in as ${session.user.name || session.user.email}. ${session.runtimeConfigured ? 'Your runtime is connected.' : 'Map exploration is available. The hosted runtime is not connected yet.'}`
        : `Signed in as ${session.user.email}. Your account is awaiting workspace access from an administrator.`;
      if (deepLink && session.grants.some(g => g.town === '*' || g.town === params.get('town'))) { location.replace(deepLink); return; }
    }
  } catch { $('account-status').textContent = 'Sign-in is temporarily unavailable. Please try again shortly.'; }
  try {
    const response = await fetch('/presets/catalog.json');
    if (!response.ok) throw new Error('Catalog unavailable');
    ({ presets } = await response.json());
    renderWorlds();
  } catch { $('worlds').textContent = 'The town library could not be loaded. Please reload the page.'; }
}
start();
