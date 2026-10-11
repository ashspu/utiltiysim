// Keep the agreed Civic Atlas welcome as the visual source of truth. Only its
// account and world-entry controls differ between the local and hosted shells.
export function hostedWelcome(source) {
  const start = source.indexOf('<section id="welcome-page"');
  const end = source.indexOf('<section id="map-page"', start);
  if (start < 0 || end < 0) throw new Error('Civic Atlas welcome section is missing');
  let welcome = source.slice(start, end);
  function replace(pattern, value) {
    if (!pattern.test(welcome)) throw new Error(`Welcome integration needs review: ${pattern}`);
    welcome = welcome.replace(pattern, value);
  }
  replace(/<div id="welcome-account-panel"[\s\S]*?<\/div>/, `<div id="welcome-account-panel" class="welcome-account-panel" hidden>
    <span class="eyebrow">YOUR WORKSPACE</span><strong id="account-name">Welcome to UtilitySim</strong>
    <p id="account-status" role="status">Sign in to open your workspace.</p>
    <button data-page="overview">Choose a world <span>→</span></button>
    <a id="sign-in" href="/api/auth/login">Sign in <span>→</span></a>
    <button id="sign-out" hidden>Sign out <span>→</span></button>
    <a href="/download/">Get the desktop app <span>↗</span></a>
  </div>`);
  replace(/<dialog id="welcome-sign-in-dialog"[\s\S]*?<\/dialog>/, '');
  replace(/Resume Brookfield/, 'Choose a world');
  replace(/Resume world/, 'Explore worlds');
  replace(/<section class="saved-world-section">[\s\S]*?<\/section>/, `<section id="welcome-worlds" class="saved-world-section" aria-labelledby="worlds-title">
    <div class="section-heading"><div><span class="eyebrow">A WORLD READY TO EXPLORE</span><h2 id="worlds-title">Find your place.</h2></div><p id="worlds-guidance" role="status">Choose a town to open its workspace.</p></div>
    <div id="worlds" class="worlds"><p>Loading town library…</p></div>
  </section>
  <footer class="welcome-footer"><span>UtilitySim v2 · Civic Atlas</span><a href="/download/">Get the desktop app →</a></footer>`);
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
<meta name="theme-color" content="#112e3f"><title>Civic Atlas · UtilitySim v2</title>
<link rel="stylesheet" href="/style.css"><link rel="stylesheet" href="/welcome.css"><link rel="stylesheet" href="/landing.css"></head>
<body data-view="welcome"><main>${welcome}</main><script type="module" src="/welcome.js"></script><script type="module" src="/landing.js"></script></body></html>`;
}
