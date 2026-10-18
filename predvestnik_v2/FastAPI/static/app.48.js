// Equipped scene surrounds every page. Previews never call this renderer.
// Reuse the catalog geometry, with a bounded static composition on phones.
(function () {
  'use strict';
  const tiers = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
  const word = /^[a-z_]{2,24}$/, hex = /^#[0-9a-f]{6}$/i;
  const shape = new Set(['sil', 'glow', 'band', 'ring', 'wave', 'arc', 'dot']);
  const flags = new Set(['m', 'fl', 'st', 'dash']);
  let current = '';
  function layersFor(id, ti) {
    const counts = {}, result = [];
    for (const [min, cls, props] of _AP_SCENES.get(id) || []) {
      const names = cls.split(' '), kind = names[0];
      if (min > ti || !shape.has(kind) || names.includes('w2') || names.some(n => /^(peek|flash|cross|sweep|rise|ripple)$/.test(n))) continue;
      const limit = kind === 'glow' ? 2 : kind === 'band' || kind === 'dot' ? 1 : 4;
      if ((counts[kind] || 0) >= limit || result.length >= 8) continue;
      counts[kind] = (counts[kind] || 0) + 1;
      const still = names.filter(n => shape.has(n) || flags.has(n) || /^i-[a-zA-Z0-9]+$/.test(n)).join(' ');
      result.push(`<i class="sc ${still}${props.cr ? ' cr' : ''}" style="${_scStyle(props, cls)}"></i>`);
    }
    return result.join('');
  }
  window.applySkinWorldV3 = function (look) {
    const ti = tiers.indexOf(look?.tier) + 1, pal = look?.pal, bg = look?.kinds?.bg;
    const valid = ti && word.test(look?.id || '') && _AP_SCENES.has(look.id) && word.test(bg || '') &&
      Array.isArray(pal) && pal.length === 3 && pal.every(c => typeof c === 'string' && hex.test(c));
    let root = document.getElementById('skin-world');
    if (!valid) {
      root?.remove(); document.body.classList.remove('has-skin-world'); current = ''; return false;
    }
    const key = JSON.stringify([look.id, ti, pal, bg]);
    if (current === key && root) return true;
    if (!root) {
      root = document.createElement('div'); root.id = 'skin-world';
      root.setAttribute('aria-hidden', 'true'); document.body.prepend(root);
    }
    root.dataset.skin = look.id;
    const vars = `--ap-a:${pal[0]};--ap-b:${pal[1]};--ap-c:${pal[2]};--ap-i:${[0,.4,.5,.6,.72,.85,.95,1][ti]}`;
    root.innerHTML = `<div class="skin-world-canvas" style="${vars}"><div class="ap-bg ap-t${ti} ap-bg-${bg}"><b></b><b></b></div><div class="ap-scene ap-t${ti}" data-sk="${look.id}">${layersFor(look.id, ti)}</div></div>`;
    current = key; document.body.classList.add('has-skin-world'); return true;
  };
})();
