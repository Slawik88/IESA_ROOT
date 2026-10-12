// ── «Тропа» питомцев · главный экран, отправка, развилка, награда ──────────────────────────────
// Питомцы v2 (/pets-v2/*, флаг pets_v2): Следы дня, три слота занятий, список питомцев, отправка в путь, развилка экспедиции и экран награды. Рисуется в #pg-pets, на экране вкладки «Питомцы».
// Карточка питомца, сборка, кормление, Лагерь, Выслеживание и Испытание недели живут в app.41.js (они подключают себя в _TR_VIEWS). Цифры правил приходят в ответе (me.rules): клиент не хранит их копию.
// Флаг выключен или сервер ответил «Тропа пока закрыта»: остаётся прежний экран питомцев (openPetsV1 из app.12.js). Стили: trail-v3.css.
let _tr = { me: null, view: 'hub', pet: 0, seq: 0, skew: 0, keys: {}, scroll: 0, bad: '', busy: false, send: null, pick: null, opener: null, late: {} };
let _trKeys = null;
const _trClassic = window.openPetsV1;
const _trE = _profileEsc;
const _TR_VIEWS = {};
const _TR_ENTER = {};   // подготовка подэкрана при входе с главного (app.41.js: Выслеживание и Испытание начинают с чистого листа)
const _TR_KIND = { trek: 'Поход', expedition: 'Экспедиция', watch: 'Дозор' };
const _TR_ROUTE = { forest: ['🌲', 'Лес'], pass: ['⛰️', 'Перевал'], ruins: ['🏛️', 'Руины'], swamp: ['🌿', 'Болота'], any: ['✦', 'Любой'] };
const _TR_PATH = { careful: 'Осторожный', steady: 'Ровный', bold: 'Рискованный' };
const _TR_FIND = { mora: ['🪙', 'Мора', 'mora'], diamond: ['💎', 'Алмазы', 'diamonds'], essence: ['💧', 'Эссенция', 'essence'], treat: ['🍖', 'Лакомства'], talisman: ['🧿', 'Талисманы'] };
const _TR_FEM = new Set(['salt_fox', 'mirror_owl', 'void_lynx']);   // лисица, сова, рысь: «вернулась», остальные виды мужского рода
Object.assign(_V3_PATHS, {
  tent: '<path d="M3.5 19.5L12 5l8.5 14.5zM12 5v14.5M9 19.5l3-5 3 5"/>',
  scope: '<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="2.4"/><path d="M12 2.5v3.2M12 18.3v3.2M2.5 12h3.2M18.3 12h3.2"/>',
});

const _trWord = (n, one, few, many) => { const m = Math.abs(n) % 100, d = m % 10; return m > 10 && m < 20 ? many : d === 1 ? one : d > 1 && d < 5 ? few : many; };
const _trMult = n => String(n).replace('.', ',');
const _trFem = (p, he, she) => _TR_FEM.has(p?.species_id) ? she : he;
function _trPet(id) { return (_tr.me?.pets || []).find(p => p.id === Number(id)); }
function _trAct(id) { return (_tr.me?.activities || []).find(a => a.id === id); }
const _trSec = (title, link) => `<div class="v3-sec"><span class="v3-eyebrow">${title}</span>${link || ''}</div>`;
// Время сервера приходит как «2026-10-12 10:00:00.123456+00:00» (в ответе игроку) или ISO: Safari не разбирает пробел вместо T, а Date держит миллисекунды
function _trTime(value) { const t = Date.parse(String(value || '').replace(' ', 'T').replace(/(\.\d{3})\d+/, '$1')); return Number.isFinite(t) ? t : NaN; }
const _trNow = () => Date.now() + _tr.skew;   // часы телефона могут идти неверно: таймеры считаются от времени сервера
function _trDur(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000)), h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60);
  return h ? `${h}\u00a0ч ${String(m).padStart(2, '0')}\u00a0мин` : m ? `${m}\u00a0мин` : `${s}\u00a0с`;
}
const _trLeft = act => _trTime(act.ends_at) - _trNow();

