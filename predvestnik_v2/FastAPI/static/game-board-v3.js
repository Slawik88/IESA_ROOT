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
    return `<span class="gb-player">${window.leaderboardAvatar ? window.leaderboardAvatar(p) : ''}<span class="v3-who"><span>${nick}${p.is_vip ? ' <em class="v3-vipdot" aria-label="VIP"></em>' : ''}${markDot(p.mark)}</span>${title}</span></span>`;
  };
})();

// A cold photo download must update the existing row without reloading the board.
(function () {
  'use strict';
  const PHOTO = /^data:image\/(?:png|jpe?g|webp);base64,/i, REF = /^[A-Za-z0-9_-]{16,64}$/;
  const photos = new Map(), inFlight = new Map(), queue = [];
  let running = 0;
  const esc = v => String(v || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.leaderboardAvatar = function (p, fallback = '') {
    const ref = p?.profile_ref || p?.ref, photo = p?.is_vip ? (p.avatar || photos.get(ref)?.photo) : null;
    const initials = Array.from(p?.display_name || p?.name || '✦').slice(0,1).join('');
    return `<span class="lb-avatar"${p?.is_vip && REF.test(ref || '') ? ` data-lb-avatar="${ref}"` : ''}>${fallback || `<span aria-hidden="true">${esc(initials)}</span>`}${PHOTO.test(photo || '') ? `<img src="${esc(photo)}" alt="" decoding="async" loading="lazy" onerror="this.remove()">` : ''}</span>`;
  };
  async function request(ref) {
    if (typeof api === 'function') return api(`/profile/avatar?profile_ref=${encodeURIComponent(ref)}`);
    const base = document.body.dataset.appBase || '';
    const options = {headers: window.GameMode?.headers() || {}};
    const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),12000);
    let response;
    try { response = await fetch(`${base}/profile/avatar?profile_ref=${encodeURIComponent(ref)}`, {...options,signal:controller.signal}); }
    finally { clearTimeout(timeout); }
    if ([403,404].includes(response.status)) return {vip:false};
    if (!response.ok) throw new Error('Не удалось загрузить фото.');
    return response.json();
  }
  function pump() {
    while (running < 4 && queue.length) {
      const job = queue.shift(); running++;
      job().finally(() => { running--; pump(); });
    }
  }
  function photoFor(ref) {
    const cached = photos.get(ref);
    if (cached && Date.now()-cached.at < 60000) return Promise.resolve(cached.photo);
    if (inFlight.has(ref)) return inFlight.get(ref);
    const pending = new Promise(resolve => {
      queue.push(async () => {
        let photo = null;
        try {
          for (const delay of [0, 2500, 6000]) {
            if (delay) await new Promise(done => setTimeout(done,delay));
            try {
              const r = await request(ref);
              if (r.vip === false) break;
              if (PHOTO.test(r.avatar || '')) { photo = r.avatar; break; }
            } catch (_) { /* bounded retry; the fallback stays visible */ }
          }
          photos.set(ref,{photo,at:Date.now()});
          if (photos.size>200) photos.delete(photos.keys().next().value);
        } finally { inFlight.delete(ref); resolve(photo); }
      });
    });
    inFlight.set(ref,pending); pump(); return pending;
  }
  window.hydrateLeaderboardAvatars = function (host) {
    if (!host) return;
    const refs = new Set([...host.querySelectorAll('[data-lb-avatar]')].map(n => n.dataset.lbAvatar).filter(r => REF.test(r)));
    refs.forEach(ref => photoFor(ref).then(photo => {
      if (!photo || !host.isConnected) return;
      host.querySelectorAll(`[data-lb-avatar="${ref}"]`).forEach(node => {
        if (!node.isConnected || node.querySelector('img')) return;
        const img = document.createElement('img'); img.src = photo; img.alt = ''; img.decoding = 'async';
        img.onerror = () => img.remove(); node.append(img);
      });
    }));
  };
})();
