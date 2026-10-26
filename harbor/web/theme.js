'use strict';
// Loaded before styles to prevent a light/dark flash when the desktop opens.
let harbourAppearance={theme:'dark',timeFormat:'24'};
try{const saved=JSON.parse(localStorage.getItem('harbour.appearance.v1')||'{}');harbourAppearance.theme=saved.theme==='light'?'light':'dark';harbourAppearance.timeFormat=saved.timeFormat==='12'?'12':'24';}catch{}
function applyHarbourAppearance(){
  document.documentElement.dataset.theme=harbourAppearance.theme;
  document.documentElement.style.colorScheme=harbourAppearance.theme;
  document.querySelector('meta[name=theme-color]')?.setAttribute('content',harbourAppearance.theme==='light'?'#f4f5f7':'#151619');
}
function saveHarbourAppearance(values){
  if(values.theme==='light'||values.theme==='dark')harbourAppearance.theme=values.theme;
  if(values.timeFormat==='12'||values.timeFormat==='24')harbourAppearance.timeFormat=values.timeFormat;
  applyHarbourAppearance();
  try{localStorage.setItem('harbour.appearance.v1',JSON.stringify(harbourAppearance));}catch{}
  document.querySelectorAll('[data-theme-choice]').forEach(button=>{const selected=button.dataset.themeChoice===harbourAppearance.theme;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});
  if(typeof tickClock==='function')tickClock();
}
applyHarbourAppearance();