// ── Вход: вкладка «Питомцы» ведёт сюда, пока включён флаг pets_v2 ───────────────────────────────
window.openPetsV1 = function () {
  if (_sysFlags.pets_v2 !== true) return _trClassic.apply(this, arguments);
  return openTrail();
};
function openTrail() {
  switchPage('pets');
  const root = el('pg-pets'); if (!root) return Promise.resolve();
  _tr.view = 'hub'; _tr.send = null; _tr.pick = null;
  if (_tr.me) _trRender();
  else { root.innerHTML = '<div class="sk" style="height:110px;border-radius:18px;margin-top:8px"></div><div class="sk" style="height:150px;border-radius:18px;margin-top:22px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:22px"></div>'; v3EnterSync(root); }
  return _trLoad().then(ok => { if (ok) _trRender(); });
}
function _trLoad() {
  const mine = ++_tr.seq;
  return api('/pets-v2/me').then(me => {
    if (mine !== _tr.seq) return false;
    _tr.me = me; _tr.bad = '';
    const at = _trTime(me.now); if (Number.isFinite(at)) _tr.skew = at - Date.now();
    return true;
  }).catch(error => {
    if (mine !== _tr.seq) return false;
    const text = typeof error === 'string' ? error : 'Нет связи. Проверьте интернет и повторите.';
    if (/Тропа пока закрыта/.test(text)) { _sysFlags.pets_v2 = false; _tr.me = null; _trClassic(); return false; }   // флаг выключили, пока приложение было открыто
    _tr.bad = text;
    if (_tr.me) toast(text, false); else _trPaintFail(text);
    return false;
  });
}
function _trPaintFail(text) {
  const root = el('pg-pets'); if (!root || _activePage !== 'pets') return;
  root.innerHTML = `<header class="v3-screen-head"><span class="v3-eyebrow">Питомцы</span><h1 class="v3-title">Тропа</h1></header><div class="v3-empty" role="alert"><b>Тропа не загрузилась</b><span>${_trE(text)}</span> <button type="button" class="v3-link" onclick="openTrail()">Повторить</button></div>`;
  v3EnterSync(root);
}
function _trRefresh() { return _trLoad().then(ok => { if (ok) _trRender(); return ok; }); }
function _trRender() {
  const root = el('pg-pets'); if (!root || _activePage !== 'pets' || !_tr.me) return;
  const view = _TR_VIEWS[_tr.view] || _TR_VIEWS.hub;
  root.innerHTML = view(_tr.me);
  v3EnterSync(root);
}

// Подэкраны (карточка питомца, Лагерь…) лежат внутри той же страницы: «‹ Тропа» возвращает на главный и на то место, где игрок был
function trailGo(view, id) {
  _haptic('select');
  if (_tr.view === 'hub') _tr.scroll = window.scrollY;
  _tr.view = view; _tr.pet = Number(id) || 0;
  if (_tr.me && _TR_ENTER[view]) _TR_ENTER[view]();
  _trRender(); try { window.scrollTo(0, 0); } catch (_) { /* прокрутка недоступна */ }
}
function trailPet(id) { trailGo('pet', id); }
// Системная кнопка «Назад» (app.01.js, navBack) сначала закрывает окно или подэкран Тропы и только потом уводит со страницы
_backHooks.push(() => {
  if (_activePage !== 'pets' || _sysFlags.pets_v2 !== true) return false;
  const confirm = document.getElementById('cf-sheet');
  if (confirm) { confirm.querySelector('.cf-no')?.click(); return true; }
  if (document.getElementById('tr-sheet')) { trailClose(); return true; }
  if (_tr.view !== 'hub') { trailBack(); return true; }
  return false;
});
function trailBack() {
  _haptic('select');
  const up = _tr.view === 'build' || _tr.view === 'feed' ? 'pet' : 'hub';
  _tr.view = up; _trRender();
  try { window.scrollTo(0, up === 'hub' ? _tr.scroll : 0); } catch (_) { /* прокрутка недоступна */ }
}
const _trBack = (label = 'Тропа') => `<div class="eyebrow-row"><button type="button" class="v3-link" onclick="trailBack()" aria-label="Назад: ${label}">‹ ${label}</button></div>`;

// ── Состояние питомца: у ведущего своё занятие, у Спутника занятие ведущего (run_id у обоих) ──────────
function _trState(p) {
  const act = p.run_id ? _trAct(p.run_id) : null;
  if (!act) return { k: 'free', label: 'В лагере' };
  const lead = act.pet_id === p.id;
  if (act.ready) return { k: 'ready', act, lead, label: lead ? _trFem(p, 'Вернулся', 'Вернулась') : 'Спутник вернулся' };
  return { k: 'busy', act, lead, label: lead ? 'В пути' : 'Идёт спутником' };
}
function _trMeter(fraction, o = {}) {
  const p = Math.max(0, Math.min(1, Number(fraction) || 0));
  return `<div class="tr-meter${o.cls ? ` ${o.cls}` : ''}" style="--p:${p.toFixed(3)}"${o.label ? ` role="img" aria-label="${_trE(o.label)}"` : ' aria-hidden="true"'}><span><i></i></span>${o.notch != null ? `<b style="left:${(o.notch * 100).toFixed(1)}%"></b>` : ''}</div>`;
}

