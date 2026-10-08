(function(){
  'use strict';
  const CLASS_PATTERN=/^skin-[a-z0-9-]{1,80}$/;
  const TIERS=['D','C','B','A','S','SS','SSS'];
  window.applyGlobalSkinV1=function(state){
    [...document.body.classList].forEach(name=>{
      if(CLASS_PATTERN.test(name)) document.body.classList.remove(name);
    });
    const active=state&&Array.isArray(state.items)
      ?state.items.find(item=>item&&item.active===true)
      :null;
    const cssClass=active&&typeof active.css_class==='string'?active.css_class:'';
    if(CLASS_PATTERN.test(cssClass)) document.body.classList.add(cssClass);
    const tier=active&&TIERS.includes(active.tier)?active.tier:'D';
    // Tier and effects are applied by the shell (app.18.js); the event keeps this file independent of it.
    document.dispatchEvent(new CustomEvent('skinchange',{detail:{css_class:cssClass,tier}}));
  };
})();
