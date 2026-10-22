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
var _V3_HEAD_EMB = { 'Задания': 'quests', 'Достижения': 'medal', 'Инвентарь': 'bag', 'Питомцы': 'paw', 'Промокоды': 'ticket', 'Экипировка': 'anvil' };
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

// Шапка-герой для экранов со своей разметкой (Топ, Магазин, Ещё, Настройки, Справка, Биржа…): эмблема, заголовок, подпись, созвездие
function v3Hero(kind, title, sub = '', { eyebrow = '', end = '', stat = '' } = {}) {
  return `<header class="v3-hero">${V3_SKY || ''}${v3Emblem(kind)}<div class="v3-hero-tx">${eyebrow ? `<small class="v3-hero-eb">${eyebrow}</small>` : ''}<h1 class="v3-title">${esc(title)}</h1>${sub ? `<p class="v3-head-s">${sub}</p>` : ''}</div>${stat}${end}</header>`;
}

// Подиум тройки лидеров (Топ и «Топ-10» в профиле): 2 · 1 · 3 с медалями; строки ниже — как раньше
function v3Podium(rows, value) {
  const top = [rows[1], rows[0], rows[2]].filter(Boolean);
  if (top.length < 2) return '';
  // нажатие открывает профиль игрока, ник — как в строке списка: скин, VIP и регалия (apWho, app.20.js)
  const open = r => r.ref && /^[A-Za-z0-9_-]{16,64}$/.test(r.ref) ? ` onclick="openPublicProfile('${r.ref}')"` : ' disabled';
  return `<ol class="v3-podium" aria-label="Тройка лидеров">${top.map(r => `<li class="v3-pod is-p${r.place}${r.is_me ? ' is-me' : ''}"><button type="button" class="v3-pod-btn"${open(r)} aria-label="${r.place} место: ${esc(r.name)}, ${value(r)}">
    <span class="v3-pod-medal" aria-hidden="true">${r.place}</span><b class="v3-pod-name">${typeof apWho === 'function' ? apWho(r) : esc(r.name)}</b><small>${value(r)}</small></button><i aria-hidden="true"></i></li>`).join('')}</ol>`;
}

// Пустой рейтинг: пьедестал ждёт первых — три пустых места с медалями и подсказка, как туда попасть
function v3PodiumEmpty(text) {
  return `<div class="v3-pod-empty"><ol class="v3-podium is-ghost" aria-hidden="true">${[2, 1, 3].map(p => `<li class="v3-pod is-p${p}"><span class="v3-pod-medal">${p}</span><b class="v3-pod-name">?</b><i></i></li>`).join('')}</ol><p>${text}</p></div>`;
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
