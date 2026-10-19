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
