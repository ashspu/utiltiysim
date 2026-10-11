import { readSession, signOut, loginUrl, escapeHtml as esc } from './shell-session.js';
const status = document.getElementById('account-status');
document.getElementById('sign-out').onclick = () => signOut().catch(() => { status.textContent = 'Could not log out. Please try again.'; });
async function start() {
  try {
    const session = await readSession();
    if (!session.authenticated) { location.replace(loginUrl('/workspace.html')); return; }
    if (!session.grants.length) { status.textContent = 'Your account is awaiting workspace access from an administrator.'; return; }
    status.textContent = `Welcome, ${session.user.name || session.user.email}. Choose a town to explore.`;
    const response = await fetch('/presets/catalog.json');
    if (!response.ok) throw new Error('Catalog unavailable');
    const { presets } = await response.json();
    const allowed = presets.filter(town => session.grants.some(g => g.town === '*' || g.town === town.id));
    document.getElementById('worlds').innerHTML = allowed.map(town => `<article class="world"><img src="/presets/${encodeURIComponent(town.id)}/overview.webp" alt="${esc(town.name)} town overview" loading="lazy"><div><span class="eyebrow">${Number(town.targetHomes).toLocaleString()} HOMES · TOWN MODEL</span><h2>${esc(town.name)}</h2><p>${esc(town.character)}</p><a href="/library.html?town=${encodeURIComponent(town.id)}#overview">Open workspace <span aria-hidden="true">→</span></a></div></article>`).join('');
    if (!allowed.length) status.textContent = 'No available towns match your workspace access. Contact your administrator.';
  } catch { status.textContent = 'Your workspace could not be loaded. Please reload the page.'; }
}
start();
