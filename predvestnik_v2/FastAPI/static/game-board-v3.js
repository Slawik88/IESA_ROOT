// ── Ник игрока в таблицах игр (Ритм, Сапёр): та же разметка, что у «Топа» в Mini App ───────────
// Игры живут на отдельных страницах без app.*.js, поэтому здесь компактная копия app.20.js (apFromLook, apName, apTitle) и v3MarkDot из app.29.js.
// Сервер присылает player.look / player.mark / player.is_vip так же, как в /leaderboards/messages; без look рисуется простой ник.
(function () {
  'use strict';
  const TIERS = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'], WORD = /^[a-z_]{2,16}$/, HEX = /^#[0-9a-f]{6}$/i, POWER = [0, .4, .5, .6, .72, .85, .95, 1];
  const TONES = new Set(['dev', 'staff', 'gold', 'green', 'pink', 'orange', 'violet', 'acc']);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  function fromLook(look) {
    const ti = TIERS.indexOf(look?.tier) + 1, kinds = look?.kinds, pal = look?.pal;
    if (!ti || !kinds || !Array.isArray(pal) || pal.length < 3 || !pal.every(c => HEX.test(c))) return null;
    const word = value => (WORD.test(value || '') ? value : '');
    const sigFrom = TIERS.indexOf(look.sig_from || look.ceiling) + 1;
    return { ti, id: String(look.id || ''), title: String(look.title || ''), name: word(kinds.name),
      sig: look.sig && ti >= sigFrom && WORD.test(look.sig) ? look.sig : '', vars: `--ap-a:${pal[0]};--ap-b:${pal[1]};--ap-c:${pal[2]};--ap-i:${POWER[ti]}` };
  }
  const sig = ap => (ap.sig ? ` ap-sig-${ap.sig}` : ''), sk = ap => (/^[a-z_]{2,24}$/.test(ap.id) ? ` data-sk="${ap.id}"` : '');
  function markDot(mark) {
    const ok = !!mark && typeof mark.id === 'string' && /^[a-z0-9_]{2,24}$/.test(mark.id) && typeof mark.title === 'string' && typeof mark.glyph === 'string' && TONES.has(mark.tone);
    return ok ? `<span class="v3-markdot" data-tone="${mark.tone}" role="img" aria-label="${esc(mark.title)}" title="${esc(mark.title)}">${esc(mark.glyph)}</span>` : '';
  }
  // player: {display_name, look, mark, is_vip}; возвращает HTML для вставки внутрь ссылки на профиль
  window.gameWhoV3 = function (player) {
    const p = player || {}, ap = fromLook(p.look), name = esc(p.display_name || 'Игрок');
    const nick = ap && typeof window.skinNicknameV3 === 'function' ? window.skinNicknameV3(ap, name, p.display_name || 'Игрок') : `<span class="ap-plain">${name}</span>`;
    const title = ap && ap.title ? `<span class="ap-title ap-t${ap.ti}${sig(ap)}"${sk(ap)} style="${ap.vars}">${esc(ap.title)}</span>` : '';
    return `<span class="v3-who"><span>${nick}${p.is_vip ? ' <em class="v3-vipdot" aria-label="VIP"></em>' : ''}${markDot(p.mark)}</span>${title}</span>`;
  };
})();
