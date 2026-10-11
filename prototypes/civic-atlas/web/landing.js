// The public introduction has one application action. Explicit old town links
// are carried through WorkOS; a bare root always enters the workspace chooser.
const params = new URLSearchParams(location.search);
const requested = params.get('returnTo');
const target = params.has('town') ? '/library.html' + location.search + location.hash
  : requested?.startsWith('/library.html?') && !requested.includes('\\') ? requested : '/workspace.html';
document.getElementById('sign-in').href = '/api/auth/login?returnTo=' + encodeURIComponent(target);
