const BASE='.',tg=null;const el=id=>document.getElementById(id);
      const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const _profileEsc=esc,fmt=n=>new Intl.NumberFormat('ru-RU').format(n);
      const _sysFlags={};let _profileData=null;const _uid=0;
      const api=()=>Promise.reject(new Error('Offline fixture'));
    function vipName(name, isVip, badge='✦', position='left') {
  if (!isVip || position === 'hidden') return name;
  if (position === 'right') return `${name} ${badge}`;
  if (position === 'both') return `${badge} ${name} ${badge}`;
  return `${badge} ${name}`;
}
// Shared by Mini App and standalone game boards. Only trusted, static SVG paths;
// player strings are escaped before attributes; no HTML, URLs or CSS from names.
(function () {
  'use strict';
  const motifs = {
    forest: ['M3 14Q3 2 15 2Q15 14 3 14Zm0 0L12 5M6 11V7m3 1h4', 'M0 7Q18 0 32 7T64 7T96 7'],
    dune: ['M1 13Q7 2 11 9Q14 5 17 13M1 16h16M11 3h3', 'M0 8Q16-2 32 8T64 8T96 8'],
    harbor: ['M9 1v12M5 5h8M2 10Q2 18 9 15Q16 18 16 10M6 3h6', 'M0 5Q8 12 16 5T32 5T48 5T64 5T80 5T96 5'],
    lotus_pond: ['M9 15Q0 12 2 6Q7 6 9 15Q16 6 16 8Q18 14 9 15Zm0 0Q4 5 9 1Q14 5 9 15Z', 'M0 7Q14 12 24 7Q36 0 48 7T72 7T96 7'],
    threshold: ['M3 16V4l6-3 6 3v12M6 16V6h6v10M1 16h16', 'M0 8h16V3h16v5h16V3h16v5h16V3h16v5'],
    frost: ['M9 1v16M2 5l14 8M2 13l14-8M6 3l3 3 3-3M6 15l3-3 3 3', 'M0 7h12l4-4 4 4h12l4-4 4 4h12l4-4 4 4h36'],
    copper: ['M9 2v3M9 13v3M2 9h3m8 0h3M4 4l2 2m6 6 2 2M4 14l2-2m6-6 2-2M13 9a4 4 0 1 1-8 0 4 4 0 1 1 8 0', 'M0 7h16v-3h8v6h8V7h32v-3h8v6h8V7h16'],
    sakura_bud: ['M2 16 14 3M7 11Q2 7 5 5Q9 4 9 9M11 7Q9 2 12 1Q17 2 14 5', 'M0 8Q36 1 64 8M28 5l-3-3m28 3 4-3M64 8l32-3'],
    inferno: ['M9 1Q11 6 15 8Q19 16 9 17Q-1 16 3 8Q4 12 7 11Q5 5 9 1Z', 'M0 8l8-4 4 4 8-5 4 5 12-4 4 4 10-5 4 5 12-4 4 4 12-5 4 5h10'],
    hanami: ['M9 8Q2 3 6 1Q11 0 10 7Q15 1 17 6Q18 10 11 9Q18 15 13 17Q8 18 9 11Q4 18 1 13Q0 9 7 9Z', 'M0 7Q20 1 40 7T80 7M22 5l3-3m34 7 3 2M80 7h16'],
    jade: ['M4 2h10v3h3v9h-3v3H4v-3H1V5h3Zm2 3v8h6V5Z', 'M0 7h12V3h12v8h12V7h24V3h12v8h12V7h12'],
    celestial: ['M9 1v3M2 4l2 2m12-2-2 2M1 11h3m10 0h3M4 16l2-2m6 0 2 2M13 10a4 4 0 1 1-8 0 4 4 0 1 1 8 0', 'M0 8 12 4l12 4 12-4 12 4 12-4 12 4 12-4 12 4'],
    ruby: ['M9 1 2 5v7l7 5 7-5V5ZM2 5l7 12 7-12M2 5h14M9 1v16', 'M0 7h16l8-4 8 4-8 4-8-4h48l8-4 8 4-8 4-8-4h32'],
    observatory: ['M3 9a6 6 0 1 0 12 0 6 6 0 1 0-12 0M1 12 17 6M9 1v16', 'M0 7h20m4 0a4 4 0 1 0 8 0 4 4 0 1 0-8 0m8 0h32m4 0a4 4 0 1 0 8 0 4 4 0 1 0-8 0m8 0h20'],
    lotus_gold: ['M9 16Q0 14 1 6Q6 7 9 16Q12 7 17 6Q18 14 9 16ZM9 16Q3 7 9 1Q15 7 9 16ZM1 17h16', 'M0 8h16l8-6 8 6h32l8-6 8 6h16'],
    void: ['M14 3A7 7 0 1 0 15 12A6 6 0 1 1 14 3ZM1 9h16', 'M0 7h28q20-9 40 0M28 7q20 9 40 0h28'],
    aurora: ['M2 15Q1 2 5 3Q9 18 10 5Q11-1 16 4M3 9l12-4', 'M0 8Q16-4 32 5T64 4T96 8'],
    solar: ['M9 1 11 5l5-2-2 5 3 3-5 1-1 5-3-4-5 2 1-5-3-3 5-1ZM12 9a3 3 0 1 1-6 0 3 3 0 1 1 6 0', 'M0 7h12l4-4 4 4 4 3 4-3h40l4-4 4 4 4 3 4-3h12'],
    sakura_storm: ['M2 9Q2 1 10 2Q17 3 15 10Q14 16 8 15Q4 13 7 9Q9 6 11 9M1 16 5 14M14 3l3-2', 'M0 8Q12-1 24 7T48 7T72 7T96 8M12 4l3-3m61 4 4-3'],
    artifact: ['M2 2h6v5H2ZM10 10h6v6h-6ZM12 1v4h5M1 12h5v5M8 8h3', 'M0 7h12V3h12v8h8V7h16V2h8v5h16v4h8V7h16'],
    moon_lotus: ['M14 1A7 7 0 1 0 17 9M9 16Q1 13 2 8Q7 9 9 16Q14 9 16 9Q16 15 9 16ZM9 16Q6 10 9 6Q12 10 9 16Z', 'M0 7Q24 12 48 7T96 7M32 7q16-9 32 0'],
    ryujin_tide: ['M1 12Q5 4 9 9Q12 2 17 6Q10 3 12 10Q15 16 7 16Q2 16 1 12ZM9 9 5 2M12 7l3-6', 'M0 8Q8-1 16 8Q24 15 32 5T64 5T96 8'],
    midnight_comet: ['M2 16 14 2M3 10 11 2M8 16 16 8M8 13a3 3 0 1 1-6 0 3 3 0 1 1 6 0', 'M0 8 38 4l-10 4h68M72 5h12'],
    chrono: ['M4 1h10M4 17h10M5 1q0 5 4 8-4 3-4 8m8-16q0 5-4 8 4 3 4 8M6 4h6M6 14h6', 'M0 7h16m0-3v6m8-5v4m8-5v6m8-5v4m8-5v6m8-5v4m8-5v6m8-5v4m8-5v6m0-3h16'],
    starheart: ['M9 16Q-1 9 3 4Q6 1 9 5Q12 1 15 4Q19 9 9 16ZM9 6v7M6 9h6', 'M0 7h24l5-5 7 10 6-8 6 3h48'],
    pumpkin_lantern: ['M9 4Q-1 0 2 12Q3 17 9 16Q16 17 17 10Q17 1 9 4ZM9 4 11 1M5 8l2 2m4 0 2-2M5 13h8', 'M0 7h16l3-3 3 6 3-6 3 3h40l3-3 3 6 3-6 3 3h16'],
    cobweb: ['M9 1v16M1 9h16M3 3l12 12M3 15 15 3M4 9l5-5 5 5-5 5ZM2 9l7-7 7 7-7 7Z', 'M0 7Q12 0 24 7Q36 14 48 7Q60 0 72 7Q84 14 96 7'],
    witch_hour: ['M4 12 9 1l3 9 5 3Q10 18 1 13ZM5 10l8 1M10 4l3-1', 'M0 7h20l4-4 4 8 4-8 4 4h24l4-4 4 8 4-8 4 4h20'],
    snow_globe: ['M4 14A7 7 0 1 1 14 14ZM3 17h12M5 14h8M6 6h1m4-2h1m-1 5h1M8 13V9h2v4', 'M0 7h12m6 0h6m6 0h6m6 0h12m6 0h6m6 0h6m6 0h12'],
    garland: ['M1 3q8 7 16 0M4 5v3m5-1v3m5-5v3M3 9h2v3H3Zm5 2h2v3H8Zm5-2h2v3h-2Z', 'M0 3Q12 12 24 3T48 3T72 3T96 3M12 7v3m24-3v3m24-3v3m24-3v3'],
    midnight_chimes: ['M9 1v3M5 4Q9 0 13 4L14 12H4ZM2 13h14M7 16h4M1 4l2 2m12 0 2-2', 'M0 7h28l4-3v6l4-3h24l4-3v6l4-3h28'],
    quiet_library: ['M1 4Q5 2 9 5Q13 2 17 4V15Q13 13 9 16Q5 13 1 15ZM9 5V16M3 8q3-1 4 0m4 0q3-1 4 0M3 11q3-1 4 0m4 0q3-1 4 0', 'M0 12h96M8 12V5m5 7V3m4 9V6m14 6V4m5 8V2m4 10V6m16 6V4m4 8V3m5 9V6m16 6V3m4 9V5'],
    alchemist: ['M7 1h4M8 1v5L3 15q-1 2 2 2h8q3 0 2-2L10 6V1M4 12q5-2 10 0M7 9h1m2 1h1', 'M0 9Q6 5 12 9T24 9T36 9T48 9T60 9T72 9T84 9T96 9M18 4a1.5 1.5 0 1 0 .1 0M52 3a1.5 1.5 0 1 0 .1 0M82 5a1.5 1.5 0 1 0 .1 0'],
    grimoire: ['M3 2h11l2 2v13H5L3 15ZM3 15h11v2M6 8q3-3 6 0-3 3-6 0M16 7h2v4h-2', 'M0 7h10l3-4v8l3-4h20l3 4 3-4 3 4h20l3-4v8l3-4h20'],
    scarlet_star: ['M9 1 11 6l6 1-4 4 1 6-5-3-5 3 1-6-4-4 6-1ZM5 11 1 13l3 2 4-2m5-2 4 2-3 2-4-2', 'M0 7h24l8-4-2 8-6-4h48l-8-4 2 8 6-4h24'],
    crimson_dark: ['M9 1Q8 5 4 9Q-1 17 9 17Q19 17 14 9ZM5 11q-1 3 2 3M16 2v4', 'M0 5h16v5l3-5h25v7l3-7h25v4l3-4h21'],
    raven_masquerade: ['M1 6Q5 3 9 7Q13 3 17 6L14 13l-4 1-1-3-1 3-4-1ZM4 8l3 1m4 0 3-1M5 4 3 1m10 3 2-3', 'M0 7Q16 0 32 7l4-4 4 4-4 4-4-4Q64 0 96 7'],
    phantom_carriage: ['M3 4Q9 0 15 4L13 12H5ZM9 3v9M6 15a2 2 0 1 1-4 0 2 2 0 1 1 4 0m12 0a2 2 0 1 1-4 0 2 2 0 1 1 4 0M2 12h14', 'M0 7h16q8-8 16 0t16 0 16 0 16 0h16'],
    gingerbread_house: ['M1 7 9 1l8 6M3 6v11h12V6M7 17v-6h4v6M4 8q2 3 4 0t4 0m-7 3h1m6 0h1', 'M0 4Q6 12 12 4T24 4T36 4T48 4T60 4T72 4T84 4T96 4'],
    polar_express: ['M1 7h10V2h6v10H1ZM4 7V3h3v4M3 15a2 2 0 1 1 4 0 2 2 0 1 1-4 0m9 0a2 2 0 1 1 4 0 2 2 0 1 1-4 0M1 12h16', 'M0 5h96M0 9h96M8 3v8m16-8v8m16-8v8m16-8v8m16-8v8m16-8v8'],
    rose_letter: ['M1 5h16v11H1Zm0 0 8 7 8-7M9 6Q3 2 6 1Q8 0 9 2Q11 0 13 1Q16 3 9 6Z', 'M0 7Q16 0 32 7T64 7T96 7M48 7q-8-8-4-8 4-2 4 2 3-4 6-1 1 3-6 7'],
    glass_heart: ['M9 17 1 7l2-5h4l2 3 2-3h4l2 5ZM1 7h16M3 2l6 15 6-15M7 2l2 5 2-5', 'M0 7h28l8-5 12 10L60 2l8 5h28M28 7h40'],
  };
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const svg = (path, cls, box) => `<svg class="${cls}" viewBox="${box}" aria-hidden="true" focusable="false"><path d="${path}"/></svg>`;
  window.skinNicknameV3 = function (ap, html, plain) {
    const id = String(ap.id || ''), motif = Object.hasOwn(motifs, id) ? motifs[id] : null;
    if (!motif) return html; // old/unknown skin payload: readable text
    const ti = Math.max(1, Math.min(7, Number(ap.ti) || 1));
    const emblem = ti >= 3 ? svg(motif[0], 'ap-nick-emblem', '0 0 18 18') : '';
    const rail = ti >= 4 ? svg(motif[1], 'ap-nick-rail', '0 0 96 14') : '';
    const rank = ti >= 6 ? '<svg class="ap-nick-rank" viewBox="0 0 12 18" aria-hidden="true"><path d="m6 3 4 6-4 6-4-6Z"/>' + (ti === 7 ? '<path d="M1 3 6 0l5 3M1 15l5 3 5-3"/>' : '') + '</svg>' : '';
    return `<span class="ap-name ap-designed ap-t${ti}" data-sk="${id}" style="${ap.vars}" title="${escape(plain)}">${emblem}<span class="ap-nick-text">${html}${rail}</span>${rank}</span>`;
  };
})();

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

// ── Shell V3: профиль-главная, плашка разработки, общие SVG-иконки ─────────────
// Разметка использует только классы из shell-v3.css; цвета приходят из скина.
const _V3_PATHS = {
  hanger: '<path d="M12 8a2.4 2.4 0 1 0-2.4-2.4M12 8v2l8 5.2c.8.5.4 1.8-.6 1.8H4.6c-1 0-1.4-1.3-.6-1.8L12 10"/>',
  paw: '<circle cx="6.5" cy="11" r="1.7"/><circle cx="10" cy="6.5" r="1.7"/><circle cx="14" cy="6.5" r="1.7"/><circle cx="17.5" cy="11" r="1.7"/><path d="M12 12.5c-3 0-5 2.7-4 4.6.8 1.5 2.4 1.2 4 1.2s3.2.3 4-1.2c1-1.9-1-4.6-4-4.6z"/>',
  flag: '<path d="M6 21V4M6 5h11l-2.5 3.5L17 12H6"/>',
  chest: '<path d="M4 10h16v9H4zM4 10a8 5 0 0 1 16 0M12 13v3"/>',
  trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0zM8 6H5v1a3 3 0 0 0 3 3M16 6h3v1a3 3 0 0 1-3 3M12 13v4M9 20h6"/>',
  chat: '<path d="M5 18l-2 3v-5.5A8 8 0 1 1 6 19z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>',
  chart: '<path d="M4 17l5-5 3.5 3.5L20 7M15 7h5v5"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.8 9.2a2.4 2.4 0 1 1 3.3 2.2c-.8.4-1.1.9-1.1 1.8M12 17h.01"/>',
  refresh: '<path d="M20 11a8 8 0 0 0-14-4.5L4 9M4 4v5h5M4 13a8 8 0 0 0 14 4.5L20 15M20 20v-5h-5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
  chev: '<path d="M9 6l6 6-6 6"/>',
  ticket: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h13A1.5 1.5 0 0 1 20 8.5V10a2 2 0 0 0 0 4v1.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 15.5V14a2 2 0 0 0 0-4zM14 7v10"/>',
  manage: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6"/>',
  essence: '<path d="M12 3c3.3 4.1 5.6 6.8 5.6 10.2a5.6 5.6 0 0 1-11.2 0C6.4 9.8 8.7 7.1 12 3z"/>',
  shop: '<path d="M3.5 5h2.3l2.1 9.6h10.3l2-6.9H6.6"/><circle cx="9.6" cy="18.6" r="1.4"/><circle cx="16.6" cy="18.6" r="1.4"/>',
  bag: '<path d="M9 5.2V4.5a3 3 0 0 1 6 0v.7"/><path d="M6.5 5.2h11A2.5 2.5 0 0 1 20 7.7v10.8a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18.5V7.7a2.5 2.5 0 0 1 2.5-2.5z"/><path d="M4 11.5h16M10.5 11.5v2.5h3v-2.5"/>',
  family: '<circle cx="9.2" cy="8" r="3.1"/><path d="M3.8 20c.7-3.3 3-5 5.4-5s4.7 1.7 5.4 5"/><circle cx="16.9" cy="9.7" r="2.4"/><path d="M15.2 14.9c2.2 0 4 1.5 4.6 5.1"/>'
};
function _v3Icon(name) {
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${_V3_PATHS[name] || ''}</svg>`;
}
function _v3Row(icon, label, action, hint) {
  return `<button type="button" class="v3-row" onclick="${action}">${_v3Icon(icon)}<span>${label}${hint ? `<small>${hint}</small>` : ''}</span><span class="v3-end">${_v3Icon('chev')}</span></button>`;
}
// Кольцо прогресса вокруг аватара: длина окружности r=35 ≈ 220
function _v3Ring(percent) {
  const offset = Math.round(220 * (1 - Math.min(100, Math.max(0, percent)) / 100));
  return `<svg viewBox="0 0 76 76" aria-hidden="true"><circle cx="38" cy="38" r="35" stroke="var(--v3-faint)"/><circle cx="38" cy="38" r="35" stroke="var(--v3-acc)" stroke-dasharray="220" stroke-dashoffset="${offset}"/></svg>`;
}
function renderProfileHome(data) {
  const d = data || {};
  const wallet = _v3Wallet(d);
  const level = Math.max(1, Number(d.account_level) || 1);
  const xp = Math.max(0, Number(d.xp_into) || 0);
  const xpNeed = Math.max(1, Number(d.xp_to_next) || Number(d.xp_per_level) || 1);
  const capped = !(Number(d.xp_to_next) > 0), left = Math.max(0, xpNeed - xp);
  const rank = String(d.rank || '').replace(/^[\p{Extended_Pictographic}\s]+/u, '');
  const publicName = String(d.display_name || '').trim();
  const uname = String(d.username || '').replace(/^@+/, '');
  const rawName = publicName || (uname ? `@${uname}` : 'Игрок');
  const ap = apFromLook(d.look);
  const chests = (typeof _sysFlags !== 'undefined' && _sysFlags.content_chests_v1)
    ? _v3Row('chest', 'Сундуки', 'openChestsV1()') : '';
  const identity = `<section class="v3-id${d.vip ? ' is-vip' : ''}${ap ? ' has-look' : ''}" aria-label="Профиль игрока">
      <div class="v3-ring">${apHalo(ap)}${_v3Ring(capped ? 100 : xp / xpNeed * 100)}<div class="v3-ava" id="pro-showcase-ava">${_v3Avatar(d)}</div>${apFrame(ap)}<span class="v3-lv" aria-label="Уровень ${level}">${level}</span></div>
      <div style="min-width:0"><div class="v3-greet">${v3GreetHtml(d)}</div><div class="v3-name">${apName(ap, _profileEsc(vipName(rawName, d.is_vip, d.vip?.badge || '✦', d.vip?.badge_position || 'left')))}</div>
      <div class="v3-sub">${_profileEsc(rank || 'Игрок')}</div>
      ${v3MarksHtml(d.marks, { own: true })}
      ${_v3VipSeal(d.vip)}
      <div class="v3-sub" style="margin-top:2px">${capped ? 'Максимальный уровень' : `${fmt(left)} XP до ${level + 1} уровня`}</div></div>
    </section>`;
  return `${apStage(ap, identity)}
    <section class="v3-next-wrap" id="v3-next" aria-live="polite"><div class="sk" style="height:76px;border-radius:14px"></div></section>
    ${_v3TodayShell()}
    <section class="v3-bal" aria-label="Баланс">
      <div class="v3-bal-head"><span class="v3-eyebrow">Мора</span><button type="button" class="v3-link" onclick="showCurrModal()">Кошелёк ›</button></div>
      <div class="v3-bal-row"><div class="v3-bal-mora">${typeof v3Cur === 'function' ? v3Cur('mora', 'v3-bal-coin') : ''}<div class="v3-num" data-key="mora" data-n="${Number(wallet.mora) || 0}">${fmt(wallet.mora || 0)}</div></div>
        <button type="button" class="v3-pill v3-pill--ghost" onclick="openZarnikiTopup()" aria-label="Пополнить Зарники. Баланс ${fmt(wallet.zarniki || 0)}">${_v3Icon('plus')}${typeof v3Cur === 'function' ? v3Cur('zarniki') : ''}Зарники ${fmt(wallet.zarniki || 0)}</button></div>
    </section>
    <section class="v3-stats" aria-label="Показатели игрока"><span class="v3-eyebrow v3-stats-label">Активность</span><div><b data-key="streak" data-n="${Number(d.streak) || 0}">${fmt(d.streak || 0)}</b><span>дней подряд</span></div><div><b data-key="ach" data-n="${Number(d.achievements) || 0}">${fmt(d.achievements || 0)}</b><span>достижений</span></div><div><b data-key="msgs" data-f="short" data-n="${Number(d.messages_all_time) || 0}">${_v3Short(d.messages_all_time || 0)}</b><span>сообщений</span></div></section>
    ${_v3PathShell()}
    ${_v3TopShell()}
    ${typeof giftsShelfShell === 'function' ? giftsShelfShell() : ''}
    <nav class="v3-list" aria-label="Разделы профиля">
      ${_v3Row('hanger', 'Образы', 'openLooksModal()', d.essence ? `Скины и сеты · Эссенция ${fmt(d.essence)}` : 'Скины, прокачка тиров и сеты')}
      ${_v3Row('bag', 'Инвентарь', 'openInventory()', 'Образы, питомцы, ключи и вещи')}
      ${_v3Row('paw', 'Питомцы', 'openPetsV1()')}
      ${_v3Row('flag', 'Задания', 'openQuestsV1()')}
      ${chests}
      ${typeof shopEntryRow === 'function' ? shopEntryRow() : ''}
      ${_v3Row('trophy', 'Достижения', 'openAchievementsV1()')}
      ${_v3Row('family', 'Моя семья', 'openFamilyTree()', 'Родословная: супруг, дети, родственники')}
      ${_v3Row('ticket', 'Промокоды', 'openPromoSheet()')}
      ${_v3Row('help', 'Путеводитель', 'openGuide()', 'Ответы на вопросы и первые шаги')}
    </nav>`;
}

// ── Telegram Mini App: haptics, цвета оболочки, жесты ──────────────────────────
// До этого _haptic() нигде не был объявлен: проверки typeof в app.01.js молча ничего не делали.
let _hapticAt = 0;
function _haptic(kind) {
  const h = tg?.HapticFeedback; if (!h) return;
  const now = Date.now(); if (now - _hapticAt < 60 && kind !== 'success' && kind !== 'error') return; _hapticAt = now;
  try {
    if (kind === 'success' || kind === 'warning' || kind === 'error') h.notificationOccurred(kind);
    else if (kind === 'select') h.selectionChanged();
    else h.impactOccurred(kind || 'light');
  } catch (err) { console.error('haptic', err); }
}
// Один делегированный слушатель на все элементы нового каркаса
document.addEventListener('click', e => {
  const t = e.target.closest('.nb, .v3-pill, .v3-chip, .v3-row, .v3-game, .v3-link, .v3-more > summary');
  if (!t || t.disabled) return;
  _haptic(t.classList.contains('nb') ? 'select' : t.classList.contains('v3-pill') ? 'medium' : 'light');
}, true);

// Шапка, фон и нижняя панель Telegram берут цвет скина: никаких чужих полос по краям
(function initTmaShell() {
  if (!tg) return;
  try { if (tg.disableVerticalSwipes) tg.disableVerticalSwipes(); } catch (err) { console.error('swipes', err); }
  let lastColor = '';
  const call = (method, since, color) => {
    try { if (tg[method] && (!tg.isVersionAtLeast || tg.isVersionAtLeast(since))) tg[method](color); }
    catch (err) { console.error(method, err); }
  };
  const syncChrome = () => {
    const bg = getComputedStyle(document.body).getPropertyValue('--v3-bg').trim();
    if (!/^#[0-9a-f]{6}$/i.test(bg) || bg === lastColor) return;
    lastColor = bg;
    call('setHeaderColor', '6.1', bg); call('setBackgroundColor', '6.1', bg); call('setBottomBarColor', '7.10', bg);
  };
  syncChrome();
  new MutationObserver(syncChrome).observe(document.body, { attributes: true, attributeFilter: ['class', 'style'] });
  try { tg.onEvent?.('themeChanged', syncChrome); } catch (err) { console.error('theme', err); }
})();

// Момент награды: тактильный отклик + россыпь частиц из центра (или из переданного элемента)
function v3Reward(anchor) {
  _haptic('success');
  if (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const level = typeof v3FxLevelNow === 'function' ? v3FxLevelNow() : 1;   // чем выше тир скина, тем щедрее эффект
  const count = level >= 5 ? 28 : level >= 3 ? 18 : 12;
  const pt = anchor && 'x' in anchor ? anchor : null;
  const r = pt ? null : anchor?.getBoundingClientRect?.();
  const x = pt ? pt.x : r ? r.left + r.width / 2 : innerWidth / 2, y = pt ? pt.y : r ? r.top + r.height / 2 : innerHeight * 0.4;
  if (level >= 7) {
    const shock = document.createElement('i'); shock.className = 'v3-shock'; document.body.appendChild(shock);
    const wave = shock.animate([{ transform: `translate(${x}px,${y}px) scale(.3)`, opacity: .9 }, { transform: `translate(${x}px,${y}px) scale(5)`, opacity: 0 }], { duration: 800, easing: 'cubic-bezier(.22,1,.36,1)' });
    wave.onfinish = () => shock.remove();
  }
  for (let i = 0; i < count; i++) {
    const p = document.createElement('i'); p.className = 'v3-burst'; document.body.appendChild(p);
    const a = (Math.PI * 2 * i) / count + Math.random() * 0.4, d = 70 + Math.random() * (level >= 5 ? 130 : 70);
    const run = p.animate([
      { transform: `translate(${x}px,${y}px) scale(1)`, opacity: 1 },
      { transform: `translate(${x + Math.cos(a) * d}px,${y + Math.sin(a) * d}px) scale(.2)`, opacity: 0 }
    ], { duration: 650 + Math.random() * 250, easing: 'cubic-bezier(.22,1,.36,1)', fill: 'forwards' });
    run.onfinish = () => p.remove();
  }
}

// ── «Сегодня»: дневные квесты прямо на профиле, награда забирается в один тап ───
let _v3Quests = null, _v3Claiming = false, _v3Seq = 0;
function _v3TodayShell() {
  const row = '<div class="sk" style="height:46px;border-radius:12px;margin-top:10px"></div>';
  return `<section class="v3-today" id="v3-today" aria-label="Сегодня"><div class="v3-sec"><span class="v3-eyebrow">Сегодня</span></div>${row}${row}${row}</section><span class="sr-only" id="v3-today-status" role="status"></span>`;
}
function loadV3Today() {
  const mine = ++_v3Seq;
  return api('/quests-v1/me').then(d => { if (mine !== _v3Seq || _v3Claiming) return; _v3Quests = d; renderV3Today(); })
    .catch(() => { if (mine !== _v3Seq || _v3Claiming) return; _v3Quests = null; renderV3Today(true); });
}
function _v3QuestRow(q) {
  const target = Math.max(1, Number(q.target) || 1), progress = Math.min(target, Math.max(0, Number(q.progress) || 0));
  const done = !!q.completed, share = done ? 100 : progress / target * 100;
  return `<button type="button" class="v3-quest${done ? ' is-done' : ''}" onclick="${_v3QuestRoute(q.metric)}" aria-label="${_profileEsc(q.title)}: ${done ? 'выполнено' : `${progress} из ${target}`}">
    <span class="v3-qring">${_v3Ring(share)}${done ? '<b>✓</b>' : ''}</span>
    <span class="v3-qt">${_profileEsc(q.title)}</span><span class="v3-qn">${done ? 'Готово' : `${progress} / ${target}`}</span></button>`;
}
function renderV3Today(failed) {
  const host = el('v3-today'); if (!host) return;
  const head = `<div class="v3-sec"><span class="v3-eyebrow">Сегодня · новые через ${v3UntilReset()}</span><button type="button" class="v3-link" onclick="openQuestsV1()">Все задания</button></div>`;
  if (failed) { host.innerHTML = `${head}<div class="v3-empty">Задания не загрузились. <button type="button" class="v3-link" onclick="loadV3Today()">Повторить</button></div>`; return; }
  const quests = _v3Quests?.daily?.quests || [];
  host.innerHTML = `${head}${quests.length ? quests.map(_v3QuestRow).join('') : '<div class="v3-empty">Заданий пока нет. Загляните чуть позже, мы что-нибудь придумаем.</div>'}`;
  renderV3Next();
}
// Оптимистично: награда помечается полученной сразу; откат только если сам claim не удался
function v3ClaimQuestReward(kind) {
  if (_v3Claiming || !_v3Quests?.rewards?.items?.[kind]) return;
  _v3Claiming = true;
  const btn = el('v3-claim'), box = btn?.querySelector('.v3-next-go')?.getBoundingClientRect() || btn?.getBoundingClientRect();
  const origin = box ? { x: box.left + box.width / 2, y: box.top + box.height / 2 } : null;
  const before = JSON.parse(JSON.stringify(_v3Quests));
  Object.assign(_v3Quests.rewards.items[kind], { claimable: false, claimed: true });
  renderV3Today();
  api('/quests-v1/claim-reward', { method: 'POST', body: JSON.stringify({ kind }) }).then(d => {
    _v3Quests = d; renderV3Today();
    const reward = d.reward_result || {};
    const note = reward.already_claimed ? 'Награда уже получена' : `Получено: +${fmt(reward.amount_mora || 0)} Моры${reward.amount_essence ? ` и +${fmt(reward.amount_essence)} Эссенции` : ''}${reward.pass_xp ? ` · +${reward.pass_xp} опыта Пропуска` : ''}`;
    toast(note); const live = el('v3-today-status'); if (live) live.textContent = note;
    if (!reward.already_claimed) v3Reward(origin);
    _v3RefreshBalance();
  }).catch(e => { _v3Quests = before; renderV3Today(); toast(e, false); })
    .finally(() => { _v3Claiming = false; });
}

// Баланс на профиле: обновляется после награды и при возврате на вкладку (не чаще раза в 20 секунд)
let _v3BalanceAt = 0;
function _v3RefreshBalance() {
  _v3BalanceAt = Date.now();
  return api('/profile/me').then(p => {
    _profileData = p;
    const mora = document.querySelector('.v3-num'); if (mora) { mora.dataset.n = String((p.balances || p).mora || 0); v3CountUp(mora.parentElement); }
    renderV3Bar(p);
  }).catch(() => { /* баланс обновится при следующем открытии профиля */ });
}
document.addEventListener('click', e => {
  if (e.target.closest('.nb[data-page="profile"]') && Date.now() - _v3BalanceAt > 20000 && typeof _profileData !== 'undefined' && _profileData) _v3RefreshBalance();
}, true);

// ── Shell V3 · постоянная панель, «Дальше», печать VIP, путь по аспектам ─────────
function _v3Wallet(d) {
  const wallet = { ...(d?.balances || {}) };
  ['mora', 'diamonds', 'zarniki', 'essence'].forEach(k => { if (d?.[k] !== undefined) wallet[k] = d[k]; });
  return wallet;
}
function _v3Short(n, from = 1e4) {
  const v = Number(n) || 0;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1).replace('.', ',').replace(',0', '')}М`;
  if (v >= from) return `${(v / 1e3).toFixed(1).replace('.', ',').replace(',0', '')}к`;
  return fmt(Math.round(v));
}
// Цифры валют не должны теряться. Не влезает ряд: сначала чипы уплотняются (fit-1, затем fit-2), и только если и так не помещается,
// край ряда затухает и ряд прокручивается; Зарники закреплены справа
function v3ChipsFade() {
  const bar = el('v3-bar'), main = el('v3-chips-main'); if (!bar || !main) return;
  const over = () => main.scrollWidth > main.clientWidth + 1;
  if (bar.classList.contains('fit-3')) _v3BarNumbers(false);
  bar.classList.remove('fit-1', 'fit-2', 'fit-3');
  if (over()) {
    bar.classList.add('fit-1');
    if (over()) { bar.classList.add('fit-2'); if (over()) { bar.classList.add('fit-3'); _v3BarNumbers(true); } }   // fit-3: суммы от тысячи сокращаются
  }
  main.classList.toggle('has-more', over());
}
// Суммы в панели; compact сокращает уже от тысячи («2,6к»), обычный вид только от десяти тысяч
let _v3BarVals = null, _v3BarFirstAt = 0;
function _v3BarNumbers(compact) {
  const v = _v3BarVals; if (!v) return;
  const set = (id, value) => { const node = el(id); if (node) node.textContent = _v3Short(value, compact ? 1e3 : 1e4); };
  set('vb-mora', v.mora); set('vb-dia', v.diamonds); set('vb-ess', v.essence); set('vb-zar', v.zarniki);   // порядок как на экране: Мора, Алмазы, остальные, Зарники
}
window.addEventListener('resize', v3ChipsFade);
document.fonts?.ready?.then(v3ChipsFade);   // шрифт приходит позже первой отрисовки и меняет ширину цифр
// Панель не зависит от вкладки: игрок всегда видит свой уровень, ресурсы и «Что нового»
function renderV3Bar(d) {
  const bar = el('v3-bar'); if (!bar || !d) return;
  const wallet = _v3Wallet(d), level = Math.max(1, Number(d.account_level) || 1);
  ['mora', 'diamonds', 'zarniki', 'essence'].forEach(k => {
    const node = el('cm-bal-' + k); if (node && wallet[k] !== undefined) node.textContent = fmtF(wallet[k]);
  });
  const need = Number(d.xp_to_next) > 0 ? Number(d.xp_to_next) : 0, xp = Math.max(0, Number(d.xp_into) || 0);
  const me = el('v3-bar-me');
  if (me) {
    me.innerHTML = `${_v3Ring(need ? xp / need * 100 : 100)}<span class="v3-bar-lv">${level}</span>`;
    me.classList.toggle('is-vip', !!d.vip);
  }
  const was = _v3BarVals;
  _v3BarVals = { mora: wallet.mora, diamonds: wallet.diamonds, essence: d.essence, zarniki: wallet.zarniki };
  _v3BarNumbers(false);
  v3ChipsFade();
  if (!was) _v3BarFirstAt = Date.now(); else if (typeof v3BalanceFx === 'function') v3BalanceFx(was, _v3BarVals, _v3BarFirstAt);   // пульс числа и «+N» под чипом (app.31.js)
  bar.classList.add('is-ready');
}

// Печать VIP: кольцо показывает остаток срока (до 30 дней = полный круг), аура вокруг аватара задаётся CSS
function _v3VipSeal(vip) {
  if (!vip) return '';
  const days = Math.max(0, Number(vip.days_left) || 0), share = Math.min(1, days / 30);
  const ring = `<svg viewBox="0 0 28 28" aria-hidden="true"><circle cx="14" cy="14" r="11" class="v3-seal-track"/><circle cx="14" cy="14" r="11" class="v3-seal-arc" stroke-dasharray="69.1" stroke-dashoffset="${(69.1 * (1 - share)).toFixed(1)}"/><path d="M8.5 17.5l1.4-6 2.6 3 1.5-4.2 1.5 4.2 2.6-3 1.4 6z" class="v3-seal-crown"/></svg>`;
  const until = vip.expires_at ? ` · до ${_profileDate(vip.expires_at)}` : '';
  return `<button type="button" class="v3-seal" onclick="openStoreV3('vip')" aria-label="VIP активен, осталось ${fmt(days)} дн. Открыть VIP">${ring}<span><b>VIP</b> ещё ${fmt(days)} дн.${until}</span></button>`;
}

// «Дальше»: одно понятное действие вместо выбора из списка
function _v3QuestRoute(metric) {
  const m = String(metric || ''), on = key => typeof _sysFlags !== 'undefined' && _sysFlags[key] === true;
  if (m.startsWith('rhythm_') && on('game_rhythm_v2')) return 'openRhythmV2Game()';
  if (m.startsWith('minesweeper_') && on('game_minesweeper_v2')) return 'openMinesweeperGame()';
  if (m === 'chest_revealed') return 'openChestsV1()';
  if (['pet_fed','pet_activity_completed','pet_trek_completed','pet_expedition_completed','pet_watch_completed'].includes(m)) return 'openPetsV1()';
  return "openQuestsV1()";
}
// Новичок (в игре меньше семи дней), который ещё не открывал тему «Первый день»: карточка ведёт туда.
// Уровень аккаунта не годится: он из прошлой версии игры и больше не растёт (services/leveling.py). Тема прочитана (pv_guide_first, app.57.js) — карточки нет.
function _v3Newcomer() {
  try { if (localStorage.getItem('pv_guide_first')) return false; } catch (_) { return false; }
  const d = typeof _profileData !== 'undefined' && _profileData || {}, joined = Date.parse(d.joined_date || '');
  return joined > 0 && Date.now() - joined < 7 * 864e5;
}
function renderV3Next() {
  const host = el('v3-next'); if (!host) return;
  const quests = _v3Quests?.daily?.quests || [], items = _v3Quests?.rewards?.items || {};
  const ready = ['daily', 'weekly', 'combined'].find(kind => items[kind]?.claimable);
  const todo = quests.find(q => !q.completed);
  let title, hint, action;
  if (!ready && _v3Newcomer()) { title = 'Первый день в игре'; hint = 'Пять шагов: с чего начать и что где нажать'; action = "openGuide('first-day')"; }
  else if (ready) { title = 'Забери награду'; hint = `+${fmt(items[ready].amount_mora || 0)} Моры${items[ready].amount_essence ? ` и +${fmt(items[ready].amount_essence)} Эссенции` : ''} уже ждут`; action = `v3ClaimQuestReward('${ready}')`; }
  else if (todo) {
    const target = Math.max(1, Number(todo.target) || 1);
    title = todo.title; hint = `${Math.min(target, Number(todo.progress) || 0)} из ${target} · ${quests.filter(q => q.completed).length} из ${quests.length} заданий за день`;
    action = _v3QuestRoute(todo.metric);
  } else if (quests.length) { title = 'На сегодня всё выполнено'; hint = _v3Tip(); action = 'openLooksModal()'; }
  else { title = 'Открой «Игры»'; hint = 'Задания на сегодня появятся позже'; action = "switchPage('arena')"; }
  const attrs = ready ? ` id="v3-claim" data-kind="${_profileEsc(ready)}" ${_v3Claiming ? 'disabled aria-busy="true"' : ''}` : '';
  if (ready) action = 'v3ClaimQuestReward(this.dataset.kind)';
  host.innerHTML = `<button type="button" class="v3-next"${attrs} onclick="${action}"><span class="v3-next-go" aria-hidden="true">${_v3Icon('chev')}</span>
    <span class="v3-next-t"><span class="v3-eyebrow">Дальше</span><b>${_profileEsc(title)}</b><small>${_profileEsc(hint)}</small></span></button>`;
}

// «Путь»: пять аспектов игры одной строкой, без списка
let _v3Path = null;
function _v3PathShell() {
  return `<section class="v3-path" id="v3-path" aria-label="Прогресс по аспектам игры"><div class="v3-sec"><span class="v3-eyebrow">Путь</span><button type="button" class="v3-link" onclick="openAchievementsV1()">Достижения</button></div><div class="v3-path-row"><div class="sk" style="height:76px;border-radius:14px;flex:1"></div></div></section>`;
}
function loadV3Path() {
  return api('/achievements-v1/me').then(d => { _v3Path = d; renderV3Path(); }).catch(() => renderV3Path(true));
}
function renderV3Path(failed) {
  const host = el('v3-path'); if (!host) return;
  const head = '<div class="v3-sec"><span class="v3-eyebrow">Путь</span><button type="button" class="v3-link" onclick="openAchievementsV1()">Достижения</button></div>';
  const families = _v3Path?.families || [];
  if (failed || !families.length) { host.innerHTML = `${head}<div class="v3-empty">${failed ? 'Прогресс не загрузился. <button type="button" class="v3-link" onclick="loadV3Path()">Повторить</button>' : 'Сыграй разок, и здесь вспыхнут первые кольца.'}</div>`; return; }
  host.innerHTML = `${head}<div class="v3-path-row">${families.map(f => {
    const max = Math.max(1, Number(f.max_level) || 40), level = Math.min(max, Number(f.level) || 0);
    return `<button type="button" class="v3-aspect" data-f="${_profileEsc(f.id || '')}" onclick="openAchievementsV1()" aria-label="${_profileEsc(f.title)}: уровень ${level} из ${max}">
      <span class="v3-aspect-ring">${_v3Ring(level / max * 100)}<b>${level}</b></span><span>${_profileEsc(f.title)}</span></button>`;
  }).join('')}</div>`;
}

// ── Профиль открывается мгновенно: последний ответ показывается сразу, свежий заменяет его ─────────────
// Осторожно: loadProfile() вызывается при загрузке app.02.js, раньше этого файла, поэтому
// v3PaintCachedProfile запускается через setTimeout(0): const верхнего уровня к тому времени уже инициализированы.
let _v3LastSync = Date.now();
function _v3ProfileKey() { return 'pv_profile_v3'; }
function _v3ProfileFields() { return ['user_id', 'username', 'display_name', 'rank', 'account_level', 'xp_into', 'xp_to_next', 'mora', 'diamonds', 'zarniki', 'streak', 'achievements', 'messages_all_time', 'is_vip', 'vip']; }
function v3SaveProfileCache(d) {
  try {
    const slim = {}; _v3ProfileFields().forEach(key => { if (d[key] !== undefined) slim[key] = d[key]; });
    slim.look = d.look || null;
    localStorage.setItem(_v3ProfileKey(), JSON.stringify(slim));
  } catch (_) { /* хранилище недоступно: профиль просто загрузится как обычно */ }
}
function v3ProfileSkeleton() {
  const bar = (w, h = 14) => `<div class="sk" style="height:${h}px;width:${w};border-radius:${h / 2}px"></div>`;
  return `<div class="v3-id" aria-hidden="true"><div class="sk" style="width:76px;height:76px;border-radius:50%;flex:none"></div><div style="flex:1;display:grid;gap:10px">${bar('50%', 22)}${bar('70%')}${bar('40%')}</div></div>
    <div class="sk" style="height:76px;border-radius:14px;margin-top:22px"></div>
    <div class="sk" style="height:150px;border-radius:14px;margin-top:22px"></div>
    <div class="sk" style="height:84px;border-radius:14px;margin-top:22px"></div>`;
}
// true, если показан кэш; иначе вызывающий рисует скелет
function v3PaintCachedProfile() {
  const host = el('pro-main'); if (!host || _profileData) return false;
  try {
    const cached = JSON.parse(localStorage.getItem(_v3ProfileKey()) || 'null');
    const me = tg?.initDataUnsafe?.user?.id;
    if (!cached || !me || Number(cached.user_id) !== Number(me)) { host.innerHTML = v3ProfileSkeleton(); return false; }
    if (typeof v3ApplyLook === 'function') v3ApplyLook(cached.look);
    host.innerHTML = renderProfileHome(cached); if(typeof v3EnterSync==='function')v3EnterSync(host); v3CountUp(host); renderV3Bar(cached); host.dataset.stale = '1';
    return true;
  } catch (_) { host.innerHTML = v3ProfileSkeleton(); return false; }
}
// Вернулся в приложение через минуту и дольше: тихо обновляем «Сегодня» и баланс
document.addEventListener('visibilitychange', () => {
  if (document.hidden || Date.now() - _v3LastSync < 60000) return;
  if (_activePage !== 'profile' || !_profileData) return;
  _v3LastSync = Date.now(); loadV3Today(); _v3RefreshBalance();
});

// Подсказки, когда задания закончились: живая польза вместо пустоты (меняются день ото дня)
function _v3Tip() {
  const tips = ['Эссенция уже капнула: загляните в «Образы» и прокачайте скин', 'Соберите сет скинов: за него положен бонус Эссенции', 'Те же рейтинги видны в чате по команде «бот топ»', 'Питомцам тоже приятно внимание: загляните к ним', 'Завтра будут новые задания, а сегодня можно сыграть для души'];
  return tips[Math.floor(Date.now() / 864e5) % tips.length];
}

// ── Shell V3 · компактные лидерборды: сообщения, Ритм, Сапёр и Мафия ──────────────
const _V3_TOPS = [
  { id: 'week', label: 'Неделя', url: '/leaderboards/messages?period=week', unit: 'сообщ.' },
  { id: 'all_time', label: 'Всё время', url: '/leaderboards/messages?period=all_time', unit: 'сообщ.' },
  { id: 'rhythm', label: 'Ритм', url: '/rhythm-v2/leaderboard/normal', unit: 'очк.', flag: 'game_rhythm_v2' },
  { id: 'minesweeper', label: 'Сапёр', url: '/leaderboards/game/minesweeper', unit: 'поб.', flag: 'game_minesweeper_v2' },
  { id: 'mafia', label: 'Мафия', url: '/leaderboards/game/mafia', unit: 'поб.', flag: 'game_mafia_v1' }
];
let _v3TopTab = 'week', _v3TopCache = {}, _v3TopSeq = 0;
function _v3TopShell() {
  return `<section class="v3-top" id="v3-top" aria-label="Лидерборды"><div class="v3-sec"><span class="v3-eyebrow">Топ-10</span></div><div class="v3-top-body"><div class="sk" style="height:300px;border-radius:14px"></div></div></section>`;
}
// Ответы двух API приводятся к одному виду: {top:[{place,name,value,is_vip,is_me}], personal:{place,value}|null}
function _v3TopNormalize(id, d) {
  if (id === 'rhythm') {
    return { top: (d.top || []).slice(0, 10).map(r => ({ place: r.place, name: r.player?.display_name || 'Игрок', ref: r.player?.profile_ref, value: r.best_score, is_vip: !!r.player?.is_vip, is_me: !!r.is_me, look: r.player?.look || null, mark: r.player?.mark || null, avatar: r.player?.avatar, avatar_state: r.player?.avatar_state, level: r.player?.level })),
      personal: d.personal ? { place: d.personal.place, value: d.personal.best_score } : null };
  }
  if (id === 'minesweeper' || id === 'mafia') {
    return { top: (d.items || []).slice(0, 10).map(r => ({ place: r.place, name: r.name, ref: r.ref, value: r.count, is_vip: r.is_vip, is_me: r.is_me, look: r.look, mark: r.mark, avatar: r.avatar, avatar_state: r.avatar_state, level: r.level })),
      personal: d.personal ? { place: d.personal.place, value: d.personal.count } : null };
  }
  return { top: (d.top || []).map(r => ({ place: r.place, name: r.name, ref: r.ref, value: r.count, is_vip: r.is_vip, is_me: r.is_me, look: r.look, mark: r.mark, avatar: r.avatar, avatar_state: r.avatar_state, level: r.level })),
    personal: d.personal ? { place: d.personal.place, value: d.personal.count } : null };
}
function _v3TopTabs() {
  const tabs = _V3_TOPS.filter(t => !t.flag || _sysFlags[t.flag] === true);
  if (!tabs.some(t => t.id === _v3TopTab)) _v3TopTab = tabs[0].id;
  return tabs;
}
function renderV3Top(state) {
  const host = el('v3-top'); if (!host) return;
  const tabs = _v3TopTabs(), tab = tabs.find(t => t.id === _v3TopTab);
  const head = `<div class="v3-sec"><span class="v3-eyebrow">Топ-10</span><div class="v3-tabs" role="tablist">${tabs.map(t =>
    `<button type="button" role="tab" class="v3-tab${t.id === _v3TopTab ? ' on' : ''}" aria-selected="${t.id === _v3TopTab}" onclick="v3TopSelect('${t.id}')">${t.label}</button>`).join('')}</div></div>`;
  const data = _v3TopCache[_v3TopTab];
  let body;
  if (state === 'error') body = `<div class="v3-empty">Топ не загрузился. <button type="button" class="v3-link" onclick="loadV3Top()">Повторить</button></div>`;
  else if (!data) body = '<div class="sk" style="height:300px;border-radius:14px"></div>';
  else if (!data.top.length) body = typeof v3PodiumEmpty === 'function' ? v3PodiumEmpty('Пока никого в рейтинге. Станьте первым.') : '<div class="v3-empty">Пока никого в рейтинге. Станьте первым.</div>';
  else {
    const inTop = data.top.some(r => r.is_me);
    const podium = typeof v3Podium === 'function' ? v3Podium(data.top, r => `${fmt(r.value)} ${tab.unit}`) : '';   // тройка — подиумом с медалями (app.50.js)
    const rest = podium ? data.top.slice(3) : data.top;
    body = `${podium}${rest.length ? `<ol class="v3-top-list" start="${podium ? 4 : 1}">${rest.map(r => `<li class="${r.is_me ? 'is-me' : ''}">${_v3RowButton(r, r.value)}</li>`).join('')}</ol>` : ''}
      <div class="v3-top-foot"><span class="v3-top-me">${data.personal && !inTop ? `Вы: #${fmt(data.personal.place)} · ${fmt(data.personal.value)} ${tab.unit}` : ''}</span><button type="button" class="v3-link" onclick="${['rhythm', 'minesweeper', 'mafia'].includes(tab.id) ? `openTopV3('${tab.id}')` : `openTopV3('global','${tab.id}')`}">Весь топ ›</button></div>`;
  }
  host.innerHTML = `${head}<div class="v3-top-body">${body}</div>`;
  window.hydrateLeaderboardAvatars?.(host);
}
function loadV3Top() {
  const tabs = _v3TopTabs(), tab = tabs.find(t => t.id === _v3TopTab), mine = ++_v3TopSeq;
  renderV3Top();
  return api(tab.url).then(d => { _v3TopCache[tab.id] = _v3TopNormalize(tab.id, d); })
    .then(() => { if (mine === _v3TopSeq) renderV3Top(); })
    .catch(() => { if (mine === _v3TopSeq) renderV3Top('error'); });
}
function v3TopSelect(id) {
  if (id === _v3TopTab) return;
  _v3TopTab = id;
  if (_v3TopCache[id]) { renderV3Top(); return; }
  loadV3Top();
}

// Топ ниже первого экрана: запрос уходит, только когда блок почти попал в зону видимости
let _v3TopObserver = null;
function v3LazyTop() {
  const host = el('v3-top'); if (!host) return;
  _v3TopObserver?.disconnect();
  if (!('IntersectionObserver' in window)) { loadV3Top(); return; }
  _v3TopObserver = new IntersectionObserver((entries, observer) => {
    if (entries.some(entry => entry.isIntersecting)) { observer.disconnect(); loadV3Top(); }
  }, { rootMargin: '240px 0px' });
  _v3TopObserver.observe(host);
}

// Строка рейтинга: нажатие открывает публичную карточку игрока (ник со стилем виден только у VIP)
// Фото VIP в строке топа (перк VIP: аватарку видно везде); без фото строка как раньше
function _v3RowAva(row) {
  const fallback = _v3Avatar({seed:row.ref || row.name,level:row.level,is_vip:row.is_vip});
  return `<span class="v3-row-ava">${window.leaderboardAvatar ? window.leaderboardAvatar(row,fallback) : fallback}</span>`;
}
function _v3RowButton(row, value) {
  const open = row.ref && /^[A-Za-z0-9_-]{16,64}$/.test(row.ref) ? ` onclick="openPublicProfile('${row.ref}')"` : ' disabled';
  return `<button type="button" class="v3-rowbtn"${open} aria-label="Профиль игрока ${_profileEsc(row.name)}"><i>${row.place}</i>${_v3RowAva(row)}<span>${apWho(row)}</span><b>${typeof value === 'string' ? _profileEsc(value) : fmt(value)}</b></button>`;   // value: число или готовая строка (время Сапёра)
}

// ── Shell V3 · тиры скинов D…SSS: контроллер эффектов ────────────────────────────
// Тир скина (с сервера) задаёт потолок эффектов. Фактический уровень = min(тир, возможности устройства).
// CSS: fx-tiers-v3.css, документация: docs/SKINS_V3.md.
const _V3_TIER_LIST = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
const _V3_FX_CAP_KEY = 'v3_fx_cap', _V3_LITE_KEY = 'v3_lite', _V3_LOW_KEY = 'v3_low';
// Пометка слабого телефона (лёгкий режим, экономный режим, сниженный потолок) хранится в localStorage и без этого держалась бы вечно, даже когда вид уже ускорили. После каждого ускорения
// номер ревизии растёт, пометки сбрасываются, и телефон проверяется заново: если он всё ещё не тянет, замер кадров вернёт пометку через несколько секунд.
const _V3_PERF_REV = '2026-10-12b';
try {
  if (localStorage.getItem('v3_perf_rev') !== _V3_PERF_REV) {
    [_V3_FX_CAP_KEY, _V3_LITE_KEY, _V3_LOW_KEY].forEach(key => localStorage.removeItem(key));
    localStorage.setItem('v3_perf_rev', _V3_PERF_REV);
  }
} catch (_) { /* без хранилища пометок и не было */ }
let _v3Skin = { css_class: '', tier: 'D' }, _v3FxLevel = 1, _v3Forced = false, _v3Watchdog = false, _v3PointerOn = false;

function v3FxLevelNow() { return _v3FxLevel; }
function _v3HardwareCap() {
  let cap = 7;
  try {
    const nav = navigator, mem = nav.deviceMemory, cores = nav.hardwareConcurrency;
    // Safari и WebView на iPhone не отдают deviceMemory, а число ядер там занижено (6 у быстрых моделей): без памяти судим только по самым слабым.
    if ((mem && mem <= 2) || (cores && cores <= 3)) cap = 3;            // слабый телефон
    else if ((mem && mem <= 4) || (!mem && cores && cores <= 4)) cap = 6;   // средний: без лент света SSS; движение образов остаётся, зависимость от кадров решает замер ниже
    if (nav.connection?.saveData) cap = Math.min(cap, 2);
  } catch (_) { /* свойств нет: оценки по железу нет, потолок полный */ }
  return cap;
}
// Потолок эффектов = железо, а если замер кадров не выдержал даже экономный режим, то ещё и записанный замером потолок (он режет только образы с тиром выше потолка)
function _v3DeviceCap() {
  let cap = _v3HardwareCap();
  try {
    const stored = Number(localStorage.getItem(_V3_FX_CAP_KEY));
    if (stored >= 1 && stored < 7) cap = Math.min(cap, stored);
  } catch (_) { /* хранилище недоступно: остаётся оценка по железу */ }
  return cap;
}
// Класс устройства: low (слабый), mid (средний), high, по железу. Решает, сколько движения включать (app.31.js) и какой режим образов нужен. Записанный замером потолок класс не меняет:
// иначе один тяжёлый образ, не выдержавший замер, отнимал бы полный вид у лёгких.
// Режимов образов три: полный (high), лёгкий .ap-lite (mid: частиц вдвое меньше, без «акцентного» слоя сцены) и экономный .ap-low (low или замер кадров не выдержал:
// фирменные детали и фон стоят на месте). Полный вид никогда не отключается «на всякий случай»: вниз ведёт только железо или замер кадров.
function _v3Class() { const cap = _v3HardwareCap(); return cap <= 3 ? 'low' : cap <= 6 ? 'mid' : 'high'; }
// Пометка «кадры не выдержал» хранит номер тира образа (1…7 = D…SSS), на котором это случилось, и действует на этот тир и выше: телефон, не тянущий SSS, лёгкие образы показывает полностью.
const _v3TierNo = () => _V3_TIER_LIST.indexOf(_v3Skin.tier) + 1;
function _v3Mark(key) { try { return Math.max(0, Number(localStorage.getItem(key)) || 0); } catch (_) { return 0; /* без памяти: только оценка по железу */ } }
function _v3Marked(key) { const from = _v3Mark(key); return from > 0 && _v3TierNo() >= from; }
function _v3Lite() { return _v3Marked(_V3_LITE_KEY) || _v3Marked(_V3_LOW_KEY) || _v3Class() !== 'high'; }
function _v3Low() { return _v3Marked(_V3_LOW_KEY) || _v3Class() === 'low'; }
function _v3Calm() {
  return document.body.classList.contains('no-fx') || !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
}
function _v3Rand(seed) { const x = Math.sin(seed * 9301 + 49297) * 233280; return x - Math.floor(x); }
// Фон страницы (B и выше) рисует JS на ОДНОМ холсте размером с экран, а не слоями CSS. Сначала слоёв было пять (дыхание, зерно, наклон, две ленты), потом три (акварель body::before, пятна света, зерно): каждый слой на весь
// экран это экран текстуры в памяти и экран заливки на каждом кадре. На телефоне с плотностью 3 набиралось больше 60 МБ графики, и на SSS экран мигал, элементы пропадали и появлялись, кадры падали до 10.
// Теперь холст один (1 пиксель = 1 пиксель CSS): акварель, пятна света и зерно рисуются в нём в том же порядке, в каком лежали слоями. Акварель и зерно не меняются: они собраны один раз на запасных холстах и просто
// копируются. Пятна считаются на крошечном холсте (1 пиксель = 4 пикселя экрана; мягкие градиенты, браузер растягивает их сам). Движение медленное, поэтому пятна пересчитываются раз в 200 мс.
// Формулы те же, что были в CSS: размеры, прозрачность, сроки и ease-in-out (v3breath 9 с, v3ribbon 26 и 34 с, сдвиг по наклону 10 px).
const _V3_FX = { glow: null, low: null, wash: null, grain: null, washList: null, washKey: null, timer: 0, size: 0, w: 0, h: 0, rgb: ['216,207,253', '216,207,253', '216,207,253'], loop: 1, colorsAt: 0, tilt: [0, 0], frozen: false };   // frozen: только для проверок (tools/ui_skin_lab.py)
const _V3_FX_STEP = 200, _V3_FX_SCALE = 4;
function _v3Ease(x) {   // cubic-bezier(.42, 0, .58, 1): ease-in-out из CSS
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  let t = x;
  for (let i = 0; i < 6; i++) {
    const u = 1 - t, cx = 3 * u * u * t * .42 + 3 * u * t * t * .58 + t * t * t, dx = 1.26 * u * u + .96 * u * t + 1.26 * t * t;
    if (Math.abs(cx - x) < 1e-5 || dx < 1e-6) break;
    t -= (cx - x) / dx;
  }
  const u = 1 - t; return 3 * u * t * t + t * t * t;
}
// Акварель страницы это токен --v3-wash: два эллипса света radial-gradient(RX% RY% at X% Y%, rgba(...), transparent S%). Читается в список; запись не по этой форме возвращает null,
// и тогда акварель остаётся слоем CSS (body::before), холст её не трогает.
function _v3FxParseWash(text) {
  if (!text || text === 'none') return [];
  const re = /radial-gradient\(\s*(-?[\d.]+)%\s+(-?[\d.]+)%\s+at\s+(-?[\d.]+)%\s+(-?[\d.]+)%\s*,\s*rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)\s*,\s*transparent\s+(-?[\d.]+)%\s*\)/g;
  const list = []; let rest = text, m;
  while ((m = re.exec(text))) {
    list.push({ rx: +m[1] / 100, ry: +m[2] / 100, x: +m[3] / 100, y: +m[4] / 100, rgb: `${m[5]},${m[6]},${m[7]}`, a: m[8] === undefined ? 1 : +m[8], end: Math.max(0, Math.min(1, +m[9] / 100)) });
    rest = rest.replace(m[0], '');
  }
  return rest.replace(/[\s,]+/g, '') === '' && list.length ? list : null;
}
function _v3FxPaintWash() {   // запасной холст с акварелью: нижний градиент рисуется первым, как нижний слой background
  const list = _V3_FX.washList, cv = _V3_FX.glow, wash = _V3_FX.wash;
  if (!cv || !wash || !list) return;
  const W = wash.width = cv.width, H = wash.height = cv.height, ctx = wash.getContext('2d');
  for (let i = list.length - 1; i >= 0; i--) {
    const g = list[i]; ctx.save(); ctx.translate(g.x * W, g.y * H); ctx.scale(g.rx * W, g.ry * H);
    const fill = ctx.createRadialGradient(0, 0, 0, 0, 0, 1); fill.addColorStop(0, `rgba(${g.rgb},${g.a})`); fill.addColorStop(g.end, `rgba(${g.rgb},0)`);
    ctx.fillStyle = fill; ctx.fillRect(-g.x / g.rx, -g.y / g.ry, 1 / g.rx, 1 / g.ry); ctx.restore();
  }
}
function _v3FxColors() {   // цвета берутся из токенов образа; читаются не чаще раза в полторы секунды
  const now = performance.now(); if (now - _V3_FX.colorsAt < 1500) return; _V3_FX.colorsAt = now;
  const body = document.body, cs = getComputedStyle(body), probe = document.createElement('i');
  probe.style.cssText = 'position:absolute;visibility:hidden;pointer-events:none'; body.appendChild(probe);
  const color = name => {
    probe.style.color = `var(${name})`;
    const text = getComputedStyle(probe).color, n = (text.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
    return n.length === 3 ? n.map(v => Math.round(/^color\(/.test(text) ? v * 255 : v)).join(',') : '216,207,253';
  };
  _V3_FX.rgb = [(cs.getPropertyValue('--acc-rgb').trim().replace(/\s+/g, '') || '216,207,253'), color('--v3-fx-a'), color('--v3-fx-b')];
  _V3_FX.loop = parseFloat(cs.getPropertyValue('--v3-loop')) || 1;
  probe.remove();
  const wash = cs.getPropertyValue('--v3-wash').trim();
  if (wash !== _V3_FX.washKey) {   // смена образа или режима OLED: акварель собирается заново, слой CSS уходит, пока холст её держит
    _V3_FX.washKey = wash; _V3_FX.washList = _v3FxParseWash(wash); _v3FxPaintWash();
    body.classList.toggle('v3-fx-wash', !!_V3_FX.washList && !!_V3_FX.glow?.getContext('2d'));
  }
}
// Один кадр света. ms: время в миллисекундах (для проверок кадр можно нарисовать на любом моменте).
function _v3FxFrame(ms) {
  const cv = _V3_FX.glow, ctx = cv && cv.getContext('2d'), low = _V3_FX.low, lc = low && low.getContext('2d'); if (!ctx || !lc) return;
  _v3FxColors();
  const W = _V3_FX.w || innerWidth, H = _V3_FX.h || innerHeight, level = _v3FxLevel, [acc, fa, fb] = _V3_FX.rgb, loop = _V3_FX.loop, k = low.width / W;   // размер экрана кэшируется: чтение innerWidth заставляет браузер пересчитать стили всех анимаций
  lc.setTransform(1, 0, 0, 1, 0, 0); lc.clearRect(0, 0, low.width, low.height); lc.setTransform(k, 0, 0, k, 0, 0);
  const blob = (cx, cy, rx, ry, rgb, alpha, end = 1) => {   // эллипс с мягким краем: radial-gradient(closest-side, цвет, transparent)
    lc.save(); lc.translate(cx, cy); lc.scale(rx, ry); lc.globalAlpha = alpha;
    const g = lc.createRadialGradient(0, 0, 0, 0, 0, 1); g.addColorStop(0, `rgba(${rgb},1)`); g.addColorStop(end, `rgba(${rgb},0)`);
    lc.fillStyle = g; lc.fillRect(-1, -1, 2, 2); lc.restore();
  };
  const swing = (seconds, back) => { const p = (ms / (seconds * 1000 * loop)) % 2, q = p < 1 ? p : 2 - p; return _v3Ease(back ? 1 - q : q); };   // alternate / alternate-reverse
  { const e = swing(9), s = 1 + .08 * e; blob(.5 * W, .5 * H - .6 * H * s, .72 * W * s, .48 * H * s, acc, .2 * (.35 + .65 * e), .7); }   // дыхание: свет сверху, 9 с
  if (level >= 6) {   // два пятна, которые сдвигаются от наклона телефона
    const bw = 1.12 * W, bh = 1.12 * H, ox = -.06 * W + _V3_FX.tilt[0] * 10, oy = -.06 * H + _V3_FX.tilt[1] * 10;
    blob(ox + .4 * bw, oy + .29 * bh, .4 * bw, .25 * bh, fa, .22); blob(ox + .7 * bw, oy + .67 * bh, .4 * bw, .25 * bh, fb, .14);
  }
  if (level >= 7) {   // две ленты света, 26 и 34 с
    const e1 = swing(26), e2 = swing(34, true);
    blob(.5 * W + (-.08 + .16 * e1) * 1.5 * W, .2 * H + .06 * e1 * .7 * H, .75 * W * (.9 + .2 * e1), .35 * H * (.9 + .2 * e1), fa, .16);
    blob(.5 * W + (-.08 + .16 * e2) * 1.5 * W, .9 * H + .06 * e2 * .7 * H, .75 * W * (.9 + .2 * e2), .35 * H * (.9 + .2 * e2), fb, .12);
  }
  // порядок слоёв как был: акварель, пятна света, зерно
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (_V3_FX.washList) { ctx.globalCompositeOperation = 'copy'; ctx.drawImage(_V3_FX.wash, 0, 0); ctx.globalCompositeOperation = 'source-over'; } else ctx.clearRect(0, 0, cv.width, cv.height);
  ctx.drawImage(low, 0, 0, cv.width, cv.height);
  if (_V3_FX.grain) ctx.drawImage(_V3_FX.grain, 0, 0);
}
function _v3FxRun() {
  clearTimeout(_V3_FX.timer);
  if (!_V3_FX.glow || document.hidden || _V3_FX.frozen) return;
  _v3FxFrame(performance.now());
  _V3_FX.timer = setTimeout(_v3FxRun, _V3_FX_STEP);
}
// Зерно: плитка шума 160 px на запасном холсте размером с экран, 1 пиксель = 1 пиксель CSS. Прозрачность .07 (она раньше стояла в CSS) вшита в плитку; шум не меняется, поэтому зерно собирается один раз.
function _v3FxPaintGrain() {
  const cv = _V3_FX.glow, grain = _V3_FX.grain; if (!cv || !grain) return;
  grain.width = cv.width; grain.height = cv.height;
  const ctx = grain.getContext('2d'), tile = document.createElement('canvas'); tile.width = tile.height = 160;
  const tc = tile.getContext('2d'), img = tc.createImageData(160, 160), d = img.data;
  for (let i = 0; i < d.length; i += 4) { d[i] = d[i + 1] = d[i + 2] = 255; d[i + 3] = Math.round(230 * .07 * (Math.random() + Math.random() + Math.random()) / 3); }
  tc.putImageData(img, 0, 0); ctx.fillStyle = ctx.createPattern(tile, 'repeat'); ctx.fillRect(0, 0, grain.width, grain.height);
}
function _v3FxResize() {
  _V3_FX.w = innerWidth; _V3_FX.h = innerHeight;
  const cv = _V3_FX.glow, low = _V3_FX.low; if (!cv || !low) return;
  const w = Math.max(1, Math.ceil(innerWidth)), h = Math.max(1, Math.ceil(innerHeight));
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  low.width = Math.max(1, Math.ceil(w / _V3_FX_SCALE)); low.height = Math.max(1, Math.ceil(h / _V3_FX_SCALE));
  _V3_FX.colorsAt = 0; _V3_FX.washKey = null; _v3FxColors();   // акварель читается заново и рисуется под новый размер
  if (_V3_FX.grain) _v3FxPaintGrain();
  _v3FxRun();
}
function _v3BuildFx(level) {
  document.querySelector('.v3-fx')?.remove(); clearTimeout(_V3_FX.timer);
  _V3_FX.glow = _V3_FX.low = _V3_FX.wash = _V3_FX.grain = null; _V3_FX.washList = null; document.body.classList.remove('v3-fx-wash');
  if (level < 3) return;
  const layer = document.createElement('div'); layer.className = 'v3-fx'; layer.setAttribute('aria-hidden', 'true');
  _V3_FX.glow = Object.assign(document.createElement('canvas'), { className: 'v3-fx-glow' }); layer.appendChild(_V3_FX.glow);
  _V3_FX.low = document.createElement('canvas'); _V3_FX.wash = document.createElement('canvas');
  if (level >= 4) _V3_FX.grain = document.createElement('canvas');
  document.body.appendChild(layer); _v3FxResize();
}
window.addEventListener('resize', () => { clearTimeout(_V3_FX.size); _V3_FX.size = setTimeout(_v3FxResize, 200); }, { passive: true });
let _v3FxOled = document.body.classList.contains('pv-oled');   // режим OLED меняет --v3-wash: холст узнаёт об этом сразу, а не через полторы секунды
new MutationObserver(() => {
  const oled = document.body.classList.contains('pv-oled'); if (oled === _v3FxOled) return;
  _v3FxOled = oled; _V3_FX.colorsAt = 0; _v3FxRun();
}).observe(document.body, { attributes: true, attributeFilter: ['class'] });
// Наклон телефона и указатель двигают слой SS+. В руке телефон никогда не лежит неподвижно: сырой наклон дрожит, а запись переменной в body пересчитывает стиль всей страницы.
// Поэтому: ноль берётся из первого замера, дрожь меньше мёртвой зоны гасится, движение сглаживается и пишется только в слой эффектов (не в body), редко и пока есть что менять.
function _v3BindTilt() {
  if (_v3PointerOn) return; _v3PointerOn = true;
  let frame = 0, goalX = 0, goalY = 0, curX = 0, curY = 0, base = null, lastPush = 0;
  const push = now => {
    frame = 0;
    curX += (goalX - curX) * 0.1; curY += (goalY - curY) * 0.1;
    if (now - lastPush >= 66 && (Math.abs(goalX - curX) > 0.004 || Math.abs(goalY - curY) > 0.004)) {   // не чаще 15 раз в секунду
      lastPush = now; _V3_FX.tilt = [curX, curY];
      _v3FxRun();   // свет сдвигается вслед за наклоном сразу, а не на следующем шаге таймера
    }
    if (Math.abs(goalX - curX) > 0.004 || Math.abs(goalY - curY) > 0.004) frame = requestAnimationFrame(push);
  };
  const aim = (x, y) => { if (Math.abs(x - goalX) < 0.06 && Math.abs(y - goalY) < 0.06) return; goalX = x; goalY = y; if (!frame) frame = requestAnimationFrame(push); };
  window.addEventListener('deviceorientation', e => {
    if (_v3FxLevel < 6 || e.gamma == null || document.hidden) return;
    if (!base) base = [e.gamma, e.beta];
    aim(Math.max(-1, Math.min(1, (e.gamma - base[0]) / 40)), Math.max(-1, Math.min(1, (e.beta - base[1]) / 40)));
  }, { passive: true });
  window.addEventListener('pointermove', e => { if (_v3FxLevel < 6 || e.pointerType === 'touch') return; aim(e.clientX / innerWidth * 2 - 1, e.clientY / innerHeight * 2 - 1); }, { passive: true });
}
function applySkinTier(skin, options = {}) {
  _v3Skin = { css_class: skin?.css_class || '', tier: _V3_TIER_LIST.includes(skin?.tier) ? skin.tier : 'D' };
  _v3Forced = !!options.force;
  const nominal = _V3_TIER_LIST.indexOf(_v3Skin.tier) + 1;
  const level = _v3Calm() ? 1 : _v3Forced ? nominal : Math.min(nominal, _v3DeviceCap());
  _v3FxLevel = level;
  const body = document.body;
  [...body.classList].forEach(name => { if (/^fx-\d$/.test(name) || /^tier-[a-z]+$/.test(name)) body.classList.remove(name); });
  for (let i = 1; i <= level; i++) body.classList.add(`fx-${i}`);
  body.classList.add(`tier-${_v3Skin.tier.toLowerCase()}`); body.dataset.tier = _v3Skin.tier;
  body.classList.toggle('ap-anim', !_v3Calm() && _v3DeviceCap() >= 3);   // движение образов (рамки, ореолы, частицы) не зависит от тира своего скина
  body.classList.toggle('ap-lite', _v3Lite()); body.classList.toggle('ap-low', _v3Low()); body.dataset.dev = _v3Class();   // лёгкий режим: частиц вдвое меньше; экономный: образ стоит на месте (fx-tiers-v3.css)
  _v3BuildFx(level); if (level >= 6) _v3BindTilt();
  _v3StartWatchdog(level);
}
// Если устройство не тянет: после показа замеряем кадры. Сначала включается лёгкий режим образов, затем экономный, и только если и после него кадры медленные,
// потолок эффектов снижается на две ступени (запоминается). Замер идёт на каждом образе (с его тиром), показанном в этом сеансе, и только пока образ на экране:
// раньше он шёл один раз за сеанс, и лёгкий образ при входе пропускал тяжёлый SSS, надетый позже; а замер без образа на экране не видел ничего.
const _v3Measured = new Set();
const _v3MeasureKey = () => `${document.body.dataset.skin || ''}:${_v3Skin.tier}`;
function _v3StartWatchdog(level) {
  if (_v3Watchdog || _v3Forced || level < 3 || _v3Measured.has(_v3MeasureKey())) return; _v3Watchdog = true;
  const stageShown = () => [...document.querySelectorAll('.ap-stage:not(.ap-off)')].some(n => n.offsetHeight > 150);   // сцена профиля, а не крошечные превью в списках
  const measure = (done, toasts = 0, idle = 0) => setTimeout(() => {
    if (document.hidden) { _v3Watchdog = false; return; }   // вкладка в фоне: замер повторится при следующем показе
    if (document.querySelector('#toast.show, #gift-toast') && toasts < 4) { measure(done, toasts + 1, idle); return; }   // пока на экране тост: он сам тянет кадры, замер подождёт (до десяти секунд)
    if (!stageShown()) { if (idle < 24) measure(done, toasts, idle + 1); else _v3Watchdog = false; return; }   // образа нет на экране: ждём до минуты, дальше замер повторится со следующим образом или показом вкладки
    const times = []; let last = performance.now(), count = 0;
    const tick = now => {
      times.push(now - last); last = now;
      if (++count < 90) { requestAnimationFrame(tick); return; }
      const sorted = times.slice(5).sort((a, b) => a - b); done(sorted[Math.floor(sorted.length / 2)]);
    };
    requestAnimationFrame(tick);
  }, 2500);
  const finish = () => { _v3Watchdog = false; _v3Measured.add(_v3MeasureKey()); };
  const lower = median => {
    if (median <= 30 || _v3FxLevel <= 2) return;
    try { localStorage.setItem(_V3_FX_CAP_KEY, String(Math.max(2, _v3FxLevel - 2))); } catch (_) { /* не сохранится: сработает снова в следующем сеансе */ }
    applySkinTier(_v3Skin);
  };
  // Ступени вниз: полный вид -> лёгкий (.ap-lite) -> экономный (.ap-low) -> ниже потолок эффектов. Каждая ступень включается только если кадры правда медленные.
  const mark = key => { try { const prev = _v3Mark(key); localStorage.setItem(key, String(prev ? Math.min(prev, _v3TierNo()) : _v3TierNo())); } catch (_) { /* не сохранится: сработает снова в следующем сеансе */ } };
  const step = median => {
    if (median <= 26) { finish(); return; }
    if (!_v3Lite()) { mark(_V3_LITE_KEY); applySkinTier(_v3Skin); measure(step); return; }
    if (!_v3Low()) { mark(_V3_LOW_KEY); applySkinTier(_v3Skin); measure(step); return; }
    lower(median); finish();
  };
  measure(step);
}
document.addEventListener('skinchange', e => applySkinTier(e.detail));
document.addEventListener('visibilitychange', () => { document.body.classList.toggle('v3-paused', document.hidden); _v3FxRun(); if (!document.hidden) _v3StartWatchdog(_v3FxLevel); });
// Круг от касания: только на SSS
document.addEventListener('pointerdown', e => {
  if (_v3FxLevel < 7) return;
  const ring = document.createElement('i'); ring.className = 'v3-ripple'; document.body.appendChild(ring);
  const run = ring.animate([{ transform: `translate(${e.clientX}px,${e.clientY}px) scale(.2)`, opacity: .9 }, { transform: `translate(${e.clientX}px,${e.clientY}px) scale(2.2)`, opacity: 0 }], { duration: 650, easing: 'cubic-bezier(.22,1,.36,1)' });
  run.onfinish = () => ring.remove();
}, { passive: true });
// Предпросмотр палитры и тира без покупки (консоль разработчика): v3SkinPreview('skin-neon-lime', 'SSS')
window.v3SkinPreview = (cssClass, tier) => {
  [...document.body.classList].forEach(name => { if (/^skin-/.test(name)) document.body.classList.remove(name); });
  if (/^skin-[a-z0-9-]{1,80}$/.test(cssClass || '')) document.body.classList.add(cssClass);
  applySkinTier({ css_class: cssClass, tier }, { force: true });
};
// Эффекты вне экрана не рисуются и не считаются: пока образ (сцена, рамка, ореол, частицы, фирменная деталь) или блик ника не виден, на нём класс .ap-off, а в CSS он стоит на паузе
// (fx-tiers-v3.css). Запас 120 px, чтобы движение уже шло, когда блок въезжает в экран. Строки списков не наблюдаются: их блики и так выключены.
const _AP_WATCH = '.ap-stage, .ap-name, .ap-title';
const _apIO = typeof IntersectionObserver === 'function'
  ? new IntersectionObserver(list => list.forEach(e => e.target.classList.toggle('ap-off', !e.isIntersecting)), { rootMargin: '120px 0px' }) : null;
function _apWatch(node) {
  if (!_apIO || node.nodeType !== 1) return;
  if (node.matches(_AP_WATCH)) _apIO.observe(node);
  node.querySelectorAll(_AP_WATCH).forEach(n => { if (!n.closest('.v3-who')) _apIO.observe(n); });
}
if (_apIO) {
  _apWatch(document.body);
  new MutationObserver(list => list.forEach(m => m.addedNodes.forEach(_apWatch))).observe(document.body, { childList: true, subtree: true });
}
applySkinTier({ css_class: '', tier: 'D' });

// ── Shell V3 · экран «Топ»: то же, что «бот топ» в чате, но на сайте ─────────────
const _V3_TOP_SCOPES = [{ id: 'global', label: 'Все игроки' }, { id: 'chats', label: 'Чаты' }, { id: 'local', label: 'Мой чат' }, { id: 'rhythm', label: 'Ритм', flag: 'game_rhythm_v2' }, { id: 'minesweeper', label: 'Сапёр', flag: 'game_minesweeper_v2' }, { id: 'mafia', label: 'Мафия', flag: 'game_mafia_v1' }];
const _V3_TOP_PERIODS = [{ id: 'day', label: 'Сегодня' }, { id: 'week', label: 'Неделя' }, { id: 'month', label: 'Месяц' }, { id: 'all_time', label: 'Всё время' }];
let _v3Full = { scope: 'global', period: 'week', chat: null, page: 0, data: null, failed: false, loading: false, photoRetries:0, photoTimer:null }, _v3FullSeq = 0;

function openTopV3(scope, period) {
  if (scope) _v3Full.scope = scope;
  if (period) _v3Full.period = period;
  _v3Full.page = 0; _v3Full.data = null; _v3Full.failed = false;
  switchPage('top'); renderTopV3(); loadTopV3();
}
function loadTopV3(quiet = false) {
  clearTimeout(_v3Full.photoTimer); if (!quiet) _v3Full.photoRetries = 0;
  const mine = ++_v3FullSeq, f = _v3Full;
  if (f.scope === 'local' && f.chat == null) { const first = _profileData?.chats?.[0]?.chat_tg_id; if (first) f.chat = Number(first); }
  const query = new URLSearchParams({ scope: f.scope, period: f.period, page: String(f.page) });
  if (f.scope === 'local' && f.chat != null) query.set('chat_id', String(f.chat));
  f.failed = false; f.loading = !quiet; if (!quiet) renderTopV3();   // прежний список остаётся на экране, пока идёт запрос: серого блока на долю секунды больше нет
  const url = f.scope === 'rhythm' ? `/rhythm-v2/leaderboard/normal/full?page=${f.page}` : f.scope === 'minesweeper' || f.scope === 'mafia' ? `/leaderboards/game/${f.scope}?page=${f.page}` : `/leaderboards/messages/full?${query}`;
  return api(url).then(d => {
    if (mine !== _v3FullSeq) return;
    if (f.scope === 'rhythm') d = _v3RhythmFull(d);
    f.data = d; f.failed = false; f.loading = false; if (f.scope === 'local' && f.chat == null && d.chats?.length) f.chat = d.chats[0].chat_id;
    renderTopV3();
    if (f.scope==='chats' && d.items?.some(r=>r.avatar_pending) && f.photoRetries++<3) {
      f.photoTimer=setTimeout(()=>{ if (_activePage==='top' && mine===_v3FullSeq && !document.hidden) loadTopV3(true); },3000);
    }
  }).catch(e => { if (mine !== _v3FullSeq) return; f.failed = String(e || 'Ошибка'); f.loading = false; renderTopV3(); });
}
// Сезонная таблица Ритма приводится к виду таблицы сообщений: очки идут в count
function _v3RhythmFull(d) {
  const items = (d.items || []).map(r => ({ place: r.place, name: r.player?.display_name || 'Игрок', ref: r.player?.profile_ref, look: r.player?.look || null, mark: r.player?.mark || null, is_vip: !!r.player?.is_vip, is_me: !!r.is_me, count: r.best_score, avatar: r.player?.avatar, avatar_state: r.player?.avatar_state, level: r.player?.level }));
  const personal = d.personal ? { place: d.personal.place, total: d.personal.total, count: d.personal.best_score } : null;
  return { page: d.page, pages: d.pages, items, personal, season: d.season, chats: _v3Full.data?.chats };
}
function v3FullSet(key, value) {
  const f = _v3Full; if (f[key] === value) return;
  f[key] = key === 'chat' ? Number(value) : value; if (key !== 'page') f.page = 0;
  _haptic('select'); loadTopV3();
}
function chatThemeStyle(r) {
  const palette = Array.isArray(r.palette) && r.palette.length===3 && r.palette.every(c=>/^#[0-9a-f]{6}$/i.test(c)) ? r.palette : ['#8ba5df','#817ccf','#b6c3e4'];
  return `--chat-a:${palette[0]};--chat-b:${palette[1]};--chat-c:${palette[2]}`;
}
function chatThemeAvatar(r) {
  const photo = _validAvatar(r.avatar) ? `<img src="${_profileEsc(_avatarSrc(r.avatar))}" alt="" decoding="async" loading="lazy" onerror="this.remove()">` : '';
  return `<span class="chat-theme-avatar"><span aria-hidden="true">${_profileEsc(Array.from(r.name || 'Ч').slice(0,1).join(''))}</span>${photo}</span>`;
}
function _v3FullRow(r, scope) {
  if (scope === 'chats') return `<li class="chat-theme" style="${chatThemeStyle(r)}"><div class="v3-rowbtn"><i>${r.place}</i>${chatThemeAvatar(r)}<span>${_profileEsc(r.name)}<small>${fmt(r.users)} уч.</small></span><b>${fmt(r.count)}</b></div></li>`;
  return `<li class="${r.is_me ? 'is-me' : ''}">${_v3RowButton(r, r.count)}</li>`;
}
function renderTopV3() {
  const host = el('pg-top'); if (!host) return;
  const f = _v3Full, d = f.data, hasChat = !!(d?.chats?.length || _profileData?.chats?.length);
  const scopes = _V3_TOP_SCOPES.filter(s => (s.id !== 'local' || hasChat) && (!s.flag || _sysFlags[s.flag] === true)), rhythm = f.scope === 'rhythm', winBoard = f.scope === 'minesweeper' || f.scope === 'mafia', game = rhythm || winBoard;
  const unit = rhythm ? 'очк.' : winBoard ? 'поб.' : 'сообщ.';
  const seg = (items, current, key) => items.map(i => `<button type="button" role="tab" class="v3-tab${i.id === current ? ' on' : ''}" aria-selected="${i.id === current}" onclick="v3FullSet('${key}','${i.id}')">${i.label}</button>`).join('');
  const chatPick = f.scope === 'local' && d?.chats?.length > 1
    ? `<label class="sr-only" for="v3-top-chat">Чат</label><select id="v3-top-chat" class="v3-select" onchange="v3FullSet('chat',this.value)">${d.chats.map(c => `<option value="${c.chat_id}"${c.chat_id === f.chat ? ' selected' : ''}>${_profileEsc(c.title)}</option>`).join('')}</select>` : '';
  let body;
  if (f.failed) body = `<div class="v3-empty">${_profileEsc(f.failed)} <button type="button" class="v3-link" onclick="loadTopV3()">Повторить</button></div>`;
  else if (!d) body = '<div class="sk" style="height:340px;border-radius:14px"></div>';
  else if (!d.items.length) {
    const text = rhythm ? 'В этом сезоне ещё нет подтверждённых забегов.' : winBoard ? 'Пока нет побед. Завершите партию победой — и вы первым окажетесь в списке.' : f.scope === 'chats' ? 'Пока тихо: чаты попадут сюда, когда в них начнут писать.' : 'Пока тихо. Напишите в чате, и вы первым окажетесь в списке.';
    body = typeof v3PodiumEmpty === 'function' ? v3PodiumEmpty(text) : `<div class="v3-empty">${text}</div>`;
  }
  else {
    const me = d.personal ? `<div class="v3-top-me">Вы: #${fmt(d.personal.place)} из ${fmt(d.personal.total)} · ${fmt(d.personal.count)} ${unit}${d.personal.delta != null ? ` · <span class="${d.personal.delta >= 0 ? 'v3-up' : ''}">${d.personal.delta >= 0 ? '+' : ''}${fmt(d.personal.delta)} к прошлому периоду</span>` : ''}</div>`
      : (f.scope === 'chats' ? '' : `<div class="v3-top-me">${rhythm ? 'Вашего забега в этом сезоне пока нет.' : winBoard ? 'У вас пока нет побед.' : 'У вас пока нет сообщений за выбранный период.'}</div>`);
    const pager = d.pages > 1 ? `<div class="v3-pager"><button type="button" class="v3-link" ${d.page <= 0 ? 'disabled' : ''} onclick="v3FullSet('page',${d.page - 1})" aria-label="Предыдущая страница">‹</button><span>${d.page + 1} / ${d.pages}</span><button type="button" class="v3-link" ${d.page + 1 >= d.pages ? 'disabled' : ''} onclick="v3FullSet('page',${d.page + 1})" aria-label="Следующая страница">›</button></div>` : '';
    // на первой странице тройка — подиумом с медалями (app.50.js), список продолжается с 4-го места
    const podium = d.page === 0 && typeof v3Podium === 'function' ? v3Podium(d.items, r => `${fmt(r.count)} ${unit}`) : '', rows = podium ? d.items.slice(3) : d.items;
    body = `${podium}${me}${rows.length ? `<div class="v3-ranking-labels"><span>Место · ${f.scope === 'chats' ? 'чат' : 'игрок'}</span><span>${rhythm ? 'Очки' : winBoard ? 'Победы' : 'Сообщения'}</span></div><ol class="v3-top-list v3-top-list--full">${rows.map(r => _v3FullRow(r, f.scope)).join('')}</ol>` : ''}${pager}`;
  }
  const sub = rhythm ? `Лучшие забеги Ритма${d?.season ? ` · сезон ${fmt(d.season.number)}` : ''}.` : winBoard ? `Больше всех побед в ${f.scope === 'minesweeper' ? 'Сапёре' : 'Мафии'} за всё время.` : `Кто задаёт темп ${f.period === 'all_time' ? 'за всё время' : f.period === 'day' ? 'сегодня' : f.period === 'month' ? 'в этом месяце' : 'на этой неделе'}.`;
  host.innerHTML = `${v3Head('Топ', { sub, back: "switchPage('profile')", end: v3GuideIcon('top') })}
    <div class="v3-tabs v3-tabs--wide" role="tablist" aria-label="Область рейтинга">${seg(scopes, f.scope, 'scope')}</div>
    ${game ? '' : `<div class="v3-tabs v3-tabs--wide" role="tablist" aria-label="Период">${seg(_V3_TOP_PERIODS, f.period, 'period')}</div>`}
    ${chatPick}<div class="v3-top-body${f.loading && d ? ' is-loading' : ''}" aria-live="polite" aria-busy="${!!f.loading}">${body}</div>`;
  v3EnterSync(host);
  window.hydrateLeaderboardAvatars?.(host);
}

// ── Skins V3 · рендер образа: ник, титул, рамка, ореол, сцена ─────────────────────
// Образ приходит с сервера одним объектом: {tier, ceiling, pal:[a,b,c], kinds:{frame,halo,pt,name,bg}, sig, title}.
// Палитра и форма берутся из скина, богатство — из тира (D…SSS = 1…7). Потолок у всех один, SSS; редкость (rarity) задаёт только цену и ряд коллекции.
// Фирменная деталь (sig) открывается с тира sig_from: у образов редкости S и выше со своей редкости, у остальных на SSS. Без VIP чужой образ приходит без pal/kinds, тогда ap = null и рисуется базовый вид.
const _AP_TIERS = ['D', 'C', 'B', 'A', 'S', 'SS', 'SSS'];
const _AP_WORD = /^[a-z_]{2,16}$/, _AP_HEX = /^#[0-9a-f]{6}$/i;
const _AP_POWER = [0, .4, .5, .6, .72, .85, .95, 1];
const _AP_DUST = [0, 6, 8, 11, 15, 20, 26, 34];
function _apTi(tier) { return _AP_TIERS.indexOf(tier) + 1; }
function apFromLook(look) {
  const ti = _apTi(look?.tier), kinds = look?.kinds, pal = look?.pal;
  if (!ti || !kinds || !Array.isArray(pal) || pal.length < 3 || !pal.every(c => _AP_HEX.test(c))) return null;
  const word = value => (_AP_WORD.test(value || '') ? value : '');
  return {
    look, ti, tier: look.tier, id: String(look.id || ''), title: String(look.title || ''),
    k: { frame: word(kinds.frame), halo: word(kinds.halo), pt: word(kinds.pt), name: word(kinds.name), bg: word(kinds.bg) },
    sig: look.sig && ti >= _apTi(look.sig_from || look.ceiling) && _AP_WORD.test(look.sig) ? look.sig : '',
    vars: `--ap-a:${pal[0]};--ap-b:${pal[1]};--ap-c:${pal[2]};--ap-i:${_AP_POWER[ti]}`,
  };
}
const _apSig = ap => (ap.sig ? ` ap-sig-${ap.sig}` : '');
const _apSk = ap => (/^[a-z_]{2,24}$/.test(ap.id || '') ? ` data-sk="${ap.id}"` : '');   // id образа на каждом слое: личные образы дорисовывают себя по нему (skins-exclusive-v3.css)
const _AP_GLINT_KINDS = ['shimmer', 'foil', 'grad', 'ink', 'lens', 'comet'];   // виды ника, по буквам которых идёт блик (те же, что в appearance-v3.css; от тира A)
const v3GlintMark = text => `<span class="ap-gl" aria-hidden="true"><span data-t="${_profileEsc(text)}"></span></span>`;   // блик крупного заголовка S+ (fx-tiers-v3.css): белая копия текста в «окне», едет через transform
// Шапка вкладки (docs/MINIAPP_DESIGN_RULES.md, п. 5): «‹» только у экранов вне нижнего меню, заголовок, одна строка пояснения, справа необязательное действие (end — готовая разметка). title и sub — простой текст, экранируются
function v3Head(title, { sub = '', back = '', end = '' } = {}) {
  const btn = back ? `<button type="button" class="v3-head-back" onclick="${back}" aria-label="Назад">‹</button>` : '';
  const emb = typeof _V3_HEAD_EMB === 'object' && _V3_HEAD_EMB ? _V3_HEAD_EMB[title] : '';   // эмблема и созвездие вкладки (app.50.js)
  return `<header class="v3-head${emb ? ' v3-head--hero' : ''}">${emb ? V3_SKY : ''}${btn}${emb ? v3Emblem(emb) : ''}<div class="v3-head-tx"><h1 class="v3-title">${esc(title)}${v3GlintMark(title)}</h1>${sub ? `<p class="v3-head-s">${esc(sub)}</p>` : ''}</div>${end}</header>`;
}
// Скелетон загрузки вместо текста «Загрузка…»: n серых строк списка; подпись читает экранный диктор
function v3Skel(label = 'Загружаем…', n = 3) { return `<div class="v3-skel" role="status" aria-label="${esc(label)}">${'<div class="sk sk-row"></div>'.repeat(n)}</div>`; }
function apName(ap, html, plain) {
  if (!ap) return html;
  const text = plain ?? String(html).replace(/<[^>]*>/g, '').replace(/&(amp|lt|gt|quot|#39|#x27);/g, e => ({'&amp;':'&','&lt;':'<','&gt;':'>','&quot;':'"','&#39;':"'",'&#x27;':"'"}[e]));
  return typeof window.skinNicknameV3 === 'function' ? window.skinNicknameV3(ap, html, text) : html;
}
function apCrest(ap) {   // знак собранного сета: сервер присылает его только владельцу или тем, кто вправе видеть образ
  const c = ap?.look?.crest;
  return c && typeof c.glyph === 'string' ? `<span class="ap-crest" style="${ap.vars}" title="${_profileEsc(c.name || '')}" role="img" aria-label="${_profileEsc(c.name || 'Сет')}">${_profileEsc(c.glyph)}</span>` : '';
}
function apTitle(ap) {
  const title = ap && ap.title ? `<span class="ap-title ap-t${ap.ti}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}">${_profileEsc(ap.title)}</span>` : '';
  return ap ? apCrest(ap) + title : '';
}
function apHalo(ap) { return ap ? `<i class="ap-halo ap-t${ap.ti} ap-ha-${ap.k.halo}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}" aria-hidden="true"><b></b><b></b><b></b></i>` : ''; }
function apFrame(ap) {
  return ap ? `<i class="ap-frame ap-t${ap.ti} ap-fr-${ap.k.frame}${_apSig(ap)}"${_apSk(ap)} style="${ap.vars}" aria-hidden="true">${typeof apFrameOrn === 'function' ? apFrameOrn(ap) : ''}${ap.sig && typeof apSigDecor === 'function' ? apSigDecor(ap.sig) : ''}</i>` : '';
}
// Частицы сцены: число растёт с тиром; положение детерминировано, чтобы кадр не прыгал при перерисовке
function _apDust(ap) {
  return Array.from({ length: _AP_DUST[ap.ti] || 0 }, (_, i) => {
    const r = n => { const x = Math.sin((i + 1) * 12.9898 + n * 78.233) * 43758.5453; return x - Math.floor(x); };
    return `<i style="--x:${(r(1) * 100).toFixed(1)}%;--y:${(r(2) * 80).toFixed(1)}%;--s:${(3 + r(3) * 4).toFixed(1)}px;--d:${(10 + r(4) * 9).toFixed(1)}s;--delay:-${(r(5) * 14).toFixed(1)}s;--dx:${((r(6) - .5) * 70).toFixed(0)}px;--r:${(r(7) * 360).toFixed(0)}deg"></i>`;
  }).join('');
}
// Сцена профиля: фон и частицы за блоком личности. inner — сам блок. Без образа возвращается как есть.
function apStage(ap, inner) {
  if (!ap) return inner;
  const cls = `ap-t${ap.ti}${_apSig(ap)}`;
  return `<div class="ap-stage ${cls}"${_apSk(ap)} style="${ap.vars}"><div class="ap-bg ${cls} ap-bg-${ap.k.bg}" aria-hidden="true"><b></b><b></b></div>${apScene(ap)}<div class="ap-fx ${cls} ap-pt-${ap.k.pt}" aria-hidden="true">${_apDust(ap)}</div>${typeof apOrn === 'function' ? apOrn(ap) : ''}${inner}</div>`;
}
// Имя и титул одной строки списка (топ): ник со стилем, титул-«таблетка», точка VIP
function apWho(row) {
  const ap = apFromLook(row.look);
  return `<span class="v3-who"><span>${ap ? apName(ap, _profileEsc(row.name)) : `<span class="ap-plain">${_profileEsc(row.name)}</span>`}${row.is_vip ? ' <em class="v3-vipdot" aria-label="VIP"></em>' : ''}${v3MarkDot(row.mark)}</span>${apTitle(ap)}</span>`;
}

// ── Аватар: фото VIP или личное созвездие. Здесь, а не в профиле: тот же аватар рисуют топы страниц игр (top-board-v3.js) ──
function _validAvatar(value) {
  return typeof value === 'string' && (/^data:image\/(?:png|jpe?g|webp);base64,[A-Za-z0-9+/=]+$/.test(value)
    || /^\/profile\/avatar\/[A-Za-z0-9_-]{16,64}\?v=[0-9a-f]{16}$/.test(value));
}
function _avatarSrc(value) {
  return value.startsWith('/') ? BASE + value : value;
}
function _v3Avatar(d) {
  const constellation = _v3Constellation(d.seed ?? d.user_id ?? d.display_name ?? d.username, d.account_level ?? d.level, !!d.is_vip);   // без фото: личное созвездие (app.20.js)
  if (!_validAvatar(d.avatar)) return constellation;
  // The photo address can fail (VIP ended, network): the image then turns back into the constellation.
  return `<img src="${_profileEsc(_avatarSrc(d.avatar))}" alt="" decoding="async" data-fallback="${_profileEsc(constellation)}" onerror="this.outerHTML=this.dataset.fallback">`;
}

// ── Аватар без фото: личное созвездие ──────────────────────────────────────────────
// У каждого игрока своё созвездие: рисунок задаёт id (одно и то же на любом устройстве), число звёзд растёт с уровнем аккаунта (4 → 9), а звёзды,
// уже появившиеся, не двигаются. Цвета берутся из токенов образа, поэтому созвездие всегда в тон. Главная звезда у VIP золотая.
function _cnRand(text) {
  let h = 1779033703 ^ text.length;
  for (let i = 0; i < text.length; i++) { h = Math.imul(h ^ text.charCodeAt(i), 3432918353); h = (h << 13) | (h >>> 19); }
  return () => { h = Math.imul(h ^ (h >>> 16), 2246822507); h = Math.imul(h ^ (h >>> 13), 3266489909); return ((h ^= h >>> 16) >>> 0) / 4294967296; };
}
const _cnCount = level => Math.min(9, 4 + Math.floor(((Number(level) || 1) - 1) / 6));
// Новый уровень добавил звезду: она вспыхивает на месте (вызов из v3Delights). Фото вместо созвездия: ничего не происходит
function v3GrowStar(from, to) {
  if (_cnCount(to) <= _cnCount(from)) return;
  document.querySelector('#pro-showcase-ava .cn-st circle:last-child')?.classList.add('cn-pop');
}
function _v3Constellation(seed, level, vip) {
  const rand = _cnRand(String(seed ?? 'player')), count = _cnCount(level);
  const pts = [], edges = [];
  for (let i = 0; i < count; i++) {       // лучший из нескольких кандидатов: звёзды расходятся по кругу, а не липнут друг к другу
    let best = null, gap = -1;
    for (let t = 0; t < 14; t++) {
      const a = rand() * 6.2832, r = 11 + Math.sqrt(rand()) * 27, p = [50 + Math.cos(a) * r, 50 + Math.sin(a) * r];
      const far = pts.length ? Math.min(...pts.map(q => Math.hypot(q[0] - p[0], q[1] - p[1]))) : 99;
      if (far > gap) { best = p; gap = far; }
    }
    const size = i ? 1.2 + rand() * 1.3 : 0, extra = rand() < .38;
    if (pts.length) {                      // линия к ближайшей из прежних звёзд, иногда ещё одна: получается фигура, а не веер
      const order = pts.map((q, j) => [Math.hypot(q[0] - best[0], q[1] - best[1]), j]).sort((x, y) => x[0] - y[0]);
      edges.push([order[0][1], i]); if (extra && order[1]) edges.push([order[1][1], i]);
    }
    pts.push(best); best.size = size;
  }
  const f = n => n.toFixed(1), main = pts[0], back = _cnRand(`${seed}-dust`);   // фоновая пыль считается отдельно: с ростом уровня она не сдвигается
  const dust = Array.from({ length: 7 }, () => { const a = back() * 6.2832, r = Math.sqrt(back()) * 43; return `<circle cx="${f(50 + Math.cos(a) * r)}" cy="${f(50 + Math.sin(a) * r)}" r="${f(.45 + back() * .4)}"/>`; }).join('');
  const path = edges.map(([a, b]) => `M${f(pts[a][0])} ${f(pts[a][1])}L${f(pts[b][0])} ${f(pts[b][1])}`).join('');
  const dots = pts.slice(1).map((p, i) => `<circle class="${i % 3 === 1 ? 'cn-tw' : ''}" cx="${f(p[0])}" cy="${f(p[1])}" r="${f(p.size)}"/>`).join('');
  const [x, y] = main.map(Number), k = 6.5;
  const spark = `M${f(x)} ${f(y - k)}Q${f(x)} ${f(y)} ${f(x + k)} ${f(y)}Q${f(x)} ${f(y)} ${f(x)} ${f(y + k)}Q${f(x)} ${f(y)} ${f(x - k)} ${f(y)}Q${f(x)} ${f(y)} ${f(x)} ${f(y - k)}Z`;
  return `<svg class="cn${vip ? ' cn-vip' : ''}" viewBox="0 0 100 100" aria-hidden="true" focusable="false"><circle class="cn-bg" cx="50" cy="50" r="50"/><g class="cn-dust">${dust}</g><path class="cn-ln" d="${path}"/><g class="cn-st">${dots}</g><circle class="cn-glow" cx="${f(x)}" cy="${f(y)}" r="11"/><path class="cn-main" d="${spark}"/></svg>`;
}

// ── Skins V3 · скин приложения и фирменные детали ───────────────────────────────
// v3ApplyLook: палитра надетого скина приходит с сервера токенами и ставится на body (без отдельного CSS на скин).
// Тир скина управляет уровнем эффектов (app.18.js). Без скина остаётся базовая палитра из shell-v3.css.
const _V3_TOKEN = /^--(?:v3-[a-z-]{2,16}|acc-rgb)$/;
let _v3Applied = [];
// Токены скина как строка style для .v3-scope (витрина, публичная карточка): те же проверки, что и для body
function v3TokenStyle(tokens) {
  if (!tokens || typeof tokens !== 'object') return '';
  return Object.entries(tokens).filter(([key, value]) => _V3_TOKEN.test(key) && _v3SafeValue(value)).map(([key, value]) => `${key}:${value}`).join(';');
}
function _v3SafeValue(value) { return typeof value === 'string' && value.length < 400 && !/[;{}<>\\]|url\(|@import|expression/i.test(value); }
function v3ApplyLook(look) {
  const style = document.body.style;
  _v3Applied.forEach(key => style.removeProperty(key));
  _v3Applied = [];
  [...document.body.classList].forEach(name => { if (/^skin-/.test(name)) document.body.classList.remove(name); });   // наследие прежних скинов
  const tokens = look && typeof look.tokens === 'object' ? look.tokens : null;
  if (tokens) {
    for (const [key, value] of Object.entries(tokens)) {
      if (_V3_TOKEN.test(key) && _v3SafeValue(value)) { style.setProperty(key, value); _v3Applied.push(key); }
    }
  }
  document.body.dataset.skin = look && /^[a-z_]{2,24}$/.test(look.id || '') ? look.id : '';
  document.dispatchEvent(new CustomEvent('skinchange', { detail: { css_class: '', tier: _AP_TIERS.includes(look?.tier) ? look.tier : 'D' } }));
}

// Фирменные детали: живут внутри рамки аватара и открываются, когда скин прокачан до своего потолка.
// Форма и движение описаны в skin-signatures-v3.css и skin-signatures-2-v3.css.
const _AP_DECOR = (() => {
  const many = (cls, count, vars) => Array.from({ length: count }, (_, i) => `<u class="${cls}" style="${vars(i)}"></u>`).join('');
  return {
    void: '<u class="sg-shadow"></u><u class="sg-disk"></u><u class="sg-arc"></u><u class="sg-arc sg-arc--low"></u>',
    aurora: '<u class="sg-veil"></u><u class="sg-veil"></u><u class="sg-veil"></u>',
    solar: many('sg-prom', 7, i => `--o:${i * 51.4}deg;--d:${(2.2 + (i % 3) * .5).toFixed(1)}s;--l:${(.7 + (i % 3) * .18).toFixed(2)}`),
    petalstorm: many('sg-pet', 9, i => `--o:${i * 40}deg;--r:${44 + (i % 3) * 8}px;--d:${(9 + (i % 4) * 2).toFixed(0)}s`),
    artifact: '<svg class="sg-hex" viewBox="0 0 100 100"><polygon points="50,2 93,26 93,74 50,98 7,74 7,26"/><polygon class="sg-hex-in" points="50,10 86,30 86,70 50,90 14,70 14,30"/></svg>' + many('sg-drone', 3, i => `--o:${i * 120}deg`) + '<u class="sg-tear"></u>',
    lotus: `<u class="sg-bloom">${[-58, -29, 0, 29, 58].map(a => `<u class="sg-leaf" style="--o:${a}deg"></u>`).join('')}${[-38, 0, 38].map(a => `<u class="sg-leaf sg-leaf--f" style="--o:${a}deg"></u>`).join('')}</u><u class="sg-moon"></u>`,
    tide: '<u class="sg-scales"></u><u class="sg-crack"></u>' + many('sg-wave', 3, i => `--i:${i}`),
    comet: '<u class="sg-orbit"><u class="sg-head"></u></u><u class="sg-orbit sg-orbit--far"><u class="sg-head"></u></u>',
    chrono: '<u class="sg-dial"></u><u class="sg-hand sg-hand--min"></u><u class="sg-hand sg-hand--hour"></u><u class="sg-cog"></u><u class="sg-cog sg-cog--r"></u>',
    heart: '<u class="sg-pulse"></u><u class="sg-pulse"></u><u class="sg-pulse"></u><u class="sg-core"></u>',
    // личные образы: глянцевые банты с орбитой звёзд и багровая луна с брызгами (skins-exclusive-v3.css); подтёки у «Багрового Мрака» с первого тира, их рисует apFrameOrn
    bowstar: () => _ornBow('sg-bow') + _ornBow('sg-bow sg-bow--s') + many('sg-star', 3, () => ''),
    bloodmoon: '<u class="sg-bmoon"></u><u class="sg-splat"></u>',
  };
})();
function apSigDecor(sig) { const draw = _AP_DECOR[sig]; return typeof draw === 'function' ? draw() : draw || ''; }

// ── Личные образы: свой слой SVG на сцене и на рамке ──────────────────────────────────────────────────────────
// «Алая Звезда» рисует глянцевые банты с цепочкой бусин, блёстки и звёзды в обводке; «Багровый Мрак» мокрые подтёки, брызги и отпечаток ладони.
// Это вектор: чёткий на любом экране, красится палитрой образа и двигается только под .ap-anim (skins-exclusive-v3.css). Богатство растёт с тиром:
// деталь с номером r появляется с тира r. Градиенты и фильтр лежат один раз в скрытом SVG страницы, поэтому их видит любая копия сцены (профиль, топ, предпросмотр).
const _ORN_DEFS = '<svg id="orn-defs" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
  + '<linearGradient id="ornBow" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff7a90"/><stop offset=".45" stop-color="#e3183c"/><stop offset="1" stop-color="#8a0a20"/></linearGradient>'
  + '<linearGradient id="ornBlood" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#3a0508"/><stop offset=".42" stop-color="#8e111a"/><stop offset="1" stop-color="#4a070c"/></linearGradient>'
  + '<linearGradient id="ornBand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7c0d15"/><stop offset="1" stop-color="#2e0407"/></linearGradient>'
  + '<radialGradient id="ornSplat" cx=".4" cy=".4" r=".7"><stop offset="0" stop-color="#781019"/><stop offset="1" stop-color="#2c0306"/></radialGradient>'
  + '<filter id="ornRough" x="-10%" y="-10%" width="120%" height="120%"><feTurbulence type="fractalNoise" baseFrequency=".05" numOctaves="2" seed="4" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="7"/><feGaussianBlur stdDeviation=".5"/></filter>'
  + '</defs></svg>';
function _ornDefs() { if (!document.getElementById('orn-defs')) document.body.insertAdjacentHTML('beforeend', _ORN_DEFS); }
// Бант как на образце: два широких округлых крыла, узел по центру и два хвоста с V-вырезом на концах. Хвосты рисуются первыми, крылья поверх них
const _ORN_BOW_TAILS = ['M29.5 27L12 54.5L22 51.5L25.5 57.5L33.5 29Z', 'M34.5 27L52 54.5L42 51.5L38.5 57.5L30.5 29Z'];
const _ORN_BOW_WINGS = ['M27 19C22 8 12 3 6 7C0 11 0 25 6 30C12 34 22 31 27 27Z', 'M37 19C42 8 52 3 58 7C64 11 64 25 58 30C52 34 42 31 37 27Z'];
const _ORN_STAR = 'M12 2.6l2.9 6.2 6.8.8-5 4.7 1.3 6.7L12 17.6 6 21l1.3-6.7-5-4.7 6.8-.8z';
function _ornBow(cls) { _ornDefs(); return `<svg class="o-bow ${cls}" viewBox="0 0 64 59" aria-hidden="true">${_ORN_BOW_TAILS.map(d => `<path class="o-w" d="${d}"/>`).join('')}${_ORN_BOW_WINGS.map(d => `<path class="o-w" d="${d}"/>`).join('')}<path class="o-fold" d="M26.5 22.5C23 20.5 19 20.5 15.5 22.5M37.5 22.5C41 20.5 45 20.5 48.5 22.5"/><path class="o-hl" d="M9 11C12 8 16 7 20 9M55 11C52 8 48 7 44 9"/><rect class="o-knot" x="27" y="17" width="10" height="13" rx="4"/><path class="o-hl" d="M29.5 20.5V25"/></svg>`; }
const _ORN = (() => {
  const bow = _ornBow;
  const spark = (cls, d) => `<svg class="o-sp ${cls}" style="--d:${d}s" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 1l2.6 8.4L23 12l-8.4 2.6L12 23l-2.6-8.4L1 12l8.4-2.6z"/></svg>`;
  const star = (cls, d) => `<svg class="o-st ${cls}" style="--d:${d}s" viewBox="0 0 24 24" aria-hidden="true"><path d="${_ORN_STAR}"/></svg>`;
  const chain = (cls, d) => { const pts = Array.from({ length: 12 }, (_, k) => [8 + 3.5 * Math.sin(k * .7), 5 + k * 9]);
    return `<svg class="o-chain ${cls}" style="--d:${d}s" viewBox="0 0 16 112" aria-hidden="true"><path d="M${pts.map(p => p.map(n => n.toFixed(1)).join(' ')).join('L')}"/>${pts.map((p, k) => `<circle cx="${p[0].toFixed(1)}" cy="${p[1]}" r="${k % 2 ? 1.7 : 2.5}"/>`).join('')}</svg>`; };
  const scarlet = [[1, bow('o-b1')], [1, bow('o-b2')], [1, chain('c1', 6)], [1, spark('sa', 3.1)], [1, spark('sb', 4.2)], [1, spark('sc', 3.6)], [1, star('sa', 6)], [1, star('sb', 7)], [1, star('sc', 5.5)],
    [2, spark('sd', 4.8)], [2, star('sd', 6.5)], [3, chain('c2', 7.5)], [5, spark('se', 3.9)], [5, spark('sf', 5.1)], [5, star('se', 7.5)], [6, spark('sg', 3.3)], [7, star('sg', 8)]];
  // подтёки: [x, длина, с какого тира]; по краю сцены 390 в ширину, обрезка по центру (slice), поэтому форма не тянется
  const DR = [[26, 34, 1], [101, 52, 1], [186, 40, 1], [268, 58, 1], [311, 30, 1], [352, 44, 1], [58, 22, 2], [143, 28, 2], [229, 24, 3], [380, 20, 4]];
  const FALL = [[101, 52, 3], [268, 58, 3], [186, 40, 5]];
  const drip = (x, l, i) => `<g class="dr" style="--d:${(6 + (i * 7) % 5).toFixed(0)}s;--i:${i}"><path class="o-wet" d="M${x - 4.2} 8V${l}a4.2 4.2 0 0 0 8.4 0V8z"/><rect class="o-gl" x="${x - 2.3}" y="13" width="1.5" height="${Math.max(4, l - 19)}" rx=".75"/><circle class="o-gl" cx="${x - 1.4}" cy="${l + 1.6}" r=".9"/></g>`;
  const fall = (x, l, i) => `<g transform="translate(${x} ${l + 11})"><path class="fl o-wet" style="--d:${(7 + i * 2)}s;--dl:${-i * 2.3}s" d="M0-5C2.6-1.8 3.6.4 3.6 1.8a3.6 3.6 0 0 1-7.2 0C-3.6.4-2.6-1.8 0-5z"/></g>`;
  // Тень подтёков (прежний drop-shadow(0 2px 3px) на всём svg): фильтр на svg, внутри которого каждый кадр двигаются подтёки и падают капли, пересчитывался целиком на каждом кадре (почти треть кадра на образе).
  // Теперь тень это три обводки той же формы со сдвигом на 2 px вниз (шире и слабее, уже и плотнее: мягкий край выходит ступенчатым, как размытие; ширины и прозрачности подобраны по пикселям прежней тени: в среднем 0,4% яркости разницы), они лежат под полосой и движутся вместе с подтёком.
  const BAND = 'M0 0H390V9Q372 14 355 9T320 9T285 10T250 9T215 10T180 9T145 10T110 9T75 10T40 9T0 10z', FALL_D = 'M0-3C2.6.2 3.6 2.4 3.6 3.8a3.6 3.6 0 0 1-7.2 0C-3.6 2.4-2.6.2 0-3z';
  const SH = ['', ' o-sh--m', ' o-sh--n'], shade = d => SH.map(c => `<path class="o-sh${c}" d="${d}"/>`).join('');
  const dripShade = (x, l, i) => `<g class="dr" style="--d:${(6 + (i * 7) % 5).toFixed(0)}s;--i:${i}">${shade(`M${x - 4.2} 10V${l + 2}a4.2 4.2 0 0 0 8.4 0V10z`)}</g>`;
  const fallShade = (x, l, i) => `<g transform="translate(${x} ${l + 11})">${SH.map(c => `<path class="fl o-sh${c}" style="--d:${(7 + i * 2)}s;--dl:${-i * 2.3}s" d="${FALL_D}"/>`).join('')}</g>`;
  const splat = (cls, d, sats) => `<svg class="o-splat ${cls}" viewBox="0 0 100 100" aria-hidden="true"><path d="${d}"/><g>${sats}</g></svg>`;
  const SPL = { a: ['M72.4 46.1Q66.1 49.5 65.3 51.5Q64.4 53.5 63.3 54.7Q62.2 55.9 61.6 57.5Q61.0 59.1 59.5 60.8Q58.0 62.6 56.3 62.5Q54.6 62.4 53.3 64.0Q52.0 65.6 50.0 65.1Q48.0 64.7 46.9 62.4Q45.8 60.0 43.5 62.1Q41.2 64.2 39.6 62.3Q37.9 60.5 37.6 58.7Q37.2 57.0 37.8 55.1Q38.4 53.2 39.0 51.7Q39.6 50.2 29.8 47.1Q20.1 43.9 28.7 43.7Q37.2 43.5 34.8 38.2Q32.3 32.9 31.9 28.7Q31.5 24.5 36.5 26.0Q41.5 27.5 45.1 33.2Q48.7 38.9 49.9 38.2Q51.0 37.6 52.2 38.8Q53.3 40.0 55.1 40.2Q57.0 40.3 62.9 37.5Q68.9 34.7 66.2 38.6Q63.6 42.6 71.1 42.7Q78.7 42.7 72.4 46.1Z', '<circle cx="63.8" cy="91.2" r="1.9"/><circle cx="37.2" cy="81.7" r="2.1"/><circle cx="81.7" cy="33.3" r="2.9"/><circle cx="90.4" cy="52.8" r="2.3"/><circle cx="34.8" cy="16.6" r="2.4"/><circle cx="94.6" cy="45.9" r="2.1"/><circle cx="20.6" cy="76.4" r="3.6"/><circle cx="96.1" cy="50.1" r="3.5"/><circle cx="9.9" cy="23.6" r="1.1"/><circle cx="68.4" cy="94.3" r="2.6"/><circle cx="19.4" cy="33.9" r="1.5"/><circle cx="18.1" cy="62.3" r="2.6"/>'], b: ['M65.8 48.2Q67.0 49.3 63.6 50.9Q60.3 52.4 69.8 58.1Q79.4 63.7 70.7 62.3Q61.9 60.9 60.2 61.0Q58.4 61.2 56.5 62.3Q54.5 63.5 52.8 62.7Q51.0 61.8 49.5 61.8Q48.0 61.8 46.1 62.9Q44.2 64.1 38.6 68.9Q33.0 73.7 36.5 66.3Q39.9 58.9 31.2 62.0Q22.5 65.2 27.8 59.4Q33.1 53.6 35.8 51.8Q38.6 50.0 38.2 48.6Q37.8 47.2 37.9 45.3Q37.9 43.3 38.0 41.0Q38.0 38.7 35.7 31.1Q33.3 23.6 39.0 29.0Q44.7 34.3 45.2 26.9Q45.6 19.5 48.9 27.7Q52.2 35.8 53.5 35.9Q54.8 35.9 59.9 31.9Q65.0 27.9 61.8 35.2Q58.7 42.5 61.7 42.6Q64.7 42.7 64.7 44.9Q64.7 47.1 65.8 48.2Z', '<circle cx="44.8" cy="6.9" r="2.8"/><circle cx="94.4" cy="54.3" r="2.1"/><circle cx="14.2" cy="71.4" r="2.2"/><circle cx="41.5" cy="83.0" r="3.3"/><circle cx="83.0" cy="60.3" r="2.7"/><circle cx="84.3" cy="82.4" r="2.4"/><circle cx="82.2" cy="62.4" r="3.0"/><circle cx="75.6" cy="85.8" r="2.0"/><circle cx="90.5" cy="67.8" r="1.7"/><circle cx="86.4" cy="55.1" r="3.0"/><circle cx="74.0" cy="14.2" r="2.0"/><circle cx="56.1" cy="86.3" r="3.3"/>'], c: ['M62.1 48.5Q63.7 49.4 64.1 51.8Q64.4 54.2 62.1 54.9Q59.7 55.6 59.4 56.8Q59.1 58.0 58.7 60.0Q58.2 62.0 56.5 61.5Q54.8 61.0 53.6 63.9Q52.4 66.8 50.4 64.1Q48.3 61.4 44.3 67.4Q40.4 73.3 41.9 66.3Q43.5 59.2 40.8 60.4Q38.1 61.6 32.7 62.2Q27.3 62.7 30.5 58.0Q33.7 53.2 33.2 51.8Q32.7 50.4 34.0 48.3Q35.2 46.3 34.9 44.4Q34.6 42.5 29.9 34.8Q25.2 27.2 34.3 33.3Q43.3 39.4 44.5 39.3Q45.7 39.2 46.0 32.5Q46.2 25.8 49.6 23.0Q53.0 20.2 53.9 27.8Q54.7 35.5 55.8 37.5Q57.0 39.5 64.5 35.6Q72.1 31.7 67.1 37.5Q62.1 43.3 61.3 45.5Q60.5 47.6 62.1 48.5Z', '<circle cx="83.9" cy="44.7" r="3.0"/><circle cx="69.2" cy="21.7" r="3.1"/><circle cx="21.9" cy="81.4" r="1.1"/><circle cx="85.0" cy="60.6" r="3.5"/><circle cx="64.7" cy="92.1" r="3.4"/><circle cx="86.3" cy="36.2" r="2.0"/><circle cx="5.7" cy="43.1" r="1.4"/><circle cx="49.5" cy="4.8" r="3.2"/><circle cx="96.0" cy="60.8" r="1.3"/><circle cx="27.0" cy="85.8" r="3.4"/><circle cx="24.9" cy="89.6" r="2.5"/><circle cx="35.3" cy="85.5" r="1.5"/>'] };
  const hand = '<svg class="o-hand" viewBox="0 0 100 130" aria-hidden="true"><g filter="url(#ornRough)"><rect x="25" y="22" width="11" height="46" rx="5.5" transform="rotate(-12 30 66)"/><rect x="39" y="10" width="12" height="56" rx="6" transform="rotate(-3 45 64)"/><rect x="54" y="14" width="11" height="52" rx="5.5" transform="rotate(5 60 64)"/><rect x="67" y="32" width="10" height="38" rx="5" transform="rotate(15 72 68)"/><rect x="5" y="66" width="11" height="38" rx="5.5" transform="rotate(-50 12 92)"/><path d="M26 66C22 92 30 120 50 124C72 120 80 92 76 66z"/></g></svg>';
  const crimson = ti => `<svg class="o-drips" viewBox="0 0 390 90" preserveAspectRatio="xMidYMin slice" aria-hidden="true">`
    + `<g class="o-shd"><g transform="translate(0 2)">${shade(BAND)}</g>${DR.filter(d => d[2] <= ti).map((d, i) => dripShade(d[0], d[1], i)).join('')}${FALL.filter(d => d[2] <= ti).map((d, i) => fallShade(d[0], d[1], i)).join('')}</g><path class="o-band" d="${BAND}"/>`
    + `${DR.filter(d => d[2] <= ti).map((d, i) => drip(d[0], d[1], i)).join('')}${FALL.filter(d => d[2] <= ti).map((d, i) => fall(d[0], d[1], i)).join('')}</svg>`
    + splat('sa', ...SPL.a) + splat('sb', ...SPL.b) + (ti >= 3 ? splat('sc', ...SPL.c) : '') + hand;
  return { scarlet_star: ti => scarlet.filter(o => o[0] <= ti).map(o => o[1]).join(''), crimson_dark: crimson };
})();
// Подтёки под кольцом аватара: четыре, вид и движение те же, что у подтёков сцены
const _ORN_FRAME = { crimson_dark: ti => `<svg class="o-rd" viewBox="0 0 92 60" preserveAspectRatio="none" aria-hidden="true">${[[14, 28], [38, 48], [56, 22], [78, 36]].map(([x, l], i) => `<g class="dr" style="--d:${6 + i}s"><path class="o-wet" d="M${x - 4.4} 0V${l}a4.4 4.4 0 0 0 8.8 0V0z"/><rect class="o-gl" x="${x - 2.4}" y="4" width="1.5" height="${l - 8}" rx=".75"/></g>`).join('')}</svg>` };
function apOrn(ap) { const draw = _ORN[ap.id]; if (!draw) return ''; _ornDefs(); return `<div class="ap-orn ap-t${ap.ti}" data-sk="${ap.id}" aria-hidden="true">${draw(ap.ti)}</div>`; }
function apFrameOrn(ap) { const draw = _ORN_FRAME[ap.id]; if (!draw) return ''; _ornDefs(); return draw(ap.ti); }

// ── Мелочи, от которых приятно ───────────────────────────────────────────────────
// Приветствие по времени игрока (если часы устройства сбиты, берётся время бота; в годовщину и после долгого отсутствия оно меняется),
// счёт чисел при открытии, поздравления с уровнем и серией, пасхалка.
const _V3_LS = { visit: 'pv_last_visit', level: 'pv_last_level', streak: 'pv_streak_step', anniv: 'pv_anniv_seen', counts: 'pv_counts_v3' };
const _lsGet = key => { try { return localStorage.getItem(key); } catch (_) { return null; } };
const _lsSet = (key, value) => { try { localStorage.setItem(key, value); } catch (_) { /* приватный режим: просто без памяти */ } };
let _v3Skew = 0, _v3ServerTz = 180, _v3SkewKnown = false, _v3Gap = null;
const _v3Plural = (n, one, few, many) => { const m = Math.abs(n) % 100, d = m % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };

// Часы бота (UTC+3 по умолчанию) нужны как запасной вариант, если часы на устройстве явно врут
function v3NoteServerClock(clock) {
  const server = clock?.iso ? Date.parse(clock.iso) : NaN;
  if (Number.isNaN(server)) return;
  _v3Skew = server - Date.now(); _v3ServerTz = Number.isFinite(clock.offset_min) ? clock.offset_min : 180; _v3SkewKnown = true;
}
function v3Hour() {
  const device = new Date(), broken = Number.isNaN(device.getTime()) || device.getFullYear() < 2024 || (_v3SkewKnown && Math.abs(_v3Skew) > 36 * 3600e3);
  if (!broken || !_v3SkewKnown) return device.getHours();
  return new Date(Date.now() + _v3Skew + _v3ServerTz * 60e3).getUTCHours();
}
function _v3Hello() {
  const h = v3Hour();
  return h >= 23 || h < 2 ? 'Доброй ночи' : h < 5 ? 'Не спится? Доброй ночи' : h < 12 ? 'Доброе утро' : h < 18 ? 'Добрый день' : 'Добрый вечер';
}
// Приветствие подводит к имени, которое стоит строкой ниже: «Добрый день, <ник>». Серия не вставляется в приветствие: она есть в показателях
// под шапкой и в поздравлении на рубеже, а «приветствие + цифра» читается как галочка. Исключения: годовщина и возвращение, это слова человеку.
function _v3GreetLead(d) {
  const joined = d?.joined_date ? new Date(d.joined_date) : null, now = new Date();
  if (joined && !Number.isNaN(joined.getTime()) && joined.getMonth() === now.getMonth() && joined.getDate() === now.getDate() && now.getFullYear() > joined.getFullYear()) {
    const years = now.getFullYear() - joined.getFullYear();
    return `Сегодня ${years} ${_v3Plural(years, 'год', 'года', 'лет')} с нами`;
  }
  if (_v3Gap != null && _v3Gap >= 3) return 'С возвращением';
  return _v3Hello();
}
function v3GreetHtml(d) { return `${_profileEsc(_v3GreetLead(d))},`; }

// Сколько осталось до обновления заданий (период считается по UTC)
function v3UntilReset() {
  const now = new Date(), next = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1), mins = Math.max(1, Math.round((next - now.getTime()) / 60000));
  return mins >= 60 ? `${Math.floor(mins / 60)} ч${mins % 60 >= 5 && mins < 600 ? ` ${mins % 60} мин` : ''}` : `${mins} мин`;
}

// Числа не прыгают, а набегают: от того, что игрок видел раньше, до нового значения
function v3CountUp(root) {
  const calm = typeof _v3Calm === 'function' ? _v3Calm() : false, prevAll = JSON.parse(_lsGet(_V3_LS.counts) || '{}'), seen = {};
  root.querySelectorAll('[data-n]').forEach(node => {
    const key = node.dataset.key, to = Number(node.dataset.n) || 0, from = Number(prevAll[key]) || 0, short = node.dataset.f === 'short';
    seen[key] = to;
    const draw = value => { node.textContent = short ? _v3Short(Math.round(value)) : fmt(Math.round(value)); };
    if (calm || from === to || Math.abs(to - from) < 1) { draw(to); return; }
    const t0 = performance.now(), span = Math.min(900, 380 + Math.abs(to - from) / Math.max(1, to) * 700);
    const tick = now => { const k = Math.min(1, (now - t0) / span), ease = 1 - Math.pow(1 - k, 3); draw(from + (to - from) * ease); if (k < 1 && node.isConnected) requestAnimationFrame(tick); else draw(to); };
    requestAnimationFrame(tick);
  });
  if (typeof v3RingIn === 'function') v3RingIn(root, prevAll, seen);
  _lsSet(_V3_LS.counts, JSON.stringify({ ...prevAll, ...seen }));
}

// Один раз за запуск: возвращение, новый уровень, серия, годовщина, новые регалии
const _V3_STREAK_STEPS = [3, 7, 14, 30, 50, 100, 200, 365];
function v3Delights(d) {
  const today = new Date().toISOString().slice(0, 10), level = Number(d.account_level) || 1, streak = Number(d.streak) || 0;
  const prevLevel = Number(_lsGet(_V3_LS.level)) || 0;
  if (prevLevel && level > prevLevel) { setTimeout(() => { toast(`Новый уровень: ${level}`); v3Reward(el('pro-showcase-ava')); v3GrowStar(prevLevel, level); }, 700); }
  _lsSet(_V3_LS.level, String(level));
  const step = _V3_STREAK_STEPS.filter(n => streak >= n).pop() || 0, done = Number(_lsGet(_V3_LS.streak)) || 0;
  if (step > done) setTimeout(() => { toast(`${streak} ${_v3Plural(streak, 'день', 'дня', 'дней')} подряд. Спасибо, что вы с нами`); v3Reward(el('pro-showcase-ava')); }, 1300);
  if (step !== done) _lsSet(_V3_LS.streak, String(step));   // серия сорвалась: праздник снова станет доступен
  if (typeof v3MarksNotice === 'function') setTimeout(() => v3MarksNotice(d.marks), 3200);   // после поздравлений: тост один и заменяет предыдущий
  const joined = d.joined_date ? new Date(d.joined_date) : null, now = new Date();
  if (joined && joined.getMonth() === now.getMonth() && joined.getDate() === now.getDate() && now.getFullYear() > joined.getFullYear() && _lsGet(_V3_LS.anniv) !== today) {
    _lsSet(_V3_LS.anniv, today); setTimeout(() => v3Reward(el('pro-showcase-ava')), 1000);
  }
}
// Время с последнего визита считается один раз за запуск, дальше строка не меняется
(function noteVisit() {
  const last = Number(_lsGet(_V3_LS.visit)) || 0;
  _v3Gap = last ? Math.floor((Date.now() - last) / 864e5) : null;
  _lsSet(_V3_LS.visit, String(Date.now()));
})();

// Пасхалка: семь касаний по аватару за две секунды
let _v3Taps = [];
document.addEventListener('click', e => {
  const ava = e.target.closest('#pro-showcase-ava'); if (!ava) return;
  const now = Date.now(); _v3Taps = _v3Taps.filter(t => now - t < 2000); _v3Taps.push(now);
  const rect = ava.getBoundingClientRect(); _haptic('light');
  if (_v3Taps.length >= 7) { _v3Taps = []; v3Reward(ava); toast('Вы нашли секрет: Эхо шлёт вам привет'); }
  else if (_v3Taps.length >= 3 && typeof v3Reward === 'function') v3Reward({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 });
}, true);

// ── Регалии игроков (внутри проекта «метки») ───────────────────────────────────────
// Регалии приходят с сервера готовыми (/profile/me, /public-profile-v3, строки топа, /marks-v1/me): штатные и особые выдают разработчики вручную,
// заслуженные сервер выдаёт сам и навсегда. Здесь только показ: две самые весомые чипами, остальные маленькими значками в ту же строку (видно все),
// лист со всем списком и одно тихое сообщение о новых. Стили: marks-v3.css. Всё, что пришло, проверяется перед тем, как попасть в разметку.
const _MK_TONES = new Set(['dev', 'staff', 'gold', 'green', 'pink', 'orange', 'violet', 'acc']);
const _MK_FULL = 2, _MK_ICONS = 18, _MK_SEEN = 'pv_marks_seen';
let _mkSheet = null;

function _mkSafe(m) {
  return !!m && typeof m.id === 'string' && /^[a-z0-9_]{2,24}$/.test(m.id) && typeof m.title === 'string' && typeof m.glyph === 'string' && _MK_TONES.has(m.tone);
}
function _mkChip(m) { return `<span class="v3-mark" data-tone="${m.tone}"><i aria-hidden="true">${_profileEsc(m.glyph)}</i><b>${_profileEsc(m.title)}</b></span>`; }
function _mkIcon(m) { return `<span class="v3-mark v3-mark--ico" data-tone="${m.tone}"><i aria-hidden="true">${_profileEsc(m.glyph)}</i></span>`; }

// Ряд регалий под рангом: сначала самые весомые чипами, дальше только значки, поэтому ряд не растёт вширь и помещаются все.
// own: свой профиль, где даже пустой ряд ведёт к списку «что можно получить»
function v3MarksHtml(marks, opts) {
  const list = (Array.isArray(marks) ? marks : []).filter(_mkSafe), own = !!opts?.own;
  if (!list.length && !own) return '';
  const full = list.slice(0, _MK_FULL), icons = list.slice(_MK_FULL, _MK_FULL + _MK_ICONS), more = list.length - full.length - icons.length;
  const label = list.length ? `Регалии: ${list.map(m => m.title).join(', ')}. Открыть список` : 'Регалии. Как их получить';
  const action = own ? 'v3MarksOpenOwn()' : `v3MarksOpenList(${JSON.stringify(list.map(m => m.id))})`;
  window.__mkKnown = { ...(window.__mkKnown || {}), ...Object.fromEntries(list.map(m => [m.id, m])) };
  return `<button type="button" class="v3-marks" onclick="${_profileEsc(action)}" aria-label="${_profileEsc(label)}">${full.map(_mkChip).join('')}${icons.map(_mkIcon).join('')}${more > 0 ? `<span class="v3-mark v3-mark--ico v3-mark--more">+${more}</span>` : ''}${list.length ? '' : '<span class="v3-mark v3-mark--more"><b>Регалии ›</b></span>'}</button>`;
}

// Один значок рядом с ником в списках (самая весомая регалия)
function v3MarkDot(mark) {
  return _mkSafe(mark) ? `<span class="v3-markdot" data-tone="${mark.tone}" role="img" aria-label="${_profileEsc(mark.title)}" title="${_profileEsc(mark.title)}">${_profileEsc(mark.glyph)}</span>` : '';
}

// ── Лист меток ─────────────────────────────────────────────────────────────────────
function _mkKeys(e) {
  if (e.key === 'Escape') { e.preventDefault(); v3MarksClose(); return; }
  if (e.key !== 'Tab') return;
  const items = [...document.querySelectorAll('#mk-sheet button')]; if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}
function v3MarksClose() {
  const host = document.getElementById('mk-sheet'), opener = _mkSheet?.opener; _mkSheet = null;
  document.removeEventListener('keydown', _mkKeys, true);
  const back = () => { if (opener && document.contains(opener)) opener.focus({ preventScroll: true }); };
  if (typeof v3Dismiss === 'function') v3Dismiss(host, back); else { host?.remove(); back(); }   // лист уезжает вниз (app.31.js)
}
// Строка листа: плитка со значком в цвете тона, название и описание полностью (лист для того и открывается: прочитать, за что каждая)
function _mkTile(m) { return `<span class="mk-tile" data-tone="${m.tone}" aria-hidden="true">${_profileEsc(m.glyph)}</span>`; }
function _mkRow(m) {
  const fresh = window.__mkFresh?.has(m.id);
  return `<li class="mk-row${fresh ? ' mk-row--new' : ''}">${_mkTile(m)}<div class="mk-tx"><b>${_profileEsc(m.title)}${fresh ? '<em class="mk-new">новая</em>' : ''}${m.kind === 'live' ? '<em class="mk-live">динамическая</em>' : ''}</b><small>${_profileEsc(m.desc || '')}</small></div></li>`;
}
function _mkAhead(a) {
  const pct = a.need > 1 ? Math.round(100 * a.have / a.need) : 0;
  return `<li class="mk-row mk-row--ahead">${_mkTile(a)}<div class="mk-tx"><b>${_profileEsc(a.title)}</b><small>${_profileEsc(a.how || a.desc || '')}</small>${a.need > 1 ? `<div class="mk-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${a.need}" aria-valuenow="${a.have}"><i style="width:${pct}%"></i></div><span class="mk-num">${fmt(a.have)} из ${fmt(a.need)}</span>` : ''}</div></li>`;
}
function _mkGroup(title, list, row) { return list.length ? `${title ? `<h3 class="mk-sub">${title}</h3>` : ''}<ul class="mk-list">${list.map(row).join('')}</ul>` : ''; }
function _mkBody(worn, ahead, note) {
  const live = worn.filter(m => m.kind === 'live'), earned = worn.filter(m => m.kind === 'earned'), special = worn.filter(m => m.kind !== 'earned' && m.kind !== 'live');
  const groups = [['Особые', special], ['Заслуженные', earned], ['Пока держите темп', live]].filter(g => g[1].length);
  const lists = !worn.length ? '<p>Пока ни одной регалии.</p>' : groups.length > 1 ? groups.map(g => _mkGroup(g[0], g[1], _mkRow)).join('') : _mkGroup('', worn, _mkRow);
  return `${lists}${ahead && ahead.length ? _mkGroup('Впереди', ahead, _mkAhead) : ''}${note ? `<p class="mk-note">${_profileEsc(note)}</p>` : ''}`;
}
// Лист открывается сразу с тем, что уже пришло с профилем; «Впереди» и пояснение подтягиваются следом на то же место
function _mkShow(worn, ahead, note, own) {
  const prev = _mkSheet?.opener; document.getElementById('mk-sheet')?.remove(); document.removeEventListener('keydown', _mkKeys, true);   // прежний лист убираем сразу, без анимации
  _mkSheet = { opener: prev || document.activeElement };
  const host = document.createElement('div'); host.id = 'mk-sheet'; host.className = 'lk-sheet-back';
  host.addEventListener('click', e => { if (e.target === host) v3MarksClose(); });
  host.innerHTML = `<section class="lk-sheet mk-sheet" role="dialog" aria-modal="true" aria-labelledby="mk-title"><header class="mk-head"><div><h2 id="mk-title">Регалии</h2><span class="mk-count">${own ? 'Получено' : 'У игрока'}: ${worn.length}</span></div>
      <button type="button" class="mk-x" onclick="v3MarksClose()" aria-label="Закрыть">✕</button></header><div id="mk-body">${_mkBody(worn, ahead, note)}</div></section>`;
  document.body.appendChild(host); document.addEventListener('keydown', _mkKeys, true);
  host.querySelector('.mk-x')?.focus({ preventScroll: true });
}
function v3MarksOpenList(ids) {   // чужой профиль: показываем то, что уже пришло с карточкой
  _haptic('select');
  _mkShow((ids || []).map(id => window.__mkKnown?.[id]).filter(_mkSafe), null, '', false);
}
function v3MarksOpenOwn() {
  _haptic('select');
  const known = (typeof _profileData !== 'undefined' && Array.isArray(_profileData?.marks) ? _profileData.marks : []).filter(_mkSafe);
  _mkShow(known, null, '', true);
  api('/marks-v1/me').then(d => {
    const body = document.getElementById('mk-body'); if (!body) return;   // лист уже закрыли
    const worn = (d.marks || []).filter(_mkSafe); body.innerHTML = _mkBody(worn, (d.ahead || []).filter(_mkSafe), d.special || '');
    const count = document.querySelector('#mk-sheet .mk-count'); if (count) count.innerHTML = `Получено: ${worn.length}`;   // число, не чужой текст
  }).catch(e => toast(e, false));
}

// Новые регалии: одно тихое сообщение за запуск. Что игрок уже видел, помнит это устройство; на новом устройстве покажется всё имеющееся один раз.
function v3MarksNotice(marks) {
  const list = (Array.isArray(marks) ? marks : []).filter(_mkSafe); if (!list.length) return;
  let seen = []; try { const raw = JSON.parse(_lsGet(_MK_SEEN) || '[]'); if (Array.isArray(raw)) seen = raw; } catch (_) { /* битая запись: считаем, что ничего не видели */ }
  const fresh = list.filter(m => !seen.includes(m.id)); if (!fresh.length) return;
  _lsSet(_MK_SEEN, JSON.stringify([...new Set([...seen, ...list.map(m => m.id)])]));
  window.__mkFresh = new Set(fresh.length < list.length ? fresh.map(m => m.id) : []);   // всё сразу «новое» (новое устройство): плашки в листе только шум
  if (fresh.length === 1) toast(fresh[0].title, true, { title: 'Новая регалия', kind: 'reward', icon: fresh[0].glyph });
  else toast(`${fresh.slice(0, 3).map(m => m.title).join(', ')}${fresh.length > 3 ? ` и ещё ${fresh.length - 3}` : ''}`, true, { title: `Новых регалий: ${fresh.length}`, kind: 'reward', icon: '✦' });
}

// ── Фирменные детали SSS · A (природа и вода) ─────────────────────────────────────────────
// Продолжение _AP_DECOR из app.22.js: разметка слоя фирменной детали (.ap-sig-<id>), SVG, привязанный к рамке аватара. Стили: skin-sig-a-v3.css. Деталь видна с тира SSS (sig_from).
// Рисунок в единицах рамки: 0..100 это сама рамка (центр 50,50; внешнее кольцо ≈ 57), холст -30..130, поэтому он масштабируется вместе с аватаром
// (76 px в профиле, ~100 в карточке и витрине). Под ником остаётся меньше 8 единиц: низ рисунка держится у кольца.
// Градиенты строятся в каждой копии со своими id и красятся палитрой образа (var(--ap-a/b/c)); цвет и движение задаёт CSS, здесь только форма. Ничего не берётся из данных игрока.
(() => {
  const R = n => Math.round(n * 10) / 10;
  const pt = (r, deg, c = 50) => [R(c + r * Math.cos(deg * Math.PI / 180)), R(c + r * Math.sin(deg * Math.PI / 180))];
  const col = k => (k.length === 1 ? `var(--ap-${k})` : k);
  const H = 'x1="0" y1="0" x2="1" y2="0"', RAD = 'cx=".5" cy=".5" r=".5"', DIAG = 'x1="0" y1="0" x2="1" y2="1"';
  const SPARK = 'M0-1L.27-.27L1 0L.27.27L0 1L-.27.27L-1 0L-.27-.27Z';
  const spark = (x, y, s, cls, d) => `<g transform="translate(${x} ${y}) scale(${s})"><path class="${cls}" style="--d:${d}s" d="${SPARK}"/></g>`;
  let seq = 0;
  const art = (name, fn) => () => {
    const defs = [];
    const g = (stops, attrs = 'x1="0" y1="0" x2="0" y2="1"', tag = attrs.startsWith('cx') ? 'radialGradient' : 'linearGradient') => {
      const id = `sa${++seq}`;
      defs.push(`<${tag} id="${id}" ${attrs}>${stops.map(([o, c, a = 1]) => `<stop offset="${o}" style="stop-color:${col(c)};stop-opacity:${a}"/>`).join('')}</${tag}>`);
      return `url(#${id})`;
    };
    const body = fn(g, d => defs.push(d)), svg = (cls, inner) => `<svg class="sa sa-${name}${cls}" viewBox="-30 -30 160 160" aria-hidden="true">${inner}</svg>`;
    return Array.isArray(body) ? svg(' sa-b', `<defs>${defs.join('')}</defs>${body[0]}`) + svg('', body[1]) : svg('', `<defs>${defs.join('')}</defs>${body}`);   // [за кольцом, поверх кольца]
  };
  const arc = (r, a0, a1, big = 0) => `M${pt(r, a0)}A${r} ${r} 0 ${big} 1 ${pt(r, a1)}`;

  // ── Лесной Странник: свод листвы над кольцом, роса на листьях, светлячки ───────────────────────────────
  const LEAF = 'M0 0C.15-.55.7-.62 1 0C.7.55.15.5 0 0Z';
  const canopy = art('canopy', g => {
    const deep = g([[0, 'b', .95], [1, 'b', .7]], H), mid = g([[0, 'b'], [.55, 'a', .92], [1, 'a', .7]], H), lite = g([[0, 'b'], [.4, 'a'], [1, 'c']], H), glow = g([[0, '#f8ffd2', 1], [.3, 'a', .8], [1, 'a', 0]], RAD);
    const leaf = (r, ang, L, tilt, fill, rich) => {
      const [x, y] = pt(r, ang), k = Math.abs(Math.sin((ang - 140) * Math.PI / 260)) ** .6;   // у концов свода листья лежат вдоль кольца: сбоку от аватара места мало
      return `<g transform="translate(${x} ${y}) rotate(${R(ang + (ang < 270 ? 90 - tilt * k : tilt * k - 90))}) scale(${R(L)})"><path d="${LEAF}" fill="${fill}"/>${rich ? '<path class="s-hl" d="M0 0C.15-.55.7-.62 1 0L.1 0Z"/><path class="s-rib" d="M0 0L.9 0"/>' : ''}</g>`;
    };
    const row = (n, off, r, tilt, base, amp, fill, rich) => Array.from({ length: n }, (_, i) => {
      const t = (i + off) / (off ? n : n - 1);
      return leaf(r, 156 + 228 * t, base + amp * Math.sin(Math.PI * t) ** 1.1, tilt, fill, rich);
    }).join('');
    const drop = ([x, y]) => `<g class="sa-dew" transform="translate(${x} ${y})"><ellipse rx="1.5" ry="1.5"/><ellipse class="s-sp" cx="-.5" cy="-.5" rx=".5" ry=".5"/></g>`;
    const fly = (x, y, d, dl) => `<g transform="translate(${x} ${y})"><g class="sa-ff" style="--d:${d}s;--dl:${dl}s"><ellipse rx="8.5" ry="8.5" fill="${glow}"/><ellipse class="s-core" rx="1.5" ry="1.5"/></g></g>`;
    return `<g class="sa-back"><path class="s-twig" d="${arc(57, 156, 384, 1)}"/>${row(11, 0, 59, 62, 10, 24, deep, false)}</g>`
      + `<g class="sa-front">${row(11, .5, 58, 38, 8, 18, mid, true)}${row(9, .5, 57, 14, 6, 11, lite, true)}${[pt(68, 222), pt(72, 292), pt(64, 346), pt(62, 176)].map(drop).join('')}</g>`
      + fly(-8, 26, 6, 0) + fly(108, 8, 7.5, -2.5) + fly(110, 100, 5.5, -4);
  });

  // ── Песчаная Тропа: гряды дюн за кольцом, низкое солнце за гребнем, ленты ветра и марево над кольцом ──────
  const dunes = art('dunes', (g, put) => {
    const far = g([[0, 'a', .95], [.28, 'b', .5], [.5, 'b', 0]]), near = g([[0, 'b', .95], [.2, 'b', .5], [.42, 'b', 0]]), crest = g([[0, 'c', .95], [.7, 'c', .8], [1, 'c', 0]]);
    const sun = g([[0, '#fff'], [.45, 'c'], [1, 'a']], RAD), halo = g([[0, 'a', .6], [1, 'a', 0]], RAD), wind = g([[0, 'c', 0], [.2, 'c', .95], [.75, 'a', .9], [1, 'a', 0]], H);
    const mk = `sam${++seq}`, cp = `sac${++seq}`;
    put(`<mask id="${mk}" maskUnits="userSpaceOnUse" x="-30" y="-30" width="160" height="160"><rect x="-30" y="-30" width="160" height="160" fill="${g([[.05, '#000'], [.28, '#fff'], [.72, '#fff'], [.95, '#000']], H)}"/></mask>`);
    put(`<clipPath id="${cp}"><path clip-rule="evenodd" d="M-30-30H130V130H-30ZM50 3A47 47 0 1 0 50.01 3Z"/></clipPath>`);   // внутри внутреннего кольца рисунка нет: аватар без фото прозрачен
    const rays = Array.from({ length: 7 }, (_, i) => { const a = -172 + i * 27, [x1, y1] = pt(13, a, 0), [x2, y2] = pt(i % 2 ? 18 : 22, a, 0); return `M${x1} ${y1}L${x2} ${y2}`; }).join('');
    const FAR = 'M-30 92C-18 82-6 82 8 88C20 94 30 100 46 102C60 103 74 98 90 90C102 84 118 82 130 90', NEAR = 'M-30 104C-10 98 8 100 26 106C40 110 54 111 66 108C84 104 100 96 114 98C122 99 126 101 130 103';
    const ripple = 'M-14 98C-6 95 4 96 12 100M96 94C104 91 114 91 124 96M32 109C40 111 52 111 62 109';
    const ribbon = (d, cls) => `<path class="s-wind sa-rb ${cls}" fill="${wind}" d="${d}"/>`;
    return [`<g clip-path="url(#${cp})"><ellipse cx="106" cy="86" rx="24" ry="24" fill="${halo}"/><g class="sa-sun" transform="translate(106 86)"><path class="s-rays" d="${rays}"/><circle r="10" fill="${sun}"/></g><g mask="url(#${mk})">`
      + `<path d="${FAR}V132H-30Z" fill="${far}"/><path class="s-crest" stroke="${crest}" d="${FAR}"/><path d="${NEAR}V132H-30Z" fill="${near}"/><path class="s-crest s-crest2" stroke="${crest}" d="${NEAR}"/><path class="s-ripl" d="${ripple}"/></g></g>`,
      ribbon('M-26 44C-12 14 26-14 62-12C92-10 112 6 122 28C112 10 92-6 62-9C28-11-8 16-26 44Z', 'sa-rb1') + ribbon('M-10 22C6 2 34-8 56-6C40-6 14 6-10 22Z', 'sa-rb2')
      + `<g class="sa-heat"><path class="s-heat" d="M102 70q2.5-2 5 0t5 0t5 0"/><path class="s-heat" d="M104 63q2.5-2 5 0t5 0"/></g>`
      + [[10, 14, 1.1, 3.4], [44, -14, .8, 4.6], [90, -6, 1, 3.9], [112, 40, .9, 5.2]].map(([x, y, r, d]) => `<circle class="s-grain" style="--d:${d}s" cx="${x}" cy="${y}" r="${r}"/>`).join('')];
  });

  // ── Тихая Гавань: маяк с вращающимся лучом, причальный канат вокруг рамки, круги на воде ────────────────
  const lighthouse = art('lighthouse', g => {
    const wall = g([[0, 'c'], [.55, 'a'], [1, 'b']], H), beam = g([[0, 'c', .8], [1, 'c', 0]], 'x1="1" y1="0" x2="0" y2="0"'), lamp = g([[0, '#fff', .95], [.35, 'c', .6], [1, 'c', 0]], RAD);
    const rope = pt(60.5, 128);
    return `<g transform="translate(106 1)"><g class="sa-beam"><path class="s-beam" fill="${beam}" d="M0 0L-132-30V30Z"/><path class="s-beam" fill="${beam}" d="M0 0L-132-9V9Z"/></g><circle class="sa-lamp" r="9" fill="${lamp}"/></g>`
      + `<circle class="s-rope" cx="50" cy="50" r="60.5"/><circle class="s-twist" cx="50" cy="50" r="60.5"/><circle class="s-rl" cx="50" cy="50" r="59.6"/><circle class="s-rd" cx="50" cy="50" r="61.5"/>`
      + `<g transform="translate(${rope})"><g class="sa-sway"><path class="s-rope s-tail" d="M-.5 1C-3 7-1.5 12-3.5 17"/><path class="s-rope s-tail" d="M1.5 1C4 6 3 10 5 13"/></g><path class="s-loop" d="M0 0C-6-6-9 2-4 3.2C-1.5 3.8 0 1.5 0 0ZM0 0C6-6 9 2 4 3.2C1.5 3.8 0 1.5 0 0Z"/><circle class="s-knot" r="2.1"/></g>`
      + `<g transform="translate(106 30)"><path class="s-rock" d="M-10 5Q-6-3-3-2Q3-5 9 5Z"/><path d="M-5 0L-3.2-24H3.2L5 0Z" fill="${wall}"/><path class="s-band" d="M-4.4-7L-4-11H4L4.4-7ZM-3.8-16L-3.5-20H3.5L3.8-16Z"/>`
      + `<rect class="s-rail" x="-4.8" y="-26.2" width="9.6" height="2" rx=".6"/><rect class="s-room" x="-2.8" y="-32.2" width="5.6" height="6" rx="1"/><path class="s-roof" d="M-4-32.2L0-37.4L4-32.2Z"/></g>`
      + `<ellipse class="s-ripple" cx="50" cy="110.5" rx="30" ry="2.6"/><ellipse class="sa-rip s-ripple" cx="50" cy="110.5" rx="30" ry="2.6"/><ellipse class="sa-rip sa-rip2 s-ripple" cx="50" cy="110.5" rx="30" ry="2.6"/>`;
  });

  // ── Пруд Лотосов: кувшинки с росой на воде у кольца, один бутон на стебле ──────────────────────────────
  const lilypads = art('lilypads', g => {
    const padG = g([[0, 'a'], [.65, 'b'], [1, 'b', .92]], 'cx=".38" cy=".34" r=".75"', 'radialGradient');
    const bud = g([[0, '#fff', .92], [.4, 'c'], [1, 'c', .8]]), side = g([[0, 'c', .55], [1, 'c']]);
    const veins = Array.from({ length: 9 }, (_, i) => { const a = (-30 + i * 40) * Math.PI / 180; return `M0 0L${R(.92 * Math.cos(a) * 100) / 100} ${R(.92 * Math.sin(a) * 100) / 100}`; }).join('');
    const pad = (x, y, rx, rot, cls) => `<g transform="translate(${x} ${y})"><g class="sa-pad ${cls}"><g transform="scale(1 .4) rotate(${rot}) scale(${rx})"><path class="s-pad" fill="${padG}" d="M0 0L.707-.707A1 1 0 1 1 .259-.966Z"/><path class="s-vein" d="${veins}"/></g></g></g>`;
    const drop = (x, y) => `<g class="sa-dew" transform="translate(${x} ${y})"><ellipse rx="1.5" ry="1.5"/><ellipse class="s-sp" cx="-.5" cy="-.5" rx=".5" ry=".5"/></g>`;
    return `<ellipse class="sa-rip s-ripple" cx="-3" cy="93" rx="17" ry="6.8"/><ellipse class="sa-rip sa-rip2 s-ripple" cx="95" cy="97" rx="16" ry="6.4"/>`
      + pad(-3, 93, 17, 20, 'sa-pa') + pad(95, 97, 16, 200, 'sa-pb') + pad(-11, 38, 8, 100, 'sa-pc') + pad(109, 108, 6, 250, 'sa-pc') + drop(-1, 92) + drop(-9, 94) + drop(98, 97) + drop(-12, 38)
      + `<path class="s-stem" d="M95 95C99 88 108 84 106 70"/><g transform="translate(106 70) scale(1.12)"><g class="sa-bud"><path class="s-sepal" d="M0 1C-5 0-7-5-6-8C-3-5-1-3 0 1ZM0 1C5 0 7-5 6-8C3-5 1-3 0 1Z"/>`
      + `<path d="M0 0C-8-2-9-13-3.5-18C-3-10-1.5-4 0 0ZM0 0C8-2 9-13 3.5-18C3-10 1.5-4 0 0Z" fill="${side}"/><path d="M0 0C-4.5-5-4.5-15 0-22C4.5-15 4.5-5 0 0Z" fill="${bud}"/><path class="s-gloss" d="M-1.6-4C-2.3-9-1.5-14 0-18"/></g></g>`;
  });

  // ── Изморозь: ледяные друзы и звёздочки инея растут по рамке, большая снежинка, блики ───────────────────
  const rime = art('rime', g => {
    const shard = g([[0, '#fff', .95], [1, 'a', .65]]), edge = g([[0, 'c', .8], [.65, 'c', .35], [1, 'c', 0]]);
    const spike = (L, w) => `<path fill="${shard}" d="M${-w} 0L${R(-w * .75)} ${R(-L * .72)}L0 ${-L}L${R(w * .75)} ${R(-L * .72)}L${w} 0Z"/><path class="s-facet" d="M0 0V${-L}"/>`;
    const druse = (ang, L) => { const [x, y] = pt(57.5, ang); return `<g transform="translate(${x} ${y}) rotate(${ang + 90})"><g transform="rotate(-24)">${spike(L * .62, 1.5)}</g><g transform="rotate(22)">${spike(L * .7, 1.6)}</g>${spike(L, 2.2)}</g>`; };
    const arm = len => `<path d="M0 0V-${len}M0-${R(len * .45)}L-3.2-${R(len * .45 + 3)}M0-${R(len * .45)}L3.2-${R(len * .45 + 3)}M0-${R(len * .72)}L-2.2-${R(len * .72 + 2.2)}M0-${R(len * .72)}L2.2-${R(len * .72 + 2.2)}"/>`;
    const star = (len, k = 1) => [0, 60, 120, 180, 240, 300].map(a => `<g transform="rotate(${a}) scale(${k})">${arm(len)}</g>`).join('');
    const mini = (ang, r) => { const [x, y] = pt(r, ang), arms = star(5, .8); return `<g transform="translate(${x} ${y}) rotate(${ang})"><g class="s-gl">${arms}</g><g class="s-ice">${arms}</g></g>`; };
    const ring = Array.from({ length: 12 }, (_, i) => pt(60, i * 30)).map(p => p.join(' ')).join('L');
    return `<path class="s-poly" stroke="${edge}" d="M${ring}Z"/>` + [[168, 10], [192, 13], [214, 11], [238, 17], [262, 12], [284, 10], [346, 12], [6, 14], [24, 10]].map(([a, L]) => druse(a, L)).join('')
      + [[180, 67], [226, 69], [250, 70], [272, 68], [356, 66], [15, 68]].map(([a, r]) => mini(a, r)).join('')
      + `<g transform="translate(103 -5)"><g class="sa-flake"><g class="s-gl">${star(12)}</g><g class="s-ice">${star(12)}</g><circle class="s-core" r="1.7"/></g></g>`
      + spark(-8, 16, 4, 's-glint', 3.4) + spark(114, 40, 3, 's-glint sg2', 4.6) + spark(30, -19, 3.6, 's-glint sg3', 3.9) + spark(76, -22, 2.4, 's-glint sg4', 5.2);
  });

  // ── Снежный Шар: стеклянный купол с бликом, городок на снегу, снег кружит у стекла ──────────────────────
  const snowdome = art('snowdome', g => {
    const glass = g([[0, '#fff', .16], [.62, '#fff', .02], [1, 'a', .14]], 'cx=".4" cy=".34" r=".7"', 'radialGradient'), rim = g([[0, '#fff', .98], [.5, 'a', .55], [1, 'b', .75]], DIAG);
    const snow = g([[0, '#fff', .96], [.55, 'a', .6], [1, 'a', .1]]);
    const Y = 103, half = Math.sqrt(62 * 62 - (Y - 50) ** 2);
    const house = (x, w, h, lit) => `<path class="s-town" d="M${x} ${Y}V${R(Y - h)}L${R(x + w / 2)} ${R(Y - h - w * .62)}L${R(x + w)} ${R(Y - h)}V${Y}Z"/><path class="s-cap" d="M${R(x - .6)} ${R(Y - h + .5)}L${R(x + w / 2)} ${R(Y - h - w * .62 - .5)}L${R(x + w + .6)} ${R(Y - h + .5)}Q${R(x + w / 2)} ${R(Y - h - .8)} ${R(x - .6)} ${R(Y - h + .5)}Z"/>${lit ? `<rect class="s-win" x="${R(x + w / 2 - .9)}" y="${R(Y - h * .72)}" width="1.8" height="2.1"/>` : ''}`;
    const flake = ([a, r, s]) => { const [x, y] = pt(r, a); return `<ellipse cx="${x}" cy="${y}" rx="${s}" ry="${s}"/>`; };
    return `<circle cx="50" cy="50" r="62" fill="${glass}"/><circle class="s-rim" cx="50" cy="50" r="62" stroke="${rim}"/>`
      + `<path fill="${snow}" d="M${R(50 - half)} ${Y}H${R(50 + half)}A62 62 0 0 1 ${R(50 - half)} ${Y}Z"/>`
      + `<g class="sa-town">${house(16, 7, 6.2, 1)}${house(23.6, 7.4, 8.6, 1)}${house(31.6, 5.6, 4.8, 0)}${house(64, 6.4, 5.4, 0)}${house(70.8, 6, 9, 1)}<path class="s-town" d="M78.4 ${Y}V${Y - 11}L80.4 ${Y - 18.6}L82.4 ${Y - 11}V${Y}Z"/><path class="s-cap" d="M77.9 ${Y - 10.4}L80.4 ${Y - 19.4}L82.9 ${Y - 10.4}Q80.4 ${Y - 11.8} 77.9 ${Y - 10.4}Z"/><rect class="s-win" x="79.6" y="${Y - 7}" width="1.6" height="2"/></g>`
      + `<path class="s-glare" d="M${pt(59.5, 194)}A59.5 59.5 0 0 1 ${pt(59.5, 266)}A47 47 0 0 0 ${pt(59.5, 194)}Z"/><path class="s-glare s-glare2" d="${arc(59.5, 280, 298)}"/><path class="s-glare s-glare3" d="${arc(59.5, 18, 48)}"/>`
      + `<path class="s-collar" d="${arc(62, 66, 114)}"/>`
      + `<g class="sa-fl1 s-flake">${[[200, 59.5, 1.4], [262, 60, 1.1], [318, 59, 1.5], [24, 60, 1], [150, 59.5, 1.1]].map(flake).join('')}</g><g class="sa-fl2 s-flake">${[[232, 59.5, 1.1], [350, 60, 1.3], [100, 60.5, 1]].map(flake).join('')}</g>`;
  });

  // ── Нефритовый Двор: резной нефритовый би с решётчатыми окнами, золотые кромки, лаковый блик и золотая пыль ──
  const jadecourt = art('jadecourt', g => {
    const body = g([[0, 'a'], [.5, 'b'], [1, 'b', .5]], DIAG);
    const circle = r => `M${50 + r} 50A${r} ${r} 0 1 0 ${50 - r} 50A${r} ${r} 0 1 0 ${50 + r} 50Z`, RO = 66, RI = 57.5, RM = (RO + RI) / 2;
    const holes = Array.from({ length: 16 }, (_, i) => { const a = i * 22.5 + 11.25; return `M${pt(RI + 1.4, a)}L${pt(RM, a + 3)}L${pt(RO - 1.4, a)}L${pt(RM, a - 3)}Z`; }).join('');
    const studs = Array.from({ length: 16 }, (_, i) => { const [x, y] = pt(RM, i * 22.5); return `<ellipse cx="${x}" cy="${y}" rx=".85" ry=".85"/>`; }).join('');
    return `<path fill="${body}" fill-rule="evenodd" d="${circle(RO)}${circle(RI)}${holes}"/><circle class="s-edge" cx="50" cy="50" r="${RO}"/><circle class="s-edge" cx="50" cy="50" r="${RI}"/><g class="s-stud">${studs}</g>`
      + `<path class="s-lacq" d="${arc(RM, 192, 246)}"/><path class="s-lacq s-lacq2" d="${arc(RM, 256, 268)}"/><g class="sa-glint"><path class="s-lacq s-sweep" d="${arc(RM, -12, 20)}"/></g>`
      + spark(-12, 14, 2.8, 's-gold', 3.2) + spark(114, 22, 2.2, 's-gold sg2', 4.1) + spark(110, 90, 2.6, 's-gold sg3', 3.6) + spark(-10, 84, 1.8, 's-gold sg4', 4.8) + spark(66, -18, 2, 's-gold sg5', 3.9)
      + [[-6, 4], [116, 62], [22, -14], [112, 2], [-14, 56], [92, -10], [8, 100], [96, 112]].map(([x, y]) => `<circle class="s-dust" cx="${x}" cy="${y}" r=".7"/>`).join('');
  });

  Object.assign(_AP_DECOR, { canopy: canopy, dunes: dunes, lighthouse: lighthouse, lilypads: lilypads, rime: rime, snowdome: snowdome, jadecourt: jadecourt });
})();

// ── Фирменные детали SSS · B (огонь, металл, ночь) ─────────────────────────────────────────────
// Продолжение _AP_DECOR и _ORN из app.22.js: разметка слоя фирменной детали (.ap-sig-<id>) и SVG-части образа (_ORN[<skin id>]); деталь видна с тира SSS (sig_from).
// Рамка рисуется в поле «-20 -20 140 140»: 1 единица это 1% рамки, центр кольца (50,50), край рамки r=50, поэтому деталь растёт и сжимается вместе с аватаром.
// Градиенты лежат один раз в своём скрытом SVG (#orn-defs-b). Всё внутри функции: имена не попадают в общую область и не спорят с другими файлами. Стили: skin-sig-b-v3.css.
(() => {
  const f = v => +v.toFixed(1), rad = d => d * Math.PI / 180;
  const pt = (r, d, c = 50) => [f(c + r * Math.cos(rad(d))), f(c + r * Math.sin(rad(d)))];
  const poly = a => `M${a.map(p => p.join(' ')).join('L')}z`;
  const hole = (x, y, r) => `M${x + r} ${y}a${r} ${r} 0 1 0 ${-2 * r} 0a${r} ${r} 0 1 0 ${2 * r} 0z`;
  const gear = (n, tip, root) => poly(Array.from({ length: n * 4 }, (_, i) => pt([root, tip, tip, root][i % 4], (Math.floor(i / 4) + [-.3, -.17, .17, .3][i % 4]) * 360 / n, 0)));
  const svg = (cls, vb, body) => `<svg class="${cls}" viewBox="${vb}" aria-hidden="true">${body}</svg>`;
  const W = '-20 -20 140 140';
  const st = a => a.map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join('');
  const RA = k => pt(64, 30 * k + 15), RB = k => pt(57.4, 30 * k);   // грани рубина: 12 углов внешнего (A) и внутреннего (B) контура, 24 треугольника между ними
  const LIN = 'x1="0" y1="0" x2="1" y2="1"', UP = 'x1="0" y1="1" x2="0" y2="0"';   // по диагонали и снизу вверх
  const DEFS = '<svg id="orn-defs-b" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
    + `<linearGradient id="ornInfernoLava" ${LIN}>${st([[0, '#ffe08a'], [.4, '#ff9a3c'], [.78, '#e3432b'], [1, '#8a1d10']])}</linearGradient>`
    + `<linearGradient id="ornInfernoCrust" ${LIN}>${st([[0, '#53200f'], [1, '#1b0805']])}</linearGradient>`
    + `<linearGradient id="ornInfernoVein" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="200">${st([[0, 'rgba(227,67,43,0)'], [.22, '#e3432b'], [.55, '#ffb35a'], [.85, '#e3432b'], [1, 'rgba(227,67,43,0)']])}</linearGradient>`
    + `<linearGradient id="ornCopperBody" ${LIN}>${st([[0, '#f6c299'], [.38, '#cd7d47'], [.75, '#8f4a27'], [1, '#5d2c17']])}</linearGradient>`
    + `<radialGradient id="ornPumpBody" cx=".5" cy=".56" r=".62">${st([[0, '#f08a1f'], [.55, '#b4500a'], [1, '#5a2105']])}</radialGradient>`
    + `<radialGradient id="ornPumpGlow" cx=".5" cy=".5" r=".6">${st([[0, '#fffbe0'], [.55, '#ffd36b'], [1, '#ffa63c']])}</radialGradient>`
    + `<radialGradient id="ornPumpHalo" cx=".5" cy=".5" r=".5">${st([[0, 'rgba(255,170,60,.6)'], [1, 'rgba(255,150,40,0)']])}</radialGradient>`
    + `<linearGradient id="ornPumpLeaf" ${LIN}>${st([[0, '#a3cc62'], [1, '#4b7a29']])}</linearGradient>`
    + `<linearGradient id="ornWitchMoon" ${LIN}>${st([[0, '#fff3c0'], [.5, '#ffd36b'], [1, '#d9992b']])}</linearGradient>`
    + `<linearGradient id="ornWitchFire" ${UP}>${st([[0, 'rgba(31,154,74,.2)'], [.5, '#3fe070'], [1, '#c8ffb0']])}</linearGradient>`
    + `<linearGradient id="ornRubySheen" x1="0" y1="0" x2="1" y2="0">${st([[0, 'rgba(255,255,255,0)'], [.5, 'rgba(255,246,242,.9)'], [1, 'rgba(255,255,255,0)']])}</linearGradient>`
    + `<linearGradient id="ornGateRise" ${UP}>${st([[0, 'rgba(190,160,255,.9)'], [1, 'rgba(190,160,255,0)']])}</linearGradient>`
    + `<clipPath id="ornRubyClip"><path clip-rule="evenodd" d="${poly(Array.from({ length: 12 }, (_, k) => RA(k)))}${hole(50, 50, 55)}"/></clipPath></defs></svg>`;
  const defs = () => { if (!document.getElementById('orn-defs-b')) document.body.insertAdjacentHTML('beforeend', DEFS); };
  const sig7 = draw => ti => (ti >= 7 ? (defs(), draw()) : '');   // часть сцены только с тира SSS
  const smooth = p => `M${p[0].join(' ')}${p.slice(1, -1).map((q, i) => `Q${q.join(' ')} ${f((q[0] + p[i + 2][0]) / 2)} ${f((q[1] + p[i + 2][1]) / 2)}`).join('')}L${p[p.length - 1].join(' ')}`;
  const star4 = (cls, a, s, extra = '') => `<path class="${cls}" ${extra} transform="translate(${a.join(' ')}) scale(${s})" d="M0-1L.22-.22 1 0 .22.22 0 1-.22.22-1 0-.22-.22z"/>`;

  // ── Инферно · blaze: обод из плит остывшей лавы, магма светится в швах и трещинах, угли; жилы-трещины по краям сцены с дрожащим жаром ──
  const jit = (k, i) => Math.sin(k * 7.3 + i * 3.1) * 1.3;
  const plates = Array.from({ length: 9 }, (_, k) => {
    const a = k * 40 - 98, at = i => a + 1.8 + i * 9.1;
    const out = [0, 1, 2, 3, 4].map(i => pt(61.8 + jit(k, i) * .85, at(i))), inn = [4, 3, 2, 1, 0].map(i => pt(56.8 + jit(k, i + 5) * .85, at(i)));
    return `<path d="${poly([...out, ...inn])}"/>${k % 2 ? '' : `<path class="sg-cr" d="M${pt(57.8, a + 12)}L${pt(59.8, a + 17)}L${pt(58.2, a + 22)}L${pt(61.2, a + 27)}"/>`}`;
  }).join('');
  const embers = [[-72, 1.5, 3.6, 0], [-8, 1.1, 4.4, -1.4], [205, 1.3, 4, -2.2], [250, 1, 3.2, -.8]].map(([a, r, d, dl], i) => `<circle class="sg-em" cx="${pt(59.5, a)[0]}" cy="${pt(59.5, a)[1]}" r="${r}" style="--d:${d}s;--dl:${dl}s;--dx:${i % 2 ? 7 : -7}px"/>`).join('');
  const vein = ph => {   // трещина вдоль края сцены: плавная жила с отростками внутрь и тающими концами; жар поднимается от неё
    const p = Array.from({ length: 11 }, (_, i) => [f(8 + Math.sin(i * 1.1 + ph) * 4.5 + Math.cos(i * .53 + ph * 2) * 2), i * 20]);
    const br = [3, 6, 8].map((i, k) => `M${p[i].join(' ')}q${5 + k * 2} 4 ${7 + k * 2} ${10 + k * 3}`).join('');
    return `<path class="o-vg" d="${smooth(p)}${br}"/><path class="o-vn" d="${smooth(p)}"/><path class="o-vb" d="${br}"/><path class="o-hz" style="--dl:${-ph}s" d="M17 188c-3-4 3-8 0-12s3-8 0-12"/>`;
  };

  // ── Медные Сумерки · cogs: медная шестерня-ободок (40 зубьев) и малая шестерня (10) в зацеплении, патина, искры кузни ──
  const ringGear = `<g transform="translate(50 50)"><path class="sg-gear" fill-rule="evenodd" d="${gear(40, 63.2, 58.6)}${hole(0, 0, 55.2)}"/>`
    + '<circle class="sg-pt" r="57" stroke-dasharray="7 37 3 49 12 66 5 80"/><circle class="sg-pt sg-pt--t" r="61.2" stroke-dasharray="4 66 9 58 3 90"/>'
    + Array.from({ length: 20 }, (_, i) => `<circle class="sg-rv" cx="${pt(56.9, i * 18, 0)[0]}" cy="${pt(56.9, i * 18, 0)[1]}" r=".85"/>`).join('')
    + `<path class="sg-hl" d="M${pt(56.9, 205, 0)}A56.9 56.9 0 0 1 ${pt(56.9, 292, 0)}"/></g>`;
  const smallGear = `<g transform="rotate(-9)"><path class="sg-gear" fill-rule="evenodd" d="${gear(10, 17.45, 12.85)}${hole(0, 0, 3)}${[36, 108, 180, 252, 324].map(a => hole(...pt(8.4, a, 0), 1.7)).join('')}"/><circle class="sg-pt" r="15.2" stroke-dasharray="7 24 3 36"/><circle class="sg-rv" r="1.3"/></g>`;
  const sparks = [[10, -12, 0], [17, -4, -.7], [5, -17, -1.4], [13, -9, -2.1]].map(([dx, dy, dl]) => `<path class="sg-spk" style="--dx:${dx}px;--dy:${dy}px;--dl:${dl}s" d="M0-2.4L.7-.7 2.4 0 .7.7 0 2.4-.7.7-2.4 0-.7-.7z"/>`).join('');

  // ── Тыквенный Фонарь · jacklight: подвесной фонарь с резным лицом (сцена), тыквенная лоза с листьями и огоньками на кольце (рамка) ──
  const lantern = '<g class="o-sw"><path class="o-ch" d="M30 0V17"/><circle class="o-gw" cx="30" cy="47" r="30"/>'
    + '<path class="o-st" d="M28.4 27c-.2-5 1.2-8.6 4.8-10.4l1.5 2.8c-2 1.3-2.9 3.5-2.9 7.6z"/>'
    + '<ellipse cx="17.5" cy="47" rx="12.5" ry="17.5"/><ellipse cx="42.5" cy="47" rx="12.5" ry="17.5"/><ellipse cx="30" cy="46" rx="15" ry="19.5"/>'
    + '<path class="o-rb" d="M23.5 28.5Q19.8 46 23.5 63.5M36.5 28.5Q40.2 46 36.5 63.5"/>'
    + '<g class="o-fc"><path d="M18.4 45.6l9.4-1-4.2-9.6zM41.6 45.6l-9.4-1 4.2-9.6zM30 48l-2.8 4.4h5.6z"/><path d="M17 53.4L21.6 55.4 24.4 52.4 28 56.4 31 53.2 34.2 56.6 37 52.4 40 55.4 43 53.4Q30 72 17 53.4z"/></g></g>';
  const vinePts = Array.from({ length: 21 }, (_, i) => pt(58.5 + 2.4 * Math.sin(i * 1.45), 192 + i * 7));
  const leaf = (a, s) => `<g transform="translate(${pt(58.6, a).join(' ')}) rotate(${a + s}) scale(${s > 0 ? 1 : .85})"><path class="o-lf" d="M0 0Q5.5-6.5 13 0Q5.5 6.5 0 0z"/><path class="o-lv" d="M1 0H11"/></g>`;
  const curl = (a, dir) => { const p = pt(58.5, a); return `<path class="o-vn" d="${smooth(Array.from({ length: 16 }, (_, i) => { const t = i * .55, r = 4.4 - i * .24; return [f(p[0] + dir * Math.cos(t + 1.6) * r), f(p[1] + Math.sin(t + 1.6) * r - 4.4)]; }))}"/>`; };
  const mini = (a, d) => `<g transform="translate(${pt(61, a).join(' ')}) rotate(${a + 90})"><g class="o-mp" style="--d:${d}s"><ellipse cx="-2.6" cy="0" rx="2.8" ry="3.4"/><ellipse cx="2.6" cy="0" rx="2.8" ry="3.4"/><ellipse cx="0" cy="0" rx="3" ry="3.8"/><path class="o-ms" d="M0-3.5q.4-2 2-2.6"/></g></g>`;

  // ── Паутина Полуночи · cobwebs: паутина в углах сцены и на кольце, росинки-звёзды, паучок на нити ──
  const web = (hx, hy, dir, span, nr, ds) => {
    const at = (d, a) => `${f(hx + d * Math.cos(rad(a)))} ${f(hy + d * Math.sin(rad(a)))}`, ang = Array.from({ length: nr }, (_, i) => dir - span / 2 + span * i / (nr - 1));
    const rays = ang.map(a => `M${hx} ${hy}L${at(ds[ds.length - 1], a)}`).join('');
    const arcs = ds.map(d => ang.slice(1).map((a, i) => `M${at(d, ang[i])}Q${at(d * .8, (ang[i] + a) / 2)} ${at(d, a)}`).join('')).join('');
    return { d: rays + arcs, dew: (j, i, s) => star4('o-dw', at(ds[j], ang[i]).split(' '), s, `style="--dl:${-(j + i) * .7}s"`) };
  };
  const cornerWeb = web(0, 0, 45, 90, 6, [16, 29, 43, 58, 74, 92]), ringWeb = web(...pt(51, -138), -138, 76, 5, [9, 17, 26, 36]);
  const legs = 'M10.4 47Q5 43 2.5 46M10 49Q4.5 47 1.8 51M10 51Q4.5 51.5 2.2 56M10.6 53Q6.5 56 5 61';
  const spider = `<line class="o-th" x1="12" y1="0" x2="12" y2="44"/><g class="o-sp"><path class="o-lg" d="${legs}"/><path class="o-lg" transform="matrix(-1 0 0 1 24 0)" d="${legs}"/><ellipse cx="12" cy="53.4" rx="3.5" ry="4.5"/><circle cx="12" cy="47.2" r="2.3"/><path class="o-mk" d="M12 51.2v4.2"/></g>`;

  // ── Час Ведьм · witchmoon: месяц и ведьма на метле (сцена), зелёный огонь под кольцом и пузырьки зелья (рамка) ──
  const witch = '<path class="o-wb" d="M6 21L41 12.5"/><path class="o-ws" d="M8 20.2L.5 16.5 -1 21 1 26.5 8 22z"/><path d="M20 18.5C14 18.5 10.5 21 7.5 25.5 13 23.4 18.5 23.2 24.5 19.6zM21 18.5C20.6 12.4 23 8.4 27.2 8.2L30.4 9.6C31.4 13 30.6 16 28.4 18.5z"/><circle cx="29.3" cy="7" r="2.6"/><path d="M24.3 5.4C25.8 1.2 24.8-1.6 21.4-4.2 27-3.6 31.6.3 33.6 5.4z"/><ellipse cx="29" cy="5.6" rx="6.9" ry="1.5"/><path class="o-wb" d="M28.4 11.6L35.4 14.4M24 18l2.4 6.4M26.8 8.4q-4 .8-6.2 4.6"/>';
  const FL = 'M-4 0C-6.4-5-3.4-8.6-1.6-12.4C-1-10.4 0-9.8.8-11C1.2-13.8.6-16.6 2-19 3.6-13 6.6-7 4 0z';
  const tongues = [[18, 14], [34, 19], [50, 21], [66, 15], [114, 15], [130, 21], [146, 19], [162, 14]].map(([a, h], i) => `<g transform="translate(${pt(54.2, a).join(' ')}) rotate(${a + 90}) scale(${i % 2 ? -.8 : .8} ${h / 19})"><g class="sg-fl" style="--d:${(1.5 + i % 3 * .4).toFixed(1)}s;--dl:${-i * .45}s"><path d="${FL}"/><path class="sg-fc" transform="scale(.55 .78)" d="${FL}"/></g></g>`).join('');
  const bubbles = [[132, 14, 4.6, 0], [48, 12, 5.4, -1.8], [150, 6, 6, -3.2], [30, 8, 4.2, -.9]].map(([a, dy, d, dl], i) => `<g transform="translate(${pt(66, a).join(' ')})"><g class="sg-bb" style="--d:${d}s;--dl:${dl}s;--dy:-${dy * 1.8}px;--dx:${i % 2 ? 6 : -6}px"><path d="M-1.2-.6a1.6 1.6 0 0 1 1-1"/><circle r="${2.5 + (i % 3) * .5}"/></g></g>`).join('');

  // ── Рубиновый Собор · facets: огранённая оправа из 24 граней, блики и полоса света по граням, стрельчатая арка с жемчужной нитью ──
  const facets = Array.from({ length: 24 }, (_, i) => {
    const k = i >> 1, tri = i % 2 ? [RA(k - 1), RA(k), RB(k)] : [RB(k), RA(k), RB(k + 1)], c = tri.reduce((s, p) => [s[0] + p[0] / 3, s[1] + p[1] / 3], [0, 0]);
    const s = Math.min(1, Math.max(0, .5 + .5 * Math.cos(Math.atan2(c[1] - 50, c[0] - 50) + rad(135)) + (i % 2 ? .12 : -.1) + Math.sin(i * 2.3) * .12));
    return `<path d="${poly(tri)}" style="fill:${s < .6 ? `color-mix(in srgb, var(--ap-a) ${f(s / .6 * 55)}%, var(--ap-b))` : `color-mix(in srgb, var(--ap-c) ${f((s - .6) / .4 * 70)}%, var(--ap-a))`}"/>`;
  }).join('');
  const glints = [[RA(7), 4.6, 0], [RA(2), 3.4, -1.1], [RA(5), 3, -2.2], [RB(3), 2.4, -.6]].map(([p, s, dl]) => star4('sg-gl', p, s, `style="--dl:${dl}s"`)).join('');
  const arch = R => `M${70 - R} 50A${R} ${R} 0 0 1 50 ${f(50 - Math.sqrt(R * R - 400))}A${R} ${R} 0 0 1 ${30 + R} 50`;   // две дуги радиуса R сходятся в вершине над кольцом (центры на линии пят, x=70 и x=30)
  const pearls = [192, 206, 220, 234, 247].map(a => { const p = [f(70 + 86.5 * Math.cos(rad(a))), f(50 + 86.5 * Math.sin(rad(a)))]; return `<circle cx="${p[0]}" cy="${p[1]}" r="1.3"/><circle cx="${f(100 - p[0])}" cy="${p[1]}" r="1.3"/>`; }).join('');

  // ── Порог · gateway: дверной проём из света вокруг кольца, порог и тени-шёпоты, что дрейфуют вверх вдоль косяков ──
  const wisp = (x, h, d, dl, mir) => `<g transform="translate(${x} 101) scale(${mir} 1)"><path class="sg-ws" style="--d:${d}s;--dl:${dl}s" d="M0 0C-7-${h * .22} 7-${h * .44} 0-${h * .66}S-5-${h * .9} 1-${h}a2.4 2.4 0 1 1 -3.6-1.4"/></g>`;
  Object.assign(_AP_DECOR, {
    blaze: () => (defs(), svg('sg-b', W, `<path class="sg-lava" d="${hole(50, 50, 59.3)}"/><g class="sg-crust">${plates}</g>${embers}`)),
    cogs: () => (defs(), svg('sg-b sg-gr', W, ringGear) + svg('sg-b sg-cg', '-20 -20 40 40', smallGear) + svg('sg-b sg-sp', W, `<g transform="translate(${pt(61, -63).join(' ')})">${sparks}</g>`)),
    jacklight: () => (defs(), svg('sg-b sg-vn', W, `<path class="o-vn" d="${smooth(vinePts)}"/>${curl(192, 1)}${curl(332, -1)}${[212, 252, 296].map((a, i) => leaf(a, i % 2 ? 30 : -34)).join('')}${mini(232, 3.1)}${mini(314, 2.6)}`)),
    cobwebs: () => (defs(), svg('sg-b sg-wb', W, `<path class="o-wl" d="${ringWeb.d}"/>${ringWeb.dew(1, 1, 1.2)}${ringWeb.dew(2, 3, 1)}${ringWeb.dew(3, 2, 1.3)}`)),
    witchmoon: () => (defs(), svg('sg-b sg-fr', W, tongues) + svg('sg-b sg-bu', W, bubbles)),
    facets: () => (defs(), svg('sg-b sg-gem', W, `<g class="sg-fct">${facets}</g><g clip-path="url(#ornRubyClip)"><g transform="rotate(24 50 50)"><rect class="sg-sw" x="-18" y="-30" width="15" height="170"/></g></g>${glints}`)
      + svg('sg-b sg-ar', '-30 -50 160 100', `<path class="sg-a1" d="${arch(90)}"/><path class="sg-a2" d="${arch(83)}"/><g class="sg-pe">${pearls}</g><path class="sg-ap" d="M50 -39.4l3.6 4.2L50 -28.6l-3.6-6.6z"/>`)),
    gateway: () => (defs(), svg('sg-b sg-lt', W, '<path class="sg-d0" d="M-8 103V50A58 58 0 0 1 108 50V103z"/>') + svg('sg-b sg-dr', W, `<path class="sg-d1" d="M-8 103V50A58 58 0 0 1 108 50V103"/><path class="sg-d2" d="M-1.5 96V50A51.5 51.5 0 0 1 101.5 50V96"/><rect class="sg-sl" x="-14" y="102.4" width="128" height="1.8"/>${star4('sg-ks', [50, -8], 4.2)}${wisp(-3, 48, 7, 0, 1)}${wisp(103, 42, 8.4, -3, -1)}${wisp(3, 34, 6.4, -4.5, -1)}${wisp(97, 36, 7.6, -1.5, 1)}`)),
  });
  Object.assign(_ORN, {
    inferno: sig7(() => svg('o-fv o-fvl', '0 0 24 200', vein(1)) + svg('o-fv o-fvr', '0 0 24 200', vein(2))),
    pumpkin_lantern: sig7(() => svg('o-lt', '0 0 60 78', lantern)),
    cobweb: sig7(() => svg('o-wc o-wcl', '0 0 100 100', `<g class="o-wq"><path class="o-wl" d="${cornerWeb.d}"/>${[[1, 2, 1.3], [2, 4, 1], [3, 1, 1.2], [4, 3, 1.5], [5, 5, 1.1]].map(a => cornerWeb.dew(...a)).join('')}</g>`)
      + svg('o-wc o-wcr', '0 0 100 100', `<g class="o-wq"><path class="o-wl" d="${cornerWeb.d}"/>${[[2, 1, 1.2], [3, 3, 1.4], [1, 4, 1], [4, 2, 1.1]].map(a => cornerWeb.dew(...a)).join('')}</g>`) + svg('o-spd', '0 0 24 64', spider)),
    witch_hour: sig7(() => svg('o-mn', '-26 -26 52 52', '<path d="M11.33-18.86A22 22 0 1 0 11.33 18.86A19 19 0 1 1 11.33-18.86z"/>') + svg('o-wt', '-3 -6 52 36', witch)),
  });
})();

// ── Фирменные детали SSS · C (цветение, небо, огни) ─────────────────────────────────────────────
// Продолжение _AP_DECOR и _ORN из app.22.js: разметка слоя фирменной детали (.ap-sig-<id>) и SVG-части образа (_ORN[<skin id>], рисуется на сцене).
// Стили: skin-sig-c-v3.css. Деталь видна с тира SSS (sig_from). Рисунок это вектор: цвета берутся из палитры образа в CSS, а градиент один и тот же белый блик (ornCSheen) в скрытом SVG страницы.
(() => {
  const DEFS = '<svg id="orn-defs-c" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>'
    + '<linearGradient id="ornCSheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".55"/><stop offset=".55" stop-color="#fff" stop-opacity="0"/></linearGradient>'
    + '<mask id="ornCHole" maskUnits="userSpaceOnUse" x="-60" y="-50" width="220" height="220"><rect x="-60" y="-50" width="220" height="220" fill="#fff"/><circle cx="50" cy="50" r="36" fill="#303030"/></mask>'   // дырка под аватар: лепестки не лезут на фото и на созвездие
    + '<radialGradient id="ornCGlow"><stop offset="0" stop-color="#ffb3d1" stop-opacity=".6"/><stop offset="1" stop-color="#ffb3d1" stop-opacity="0"/></radialGradient>'   // мягкое свечение цветка и фонаря без размытия: filter на SVG не везде работает
    + '<clipPath id="ornCDisc"><circle r="10"/></clipPath>'
    + '<g id="ornCBlossom"><path d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(72)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(144)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(216)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><path transform="rotate(288)" d="M0 0C-3.2-1-4-5-1.9-7L0-6 1.9-7C4-5 3.2-1 0 0z"/><circle r="1.5" style="fill:var(--ap-b)"/></g>'
    + '</defs></svg>';
  // витражное крыло (левое; правое это то же, отражённое): перья из трёх вложенных лепестков, синий кончик, золото, светлая сердцевина, свинцовый контур
  const leafD = (L, W) => `M0 0C${-W} ${-L * .3} ${-W * .85} ${-L * .8} 0 ${-L}C${W * .85} ${-L * .8} ${W} ${-L * .3} 0 0z`;
  const wingFeather = (a, L, W) => `<g transform="rotate(${a})">${[1, .72, .44].map((k, i) => `<path class="sr-f${i}" d="${leafD(L * k, W * k)}"/>`).join('')}<path class="sr-sh" d="${leafD(L, W)}"/></g>`;
  const WING = '<g id="ornCWing"><g transform="translate(36 58)">' + [[-76, 46, 9], [-62, 60, 11], [-48, 68, 12.5], [-35, 66, 12], [-22, 56, 11], [-9, 44, 10]].map(f => wingFeather(...f)).join('')
    + [[-70, 28, 7.5], [-54, 36, 8.5], [-38, 36, 8], [-22, 30, 7.5]].map(f => wingFeather(...f)).join('') + '</g></g>';
  const DEFS_ALL = DEFS.replace('</defs>', WING + '</defs>');
  const defs = () => { if (!document.getElementById('orn-defs-c')) document.body.insertAdjacentHTML('beforeend', DEFS_ALL); };
  const SSS = 7;
  const draw = parts => ti => (ti >= SSS ? (defs(), parts) : '');   // деталь одна и видна только на потолке
  const svg = (cls, box, body) => `<svg class="${cls}" viewBox="${box}" aria-hidden="true">${body}</svg>`;

  // ── Бутон Сакуры: голая ветка из угла, тугие бутоны и один раскрывающийся ──
  const bark = (d, w) => `<path class="bd-bk" style="stroke-width:${w}" d="${d}"/><path class="bd-bh" style="stroke-width:${(w * .24).toFixed(1)}" transform="translate(${(-w * .2).toFixed(1)} ${(-w * .22).toFixed(1)})" d="${d}"/>`;
  const bud = (x, y, a, s) => `<g transform="translate(${x} ${y}) rotate(${a}) scale(${s})"><path class="bd-a" d="M0 0C-3.4-1.4-4.2-7 0-12.5 4.2-7 3.4-1.4 0 0z"/><path class="bd-b" d="M0-12.5C4.2-7 3.4-1.4 0 0 1.7-4 1.9-8.4 0-12.5z"/><path class="bd-c" d="M-1.6-4.4C-2-6.8-1-8.8-.3-10.2"/><path class="bd-k" d="M-3.2 1C-2 4.2 2 4.2 3.2 1 2.2-1.9-2.2-1.9-3.2 1z"/></g>`;
  const PET = 'M0 0C-5.2-1.8-6.6-8-3.4-12.6L-1-11 0-11.8 1-11 3.4-12.6C6.6-8 5.2-1.8 0 0z';   // лепесток сакуры с выемкой на конце
  const bloom = `<g transform="translate(140 58) rotate(204) scale(1.6)"><circle class="bd-gl" r="13" cy="-7"/>`
    + `<path class="bd-pl bd-a" style="--r:-34deg" d="${PET}"/><path class="bd-pl bd-a" style="--r:34deg" d="${PET}"/><path class="bd-pl bd-b" style="--r:-12deg" d="${PET}"/><path class="bd-pl bd-b" style="--r:12deg" d="${PET}"/>`
    + `<g class="bd-st"><path d="M-1.6-4V-8.6M0-4V-10M1.6-4V-8.6"/><circle cx="-1.6" cy="-8.8" r=".8"/><circle cx="0" cy="-10.2" r=".8"/><circle cx="1.6" cy="-8.8" r=".8"/></g>`
    + `<path class="bd-a" d="M0 0C-4-1.4-4.6-8.4-2.2-11.4L-.8-10.2 0-10.8.8-10.2 2.2-11.4C4.6-8.4 4-1.4 0 0z"/><path class="bd-c" d="M-2.2-4.6C-2.6-6.8-2.2-8.4-1.6-9.4"/>`
    + `<path class="bd-k" d="M-3.4 1.2C-2 4.6 2 4.6 3.4 1.2 2.4-2-2.4-2-3.4 1.2z"/></g>`;
  const branch = [
    bark('M178-6C158 6 142 16 120 22', 5.4), bark('M120 22C104 28 88 36 74 48', 3.6), bark('M74 48C66 55 60 62 56 72', 2.3),
    bark('M146 14C150 28 148 44 140 58', 2.1), bark('M120 22C116 12 108 6 98 4', 1.9), bark('M96 34C98 46 94 58 88 66', 1.8), bark('M74 48C68 42 62 40 54 41', 1.6),
    bud(98, 4, -66, .95), bud(88, 66, 196, .9), bud(54, 41, -100, .8), bud(56, 72, 202, .85), bloom,
    '<g transform="translate(138 62)"><path class="bd-fall" d="M0 0C3-1 5 2 4 5 2 4-1 2 0 0z"/></g>',
  ].join('');
  Object.assign(_ORN, { sakura_bud: draw(svg('bd-branch', '0 0 170 90', branch)) });
  Object.assign(_AP_DECOR, { budbloom: '' });

  // ── Ханами: облако цветущей кроны над сценой, бумажный фонарь и лепестки, медленно падающие вниз (тушь и васи: приглушённые тона) ──
  const rnd = k => { const x = Math.sin(k * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
  const cloud = (cx, cy, rx, ry, n, k0, m = 1) => Array.from({ length: n }, (_, i) => {
    const a = rnd(k0 + i) * 6.283, r = Math.sqrt(rnd(k0 + i + 40)), x = Math.min(384, Math.max(6, cx + Math.cos(a) * r * rx)), y = Math.max(2, cy + Math.sin(a) * r * ry);
    return `<use class="hn-${i % 3 + 1}" href="#ornCBlossom" transform="translate(${x.toFixed(0)} ${y.toFixed(0)}) rotate(${(rnd(k0 + i + 80) * 72).toFixed(0)}) scale(${((.8 + rnd(k0 + i + 120) * .8) * m).toFixed(2)})"/>`;
  }).join('');
  const hnInk = (d, w) => `<path class="hn-ink" style="stroke-width:${w}" d="${d}"/>`;
  const lantern = '<g transform="translate(344 22)"><path class="hn-ink" style="stroke-width:.8" d="M0 0V9"/><g class="hn-sw"><circle class="hn-gl" cx="0" cy="25" r="24"/><rect class="hn-cap" x="-5" y="8" width="10" height="3" rx="1.2"/><rect class="hn-lb" x="-10" y="10" width="20" height="26" rx="9"/><path class="hn-rib" d="M-9.2 17H9.2M-10 23H10M-9.2 29H9.2"/><rect class="hn-cap" x="-5" y="35" width="10" height="3" rx="1.2"/><path class="hn-ink" style="stroke-width:.8" d="M0 38V46"/><circle class="hn-lb" cx="0" cy="47" r="1.8"/></g></g>';
  const petal = (x, y, dx, d, dl) => `<g transform="translate(${x} ${y})"><path class="hn-pt" style="--dx:${dx}px;--d:${d}s;--dl:${dl}s" d="M0 0C3-1.4 6 1.6 5 5 2.6 4.4-1 2.2 0 0z"/></g>`;
  const canopy = '<g class="hn-wash"><circle cx="50" cy="12" r="56"/><circle cx="338" cy="14" r="62"/></g>'
    + hnInk('M-8 16C40 6 92 28 150 10', 2.6) + hnInk('M398 8C350 22 300 10 236 22', 2.8) + hnInk('M60 20C66 34 62 46 54 54', 1.2) + hnInk('M300 18C298 32 302 44 310 50', 1.2) + hnInk('M120 24C128 36 124 44 116 50', 1)
    + cloud(36, 20, 60, 34, 15, 1) + cloud(346, 24, 66, 38, 16, 60) + cloud(190, 1, 92, 3, 6, 130, .6) + cloud(100, 50, 12, 8, 2, 200) + cloud(262, 46, 14, 8, 2, 220)
    + lantern + petal(118, 56, -22, 17, -2) + petal(250, 40, 26, 19, -8) + petal(60, 60, 18, 15, -11) + petal(318, 58, -30, 21, -5) + petal(190, 20, 14, 23, -14);
  Object.assign(_ORN, { hanami: draw(svg('hn-canopy', '0 0 390 130', canopy)) });
  Object.assign(_AP_DECOR, { hanamitree: '' });

  // ── Золотой Лотос: лотос из золотых лепестков под кольцом, блики и круги храмового пруда (рисуется в координатах рамки: 0..100 это кольцо) ──
  const gx = n => +n.toFixed(1);
  const lotusPetal = (a, L, W, cls, fine) => {
    const d = (k = 1) => `M0 0C${gx(-W * .55 * k)} ${gx(-L * .28 * k)} ${gx(-W * .6 * k)} ${gx(-L * .66 * k)} 0 ${gx(-L * k)}C${gx(W * .6 * k)} ${gx(-L * .66 * k)} ${gx(W * .55 * k)} ${gx(-L * .28 * k)} 0 0z`;
    return `<g transform="rotate(${a})"><path class="${cls}" d="${d()}"/>${fine ? `<path class="gl-vn" d="M0-${gx(L * .1)}V-${gx(L * .74)}"/><path class="gl-in" d="${d(.72)}"/>` : ''}<path class="gl-sh" d="${d()}"/></g>`;
  };
  const glint = (x, y, s, d) => `<g transform="translate(${x} ${y})"><path class="gl-sp" style="--s:${s};--d:${d}s" d="M0-5L1.2-1.2 5 0 1.2 1.2 0 5-1.2 1.2-5 0-1.2-1.2z"/></g>`;
  const lotusBack = '<ellipse class="gl-glow" cx="50" cy="96" rx="62" ry="28"/>'
    + [0, 1, 2].map(i => `<ellipse class="gl-rp" style="--i:${i}" cx="50" cy="106" rx="${50 + i * 19}" ry="${10 + i * 4}"/>`).join('')
    + `<g transform="translate(50 108)">${[-72, -50, -28, 28, 50, 72, 0].map(a => lotusPetal(a, 70, 26, 'gl-b', false)).join('')}${[-62, -40, -18, 18, 40, 62].map(a => lotusPetal(a, 62, 24, 'gl-a', true)).join('')}</g>`;
  const lotusFront = `<g transform="translate(50 114)">${[-38, 38, 0].map(a => lotusPetal(a, 34, 17, 'gl-c', true)).join('')}</g>` + glint(-8, 80, 1.5, 3.4) + glint(108, 78, 1.2, 4.6) + glint(50, 108, 1, 5.4) + glint(86, 100, .8, 4);
  Object.assign(_AP_DECOR, {
    goldlotus: () => (defs(), svg('gl-back', '-30 -10 160 130', `<g mask="url(#ornCHole)">${lotusBack}</g>`) + svg('gl-front', '-30 -10 160 130', `<g mask="url(#ornCHole)">${lotusFront}</g>`)),
  });

  // ── Лазурная Обсерватория: латунный телескоп смотрит на планету с кольцом и орбитами; спутник идёт по орбите ──
  const tube = '<g transform="translate(32 80) rotate(-36)"><path class="tl-yk" d="M0 0L-5 15M0 0L5 15"/>'
    + '<rect class="tl-d" x="-14" y="-2.6" width="10" height="5.2" rx="1.4"/><rect class="tl-d" x="-17.5" y="-3.6" width="4.4" height="7.2" rx="1.6"/>'
    + '<rect class="tl-br" x="-4" y="-6" width="40" height="12" rx="2.5"/><rect class="tl-hl" x="-3" y="-5" width="38" height="2.2" rx="1.1"/><rect class="tl-sd" x="-3" y="3.4" width="38" height="2.4" rx="1.2"/>'
    + '<path class="tl-ln" d="M6-6V6M22-6V6"/><rect class="tl-d" x="34" y="-7.6" width="4" height="15.2" rx="1.4"/><rect class="tl-br" x="36" y="-8.4" width="14" height="16.8" rx="2.6"/><rect class="tl-hl" x="37" y="-7.4" width="12" height="2.2" rx="1.1"/>'
    + '<ellipse class="tl-ln2" cx="50.6" cy="0" rx="2.6" ry="7.2"/><rect class="tl-d" x="4" y="-12.8" width="19" height="4.2" rx="1.9"/><rect class="tl-d" x="7" y="-9.2" width="2.2" height="3.4"/><rect class="tl-d" x="17.6" y="-9.2" width="2.2" height="3.4"/>'
    + '<circle class="tl-d" r="3.6"/><circle class="tl-hl2" r="1.2"/></g>';
  const planet = '<g transform="translate(104 28) rotate(-20)"><path class="tl-rg" d="M-20 0A20 5.4 0 0 1 20 0"/><g transform="rotate(20)"><circle class="tl-pl" r="10"/><circle class="tl-pd" cx="5" cy="4" r="11" clip-path="url(#ornCDisc)"/><path class="tl-pb" d="M-8.2-5.6A10 10 0 0 1 2-9.8"/></g><path class="tl-rg tl-rf" d="M-20 0A20 5.4 0 0 0 20 0"/>'
    + '<ellipse class="tl-or" rx="36" ry="11"/><ellipse class="tl-or tl-o2" rx="52" ry="16"/><g transform="scale(1 .305)"><g class="tl-mn"><g transform="translate(36 0) scale(1 3.28)"><circle class="tl-mo" r="2.5"/></g></g></g></g>';
  const star = (x, y, r, d) => `<circle class="tl-s" style="--d:${d}s" cx="${x}" cy="${y}" r="${r}"/>`;
  const scope = '<path class="tl-ray" d="M76 49L92 38"/>' + planet + tube + '<path class="tl-ln" d="M32 80V95"/><path class="tl-ft" d="M22 97H42"/>'
    + star(132, 62, 1, 3.1) + star(142, 44, 1.3, 4.3) + star(80, 12, 1.1, 3.7) + star(58, 30, .9, 5.1) + star(140, 84, 1, 4.7) + star(112, 76, .9, 3.3);
  Object.assign(_ORN, { observatory: draw(svg('tl-scope', '0 0 150 100', scope)) });
  Object.assign(_AP_DECOR, { telescope: '' });

  // ── Огни Гирлянды: провисший провод с цветными лампочками по верху сцены и короткая нитка вокруг кольца; огни бегут по цепочке (только opacity) ──
  const bulb = (x, y, r, i, k, z = 1) => `<g transform="translate(${x} ${y}) rotate(${r}) scale(${z})"><g class="fl-b fl-${k}" style="--i:${i}"><circle class="fl-g" cy="5.4" r="6.6"/><rect class="fl-sk" x="-1.7" y="0" width="3.4" height="2.8" rx=".8"/><path class="fl-bl" d="M-2.5 2.6C-3.7 5-3.3 8.4 0 9.4 3.3 8.4 3.7 5 2.5 2.6z"/><ellipse class="fl-hi" cx="-.9" cy="5.2" rx=".7" ry="1.6"/></g></g>`;
  const swag = (x0, x1, sag, k0, n, count) => {   // провод провисает по параболе, лампочки висят вниз; по краям провис глубже, над ником мелкий
    const mid = (x0 + x1) / 2, pts = Array.from({ length: count }, (_, j) => { const t = (j + 1) / (count + 1), u = 1 - t; return [u * u * x0 + 2 * u * t * mid + t * t * x1, u * u * 3 + 2 * u * t * (3 + sag * 2) + t * t * 3]; });
    return `<path class="fl-w" d="M${x0} 3Q${mid} ${3 + sag * 2} ${x1} 3"/>` + pts.map((q, j) => bulb(q[0].toFixed(1), q[1].toFixed(1), 0, n + j, (k0 + j) % 3 + 1, 1.2)).join('');
  };
  const swags = swag(-4, 104, 22, 0, 0, 3) + swag(104, 288, 6, 0, 3, 4) + swag(288, 394, 22, 1, 7, 3);
  const ringLights = () => {
    const ang = [-160, -138, -116, -94, -72, -50, -28], at = a => [50 + 57 * Math.cos(a * Math.PI / 180), 50 + 57 * Math.sin(a * Math.PI / 180)].map(n => n.toFixed(1));
    const [x0, y0] = at(-172), [x1, y1] = at(-16);
    return `<path class="fl-w" d="M${x0} ${y0}A57 57 0 0 1 ${x1} ${y1}"/>` + ang.map((a, j) => { const [x, y] = at(a); return bulb(x, y, a - 90, j, j % 3 + 1); }).join('');
  };
  Object.assign(_ORN, { garland: draw(svg('fl-swags', '0 0 390 48', swags)) });
  Object.assign(_AP_DECOR, { fairylights: () => (defs(), svg('fl-ring', '-12 -12 124 124', ringLights())) });

  // ── Бой Курантов: циферблат на полночь, качающийся колокол на кронштейне и золотые салюты по краям (колокол качается, салют вспыхивает: transform и opacity) ──
  const ticks = Array.from({ length: 12 }, (_, k) => { const a = k * Math.PI / 6, r0 = k % 3 ? 17.4 : 15.4; return `M${(Math.sin(a) * r0).toFixed(1)} ${(-Math.cos(a) * r0).toFixed(1)}L${(Math.sin(a) * 19.4).toFixed(1)} ${(-Math.cos(a) * 19.4).toFixed(1)}`; }).join('');
  const clock = `<g transform="translate(76 28)"><circle class="bc-fc" r="24"/><circle class="bc-bz" r="24"/><circle class="bc-bz2" r="20.6"/><path class="bc-tk" d="${ticks}"/><path class="bc-dm" d="M0-14.4l1.9 2.3L0-9.8l-1.9-2.3z"/><path class="bc-hm" d="M0 2.5V-15.6"/><path class="bc-hh" d="M0 2.5L-1.7-10"/><circle class="bc-hub" r="2.2"/></g>`;
  const bell = '<g transform="translate(18 13)"><g class="bc-bell"><path class="bc-bd" d="M-4.5 2C-4.5-.6 4.5-.6 4.5 2 8 6 9 15 12 21 13.2 23.4 15 24.4 16 26H-16C-15 24.4-13.2 23.4-12 21-9 15-8 6-4.5 2z"/><path class="bc-bs" d="M4.5 2C8 6 9 15 12 21 13.2 23.4 15 24.4 16 26H5C6.4 20 6.4 8 4.5 2z"/><path class="bc-bh" d="M-6.4 6.4C-7.8 11.4-8.8 15.6-10.8 20"/><rect class="bc-lp" x="-17" y="25.2" width="34" height="3.6" rx="1.8"/><circle class="bc-lo" cy="-2.2" r="2.2"/><g class="bc-cl"><path class="bc-cn" d="M0 8V29"/><circle class="bc-cb" cy="30.6" r="2.8"/></g></g></g>';
  const burst = (cx, cy, r, k, dl) => `<g transform="translate(${cx} ${cy})"><g class="bc-fw" style="--dl:${dl}s"><circle class="bc-d1" r="2.2"/>${Array.from({ length: 12 }, (_, j) => {
    const a = (j * 30 + k * 11) * Math.PI / 180, c = Math.cos(a), n = Math.sin(a), f = v => (v).toFixed(1);
    return `<path class="bc-r${j % 3}" d="M${f(c * r * .4)} ${f(n * r * .4)}L${f(c * r * .8)} ${f(n * r * .8)}"/><circle class="bc-d${j % 3}" cx="${f(c * r)}" cy="${f(n * r)}" r="${j % 2 ? 1 : 1.6}"/>`;
  }).join('')}</g></g>`;
  const arm = '<rect class="bc-ar" x="4" y="10.4" width="52" height="3.2" rx="1.6"/><path class="bc-br" d="M44 13.6L56 25"/>';
  const waves = '<g class="bc-wv"><path d="M38 18Q41 27 38 36"/><path d="M43 15Q48 27 43 39"/></g>';
  Object.assign(_ORN, {
    midnight_chimes: draw(svg('bc-clock', '0 0 104 66', arm + clock + waves + bell) + svg('bc-fw1', '0 0 110 80', burst(34, 34, 28, 0, 0) + burst(86, 16, 13, 1, -3.4)) + svg('bc-fw2', '0 0 60 60', burst(30, 30, 16, 2, -5.2))),
  });
  Object.assign(_AP_DECOR, { bellchimes: '' });

  // ── Небесное Сияние: витражные крылья за кольцом, тонкий золотой нимб над ним, перо падает вниз ──
  const feather = (x, y, d, dl, dx) => `<g transform="translate(${x} ${y})"><g class="sr-fd" style="--d:${d}s;--dl:${dl}s;--dx:${dx}px"><path class="sr-fe" d="M0 0C2.6-3 3-9 0-15-3-9-2.6-3 0 0z"/><path class="sr-q" d="M0 1V-12"/></g></g>`;
  const seraphBack = '<g mask="url(#ornCHole)"><use class="sr-w" href="#ornCWing"/><g transform="translate(100 0) scale(-1 1)"><use class="sr-w" href="#ornCWing"/></g></g>'
    + feather(-8, 44, 16, -3, 10) + feather(108, 56, 19, -9, -12) + feather(14, 82, 22, -13, 8);
  const seraphHalo = '<g transform="translate(50 -15) rotate(-6)"><ellipse class="sr-h0" rx="24" ry="6.4"/><ellipse class="sr-h1" rx="20.5" ry="5.2"/><g transform="translate(24 0)"><path class="sr-sp" d="M0-6L1.4-1.4 6 0 1.4 1.4 0 6-1.4 1.4-6 0-1.4-1.4z"/></g></g>';
  Object.assign(_AP_DECOR, { seraph: () => (defs(), svg('sr-back', '-30 -10 160 130', seraphBack) + svg('sr-halo', '-30 -40 160 100', seraphHalo)) });
})();

// ── Skins V3 · сцена образа: окружение вокруг аватара ──────────────────────────────────────────
// У каждого образа свой набор слоёв, и он растёт с тиром (C земля и вода, B небо и свет, A предметы по бокам, S живое, SS редкое событие, SSS фирменная деталь, app.32–34.js).
// Слой это строка [минимальный тир 1…7, 'форма движение', {геометрия и переменные}]; формы и движения описаны в skin-scene-v3.css, картинки-силуэты в skin-scene-*-v3.css (подгружаются по требованию, _scArt).
// Форма: glow (мягкое пятно), ring, sil i-<имя> (силуэт), dot (точки через --bs), band, wave. Движение: drift sway pulse breathe beat blink twinkle float rise spin ripple shimmer sweep cross peek flash flicker (неон: трубка гаснет и загорается).
// Флаги: w2 отдаёт слой только полному режиму (на среднем телефоне его нет), m маска, fl зеркало (неподвижным), st растянуть картинку на весь слой (полосы земли и хребтов), go бегущая волна, rev спин назад, dash пунктир.
// cr: [x0, y0, x1, y1] кадрирует рамку слоя до границ рисунка (целые px рамки; у рамки в % доли), см. _scCrop; границы считает и проверяет tools/scene_crop.py.
// Данные образов лежат в app.35–38.js и собираются сюда через _scAdd.
const _AP_SCENES = new Map();
function _scAdd(id, layers) { _AP_SCENES.set(id, layers); }
const _SC_GEO = { l: 'left', t: 'top', r: 'right', b: 'bottom', w: 'width', h: 'height' };
const _SC_SEC = new Set(['dur', 'del']);
// цвет палитры образа (a, b, c) или любой готовый
const _scColor = v => (v === 'a' || v === 'b' || v === 'c' ? `var(--ap-${v})` : v);
// точки светлячков, звёзд, искр: список [dx, dy, размытие, радиус, цвет] превращается в box-shadow одного элемента (один слой вместо десяти)
const _scBs = dots => dots.map(([x, y, blur, spread, color]) => `${x}px ${y}px ${blur}px ${spread}px ${_scColor(color)}`).join(',');
// Кадр слоя: cr = [x0, y0, x1, y1] кадрирует рамку до той части, где у картинки есть пиксели (границы считает и проверяет tools/scene_crop.py). Слой занимает только её, а картинка,
// градиент цвета, центр поворота и масштаба остаются там же, где были в целой рамке: вид тот же, но композитору рисовать и хранить меньше (стрелки часов, дроны, тонкие лучи в большой
// квадратной рамке). Рамка в px: cr в целых px от её левого верхнего угла (тогда пиксельная сетка слоя не сдвигается и картинка ложится точно); рамка в %: cr долями рамки.
const _scIn = v => (v === '0' ? '0px' : v.startsWith('calc(') ? v.slice(5, -1) : v);
const _scPx = v => (/^-?\d*\.?\d+px$/.test(v) ? parseFloat(v) : null);
const _scR = n => +n.toFixed(3);
// длина плюс сдвиг в px (числом, пока длина тоже в px)
const _scMove = (len, px) => {
  if (!px) return len;
  const a = _scPx(len === '0' ? '0px' : len);
  return a !== null ? `${_scR(a + px)}px` : `calc(${_scIn(len)} + ${_scR(px)}px)`;
};
// длина плюс доля другой длины
const _scMoveBy = (len, size, f) => (f ? `calc(${_scIn(len)} + (${_scIn(size)}) * ${_scR(f)})` : len);
function _scCrop(p, cls) {
  const [x0, y0, x1, y1] = p.cr, q = { ...p }, W = _scPx(p.w), H = _scPx(p.h), px = W !== null && H !== null;
  delete q.cr;
  delete q.bp;
  const [ox, oy] = (p.org || '50% 50%').split(' ');
  let kx;
  if (px) {
    if (q.l !== undefined) q.l = _scMove(q.l, x0); else q.r = _scMove(q.r, W - x1);
    if (q.t !== undefined) q.t = _scMove(q.t, y0); else q.b = _scMove(q.b, H - y1);
    q.w = `${x1 - x0}px`;
    q.h = `${y1 - y0}px`;
    const at = (v, size) => (v.endsWith('%') ? (parseFloat(v) / 100) * size : parseFloat(v));
    q.org = `${_scR(at(ox, W) - x0)}px ${_scR(at(oy, H) - y0)}px`;
    q.bz = `${W}px ${H}px`;
    q.cp = `${-x0}px ${-y0}px`;
    kx = (x1 - x0) / W;
  } else {
    kx = x1 - x0;
    const ky = y1 - y0, frac = (v, size) => (v.endsWith('%') ? parseFloat(v) / 100 : _scPx(v) / _scPx(size));
    if (q.l !== undefined) q.l = _scMoveBy(q.l, p.w, x0); else q.r = _scMoveBy(q.r, p.w, 1 - x1);
    if (q.t !== undefined) q.t = _scMoveBy(q.t, p.h, y0); else q.b = _scMoveBy(q.b, p.h, 1 - y1);
    q.w = `calc((${_scIn(p.w)}) * ${_scR(kx)})`;
    q.h = `calc((${_scIn(p.h)}) * ${_scR(ky)})`;
    q.org = `${_scR(((frac(ox, p.w) - x0) / kx) * 100)}% ${_scR(((frac(oy, p.h) - y0) / ky) * 100)}%`;
    q.bz = `${_scR(100 / kx)}% ${_scR(100 / ky)}%`;
    q.cp = `${kx < 1 ? _scR((x0 / (1 - kx)) * 100) : 0}% ${ky < 1 ? _scR((y0 / (1 - ky)) * 100) : 0}%`;
  }
  if (/\bdrift\b/.test(cls) && (p.dx || '7%').endsWith('%')) q.dx = `${_scR(parseFloat(p.dx || '7') / kx)}%`;   // дрейф в процентах считается от ширины самого слоя
  return q;
}
function _scStyle(p, cls = '') {
  if (p.cr) p = _scCrop(p, cls);
  let out = '';
  for (const key in p) {
    const v = p[key];
    out += _SC_GEO[key] ? `${_SC_GEO[key]}:${v};` : key === 'c' || key === 'c2' ? `--${key}:${_scColor(v)};` : _SC_SEC.has(key) ? `--${key}:${v}s;` : `--${key}:${v};`;
  }
  return out;
}
// Картинки слоёв (i-<имя>) лежат в семи файлах skin-scene-{a…g}-v3.css (~830 КБ) и не грузятся при запуске: первый слой с картинкой из файла
// подключает этот файл, а до его прихода слой невидим (data-al, skin-scene-v3.css). Образ по умолчанию и образы без картинок не качают ничего.
// Какая картинка в каком файле, сервер пишет в index.html (window.__pvSceneArt = {буква: [адрес, "имя имя …"]}, FastAPI/main.py _scene_art).
const _SC_ART_FILES = globalThis.__pvSceneArt || {}, _SC_ART = new Map();
for (const [letter, [, names]] of Object.entries(_SC_ART_FILES)) for (const name of names.split(' ')) _SC_ART.set(name, letter);
const _scArtAsked = new Set();
function _scArt(cls) {
  const m = /\bi-([\w-]+)/.exec(cls), letter = m && _SC_ART.get(m[1]);
  if (!letter) return '';
  if (!_scArtAsked.has(letter)) {
    _scArtAsked.add(letter);
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = _SC_ART_FILES[letter][0];
    link.onerror = () => { _scArtAsked.delete(letter); link.remove(); };   // нет сети: слой остаётся невидимым, следующая отрисовка спросит снова
    document.head.appendChild(link);
  }
  return ` data-al="${letter}"`;
}
function apScene(ap) {
  const layers = _AP_SCENES.get(ap.id);
  if (!layers) return '';
  const html = layers.filter(l => l[0] <= ap.ti).map(l => `<i class="sc ${l[1]}${l[2].cr ? ' cr' : ''}"${_scArt(l[1])} style="${_scStyle(l[2], l[1])}"></i>`).join('');
  return html ? `<div class="ap-scene ap-t${ap.ti}" data-sk="${ap.id}" style="${ap.vars}" aria-hidden="true">${html}</div>` : '';
}

// ── Лесной Странник: туман у корней, лучи сквозь хвою, сосны по бокам, светлячки, сова ──
_scAdd('forest', [
  [2, 'glow drift', { l: '-30%', b: '-8%', w: '120%', h: '46%', c: 'a', k: '20%', dx: '7%', dur: 24 }],
  [2, 'glow drift', { r: '-34%', b: '4%', w: '110%', h: '34%', c: 'c', k: '14%', dx: '7%', dur: 31, del: -9 }],
  [3, 'glow sway', { l: '52%', t: '-14%', w: '15%', h: '130%', c: '#fffbe0', k: '24%', rot: '22deg', org: '50% 0', dur: 9 }],
  [3, 'glow sway', { l: '66%', t: '-14%', w: '11%', h: '130%', c: '#fffbe0', k: '19%', rot: '16deg', org: '50% 0', dur: 12, del: -4 }],
  [3, 'glow sway', { l: '36%', t: '-14%', w: '9%', h: '130%', c: '#fffbe0', k: '15%', rot: '28deg', org: '50% 0', dur: 15, del: -7 }],
  [4, 'sil i-pineL', { l: '-5%', b: '-2%', w: '36%', h: '74%', o: .78, bp: '0% 100%' }],
  [4, 'sil i-pineR', { r: '-5%', b: '-2%', w: '36%', h: '74%', o: .78, bp: '100% 100%' }],
  [5, 'dot blink float', { l: '22%', t: '46%', c: '#fffbe0', bs: _scBs([[0, 0, 7, 3, '#e6ff9a'], [70, 26, 6, 2, '#e6ff9a'], [150, -10, 7, 3, 'a']]), dur: 4.2 }],
  [5, 'dot blink float', { l: '58%', t: '28%', c: '#fffbe0', bs: _scBs([[0, 0, 7, 3, '#e6ff9a'], [-54, 60, 6, 2, 'a'], [66, 74, 7, 3, '#e6ff9a']]), dur: 5.4, del: -1.7 }],
  [5, 'dot blink float', { l: '78%', t: '58%', c: '#fffbe0', bs: _scBs([[0, 0, 7, 3, '#e6ff9a'], [-120, -16, 6, 2, '#e6ff9a'], [-40, 22, 7, 3, 'a']]), dur: 3.7, del: -2.6, dx: '-14px' }],
  [6, 'dot peek w2', { r: '15%', b: '40%', s: '4px', c: '#ffe27a', bs: _scBs([[0, 0, 6, 2, '#ffd54a'], [11, 0, 0, 0, '#ffe27a'], [11, 0, 6, 2, '#ffd54a']]), dur: 11 }],
]);

// ── Песчаная Тропа: закатное небо, низкое солнце и лучи, барханы с подсвеченным гребнем, марево, позёмка, караван ──
_scAdd('dune', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, transparent 26%, rgba(240,201,135,.16) 58%, rgba(224,150,70,.34) 84%, rgba(120,60,20,.3))' }],
  [2, 'glow drift', { l: '-25%', b: '2%', w: '150%', h: '40%', c: 'a', k: '38%', dx: '6%', dur: 28 }],
  [2, 'band shimmer', { l: '4%', b: '30%', w: '92%', h: '22px', bg: 'radial-gradient(closest-side, rgba(255,230,180,.34), transparent)', dx: '18px', dur: 3.4 }],
  [2, 'band shimmer w2', { l: '14%', b: '21%', w: '72%', h: '18px', bg: 'radial-gradient(closest-side, rgba(255,226,170,.3), transparent)', dx: '-14px', dur: 4.6, del: -1.3 }],
  [3, 'glow breathe', { l: '36%', t: '-36%', w: '90%', h: '84%', c: 'c', k: '54%', dur: 10 }],
  [3, 'glow sway', { l: '52%', t: '-14%', w: '15%', h: '130%', c: '#ffe3a8', k: '26%', rot: '24deg', org: '50% 0', dur: 10 }],
  [3, 'glow sway', { l: '68%', t: '-14%', w: '10%', h: '130%', c: '#ffe3a8', k: '20%', rot: '16deg', org: '50% 0', dur: 13, del: -5 }],
  [4, 'sil i-duneFar', { l: '-4%', b: '13%', w: '108%', h: '26%', o: .9 }],
  [4, 'sil i-duneL', { l: '-6%', b: '3%', w: '66%', h: '58%', bp: '0% 100%' }],
  [4, 'sil i-duneR', { r: '-6%', b: '3%', w: '66%', h: '58%', bp: '100% 100%' }],
  [5, 'dot sweep', { l: '0', t: '56%', s: '2px', c: '#f0c987', bs: _scBs([[0, 0, 0, 0, 'a'], [22, 6, 0, 0, 'a'], [46, -4, 0, 1, 'c'], [70, 8, 0, 0, 'a'], [96, 0, 0, 1, 'c'], [120, -6, 0, 1, 'a'], [150, 4, 0, 0, 'c']]), fx: '-170px', tx: '560px', ty: '-34px', dur: 11 }],
  [5, 'dot sweep w2', { l: '0', t: '72%', s: '2px', c: '#fff1d6', bs: _scBs([[0, 0, 0, 0, 'c'], [30, -5, 0, 0, 'a'], [58, 7, 0, 1, 'c'], [90, -2, 0, 0, 'a'], [126, 5, 0, 1, 'c']]), fx: '-150px', tx: '560px', ty: '-22px', dur: 9, del: -4 }],
  [5, 'glow sweep', { l: '0', t: '60%', w: '28%', h: '7%', c: '#ffe3a8', k: '34%', fx: '-140px', tx: '560px', ty: '-14px', dur: 15, del: -6 }],
  [5, 'glow sway', { l: '9%', b: '16%', w: '10%', h: '42%', c: 'a', k: '30%', ang: '5deg', org: '50% 100%', dur: 7 }],
  [6, 'sil i-camels cross w2', { l: '0', b: '29%', w: '30%', h: '11%', o: .9, fx: '-140px', tx: '540px', dur: 56 }],
  [7, 'dot twinkle', { l: '24%', t: '80%', s: '3px', c: '#fff1d6', bs: _scBs([[0, 0, 5, 2, '#fff1d6'], [210, -6, 5, 2, '#fff1d6'], [96, 12, 4, 1, 'a'], [300, 18, 4, 1, '#fff1d6']]), dur: 3.1 }],
]);

// ── Тихая Гавань: туман над водой, огни города, пирс с фонарём, причал с краном и лодка, чайки, парусник на горизонте ──
_scAdd('harbor', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, transparent 38%, rgba(75,127,168,.26) 64%, rgba(30,70,110,.46) 100%)' }],
  [2, 'glow drift', { l: '-30%', b: '12%', w: '160%', h: '38%', c: 'c', k: '26%', dx: '8%', dur: 30 }],
  [3, 'glow breathe', { l: '-18%', t: '-34%', w: '76%', h: '76%', c: 'c', k: '52%', dur: 12 }],
  [3, 'dot blink', { l: '9%', t: '55%', s: '3px', c: '#ffe2a8', bs: _scBs([[0, 0, 6, 3, '#ffd98a'], [38, 2, 5, 2, '#ffd98a'], [196, 6, 5, 2, '#ffd98a'], [236, 3, 5, 2, '#ffd98a'], [262, 7, 4, 2, '#ffd98a'], [330, 1, 5, 2, '#ffd98a']]), dur: 6 }],
  [3, 'glow shimmer', { l: '2%', b: '-4%', w: '18%', h: '42%', c: 'c', k: '40%', dx: '8px', dur: 3.6 }],
  [4, 'sil i-quay', { r: '-4%', b: '7%', w: '44%', h: '40%', bp: '100% 100%', o: .95 }],
  [4, 'sil i-pier', { l: '-4%', b: '8%', w: '42%', h: '34%', bp: '0% 100%' }],
  [4, 'glow pulse', { l: '30%', t: '44%', w: '17%', h: '24%', c: '#ffd98a', k: '58%', dur: 3.4 }],
  [4, 'sil i-boat float', { r: '14%', b: '6%', w: '22%', h: '36%', bp: '100% 100%', dx: '3px', dy: '-6px', dur: 7 }],
  [2, 'wave go i-wave', { l: '0', b: '-3%', w: 'calc(100% + 150px)', h: '18%', tw: '150px', dur: 24 }],
  [3, 'wave go i-wave2', { l: '0', b: '-5%', w: 'calc(100% + 225px)', h: '15%', tw: '225px', o: .85, dur: 40 }],
  [5, 'sil m i-gull cross', { l: '0', t: '14%', w: '38px', h: '18px', c: '#e8f3fb', o: .95, fx: '-60px', tx: '520px', ty: '-34px', dur: 24 }],
  [5, 'sil m i-gull cross w2', { l: '0', t: '24%', w: '28px', h: '13px', c: '#e8f3fb', o: .8, fx: '-60px', tx: '520px', ty: '22px', dur: 31, del: -12 }],
  [5, 'dot blink', { r: '31%', b: '19%', s: '4px', c: '#ff6b5a', bs: '0 0 8px 3px rgba(255,107,90,.7)', dur: 2.4 }],
  [5, 'ring ripple', { l: '14%', b: '4%', w: '22%', h: '5%', c: 'c', k: '80%', bw: '1.4px', dur: 5.4 }],
  [5, 'ring ripple w2', { r: '8%', b: '6%', w: '18%', h: '4%', c: 'c', k: '70%', bw: '1.4px', dur: 6.6, del: -2.5 }],
  [6, 'sil i-ship cross w2', { l: '0', b: '31%', w: '26%', h: '28%', o: .7, fx: '-130px', tx: '560px', dur: 84 }],
  [7, 'glow sway', { r: '-12%', b: '31%', w: '118%', h: '9%', c: '#fff6d0', k: '30%', rot: '-9deg', ang: '10deg', org: '100% 50%', dur: 8 }],
]);

// ── Пруд Лотосов: утренний туман, лучи сквозь дымку, камыш и листья, стрекозы, круги на воде, карп под водой ──
_scAdd('lotus_pond', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, transparent 40%, rgba(63,200,170,.14) 70%, rgba(20,110,95,.36))' }],
  [2, 'glow drift', { l: '-30%', b: '-4%', w: '160%', h: '46%', c: 'a', k: '34%', dx: '7%', dur: 27 }],
  [2, 'band shimmer', { l: '4%', b: '15%', w: '92%', h: '22px', bg: 'radial-gradient(closest-side, rgba(232,255,246,.3), transparent)', dx: '12px', dur: 4.4 }],
  [3, 'glow breathe', { l: '40%', t: '-32%', w: '76%', h: '70%', c: 'c', k: '44%', dur: 10 }],
  [3, 'glow sway', { l: '56%', t: '-14%', w: '13%', h: '128%', c: '#ffe9f0', k: '22%', rot: '20deg', org: '50% 0', dur: 11 }],
  [3, 'glow sway w2', { l: '40%', t: '-14%', w: '9%', h: '128%', c: '#e8fff6', k: '18%', rot: '26deg', org: '50% 0', dur: 14, del: -6 }],
  [3, 'dot twinkle', { l: '12%', t: '10%', s: '2px', c: '#fff', bs: _scBs([[0, 0, 4, 1, '#fff'], [240, 20, 4, 1, '#fff'], [310, -4, 3, 1, 'c'], [70, 44, 3, 1, '#fff']]), dur: 3.3 }],
  [4, 'sil i-reeds', { l: '-3%', b: '1%', w: '28%', h: '68%', bp: '0% 100%' }],
  [4, 'sil i-reeds fl', { r: '-3%', b: '1%', w: '28%', h: '62%', bp: '0% 100%' }],
  [4, 'sil i-pads', { l: '0', b: '-1%', w: '100%', h: '18%' }],
  [5, 'dot float blink', { l: '70%', t: '36%', s: '3px', c: '#e8fff6', bs: _scBs([[0, 0, 5, 2, 'a'], [-110, 40, 5, 2, '#e8fff6']]), dx: '16px', dy: '-10px', dur: 4.1 }],
  [5, 'dot float blink w2', { l: '16%', t: '44%', s: '3px', c: '#ffc2d6', bs: _scBs([[0, 0, 5, 2, 'c'], [90, -30, 5, 2, 'a']]), dx: '-14px', dy: '12px', dur: 5.2, del: -2 }],
  [5, 'ring ripple', { l: '22%', b: '5%', w: '20%', h: '5%', c: 'c', k: '80%', bw: '1.4px', dur: 5.8 }],
  [5, 'ring ripple', { r: '16%', b: '7%', w: '16%', h: '4%', c: 'a', k: '80%', bw: '1.4px', dur: 6.8, del: -3 }],
  [6, 'sil i-koi cross w2', { l: '0', b: '6%', w: '22%', h: '9%', o: .75, fx: '-110px', tx: '540px', ty: '-16px', dur: 38 }],
  [7, 'glow breathe', { l: '30%', b: '-6%', w: '40%', h: '30%', c: 'c', k: '40%', dur: 7 }],
]);

// ── Порог: фиолетовая граница, менгиры с рунами, шепчущая тень, разлом ──
_scAdd('threshold', [
  [2, 'glow drift', { l: '-30%', b: '-10%', w: '160%', h: '46%', c: '#000', k: '56%', dx: '6%', dur: 26 }],
  [2, 'glow drift', { l: '-20%', b: '2%', w: '140%', h: '38%', c: 'a', k: '30%', dx: '8%', dur: 33, del: -11 }],
  [3, 'glow pulse', { l: '42%', t: '-12%', w: '16%', h: '130%', c: 'a', k: '40%', dur: 5.5 }],
  [3, 'ring dash spin', { l: '6%', t: '-6%', w: '88%', h: '96%', c: 'b', k: '80%', bw: '1.2px', dur: 140 }],
  [3, 'glow breathe', { l: '20%', t: '-20%', w: '60%', h: '50%', c: 'b', k: '30%', dur: 9 }],
  [4, 'sil i-stones', { l: '-3%', b: '1%', w: '38%', h: '66%', bp: '0% 100%' }],
  [4, 'sil i-stones fl', { r: '-3%', b: '1%', w: '38%', h: '58%', bp: '0% 100%', o: .92 }],
  [4, 'dot pulse', { l: '10%', t: '45%', s: '2px', c: 'a', bs: _scBs([[0, 0, 6, 3, 'a'], [8, 28, 5, 2, 'a'], [293, 4, 6, 3, '#7aa8ff'], [300, 38, 5, 2, '#7aa8ff']]), dur: 3.6 }],
  [5, 'sil i-wisp peek w2', { l: '2%', b: '8%', w: '14%', h: '38%', o: .9, dur: 13 }],
  [5, 'dot rise', { l: '30%', b: '4%', s: '2px', c: 'a', bs: _scBs([[0, 0, 4, 1, 'a'], [90, -10, 4, 1, '#7aa8ff'], [160, 6, 4, 1, 'a'], [230, -4, 3, 1, '#7aa8ff']]), dy: '-110px', dur: 8 }],
  [5, 'dot rise w2', { l: '40%', b: '2%', s: '2px', c: 'b', bs: _scBs([[0, 0, 4, 1, 'b'], [80, 6, 4, 1, 'a'], [150, -8, 3, 1, '#7aa8ff']]), dy: '-90px', dur: 10, del: -4 }],
  [6, 'glow peek', { l: '66%', t: '-12%', w: '18%', h: '128%', c: '#e8dcff', k: '66%', dur: 17 }],
  [6, 'band peek', { l: '74.4%', t: '2%', w: '2px', h: '96%', bg: 'linear-gradient(transparent, #fff 18%, #fff 82%, transparent)', bs: '0 0 10px 3px rgba(180,140,255,.85)', dur: 17 }],
  [6, 'glow flash w2', { l: '10%', t: '-30%', w: '90%', h: '120%', c: 'a', k: '34%', dur: 17 }],
]);

// ── Изморозь: полярная ночь, холодные лучи, ледяные осколки и сосульки, снегопад, падающая звезда ──
_scAdd('frost', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, transparent 36%, rgba(166,224,255,.12) 62%, rgba(90,169,238,.3))' }],
  [2, 'glow drift', { l: '-30%', b: '-10%', w: '160%', h: '44%', c: 'c', k: '30%', dx: '7%', dur: 28 }],
  [2, 'band shimmer', { l: '4%', b: '8%', w: '92%', h: '14px', bg: 'radial-gradient(closest-side, rgba(255,255,255,.4), transparent)', dx: '18px', dur: 5 }],
  [3, 'glow breathe', { l: '-12%', t: '-36%', w: '74%', h: '74%', c: 'c', k: '40%', dur: 11 }],
  [3, 'glow sway', { l: '58%', t: '-14%', w: '13%', h: '128%', c: 'a', k: '30%', rot: '20deg', org: '50% 0', dur: 10 }],
  [3, 'glow sway', { l: '30%', t: '-14%', w: '9%', h: '128%', c: 'c', k: '22%', rot: '-18deg', org: '50% 0', dur: 14, del: -5 }],
  [4, 'sil i-ice', { l: '-5%', b: '1%', w: '34%', h: '62%', bp: '0% 100%' }],
  [4, 'sil i-ice fl', { r: '-5%', b: '1%', w: '32%', h: '54%', bp: '0% 100%' }],
  [4, 'sil i-icicles', { l: '-2%', t: '4%', w: '50%', h: '32%', bp: '0% 0%' }],
  [4, 'sil i-icicles fl', { r: '-2%', t: '4%', w: '44%', h: '28%', bp: '0% 0%' }],
  [4, 'glow pulse', { l: '4%', b: '8%', w: '22%', h: '30%', c: '#fff', k: '24%', dur: 4.4 }],
  [5, 'dot rise', { l: '8%', t: '-6%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 2, 1, '#fff'], [90, 40, 2, 0, '#fff'], [180, -10, 2, 1, '#fff'], [250, 60, 2, 0, '#fff'], [320, 20, 2, 1, '#fff']]), dy: '300px', dx: '-24px', s0: '1', s1: '1', dur: 11 }],
  [5, 'dot rise', { l: '16%', t: '-6%', s: '2px', c: '#dff4ff', bs: _scBs([[0, 0, 1, 0, '#dff4ff'], [70, 30, 1, 0, '#fff'], [150, 8, 1, 1, '#dff4ff'], [230, 50, 1, 0, '#fff'], [300, 14, 1, 0, '#dff4ff']]), dy: '300px', dx: '20px', s0: '1', s1: '1', dur: 8, del: -3 }],
  [5, 'dot twinkle', { l: '20%', t: '22%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [250, 70, 5, 2, '#fff'], [118, 150, 4, 1, 'a']]), dur: 2.9 }],
  [6, 'band cross', { l: '0', t: '6%', w: '150px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(166,224,255,.75) 70%, #fff)', bs: '0 0 8px 2px rgba(166,224,255,.7)', rot: '16deg', fx: '-150px', tx: '540px', ty: '130px', dur: 19 }],
  [7, 'glow breathe', { l: '30%', t: '-30%', w: '40%', h: '60%', c: '#fff', k: '16%', dur: 5.5 }],
]);

// ── Медные Сумерки: горн внизу, сумеречное небо, трубы и шестерни, пар и искры, выброс пара ──
_scAdd('copper', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(47,156,154,.16), transparent 36%, rgba(229,154,107,.22) 84%, rgba(255,150,70,.3))' }],
  [2, 'glow breathe', { l: '-10%', b: '-14%', w: '120%', h: '54%', c: 'a', k: '58%', dur: 4.8 }],
  [2, 'glow rise', { l: '8%', b: '16%', w: '22%', h: '26%', c: '#ffd9b8', k: '22%', dy: '-90px', s0: '.6', s1: '1.5', dur: 7 }],
  [3, 'glow drift', { l: '-20%', t: '-20%', w: '90%', h: '52%', c: 'b', k: '30%', dx: '8%', dur: 22 }],
  [3, 'glow pulse', { l: '36%', t: '30%', w: '28%', h: '40%', c: 'a', k: '22%', dur: 3.2 }],
  [3, 'sil m i-cog spin', { l: '-18%', b: '14%', w: '38%', h: '48%', c: '#b5683a', o: .34, dur: 120 }],
  [3, 'sil m i-cog spin rev', { r: '-14%', t: '-6%', w: '34%', h: '42%', c: '#b5683a', o: .3, dur: 90 }],
  [4, 'sil i-pipes', { l: '-4%', b: '1%', w: '32%', h: '72%', bp: '0% 100%' }],
  [4, 'sil i-pipes fl', { r: '-4%', b: '1%', w: '32%', h: '62%', bp: '0% 100%' }],
  [4, 'glow pulse', { l: '3%', b: '1%', w: '16%', h: '18%', c: '#ffb26b', k: '60%', dur: 2.6 }],
  [4, 'glow pulse', { r: '3%', b: '1%', w: '16%', h: '16%', c: '#ffb26b', k: '56%', dur: 3.1, del: -1 }],
  [5, 'dot rise', { l: '8%', b: '30%', s: '2px', c: '#ffd9b8', bs: _scBs([[0, 0, 3, 1, 'a'], [26, -14, 3, 1, '#ffc27a'], [48, 6, 3, 1, 'a'], [70, -22, 3, 1, '#ffc27a']]), dx: '30px', dy: '-120px', dur: 4.2 }],
  [5, 'dot rise', { r: '12%', b: '24%', s: '2px', c: '#ffd9b8', bs: _scBs([[0, 0, 3, 1, 'a'], [-30, -10, 3, 1, '#ffc27a'], [-52, 8, 3, 1, 'a']]), dx: '-26px', dy: '-100px', dur: 5.1, del: -2 }],
  [5, 'glow rise w2', { l: '11%', b: '58%', w: '14%', h: '20%', c: '#ffe9d6', k: '26%', dy: '-70px', dx: '10px', s0: '.5', s1: '1.8', dur: 6 }],
  [5, 'glow rise w2', { r: '6%', b: '50%', w: '14%', h: '20%', c: '#ffe9d6', k: '22%', dy: '-70px', dx: '-10px', s0: '.5', s1: '1.8', dur: 7.4, del: -3 }],
  [5, 'dot blink', { l: '23%', b: '37%', s: '3px', c: 'b', bs: _scBs([[0, 0, 5, 2, 'b'], [262, -12, 5, 2, 'b']]), dur: 2.6 }],
  [6, 'glow peek', { r: '2%', b: '34%', w: '40%', h: '10%', c: '#fff4e6', k: '60%', dur: 9 }],
  [6, 'glow flash w2', { l: '-10%', b: '-20%', w: '120%', h: '60%', c: '#ff9a55', k: '44%', dur: 12 }],
]);

// ── Бутон Сакуры: рассвет над голой веткой, тугие бутоны, лепестки на земле и в воздухе, один цветок распускается ──
_scAdd('sakura_bud', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(120,60,100,.18), transparent 34%, rgba(255,194,217,.14) 70%, rgba(217,107,148,.28))' }],
  [2, 'glow drift', { l: '-30%', b: '-12%', w: '160%', h: '46%', c: 'a', k: '34%', dx: '7%', dur: 26 }],
  [2, 'dot', { l: '8%', b: '3%', s: '3px', c: 'c', bs: _scBs([[0, 0, 1, 1, 'a'], [40, 6, 1, 0, 'c'], [86, -3, 1, 1, 'a'], [140, 7, 1, 0, 'c'], [190, 0, 1, 1, 'a'], [244, 6, 1, 0, 'c'], [290, -4, 1, 1, 'a'], [338, 5, 1, 0, 'c']]) }],
  [3, 'glow breathe', { l: '12%', t: '-38%', w: '90%', h: '70%', c: '#ffe9c8', k: '44%', dur: 11 }],
  [3, 'glow sway', { l: '60%', t: '-14%', w: '12%', h: '126%', c: '#fff2f6', k: '24%', rot: '20deg', org: '50% 0', dur: 11 }],
  [3, 'glow sway w2', { l: '44%', t: '-14%', w: '8%', h: '126%', c: '#ffd9e6', k: '18%', rot: '26deg', org: '50% 0', dur: 15, del: -6 }],
  [4, 'sil i-budsL', { l: '-6%', t: '2%', w: '46%', h: '46%', bp: '0% 0%' }],
  [4, 'sil i-budsR', { r: '-6%', b: '12%', w: '44%', h: '42%', bp: '100% 100%' }],
  [5, 'dot rise', { l: '14%', t: '4%', s: '5px', c: 'a', bs: _scBs([[0, 0, 1, 0, 'a'], [90, 36, 1, 0, 'c'], [180, 6, 1, 1, 'a'], [270, 52, 1, 0, 'c']]), dy: '280px', dx: '36px', s0: '1', s1: '.8', dur: 12 }],
  [5, 'dot rise w2', { l: '30%', t: '2%', s: '4px', c: 'c', bs: _scBs([[0, 0, 1, 0, 'c'], [70, 28, 1, 0, 'a'], [160, 14, 1, 1, 'c']]), dy: '300px', dx: '-30px', s0: '1', s1: '.8', dur: 15, del: -6 }],
  [5, 'dot pulse', { l: '30%', t: '18%', s: '3px', c: '#fff2f6', bs: _scBs([[0, 0, 7, 3, 'a'], [60, -14, 6, 2, 'a'], [200, 120, 7, 3, 'a']]), dur: 4 }],
  [6, 'glow ripple', { l: '10%', t: '16%', w: '26%', h: '30%', c: 'a', k: '60%', dur: 9 }],
  [6, 'sil m i-bloom ripple', { l: '17%', t: '27%', w: '46px', h: '46px', c: 'c', o: .95, dur: 9 }],
]);

// ── Skins V3 · сцены образов B и A: Инферно, Ханами, Нефритовый Двор, Небесное Сияние, Рубиновый Собор, Лазурная Обсерватория, Золотой Лотос ──
// Движок, словарь слоёв и правила лежат в app.35.js (_scAdd, _scBs); картинки-силуэты рисует tools/scene_art_b.py (skin-scene-b-v3.css).

// ── Инферно: багровое небо, два вулкана с лавовыми реками, дальний хребет, угли и пепел, извержение с лавовыми бомбами ──
_scAdd('inferno', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(110,20,12,.22), transparent 40%, rgba(227,67,43,.18) 72%, rgba(255,130,40,.38))' }],
  [2, 'glow breathe', { l: '-14%', b: '-22%', w: '128%', h: '58%', c: 'a', k: '60%', dur: 4.4 }],
  [2, 'band shimmer', { l: '8%', b: '9%', w: '84%', h: '16px', bg: 'radial-gradient(closest-side, rgba(255,196,120,.42), transparent)', dx: '18px', dur: 2.6 }],
  [3, 'glow drift', { l: '-30%', t: '-26%', w: '120%', h: '54%', c: 'b', k: '40%', dx: '8%', dur: 21 }],
  [3, 'glow drift', { l: '-22%', t: '-8%', w: '86%', h: '42%', c: '#2a0d0a', k: '62%', dx: '6%', dur: 27, del: -9 }],
  [3, 'glow breathe', { l: '34%', t: '-30%', w: '84%', h: '66%', c: '#ff6a30', k: '26%', dur: 9 }],
  [3, 'glow', { l: '-24%', t: '22%', w: '148%', h: '62%', c: '#ff5a26', k: '34%' }],
  [3, 'sil i-volcFar st', { l: '-4%', b: '8%', w: '108%', h: '22%', o: .95 }],
  [4, 'sil i-volcL', { l: '-22%', b: '1%', w: '78%', h: '88%', bp: '0% 100%' }],
  [4, 'sil i-volcR', { r: '-14%', b: '1%', w: '72%', h: '70%', bp: '100% 100%' }],
  [4, 'glow pulse', { l: '2%', t: '33%', w: '27%', h: '20%', c: '#ff7a2a', k: '66%', dur: 2.4 }],
  [4, 'glow pulse', { l: '70%', t: '51%', w: '22%', h: '16%', c: '#ff7a2a', k: '62%', dur: 3, del: -1.1 }],
  [4, 'sil i-crags st', { l: '-4%', b: '3%', w: '108%', h: '12%' }],
  [5, 'dot rise', { l: '15%', t: '41%', s: '2px', c: '#ffd9a0', bs: _scBs([[0, 0, 3, 1, 'a'], [14, -22, 3, 1, '#ffc27a'], [-12, -46, 3, 1, 'a'], [20, -70, 3, 1, '#ffc27a'], [-6, -96, 2, 1, 'a']]), dx: '26px', dy: '-90px', dur: 5 }],
  [5, 'dot rise', { l: '81%', t: '57%', s: '2px', c: '#ffd9a0', bs: _scBs([[0, 0, 3, 1, 'a'], [-16, -20, 3, 1, '#ffc27a'], [10, -44, 3, 1, 'a'], [-18, -68, 3, 1, '#ffc27a']]), dx: '-22px', dy: '-80px', dur: 6.2, del: -2.4 }],
  [5, 'glow rise w2', { l: '6%', t: '16%', w: '18%', h: '26%', c: '#7a4a40', k: '34%', dy: '-70px', dx: '14px', s0: '.6', s1: '1.9', dur: 8 }],
  [5, 'glow rise w2', { l: '74%', t: '34%', w: '16%', h: '24%', c: '#7a4a40', k: '30%', dy: '-60px', dx: '-12px', s0: '.6', s1: '1.9', dur: 9.4, del: -4 }],
  [6, 'glow flash', { l: '-12%', t: '-8%', w: '70%', h: '48%', c: '#e8d0ff', k: '46%', dur: 13 }],
  [6, 'sil m i-bolt flash', { l: '14%', t: '4%', w: '30px', h: '96px', c: '#fff2d8', dur: 13 }],
  [6, 'glow peek', { l: '10%', t: '-12%', w: '10%', h: '52%', c: '#ffb25a', k: '60%', dur: 15, del: -5 }],
  [6, 'sil m i-fireball cross', { l: '0', t: '58%', w: '92px', h: '42px', c: 'rgba(255,90,30,.15)', c2: '#ffe27a', gd: '90deg', rot: '-26deg', fx: '60px', tx: '420px', ty: '-170px', dur: 15, del: -9 }],
  [6, 'sil m i-fireball cross w2', { l: '0', t: '72%', w: '66px', h: '30px', c: 'rgba(255,90,30,.15)', c2: '#ffd27a', gd: '90deg', rot: '206deg', fx: '460px', tx: '80px', ty: '-150px', dur: 15, del: -2 }],
  [7, 'dot rise', { l: '15%', t: '40%', s: '3px', c: '#fff0c0', bs: _scBs([[0, 0, 4, 2, '#ffd27a'], [10, -34, 3, 1, 'a'], [-14, -70, 3, 2, '#ffd27a'], [16, -108, 3, 1, 'a'], [-8, -140, 2, 1, '#ffd27a']]), dx: '-30px', dy: '-130px', dur: 3.4 }],
  [7, 'glow breathe', { l: '-12%', t: '22%', w: '52%', h: '42%', c: '#ff8a3a', k: '40%', dur: 3.6 }],
]);

// ── Ханами: сад ночью на васи, Фудзи в дымке и луна, вишня в цвету, тории и каменный фонарь, лепестки на воде, порыв ветра ──
_scAdd('hanami', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(70,24,58,.24), transparent 40%, rgba(255,168,204,.1) 70%, rgba(239,106,163,.3))' }],
  [2, 'glow drift', { l: '-30%', b: '-6%', w: '160%', h: '42%', c: 'a', k: '30%', dx: '7%', dur: 26 }],
  [2, 'wave go i-sakuWave', { l: '0', b: '-3%', w: 'calc(100% + 150px)', h: '16%', tw: '150px', dur: 30 }],
  [3, 'glow breathe', { l: '-4%', t: '-4%', w: '52%', h: '46%', c: '#fff0f6', k: '34%', dur: 11 }],
  [3, 'sil m i-disc', { l: '13%', t: '22%', w: '54px', h: '54px', c: '#fff7fb', c2: '#ffd9e8', gd: '160deg', o: .92 }],
  [3, 'sil i-fuji st', { l: '-30%', b: '13%', w: '92%', h: '34%', o: .95 }],
  [3, 'wave go i-sakuWave2', { l: '0', b: '-5%', w: 'calc(100% + 225px)', h: '13%', tw: '225px', o: .85, dur: 46 }],
  [4, 'sil i-sakuraTree', { l: '-5%', b: '1%', w: '46%', h: '64%', bp: '0% 100%' }],
  [4, 'sil i-torii', { r: '3%', b: '13%', w: '21%', h: '30%', bp: '100% 100%' }],
  [4, 'sil i-tourou', { r: '13%', b: '8%', w: '12%', h: '26%', bp: '100% 100%' }],
  [4, 'glow pulse', { l: '72%', t: '69%', w: '17%', h: '15%', c: '#ffb878', k: '56%', dur: 4 }],
  [5, 'dot rise', { l: '14%', t: '10%', s: '5px', c: 'a', bs: _scBs([[0, 0, 1, 0, 'a'], [90, 36, 1, 0, 'c'], [180, 6, 1, 1, 'a'], [270, 52, 1, 0, 'c']]), dy: '280px', dx: '36px', s0: '1', s1: '.8', dur: 12 }],
  [5, 'dot rise', { l: '34%', t: '6%', s: '4px', c: 'c', bs: _scBs([[0, 0, 1, 0, 'c'], [70, 28, 1, 0, 'a'], [160, 14, 1, 1, 'c'], [230, 44, 1, 0, 'a']]), dy: '300px', dx: '-30px', s0: '1', s1: '.8', dur: 15, del: -6 }],
  [5, 'dot float', { l: '10%', b: '5%', s: '4px', c: '#ffd6e6', bs: _scBs([[0, 0, 1, 0, '#ffd6e6'], [86, 3, 1, 0, 'a'], [170, -2, 1, 0, '#fff0f6'], [262, 4, 1, 0, 'a'], [330, 0, 1, 0, '#ffd6e6']]), dx: '16px', dy: '0px', dur: 9 }],
  [5, 'ring ripple', { l: '36%', b: '3%', w: '24%', h: '5%', c: 'c', k: '70%', bw: '1.4px', dur: 6 }],
  [6, 'dot sweep', { l: '0', t: '38%', s: '5px', c: '#ffd6e6', bs: _scBs([[0, 0, 1, 0, 'a'], [26, 12, 1, 0, 'c'], [48, -10, 1, 1, '#ffd6e6'], [70, 22, 1, 0, 'a'], [96, 2, 1, 0, 'c'], [120, -16, 1, 1, 'a'], [146, 14, 1, 0, '#ffd6e6'], [168, -4, 1, 0, 'c'], [194, 20, 1, 1, 'a'], [220, -12, 1, 0, '#ffd6e6'], [246, 6, 1, 0, 'c']]), fx: '-260px', tx: '620px', ty: '-60px', dur: 17 }],
  [6, 'glow peek', { l: '2%', t: '2%', w: '44%', h: '42%', c: '#fff0f6', k: '56%', dur: 17, del: -7 }],
  [6, 'dot sweep w2', { l: '0', t: '56%', s: '4px', c: '#ffa8cc', bs: _scBs([[0, 0, 1, 0, 'a'], [34, -8, 1, 0, 'c'], [66, 12, 1, 0, '#ffd6e6'], [102, -4, 1, 1, 'a'], [140, 10, 1, 0, 'c']]), fx: '-200px', tx: '600px', ty: '-40px', dur: 17, del: -3 }],
  [7, 'glow breathe', { l: '-12%', t: '14%', w: '66%', h: '40%', c: 'b', k: '34%', dur: 6 }],
  [7, 'ring pulse', { l: '7%', t: '18%', w: '90px', h: '90px', c: '#fff0f6', k: '50%', bw: '1.4px', dur: 5 }],
  [7, 'dot rise', { l: '22%', t: '16%', s: '5px', c: 'a', bs: _scBs([[0, 0, 1, 0, 'a'], [60, 20, 1, 0, 'c'], [130, 8, 1, 1, 'a'], [200, 38, 1, 0, 'c'], [250, 14, 1, 0, 'a']]), dy: '260px', dx: '-44px', s0: '1', s1: '.8', dur: 10, del: -4 }],
]);

// ── Нефритовый Двор: пагода на фоне луны, лунные врата с тёплым светом, бамбук, золотые фонари и пыльца, нефритовый дракон, диск би за аватаром ──
_scAdd('jade', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(8,40,30,.3), transparent 38%, rgba(31,154,116,.14) 70%, rgba(20,110,84,.34))' }],
  [2, 'glow drift', { l: '-30%', b: '-4%', w: '160%', h: '44%', c: 'a', k: '28%', dx: '7%', dur: 27 }],
  [2, 'wave go i-jadeWave', { l: '0', b: '-3%', w: 'calc(100% + 150px)', h: '16%', tw: '150px', dur: 30 }],
  [3, 'glow', { l: '46%', t: '12%', w: '66%', h: '52%', c: '#fff3cf', k: '24%' }],
  [3, 'sil m i-disc', { r: '10%', t: '28%', w: '76px', h: '76px', c: '#fff6d8', c2: '#e8cf8a', gd: '160deg', o: .94 }],
  [3, 'sil i-jadeHills st', { l: '-4%', b: '12%', w: '108%', h: '26%', o: .95 }],
  [3, 'wave go i-jadeWave2', { l: '0', b: '-5%', w: 'calc(100% + 225px)', h: '13%', tw: '225px', o: .85, dur: 46 }],
  [4, 'glow pulse', { l: '0', t: '56%', w: '38%', h: '40%', c: '#ffe9a6', k: '58%', dur: 5.4 }],
  [4, 'sil i-moonGate', { l: '-6%', b: '5%', w: '52%', h: '52%', bp: '0% 100%' }],
  [4, 'sil i-pagoda', { r: '3%', b: '5%', w: '30%', h: '78%', bp: '100% 100%' }],
  [4, 'sil i-bamboo', { r: '-4%', b: '0', w: '22%', h: '52%', bp: '100% 100%' }],
  [5, 'glow', { l: '14%', t: '16%', w: '22%', h: '26%', c: '#ffe9a6', k: '34%' }],
  [5, 'sil i-hangLantern sway', { l: '20%', t: '18%', w: '8%', h: '24%', bp: '50% 0%', org: '50% 0', ang: '4deg', dur: 6 }],
  [5, 'sil i-hangLantern sway', { l: '66%', t: '14%', w: '8%', h: '24%', bp: '50% 0%', org: '50% 0', ang: '3deg', dur: 7.4, del: -3 }],
  [5, 'dot float blink', { l: '30%', t: '52%', s: '3px', c: '#ffe9a6', bs: _scBs([[0, 0, 5, 2, '#e8cf8a'], [60, -30, 5, 2, 'a'], [140, 10, 5, 2, '#e8cf8a'], [210, -44, 4, 1, 'a']]), dx: '16px', dy: '-12px', dur: 6 }],
  [5, 'dot float blink w2', { l: '60%', t: '44%', s: '3px', c: '#ffe9a6', bs: _scBs([[0, 0, 5, 2, '#e8cf8a'], [-70, 36, 5, 2, 'a'], [40, 70, 5, 2, '#e8cf8a']]), dx: '-14px', dy: '14px', dur: 7.4, del: -2.5 }],
  [5, 'ring ripple', { l: '34%', b: '3%', w: '24%', h: '5%', c: 'a', k: '70%', bw: '1.4px', dur: 6 }],
  [6, 'sil m i-dragon cross', { l: '0', t: '12%', w: '200px', h: '54px', c: '#1f9a74', c2: '#8dffd0', gd: '90deg', fx: '-220px', tx: '640px', ty: '-24px', dur: 38 }],
  [6, 'glow peek w2', { l: '40%', t: '10%', w: '60%', h: '46%', c: '#8dffd0', k: '36%', dur: 19 }],
  [7, 'ring breathe', { l: '24%', t: '24%', w: '40%', h: '46%', c: 'a', k: '16%', bw: '22px', dur: 7 }],
  [7, 'ring dash spin', { l: '15%', t: '16%', w: '60%', h: '66%', c: 'c', k: '70%', bw: '1.2px', dur: 160 }],
  [7, 'dot twinkle', { l: '16%', t: '20%', s: '3px', c: '#fff3cf', bs: _scBs([[0, 0, 5, 2, '#fff3cf'], [250, 70, 5, 2, 'c'], [120, 150, 4, 1, 'a'], [300, 30, 4, 1, '#fff3cf']]), dur: 3 }],
]);

// ── Небесное Сияние: море облаков на рассвете, мраморные колонны, перья и голуби, луч света, витражная роза за аватаром ──
_scAdd('celestial', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(20,30,70,.3), transparent 40%, rgba(255,220,143,.1) 70%, rgba(255,196,110,.3))' }],
  [2, 'sil i-clouds st', { l: '-4%', b: '-3%', w: '108%', h: '26%', o: .92 }],
  [2, 'glow drift', { l: '-30%', b: '-8%', w: '160%', h: '40%', c: 'a', k: '30%', dx: '7%', dur: 26 }],
  [3, 'glow', { l: '-10%', t: '44%', w: '120%', h: '50%', c: '#ffdc8f', k: '30%' }],
  [3, 'sil i-clouds st drift', { l: '-12%', b: '9%', w: '124%', h: '22%', o: .6, dx: '4%', dur: 46 }],
  [3, 'glow', { l: '24%', t: '-26%', w: '52%', h: '56%', c: '#fff6dd', k: '26%' }],
  [4, 'glow', { l: '-14%', t: '8%', w: '42%', h: '84%', c: '#ffdc8f', k: '20%' }],
  [4, 'sil i-column', { l: '-2%', b: '6%', w: '20%', h: '92%', bp: '0% 100%' }],
  [4, 'sil i-column fl', { r: '0', b: '6%', w: '16%', h: '66%', bp: '100% 100%', o: .85 }],
  [5, 'sil m i-feather rise', { l: '24%', t: '22%', w: '15px', h: '38px', c: '#fff6dd', c2: '#ffdc8f', gd: '160deg', rot: '24deg', dx: '30px', dy: '130px', s0: '1', s1: '1', dur: 11 }],
  [5, 'sil m i-feather rise', { l: '72%', t: '16%', w: '13px', h: '34px', c: '#fff6dd', c2: '#82c9ff', gd: '160deg', rot: '-30deg', dx: '-26px', dy: '150px', s0: '1', s1: '1', dur: 14, del: -5 }],
  [5, 'sil m i-feather rise w2', { l: '50%', t: '8%', w: '12px', h: '30px', c: '#fff6dd', c2: '#ffdc8f', gd: '160deg', rot: '10deg', dx: '16px', dy: '140px', s0: '1', s1: '1', dur: 16, del: -9 }],
  [5, 'dot twinkle', { l: '14%', t: '30%', s: '3px', c: '#fff6dd', bs: _scBs([[0, 0, 5, 2, '#fff6dd'], [250, 20, 5, 2, '#ffdc8f'], [120, -70, 4, 1, '#82c9ff'], [310, 90, 4, 1, '#fff6dd']]), dur: 3.2 }],
  [5, 'glow pulse', { l: '36%', t: '-12%', w: '28%', h: '30%', c: '#fff6dd', k: '40%', dur: 5 }],
  [6, 'sil m i-doves cross', { l: '0', t: '14%', w: '130px', h: '60px', c: '#fff6dd', c2: '#ffffff', gd: '90deg', fx: '-160px', tx: '560px', ty: '-30px', dur: 34 }],
  [6, 'sil m i-doves cross w2', { l: '0', t: '40%', w: '90px', h: '42px', c: '#ffe9c0', c2: '#ffffff', gd: '90deg', fx: '560px', tx: '-160px', ty: '20px', dur: 41, del: -17 }],
  [6, 'glow peek', { l: '34%', t: '-12%', w: '32%', h: '116%', c: '#fff6dd', k: '58%', dur: 18 }],
  [6, 'glow flash', { l: '20%', t: '-20%', w: '60%', h: '50%', c: '#ffdc8f', k: '56%', dur: 23, del: -10 }],
  [7, 'sil m i-rose spin', { l: 'calc(50% - 135px)', t: 'calc(50% - 135px)', w: '270px', h: '270px', c: '#ffdc8f', c2: '#82c9ff', gd: '160deg', o: .32, dur: 160 }],
  [7, 'ring pulse', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: '#fff6dd', k: '40%', bw: '1.3px', dur: 6 }],
]);

// ── Рубиновый Собор: алый неф со стрельчатыми окнами, лучи витражей, подсвечники и кадила, живые свечи, вспышка за стеклом, затмение с короной за аватаром ──
_scAdd('ruby', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(40,4,12,.4), transparent 36%, rgba(179,18,47,.18) 68%, rgba(100,8,26,.42))' }],
  [7, 'glow breathe', { l: 'calc(50% - 175px)', t: 'calc(50% - 189px)', w: '350px', h: '350px', c: '#ff2a4a', k: '44%', dur: 7 }],
  [7, 'sil m i-corona sway', { l: 'calc(50% - 170px)', t: 'calc(50% - 184px)', w: '340px', h: '340px', c: '#e8324f', c2: '#ffb0b8', gd: '160deg', o: .62, ang: '2.5deg', dur: 11, cr: [22, 2, 325, 269] }],
  [7, 'sil m i-disc', { l: 'calc(50% - 86px)', t: 'calc(50% - 100px)', w: '172px', h: '172px', c: '#06010a', o: .97 }],
  [2, 'glow breathe', { l: '-14%', b: '-24%', w: '128%', h: '56%', c: 'a', k: '40%', dur: 6 }],
  [2, 'band shimmer', { l: '16%', b: '6%', w: '68%', h: '16px', bg: 'radial-gradient(closest-side, rgba(255,170,160,.32), transparent)', dx: '16px', dur: 4.2 }],
  [3, 'sil i-nave st', { l: '0', t: '0', w: '50%', h: '100%' }],
  [3, 'sil i-nave st fl', { r: '0', t: '0', w: '50%', h: '100%' }],
  [3, 'glow', { l: '-1%', t: '11%', w: '20%', h: '32%', c: '#ff4a64', k: '46%' }],
  [3, 'glow', { r: '-1%', t: '11%', w: '20%', h: '32%', c: '#ff9a5a', k: '40%' }],
  [3, 'glow sway', { l: '-5%', t: '12%', w: '13%', h: '120%', c: '#ff4a64', k: '30%', rot: '-28deg', org: '50% 0', ang: '2.5deg', dur: 10 }],
  [3, 'glow sway', { r: '-5%', t: '12%', w: '13%', h: '120%', c: '#ff9a5a', k: '26%', rot: '28deg', org: '50% 0', ang: '2.5deg', dur: 13, del: -5 }],
  [4, 'sil i-candelabra', { l: '7%', b: '3%', w: '17%', h: '46%' }],
  [4, 'sil i-candelabra fl', { r: '7%', b: '3%', w: '17%', h: '46%' }],
  [4, 'sil i-censer sway', { l: '19%', t: '0%', w: '40px', h: '150px', bp: '50% 0%', org: '50% 0', ang: '3.5deg', dur: 7 }],
  [4, 'sil i-censer sway', { r: '19%', t: '0%', w: '40px', h: '150px', bp: '50% 0%', org: '50% 0', ang: '3deg', dur: 8.4, del: -3 }],
  [5, 'sil i-flames pulse', { l: '7%', b: '3%', w: '17%', h: '46%', dur: 1.7 }],
  [5, 'sil i-flames fl pulse', { r: '7%', b: '3%', w: '17%', h: '46%', dur: 2.3, del: -1 }],
  [5, 'dot rise', { l: '15.4%', t: '54.5%', s: '2px', c: '#ffd9a0', bs: _scBs([[0, 0, 3, 1, '#ffd27a'], [-22, 24, 3, 1, 'a'], [10, -24, 3, 1, '#ffd27a'], [-14, -52, 2, 1, 'a'], [22, -80, 2, 1, '#ffd27a']]), dx: '8px', dy: '-90px', dur: 5 }],
  [5, 'dot rise', { l: '84.6%', t: '54.5%', s: '2px', c: '#ffd9a0', bs: _scBs([[0, 0, 3, 1, '#ffd27a'], [22, 24, 3, 1, 'a'], [-10, -24, 3, 1, '#ffd27a'], [14, -52, 2, 1, 'a'], [-22, -80, 2, 1, '#ffd27a']]), dx: '-8px', dy: '-90px', dur: 6.1, del: -2.3 }],
  [5, 'glow rise w2', { l: '20.8%', t: '20%', w: '26px', h: '34px', c: '#e0b8c0', k: '34%', dy: '-70px', dx: '10px', s0: '.6', s1: '2.2', dur: 6 }],
  [5, 'glow rise w2', { r: '20.8%', t: '20%', w: '26px', h: '34px', c: '#e0b8c0', k: '30%', dy: '-70px', dx: '-10px', s0: '.6', s1: '2.2', dur: 7.2, del: -3 }],
  [6, 'glow flash', { l: '-12%', t: '4%', w: '124%', h: '44%', c: '#ffc8d4', k: '44%', dur: 17 }],
  [6, 'glow peek', { l: '36%', t: '-14%', w: '28%', h: '120%', c: '#ffe1b0', k: '46%', dur: 21, del: -8 }],
]);

// ── Лазурная Обсерватория: купол с открытой щелью, небо с туманностью, орбиты планет, армиллярная сфера и оррери, созвездие, метеорный дождь, газовый гигант за краем купола ──
_scAdd('observatory', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(4,10,40,.4), transparent 40%, rgba(42,86,201,.16) 72%, rgba(224,184,106,.2))' }],
  [3, 'glow drift', { l: '-10%', t: '-12%', w: '80%', h: '60%', c: 'b', k: '46%', dx: '8%', dur: 24 }],
  [3, 'glow drift', { l: '40%', t: '4%', w: '70%', h: '56%', c: '#7a4acd', k: '30%', dx: '8%', dur: 31, del: -12 }],
  [3, 'band', { l: '-10%', t: '26%', w: '120%', h: '34%', bg: 'radial-gradient(closest-side, rgba(170,200,255,.2), transparent)', rot: '-22deg' }],
  [3, 'dot twinkle', { l: '30%', t: '8%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [170, 22, 4, 1, 'a'], [-30, 70, 4, 1, '#fff'], [210, -4, 4, 1, 'c'], [90, 130, 4, 1, 'a']]), dur: 3.1 }],
  [7, 'glow breathe', { l: '11.5%', t: '12.4%', w: '130px', h: '130px', c: '#7fb2ff', k: '36%', dur: 8 }],
  [7, 'sil i-gasGiant', { l: '18.1%', t: '19.8%', w: '79px', h: '79px' }],
  [7, 'sil m i-orbits spin rev', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#7fb2ff', c2: '#e0b86a', gd: '20deg', o: .34, dur: 150, cr: [22, 22, 358, 358] }],
  [5, 'sil m i-orbits spin', { l: 'calc(50% - 230px)', t: 'calc(50% - 230px)', w: '460px', h: '460px', c: 'c', c2: 'a', gd: '160deg', o: .5, dur: 220, cr: [27, 27, 433, 433] }],
  [5, 'sil m i-constellation pulse', { l: '72%', t: '46%', w: '60px', h: '60px', c: 'c', c2: '#fff1c8', gd: '160deg', o: .9, dur: 4 }],
  [6, 'band sweep', { l: '0', t: '4%', w: '120px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(166,200,255,.7) 70%, #fff)', bs: '0 0 8px 2px rgba(127,178,255,.7)', rot: '22deg', fx: '-60px', tx: '430px', ty: '180px', dur: 9 }],
  [6, 'band sweep', { l: '0', t: '2%', w: '100px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(255,226,170,.7) 70%, #fff)', bs: '0 0 8px 2px rgba(224,184,106,.7)', rot: '160deg', fx: '460px', tx: '-60px', ty: '190px', dur: 13, del: -5 }],
  [6, 'band sweep w2', { l: '0', t: '20%', w: '80px', h: '1.5px', bg: 'linear-gradient(90deg, transparent, rgba(166,200,255,.7) 70%, #fff)', bs: '0 0 6px 1px rgba(127,178,255,.7)', rot: '24deg', fx: '-40px', tx: '420px', ty: '200px', dur: 17, del: -9 }],
  [3, 'sil i-domeShell st', { l: '0', t: '0', w: '100%', h: '100%' }],
  [2, 'glow breathe', { l: '-14%', b: '-24%', w: '128%', h: '54%', c: 'c', k: '34%', dur: 6 }],
  [2, 'band shimmer', { l: '16%', b: '6%', w: '68%', h: '16px', bg: 'radial-gradient(closest-side, rgba(255,226,170,.3), transparent)', dx: '16px', dur: 4.6 }],
  [4, 'sil i-armillary', { l: '6%', b: '8%', w: '22%', h: '44%', bp: '50% 100%' }],
  [4, 'sil i-orrery', { r: '6%', b: '7%', w: '24%', h: '36%', bp: '50% 100%' }],
  [5, 'dot twinkle', { l: '5.1%', t: '21.6%', s: '3px', c: '#fff1c8', bs: _scBs([[0, 0, 5, 2, '#fff1c8'], [52, 68, 5, 2, 'c'], [26, 152, 4, 1, '#fff1c8']]), dur: 3.6 }],
  [5, 'glow pulse', { l: '11.3%', t: '65.7%', w: '44px', h: '44px', c: '#7fb2ff', k: '60%', dur: 3.4 }],
  [5, 'glow pulse', { l: '77.7%', t: '73.8%', w: '40px', h: '40px', c: '#ffd27a', k: '56%', dur: 4.2, del: -1.6 }],
]);

// ── Золотой Лотос: храмовый пруд на рассвете, дальний берег и золотой храм, лотосы и цапля, плавучие фонарики, блики на воде, журавли в небе, лотосовая мандала за аватаром ──
_scAdd('lotus_gold', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(60,20,10,.34), transparent 38%, rgba(255,210,122,.1) 62%, rgba(224,138,74,.26))' }],
  [7, 'sil m i-mandala spin', { l: 'calc(50% - 160px)', t: 'calc(50% - 160px)', w: '320px', h: '320px', c: '#ffd27a', c2: '#e08a4a', gd: '160deg', o: .3, dur: 200 }],
  [3, 'glow drift', { l: '-20%', t: '-24%', w: '90%', h: '56%', c: 'c', k: '34%', dx: '8%', dur: 26 }],
  [3, 'glow drift w2', { l: '30%', t: '-16%', w: '80%', h: '50%', c: 'a', k: '30%', dx: '8%', dur: 33, del: -11 }],
  [3, 'glow breathe', { l: '36%', t: '30%', w: '80%', h: '38%', c: '#ffe9b0', k: '40%', dur: 9 }],
  [3, 'sil i-shore st', { l: '-4%', b: '39%', w: '108%', h: '18%', o: .95 }],
  [4, 'sil i-temple', { r: '1%', b: '39%', w: '33%', h: '34%', bp: '100% 100%' }],
  [2, 'band', { l: '0', t: '59%', w: '100%', h: '41%', bg: 'linear-gradient(180deg, transparent, rgba(255,210,122,.14) 18%, rgba(224,138,74,.1) 50%, rgba(50,20,6,.2))' }],
  [2, 'wave go i-goldWave', { l: '0', b: '-3%', w: 'calc(100% + 150px)', h: '16%', tw: '150px', dur: 30 }],
  [3, 'wave go w2 i-goldWave2', { l: '0', b: '-5%', w: 'calc(100% + 225px)', h: '13%', tw: '225px', o: .85, dur: 46 }],
  [3, 'glow shimmer', { l: '66%', t: '60%', w: '34%', h: '24%', c: '#ffd27a', k: '30%', dx: '6px', dur: 3.8 }],
  [4, 'sil i-crane', { l: '16%', b: '27%', w: '13%', h: '32%', bp: '50% 100%' }],
  [4, 'sil i-lotusPlants', { l: '-4%', b: '-1%', w: '34%', h: '62%', bp: '0% 100%' }],
  [4, 'sil i-lotusPlants fl', { r: '-3%', b: '-1%', w: '22%', h: '46%', bp: '0% 100%' }],
  [5, 'sil i-waterLantern float', { r: '11%', b: '30%', w: '30px', h: '26px', dx: '8px', dy: '-3px', dur: 9 }],
  [5, 'sil i-waterLantern float', { r: '27%', b: '26%', w: '24px', h: '21px', dx: '-6px', dy: '-3px', dur: 12, del: -5 }],
  [5, 'dot float blink', { l: '26%', t: '52%', s: '3px', c: '#fff1c8', bs: _scBs([[0, 0, 5, 2, '#ffd27a'], [150, -22, 5, 2, 'a'], [96, 40, 4, 1, '#ffd27a']]), dx: '14px', dy: '-10px', dur: 5 }],
  [5, 'ring ripple', { l: '70%', t: '72%', w: '18%', h: '4%', c: 'c', k: '70%', bw: '1.4px', dur: 6 }],
  [5, 'ring ripple', { l: '20%', t: '80%', w: '18%', h: '4%', c: 'a', k: '70%', bw: '1.4px', dur: 7.4, del: -3 }],
  [5, 'dot twinkle', { l: '22%', t: '66%', s: '3px', c: '#fff1c8', bs: _scBs([[0, 0, 4, 1, '#fff1c8'], [150, 18, 4, 1, 'a'], [44, 34, 3, 1, '#fff1c8'], [250, -6, 4, 1, 'c'], [110, 56, 3, 1, 'a']]), dur: 2.8 }],
  [6, 'sil m i-craneFly cross', { l: '0', t: '14%', w: '110px', h: '54px', c: '#fff1c8', c2: '#ffd27a', gd: '90deg', fx: '-130px', tx: '520px', ty: '-26px', dur: 36 }],
  [6, 'sil m i-craneFly cross w2', { l: '0', t: '30%', w: '72px', h: '36px', c: '#ffe9f0', c2: '#ffd27a', gd: '90deg', fx: '-90px', tx: '480px', ty: '20px', dur: 44, del: -19 }],
  [6, 'glow peek', { l: '30%', t: '-14%', w: '40%', h: '120%', c: '#ffe9b0', k: '40%', dur: 19 }],
  [7, 'ring pulse', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: '#ffd27a', k: '40%', bw: '1.3px', dur: 6 }],
]);

// ── Skins V3 · сцены образов S, SS и SSS: Бездна, Северное Сияние, Расплавленное Солнце, Лепестковый Вихрь, Артефакт, Лунный Лотос, Прилив Рюдзина, Полуночная Комета, Хроно-ткач, Сердце Звезды ──
// Движок, словарь слоёв и правила лежат в app.35.js (_scAdd, _scBs); картинки-силуэты рисует tools/scene_art_c.py (skin-scene-c-v3.css).

// ── Бездна: воронка с пылью, дуги линзирования, обломки и разорванная планета, пояса обломков по орбитам, струя, падение света, кольцо Эйнштейна ──
_scAdd('void', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 50% 50%, rgba(2,0,10,.5) 0, rgba(2,0,10,.3) 22%, transparent 64%), linear-gradient(180deg, rgba(20,6,50,.4), transparent 44%, rgba(90,44,217,.22))' }],
  [7, 'glow breathe', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: 'a', k: '34%', dur: 7 }],
  [2, 'glow drift', { l: '-30%', b: '-14%', w: '160%', h: '52%', c: 'b', k: '38%', dx: '7%', dur: 26 }],
  [2, 'dot', { l: '8%', t: '20%', s: '2px', c: '#fff', bs: _scBs([[0, 0, 1, 0, '#fff'], [62, 140, 1, 0, 'c'], [118, 40, 1, 0, '#fff'], [206, 118, 1, 0, 'a'], [266, 20, 1, 0, '#fff'], [304, 196, 1, 0, 'c'], [20, 220, 1, 0, '#fff'], [158, 232, 1, 0, 'a']]) }],
  [3, 'glow drift', { l: '38%', t: '-18%', w: '90%', h: '60%', c: 'c', k: '28%', dx: '8%', dur: 33, del: -12 }],
  [3, 'sil m i-spiral spin rev', { l: 'calc(50% - 215px)', t: 'calc(50% - 215px)', w: '430px', h: '430px', c: 'b', c2: 'c', gd: '160deg', o: .3, dur: 260 }],
  [3, 'dot twinkle', { l: '16%', t: '12%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [220, 40, 4, 1, 'c'], [60, 150, 4, 1, 'a'], [250, 170, 4, 1, '#fff']]), dur: 3.2 }],
  [4, 'sil i-rubble', { l: '-2%', t: '26%', w: '26%', h: '44%', bp: '0% 50%' }],
  [4, 'sil i-rubble fl', { r: '-2%', t: '48%', w: '24%', h: '38%', bp: '0% 50%' }],
  [4, 'sil i-shredded', { l: '4%', t: '8%', w: '42%', h: '30%', bp: '0% 0%' }],
  [5, 'sil m i-lensArcs spin', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: '#ff7ad9', c2: '#cf74ff', gd: '160deg', o: .55, dur: 90, cr: [17, 19, 323, 326] }],
  [5, 'dot spin', { l: 'calc(50% - 1.5px)', t: 'calc(50% - 1.5px)', s: '3px', c: '#ffb0ec', bs: _scBs([[105, 0, 3, 1, '#ffb0ec'], [91, 52, 3, 1, 'a'], [52, 91, 3, 1, '#ffb0ec'], [-20, 103, 3, 1, 'c'], [-72, 77, 3, 1, '#ffb0ec'], [-100, 28, 3, 1, 'a'], [-95, -45, 3, 1, '#ffb0ec'], [-40, -97, 3, 1, 'c'], [28, -101, 3, 1, '#ffb0ec'], [86, -60, 3, 1, 'a']]), dur: 70 }],
  [5, 'dot spin rev', { l: 'calc(50% - 2px)', t: 'calc(50% - 2px)', s: '4px', c: '#fff', bs: _scBs([[132, 0, 4, 1, '#fff'], [66, 114, 4, 1, 'c'], [-66, 114, 4, 1, '#fff'], [-132, 0, 4, 1, 'a'], [-66, -114, 4, 1, '#fff'], [66, -114, 4, 1, 'c']]), dur: 130 }],
  [6, 'sil m i-jet peek', { l: 'calc(50% - 50px)', t: '-6%', w: '100px', h: '60%', bp: '50% 100%', c: '#ff7ad9', c2: '#ffffff', gd: '0deg', o: .9, dur: 17 }],
  [6, 'sil m i-spiral rise', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: '#ffd0f4', c2: '#cf74ff', gd: '160deg', o: .8, dx: '0px', dy: '0px', s0: '1.5', s1: '.35', dur: 9, del: -3 }],
  [6, 'glow flash', { l: '-10%', t: '-10%', w: '120%', h: '60%', c: '#e8d0ff', k: '40%', dur: 21 }],
  [7, 'ring pulse', { l: 'calc(50% - 112px)', t: 'calc(50% - 112px)', w: '224px', h: '224px', c: '#ff7ad9', k: '70%', bw: '2px', dur: 6 }],
  [7, 'ring dash spin rev', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: '#cf74ff', k: '60%', bw: '1.2px', dur: 150 }],
]);

// ── Северное Сияние: занавеси полярного света над ледяными горами, лес и волк, ледяные искры, вспышка и корона сияния ──
_scAdd('aurora', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(2,10,16,.45), transparent 40%, rgba(123,240,200,.08) 68%, rgba(200,255,240,.2))' }],
  [3, 'glow', { l: '10%', t: '-20%', w: '80%', h: '60%', c: 'a', k: '22%' }],
  [7, 'sil m i-auroraCrown breathe', { l: 'calc(50% - 230px)', t: '-22%', w: '460px', h: '307px', bp: '50% 0%', c: '#9affd8', c2: '#a06cff', gd: '180deg', o: .8, dur: 12, cr: [42, 10, 409, 307] }],
  [3, 'sil m i-curtain sway', { l: '-14%', t: '-2%', w: '76%', h: '56%', c: '#7bf0c8', c2: '#8a7cff', gd: '0deg', o: .85, ang: '2deg', org: '50% 100%', dur: 14 }],
  [3, 'sil m i-curtain2 drift', { l: '38%', t: '-8%', w: '78%', h: '58%', c: '#a8ffd8', c2: '#e070ff', gd: '0deg', o: .7, dx: '6%', dur: 19, del: -6 }],
  [3, 'dot twinkle', { l: '22%', t: '8%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [200, 60, 4, 1, 'a'], [90, 140, 4, 1, '#fff'], [250, 20, 4, 1, 'c']]), dur: 3.4 }],
  [2, 'sil i-snowRange st', { l: '-4%', b: '-2%', w: '108%', h: '42%' }],
  [2, 'glow breathe', { l: '-14%', b: '-26%', w: '128%', h: '54%', c: 'c', k: '30%', dur: 7 }],
  [2, 'band shimmer', { l: '14%', b: '6%', w: '72%', h: '12px', bg: 'radial-gradient(closest-side, rgba(200,255,240,.34), transparent)', dx: '14px', dur: 4.4 }],
  [4, 'sil i-icePines', { l: '-5%', b: '-2%', w: '36%', h: '66%', bp: '0% 100%' }],
  [4, 'sil i-icePines fl', { r: '-8%', b: '-2%', w: '22%', h: '46%', bp: '0% 100%' }],
  [4, 'sil i-wolf', { r: '11%', b: '1%', w: '22%', h: '40%', bp: '50% 100%' }],
  [5, 'dot twinkle', { l: '20%', t: '72%', s: '2px', c: '#fff', bs: _scBs([[0, 0, 4, 1, '#fff'], [60, 20, 4, 1, 'a'], [150, -8, 3, 1, '#fff'], [230, 24, 4, 1, 'c'], [300, 4, 3, 1, '#fff']]), dur: 2.7 }],
  [5, 'dot rise', { l: '12%', t: '-4%', s: '2px', c: '#dff4ff', bs: _scBs([[0, 0, 1, 0, '#dff4ff'], [90, 40, 1, 0, '#fff'], [170, 8, 1, 1, '#dff4ff'], [250, 60, 1, 0, '#fff'], [310, 16, 1, 0, '#dff4ff']]), dy: '300px', dx: '-20px', s0: '1', s1: '1', dur: 12 }],
  [6, 'band cross', { l: '0', t: '6%', w: '130px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(123,240,200,.7) 70%, #fff)', bs: '0 0 8px 2px rgba(123,240,200,.7)', rot: '16deg', fx: '-150px', tx: '540px', ty: '130px', dur: 19 }],
  [6, 'glow flash', { l: '-10%', t: '-10%', w: '120%', h: '70%', c: 'a', k: '56%', dur: 16 }],
  [7, 'glow breathe', { l: '10%', b: '-10%', w: '80%', h: '34%', c: 'a', k: '34%', dur: 8 }],
]);

// ── Расплавленное Солнце: корка с золотыми трещинами и поток золота, протуберанцы по бокам, брызги, вспышка с ударной волной, корона из лучей ──
_scAdd('solar', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(60,20,4,.4), transparent 40%, rgba(255,106,26,.22) 74%, rgba(255,196,71,.34))' }],
  [7, 'glow breathe', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'a', k: '36%', dur: 6 }],
  [7, 'sil m i-sunRays spin', { l: 'calc(50% - 175px)', t: 'calc(50% - 175px)', w: '350px', h: '350px', c: '#ffc447', c2: '#ff6a1a', gd: '160deg', o: .45, dur: 180, cr: [32, 23, 335, 266] }],
  [2, 'glow breathe', { l: '-14%', b: '-24%', w: '128%', h: '58%', c: 'b', k: '58%', dur: 4.6 }],
  [3, 'glow drift', { l: '-30%', t: '-26%', w: '120%', h: '54%', c: 'b', k: '40%', dx: '8%', dur: 22 }],
  [3, 'glow drift w2', { l: '34%', t: '-30%', w: '84%', h: '66%', c: 'c', k: '24%', dx: '8%', dur: 28, del: -9 }],
  [3, 'band shimmer', { l: '6%', t: '66%', w: '88%', h: '14px', bg: 'radial-gradient(closest-side, rgba(255,220,150,.28), transparent)', dx: '14px', dur: 3 }],
  [4, 'sil m i-prominence sway', { l: '-4%', b: '15%', w: '34%', h: '46%', c: '#ff6a1a', c2: '#ffc447', gd: '0deg', bp: '0% 100%', o: .9, ang: '1.5deg', org: '50% 100%', dur: 9 }],
  [4, 'sil m i-prominence fl', { r: '-4%', b: '15%', w: '30%', h: '40%', c: '#ff6a1a', c2: '#ffc447', gd: '0deg', bp: '0% 100%', o: .85 }],
  [3, 'sil i-crust st', { l: '-4%', b: '5%', w: '108%', h: '36%' }],
  [2, 'wave go i-goldFlow', { l: '0', b: '-3%', w: 'calc(100% + 140px)', h: '16%', tw: '140px', dur: 26 }],
  [5, 'dot rise', { l: '14%', t: '62%', s: '2px', c: '#ffe9a6', bs: _scBs([[0, 0, 3, 1, 'a'], [14, -22, 3, 1, '#ffd27a'], [-12, -46, 3, 1, 'a'], [20, -70, 3, 1, '#ffd27a'], [-6, -96, 2, 1, 'a']]), dx: '26px', dy: '-110px', dur: 4.6 }],
  [5, 'dot rise', { l: '84%', t: '64%', s: '2px', c: '#ffe9a6', bs: _scBs([[0, 0, 3, 1, 'a'], [-16, -20, 3, 1, '#ffd27a'], [10, -44, 3, 1, 'a'], [-18, -68, 3, 1, '#ffd27a']]), dx: '-22px', dy: '-100px', dur: 5.8, del: -2.4 }],
  [5, 'glow rise w2', { l: '6%', t: '40%', w: '18%', h: '24%', c: '#ff8a3a', k: '34%', dy: '-70px', dx: '14px', s0: '.6', s1: '1.9', dur: 8 }],
  [6, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#ffd27a', k: '60%', bw: '2px', dur: 9 }],
  [6, 'glow flash', { l: '-10%', t: '30%', w: '60%', h: '40%', c: '#fff0c2', k: '60%', dur: 13 }],
  [6, 'glow peek', { l: '60%', t: '-10%', w: '40%', h: '50%', c: '#ffe9a6', k: '56%', dur: 15, del: -6 }],
]);

// ── Лепестковый Вихрь: грозовое небо над садом, ворота тории вдали, ветви сакуры по бокам, смерч лепестков, порыв ветра, молния, огромный цветок ──
_scAdd('sakura_storm', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 50% 46%, transparent 30%, rgba(14,2,24,.5) 100%), linear-gradient(180deg, rgba(90,24,100,.3), transparent 42%, rgba(255,158,196,.1))' }],
  [2, 'glow drift', { l: '-20%', t: '-24%', w: '90%', h: '56%', c: 'b', k: '44%', dx: '8%', dur: 24 }],
  [3, 'glow drift', { l: '34%', t: '-18%', w: '86%', h: '50%', c: '#7a2a8c', k: '40%', dx: '8%', dur: 31, del: -11 }],
  [3, 'sil i-toriiFar', { l: '3%', b: '11%', w: '17%', h: '26%', o: .8, bp: '50% 100%' }],
  [7, 'sil m i-stormBloom spin', { l: 'calc(50% - 165px)', t: 'calc(50% - 165px)', w: '330px', h: '330px', c: '#ffc2da', c2: '#c06bd6', gd: '160deg', o: .5, dur: 160, cr: [12, 15, 318, 306] }],
  [4, 'sil i-branchL', { l: '-4%', t: '18%', w: '44%', h: '42%', bp: '0% 0%' }],
  [4, 'sil i-branchR', { r: '-5%', t: '32%', w: '34%', h: '36%', bp: '100% 0%' }],
  [5, 'sil i-petalVortex spin', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', dur: 80 }],
  [5, 'dot rise', { l: '10%', t: '86%', s: '3px', c: '#ffb0cf', bs: _scBs([[0, 0, 2, 1, '#ffb0cf'], [40, -34, 2, 1, '#fff0f7'], [84, 6, 2, 1, '#ff8fbb'], [128, -22, 2, 1, '#ffb0cf']]), dx: '90px', dy: '-170px', s0: '1', s1: '1.4', dur: 6.4 }],
  [5, 'dot rise', { l: '62%', t: '92%', s: '3px', c: '#ffb0cf', bs: _scBs([[0, 0, 2, 1, '#fff0f7'], [-50, -40, 2, 1, '#ffb0cf'], [64, -12, 2, 1, '#ff8fbb'], [120, -50, 2, 1, '#fff0f7']]), dx: '-100px', dy: '-190px', s0: '1', s1: '1.5', dur: 7.8, del: -3 }],
  [6, 'sil i-gust cross w2', { l: '0', t: '30%', w: '200px', h: '60px', rot: '-8deg', fx: '-220px', tx: '600px', ty: '-40px', dur: 8, del: -2, cr: [0, 7, 200, 56] }],
  [6, 'sil i-stormBolt flash', { l: '72%', t: '-4%', w: '12%', h: '62%', bp: '50% 0%', dur: 11, del: -3 }],
  [6, 'glow flash', { l: '30%', t: '-20%', w: '100%', h: '70%', c: '#c06bd6', k: '60%', dur: 11, del: -3 }],
  [6, 'sil i-petalVortex spin rev', { l: 'calc(50% - 235px)', t: 'calc(50% - 235px)', w: '470px', h: '470px', o: .4, dur: 130 }],
  [3, 'band', { l: '16%', t: '62%', w: '68%', h: '36%', bg: 'radial-gradient(closest-side, rgba(20,4,30,.82), rgba(20,4,30,.5) 58%, transparent)' }],
  [7, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#ffb0cf', k: '70%', bw: '2px', dur: 7 }],
  [7, 'glow breathe', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: '#ff9ec4', k: '30%', dur: 6 }],
]);

// ── Артефакт: трещины реальности, пилоны и строчки данных, шестигранное силовое кольцо, дроны-разведчики, сбой картинки, прицельные уголки и осколки ──
_scAdd('artifact', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 50% 50%, rgba(6,40,56,.5), transparent 60%), linear-gradient(180deg, rgba(0,12,20,.5), transparent 40%, rgba(42,156,255,.12))' }],
  [2, 'glow breathe', { l: '-10%', b: '-24%', w: '120%', h: '50%', c: 'a', k: '26%', dur: 7 }],
  [3, 'band', { l: '0', t: '0', w: '100%', h: '100%', o: .5, bg: 'repeating-linear-gradient(0deg, rgba(0,0,0,.22) 0 1px, transparent 1px 3px)' }],
  [5, 'sil m i-fracture pulse', { l: 'calc(50% - 200px)', t: 'calc(50% - 200px)', w: '400px', h: '400px', c: 'a', c2: 'b', gd: '160deg', o: .85, dur: 5 }],
  [3, 'sil i-pylons', { l: '-2%', b: '-3%', w: '26%', h: '74%', bp: '0% 100%' }],
  [3, 'sil i-pylons fl', { r: '-2%', b: '-3%', w: '22%', h: '60%', bp: '0% 100%' }],
  [3, 'glow drift', { l: '-20%', t: '10%', w: '90%', h: '60%', c: 'b', k: '22%', dx: '8%', dur: 26 }],
  [4, 'sil m i-hexRing spin', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'a', o: .8, dur: 110, cr: [31, 31, 349, 349] }],
  [4, 'dot rise', { l: '12%', t: '-6%', s: '3px', c: '#62f2e2', bs: _scBs([[0, 0, 3, 0, '#62f2e2'], [0, 22, 3, 0, '#c8fff8'], [0, 50, 3, 0, '#62f2e2'], [0, 84, 3, 0, '#2a9cff'], [16, -6, 3, 0, '#c8fff8'], [16, 30, 3, 0, '#62f2e2']]), dy: '330px', dx: '0px', s0: '1', s1: '1', dur: 5.4 }],
  [4, 'dot rise', { l: '86%', t: '-6%', s: '3px', c: '#62f2e2', bs: _scBs([[0, 0, 3, 0, '#c8fff8'], [0, 30, 3, 0, '#62f2e2'], [0, 66, 3, 0, '#2a9cff'], [-14, 14, 3, 0, '#62f2e2'], [-14, 52, 3, 0, '#c8fff8']]), dy: '330px', dx: '0px', s0: '1', s1: '1', dur: 6.6, del: -2.8 }],
  [5, 'sil m i-drone spin', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: '#c8fff8', o: .95, dur: 38, cr: [113, 3, 187, 50] }],
  [6, 'sil m i-drone spin rev w2', { l: 'calc(50% - 180px)', t: 'calc(50% - 180px)', w: '360px', h: '360px', c: '#62f2e2', o: .85, dur: 52, cr: [136, 4, 224, 60] }],
  [6, 'band flash', { l: '0', t: '38%', w: '100%', h: '7px', bg: 'linear-gradient(90deg, transparent 0, rgba(255,61,138,.55) 22%, rgba(98,242,226,.75) 55%, rgba(42,156,255,.5) 78%, transparent)', dur: 9, del: -2 }],
  [6, 'band flash', { l: '0', t: '58%', w: '100%', h: '4px', bg: 'linear-gradient(90deg, transparent 10%, rgba(98,242,226,.7) 40%, rgba(255,61,138,.5) 70%, transparent)', dur: 13, del: -7 }],
  [6, 'band flash w2', { l: '0', t: '22%', w: '100%', h: '10px', bg: 'linear-gradient(90deg, transparent 0, rgba(42,156,255,.5) 30%, rgba(200,255,248,.6) 60%, transparent)', dur: 11, del: -5 }],
  [6, 'band sweep', { l: '0', t: '0', w: '100%', h: '3px', bg: 'linear-gradient(90deg, transparent, rgba(98,242,226,.7) 20%, rgba(200,255,248,.9) 50%, rgba(98,242,226,.7) 80%, transparent)', bs: '0 0 10px 2px rgba(98,242,226,.5)', fx: '0px', tx: '0px', ty: '340px', dur: 12 }],
  [6, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'a', k: '70%', bw: '1.5px', dur: 6 }],
  [7, 'sil m i-brackets pulse st', { l: '6%', t: '20%', w: '88%', h: '74%', c: 'a', o: .9, dur: 3 }],
  [7, 'sil m i-chips float', { l: 'calc(50% - 200px)', t: 'calc(50% - 200px)', w: '400px', h: '400px', c: '#c8fff8', o: .9, dx: '8px', dy: '-10px', dur: 14, cr: [70, 34, 371, 387] }],
  [7, 'glow breathe', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: 'a', k: '24%', dur: 5 }],
]);

// ── Лунный Лотос: ночной пруд под лунным серпом, далёкий берег в дымке, тростник, цапля, листья и жемчужные лотосы, светляки, круги на воде, журавли, кольцо из лепестков ──
_scAdd('moon_lotus', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 66% 32%, rgba(228,236,255,.1), transparent 46%), linear-gradient(180deg, rgba(4,8,22,.4), transparent 40%, rgba(147,169,238,.08))' }],
  [7, 'sil m i-lotusHalo breathe', { l: 'calc(50% - 200px)', t: 'calc(50% - 200px)', w: '400px', h: '400px', c: '#e4ecff', c2: '#93a9ee', gd: '180deg', o: .55, dur: 9 }],
  [2, 'band', { l: '-6%', t: '73%', w: '112%', h: '30%', bg: 'linear-gradient(180deg, rgba(150,170,230,0), rgba(30,48,98,.55) 18%, rgba(8,14,34,.82))' }],
  [3, 'glow breathe', { l: 'calc(50% - 35px)', t: 'calc(50% - 161px)', w: '200px', h: '200px', c: '#e4ecff', k: '34%', dur: 8 }],
  [3, 'sil i-moonHills st', { l: '-4%', t: '66%', w: '108%', h: '9%' }],
  [3, 'glow drift', { l: '-30%', t: '60%', w: '160%', h: '24%', c: '#c9d6ff', k: '22%', dx: '7%', dur: 30 }],
  [3, 'dot twinkle', { l: '14%', t: '10%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [120, 36, 4, 1, 'a'], [230, 14, 4, 1, '#fff'], [60, 110, 4, 1, 'b']]), dur: 3.4 }],
  [2, 'glow shimmer', { l: 'calc(50% + 40px)', t: '74%', w: '50px', h: '22%', c: '#e4ecff', k: '50%', dx: '5px', dur: 3.4 }],
  [4, 'sil i-moonCloud drift w2', { l: 'calc(50% + 10px)', t: '26%', w: '260px', h: '35px', o: .7, dx: '10%', dur: 34, cr: [1, 8, 259, 30] }],
  [4, 'sil i-heron', { r: '8%', b: '11%', w: '14%', h: '36%', bp: '50% 100%' }],
  [4, 'sil i-moonReeds sway', { l: '-3%', b: '-3%', w: '26%', h: '70%', bp: '0% 100%', ang: '1.5deg', org: '50% 100%', dur: 7 }],
  [4, 'sil i-moonReeds fl', { r: '-3%', b: '-3%', w: '22%', h: '56%', bp: '0% 100%' }],
  [4, 'sil i-moonPads st', { l: '-4%', b: '-2%', w: '108%', h: '19%' }],
  [4, 'sil i-pearlLotus', { l: '6%', b: '4%', w: '18%', h: '24%' }],
  [5, 'dot blink float', { l: '24%', t: '64%', c: '#f6f2c0', bs: _scBs([[0, 0, 6, 2, '#f6f2c0'], [60, 18, 5, 2, '#f6f2c0'], [150, -10, 6, 2, '#e4ecff']]), dur: 4.6 }],
  [5, 'dot blink float', { l: '58%', t: '70%', c: '#f6f2c0', bs: _scBs([[0, 0, 6, 2, '#f6f2c0'], [-50, 22, 5, 2, '#e4ecff'], [70, 10, 6, 2, '#f6f2c0']]), dur: 5.8, del: -2 }],
  [5, 'ring ripple', { l: '8%', t: '82%', w: '110px', h: '26px', c: '#e4ecff', k: '60%', bw: '1px', dur: 7 }],
  [5, 'ring ripple', { l: '66%', t: '88%', w: '90px', h: '20px', c: '#e4ecff', k: '60%', bw: '1px', dur: 7, del: -3.5 }],
  [6, 'sil i-moonCranes cross w2', { l: '0', t: '14%', w: '110px', h: '40px', o: .9, fx: '-130px', tx: '560px', ty: '-30px', dur: 34, del: -8 }],
  [6, 'band cross', { l: '0', t: '8%', w: '110px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(228,236,255,.7) 70%, #fff)', bs: '0 0 8px 2px rgba(228,236,255,.6)', rot: '18deg', fx: '-130px', tx: '520px', ty: '150px', dur: 21, del: -5 }],
  [7, 'ring dash spin', { l: 'calc(50% - 165px)', t: 'calc(50% - 165px)', w: '330px', h: '330px', c: '#e4ecff', k: '55%', bw: '1px', dur: 160 }],
  [7, 'dot rise', { l: '30%', t: '80%', s: '4px', c: '#fff', bs: _scBs([[0, 0, 6, 2, '#e4ecff'], [90, 20, 6, 2, '#fff'], [170, -6, 6, 2, '#93a9ee'], [220, 26, 6, 2, '#e4ecff']]), dx: '10px', dy: '-120px', s0: '1', s1: '1.2', dur: 7 }],
]);

// ── Прилив Рюдзина: толща моря со столбами света, дворец на дне, водоросли, пузыри, косяк карпов, дракон вокруг аватара и две жемчужины прилива ──
_scAdd('ryujin_tide', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(0,22,30,.5), transparent 40%, rgba(233,196,93,.08) 78%, rgba(0,12,16,.5))' }],
  [3, 'sil m i-shafts sway', { l: 'calc(50% - 230px)', t: '-14%', w: '460px', h: '460px', bp: '50% 0%', c: '#8fe9ff', c2: '#52e6cc', gd: '180deg', o: .4, ang: '3deg', org: '50% 0%', dur: 12 }],
  [3, 'sil m i-shafts sway w2', { l: 'calc(50% - 150px)', t: '-14%', w: '300px', h: '300px', bp: '50% 0%', c: '#8fe9ff', c2: '#52e6cc', gd: '180deg', o: .3, ang: '4deg', org: '50% 0%', dur: 17, del: -6 }],
  [2, 'glow breathe', { l: '-14%', b: '-24%', w: '128%', h: '54%', c: 'b', k: '28%', dur: 7 }],
  [3, 'sil i-palaceGate', { l: '-3%', b: '4%', w: '28%', h: '50%', o: .75, bp: '50% 100%' }],
  [3, 'sil i-palaceGate fl', { r: '-3%', b: '4%', w: '24%', h: '42%', o: .75, bp: '50% 100%' }],
  [4, 'sil i-kelp sway', { l: '-4%', b: '-3%', w: '22%', h: '66%', bp: '0% 100%', ang: '2deg', org: '50% 100%', dur: 6 }],
  [4, 'sil i-kelp fl', { r: '-4%', b: '-3%', w: '20%', h: '56%', bp: '0% 100%' }],
  [3, 'dot rise', { l: '10%', t: '92%', s: '3px', c: '#c8fbff', bs: _scBs([[0, 0, 1, 1, '#c8fbff'], [18, -26, 1, 0, '#fff'], [-8, -60, 1, 1, '#c8fbff'], [24, -96, 1, 0, '#fff']]), dx: '16px', dy: '-250px', s0: '1', s1: '1.3', dur: 7 }],
  [5, 'dot rise', { l: '84%', t: '96%', s: '4px', c: '#c8fbff', bs: _scBs([[0, 0, 1, 1, '#c8fbff'], [-20, -34, 1, 0, '#fff'], [10, -70, 1, 1, '#c8fbff'], [-14, -112, 1, 0, '#fff']]), dx: '-18px', dy: '-270px', s0: '1', s1: '1.3', dur: 8.6, del: -3 }],
  [5, 'band shimmer', { l: '0', t: '14%', w: '100%', h: '18px', bg: 'radial-gradient(closest-side, rgba(143,233,255,.25), transparent)', dx: '20px', dur: 5 }],
  [5, 'dot twinkle', { l: '18%', t: '44%', s: '3px', c: '#fff3c0', bs: _scBs([[0, 0, 5, 2, '#e9c45d'], [190, -36, 4, 1, '#fff3c0'], [120, 50, 5, 2, '#52e6cc'], [250, 30, 4, 1, '#e9c45d']]), dur: 3.8 }],
  [6, 'sil i-koiShoal cross w2', { l: '0', t: '40%', w: '120px', h: '42px', o: .9, fx: '-140px', tx: '560px', ty: '-24px', dur: 38, del: -10 }],
  [6, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'b', k: '60%', bw: '2px', dur: 8 }],
  [7, 'sil i-seaDragon spin', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', dur: 150, cr: [45, 32, 316, 340] }],
  [3, 'band', { l: '16%', t: '62%', w: '68%', h: '36%', bg: 'radial-gradient(closest-side, rgba(2,16,20,.82), rgba(2,16,20,.5) 58%, transparent)' }],
  [7, 'dot spin', { l: 'calc(50% - 5px)', t: 'calc(50% - 5px)', s: '10px', c: 'transparent', bs: _scBs([[104, 0, 9, 4, '#8fe9ff'], [104, 0, 0, 0, '#ffffff']]), dur: 40 }],
  [7, 'dot spin rev', { l: 'calc(50% - 5px)', t: 'calc(50% - 5px)', s: '10px', c: 'transparent', bs: _scBs([[-122, 0, 9, 4, '#e9c45d'], [-122, 0, 0, 0, '#fff3c0']]), dur: 56 }],
  [7, 'glow breathe', { l: 'calc(50% - 160px)', t: 'calc(50% - 160px)', w: '320px', h: '320px', c: 'a', k: '24%', dur: 6 }],
]);

// ── Полуночная Комета: Млечный Путь, большая комета с золотым пылевым и синим ионным хвостом, холмы с наблюдателем, пыль и метеоры, малая комета, комета на орбите ──
_scAdd('midnight_comet', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 50% 50%, transparent 30%, rgba(2,4,14,.55) 100%)' }],
  [2, 'glow drift', { l: '-20%', t: '-20%', w: '80%', h: '60%', c: 'b', k: '18%', dx: '8%', dur: 30 }],
  [3, 'sil i-milkyWay st', { l: '-6%', t: '-6%', w: '112%', h: '112%', o: .9 }],
  [3, 'glow drift w2', { l: '40%', t: '30%', w: '80%', h: '60%', c: '#7a5cff', k: '14%', dx: '8%', dur: 38, del: -14 }],
  [3, 'dot twinkle', { l: '12%', t: '14%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [210, 52, 4, 1, 'a'], [96, 150, 4, 1, '#fff'], [250, 20, 4, 1, 'b']]), dur: 3.6 }],
  [4, 'sil i-greatComet', { l: '-178px', t: '62px', w: '520px', h: '140px', bp: '100% 50%', o: .9, rot: '-6deg', org: '470px 56px' }],
  [4, 'sil i-hillL', { l: '-3%', b: '-3%', w: '44%', h: '46%', bp: '0% 100%' }],
  [4, 'sil i-hillR', { r: '-3%', b: '-3%', w: '38%', h: '34%', bp: '100% 100%' }],
  [5, 'glow breathe', { l: 'calc(50% + 57px)', t: 'calc(50% - 96px)', w: '80px', h: '80px', c: '#cfe4ff', k: '40%', dur: 6 }],
  [5, 'dot rise', { l: '70%', t: '31%', s: '2px', c: '#cfe4ff', bs: _scBs([[0, 0, 1, 0, '#cfe4ff'], [-46, 8, 1, 0, '#fff0c8'], [-96, 14, 1, 0, '#cfe4ff'], [-150, 24, 1, 0, '#fff0c8'], [-210, 28, 1, 0, '#cfe4ff']]), dx: '-60px', dy: '10px', s0: '1', s1: '1', dur: 9 }],
  [5, 'band cross', { l: '0', t: '8%', w: '120px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(207,228,255,.7) 70%, #fff)', bs: '0 0 8px 2px rgba(207,228,255,.6)', rot: '20deg', fx: '-140px', tx: '540px', ty: '190px', dur: 23 }],
  [6, 'sil i-miniComet cross w2', { l: '0', t: '58%', w: '120px', h: '24px', o: .95, rot: '-12deg', fx: '-140px', tx: '560px', ty: '-120px', dur: 31, del: -9 }],
  [6, 'glow flash', { l: '30%', t: '6%', w: '50%', h: '30%', c: '#cfe4ff', k: '60%', dur: 17 }],
  [7, 'dot spin', { l: 'calc(50% - 1px)', t: 'calc(50% - 1px)', s: '2px', c: 'transparent', bs: _scBs([[150, 0, 7, 3, '#ffffff'], [149, -13, 3, 1.5, 'rgba(207,228,255,0.67)'], [148, -25, 3, 1.3, 'rgba(207,228,255,0.59)'], [145, -37, 3, 1.1, 'rgba(207,228,255,0.51)'], [142, -49, 3, 0.9, 'rgba(207,228,255,0.43)'], [137, -61, 3, 0.7, 'rgba(207,228,255,0.35)'], [131, -72, 3, 0.5, 'rgba(207,228,255,0.27)'], [125, -83, 3, 0.3, 'rgba(207,228,255,0.19)'], [118, -93, 3, 0.2, 'rgba(207,228,255,0.11)']]), dur: 80 }],
  [7, 'glow breathe', { l: 'calc(50% - 160px)', t: 'calc(50% - 160px)', w: '320px', h: '320px', c: '#cfe4ff', k: '14%', dur: 8 }],
]);

// ── Хроно-ткач: шестерни в глубине, маятник и песочные часы, циферблат со стрелками, нити времени, пульс времени ──
_scAdd('chrono', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 50% 46%, transparent 34%, rgba(10,6,0,.55) 100%), linear-gradient(180deg, rgba(40,28,6,.3), transparent 40%, rgba(47,183,168,.08))' }],
  [2, 'glow breathe', { l: '-10%', b: '-22%', w: '120%', h: '48%', c: 'a', k: '24%', dur: 8 }],
  [3, 'sil m i-gearBrass spin', { l: '-92px', t: '4px', w: '300px', h: '300px', c: '#c9a14a', c2: '#6b4a1e', gd: '160deg', o: .5, dur: 140 }],
  [3, 'sil m i-gearBrass spin rev', { l: '270px', t: '140px', w: '260px', h: '260px', c: '#c9a14a', c2: '#6b4a1e', gd: '160deg', o: .45, dur: 110 }],
  [4, 'sil m i-gearSmall spin', { l: '20px', t: '246px', w: '90px', h: '90px', c: '#2fb7a8', c2: '#0b4a44', gd: '160deg', o: .7, dur: 30 }],
  [4, 'sil m i-gearSmall spin rev w2', { l: '300px', t: '70px', w: '80px', h: '80px', c: '#e8c36a', c2: '#6b4a1e', gd: '160deg', o: .65, dur: 24 }],
  [4, 'sil m i-pendulum sway', { l: '82%', t: '-12%', w: '60px', h: '220px', bp: '50% 0%', c: '#e8c36a', c2: '#a8832e', gd: '180deg', o: .85, ang: '12deg', org: '50% 0%', dur: 2.6, cr: [6, 0, 54, 218] }],
  [4, 'sil i-hourglass', { l: '4%', t: '34%', w: '52px', h: '92px', bp: '50% 100%', o: .95 }],
  [6, 'sil m i-threads drift st w2', { l: '-6%', t: '56%', w: '112%', h: '36%', c: '#e8c36a', o: .38, dx: '5%', dur: 22 }],
  [3, 'band', { l: '16%', t: '62%', w: '68%', h: '36%', bg: 'radial-gradient(closest-side, rgba(10,6,0,.82), rgba(10,6,0,.5) 58%, transparent)' }],
  [5, 'sil m i-clockDial spin', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#e8c36a', o: .6, dur: 240 }],
  [5, 'dot rise', { l: '41px', t: '163px', s: '2px', c: '#e8c36a', bs: _scBs([[0, 0, 1, 0, '#e8c36a'], [0, -8, 1, 0, '#fff3cf'], [0, -16, 1, 0, '#e8c36a']]), dx: '0px', dy: '24px', s0: '1', s1: '1', dur: 1.1 }],
  [5, 'dot twinkle', { l: '22%', t: '16%', s: '3px', c: '#fff3cf', bs: _scBs([[0, 0, 5, 2, '#e8c36a'], [200, 24, 4, 1, '#2fb7a8'], [110, 130, 5, 2, '#fff3cf'], [260, 90, 4, 1, '#e8c36a']]), dur: 3.4 }],
  [6, 'sil m i-handHour spin w2', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#e8c36a', o: .7, dur: 480, cr: [179, 70, 201, 142] }],
  [6, 'sil m i-handMinute spin', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#f0d58a', o: .7, dur: 40, cr: [181, 12, 199, 111] }],
  [6, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'a', k: '60%', bw: '2px', dur: 9 }],
  [7, 'sil m i-clockDial spin rev', { l: 'calc(50% - 235px)', t: 'calc(50% - 235px)', w: '470px', h: '470px', c: '#2fb7a8', o: .32, dur: 420 }],
  [7, 'dot spin', { l: 'calc(50% - 3px)', t: 'calc(50% - 3px)', s: '6px', c: '#fff3cf', bs: '0 -158px 0 0 #fff3cf, 0 -158px 12px 4px rgba(232,195,106,.8)', dur: 16 }],
  [7, 'glow breathe', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: 'a', k: '22%', dur: 6 }],
]);

// ── Сердце Звезды: пульс сердца и кольца-эхо, оболочка сверхновой, столбы газа с молодыми звёздами, звёздный крест, рождение звёзд ──
_scAdd('starheart', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'radial-gradient(circle at 50% 50%, rgba(255,111,176,.16), transparent 52%), radial-gradient(circle at 50% 50%, transparent 36%, rgba(14,2,20,.5) 100%)' }],
  [2, 'glow drift', { l: '-30%', b: '-14%', w: '110%', h: '60%', c: 'b', k: '30%', dx: '7%', dur: 24 }],
  [3, 'glow drift', { l: '34%', t: '-22%', w: '90%', h: '56%', c: '#8a3dff', k: '24%', dx: '8%', dur: 30, del: -12 }],
  [3, 'sil m i-nebulaShell spin', { l: 'calc(50% - 200px)', t: 'calc(50% - 200px)', w: '400px', h: '400px', c: '#ff6fb0', c2: '#fff0b0', gd: '160deg', o: .5, dur: 220 }],
  [3, 'dot twinkle', { l: '16%', t: '12%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [220, 40, 4, 1, 'b'], [70, 150, 4, 1, 'a'], [250, 170, 4, 1, '#fff']]), dur: 3.2 }],
  [4, 'sil i-gasPillar', { l: '-4%', b: '-3%', w: '34%', h: '76%', bp: '0% 100%' }],
  [4, 'sil i-gasPillar fl', { r: '-4%', b: '-3%', w: '28%', h: '62%', bp: '0% 100%' }],
  [5, 'glow beat', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: 'b', k: '36%', dur: 3.2 }],
  [5, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'b', k: '70%', bw: '2px', dur: 3.2 }],
  [5, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'a', k: '60%', bw: '1.5px', dur: 3.2, del: -1.6 }],
  [5, 'dot rise', { l: '24%', t: '88%', s: '2px', c: '#fff0b0', bs: _scBs([[0, 0, 3, 1, 'a'], [34, -20, 3, 1, 'b'], [70, 6, 3, 1, 'a'], [120, -14, 3, 1, '#fff'], [170, 8, 3, 1, 'b']]), dx: '16px', dy: '-200px', s0: '1', s1: '1.2', dur: 6 }],
  [6, 'sil m i-starFlare spin', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: '#fff0b0', c2: '#ff6fb0', gd: '160deg', o: .5, dur: 120, cr: [2, 2, 338, 246] }],
  [6, 'sil i-sparklesA twinkle st', { l: '0', t: '0', w: '100%', h: '100%', dur: 4.2, cr: [0.043, 0.123, 0.441, 0.743] }],
  [6, 'sil i-sparklesB twinkle st', { l: '0', t: '0', w: '100%', h: '100%', dur: 5, del: -2.4, cr: [0.145, 0.298, 0.796, 0.81] }],
  [6, 'glow flash', { l: '20%', t: '6%', w: '60%', h: '50%', c: '#fff0b0', k: '60%', dur: 15 }],
  [7, 'ring ripple', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: '#fff0b0', k: '60%', bw: '1.5px', dur: 3.2, del: -.8 }],
  [7, 'sil m i-starFlare spin rev', { l: 'calc(50% - 230px)', t: 'calc(50% - 230px)', w: '460px', h: '460px', c: '#ff6fb0', c2: '#fff0b0', gd: '160deg', o: .3, dur: 180, cr: [4, 4, 456, 332] }],
  [7, 'glow breathe', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: '#fff0b0', k: '20%', dur: 6 }],
]);

// ── Skins V3 · сцены сезонных и личных образов: Тыквенный Фонарь, Паутина Полуночи, Час Ведьм, Снежный Шар, Огни Гирлянды, Бой Курантов, Алая Звезда, Багровый Мрак ──
// Движок, словарь слоёв и правила лежат в app.35.js (_scAdd, _scBs); картинки-силуэты рисует tools/scene_art_d.py (skin-scene-d-v3.css).

// Предмет у правого края сцены держится края, а на узком экране (уже 390 px) уходит за край на половину нехватки: башня и ёлка не ложатся на ник.
const _scEdge = px => `calc(${px}px - max(0px, 390px - 100%) / 2)`;

// ── Тыквенный Фонарь: сумерки над тыквенным полем, жатвенная луна за мёртвым деревом, резные фонари и пугало, летучие мыши, привидение и огромное пламя свечи за аватаром ──
_scAdd('pumpkin_lantern', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(64,20,120,.62), rgba(110,36,70,.2) 44%, rgba(255,130,40,.16) 74%, rgba(36,10,3,.5))' }],
  [2, 'glow drift', { l: '-30%', b: '6%', w: '160%', h: '34%', c: 'b', k: '30%', dx: '7%', dur: 26 }],
  [3, 'glow breathe', { l: '230px', t: '48px', w: '180px', h: '180px', c: 'c', k: '34%', dur: 9 }],
  [3, 'dot', { l: '268px', t: '86px', s: '64px', c: '#ffd9a0', bs: '0 0 30px 10px rgba(255,190,110,.42), inset -9px -6px 14px rgba(214,120,40,.5)' }],
  [3, 'band drift', { l: '38%', t: '24%', w: '70%', h: '9%', bg: 'radial-gradient(closest-side, rgba(58,20,92,.6), transparent)', dx: '12%', dur: 32 }],
  [3, 'dot twinkle', { l: '9%', t: '20%', s: '2px', c: '#fff3d6', bs: _scBs([[0, 0, 4, 1, '#fff3d6'], [70, 26, 3, 1, '#fff3d6'], [150, -8, 3, 1, 'c'], [206, 34, 3, 1, '#fff3d6']]), dur: 3.4 }],
  [7, 'sil m i-flame breathe', { l: 'calc(50% - 150px)', t: 'calc(50% - 190px)', w: '300px', h: '360px', c: '#ff6a1a', c2: '#ffd27a', gd: '180deg', o: .5, org: '50% 100%', dur: 3.4, cr: [37, 16, 281, 354] }],
  [7, 'sil m i-flame sway', { l: 'calc(50% - 100px)', t: 'calc(50% - 128px)', w: '200px', h: '240px', c: '#ffa23a', c2: '#fff0b0', gd: '180deg', o: .4, ang: '2.5deg', org: '50% 100%', dur: 2.6, cr: [24, 10, 188, 237] }],
  [4, 'sil i-deadTree', { r: '-6%', b: '4%', w: '52%', h: '84%', bp: '100% 100%' }],
  [2, 'sil i-patch st', { l: '-4%', b: '-1%', w: '108%', h: '35%' }],
  [3, 'band', { l: '16%', t: '62%', w: '68%', h: '36%', bg: 'radial-gradient(closest-side, rgba(18,6,2,.85), rgba(18,6,2,.5) 58%, transparent)' }],
  [4, 'sil i-jackBig', { l: '-7%', b: '1%', w: '46%', h: '54%', bp: '0% 100%' }],
  [4, 'sil i-pumpkinPair', { r: '-6%', b: '1%', w: '46%', h: '54%', bp: '100% 100%' }],
  [4, 'glow pulse', { l: '-20px', t: '236px', w: '130px', h: '100px', c: 'a', k: '36%', dur: 2.4 }],
  [4, 'glow pulse', { l: '290px', t: '280px', w: '110px', h: '70px', c: 'a', k: '36%', dur: 3.1, del: -1 }],
  [5, 'dot rise', { l: '62px', t: '236px', s: '3px', c: '#ffd27a', bs: _scBs([[0, 0, 3, 1, 'a'], [12, -14, 3, 1, '#ffd27a'], [-10, -30, 3, 1, 'a'], [16, -52, 2, 1, '#ffd27a']]), dx: '16px', dy: '-120px', dur: 5.2 }],
  [5, 'dot rise', { l: '338px', t: '270px', s: '3px', c: '#ffd27a', bs: _scBs([[0, 0, 3, 1, 'a'], [-12, -16, 3, 1, '#ffd27a'], [10, -34, 3, 1, 'a']]), dx: '-14px', dy: '-110px', dur: 6.4, del: -2 }],
  [5, 'sil m i-bats cross', { l: '0', t: '14%', w: '86px', h: '52px', c: '#0e0614', o: .95, fx: '-100px', tx: '520px', ty: '-30px', dur: 22 }],
  [6, 'sil m i-ghost cross w2', { l: '0', t: '36%', w: '48px', h: '60px', c: '#fff2d6', c2: '#ffb978', gd: '180deg', o: .5, fx: '-70px', tx: '470px', ty: '-30px', dur: 34 }],
  [6, 'glow flash', { l: '-10%', b: '-10%', w: '120%', h: '60%', c: '#ff9a3c', k: '40%', dur: 13 }],
  [7, 'dot rise', { l: 'calc(50% - 90px)', t: '70%', s: '3px', c: '#ffd27a', bs: _scBs([[0, 0, 3, 1, 'a'], [-14, -22, 3, 1, '#ffd27a'], [10, -46, 3, 1, 'a'], [-8, -72, 2, 1, '#ffd27a']]), dx: '-10px', dy: '-150px', dur: 4.4 }],
  [7, 'dot rise', { l: 'calc(50% + 86px)', t: '66%', s: '3px', c: '#ffd27a', bs: _scBs([[0, 0, 3, 1, '#ffd27a'], [14, -20, 3, 1, 'a'], [-8, -44, 3, 1, '#ffd27a'], [10, -68, 2, 1, 'a']]), dx: '12px', dy: '-150px', dur: 5.2, del: -2 }],
]);

// ── Паутина Полуночи: затмение над садом, серебряные нити, ветви с паутиной в углах, паук на нити, мотылёк, падающая искра и огромная паутина вокруг аватара ──
_scAdd('cobweb', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(34,22,86,.55), transparent 44%, rgba(80,60,170,.2) 76%, rgba(10,8,30,.5))' }],
  [2, 'glow drift', { l: '-30%', b: '4%', w: '160%', h: '36%', c: 'b', k: '30%', dx: '7%', dur: 27 }],
  [3, 'glow breathe', { l: '252px', t: '52px', w: '120px', h: '120px', c: 'c', k: '46%', dur: 7 }],
  [3, 'dot', { l: '279px', t: '79px', s: '66px', c: '#05030d', bs: '0 0 0 2px rgba(241,236,255,.78), 0 0 22px 7px rgba(203,184,255,.55)' }],
  [3, 'dot', { l: '331px', t: '86px', s: '5px', c: '#fff', bs: '0 0 10px 4px rgba(255,255,255,.85), 0 0 22px 8px rgba(203,184,255,.6)' }],
  [3, 'dot twinkle', { l: '22%', t: '14%', s: '2px', c: '#fff', bs: _scBs([[0, 0, 4, 1, '#fff'], [90, 44, 3, 1, 'c'], [150, -6, 3, 1, '#fff'], [230, 38, 3, 1, 'a']]), dur: 3.6 }],
  [3, 'sil m i-silk sway', { l: '25%', t: '-3%', w: '90px', h: '174px', c: 'a', o: .55, ang: '1.4deg', org: '50% 0', dur: 9, cr: [6, 0, 82, 167] }],
  [7, 'glow breathe', { l: 'calc(50% - 190px)', t: 'calc(50% - 190px)', w: '380px', h: '380px', c: 'a', k: '26%', dur: 7 }],
  [7, 'sil m i-orbWeb sway', { l: 'calc(50% - 200px)', t: 'calc(50% - 200px)', w: '400px', h: '400px', c: '#f1ecff', c2: '#9a86ff', gd: '160deg', o: .5, ang: '.8deg', dur: 12 }],
  [2, 'sil i-dryGrass st', { l: '-4%', b: '-1%', w: '108%', h: '31%' }],
  [2, 'dot', { l: '6%', b: '5%', s: '2px', c: '#e8e0ff', bs: _scBs([[0, 0, 1, 0, '#e8e0ff'], [52, 8, 1, 0, 'c'], [118, -4, 1, 0, '#e8e0ff'], [262, 6, 1, 0, 'c'], [318, -2, 1, 0, '#e8e0ff'], [352, 9, 1, 0, 'c']]) }],
  [3, 'band', { l: '16%', t: '62%', w: '68%', h: '36%', bg: 'radial-gradient(closest-side, rgba(10,8,28,.82), rgba(10,8,28,.5) 58%, transparent)' }],
  [4, 'sil i-webBranchL', { l: '-4%', t: '-2%', w: '46%', h: '56%', bp: '0% 0%' }],
  [4, 'sil i-webBranchR', { r: '-4%', t: '18%', w: '44%', h: '50%', bp: '100% 0%' }],
  [4, 'dot twinkle', { l: '38px', t: '65px', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [64, 9, 5, 2, '#fff']]), dur: 3.1 }],
  [4, 'dot twinkle', { l: '358px', t: '126px', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [-58, 8, 5, 2, '#fff']]), dur: 3.9, del: -1.6 }],
  [5, 'sil m i-spiderThread float', { l: '4%', t: '-12%', w: '44px', h: '140px', c: '#e8e0ff', o: .92, dx: '0px', dy: '30px', dur: 9 }],
  [5, 'dot float blink', { l: '70%', t: '58%', s: '3px', c: '#e8e0ff', bs: _scBs([[0, 0, 5, 2, 'a'], [-120, 34, 5, 2, '#e8e0ff'], [-60, -50, 5, 2, 'a']]), dx: '14px', dy: '-12px', dur: 6 }],
  [6, 'sil m i-moth cross w2', { l: '0', t: '40%', w: '40px', h: '28px', c: '#d9ccff', o: .85, fx: '-60px', tx: '470px', ty: '-60px', dur: 26 }],
  [6, 'band cross', { l: '0', t: '8%', w: '130px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(203,184,255,.7) 70%, #fff)', bs: '0 0 8px 2px rgba(203,184,255,.7)', rot: '16deg', fx: '-150px', tx: '540px', ty: '130px', dur: 19 }],
  [6, 'glow flash', { l: '40%', t: '-24%', w: '80%', h: '64%', c: 'c', k: '44%', dur: 15 }],
  [7, 'dot twinkle', { l: 'calc(50% - 1.5px)', t: 'calc(50% - 1.5px)', s: '3px', c: '#fff', bs: _scBs(Array.from({ length: 9 }, (_, k) => [Math.round(128 * Math.cos(k * 2.4)), Math.round(128 * Math.sin(k * 2.4)), 4, 1, k % 2 ? 'c' : 'a'])), dur: 3.3 }],
]);

// ── Час Ведьм: вихрь туч над крышами, башня ведьмы и кривой дом, чёрная кошка, летучие мыши, дым и огоньки, молния и зелёная комета, кольцо рун вокруг аватара ──
_scAdd('witch_hour', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(44,12,100,.58), rgba(70,20,120,.16) 44%, rgba(40,180,90,.12) 74%, rgba(4,10,6,.6))' }],
  [2, 'glow drift', { l: '-30%', b: '4%', w: '160%', h: '36%', c: 'a', k: '24%', dx: '7%', dur: 25 }],
  [3, 'glow breathe', { l: '-10%', t: '-24%', w: '90%', h: '60%', c: 'b', k: '36%', dur: 9 }],
  [3, 'sil m i-witchSwirl spin rev', { l: 'calc(50% - 240px)', t: 'calc(50% - 240px)', w: '480px', h: '480px', c: '#9a55ff', c2: '#2fd47a', gd: '160deg', o: .4, dur: 200, cr: [13, 3, 448, 424] }],
  [3, 'dot twinkle', { l: '12%', t: '12%', s: '2px', c: '#e8ffe8', bs: _scBs([[0, 0, 4, 1, '#e8ffe8'], [90, 40, 3, 1, 'c'], [160, -4, 3, 1, '#e8ffe8'], [250, 30, 3, 1, 'a']]), dur: 3.3 }],
  [4, 'sil i-witchTower', { l: '-2%', b: '7%', w: '30%', h: '74%', bp: '0% 100%' }],
  [4, 'sil i-crookedHouse', { r: '-3%', b: '7%', w: '38%', h: '62%', bp: '100% 100%' }],
  [2, 'sil i-roofs st', { l: '-4%', b: '-1%', w: '108%', h: '34%' }],
  [3, 'band', { l: '16%', t: '62%', w: '68%', h: '36%', bg: 'radial-gradient(closest-side, rgba(6,3,12,.85), rgba(6,3,12,.5) 58%, transparent)' }],
  [4, 'glow pulse', { l: '19px', t: '211px', w: '60px', h: '60px', c: 'a', k: '46%', dur: 3.4 }],
  [4, 'glow pulse', { l: '281px', t: '245px', w: '60px', h: '50px', c: 'c', k: '46%', dur: 2.8, del: -1 }],
  [5, 'sil i-blackCat', { l: '324px', t: '122px', w: '30px', h: '30px', bp: '50% 100%' }],
  [5, 'dot blink', { l: '338px', t: '132px', s: '2px', c: '#b6ffc0', bs: _scBs([[0, 0, 3, 1, 'a'], [5, 0, 3, 1, 'a']]), dur: 4.6 }],
  [5, 'glow rise', { l: '346px', t: '140px', w: '30px', h: '40px', c: 'a', k: '24%', dy: '-70px', dx: '-14px', s0: '.6', s1: '1.8', dur: 6 }],
  [5, 'glow rise w2', { l: '346px', t: '140px', w: '26px', h: '36px', c: 'b', k: '26%', dy: '-60px', dx: '-8px', s0: '.6', s1: '1.9', dur: 7.4, del: -3 }],
  [5, 'sil m i-bats cross', { l: '0', t: '16%', w: '80px', h: '48px', c: '#0c0618', o: .95, fx: '-100px', tx: '520px', ty: '40px', dur: 24, del: -8 }],
  [5, 'dot float blink', { l: '30%', t: '58%', s: '3px', c: '#c8ffd0', bs: _scBs([[0, 0, 6, 2, 'a'], [-66, 20, 5, 2, '#c8ffd0'], [100, 8, 5, 2, 'a']]), dx: '14px', dy: '-12px', dur: 5.4 }],
  [6, 'sil m i-witchBolt flash', { l: '66%', t: '-4%', w: '10%', h: '62%', bp: '50% 0%', c: '#eaffe6', o: .95, dur: 11, del: -3 }],
  [6, 'glow flash', { l: '30%', t: '-20%', w: '100%', h: '70%', c: '#9a55ff', k: '56%', dur: 11, del: -3 }],
  [6, 'band cross w2', { l: '0', t: '10%', w: '140px', h: '2px', bg: 'linear-gradient(90deg, transparent, rgba(141,255,156,.75) 70%, #fff)', bs: '0 0 8px 2px rgba(141,255,156,.7)', rot: '14deg', fx: '-150px', tx: '540px', ty: '120px', dur: 21 }],
  [7, 'glow breathe', { l: 'calc(50% - 150px)', t: 'calc(50% - 150px)', w: '300px', h: '300px', c: 'a', k: '22%', dur: 6 }],
  [7, 'sil m i-runeRing spin', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: '#8dff9c', c2: '#ffd36b', gd: '160deg', o: .75, dur: 120 }],
  [7, 'sil m i-runeRing spin rev w2', { l: 'calc(50% - 124px)', t: 'calc(50% - 124px)', w: '248px', h: '248px', c: '#b98cff', c2: '#8dff9c', gd: '20deg', o: .5, dur: 80 }],
]);

// ── Снежный Шар: ночной городок в стеклянном шаре: церковь и дома под снегом, ели, фонарь со снеговиком, луна, снегопад, сани над крышами, вихрь снега и блик стекла ──
_scAdd('snow_globe', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(14,26,62,.62), rgba(34,62,124,.18) 44%, rgba(120,170,235,.12) 74%, rgba(6,12,28,.5))' }],
  [2, 'glow drift', { l: '-30%', b: '4%', w: '160%', h: '36%', c: 'b', k: '30%', dx: '7%', dur: 27 }],
  [2, 'sil i-snowTown st', { l: '-4%', b: '-1%', w: '108%', h: '33%' }],
  [2, 'band', { l: '12%', t: '75%', w: '66%', h: '25%', bg: 'radial-gradient(closest-side, rgba(8,14,34,.9), rgba(8,14,34,.55) 62%, transparent)' }],
  [3, 'glow breathe', { l: '246px', t: '-36px', w: '190px', h: '190px', c: 'c', k: '26%', dur: 10 }],
  [3, 'dot', { l: '312px', t: '30px', s: '58px', c: 'radial-gradient(circle at 63% 61%, rgba(120,150,205,.4) 0 8%, transparent 9%), radial-gradient(circle at 36% 42%, rgba(120,150,205,.32) 0 6%, transparent 7%), radial-gradient(circle at 70% 30%, rgba(120,150,205,.26) 0 4.5%, transparent 5.5%), radial-gradient(circle at 34% 30%, #fff, #d9e8fc 62%, #a7c2ec)', bs: '0 0 26px 8px rgba(190,224,255,.34)' }],
  [3, 'dot twinkle', { l: '9%', t: '8%', s: '2px', c: '#fff', bs: _scBs([[0, 0, 4, 1, '#fff'], [88, 30, 3, 1, 'a'], [150, -4, 3, 1, '#fff'], [214, 22, 3, 1, '#fff']]), dur: 3.4 }],
  [4, 'sil i-snowFir', { l: '-5%', b: '5%', w: '30%', h: '72%', bp: '0% 100%' }],
  [4, 'sil i-lampPost', { r: '-2%', b: '4%', w: '14%', h: '50%', bp: '50% 100%' }],
  [4, 'glow pulse', { r: 'calc(5% - 41px)', b: 'calc(35% - 41px)', w: '82px', h: '82px', c: '#ffd27a', k: '58%', dur: 3.4 }],
  [4, 'sil i-snowman', { r: '14px', b: '3%', w: '38px', h: '62px', bp: '50% 100%' }],
  [5, 'dot rise', { l: '6%', t: '-6%', s: '4px', c: '#fff', bs: _scBs([[0, 0, 2, 1, '#fff'], [58, 40, 2, 0, '#fff'], [120, -10, 2, 1, '#fff'], [176, 60, 2, 0, '#fff'], [236, 20, 2, 1, '#fff'], [290, 52, 2, 0, '#fff'], [340, 4, 2, 1, '#fff']]), dy: '300px', dx: '26px', s0: '1', s1: '1', dur: 12 }],
  [5, 'dot rise', { l: '12%', t: '-6%', s: '2px', c: '#dff0ff', bs: _scBs([[0, 0, 1, 0, '#dff0ff'], [44, 30, 1, 0, '#fff'], [100, 8, 1, 1, '#dff0ff'], [160, 50, 1, 0, '#fff'], [214, 14, 1, 0, '#dff0ff'], [270, 40, 1, 1, '#fff'], [326, 2, 1, 0, '#dff0ff']]), dy: '300px', dx: '-22px', s0: '1', s1: '1', dur: 8, del: -3 }],
  [5, 'glow rise w2', { l: '8px', b: '36px', w: '26px', h: '34px', c: '#dff0ff', k: '26%', dy: '-60px', dx: '10px', s0: '.6', s1: '1.8', dur: 6 }],
  [5, 'glow rise w2', { r: '38px', b: '30px', w: '26px', h: '34px', c: '#dff0ff', k: '24%', dy: '-60px', dx: '-8px', s0: '.6', s1: '1.9', dur: 7.4, del: -3 }],
  [6, 'sil m i-sleigh cross w2', { l: '0', t: '24%', w: '96px', h: '36px', c: '#e8f4ff', c2: '#a8d0ff', gd: '180deg', o: .9, fx: '-110px', tx: '520px', ty: '-36px', dur: 38 }],
  [6, 'dot sweep', { l: '0', t: '46%', s: '2px', c: '#fff', bs: _scBs([[0, 0, 1, 0, '#fff'], [26, 8, 1, 0, '#fff'], [52, -4, 1, 1, '#dff0ff'], [80, 10, 1, 0, '#fff'], [108, 0, 1, 1, '#dff0ff'], [138, -6, 1, 1, '#fff'], [170, 6, 1, 0, '#dff0ff']]), fx: '-190px', tx: '560px', ty: '36px', dur: 12 }],
  [7, 'sil m i-snowSwirl spin', { l: '-64px', t: 'calc(50% + var(--bleed) / 2 - 137px)', w: '248px', h: '248px', c: '#eaf4ff', c2: '#9cc8ff', gd: '160deg', o: .45, dur: 160, cr: [26, 0, 245, 226] }],
  [7, 'sil m i-domeGlint breathe', { l: '0', t: '0', w: '100%', h: '100%', c: '#fff', c2: '#bfe4ff', gd: '135deg', o: .42, dur: 8 }],
  [7, 'dot twinkle', { l: '26%', t: '36%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [180, -34, 5, 2, '#fff'], [92, 66, 4, 1, 'a'], [236, 54, 4, 1, '#fff']]), dur: 3.1 }],
]);

// ── Огни Гирлянды: комната в сочельник: подарки под ёлкой, ёлка с шарами и бегущими огнями, замёрзшее окно со шторами, гирлянда под потолком, шары на нитях и венок из огней ──
_scAdd('garland', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(84,14,44,.5), rgba(40,10,34,.14) 42%, rgba(14,72,48,.2) 76%, rgba(8,3,8,.55))' }],
  [2, 'glow drift', { l: '-30%', b: '2%', w: '160%', h: '34%', c: 'a', k: '24%', dx: '7%', dur: 27 }],
  [2, 'sil i-giftRow st', { l: '-4%', b: '4%', w: '108%', h: '29%' }],
  [2, 'band', { l: '12%', t: '76%', w: '60%', h: '24%', bg: 'radial-gradient(closest-side, rgba(10,3,10,.85), rgba(10,3,10,.5) 62%, transparent)' }],
  [3, 'sil i-frostWindow', { r: _scEdge(12), t: '6px', w: '78px', h: '97px', bp: '100% 0%' }],
  [3, 'glow pulse', { l: '-6%', t: '-8%', w: '46%', h: '58%', c: 'a', k: '30%', dur: 5.2 }],
  [5, 'glow pulse', { r: _scEdge(2), t: '0px', w: '96px', h: '112px', c: '#ffd9a0', k: '34%', dur: 4.6 }],
  [3, 'glow pulse w2', { l: '52%', t: '30%', w: '44%', h: '60%', c: 'b', k: '22%', dur: 6.4, del: -2 }],
  [3, 'glow pulse w2', { l: '30%', t: '-14%', w: '40%', h: '46%', c: 'c', k: '20%', dur: 7.4, del: -4 }],
  [4, 'sil i-xmasTree', { r: _scEdge(-4), t: '70px', w: '70px', h: '160px', bp: '50% 100%' }],
  [4, 'sil i-swagTop st', { l: '-4%', t: '2%', w: '108%', h: '26%' }],
  [4, 'sil i-ornaments sway', { l: '6px', t: '-2px', w: '96px', h: '88px', bp: '0% 0%', ang: '2.4deg', org: '50% 0', dur: 7 }],
  [5, 'dot blink', { r: _scEdge(40), t: '126px', s: '3px', c: '#ff6b8a', bs: _scBs([[0, 0, 5, 1, '#ff6b8a'],[15, 2, 5, 1, '#ff6b8a'],[3, 26, 5, 1, '#ff6b8a'],[24, 23, 5, 1, '#ff6b8a'],[10, 51, 5, 1, '#ff6b8a'],[-10, 71, 5, 1, '#ff6b8a'],[20, 75, 5, 1, '#ff6b8a']]), dur: 2.4 }],
  [5, 'dot blink', { r: _scEdge(35), t: '128px', s: '3px', c: '#35d68a', bs: _scBs([[0, 0, 5, 1, '#35d68a'],[15, -2, 5, 1, '#35d68a'],[5, 25, 5, 1, '#35d68a'],[-13, 44, 5, 1, '#35d68a'],[14, 48, 5, 1, '#35d68a'],[-5, 72, 5, 1, '#35d68a'],[25, 69, 5, 1, '#35d68a']]), dur: 2.4, del: -0.8 }],
  [5, 'dot blink', { r: _scEdge(29), t: '129px', s: '3px', c: '#ffe9a6', bs: _scBs([[0, 0, 5, 1, '#ffe9a6'],[-14, 20, 5, 1, '#ffe9a6'],[7, 23, 5, 1, '#ffe9a6'],[-9, 47, 5, 1, '#ffe9a6'],[18, 43, 5, 1, '#ffe9a6'],[0, 73, 5, 1, '#ffe9a6']]), dur: 2.4, del: -1.6 }],
  [5, 'dot blink', { l: '-1px', t: '27px', s: '3px', c: '#ff6b8a', bs: _scBs([[0, 0, 6, 1, '#ff6b8a'],[47, 14, 6, 1, '#ff6b8a'],[94, 7, 6, 1, '#ff6b8a'],[156, 7, 6, 1, '#ff6b8a'],[203, 14, 6, 1, '#ff6b8a'],[250, 0, 6, 1, '#ff6b8a'],[312, 12, 6, 1, '#ff6b8a'],[359, 12, 6, 1, '#ff6b8a']]), dur: 2.7 }],
  [5, 'dot blink', { l: '14px', t: '34px', s: '3px', c: '#35d68a', bs: _scBs([[0, 0, 6, 1, '#35d68a'],[47, 7, 6, 1, '#35d68a'],[94, -7, 6, 1, '#35d68a'],[156, 5, 6, 1, '#35d68a'],[203, 5, 6, 1, '#35d68a'],[265, -7, 6, 1, '#35d68a'],[312, 7, 6, 1, '#35d68a'],[359, 0, 6, 1, '#35d68a']]), dur: 2.7, del: -0.9 }],
  [5, 'dot blink', { l: '30px', t: '39px', s: '3px', c: '#ffe9a6', bs: _scBs([[0, 0, 6, 1, '#ffe9a6'],[47, 0, 6, 1, '#ffe9a6'],[109, -12, 6, 1, '#ffe9a6'],[156, 2, 6, 1, '#ffe9a6'],[203, -5, 6, 1, '#ffe9a6'],[265, -5, 6, 1, '#ffe9a6'],[312, 2, 6, 1, '#ffe9a6'],[359, -12, 6, 1, '#ffe9a6']]), dur: 2.7, del: -1.8 }],
  [6, 'glow peek', { r: _scEdge(1), t: '64px', w: '60px', h: '60px', c: '#ffe9a6', k: '70%', dur: 9 }],
  [6, 'sil m i-sparkle peek', { r: _scEdge(14), t: '76px', w: '34px', h: '34px', c: '#fff', c2: '#ffe9a6', gd: '180deg', o: .95, dur: 9 }],
  [6, 'band sweep w2', { l: 'calc(100% - 92px + max(0px, 390px - 100%) / 2)', t: '8px', w: '12px', h: '88px', bg: 'linear-gradient(90deg, transparent, rgba(255,236,200,.5) 42%, rgba(255,255,255,.75) 50%, transparent)', rot: '14deg', fx: '0px', tx: '68px', ty: '0px', dur: 12 }],
  [7, 'sil m i-wreath spin', { l: 'calc(50% - 170px)', t: 'calc(50% - 170px)', w: '340px', h: '340px', c: '#ff6b8a', c2: '#ffe9a6', gd: '160deg', o: .66, dur: 90 }],
  [7, 'sil m i-wreath spin rev w2', { l: 'calc(50% - 124px)', t: 'calc(50% - 124px)', w: '248px', h: '248px', c: '#35d68a', c2: '#ffe9a6', gd: '20deg', o: .44, dur: 70 }],
  [7, 'dot twinkle', { l: '22%', t: '12%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [150, 38, 5, 2, 'b'], [214, -4, 4, 1, '#fff'], [60, 100, 4, 1, 'a']]), dur: 3.3 }],
]);

// ── Бой Курантов: полночь над старым городом: купола и крыши с тёплыми окнами, башня с часами, бокалы с золотым вином, первый салют: круглый и «ива», двенадцать ударов кругами ──
_scAdd('midnight_chimes', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(8,12,44,.6), rgba(30,24,70,.14) 44%, rgba(255,190,90,.16) 76%, rgba(44,22,4,.5))' }],
  [2, 'glow drift', { l: '-30%', b: '4%', w: '160%', h: '36%', c: 'b', k: '30%', dx: '7%', dur: 27 }],
  [2, 'sil i-cityRoofs st', { l: '-4%', b: '-1%', w: '108%', h: '33%' }],
  [2, 'band', { l: '12%', t: '75%', w: '66%', h: '25%', bg: 'radial-gradient(closest-side, rgba(6,8,24,.9), rgba(6,8,24,.55) 62%, transparent)' }],
  [3, 'glow breathe', { l: '22%', t: '-34%', w: '80%', h: '74%', c: 'a', k: '24%', dur: 9 }],
  [3, 'dot twinkle', { l: '10%', t: '7%', s: '2px', c: '#fff6dc', bs: _scBs([[0, 0, 4, 1, '#fff6dc'], [96, 24, 3, 1, 'a'], [150, -4, 3, 1, '#fff6dc'], [210, 30, 3, 1, '#fff6dc'], [264, 6, 3, 1, 'a']]), dur: 3.4 }],
  [4, 'sil i-clockTower', { r: _scEdge(4), t: '36px', w: '56px', h: '210px', bp: '50% 100%' }],
  [4, 'glow pulse', { r: _scEdge(0), t: '90px', w: '64px', h: '64px', c: '#ffd36b', k: '60%', dur: 3.6 }],
  [4, 'sil i-flutes', { l: '6px', b: '8px', w: '50px', h: '44px', bp: '0% 100%' }],
  [5, 'dot rise', { l: '24px', b: '32px', s: '2px', c: '#fff6dc', bs: _scBs([[0, 0, 1, 0, '#fff6dc'], [6, -7, 1, 0, 'a'], [-3, -14, 1, 0, '#fff6dc']]), dx: '2px', dy: '-26px', s0: '.6', s1: '1.1', dur: 3.2 }],
  [5, 'dot rise', { l: '37px', b: '31px', s: '2px', c: '#fff6dc', bs: _scBs([[0, 0, 1, 0, '#fff6dc'], [-5, -8, 1, 0, 'a'], [4, -15, 1, 0, '#fff6dc']]), dx: '-2px', dy: '-24px', s0: '.6', s1: '1.1', dur: 3.9, del: -1.4 }],
  [5, 'dot float blink', { l: '36%', t: '60%', s: '3px', c: '#ffe9a6', bs: _scBs([[0, 0, 5, 2, 'a'], [-110, 26, 5, 2, '#ffe9a6'], [90, -26, 5, 2, 'a']]), dx: '14px', dy: '-12px', dur: 5.6 }],
  [5, 'dot float blink w2', { l: '58%', t: '30%', s: '3px', c: '#fff6dc', bs: _scBs([[0, 0, 5, 2, '#fff6dc'], [-70, 44, 5, 2, 'a'], [60, 64, 5, 2, '#fff6dc']]), dx: '-12px', dy: '12px', dur: 4.8, del: -2 }],
  [5, 'ring beat', { r: _scEdge(8), t: '98px', w: '48px', h: '48px', c: '#ffd36b', k: '80%', bw: '1.6px', dur: 3.6 }],
  [6, 'sil m i-burst ripple', { l: '187px', t: '-35px', w: '150px', h: '150px', c: '#fff6dc', c2: '#ffb84a', gd: '180deg', o: .9, dur: 11 }],
  [6, 'sil m i-burst ripple w2', { l: '46px', t: '-16px', w: '100px', h: '100px', c: '#ffd9a0', c2: '#ff8a5a', gd: '180deg', o: .85, dur: 9, del: -4.5 }],
  [6, 'sil m i-sparkle peek', { l: '14px', b: '26px', w: '34px', h: '34px', c: '#fff', c2: '#ffe9a6', gd: '180deg', o: .95, dur: 7 }],
  [7, 'ring ripple', { r: _scEdge(-68), t: '22px', w: '200px', h: '200px', c: '#ffd36b', k: '70%', bw: '1.6px', dur: 6 }],
  [7, 'ring ripple w2', { r: _scEdge(-108), t: '-18px', w: '280px', h: '280px', c: '#fff6dc', k: '55%', bw: '1.2px', dur: 6, del: -3 }],
  [7, 'sil m i-willow ripple w2', { l: '100px', t: '-50px', w: '200px', h: '164px', c: '#ffe9a6', c2: '#ffb84a', gd: '180deg', o: .8, dur: 13, del: -6, cr: [24, 39, 177, 164] }],
  [7, 'dot rise', { l: '8%', t: '-6%', s: '3px', c: '#ffe9a6', bs: _scBs([[0, 0, 3, 1, '#ffe9a6'], [58, 40, 3, 0, '#fff6dc'], [120, -10, 3, 1, '#ffd36b'], [176, 60, 3, 0, '#ffe9a6'], [236, 20, 3, 1, '#fff6dc'], [290, 52, 3, 0, '#ffd36b']]), dy: '280px', dx: '18px', s0: '1', s1: '1', dur: 10 }],
]);

// ── Алая Звезда: чёрная сцена с неоном: вывеска-звезда за аватаром, созвездие, закрученная лента вдоль низа, звёзды в обводке, кометы и мерцание трубки ──
_scAdd('scarlet_star', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(40,0,12,.58), rgba(0,0,0,.2) 44%, rgba(160,10,44,.16) 78%, rgba(0,0,0,.5))' }],
  [2, 'glow drift', { l: '-30%', b: '2%', w: '160%', h: '34%', c: 'b', k: '30%', dx: '7%', dur: 27 }],
  [2, 'sil m i-ribbonFloor', { l: '-4%', b: '1%', w: '108%', h: '44px', c: '#ff3b5c', c2: '#ffb0c0', gd: '90deg', o: .6 }],
  [2, 'band', { l: '12%', t: '78%', w: '66%', h: '22%', bg: 'radial-gradient(closest-side, rgba(10,0,4,.9), rgba(10,0,4,.5) 62%, transparent)' }],
  [3, 'glow breathe', { l: '-76px', t: 'calc(50% + var(--bleed) / 2 - 138px)', w: '280px', h: '250px', c: 'a', k: '24%', dur: 8 }],
  [3, 'sil m i-starSign', { l: '-28px', t: 'calc(50% + var(--bleed) / 2 - 101px)', w: '176px', h: '176px', rot: '-10deg', c: '#ff3b5c', c2: '#c8123a', gd: '180deg', o: .5 }],
  [3, 'dot twinkle', { l: '60%', t: '14%', s: '2px', c: '#ffb0c0', bs: _scBs([[0, 0, 4, 1, '#ffb0c0'], [-70, 30, 3, 1, 'a'], [40, 54, 3, 1, '#ffb0c0'], [-136, -4, 3, 1, 'a']]), dur: 3.4 }],
  [4, 'sil m i-starMap', { l: '112px', t: '44px', w: '190px', h: '44px', c: '#ffb0c0', c2: '#ff3b5c', gd: '180deg', o: .55, bp: '0% 0%' }],
  [4, 'glow pulse', { r: '-36px', t: '40px', w: '170px', h: '150px', c: 'a', k: '24%', dur: 5.2 }],
  [5, 'sil m i-starSm rise', { l: '120px', b: '25px', w: '22px', h: '22px', c: '#ff7a92', c2: '#ffb0c0', gd: '180deg', o: .9, dx: '10px', dy: '-120px', s0: '.6', s1: '1.3', dur: 7 }],
  [5, 'sil m i-starSm rise w2', { r: '44px', b: '17px', w: '16px', h: '16px', c: '#ffb0c0', c2: '#ff7a92', gd: '180deg', o: .9, dx: '-8px', dy: '-110px', s0: '.6', s1: '1.3', dur: 8.4, del: -3.2 }],
  [6, 'sil m i-comet cross w2', { l: '0', t: '18%', w: '124px', h: '37px', c: '#ffb0c0', c2: '#ff3b5c', gd: '90deg', o: .85, rot: '14deg', fx: '-160px', tx: '560px', ty: '130px', dur: 17 }],
  [6, 'glow flash', { l: '10%', t: '-20%', w: '90%', h: '70%', c: 'a', k: '44%', dur: 13 }],
  [7, 'sil m i-starSign flicker', { l: '-28px', t: 'calc(50% + var(--bleed) / 2 - 101px)', w: '176px', h: '176px', rot: '-10deg', c: '#ff8ea4', c2: '#ff3b5c', gd: '180deg', o: 1, dur: 7, cr: [6, 8, 170, 164] }],
  [7, 'sil m i-comet cross w2', { l: '0', t: '34%', w: '100px', h: '30px', c: '#ffb0c0', c2: '#ff3b5c', gd: '90deg', o: .8, rot: '10deg', fx: '-140px', tx: '560px', ty: '90px', dur: 23, del: -9 }],
  [7, 'dot twinkle', { l: '70%', t: '36%', s: '3px', c: '#fff', bs: _scBs([[0, 0, 5, 2, '#fff'], [-34, 62, 5, 2, 'c'], [64, 86, 4, 1, '#fff'], [-190, 40, 4, 1, 'c']]), dur: 3.1 }],
]);

// ── Багровый Мрак: ночное кладбище под багровым небом: ограда и покосившиеся камни, обгоревший собор с горящими окнами, дрожащий свет, вороны, молния и окно-розетка за аватаром ──
_scAdd('crimson_dark', [
  [2, 'band', { l: '0', t: '0', w: '100%', h: '100%', bg: 'linear-gradient(180deg, rgba(60,4,10,.6), rgba(20,0,4,.2) 44%, rgba(140,14,28,.16) 76%, rgba(0,0,0,.55))' }],
  [2, 'glow drift', { l: '-30%', b: '4%', w: '160%', h: '36%', c: 'b', k: '30%', dx: '7%', dur: 26 }],
  [3, 'glow breathe', { l: '30%', t: '-30%', w: '90%', h: '70%', c: 'a', k: '26%', dur: 9 }],
  [3, 'band drift', { l: '-10%', t: '15%', w: '90%', h: '11%', bg: 'radial-gradient(closest-side, rgba(36,3,9,.62), transparent)', dx: '14%', dur: 34 }],
  [4, 'sil i-cathedral', { r: _scEdge(-10), t: '-14px', w: '108px', h: '250px', bp: '100% 100%' }],
  [2, 'sil i-graveyard st', { l: '-4%', b: '-1%', w: '108%', h: '31%' }],
  [2, 'band', { l: '12%', t: '75%', w: '66%', h: '25%', bg: 'radial-gradient(closest-side, rgba(8,1,3,.9), rgba(8,1,3,.55) 62%, transparent)' }],
  [5, 'glow flicker', { r: _scEdge(-12), t: '92px', w: '100px', h: '100px', c: '#ff5a4a', k: '46%', dur: 6 }],
  [5, 'glow beat', { l: '-30px', t: 'calc(50% + var(--bleed) / 2 - 105px)', w: '184px', h: '184px', c: 'b', k: '50%', dur: 3.4 }],
  [5, 'dot blink', { l: '250px', b: '14px', s: '2px', c: '#ff3b3b', bs: _scBs([[0, 0, 3, 1, '#ff3b3b'], [7, 0, 3, 1, '#ff3b3b']]), dur: 5.2 }],
  [5, 'dot blink', { l: '146px', b: '6px', s: '2px', c: '#ff3b3b', bs: _scBs([[0, 0, 3, 1, '#ff3b3b'], [6, 0, 3, 1, '#ff3b3b']]), dur: 6.4, del: -2.6 }],
  [5, 'dot rise', { r: _scEdge(70), b: '16px', s: '2px', c: '#ff7a4a', bs: _scBs([[0, 0, 3, 1, 'a'], [10, -16, 3, 1, '#ff7a4a'], [-8, -34, 2, 1, 'a']]), dx: '-12px', dy: '-110px', dur: 6 }],
  [6, 'sil m i-crows cross w2', { l: '0', t: '17%', w: '96px', h: '58px', c: '#0a0204', o: .95, fx: '-120px', tx: '520px', ty: '-14px', dur: 24 }],
  [6, 'sil m i-witchBolt flash', { l: '70%', t: '-4%', w: '10%', h: '62%', bp: '50% 0%', c: '#ffe3e3', o: .95, dur: 11, del: -3 }],
  [6, 'glow flash', { l: '30%', t: '-20%', w: '100%', h: '70%', c: '#e0303c', k: '56%', dur: 11, del: -3 }],
  [7, 'sil m i-roseWindow spin', { l: '-40px', t: 'calc(50% + var(--bleed) / 2 - 115px)', w: '204px', h: '204px', c: '#e0303c', c2: '#7a0f1a', gd: '160deg', o: .5, dur: 160 }],
]);

// ── Сезонные истории, второе издание (владелец 2026-10-22: «к каждому скину свой подход») ───────────────────────────
// Не шаблон «предмет слева + предмет справа + кольцо»: у каждой сцены своя композиция и своё движение.
// Маскарад — театр сверху вниз (ламбрекен, кулисы, прожектор, рампа, падающие перья, ворон над сценой, золотое конфетти).
// Экипаж — дорога в глубину (туман ползёт лентой, фонари уменьшаются к горизонту, экипаж проезжает, фосфорное колесо).
// Пряничная — изнутри тёплого окна (иней по углам стекла, гирлянда пряников качается, жар печи, сахарная пудра, пар над какао).
// Экспресс — путь (горы и виадук едут с разной скоростью, косой снег, Полярная звезда, локомотив проносится, пар).
// Письмо — лист бумаги (линовка, строки пишутся сами, перо, сургуч, лепестки падают).
// Хрусталь — преломление (спектральные лучи из-под аватара, осколки, двойная звезда на орбите).
// Средний центр сцены пуст: аватар и ник всегда читаются. Картинки: tools/scene_art_g.py.
_scAdd('raven_masquerade', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% -10%, #3a1a5299, transparent 64%), linear-gradient(0deg, #12081899, transparent 34%)'}],
  [2, 'band', {l:'0',b:'0',w:'100%',h:'10%',bg:'repeating-linear-gradient(90deg, #2c18129e 0 38px, #3a2216a8 38px 40px), linear-gradient(0deg, #1a0e0a, transparent)'}],
  [2, 'band', {l:'0',b:'10%',w:'100%',h:'1px',bg:'linear-gradient(90deg, transparent, #d6b06aaa, transparent)'}],
  [3, 'glow breathe', {l:'22%',t:'-42%',w:'56%',h:'136%',c:'#ffe6a8',k:'14%',dur:11}],
  [3, 'dot twinkle', {l:'38%',t:'16%',s:'2px',c:'#ffe6a8',bs:_scBs([[40,30,1,0,'#ffe6a8'],[80,70,1,0,'c'],[-20,90,1,0,'#ffe6a8'],[60,120,1,0,'c']]),dur:4.4}],
  [4, 'band', {l:'0',t:'0',w:'100%',h:'19%',bg:'radial-gradient(60px 26px at 12.5% 100%, transparent 96%, #2a0f3a) 0 0 / 25% 100% repeat-x'}],
  [4, 'band', {l:'0',t:'19%',w:'100%',h:'2px',bg:'repeating-linear-gradient(90deg, #d6b06a 0 3px, transparent 3px 7px)'}],
  [4, 'sil i-curtainL sway', {l:'-3%',t:'0',w:'15%',h:'92%',org:'0% 0%',ang:'1deg',dur:12}],
  [4, 'sil i-curtainL fl sway', {r:'-3%',t:'0',w:'15%',h:'92%',org:'100% 0%',ang:'1deg',dur:13,del:-4}],
  [5, 'dot pulse', {l:'8%',b:'6%',s:'4px',c:'#ffd88a',bs:_scBs([[40,0,6,1,'#ffd88a'],[80,0,6,1,'#ffd88a'],[120,0,6,1,'#ffd88a'],[160,0,6,1,'#ffd88a'],[200,0,6,1,'#ffd88a'],[240,0,6,1,'#ffd88a'],[280,0,6,1,'#ffd88a'],[320,0,6,1,'#ffd88a']]),dur:2.6}],
  [5, 'sil m i-ravenFeather rise', {l:'20%',t:'4%',w:'9px',h:'18px',c:'c',o:.85,dx:'18px',dy:'170px',s0:'1',s1:'1',rot:'20deg',dur:12}],
  [5, 'sil m i-ravenFeather rise w2', {r:'24%',t:'2%',w:'8px',h:'16px',c:'a',o:.7,dx:'-14px',dy:'180px',s0:'1',s1:'1',rot:'-24deg',dur:15,del:-6}],
  [6, 'sil m i-ravenFly cross', {l:'0',t:'14%',w:'64px',h:'28px',c:'#0b0712',o:.95,fx:'-90px',tx:'500px',ty:'-24px',dur:27}],
  [7, 'dot rise', {l:'30%',t:'-2%',s:'3px',c:'#ffe6a8',bs:_scBs([[30,10,0,0,'c'],[70,-4,0,0,'#ffe6a8'],[110,6,0,0,'a'],[150,-2,0,0,'#ffe6a8'],[-20,8,0,0,'c']]),dx:'10px',dy:'190px',s0:'1',s1:'1',dur:9}],
  [7, 'dot rise w2', {l:'26%',t:'-6%',s:'2px',c:'#ffd88a',bs:_scBs([[50,0,0,0,'a'],[90,12,0,0,'#ffe6a8'],[130,-6,0,0,'c'],[170,4,0,0,'#ffd88a']]),dx:'-12px',dy:'200px',s0:'1',s1:'1',dur:11,del:-5}],
]);
_scAdd('phantom_carriage', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(180deg, #040e10, #0b2a2a99 58%, #12302c 100%)'}],
  [2, 'wave go i-fogTile m', {l:'0',b:'-2%',w:'calc(100% + 200px)',h:'26%',tw:'200px',c:'#89f3da',o:.18,dur:38}],
  [3, 'glow', {l:'58%',t:'-8%',w:'34%',h:'44%',c:'#ddfff5',k:'22%'}],
  [3, 'band', {l:'34%',t:'58%',w:'32%',h:'42%',bg:'linear-gradient(180deg, transparent, #89f3da14 40%, #89f3da26)'}],
  [3, 'wave go i-fogTile m w2', {l:'0',b:'14%',w:'calc(100% + 200px)',h:'18%',tw:'200px',c:'#c8fff0',o:.12,dur:64}],
  [4, 'sil i-lanternPost', {l:'3%',b:'0',w:'9%',h:'56%',o:.85}],
  [4, 'sil i-lanternPost', {l:'17%',b:'14%',w:'5%',h:'32%',o:.6}],
  [4, 'sil i-lanternPost', {l:'27%',b:'22%',w:'3%',h:'18%',o:.4}],
  [4, 'sil i-lanternPost fl', {r:'3%',b:'0',w:'9%',h:'56%',o:.85}],
  [4, 'sil i-lanternPost fl', {r:'17%',b:'14%',w:'5%',h:'32%',o:.6}],
  [4, 'sil i-lanternPost fl', {r:'27%',b:'22%',w:'3%',h:'18%',o:.4}],
  [5, 'dot float blink', {l:'12%',t:'30%',s:'4px',c:'#c8fff0',bs:'0 0 10px 3px #89f3da66',dx:'14px',dy:'-10px',dur:9}],
  [5, 'dot float blink', {r:'14%',t:'40%',s:'3px',c:'#c8fff0',bs:'0 0 8px 2px #89f3da55',dx:'-12px',dy:'-14px',dur:11,del:-3}],
  [6, 'sil i-ghostCoach cross', {l:'0',b:'-2%',w:'110px',h:'78px',o:.75,fx:'-140px',tx:'520px',dur:24}],
  [7, 'sil m i-ghostWheel spin', {l:'calc(50% - 190px)',t:'calc(50% - 190px)',w:'380px',h:'380px',c:'#89f3da',o:.13,dur:60}],
]);
_scAdd('gingerbread_house', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(0deg, #3a1d0e, #150b08 60%)'}],
  [2, 'glow breathe', {l:'-10%',b:'-36%',w:'120%',h:'62%',c:'#ff9a4a',k:'26%',dur:5}],
  [3, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(90deg, #ffe8c512, transparent 16%, transparent 84%, #ffe8c512), linear-gradient(180deg, #ffe8c514, transparent 20%)'}],
  [3, 'sil m i-frostCorner', {l:'0',t:'6%',w:'34%',h:'40%',c:'#fff4e2',o:.5,bp:'0% 0%'}],
  [3, 'sil m i-frostCorner fl', {r:'0',t:'6%',w:'34%',h:'40%',c:'#fff4e2',o:.5,bp:'0% 0%'}],
  [4, 'sil i-cookieGarland sway', {l:'-2%',t:'7%',w:'104%',h:'34%',bp:'50% 0%',org:'50% 0%',ang:'1.5deg',dur:7}],
  [5, 'dot rise', {l:'10%',t:'-4%',s:'2px',c:'#fff7ea',bs:_scBs([[40,6,0,0,'#fff7ea'],[90,-2,0,0,'#fff7ea'],[150,10,0,0,'#fff7ea'],[210,0,0,0,'#fff7ea'],[260,8,0,0,'#fff7ea'],[310,-4,0,0,'#fff7ea']]),dx:'8px',dy:'190px',s0:'1',s1:'1',o:.8,dur:10}],
  [5, 'dot rise w2', {l:'4%',t:'-10%',s:'1.5px',c:'#ffe1b8',bs:_scBs([[70,0,0,0,'#ffe1b8'],[130,8,0,0,'#ffe1b8'],[190,-6,0,0,'#ffe1b8'],[240,4,0,0,'#ffe1b8'],[300,-2,0,0,'#ffe1b8']]),dx:'-6px',dy:'200px',s0:'1',s1:'1',o:.7,dur:13,del:-6}],
  [6, 'glow flash', {l:'8%',t:'6%',w:'22%',h:'28%',c:'#fff4e2',k:'40%',dur:15}],
  [7, 'sil m i-steamPuff rise', {r:'10%',b:'2%',w:'44px',h:'28px',c:'#ffe1b8',o:.22,dx:'-10px',dy:'-110px',s0:'.5',s1:'1.5',dur:8}],
  [7, 'glow flicker', {l:'-6%',b:'-12%',w:'30%',h:'36%',c:'#ffb35c',k:'30%',dur:3}],
]);
_scAdd('polar_express', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(180deg, #06101a, #16304e 70%, #23415f)'}],
  [2, 'dot twinkle', {l:'8%',t:'8%',s:'2px',c:'#e6f2ff',bs:_scBs([[50,20,1,0,'#e6f2ff'],[120,6,1,0,'c'],[200,30,1,0,'#e6f2ff'],[280,12,1,0,'a'],[330,40,1,0,'#e6f2ff']]),dur:5}],
  [3, 'wave go i-peaksTile', {l:'0',b:'14%',w:'calc(100% + 240px)',h:'24%',tw:'240px',o:.85,dur:70}],
  [3, 'glow breathe', {r:'2%',t:'-8%',w:'34%',h:'44%',c:'#ffe0a0',k:'22%',dur:7}],
  [4, 'wave go i-trackTile', {l:'0',b:'-1%',w:'calc(100% + 120px)',h:'17%',tw:'120px',dur:9}],
  [4, 'sil m i-northStar breathe', {r:'9%',t:'4%',w:'46px',h:'46px',c:'#fff3d6',o:.95,dur:4}],
  [5, 'dot sweep', {l:'0',t:'6%',s:'2px',c:'#ffffff',bs:_scBs([[-40,30,0,0,'#fff'],[-90,70,0,0,'#e6f2ff'],[-150,20,0,0,'#fff'],[-210,90,0,0,'#e6f2ff'],[-260,50,0,0,'#fff']]),fx:'420px',tx:'-120px',ty:'120px',dur:5}],
  [5, 'dot sweep w2', {l:'0',t:'30%',s:'1.5px',c:'#e6f2ff',bs:_scBs([[-60,10,0,0,'#e6f2ff'],[-130,50,0,0,'#fff'],[-190,-10,0,0,'#e6f2ff'],[-250,30,0,0,'#fff']]),fx:'440px',tx:'-140px',ty:'110px',dur:6.5,del:-2}],
  [6, 'sil i-northEngine cross', {l:'0',b:'11%',w:'96px',h:'80px',fx:'-120px',tx:'520px',dur:18}],
  [7, 'sil m i-steamPuff rise', {l:'8%',b:'16%',w:'58px',h:'38px',c:'#dce9f5',o:.55,dx:'-20px',dy:'-120px',s0:'.6',s1:'1.6',dur:7}],
  [7, 'sil m i-steamPuff rise w2', {l:'14%',b:'14%',w:'46px',h:'30px',c:'#dce9f5',o:.45,dx:'-30px',dy:'-140px',s0:'.6',s1:'1.8',dur:9,del:-4}],
]);
_scAdd('rose_letter', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'repeating-linear-gradient(180deg, transparent 0 27px, #ffa9c11c 27px 28px), linear-gradient(180deg, #2a1218, #14090f)'}],
  [2, 'band', {l:'9%',t:'0',w:'1px',h:'100%',bg:'#ff7a9a33'}],
  [3, 'glow breathe', {r:'-14%',t:'-20%',w:'60%',h:'80%',c:'#ffcf8a',k:'18%',dur:8}],
  [4, 'sil m i-inkLine sweep', {l:'0',b:'18%',w:'46%',h:'18px',c:'#ffa9c1',o:.55,fx:'-180px',tx:'0px',dur:9}],
  [4, 'sil m i-inkLine sweep w2', {l:'0',b:'8%',w:'38%',h:'16px',c:'#ffa9c1',o:.42,fx:'-160px',tx:'0px',dur:9,del:-4.5}],
  [4, 'sil i-roseQuill sway', {r:'-4%',b:'-6%',w:'22%',h:'54%',bp:'100% 100%',org:'80% 100%',ang:'4deg',o:.75,dur:3}],
  [5, 'sil m i-petal rise', {l:'16%',t:'-6%',w:'12px',h:'10px',c:'#d84a72',o:.85,dx:'30px',dy:'190px',s0:'1',s1:'.8',rot:'30deg',dur:10}],
  [5, 'sil m i-petal rise', {r:'30%',t:'-6%',w:'10px',h:'8px',c:'#ff8fae',o:.75,dx:'-24px',dy:'200px',s0:'1',s1:'.8',rot:'-40deg',dur:13,del:-5}],
  [5, 'sil m i-petal rise w2', {l:'44%',t:'-8%',w:'9px',h:'8px',c:'#c43f66',o:.7,dx:'14px',dy:'210px',s0:'1',s1:'.8',dur:15,del:-9}],
  [6, 'sil i-waxSeal beat', {l:'4%',b:'4%',w:'40px',h:'40px',o:.9,dur:5}],
  [7, 'sil m i-petal rise', {l:'6%',t:'-6%',w:'14px',h:'12px',c:'#ff6f92',o:.9,dx:'40px',dy:'200px',s0:'1',s1:'.7',rot:'10deg',dur:8,del:-2}],
  [7, 'glow pulse', {l:'calc(50% - 120px)',t:'calc(50% - 120px)',w:'240px',h:'240px',c:'#ff9ab6',k:'14%',dur:4}],
]);
_scAdd('glass_heart', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 120%, #4b2c6c88, transparent 60%), linear-gradient(180deg, #0f0919, #170e26)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'-34deg',bg:'linear-gradient(0deg, #ff7ad955, #ffd36b33, #7affc322, transparent)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'-12deg',bg:'linear-gradient(0deg, #7ac8ff55, #b5b5ef33, transparent)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'14deg',bg:'linear-gradient(0deg, #ffd36b55, #ff7ad933, transparent)'}],
  [3, 'band', {l:'calc(50% - 2px)',b:'-10%',w:'4px',h:'120%',org:'50% 100%',rot:'36deg',bg:'linear-gradient(0deg, #7affc355, #7ac8ff33, transparent)'}],
  [4, 'sil i-shard float', {l:'3%',t:'12%',w:'26px',h:'46px',o:.8,rot:'-18deg',dx:'4px',dy:'-8px',dur:9}],
  [4, 'sil i-shard float', {r:'5%',t:'50%',w:'20px',h:'36px',o:.7,rot:'24deg',dx:'-4px',dy:'-10px',dur:11,del:-3}],
  [4, 'sil i-shard float w2', {l:'12%',b:'6%',w:'16px',h:'28px',o:.6,rot:'40deg',dx:'5px',dy:'-6px',dur:13,del:-6}],
  [5, 'dot spin', {l:'calc(50% - 2px)',t:'calc(50% - 2px)',s:'4px',c:'transparent',bs:_scBs([[118,0,6,2,'#f6b6ed'],[-118,0,6,2,'#b5e4ff']]),dur:26}],
  [5, 'dot twinkle', {l:'14%',t:'20%',s:'2px',c:'#e4fbff',bs:_scBs([[60,50,2,0,'#f6b6ed'],[230,10,2,0,'#e4fbff'],[280,90,2,0,'#f6b6ed']]),dur:4}],
  [6, 'band sweep', {l:'0',t:'34%',w:'90px',h:'2px',bg:'linear-gradient(90deg, transparent, #f6b6ed, #b5e4ff, #ffd36b, transparent)',rot:'-8deg',fx:'-100px',tx:'480px',ty:'20px',dur:13}],
  [7, 'dot spin rev', {l:'calc(50% - 2px)',t:'calc(50% - 2px)',s:'3px',c:'transparent',bs:_scBs([[0,-146,5,2,'#ffffff'],[0,146,5,2,'#f6b6ed']]),dur:40}],
  [7, 'sil i-crystalHeart beat', {r:'4%',b:'4%',w:'40px',h:'46px',o:.85,dur:3.2}],
]);

// Фирменные детали сезонных образов (SSS): у каждой своя мысль, не медальон-шаблон. Рисунок в единицах рамки (центр 50,50, кольцо ≈ 57), холст -30..130.
// Маска соскользнула на оправу; фосфорное колесо кареты за кольцом и фонарь на крюке; пряничный человечек держится за кольцо глазури;
// огонёк экспресса бежит по латунным рельсам вокруг; роза вьётся по кольцу и роняет лепесток; кристаллы прорастают из оправы, две звезды на парной орбите.
// Цвет и движение: skin-holidays-v3.css (только под .ap-anim, .ap-low и reduced-motion гасят).
(() => {
  const R = n => Math.round(n * 10) / 10;
  const pt = (r, deg) => `${R(50 + r * Math.cos(deg * Math.PI / 180))} ${R(50 + r * Math.sin(deg * Math.PI / 180))}`;
  const svg = (name, inner, back) => `<svg class="sa hs-${name}${back ? ' sa-b' : ''}" viewBox="-30 -30 160 160" aria-hidden="true">${inner}</svg>`;
  const ring = (n, f) => Array.from({ length: n }, (_, i) => f(i * 360 / n, i)).join('');
  const SPARK = 'M0-1L.27-.27L1 0L.27.27L0 1L-.27.27L-1 0L-.27-.27Z';

  const ravenmask = svg('mask', `<g transform="translate(88 8) rotate(36)"><g class="hs-bob">
    <path class="hs-rib" d="M-19-1q-9 7-7 18 2 9-4 17"/><path class="hs-rib hs-rib2" d="M-17 2q-4 9 0 17 3 7-1 14"/>
    <path class="hs-fth" d="M18-4Q30-17 27-36Q17-22 18-4Z"/><path class="hs-vein" d="M18-4Q25-18 27-34"/>
    <path class="hs-mk" fill-rule="evenodd" d="M-20-2Q-14-11-4-6Q0-3 4-6Q14-11 20-2Q18 8 8 7Q3 6 0 2Q-3 6-8 7Q-18 8-20-2ZM-13 0a4.6 2.7 0 1 0 9.2 0a4.6 2.7 0 1 0-9.2 0ZM3.8 0a4.6 2.7 0 1 0 9.2 0a4.6 2.7 0 1 0-9.2 0Z"/>
    <path class="hs-fil" d="M-17-3Q-12-8-5-5M5-5Q12-8 17-3M0-1v-3"/><circle class="hs-gem" cx="0" cy="-5.5" r="1.4"/></g></g>`);
  const ghostcoach = [svg('wheel', `<g class="hs-spin"><circle class="hs-rim" cx="50" cy="50" r="67"/><circle class="hs-rim2" cx="50" cy="50" r="62"/>
    ${ring(16, a => `<path class="hs-spk" d="M${pt(57, a)}L${pt(67, a)}"/>`)}${ring(8, a => `<circle class="hs-stud" cx="${pt(67, a).split(' ')[0]}" cy="${pt(67, a).split(' ')[1]}" r="1.3"/>`)}</g>`, true),
    svg('lamp', `<path class="hs-hook" d="M-4-18H14v6"/><g class="hs-swing"><path class="hs-hook" d="M14-12v5"/><circle class="hs-halo" cx="14" cy="5" r="11"/>
    <path class="hs-lbody" d="M8-7h12l-2 4v13l2 3H8l2-3V-3Z"/><path class="hs-lglass" d="M11-2h6v11h-6Z"/><circle class="hs-flame" cx="14" cy="4" r="1.8"/></g>`)];
  const sugarhouse = svg('icing', `<path class="hs-scal" d="${ring(28, (a, i) => `${i ? 'L' : 'M'}${pt(i % 2 ? 61 : 64, a)}`)}Z"/>
    ${ring(22, (a, i) => `<path class="hs-spr hs-spr${i % 3}" transform="translate(${pt(i % 2 ? 67.5 : 69.5, a + 6)}) rotate(${(i * 47) % 180})" d="M-1.6 0h3.2"/>`)}
    <g transform="translate(${pt(66, 38)}) rotate(-28)"><g class="hs-rock"><path class="hs-gb" d="M0-14a5 5 0 1 1 0 .1ZM-4-9h8l9 5-2 4-7-3 1 9 5 9-4 2-6-8-6 8-4-2 5-9 1-9-7 3-2-4Z"/>
    <path class="hs-gbi" d="M-2-15h1m2 0h1M-2-11q2 1 4 0M-3 3q3 2 6 0M0-5v1m0 3v1M-8-6q-2 1-4 0M8-6q2 1 4 0"/></g></g>`);
  const northtrain = svg('rail', `<circle class="hs-rl" cx="50" cy="50" r="61.5"/><circle class="hs-rl" cx="50" cy="50" r="65.5"/>
    ${ring(40, a => `<path class="hs-tie" d="M${pt(59.5, a)}L${pt(67.5, a)}"/>`)}
    <g class="hs-run"><circle class="hs-trail" cx="${pt(63.5, -104).split(' ')[0]}" cy="${pt(63.5, -104).split(' ')[1]}" r="1.1"/><circle class="hs-trail" cx="${pt(63.5, -98).split(' ')[0]}" cy="${pt(63.5, -98).split(' ')[1]}" r="1.5"/>
    <circle class="hs-lglow" cx="50" cy="-13.5" r="7"/><circle class="hs-lamp" cx="50" cy="-13.5" r="2.3"/></g>
    <g transform="translate(108 -8) scale(5)"><path class="hs-star" d="${SPARK}"/></g>`);
  const rosequill = svg('rose', `<path class="hs-vine" d="M${pt(60, 150)}C${pt(70, 175)} ${pt(55, 195)} ${pt(62, 215)}S${pt(66, 245)} ${pt(60, 262)}"/>
    ${[160, 188, 228].map((a, i) => `<path class="hs-leaf" transform="translate(${pt(62 + (i % 2) * 3, a)}) rotate(${a + (i % 2 ? 50 : -40)}) scale(7)" d="M0 0C.15-.55.7-.62 1 0C.7.55.15.5 0 0Z"/>`).join('')}
    ${[172, 205, 240].map(a => `<path class="hs-thorn" transform="translate(${pt(64, a)}) rotate(${a})" d="M0-1l3 1-3 1Z"/>`).join('')}
    <g transform="translate(${pt(60, 264)})"><g class="hs-bud"><path class="hs-pt hs-pt1" d="M0 2Q-7-1-5-8Q-2-6 0-4Z"/><path class="hs-pt hs-pt1" d="M0 2Q7-1 5-8Q2-6 0-4Z"/>
    <path class="hs-pt" d="M0 1Q-4-4 0-10Q4-4 0 1Z"/><path class="hs-sepal" d="M-4 3Q0 1 4 3L0 6Z"/></g><path class="hs-fall" d="M2-4q3-2 5 1-2 3-5 1Z"/></g>`);
  const prism = (x, y, ang, L, w) => `<g transform="translate(${x} ${y}) rotate(${ang})"><path class="hs-cf1" d="M0 ${-w}L${L} ${-w * .6}L${L + w * 1.6} 0L${L} ${w * .6}L0 ${w}Z"/><path class="hs-cf2" d="M0 0L${L} ${-w * .6}L${L + w * 1.6} 0Z"/><path class="hs-ce" d="M0 0H${L + w * 1.6}"/></g>`;
  const clus = (a, specs) => { const [x, y] = pt(55, a).split(' '); return specs.map(([d, L, w]) => prism(x, y, a + d, L, w)).join(''); };
  const crystalheart = svg('cryst', `${clus(38, [[-22, 12, 2.6], [0, 20, 3.4], [20, 9, 2.2], [36, 6, 1.6]])}${clus(218, [[-14, 9, 2.2], [8, 13, 2.8], [28, 5, 1.4]])}
    <g transform="translate(${pt(78, 38)}) scale(3.2)"><path class="hs-glint" d="${SPARK}"/></g>
    <g class="hs-orb"><circle class="hs-tw1" cx="${pt(71, -60).split(' ')[0]}" cy="${pt(71, -60).split(' ')[1]}" r="2"/><circle class="hs-tw2" cx="${pt(71, 120).split(' ')[0]}" cy="${pt(71, 120).split(' ')[1]}" r="2"/></g>`);
  if (typeof _AP_DECOR !== 'undefined') Object.assign(_AP_DECOR, { ravenmask: ravenmask, ghostcoach: ghostcoach.join(''), sugarhouse: sugarhouse, northtrain: northtrain, rosequill: rosequill, crystalheart: crystalheart });
})();

// ── Картинки вкладок: эмблема и созвездие в шапке, рисованные валюты (тот же язык, что у Лиги сезона) ──────────
// Эмблема — плитка 56px с рисунком вкладки цветом образа (--v3-acc) и золотом; за шапкой статичное созвездие.
// Появление эмблемы одноразовое и идёт вместе с каскадом страницы (--enter-skip, v3EnterSync): перерисовка не перезапускает его.
// Данные — var, а функции объявлены целиком: app.js склеен из частей, и шапка может рисоваться раньше, чем дошла очередь этого файла.
// Слабый телефон (data-dev=low), «Спокойный режим» и reduced-motion: без движения (art-v3.css). Смысл всегда несёт текст рядом.
var _V3_GOLD = '#f5cf73';
var _V3_EMB = {
  quests: `<path d="M18 12h26a4 4 0 0 1 4 4v32a4 4 0 0 1-4 4H18z" fill="currentColor" fill-opacity=".16" stroke="currentColor" stroke-width="2.4"/><path d="M14 12a4 4 0 0 1 8 0v36a4 4 0 0 1-8 0z" fill="currentColor"/><path d="M27 22h14M27 29h14M27 36h9" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><circle cx="44" cy="46" r="7" fill="${_V3_GOLD}"/><path d="M41 46l2 2 4-4" fill="none" stroke="#3a2706" stroke-width="2" stroke-linecap="round"/>`,
  medal: `<path d="M22 8h8l6 16h-8zM42 8h-8l-6 16h8z" fill="currentColor"/><circle cx="32" cy="38" r="16" fill="${_V3_GOLD}"/><circle cx="32" cy="38" r="11.5" fill="none" stroke="#8a5a12" stroke-opacity=".6" stroke-width="1.6"/><path d="M32 30.5l2.3 4.7 5.2.7-3.8 3.6.9 5.1-4.6-2.4-4.6 2.4.9-5.1-3.8-3.6 5.2-.7z" fill="#fff4cc"/>`,
  bag: `<path d="M24 18v-3a8 8 0 0 1 16 0v3" fill="none" stroke="currentColor" stroke-width="3"/><path d="M12 22a4 4 0 0 1 4-4h32a4 4 0 0 1 4 4v24a8 8 0 0 1-8 8H20a8 8 0 0 1-8-8z" fill="currentColor" fill-opacity=".2" stroke="currentColor" stroke-width="2.4"/><path d="M12 30h40" stroke="currentColor" stroke-width="2.4"/><rect x="27" y="26" width="10" height="9" rx="2" fill="${_V3_GOLD}"/>`,
  paw: `<g fill="currentColor"><ellipse cx="32" cy="41" rx="11" ry="9.5"/><ellipse cx="17" cy="28" rx="5" ry="6.2"/><ellipse cx="47" cy="28" rx="5" ry="6.2"/><ellipse cx="25" cy="17" rx="4.8" ry="6"/><ellipse cx="39" cy="17" rx="4.8" ry="6"/></g><ellipse cx="29" cy="38" rx="3.5" ry="2.4" fill="#fff" fill-opacity=".35"/>`,
  ticket: `<path d="M10 20a4 4 0 0 1 4-4h36a4 4 0 0 1 4 4v6a6 6 0 0 0 0 12v6a4 4 0 0 1-4 4H14a4 4 0 0 1-4-4v-6a6 6 0 0 0 0-12z" fill="currentColor" fill-opacity=".2" stroke="currentColor" stroke-width="2.4"/><path d="M40 18v28" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"/><path d="M25 25l2 4.2 4.6.6-3.4 3.2.9 4.5L25 35.3l-4.1 2.2.9-4.5-3.4-3.2 4.6-.6z" fill="${_V3_GOLD}"/>`,
  anvil: `<path d="M10 22h34c0 6 4 9 10 9v3H40l-4 6v6h6v6H18v-6h6v-6l-4-6h-4c-4 0-6-4-6-12z" fill="currentColor"/><path d="M48 12l2 4 4 1-3 3 1 4-4-2-4 2 1-4-3-3 4-1z" fill="${_V3_GOLD}"/>`,
  trophy: `<path d="M20 10h24v14a12 12 0 0 1-24 0z" fill="${_V3_GOLD}"/><path d="M20 14h-6v4a8 8 0 0 0 8 8M44 14h6v4a8 8 0 0 1-8 8" fill="none" stroke="${_V3_GOLD}" stroke-width="3"/><path d="M28 36h8v6h-8z" fill="${_V3_GOLD}"/><rect x="20" y="42" width="24" height="8" rx="2" fill="currentColor"/><path d="M26 15v8" stroke="#fff" stroke-opacity=".6" stroke-width="2.4" stroke-linecap="round"/>`,
  compass: `<circle cx="32" cy="32" r="21" fill="currentColor" fill-opacity=".14" stroke="currentColor" stroke-width="2.4"/><path d="M32 12l5 20-5 20-5-20z" fill="currentColor"/><path d="M12 32l20-5 20 5-20 5z" fill="${_V3_GOLD}"/><circle cx="32" cy="32" r="3.4" fill="#fff"/>`,
  gear: `<g fill="currentColor"><rect x="28" y="6" width="8" height="12" rx="2"/><rect x="28" y="46" width="8" height="12" rx="2"/><rect x="6" y="28" width="12" height="8" rx="2"/><rect x="46" y="28" width="12" height="8" rx="2"/><rect x="28" y="6" width="8" height="12" rx="2" transform="rotate(45 32 32)"/><rect x="28" y="46" width="8" height="12" rx="2" transform="rotate(45 32 32)"/><rect x="6" y="28" width="12" height="8" rx="2" transform="rotate(45 32 32)"/><rect x="46" y="28" width="12" height="8" rx="2" transform="rotate(45 32 32)"/><circle cx="32" cy="32" r="16"/></g><circle cx="32" cy="32" r="7" fill="${_V3_GOLD}"/>`,
  crystal: `<path d="M20 12h24l10 14-22 28L10 26z" fill="currentColor" fill-opacity=".85"/><path d="M10 26h44M20 12l6 14 6 28M44 12l-6 14-6 28M26 26l6-14 6 14" fill="none" stroke="#fff" stroke-opacity=".55" stroke-width="1.6"/><path d="M50 8l1.6 3.6 3.8.6-2.8 2.6.8 3.8-3.4-1.8-3.4 1.8.8-3.8-2.8-2.6 3.8-.6z" fill="${_V3_GOLD}"/>`,
  crown: `<path d="M8 22l12 10 12-20 12 20 12-10-5 28H13z" fill="${_V3_GOLD}"/><path d="M13 50h38" stroke="#8a5a12" stroke-opacity=".5" stroke-width="2.4"/><circle cx="32" cy="12" r="4" fill="currentColor"/><circle cx="8" cy="22" r="3" fill="currentColor"/><circle cx="56" cy="22" r="3" fill="currentColor"/>`,
  comet: `<path d="M12 52L38 26" stroke="currentColor" stroke-opacity=".35" stroke-width="10" stroke-linecap="round"/><path d="M16 50L38 28" stroke="currentColor" stroke-opacity=".6" stroke-width="5" stroke-linecap="round"/><circle cx="42" cy="22" r="11" fill="${_V3_GOLD}"/><circle cx="38.5" cy="18.5" r="3.2" fill="#fff" fill-opacity=".7"/>`,
  lantern: `<path d="M26 10h12M32 10V6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/><path d="M22 16h20l-2 30H24z" fill="currentColor" fill-opacity=".18" stroke="currentColor" stroke-width="2.4"/><ellipse cx="32" cy="32" rx="6" ry="9" fill="${_V3_GOLD}"/><path d="M20 50h24" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>`,
  chart: `<rect x="12" y="36" width="8" height="14" rx="2" fill="currentColor" fill-opacity=".5"/><rect x="25" y="28" width="8" height="22" rx="2" fill="currentColor" fill-opacity=".7"/><rect x="38" y="20" width="8" height="30" rx="2" fill="currentColor"/><path d="M12 28l12-10 10 6 16-14" fill="none" stroke="${_V3_GOLD}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><path d="M44 10h6v6" fill="none" stroke="${_V3_GOLD}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`,
  seal: `<path d="M32 8l5 4 6-1 2 6 6 3-1 6 4 5-4 5 1 6-6 3-2 6-6-1-5 4-5-4-6 1-2-6-6-3 1-6-4-5 4-5-1-6 6-3 2-6 6 1z" fill="currentColor"/><circle cx="32" cy="32" r="12" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width="1.6"/><path d="M32 24l2.4 5 5.4.7-4 3.7 1 5.4-4.8-2.6-4.8 2.6 1-5.4-4-3.7 5.4-.7z" fill="${_V3_GOLD}"/>`,
  coins: `<ellipse cx="26" cy="44" rx="15" ry="6" fill="#b9781b"/><rect x="11" y="38" width="30" height="6" fill="#b9781b"/><ellipse cx="26" cy="38" rx="15" ry="6" fill="${_V3_GOLD}"/><ellipse cx="38" cy="30" rx="15" ry="6" fill="#b9781b"/><rect x="23" y="24" width="30" height="6" fill="#b9781b"/><ellipse cx="38" cy="24" rx="15" ry="6" fill="${_V3_GOLD}"/><path d="M33 23h10" stroke="#8a5a12" stroke-width="2" stroke-linecap="round"/><path d="M50 8l1.6 3.6 3.8.6-2.8 2.6.8 3.8-3.4-1.8-3.4 1.8.8-3.8-2.8-2.6 3.8-.6z" fill="currentColor"/>`,
  chat: `<path d="M12 16a6 6 0 0 1 6-6h28a6 6 0 0 1 6 6v18a6 6 0 0 1-6 6H28l-10 9v-9a6 6 0 0 1-6-6z" fill="currentColor" fill-opacity=".2" stroke="currentColor" stroke-width="2.4"/><circle cx="24" cy="25" r="3" fill="currentColor"/><circle cx="33" cy="25" r="3" fill="currentColor"/><circle cx="42" cy="25" r="3" fill="${_V3_GOLD}"/>`,
  chest: `<path d="M10 28c0-9 10-15 22-15s22 6 22 15v4H10z" fill="currentColor" fill-opacity=".55"/><rect x="10" y="30" width="44" height="22" rx="3" fill="currentColor"/><path d="M10 34h44M20 14v38M44 14v38" stroke="${_V3_GOLD}" stroke-width="2.4"/><rect x="27" y="28" width="10" height="11" rx="2" fill="${_V3_GOLD}"/>`,
};
// Какая эмблема у какой шапки (v3Head): Сундуки рисуют свою сцену с сундуком и эмблему не берут
var _V3_HEAD_EMB = { 'Топ': 'trophy', 'Что нового': 'comet', 'Задания': 'quests', 'Достижения': 'medal', 'Инвентарь': 'bag', 'Питомцы': 'paw', 'Промокоды': 'ticket', 'Экипировка': 'anvil' };
function v3Emblem(kind, cls = '') { return _V3_EMB && _V3_EMB[kind] ? `<span class="v3-emblem v3-emblem--${kind} ${cls}" aria-hidden="true"><svg viewBox="0 0 64 64">${_V3_EMB[kind]}</svg></span>` : ''; }
// Созвездие за шапкой: статично, две звезды мерцают три раза только на сильном телефоне
var V3_SKY = '<svg class="v3-sky" viewBox="0 0 360 120" preserveAspectRatio="xMaxYMid slice" aria-hidden="true" focusable="false"><path d="M196 30L232 18L270 40L300 26L332 52M270 40L262 78L298 96M232 18L214 62L262 78" fill="none" stroke="currentColor" stroke-opacity=".2" stroke-width=".8"/><g fill="currentColor"><circle cx="196" cy="30" r="1.3" opacity=".7"/><circle cx="232" cy="18" r="1.9"/><circle cx="270" cy="40" r="1.5" opacity=".85"/><circle cx="300" cy="26" r="1.2" opacity=".7"/><circle cx="332" cy="52" r="1.6" opacity=".8"/><circle cx="262" cy="78" r="2.1"/><circle cx="298" cy="96" r="1.2" opacity=".6"/><circle cx="214" cy="62" r="1.1" opacity=".6"/><circle cx="150" cy="16" r=".8" opacity=".4"/><circle cx="350" cy="12" r=".9" opacity=".4"/><circle class="v3-tw" cx="232" cy="18" r="3.2" opacity="0"/><circle class="v3-tw v3-tw2" cx="262" cy="78" r="3.4" opacity="0"/></g></svg>';

// Рисованные валюты (вместо 🪙 💎 ✨ 💧) — те же, что в Пропуске Лиги и добыче сундуков
var _V3_CUR = {
  mora: '<circle cx="16" cy="16" r="13" fill="#f0bf4c"/><circle cx="16" cy="16" r="13" fill="none" stroke="#b9781b" stroke-width="1.6"/><circle cx="16" cy="16" r="9.6" fill="none" stroke="#8a5a12" stroke-opacity=".55" stroke-width="1.4"/><path d="M11 21V11l5 6 5-6v10" fill="none" stroke="#7a4c0c" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/><path d="M8.5 11.5a9 9 0 0 1 5-4.6" fill="none" stroke="#fff" stroke-opacity=".7" stroke-width="1.6" stroke-linecap="round"/>',
  diamonds: '<path d="M9 5h14l6 8-13 15L3 13z" fill="#8fd8ff"/><path d="M9 5h14l6 8H3z" fill="#e9fbff" fill-opacity=".6"/><path d="M3 13h26M9 5l4 8 3 15M23 5l-4 8-3 15M13 13l3-8 3 8" fill="none" stroke="#fff" stroke-opacity=".6" stroke-width="1"/><path d="M16 28L3 13h26z" fill="#7a6bff" fill-opacity=".45"/>',
  zarniki: '<path d="M16 2l3.4 9.2L29 14l-8.2 4.6L22 29l-6-6.8L10 29l1.2-10.4L3 14l9.6-2.8z" fill="#ffc35c"/><path d="M16 2l3.4 9.2L29 14l-8.2 4.6L22 29l-6-6.8z" fill="#d36bff" fill-opacity=".35"/><path d="M16 9l1.6 4.6 4.4 1.2-3.8 2.2.6 4.8L16 18.6l-2.8 3.2.6-4.8-3.8-2.2 4.4-1.2z" fill="#fff" fill-opacity=".6"/>',
  essence: '<path d="M16 3c5 7 9 11.5 9 17a9 9 0 0 1-18 0c0-5.5 4-10 9-17z" fill="#6fc3ff"/><path d="M16 3c5 7 9 11.5 9 17a9 9 0 0 1-9 9z" fill="#4a7dff" fill-opacity=".45"/><path d="M11.5 19a5 5 0 0 0 3 5" fill="none" stroke="#fff" stroke-opacity=".75" stroke-width="1.8" stroke-linecap="round"/>',
};
function v3Cur(kind, cls = '') { return _V3_CUR && _V3_CUR[kind] ? `<svg class="v3-cur v3-cur--${kind} ${cls}" viewBox="0 0 32 32" aria-hidden="true" focusable="false">${_V3_CUR[kind]}</svg>` : ''; }
// Готовая разметка: 🪙 💎 ✨ 💧 в тексте → рисованные валюты. Атрибуты (aria-label, title) и <option>/<textarea>/<title> не трогаю: там нужен текст
var _V3_CUR_EMOJI = { '🪙': 'mora', '💎': 'diamonds', '✨': 'zarniki', '💧': 'essence' };
function v3CurIn(html) {
  const src = String(html ?? ''); if (!/🪙|💎|✨|💧/u.test(src)) return src;
  let raw = 0;
  return src.split(/(<(?:[^>"']|"[^"]*"|'[^']*')*>)/).map(part => {
    if (part[0] === '<') { const m = /^<(\/?)(option|textarea|title)\b/i.exec(part); if (m) raw += m[1] ? -1 : 1; return part; }
    return raw > 0 ? part : part.replace(/🪙|💎|✨|💧/gu, e => v3Cur(_V3_CUR_EMOJI[e]) || e);
  }).join('');
}

// Шапка-герой для экранов со своей разметкой (Топ, Магазин, Ещё, Настройки, Справка, Биржа…): эмблема, заголовок, подпись, созвездие
function v3Hero(kind, title, sub = '', { eyebrow = '', end = '', stat = '' } = {}) {
  return `<header class="v3-hero">${V3_SKY || ''}${v3Emblem(kind)}<div class="v3-hero-tx">${eyebrow ? `<small class="v3-hero-eb">${eyebrow}</small>` : ''}<h1 class="v3-title">${esc(title)}</h1>${sub ? `<p class="v3-head-s">${sub}</p>` : ''}</div>${stat}${end}</header>`;
}

// Подиум тройки лидеров (Топ и «Топ-10» в профиле): 2 · 1 · 3. Каждое место — карточка-сцена с тем же образом, что в публичном
// профиле: фон и частицы, ореол, рамка, аватар (фото VIP или личное созвездие по ref и уровню), ник со стилем, титул, VIP и регалия
function _v3PodId(r) {
  if (r.kind==='chat') return `<span class="v3-pod-card chat-theme" style="${chatThemeStyle(r)}"><span class="v3-pod-id"><span class="v3-ring">${chatThemeAvatar(r)}<span class="v3-pod-medal" aria-hidden="true">${r.place}</span></span><b class="v3-pod-name">${esc(r.name)}</b></span></span>`;
  const ap = typeof apFromLook === 'function' ? apFromLook(r.look) : null;
  const fallback = typeof _v3Avatar === 'function' ? _v3Avatar({ seed: r.ref || r.name, level: r.level, is_vip: !!r.is_vip, display_name: r.name }) : '';
  const ava = window.leaderboardAvatar ? window.leaderboardAvatar(r, fallback) : fallback;
  const name = ap ? apName(ap, esc(r.name)) : `<span class="ap-plain">${esc(r.name)}</span>`;
  const id = `<span class="v3-pod-id"><span class="v3-ring">${apHalo(ap)}<svg viewBox="0 0 76 76" aria-hidden="true"><circle cx="38" cy="38" r="35"/></svg><span class="v3-ava">${ava}</span>${apFrame(ap)}<span class="v3-pod-medal" aria-hidden="true">${r.place}</span></span>
    <b class="v3-pod-name">${name}${r.is_vip ? '<em class="v3-vipdot" aria-label="VIP"></em>' : ''}${typeof v3MarkDot === 'function' ? v3MarkDot(r.mark) : ''}</b>${ap ? apTitle(ap) : ''}</span>`;
  return `<span class="v3-pod-card${ap ? ' has-look' : ''}">${ap ? apStage(ap, id) : id}</span>`;
}
function v3Podium(rows, value) {
  const top = [rows[1], rows[0], rows[2]].filter(Boolean);
  if (top.length < 2) return '';
  const open = r => r.ref && /^[A-Za-z0-9_-]{16,64}$/.test(r.ref) ? ` onclick="openPublicProfile('${r.ref}')"` : ' disabled';
  return `<ol class="v3-podium" aria-label="Тройка лидеров">${top.map(r => {
    const tag = r.kind==='chat' ? 'div' : 'button', attrs = r.kind==='chat' ? ' role="group"' : ` type="button"${open(r)}`;
    return `<li class="v3-pod is-p${r.place}${r.is_me ? ' is-me' : ''}"><${tag} class="v3-pod-btn"${attrs} aria-label="${r.place} место: ${esc(r.name)}, ${value(r)}">
    ${_v3PodId(r)}<small>${value(r)}</small></${tag}><i aria-hidden="true"></i></li>`;
  }).join('')}</ol>`;
}

// Пустой рейтинг: пьедестал ждёт первых — три пустых места с медалями и подсказка, как туда попасть
function v3PodiumEmpty(text) {
  return `<div class="v3-pod-empty"><ol class="v3-podium is-ghost" aria-hidden="true">${[2, 1, 3].map(p => `<li class="v3-pod is-p${p}"><span class="v3-pod-card"><span class="v3-pod-id"><span class="v3-ring"><svg viewBox="0 0 76 76"><circle cx="38" cy="38" r="35"/></svg><span class="v3-ava"></span><span class="v3-pod-medal">${p}</span></span><b class="v3-pod-name">?</b></span></span><i></i></li>`).join('')}</ol><p>${text}</p></div>`;
}

function _v3Word(n, one, few, many) { n = Math.abs(Number(n) || 0); return n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? few : many; }
// Карточка цели периода (Задания): кольцо «сделано из стольких» и награда за весь период рисованными валютами.
// Кольцо цвета текста: акцент экрана заданий — вкладка и «Забрать» (tools/test_questlog_visual_contract.py).
function v3GoalCard({ done, total, label, reward, claimed }) {
  const share = total ? Math.min(1, done / total) : 0, c = 2 * Math.PI * 30;
  const parts = [['mora', reward?.amount_mora, 'Моры'], ['essence', reward?.amount_essence, 'Эссенции']].filter(([, n]) => Number(n) > 0)
    .map(([k, n, w]) => `<span class="v3-goal-r">${v3Cur(k)}<b>${fmt(n)}</b><small>${w}</small></span>`);
  const keys = _sysFlags.content_chests_v1 ? Number(reward?.amount_keys || 0) : 0;
  if (keys) parts.push(`<span class="v3-goal-r"><span class="v3-goal-key">${typeof _CH_KEY_SVG !== 'undefined' ? _CH_KEY_SVG : ''}</span><b>${fmt(keys)}</b><small>${_v3Word(keys, 'ключ', 'ключа', 'ключей')}</small></span>`);
  return `<section class="v3-goal${done >= total && total ? ' is-full' : ''}" aria-label="${label}: ${done} из ${total}">
    <span class="v3-goal-ring"><svg viewBox="0 0 72 72" aria-hidden="true"><circle cx="36" cy="36" r="30"/><circle class="v3-goal-arc" cx="36" cy="36" r="30" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - share)).toFixed(1)}"/></svg><b>${done}<small>/${total}</small></b></span>
    <div class="v3-goal-tx"><small>${label}${claimed ? ' · получено' : ''}</small><div class="v3-goal-rs">${parts.join('') || '<span class="v3-goal-r"><small>награда появится позже</small></span>'}</div></div></section>`;
}

// Шапки статичной разметки (index.html: «Ещё», «Справка») помечены data-v3-hero="эмблема": созвездие и эмблема дорисовываются один раз
function v3DecorStatic() {
  document.querySelectorAll('[data-v3-hero]').forEach(h => {
    if (h.dataset.v3Done) return;
    h.dataset.v3Done = '1';
    h.insertAdjacentHTML('afterbegin', V3_SKY + v3Emblem(h.dataset.v3Hero));
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', v3DecorStatic); else v3DecorStatic();

// ── Набор «Тайное Знание»: сцены и фирменные детали трёх образов ────────────────────────────────────────────
// Три разных способа показать знание, три разные композиции (не «предмет слева + предмет справа»):
// Тихая Библиотека — диагональ: луч из высокого окна идёт через всю сцену, пыль живёт только в нём, внизу стол со свечой. Движение почти замерло.
// Лаборатория Алхимика — снизу вверх: эликсир кипит по всему низу, пузыри и пар поднимаются, на полу круг стихий, на SSS вспышка превращения.
// Живой Гримуар — вихрь: кольцо рун медленно вращается вокруг всего героя, страницы вырываются из книги на кафедре и улетают вверх, буквы всплывают.
// Средняя колонка (аватар, ник, значки) свободна: крупные предметы стоят у краёв и в самом низу. Картинки: tools/scene_art_f.py.
_scAdd('quiet_library', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'linear-gradient(200deg, #2a1d1299, transparent 46%), linear-gradient(0deg, #1c140c, #0f0c08 70%)'}],
  [2, 'sil i-libShelves', {l:'-6%',b:'-2%',w:'30%',h:'62%',o:.5}],
  [3, 'sil i-libWindow', {r:'1%',t:'6%',w:'16%',h:'50%',o:.32}],
  [3, 'band breathe', {l:'26%',t:'-20%',w:'30%',h:'150%',rot:'38deg',org:'50% 0%',o:.9,bg:'linear-gradient(90deg, transparent, #fff4dc14 30%, #fff4dc24 50%, #fff4dc14 70%, transparent)',dur:9}],
  [4, 'dot float', {l:'52%',t:'18%',s:'2px',c:'#fff4dc',o:.75,bs:_scBs([[-20,30,1,0,'#fff4dc'],[-44,62,1,0,'c'],[-70,96,1,0,'#fff4dc'],[-96,128,1,0,'c'],[-30,84,1,0,'#fff4dc'],[-58,140,1,0,'#fff4dc']]),dx:'6px',dy:'-8px',dur:14}],
  [4, 'dot float w2', {l:'46%',t:'30%',s:'1.5px',c:'#e9d3a3',o:.6,bs:_scBs([[-14,20,1,0,'#e9d3a3'],[-40,52,1,0,'#fff4dc'],[-64,88,1,0,'#e9d3a3'],[-88,120,1,0,'#fff4dc']]),dx:'-5px',dy:'-10px',dur:19,del:-7}],
  [5, 'sil i-libDesk', {r:'-2%',b:'-3%',w:'34%',h:'58%'}],
  [5, 'glow flicker', {r:'4%',b:'26%',w:'18%',h:'24%',c:'#ffd38a',k:'40%',dur:5}],
  [6, 'sil m i-libPage float', {l:'40%',t:'12%',w:'20px',h:'26px',c:'#fff4dc',o:.55,rot:'-12deg',dx:'-26px',dy:'18px',dur:17}],
  [7, 'glow drift', {l:'-14%',b:'4%',w:'46%',h:'40%',c:'#ffe3a8',k:'16%',dx:'6%',dur:21}],
  [7, 'dot twinkle', {l:'3%',b:'40%',s:'2px',c:'#e9d3a3',bs:_scBs([[18,40,2,0,'#e9d3a3'],[40,80,2,0,'c'],[8,118,2,0,'#e9d3a3']]),dur:6}],
]);
_scAdd('alchemist', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 120%, #3fcf8644, transparent 60%), linear-gradient(180deg, #050b08, #0b1a12)'}],
  [2, 'wave go i-alcLiquidTile m', {l:'0',b:'-3%',w:'calc(100% + 160px)',h:'15%',tw:'160px',c:'#3fcf86',o:.55,dur:6}],
  [3, 'wave go i-alcLiquidTile m rev w2', {l:'-160px',b:'-1%',w:'calc(100% + 160px)',h:'11%',tw:'160px',c:'#8cf2b0',o:.25,dur:9}],
  [3, 'sil m i-alcSigils st breathe', {l:'calc(50% - 130px)',b:'2%',w:'260px',h:'54px',c:'#8cf2b0',o:.3,dur:6}],
  [4, 'sil i-alcShelf', {r:'-4%',t:'4%',w:'22%',h:'40%',o:.8}],
  [4, 'dot rise', {l:'8%',b:'6%',s:'3px',c:'#8cf2b0',o:.8,bs:_scBs([[30,0,1,0,'#e9fff2'],[90,4,1,0,'#8cf2b0'],[150,-2,1,0,'#e9fff2'],[210,2,1,0,'#8cf2b0'],[270,0,1,0,'#e9fff2']]),dx:'4px',dy:'-46px',s0:'.6',s1:'1.2',dur:3.4}],
  [5, 'sil i-alcRetort', {r:'1%',b:'-2%',w:'28%',h:'56%'}],
  [5, 'glow flicker', {r:'9%',b:'-8%',w:'18%',h:'20%',c:'#d8973f',k:'46%',dur:2.4}],
  [6, 'dot rise w2', {r:'4%',b:'26%',s:'4px',c:'#8cf2b0',o:.5,bs:_scBs([[-6,-4,4,1,'#8cf2b0'],[4,-10,4,1,'#e9fff2']]),dx:'-14px',dy:'-90px',s0:'.6',s1:'2',dur:5}],
  [6, 'dot rise', {l:'40%',b:'2%',s:'2px',c:'#d8973f',bs:_scBs([[20,0,2,0,'#ffd88a'],[60,-6,2,0,'#d8973f'],[100,2,2,0,'#ffd88a']]),dx:'0px',dy:'-120px',s0:'1',s1:'.4',dur:6,del:-2}],
  [7, 'glow flash', {l:'-10%',t:'-10%',w:'120%',h:'120%',c:'#8cf2b0',k:'18%',dur:11}],
  [7, 'dot twinkle', {l:'calc(50% - 2px)',b:'8%',s:'3px',c:'#ffd88a',bs:_scBs([[-110,-6,3,1,'#ffd88a'],[110,-6,3,1,'#ffd88a'],[-60,-18,3,1,'#8cf2b0'],[60,-18,3,1,'#8cf2b0']]),dur:3}],
]);
_scAdd('grimoire', [
  [2, 'band', {l:'0',t:'0',w:'100%',h:'100%',bg:'radial-gradient(ellipse at 50% 60%, #7a52e033, transparent 62%), linear-gradient(180deg, #07050e, #120c22)'}],
  [2, 'dot twinkle', {l:'10%',t:'12%',s:'2px',c:'#ffe6a8',bs:_scBs([[60,40,1,0,'#ffe6a8'],[170,10,1,0,'c'],[240,70,1,0,'#ffe6a8'],[300,20,1,0,'a']]),dur:5.5}],
  [3, 'sil m i-grimRunes spin rev', {l:'calc(50% - 220px)',t:'calc(50% - 220px)',w:'440px',h:'440px',c:'#c9b2ff',o:.13,dur:150}],
  [4, 'sil i-grimLectern', {r:'-1%',b:'-3%',w:'30%',h:'52%'}],
  [4, 'sil i-grimCandles', {l:'-3%',b:'-3%',w:'20%',h:'34%',o:.9}],
  [5, 'glow flicker', {l:'0%',b:'14%',w:'16%',h:'20%',c:'#ffcf7a',k:'40%',dur:4}],
  [5, 'glow breathe', {r:'4%',b:'18%',w:'24%',h:'26%',c:'#c9b2ff',k:'30%',dur:5}],
  [6, 'sil m i-grimPage cross', {r:'12%',b:'26%',w:'18px',h:'24px',c:'#e9dcc0',o:.8,rot:'-16deg',fx:'0px',fy:'0px',tx:'-260px',ty:'-150px',dur:11}],
  [6, 'sil m i-grimPage cross w2', {r:'10%',b:'28%',w:'14px',h:'18px',c:'#ddcfae',o:.65,rot:'14deg',fx:'0px',fy:'0px',tx:'-200px',ty:'-190px',dur:14,del:-6}],
  [7, 'dot rise', {r:'15%',b:'30%',s:'2px',c:'#ffe6a8',bs:_scBs([[-8,0,2,0,'#ffe6a8'],[6,-6,2,0,'#c9b2ff'],[-2,-14,2,0,'#ffe6a8']]),dx:'-30px',dy:'-120px',s0:'1',s1:'.5',dur:5}],
  [7, 'sil m i-grimPage cross', {r:'14%',b:'24%',w:'16px',h:'20px',c:'#ffe6a8',o:.7,rot:'30deg',fx:'0px',fy:'0px',tx:'-320px',ty:'-90px',dur:17,del:-3}],
]);

// Фирменные детали (рамка аватара, холст -30..130, кольцо ≈ 57): свеча на оправе и лента-закладка; уроборос вокруг кольца и четыре стихии;
// раскрытая книга над кольцом листает сама себя, буквы уходят по дуге, руны на кольце загораются по очереди. Цвет и движение: skin-sig-d-v3.css.
(() => {
  const R = n => Math.round(n * 10) / 10;
  const xy = (r, deg) => [R(50 + r * Math.cos(deg * Math.PI / 180)), R(50 + r * Math.sin(deg * Math.PI / 180))];
  const pt = (r, deg) => xy(r, deg).join(' ');
  const svg = (name, inner) => `<svg class="sa sk-${name}" viewBox="-30 -30 160 160" aria-hidden="true">${inner}</svg>`;
  const arc = (r, a0, a1) => `M${pt(r, a0)}A${r} ${r} 0 ${(a1 - a0) % 360 > 180 ? 1 : 0} 1 ${pt(r, a1)}`;

  const [cx, cy] = xy(57, -40);
  const candlelit = svg('candle', `<g transform="translate(${cx} ${cy})">
    <path class="sk-wax" d="M-4.5 2V-14h9V2Z"/><path class="sk-drip" d="M-4.5-14q0 6 1.5 9 1.5-3 1.5-9M2-14q0 4 1.2 7 1.3-2 1.3-7"/>
    <path class="sk-wick" d="M0-14v-3"/><circle class="sk-halo" cx="0" cy="-21" r="9"/>
    <g class="sk-flame"><path class="sk-fl" d="M0-17q-4-5 0-11 4 6 0 11Z"/><path class="sk-core" d="M0-18q-1.6-2.4 0-5 1.6 2.6 0 5Z"/></g>
    <path class="sk-base" d="M-7 2h14l-2 3H-5Z"/></g>
    <g transform="translate(${pt(57, 128)})"><g class="sk-ribbon"><path class="sk-rib" d="M0 0q-2 10 1 20 2 8-1 16l-3 4 4-1 3 3 0-6q2-8-1-16-3-9-1-20Z"/></g></g>
    <g class="sk-mote"><circle cx="${R(cx - 6)}" cy="${R(cy - 30)}" r=".9"/><circle cx="${R(cx + 7)}" cy="${R(cy - 26)}" r=".7"/></g>`);

  const scales = Array.from({ length: 28 }, (_, i) => { const a = -70 + i * 11.5; return `<path class="sk-scale" transform="translate(${pt(64, a)}) rotate(${R(a + 90)})" d="M-2.4-1q2.4 2.6 4.8 0"/>`; }).join('');
  const elements = ['M-4 3 0-4 4 3Z', 'M-4-3 0 4 4-3Z', 'M-4 3 0-4 4 3ZM-3 0h6', 'M-4-3 0 4 4-3ZM-3 0h6']
    .map((d, i) => `<path class="sk-el sk-el${i}" transform="translate(${pt(77, 45 + i * 90)})" d="${d}"/>`).join('');
  const [hx, hy] = xy(64, -76);
  const ouroboros = svg('ouro', `<g class="sk-turn"><path class="sk-body" d="${arc(64, -70, 266)}"/><path class="sk-belly" d="${arc(64, -70, 266)}"/>${scales}
    <g transform="translate(${hx} ${hy}) rotate(14)"><path class="sk-head" d="M-5-5Q4-7 8 0Q4 7-5 5Q-3 0-5-5Z"/><circle class="sk-eye" cx="2" cy="-1.8" r="1"/><path class="sk-jaw" d="M8 0l-5 1.6"/></g></g>${elements}`);

  const glyphs = ['M0-3v6M0-1l2-2', 'M-2-3v6M-2-3l3 2-3 2', 'M2-3-2 0l4 3', 'M-2-3 2 3M2-3-2 3'];
  const runes = Array.from({ length: 8 }, (_, i) => `<path class="sk-rune" style="--i:${i}" transform="translate(${pt(61, -150 + i * 45)}) rotate(${-60 + i * 45})" d="${glyphs[i % 4]}"/>`).join('');
  const [bx, by] = xy(66, -128);
  const grimoire = svg('grim', `${runes}<g transform="translate(${bx} ${by}) rotate(-18)"><g class="sk-hover">
    <circle class="sk-aura" cx="0" cy="0" r="14"/>
    <path class="sk-cover" d="M-15 4-14-6Q-7-9 0-6Q7-9 14-6L15 4Q7 1 0 4Q-7 1-15 4Z"/>
    <path class="sk-pg" d="M-13 2-12.5-6Q-6-8.5 0-6V3Q-6 0-13 2Z"/><path class="sk-pg" d="M13 2 12.5-6Q6-8.5 0-6V3Q6 0 13 2Z"/>
    <path class="sk-ln" d="M-11-3q4-1.5 9 0M-11-.6q4-1.5 9 0M2-3q4-1.5 9 0M2-.6q4-1.5 9 0"/>
    <path class="sk-flip" d="M0-6Q6-8.5 12.5-6L13 2Q6 0 0 3Z"/><path class="sk-clasp" d="M15 0q4 0 4 4v8"/></g></g>
    <g class="sk-drift"><path class="sk-gl" style="--d:0s" transform="translate(${R(bx + 10)} ${R(by - 14)})" d="${glyphs[0]}"/><path class="sk-gl" style="--d:-2s" transform="translate(${R(bx + 20)} ${R(by - 8)})" d="${glyphs[2]}"/><path class="sk-gl" style="--d:-4s" transform="translate(${R(bx + 28)} ${R(by + 2)})" d="${glyphs[3]}"/></g>`);

  if (typeof _AP_DECOR !== 'undefined') Object.assign(_AP_DECOR, { candlelit: candlelit, ouroboros: ouroboros, grimoire: grimoire });
})();
