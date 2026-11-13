// Фото VIP в строках топов (Mini App и страницы игр): холодная загрузка фото дорисовывает уже показанную строку, не перерисовывая таблицу.
// A cold photo download must update the existing row without reloading the board.
(function () {
  'use strict';
  // A photo is a data URI (older answers) or the server's photo address /profile/avatar/<ref>?v=<version>.
  const PHOTO = /^(?:data:image\/(?:png|jpe?g|webp);base64,|\/profile\/avatar\/[A-Za-z0-9_-]{16,64}\?v=[0-9a-f]{16}$)/i, REF = /^[A-Za-z0-9_-]{16,64}$/;
  // "absent" (no photo) and "vip_only" are answers: such rows never ask the server again.
  const FINAL = new Set(['absent', 'vip_only']);
  const appBase = () => typeof BASE === 'string' ? BASE : (document.body.dataset.appBase || '');
  const src = photo => photo.startsWith('/') ? appBase() + photo : photo;
  const photos = new Map(), inFlight = new Map(), queue = [];
  let running = 0;
  const esc = v => String(v || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.leaderboardAvatar = function (p, fallback = '') {
    const ref = p?.profile_ref || p?.ref, photo = p?.is_vip ? (p.avatar || photos.get(ref)?.photo) : null;
    const initials = Array.from(p?.display_name || p?.name || '✦').slice(0,1).join('');
    const hydrate = p?.is_vip && REF.test(ref || '') && !PHOTO.test(photo || '') && !FINAL.has(p?.avatar_state);
    return `<span class="lb-avatar"${hydrate ? ` data-lb-avatar="${ref}"` : ''}>${fallback || `<span aria-hidden="true">${esc(initials)}</span>`}${PHOTO.test(photo || '') ? `<img src="${esc(src(photo))}" alt="" decoding="async" loading="lazy" onerror="this.remove()">` : ''}</span>`;
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
              if (r.vip === false || FINAL.has(r.avatar_state)) break;
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
        const img = document.createElement('img'); img.src = src(photo); img.alt = ''; img.decoding = 'async';
        img.onerror = () => img.remove(); node.append(img);
      });
    }));
  };
})();
