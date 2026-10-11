export const hosted = Boolean(document.querySelector('meta[name="utilitysim-hosted"]'));
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const loginUrl = returnTo => '/api/auth/login?returnTo=' + encodeURIComponent(returnTo || '/');
export async function readSession() {
  const response = await fetch('/api/auth/session', { cache: 'no-store' });
  if (!response.ok) throw new Error('Sign-in unavailable');
  return response.json();
}
export async function signOut() {
  const response = await fetch('/api/auth/logout', { method: 'POST' });
  if (!response.ok) throw new Error('Sign-out failed');
  const { url } = await response.json();
  location.assign(url);
}
export async function requireWorkspace(town) {
  if (!hosted) return true;
  const session = await readSession();
  if (!session.authenticated || !session.grants.some(g => g.town === '*' || g.town === town)) {
    location.replace('/?returnTo=' + encodeURIComponent(location.pathname + location.search + location.hash));
    return false;
  }
  return true;
}