// ── Главный экран ──────────────────────────────────────────────────────────────────────────────
function _trHead() {
  return `<header class="v3-screen-head"><span class="v3-eyebrow">Питомцы</span><h1 class="v3-title">Тропа${v3GlintMark('Тропа')}</h1></header>`;
}
// Следы дня видны на каждом экране Тропы. Упёрлись в норму: спокойная строка, без красного (питомцы устали расти, награды остаются)
function _trTraces(me, compact) {
  const d = me.daily || {}, r = me.rules || {}, max = Number(d.max) || 625, cur = Math.max(0, Math.min(max, Number(d.credited) || 0)), soft = Number(r.daily_soft_from) || 500;
  const full = cur >= max - 0.05, rate = Math.round((Number(r.daily_soft_rate) || 0.25) * 100), shown = full ? max : Math.floor(cur);
  const note = full ? 'На сегодня питомцы устали расти. Награды остаются.'
    : cur >= soft ? `Следы идут медленнее: теперь засчитывается ${rate}\u00a0%.`
    : cur < 1 ? 'Сегодня Следов ещё нет. Отправьте питомца в путь.'
    : `По полной ставке ещё ${fmt(Math.max(0, Math.floor(soft - cur)))}. Дальше засчитывается ${rate}\u00a0%.`;
  const label = `Следы за сегодня: ${fmt(shown)} из ${fmt(max)}`;
  if (compact) return `<p class="tr-line" aria-label="${_trE(label)}"><span>Следы за сегодня</span><b>${fmt(shown)}</b><small>из ${fmt(max)}</small></p>`;
  return `<section class="tr-sec tr-traces" aria-label="Следы за сегодня">${_trSec('Следы за сегодня')}<p class="tr-big"><b>${fmt(shown)}</b><span>из ${fmt(max)}</span></p>${_trMeter(cur / max, { notch: soft / max, label })}<p class="tr-note">${note}</p></section>`;
}
function _trSlot(act) {
  const pet = _trPet(act.pet_id); if (!pet) return '';
  const mate = (_tr.me.pets || []).find(p => p.id !== pet.id && p.run_id === act.id), route = act.route ? _TR_ROUTE[act.route] : null;
  const what = [_TR_KIND[act.kind] || act.kind, `${act.hours}\u00a0ч`, route ? `${route[0]}\u00a0${route[1]}` : ''].filter(Boolean).join(' · ');
  const end = act.ready
    ? `<button type="button" class="v3-pill v3-pill--sm" data-run="${_trE(act.id)}" onclick="trailRun(this)">${act.kind === 'expedition' ? 'Выбрать путь' : 'Забрать'}</button>`
    : `<span class="tr-left"><small>осталось</small><b data-end="${_trTime(act.ends_at)}" data-id="${_trE(act.id)}">${_trDur(_trLeft(act))}</b></span>`;
  return `<li class="tr-row tr-slot is-${act.ready ? 'ready' : 'busy'}"><span class="tr-ic" aria-hidden="true">${_trE(pet.icon)}</span><span class="tr-nm"><b>${_trE(pet.name)}</b><small>${_trE(what)}</small>${mate ? `<small>Спутник: ${_trE(mate.name)}</small>` : ''}</span><span class="tr-end">${end}</span></li>`;
}
function _trFreeSlot(me, sendable) {
  const hint = sendable ? `${sendable} ${_trWord(sendable, 'питомец готов', 'питомца готовы', 'питомцев готовы')} к пути` : 'Свободных питомцев с силами нет';
  return `<li class="tr-row tr-slot is-free"><span class="tr-ic tr-ic--empty" aria-hidden="true"></span><span class="tr-nm"><b>Свободный слот</b><small>${hint}</small></span><span class="tr-end">${sendable ? '<button type="button" class="v3-link tr-go" onclick="trailSend()">Отправить ›</button>' : ''}</span></li>`;
}
function _trMinCost(me) { return Math.min(...Object.values(me.rules.energy.run), ...Object.values(me.rules.energy.watch)); }
function _trSlots(me) {
  const acts = me.activities || [], slots = Number(me.slots) || 3, min = _trMinCost(me);
  const sendable = (me.pets || []).filter(p => !p.run_id && p.energy >= min).length;
  const free = Math.max(0, slots - acts.length);
  const rows = acts.map(_trSlot).join('') + Array.from({ length: free }, () => _trFreeSlot(me, sendable)).join('');
  return `<section class="tr-sec" id="tr-slots">${_trSec('Занятия', `<span class="tr-count">${acts.length} из ${slots}</span>`)}<ul class="tr-list" aria-label="Занятия">${rows}</ul></section>`;
}
function _trLevelLine(p) {
  if (p.level >= (_tr.me.rules.max_level || 30)) return '<small class="tr-sub">Высший уровень</small>';
  if (p.level >= p.ceiling) return `<small class="tr-sub">Ждёт Связи: ${p.bond_days} из ${p.next_gate_days} дн.</small>`;
  return _trMeter(p.xp / p.next_cost, { cls: 'tr-meter--xp' });
}
function _trPetRow(p) {
  const s = _trState(p), min = _trMinCost(_tr.me), low = p.energy < min;
  const say = `${p.name}, уровень ${p.level}, ${s.label.toLowerCase()}, силы ${Math.round(p.energy)} из ${p.energy_max}`;
  return `<li><button type="button" class="tr-row tr-pet is-${s.k}${low ? ' is-low' : ''}" onclick="trailPet(${p.id})" aria-label="${_trE(say)}"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span class="tr-nm"><b>${_trE(p.name)}</b><small>Ур.\u00a0${p.level} · <em class="tr-s">${s.label}</em></small>${_trLevelLine(p)}</span><span class="tr-en" aria-hidden="true"><b>${Math.round(p.energy)}</b><small>/${p.energy_max}</small>${_trMeter(p.energy / p.energy_max, { cls: 'tr-meter--sm' })}${low ? '<em>мало сил</em>' : ''}</span></button></li>`;
}
function _trPets(me) {
  const rank = { ready: 0, free: 1, busy: 2 }, pets = (me.pets || []).slice().sort((a, b) => rank[_trState(a).k] - rank[_trState(b).k] || b.level - a.level || a.id - b.id);
  const count = k => pets.filter(p => _trState(p).k === k).length, parts = [[count('ready'), 'Вернулись'], [count('free'), 'В лагере'], [count('busy'), 'В пути']].filter(x => x[0]);
  return `<section class="tr-sec" id="tr-pets">${_trSec(`Питомцы · ${pets.length}`)}${parts.length ? `<p class="tr-note">${parts.map(x => `${x[1]}: ${x[0]}`).join(' · ')}</p>` : ''}<ul class="tr-list">${pets.map(_trPetRow).join('')}</ul></section>`;
}
function _trEmpty() {
  return `<section class="tr-sec"><div class="v3-empty tr-empty"><b>Питомцев пока нет, их можно получить в сундуках.</b>${_sysFlags.content_chests_v1 === true ? '<button type="button" class="v3-link" onclick="openChestsV1()">К сундукам ›</button>' : ''}</div></section>`;
}
function _trTags(t) { return [(_TR_ROUTE[t.route] || [])[1], `${t.tempo}\u00a0ч`, t.style === 'careful' ? 'осторожный путь' : 'рискованный путь'].filter(Boolean).join(' · '); }
function _trMore(me) {
  const camp = me.camp || {}, lv = camp.levels || {}, job = camp.job, pets = (me.pets || []).length, trial = me.trial || {}, track = me.track || {};
  const campHint = job ? (job.done ? 'Стройка завершена' : `Идёт стройка · осталось <span data-end="${_trTime(job.ends_at)}" data-id="camp-${_trTime(job.ends_at)}">${_trDur(_trTime(job.ends_at) - _trNow())}</span>`)
    : `Лежанка ${lv.lounge || 0} · Указатели ${lv.markers || 0} · Мастерская ${lv.workshop || 0}`;
  const trackHint = track.open ? 'Игра не закончена, можно продолжить' : track.attempts_left ? `Попыток сегодня: ${track.attempts_left} из ${me.rules.track.daily}` : 'Попытки на сегодня закончились';
  const trialHint = trial.done ? 'На этой неделе сдано' : trial.tags ? _trE(_trTags(trial.tags)) : '';
  const rows = [_v3Row('tent', 'Лагерь', "trailGo('camp')", campHint)];
  if (pets) rows.push(_v3Row('scope', 'Выслеживание', "trailGo('track')", trackHint), _v3Row('trophy', 'Испытание недели', "trailGo('trial')", trialHint));
  return `<section class="tr-sec tr-more">${_trSec('Ещё')}${rows.join('')}</section>`;
}
_TR_VIEWS.hub = me => `${_trHead()}${_trTraces(me)}${(me.pets || []).length ? `${_trSlots(me)}${_trPets(me)}` : _trEmpty()}${_trMore(me)}`;

