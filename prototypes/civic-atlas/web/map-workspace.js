// The map owns the viewport. Navigation and tools are explicitly opened overlays.
export function createMapWorkspace(){
 const $=id=>document.getElementById(id),sidebar=document.querySelector('.sidebar'),page=$('map-page');
 const navigation=document.createElement('div');navigation.className='navigation-controls';
 navigation.innerHTML='<button id="collapse-navigation" aria-label="Collapse navigation" title="Collapse navigation">‹</button><button id="hide-navigation" aria-label="Hide navigation" title="Hide navigation">×</button>';
 sidebar.prepend(navigation);
 for(const button of sidebar.querySelectorAll('nav button')){
  button.setAttribute('aria-label',button.textContent.trim());button.title=button.textContent.trim();
  for(const node of [...button.childNodes])if(node.nodeType===Node.TEXT_NODE&&node.textContent.trim()){
   const label=document.createElement('span');label.className='nav-label';node.replaceWith(label);label.append(node);
  }
 }
 const launcher=document.createElement('button');launcher.id='open-navigation';launcher.className='map-floating-button';launcher.setAttribute('aria-label','Show navigation');launcher.setAttribute('aria-expanded','false');launcher.innerHTML='☰';
 document.body.append(launcher);
 const toolsButton=document.createElement('button');toolsButton.id='toggle-map-options';toolsButton.className='map-floating-button';toolsButton.setAttribute('aria-label','Map options');toolsButton.setAttribute('aria-expanded','false');toolsButton.setAttribute('aria-controls','map-options');toolsButton.innerHTML='<span aria-hidden="true">☷</span><span>Map options</span>';
 page.append(toolsButton);
 const panel=document.createElement('section');panel.id='map-options';panel.hidden=true;panel.setAttribute('aria-label','Map options');
 panel.innerHTML='<header><div><span class="eyebrow">YOUR VIEW</span><h2>Map options</h2></div><button id="close-map-options" aria-label="Close map options">×</button></header>';
 for(const selector of ['.map-toolbar','.map-controls','.place-tour','.map-caption','#map-legend','#sketch-tools','.map-footer'])panel.append(page.querySelector(selector));
 page.append(panel);
 const selected=document.createElement('div');selected.id='map-selection';selected.hidden=true;selected.innerHTML='<span id="map-selection-name"></span><button id="view-property">View records</button><button id="clear-map-selection" aria-label="Clear selected property">×</button>';page.append(selected);
 let nav='expanded',lastView=null;
 function setNavigation(value){
  nav=value;document.body.dataset.navigation=value;
  sidebar.inert=value==='hidden';launcher.setAttribute('aria-expanded',String(value!=='hidden'));
  $('collapse-navigation').textContent=value==='rail'?'›':'‹';
  $('collapse-navigation').setAttribute('aria-label',value==='rail'?'Expand navigation':'Collapse navigation');
 }
 function options(show){panel.hidden=!show;toolsButton.setAttribute('aria-expanded',String(show));if(show)$('close-map-options').focus();else toolsButton.focus();}
 launcher.onclick=()=>setNavigation(nav==='hidden'?'expanded':'hidden');
 $('collapse-navigation').onclick=()=>setNavigation(nav==='rail'?'expanded':'rail');
 $('hide-navigation').onclick=()=>{setNavigation('hidden');launcher.focus();};
 toolsButton.onclick=()=>options(panel.hidden);$('close-map-options').onclick=()=>options(false);
 $('view-property').onclick=()=>{$('property-dialog').showModal();};
 $('close-property-dialog').onclick=()=>{$('property-dialog').close();$('view-property').focus();};
 $('clear-map-selection').onclick=()=>$('close-inspector')?.click();
 $('property-dialog').addEventListener('click',event=>{if(event.target===$('property-dialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
 document.addEventListener('keydown',event=>{
  if(document.body.dataset.view!=='map'||event.target.closest('input,textarea,select'))return;
  if(event.key==='Escape'&&!$('property-dialog').open){if(!panel.hidden)options(false);setNavigation('hidden');}
  if(event.key==='/'&&!$('property-dialog').open){options(true);$('map-search').focus();event.preventDefault();}
 });
 return {options,setNavigation,selection(home){selected.hidden=!home;$('map-selection-name').textContent=home?.address||'';if(!home)$('property-dialog').close();},view(next){
  if(next!==lastView){setNavigation(next==='map'?'hidden':'expanded');panel.hidden=true;toolsButton.setAttribute('aria-expanded','false');$('property-dialog').close();lastView=next;}
 }};
}
