// Relationships transcribed from Greg's original ecosystem diagram.
// Navigation is explanatory on the public page, never an application link.
export const integrationEdges = [
  ['Virtual Systems','Utility Billing One'],
  ['Virtual Systems','M2C App Data Agent'],
  ['Utility Billing One','M2C App Data Agent'],
  ['M2C App Data Agent','M2C Celonis App'],
  ['M2C Celonis App','UCascade'],
  ['UCascade','Utility Billing One'],
];
export const navigationEdges = [
  ['UtilitySim','Utility Billing One'], ['UtilitySim','Virtual Systems'],
  ['UtilitySim','M2C App Data Agent'], ['Virtual Systems','M2C App Data Agent'],
  ['M2C_SEW - Portlet','M2C Celonis App'], ['M2C_SEW - Portlet','UCascade'],
];
export function ecosystemMarkup() {
  const node = (x,y,w,label,sub) => `<g class="ecosystem-node"><rect x="${x}" y="${y}" width="${w}" height="76" rx="10"/><text x="${x+w/2}" y="${y+33}" text-anchor="middle">${label}</text><text class="node-note" x="${x+w/2}" y="${y+55}" text-anchor="middle">${sub}</text></g>`;
  return `<section class="welcome-ecosystem" aria-labelledby="ecosystem-title">
  <div class="ecosystem-intro"><span class="eyebrow">FROM A LIVING TOWN TO A CONNECTED ECOSYSTEM</span><h2 id="ecosystem-title">See the connections. Follow the whole loop.</h2><p>UtilitySim is the starting point for exploring the physical world. The original ecosystem design connects operations, billing and analysis, with a feedback path back to Utility Billing One.</p></div>
  <div class="ecosystem-legend"><span><i class="integration-key"></i>Integration flow</span><span><i class="navigation-key"></i>Navigation flow</span><small>Intended architecture · external connections are not configured</small></div>
  <svg class="ecosystem-diagram" viewBox="0 0 1100 640" role="img" aria-labelledby="ecosystem-svg-title ecosystem-svg-desc">
  <title id="ecosystem-svg-title">UtilitySim ecosystem connections</title><desc id="ecosystem-svg-desc">Red arrows show the integration loop: Virtual Systems to Utility Billing One and M2C App Data Agent; Utility Billing One to the Data Agent; Data Agent to M2C Celonis App, then UCascade, then back to Utility Billing One. Gray arrows show navigation from UtilitySim to billing, Virtual Systems and the Data Agent, from Virtual Systems to the Data Agent, and from M2C_SEW - Portlet to Celonis and UCascade.</desc>
  <defs><marker id="eco-red" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#b94736"/></marker><marker id="eco-gray" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#83959b"/></marker></defs>
  <g class="navigation-lines" fill="none" stroke="#83959b" stroke-width="1.6" marker-end="url(#eco-gray)"><path d="M280 256H318V78H370"/><path d="M280 256H318V208H370"/><path d="M280 256H340V338H610"/><path d="M485 246V279H660V300"/><path d="M280 468H340V438H610"/><path d="M280 468H340V558H610"/></g>
  <g class="integration-lines" fill="none" stroke="#b94736" stroke-width="3" stroke-linejoin="round" marker-end="url(#eco-red)"><path d="M485 170V116"/><path d="M600 78H765V300"/><path d="M600 208H750V300"/><path d="M765 376V400"/><path d="M765 476V520"/><path d="M765 596V620H35V78H370"/></g>
  ${node(65,218,215,'UtilitySim','The physical world')}${node(370,40,230,'Utility Billing One','Billing perspective')}${node(370,170,230,'Virtual Systems','Operational perspective')}${node(610,300,310,'M2C App Data Agent','Data handoff')}${node(610,400,310,'M2C Celonis App','Analysis perspective')}${node(610,520,310,'UCascade','Feedback into billing')}${node(65,430,215,'M2C_SEW - Portlet','Another navigation entry')}
  <text class="loop-label" x="70" y="603">Feedback returns to Utility Billing One</text></svg>
  <div class="ecosystem-reading"><div><h3>Connect the systems</h3><p>Virtual Systems feeds Utility Billing One and M2C App Data Agent. Billing also feeds the Data Agent.</p></div><div><h3>Close the loop</h3><p>M2C App Data Agent → M2C Celonis App → UCascade → Utility Billing One.</p></div><div><h3>Move between perspectives</h3><p>UtilitySim opens the billing, operational and Data Agent perspectives. Virtual Systems also leads to the Data Agent. M2C_SEW - Portlet leads to Celonis and UCascade.</p></div></div>
  </section>`;
}