// Секундомер: правит только текст таймеров (разметку не пересобирает). Время вышло, а сервер ещё не отметил занятие готовым: просим свежий ответ, не чаще раза в 4 секунды
setInterval(() => {
  if (_activePage !== 'pets' || document.hidden || !_tr.me) return;
  const now = _trNow();
  document.querySelectorAll('#pg-pets [data-end]').forEach(node => {
    const left = Number(node.dataset.end) - now;
    node.textContent = _trDur(left);
    const id = node.dataset.id || '';
    if (left <= 0 && id && now - (_tr.late[id] || 0) > 4000 && (_tr.late[`${id}#`] = (_tr.late[`${id}#`] || 0) + 1) <= 6) { _tr.late[id] = now; _trRefresh(); }
  });
}, 1000);

// ── Окна (листы): основа та же, что у подтверждения траты ───────────────────────────────────────
function trailClose(now) {
  const host = document.getElementById('tr-sheet'); if (!host) return;
  if (_trKeys) { document.removeEventListener('keydown', _trKeys, true); _trKeys = null; }
  const opener = _tr.opener; _tr.opener = null;
  const back = () => { if (opener && document.contains(opener)) opener.focus({ preventScroll: true }); };
  if (now || typeof v3Dismiss !== 'function') { host.remove(); back(); } else v3Dismiss(host, back);
}
const _trSheetHtml = (title, body, foot) => `<div class="tr-sbody"><div class="tr-shead"><h2 id="tr-sheet-t">${title}</h2><button type="button" class="v3-link" onclick="trailClose()">Закрыть</button></div>${body}</div>${foot ? `<div class="tr-foot">${foot}</div>` : ''}`;
function _trSheet(html) {
  const keep = document.getElementById('tr-sheet') ? _tr.opener : document.activeElement;
  trailClose(true); _tr.opener = keep;
  const host = document.createElement('div'); host.id = 'tr-sheet'; host.className = 'lk-sheet-back';
  host.innerHTML = `<section class="lk-sheet tr-sheet" role="dialog" aria-modal="true" aria-labelledby="tr-sheet-t" tabindex="-1">${html}</section>`;
  host.addEventListener('click', e => { if (e.target === host) trailClose(); });
  _trKeys = e => {
    if (document.getElementById('cf-sheet')) return;   // сверху окно подтверждения: клавиши принадлежат ему
    if (e.key === 'Escape') { e.preventDefault(); trailClose(); return; }
    if (e.key !== 'Tab') return;
    const items = [...host.querySelectorAll('button:not([disabled])')], first = items[0], last = items[items.length - 1];
    if (!first) return;
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', _trKeys, true);
  document.body.appendChild(host); host.firstElementChild.focus({ preventScroll: true });
}
// Выбор внутри окна перерисовывает его содержимое; прокрутка и фокус остаются на месте
function _trRepaint(html) {
  const sheet = document.querySelector('#tr-sheet .tr-sheet'); if (!sheet) return _trSheet(html);
  const body = sheet.querySelector('.tr-sbody'), top = body ? body.scrollTop : 0, key = document.activeElement?.dataset?.f;
  sheet.innerHTML = html;
  const next = sheet.querySelector('.tr-sbody'); if (next) next.scrollTop = top;
  (key && sheet.querySelector(`[data-f="${key}"]`) || sheet).focus({ preventScroll: true });
}

// ── Действия: один номер операции на одно действие ───────────────────────────────────────────────
// Номер (action_id) живёт, пока сервер не ответил: повтор после обрыва связи уходит с тем же номером и не списывает второй раз. Любой ответ сервера, в том числе отказ правил, номер снимает.
function _trKey(...parts) {
  const k = parts.join(':');
  return _tr.keys[k] ||= { k, id: `tr-${String(parts[0]).slice(0, 12)}-${globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2, 10)}` };
}
function _trPost(path, body, ...parts) {
  const key = _trKey(...parts);
  return api(`/pets-v2/${path}`, { method: 'POST', body: JSON.stringify({ ...body, action_id: key.id }) }).then(
    data => { delete _tr.keys[key.k]; return data; },
    error => { if (typeof error === 'string') delete _tr.keys[key.k]; throw error; });
}
async function _trRun(button, job) {
  if (_tr.busy) return;
  _tr.busy = true; if (button) button.disabled = true;
  try { return await job(); } finally { _tr.busy = false; if (button && button.isConnected) button.disabled = false; }
}
// Отказ правил (HTTP 409) показывается дословно: внутри окна строкой над кнопкой, на экране тостом. Состояние могло устареть, поэтому тихо обновляем данные
function _trFail(error) {
  const text = typeof error === 'string' ? error : 'Нет связи. Повторите: операция не продублируется.';
  _haptic('error');
  const box = document.querySelector('#tr-sheet .tr-err');
  if (box) { box.textContent = text; box.hidden = false; } else toast(text, false);
  if (typeof error === 'string') _trRefresh();
}

// ── Отправка ─────────────────────────────────────────────────────────────────────────────────────────
const _trCost = (kind, hours) => Number(_tr.me.rules.energy[kind === 'watch' ? 'watch' : 'run'][hours]) || 0;
function trailSend(petId) {
  const me = _tr.me; if (!me) return;
  const free = (me.pets || []).filter(p => !p.run_id), min = _trMinCost(me);
  const pick = petId ? _trPet(petId) : free.filter(p => p.energy >= min).sort((a, b) => b.energy - a.energy)[0] || free[0];
  _tr.send = { pet: pick ? pick.id : 0, kind: 'trek', hours: 3, route: '', routeSet: false, comp: 0 };
  _trSendFit();
  _trSheet(_trSendHtml());
}
// Длина по умолчанию: самая долгая из тех, что питомцу по силам (длинный поход выгоднее по Следам на единицу сил); маршрут по умолчанию любимый
function _trSendFit() {
  const s = _tr.send, pet = _trPet(s.pet), me = _tr.me, list = s.kind === 'watch' ? me.durations.watch : me.durations.run;
  if (!list.includes(s.hours)) s.hours = list[0];
  if (pet) { const fit = list.filter(h => _trCost(s.kind, h) <= pet.energy); if (fit.length && !s.fitted) { s.hours = fit[fit.length - 1]; s.fitted = true; } }
  if (!s.routeSet) s.route = pet && pet.favorite_route !== 'any' ? pet.favorite_route : (me.routes || [])[0] || 'forest';
}
function trailSendSet(key, value) {
  const s = _tr.send; if (!s) return;
  _haptic('select');
  if (key === 'pet') { s.pet = Number(value); s.comp = 0; s.fitted = false; }
  else if (key === 'kind') { s.kind = value; s.fitted = false; if (value === 'watch') s.comp = 0; }
  else if (key === 'hours') { s.hours = Number(value); s.fitted = true; }
  else if (key === 'route') { s.route = value; s.routeSet = true; }
  else if (key === 'comp') s.comp = Number(value);
  _trSendFit(); _trRepaint(_trSendHtml());
}
function _trSendHtml() {
  const me = _tr.me, s = _tr.send, rules = me.rules, pet = _trPet(s.pet), watch = s.kind === 'watch';
  const free = (me.pets || []).filter(p => !p.run_id), min = _trMinCost(me), cost = _trCost(s.kind, s.hours), pairCost = Number(rules.energy.pair) || 10;
  const slotsLeft = Math.max(0, (Number(me.slots) || 3) - (me.activities || []).length), mate = !watch && s.comp ? _trPet(s.comp) : null;
  const radio = (on, f, click, inner, cls = 'tr-chip') => `<button type="button" class="${cls}" role="radio" aria-checked="${on}" data-f="${f}" onclick="${click}">${inner}</button>`;
  const pets = free.map(p => radio(p.id === s.pet, `pet-${p.id}`, `trailSendSet('pet',${p.id})`, `<span aria-hidden="true">${_trE(p.icon)}</span><b>${_trE(p.name)}</b><small>${Math.round(p.energy)} из ${p.energy_max}</small>`, `tr-chip tr-chip--i${p.energy < min ? ' is-dim' : ''}`)).join('');
  const kinds = ['trek', 'expedition', 'watch'].map(k => radio(s.kind === k, `kind-${k}`, `trailSendSet('kind','${k}')`, _TR_KIND[k], 'tr-seg-b')).join('');
  const note = { trek: 'Награда сразу, решений нет.', expedition: `На развилке вы выберете путь: награда больше, но есть риск. Следы ×${_trMult(rules.xp.expedition)}.`, watch: 'Долгий дозор без маршрута, для тех, кто заходит раз в день.' }[s.kind];
  const hours = (watch ? me.durations.watch : me.durations.run).map(h => radio(h === s.hours, `hours-${h}`, `trailSendSet('hours',${h})`, `<b>${h}\u00a0ч</b><small>${_trCost(s.kind, h)} сил</small>`, `tr-chip tr-chip--c${pet && _trCost(s.kind, h) > pet.energy ? ' is-dim' : ''}`)).join('');
  const fav = r => pet && (pet.favorite_route === r || pet.favorite_route === 'any');
  const routes = (me.routes || []).map(r => radio(r === s.route, `route-${r}`, `trailSendSet('route','${r}')`, `<span aria-hidden="true">${_TR_ROUTE[r][0]}</span><b>${_TR_ROUTE[r][1]}</b>${fav(r) ? '<small>любимый</small>' : ''}`, 'tr-chip tr-chip--i')).join('');
  const mates = free.filter(p => p.id !== s.pet && p.energy >= pairCost);
  let pair = '';
  if (!watch) {
    const need = me.pair?.need || 5;
    pair = me.pair?.unlocked
      ? `<div class="tr-grp"><span class="v3-eyebrow">Спутник</span><div class="tr-chips" role="radiogroup" aria-label="Спутник">${radio(!s.comp, 'comp-0', "trailSendSet('comp',0)", '<b>Без спутника</b>')}${mates.map(p => radio(p.id === s.comp, `comp-${p.id}`, `trailSendSet('comp',${p.id})`, `<span aria-hidden="true">${_trE(p.icon)}</span><b>${_trE(p.name)}</b><small>${Math.round(p.energy)} сил</small>`, 'tr-chip tr-chip--i')).join('')}</div><p class="tr-note">Спутник тратит ${pairCost} сил и получает ${Math.round((rules.pair_share || .3) * 100)}\u00a0% Следов.</p></div>`
      : `<p class="tr-note tr-hint">Спутник открывается при ${need} разных видах питомцев, сейчас их ${me.pair?.species || 0}.</p>`;
  }
  const base = watch ? rules.xp.watch[s.hours] : rules.xp.run[s.hours], mods = [];
  if (s.kind === 'expedition') mods.push(`экспедиция ×${_trMult(rules.xp.expedition)}`);
  if (!watch && fav(s.route)) mods.push(`любимый маршрут +${Math.round((rules.affinity_bonus || .2) * 100)}\u00a0%`);
  const enough = pet && pet.energy >= cost, why = !pet ? 'Выберите питомца.' : !slotsLeft ? 'Все слоты заняты.' : !enough ? `Не хватает сил: нужно ${cost}, у питомца ${Math.floor(pet.energy)}.` : mate && mate.energy < pairCost ? `Спутнику нужно ${pairCost} сил.` : '';
  const summary = pet ? `<dl class="cf-rows tr-sum"><div><dt>Силы</dt><dd>${Math.round(pet.energy)} → ${Math.max(0, Math.round(pet.energy - cost))} из ${pet.energy_max}</dd></div>${mate ? `<div><dt>Силы спутника</dt><dd>${Math.round(mate.energy)} → ${Math.round(mate.energy - pairCost)}</dd></div>` : ''}<div><dt>Базовые Следы${mods.length ? `<small>${mods.join(' · ')}</small>` : ''}</dt><dd>${fmt(base)}</dd></div></dl>` : '';
  const body = `<div class="tr-grp"><span class="v3-eyebrow">Кто идёт</span>${free.length ? `<div class="tr-chips" role="radiogroup" aria-label="Кто идёт">${pets}</div>` : '<p class="tr-note">Свободных питомцев нет: все в пути или ждут награды.</p>'}</div>
    <div class="tr-grp"><span class="v3-eyebrow">Что делать</span><div class="tr-seg" role="radiogroup" aria-label="Что делать">${kinds}</div><p class="tr-note">${note}</p></div>
    <div class="tr-grp"><span class="v3-eyebrow">Сколько</span><div class="tr-chips tr-chips--3" role="radiogroup" aria-label="Сколько часов">${hours}</div></div>
    ${watch ? '' : `<div class="tr-grp"><span class="v3-eyebrow">Куда</span><div class="tr-chips tr-chips--2" role="radiogroup" aria-label="Маршрут">${routes}</div></div>`}${pair}${summary}`;
  const foot = `${why ? `<p class="tr-note tr-why" role="status">${_trE(why)}</p>` : ''}<p class="tr-err" role="alert" hidden></p><button type="button" class="v3-pill v3-pill--full" onclick="trailSendGo(this)"${why ? ' disabled' : ''}>Отправить в путь</button>`;
  return _trSheetHtml('Отправить в путь', body, foot);
}
function trailSendGo(button) {
  const s = _tr.send, pet = s && _trPet(s.pet); if (!pet) return;
  const watch = s.kind === 'watch', body = { pet_id: pet.id, kind: s.kind, hours: s.hours, route: watch ? null : s.route };
  if (!watch && s.comp) body.companion_id = s.comp;
  _trRun(button, () => _trPost('start', body, 'start', pet.id, s.kind, s.hours, body.route || '', body.companion_id || 0).then(r => {
    _haptic('success'); trailClose();
    const route = body.route ? ` · ${_TR_ROUTE[body.route][1]}` : '';
    toast(`${pet.name}: ${_TR_KIND[s.kind].toLowerCase()} на ${s.hours}\u00a0ч${route}`, true, { icon: pet.icon });
    return _trRefresh();
  }).catch(_trFail));
}

// ── Возвращение: «Забрать» у похода и дозора, развилка у экспедиции ───────────────────────────────────
function trailRun(button) {
  const act = _trAct(button.dataset.run); if (!act) return;
  if (act.kind === 'expedition') _trDecision(act);
  else _trClaim(act, null, button);
}
// Что повышает и понижает шанс (для уровней с подсказкой «факторы» и выше). Только факты о питомце из того же ответа, процентов сюда клиент не добавляет
function _trFactors(pet, act) {
  const up = [], down = [], share = pet.energy / Math.max(1, pet.energy_max);
  if (act.route && (pet.favorite_route === act.route || pet.favorite_route === 'any')) up.push('любимое место');
  if (pet.fed_favorite) up.push('сыт любимым');
  if (pet.calling === 'guardian') up.push('Хранитель');
  if (share >= 0.8) up.push('много сил'); else if (share < 0.5) down.push('мало сил');
  return { up, down };
}
function _trDecision(act) {
  const pet = _trPet(act.pet_id); if (!pet) return;
  _tr.pick = { run: act.id, path: '' };
  _trSheet(_trDecisionHtml(act, pet));
}
const _TR_SIGN = { 'Надёжно': 'is-good', 'Скорее удастся': 'is-good', 'Как повезёт': 'is-mid', 'Рискованно': 'is-warn', 'Отчаянно': 'is-warn' };
function _trDecisionHtml(act, pet) {
  const rules = _tr.me.rules, dec = act.decision || null, chosen = _tr.pick.path, route = act.route ? _TR_ROUTE[act.route] : null;
  const fx = dec && dec.detail !== 'sign' ? _trFactors(pet, act) : null;
  const chips = fx && (fx.up.length || fx.down.length) ? `<p class="tr-fxs" aria-label="Что влияет на шанс">${fx.up.map(t => `<span class="tr-fx is-up">+ ${_trE(t)}</span>`).join('')}${fx.down.map(t => `<span class="tr-fx is-down">− ${_trE(t)}</span>`).join('')}</p>` : '';
  const opts = ['careful', 'steady', 'bold'].map(path => {
    const h = dec?.paths?.[path] || {}, reward = rules.paths[path].reward, loss = rules.paths[path].energy_loss;
    const odds = h.chance != null ? `${_trMult(h.chance)}\u00a0%` : h.range ? `${h.range[0]}–${h.range[1]}\u00a0%` : '';
    const sub = `Награда ×${_trMult(reward[0])}, при неудаче ${reward[2] > 0 ? `×${_trMult(reward[2])}` : 'без награды'}${loss ? `, −${loss} сил` : ''}`;
    return `<button type="button" class="tr-opt" role="radio" aria-checked="${chosen === path}" data-f="path-${path}" onclick="trailPath('${path}')"><span class="tr-opt-t"><b>${_TR_PATH[path]}</b><small>${sub}</small></span>${h.sign ? `<span class="tr-sign ${_TR_SIGN[h.sign] || ''}">${_trE(h.sign)}${odds ? `<small>${odds}</small>` : ''}</span>` : ''}</button>`;
  }).join('');
  const lead = `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(pet.icon)}</span><span><b>${_trE(pet.name)} ${_trFem(pet, 'вернулся', 'вернулась')}</b><small>${route ? `${route[1]} · ` : ''}силы ${Math.round(pet.energy)} из ${pet.energy_max} · Выдержка ${Math.round(pet.resilience)}</small></span></p>`;
  const body = `${lead}<p class="tr-note">Выберите путь. Бросок делает сервер, один раз. Провал не отнимает уровни и Связь.</p><div class="tr-opts" role="radiogroup" aria-label="Путь">${opts}</div>${chips}${dec ? '' : '<p class="tr-note">Подсказки сейчас недоступны.</p>'}`;
  const foot = `<p class="tr-err" role="alert" hidden></p><button type="button" class="v3-pill v3-pill--full" onclick="trailPathGo(this)"${chosen ? '' : ' disabled'}>${chosen ? `Выбрать ${_TR_PATH[chosen].toLowerCase()} путь` : 'Выберите путь'}</button>`;
  return _trSheetHtml('Развилка', body, foot);
}
function trailPath(path) {
  const act = _tr.pick && _trAct(_tr.pick.run), pet = act && _trPet(act.pet_id); if (!pet) return;
  _haptic('select'); _tr.pick.path = path; _trRepaint(_trDecisionHtml(act, pet));
}
function trailPathGo(button) {
  const act = _tr.pick && _trAct(_tr.pick.run); if (!act || !_tr.pick.path) return;
  _trClaim(act, _tr.pick.path, button);
}
function _trClaim(act, path, button) {
  const pet = _trPet(act.pet_id);
  _trRun(button, () => _trPost('claim', path ? { run_id: act.id, path } : { run_id: act.id }, 'claim', act.id, path || '').then(r => {
    _haptic(r.outcome === 'fail' ? 'warning' : 'success');
    _trResult(act, pet, r);
    return _trRefresh();
  }).catch(_trFail));
}

// ── Награда ─────────────────────────────────────────────────────────────────────────────────────────────
function _trResultHtml(act, pet, r) {
  const me = _tr.me, rows = [];
  const add = (glyph, n, label, kind = '') => rows.push(`<li data-k="${kind}" style="--i:${rows.length}"><span class="tr-g" aria-hidden="true">${glyph}</span><span class="tr-gl">${label}</span><b class="tr-n">+${fmt(n)}</b></li>`);
  if (Number(r.xp_credited) >= 0.5) add('🐾', Math.round(r.xp_credited), 'Следы');
  Object.entries(_TR_FIND).forEach(([key, f]) => { const n = Number((r.finds || {})[key]) || 0; if (n > 0) add(f[0], n, f[1], key); });
  if (Number(r.key) > 0) add('🗝', r.key, _trWord(r.key, 'Ключ', 'Ключа', 'Ключей'));
  if (Number(r.stage_essence) > 0) add('💧', r.stage_essence, 'Эссенция за ступень');
  const route = act.route ? _TR_ROUTE[act.route] : null, expedition = act.kind === 'expedition';
  const title = !expedition ? `${_trE(pet.name)} ${_trFem(pet, 'вернулся', 'вернулась')}` : r.outcome === 'success' ? 'Путь удался' : r.outcome === 'partial' ? 'Путь удался отчасти' : 'Не повезло на этот раз';
  const sub = [expedition ? `${_TR_PATH[r.path]} путь` : _TR_KIND[act.kind], `${act.hours}\u00a0ч`, route ? route[1] : '', expedition && r.outcome !== 'success' && Number(r.reward_mult) > 0 ? `награда ×${_trMult(r.reward_mult)}` : ''].filter(Boolean).join(' · ');
  const calm = r.outcome === 'fail' ? `<p class="tr-note">Уровни, Связь и питомец остаются при вас.${Number(r.reward_mult) > 0 ? ' Часть награды сохранена.' : ' Рискованный путь на неудаче награды не даёт.'}</p>` : '';
  const up = Number(r.level_after) > Number(r.level_before);
  const level = up ? `<p class="tr-lv is-up"><span>Новый уровень</span><b>${r.level_before} → ${r.level_after}</b></p>`
    : r.level_after >= r.ceiling && r.level_after < (me.rules.max_level || 30) ? `<p class="tr-note">Уровень ${r.level_after} — потолок этой ступени. Дальше питомец растёт со Связью: дней ${r.bond_days}.</p>` : '';
  const energy = `<p class="tr-note">Силы: ${Math.round(r.energy)}${Number(r.energy_loss) > 0 ? `, потеряно ${r.energy_loss}` : ''}. Дней Связи: ${r.bond_days}.</p>`;
  const d = Object.assign({}, me.daily, { credited: Number(r.daily_credited) }), meter = _trTraces(Object.assign({}, me, { daily: d }));
  const body = `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(pet.icon)}</span><span><b>${title}</b><small>${_trE(sub)}</small></span></p>${calm}
    <ul class="tr-gain" aria-label="Что получено">${rows.join('') || '<li class="tr-none">На этот раз без находок.</li>'}</ul>${level}${energy}${meter}`;
  return _trSheetHtml('Награда', body, '<button type="button" class="v3-pill v3-pill--full" onclick="trailClose()">Готово</button>');
}
function _trResult(act, pet, r) {
  if (!pet) { trailClose(); return; }
  const had = document.getElementById('tr-sheet');
  if (had) _trRepaint(_trResultHtml(act, pet, r)); else _trSheet(_trResultHtml(act, pet, r));
  Object.entries(_TR_FIND).forEach(([key, f]) => { const n = Number((r.finds || {})[key]) > 0, row = n && f[2] && document.querySelector(`#tr-sheet .tr-gain li[data-k="${key}"] .tr-g`); if (row) v3Fly(row, f[2], f[0], 4); });   // награда летит из своей строки в чип валюты
}
