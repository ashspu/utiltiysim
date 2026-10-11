import { ecosystemMarkup } from './welcome_ecosystem.mjs';
// Preserve the agreed illustrated story. The public surface
// has one application action: WorkOS login. World selection lives behind auth.
export function hostedWelcome(source) {
  const start = source.indexOf('<section id="welcome-page"');
  const end = source.indexOf('<section id="map-page"', start);
  if (start < 0 || end < 0) throw new Error('UtilitySim welcome section is missing');
  let welcome = source.slice(start, end);
  function replace(pattern, value) {
    if (!pattern.test(welcome)) throw new Error(`Welcome integration needs review: ${pattern}`);
    welcome = welcome.replace(pattern, value);
  }
  replace(/<header class="welcome-masthead">[\s\S]*?<\/header>/, '');
  replace(/<dialog id="welcome-sign-in-dialog"[\s\S]*?<\/dialog>/, '');
  replace(/<section class="saved-world-section">[\s\S]*?<\/section>/, '');
  replace(/<img id="hero-image"[^>]+>/, '<img id="hero-image" src="/assets/lantern-harbour-welcome.webp" srcset="/assets/lantern-harbour-welcome-small.webp 1266w, /assets/lantern-harbour-welcome.webp 2532w" sizes="(max-width:760px) 100vw, 58vw" fetchpriority="high" width="2532" height="2486" alt="The complete Lantern Harbour illustrated map, showing its marina, waterfront neighborhoods, connected streets and central park">');
  replace(/<span id="hero-geography"[^>]*>[\s\S]*?<\/span>/, '<span id="hero-geography" class="welcome-art-caption">Lantern Harbour · whole-map illustration</span>');
  replace(/<section class="welcome-connections"[\s\S]*?<\/section>/, '');
  replace(/<section class="welcome-ecosystem">[\s\S]*?<\/section>/, ecosystemMarkup());
  replace(/<div class="welcome-hero">/, `<div class="welcome-hero"><div class="hero-brand"><img src="/brand/utility-studio-icon-color.svg" alt="" width="64" height="64"><span>UtilitySim</span></div>`);
  replace(/<div class="welcome-actions">[\s\S]*?<\/div>/, '<div class="welcome-actions"><a id="sign-in" class="primary big" href="/api/auth/login?returnTo=%2Fworkspace.html">Log in <span aria-hidden="true">→</span></a></div>');
  // Informational ecosystem cards and chapters remain; they do not open apps.
  welcome = welcome.replace(/<button class="text-button" data-page="[^"]+">[\s\S]*?<\/button>/g, '');
  welcome = welcome.replace(/<button data-page="connections">([\s\S]*?)<b>→<\/b><\/button>/g, '<div class="welcome-connection-card">$1</div>');
  welcome = welcome.replace(/<button data-story-jump="(\d)"[^>]*>([\s\S]*?)<\/button>/g, '<span data-story-step="$1">$2</span>');
  welcome = welcome.replace(/Civic Atlas/g, 'UtilitySim');
  if (/data-page=|data-scroll-target=|<button\b/.test(welcome)) throw new Error('Public welcome contains an unexpected action');
  // The same icon shapes used in app.js, without booting the world or WebGL.
  const icons = {
    map: 'm3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2z M9 3v16 M15 5v16',
    overview: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    sliders: 'M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6',
    activity: 'M2 12h5l3-8 4 16 3-8h5',
    connections: 'M9 5h6 M5 9v6 M19 9v6 M9 19h6 M3 3h6v6H3z M15 3h6v6h-6z M3 15h6v6H3z M15 15h6v6h-6z',
  };
  welcome = welcome.replace(/<i data-icon="(\w+)"><\/i>/g, (_, name) => {
    if (!icons[name]) throw new Error(`Missing welcome icon: ${name}`);
    return `<i><svg class="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${icons[name]}"/></svg></i>`;
  });
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#112e3f"><title>UtilitySim</title>
<link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/welcome.css"><link rel="stylesheet" href="/landing.css"></head>
<body data-view="welcome"><main>${welcome}</main><script type="module" src="/welcome.js"></script><script type="module" src="/landing.js"></script></body></html>`;
}
