// ── «Тропа» питомцев · главный экран, отправка, развилка, награда ──────────────────────────────
// Питомцы v2 (/pets-v2/*, флаг pets_v2): Следы дня, три слота занятий, список питомцев, отправка в путь, развилка экспедиции и экран награды. Рисуется в #pg-pets, на экране вкладки «Питомцы».
// Карточка питомца, сборка, кормление, Лагерь, Выслеживание и Испытание недели живут в app.41.js (они подключают себя в _TR_VIEWS). Цифры правил приходят в ответе (me.rules): клиент не хранит их копию.
// Флаг выключен или сервер ответил «Тропа пока закрыта»: остаётся прежний экран питомцев (openPetsV1 из app.12.js). Стили: trail-v3.css.
let _tr = { me: null, view: 'hub', pet: 0, seq: 0, skew: 0, keys: {}, scroll: 0, bad: '', busy: false, needsRefresh: false, send: null, pick: null, opener: null, late: {} };
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
  _tr.nav = (_tr.nav || 0) + 1;
  switchPage('pets');
  const root = el('pg-pets'); if (!root) return Promise.resolve();
  _tr.view = 'hub'; _tr.tab = 'overview'; _tr.history = []; _tr.send = null; _tr.sendDraft = null; _tr.pick = null;
  if (_tr.me) _trRender();
  else { root.innerHTML = '<div class="sk" style="height:110px;border-radius:18px;margin-top:8px"></div><div class="sk" style="height:150px;border-radius:18px;margin-top:22px"></div><div class="sk" style="height:220px;border-radius:18px;margin-top:22px"></div>'; v3EnterSync(root); }
  return _trLoad().then(ok => { if (ok) _trRender(); });
}
function _trLoad() {
  const mine = ++_tr.seq;
  return api('/pets-v2/me').then(me => {
    if (mine !== _tr.seq) return false;
    _tr.me = me; _tr.bad = ''; _tr.needsRefresh = false;
    const at = _trTime(me.now); if (Number.isFinite(at)) _tr.skew = at - Date.now();
    return true;
  }).catch(error => {
    if (mine !== _tr.seq) return false;
    const text = typeof error === 'string' ? error : 'Нет связи. Проверьте интернет и повторите.';
    if (/Тропа пока закрыта/.test(text)) { _sysFlags.pets_v2 = false; _tr.me = null; _trClassic(); return false; }   // флаг выключили, пока приложение было открыто
    _tr.bad = text;
    if (_tr.me) { toast(text, false); if (_tr.needsRefresh) _trRender(); } else _trPaintFail(text);
    return false;
  });
}
function _trPaintFail(text) {
  const root = el('pg-pets'); if (!root || _activePage !== 'pets') return;
  root.innerHTML = `${v3Head('Питомцы')}<div class="v3-empty" role="alert"><b>Тропа не загрузилась</b><span>${_trE(text)}</span> <button type="button" class="v3-link" onclick="openTrail()">Повторить</button></div>`;
  v3EnterSync(root);
}
function _trRefresh() { return _trLoad().then(ok => { if (ok) _trRender(); return ok; }); }
function _trRecoveryHtml() {
  return '<div class="tr-recovery" role="status"><b>Действие выполнено</b><span>Обновите запасы перед следующим действием.</span><button type="button" class="v3-link" onclick="trailRecover()">Обновить данные</button></div>';
}
async function trailRecover() {
  const ok = await _trRefresh();
  if (ok && document.getElementById('tr-sheet')) {
    trailClose(true); toast('Данные обновлены', true);
  }
}
function _trRender() {
  const root = el('pg-pets'); if (!root || _activePage !== 'pets' || !_tr.me) return;
  const same = root.dataset.trView === `${_tr.view}:${_tr.pet}:${_tr.tab || ''}`;
  const opened = same ? [...root.querySelectorAll('details[data-detail][open]')].map(n => n.dataset.detail) : [];
  const focus = same && root.contains(document.activeElement) ? document.activeElement?.dataset?.f : null;
  const view = _TR_VIEWS[_tr.view] || _TR_VIEWS.hub;
  root.innerHTML = `${_tr.needsRefresh ? _trRecoveryHtml() : ''}${view(_tr.me)}`;
  root.dataset.trView = `${_tr.view}:${_tr.pet}:${_tr.tab || ''}`;
  opened.forEach(key => root.querySelector(`details[data-detail="${key}"]`)?.setAttribute('open', ''));
  v3EnterSync(root);
  if (_tr.sendDraft && _tr.view === 'pet' && _tr.sendDraft.pet === _tr.pet) root.insertAdjacentHTML('beforeend', `<div class="tr-draft"><span>Маршрут сохранён</span><button type="button" class="v3-pill${_trPet(_tr.pet)?.run_id || _trPet(_tr.pet)?.outing ? ' v3-pill--ghost' : ''}" data-f="resume-send" onclick="trailResumeSend(this)">К отправке ›</button></div>`);
  if (focus) root.querySelector(`[data-f="${focus}"]`)?.focus({preventScroll:true});
}

// Подэкраны (карточка питомца, Лагерь…) лежат внутри той же страницы: «‹ Тропа» возвращает на главный и на то место, где игрок был
function trailGo(view, id, gearSlot) {
  _tr.nav = (_tr.nav || 0) + 1;
  if (typeof _syncOverlayScroll === 'function') _syncOverlayScroll();
  _haptic('select');
  if (_tr.view === 'hub') _tr.scroll = window.scrollY;
  (_tr.history ||= []).push({view:_tr.view, pet:_tr.pet, tab:_tr.tab, filter:_tr.filter, gearSlot:_tr.gearSlot, trialPet:_tr.trial?.pet, trackPet:_tr.track?.pet, scroll:window.scrollY, focus:document.activeElement?.dataset?.f, opened:[...el('pg-pets').querySelectorAll('details[data-detail][open]')].map(n=>n.dataset.detail)});
  _tr.view = view; _tr.pet = Number(id) || 0;
  if (view === 'equipment') _tr.gearSlot = gearSlot || null;
  if (_tr.me && _TR_ENTER[view]) _TR_ENTER[view]();
  _trRender(); try { window.scrollTo(0, 0); } catch (_) { /* прокрутка недоступна */ }
  _trFocusHead();
}
function _trFocusHead() { const h = el('pg-pets')?.querySelector('h1'); if (h) { h.tabIndex = -1; h.focus({preventScroll:true}); } }
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
  _tr.nav = (_tr.nav || 0) + 1;
  if (typeof _syncOverlayScroll === 'function') _syncOverlayScroll();
  _haptic('select');
  const frame = (_tr.history || []).pop() || {view:'hub', pet:0, tab:'overview', scroll:_tr.scroll};
  Object.assign(_tr, {view:frame.view, pet:frame.pet, tab:frame.tab, filter:frame.filter, gearSlot:frame.gearSlot});
  if (frame.view === 'trial' && _tr.trial) _tr.trial.pet = frame.trialPet || 0;
  if (frame.view === 'track' && _tr.track) _tr.track.pet = frame.trackPet || 0;
  _trRender();
  (frame.opened || []).forEach(key=>el('pg-pets')?.querySelector(`details[data-detail="${key}"]`)?.setAttribute('open',''));
  try { window.scrollTo(0, frame.scroll || 0); } catch (_) { /* прокрутка недоступна */ }
  const focus = frame.focus && el('pg-pets')?.querySelector(`[data-f="${frame.focus}"]`);
  if (focus) focus.focus({preventScroll:true}); else _trFocusHead();
}

// ── Состояние питомца: у ведущего своё занятие, у Спутника занятие ведущего (run_id у обоих) ──────────
function _trState(p) {
  if (p.outing) return { k: 'outing', label: 'Вылазка продолжается' };
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
function _trHead() { return v3Head('Питомцы', { end: v3GuideBtn('trail').replace('v3-pill--sm','v3-pill--sm v3-pill--ghost') }); }
// Следы дня видны на каждом экране Тропы: на главном — строка с числом, полосой и подсказкой, на подэкранах (compact) — текст для строки под заголовком.
// Упёрлись в норму: спокойная строка, без красного (питомцы устали расти, награды остаются)
function _trTraces(me, compact) {
  const d = me.daily || {}, r = me.rules || {}, max = Number(d.max) || 625, cur = Math.max(0, Math.min(max, Number(d.credited) || 0)), soft = Number(r.daily_soft_from) || 500;
  const full = cur >= max - 0.05, rate = Math.round((Number(r.daily_soft_rate) || 0.25) * 100), shown = full ? max : Math.floor(cur);
  const note = full ? 'На сегодня питомцы устали расти. Награды остаются.'
    : cur >= soft ? `Следы идут медленнее: теперь засчитывается ${rate}\u00a0%.`
    : cur < 1 ? 'Сегодня Следов ещё нет. Отправьте питомца в путь.'
    : `По полной ставке ещё ${fmt(Math.max(0, Math.floor(soft - cur)))}. Дальше засчитывается ${rate}\u00a0%.`;
  const label = `Следы за сегодня: ${fmt(shown)} из ${fmt(max)}`;
  if (compact) return `Следы: ${fmt(shown)} из ${fmt(max)}`;
  return `<section class="tr-sec tr-traces" aria-label="Следы за сегодня"><p class="tr-tline"><span>Следы за сегодня</span><b>${fmt(shown)}<small> из ${fmt(max)}</small></b></p>${_trMeter(cur / max, { notch: soft / max, label })}<p class="tr-note">${note}</p></section>`;
}
function _trSlot(act, primary = false) {
  const pet = _trPet(act.pet_id); if (!pet) return '';
  const mate = (_tr.me.pets || []).find(p => p.id !== pet.id && p.run_id === act.id), route = act.route ? _TR_ROUTE[act.route] : null;
  const what = [_TR_KIND[act.kind] || act.kind, `${act.hours}\u00a0ч`, route ? `${route[0]}\u00a0${route[1]}` : ''].filter(Boolean).join(' · ');
  const end = act.ready
    ? `<button type="button" class="v3-pill v3-pill--sm${primary ? '' : ' v3-pill--ghost'}" data-run="${_trE(act.id)}" onclick="trailRun(this)">${act.kind === 'expedition' ? 'Выбрать путь' : 'Забрать'}</button>`
    : `<span class="tr-left"><small>осталось</small><b data-end="${_trTime(act.ends_at)}" data-id="${_trE(act.id)}">${_trDur(_trLeft(act))}</b></span>`;
  return `<li class="tr-row tr-slot is-${act.ready ? 'ready' : 'busy'}"><span class="tr-ic" aria-hidden="true">${_trE(pet.icon)}</span><span class="tr-nm"><b>${_trE(pet.name)}</b><small>${_trE(what)}</small>${mate ? `<small>Спутник: ${_trE(mate.name)}</small>` : ''}</span><span class="tr-end">${end}</span></li>`;
}
function _trMinCost(me) { return Math.min(...Object.values(me.rules.energy.run), ...Object.values(me.rules.energy.watch)); }
function _trSlots(me) {
  const acts = me.activities || [], slots = Number(me.slots) || 3;
  const free = Math.max(0, slots - acts.length), min = _trMinCost(me);
  const sendable = me.pets.some(p => !p.run_id && !p.outing && p.energy >= min);
  return `<section class="tr-sec" id="tr-slots">${_trSec('В пути и возвращения', `<span class="tr-count">${acts.length}/${slots} слотов</span>`)}${acts.length ? `<ul class="tr-list" aria-label="Занятия">${acts.slice().sort((a,b)=>Number(b.ready)-Number(a.ready)).map((a,i)=>_trSlot(a,i===0 && a.ready)).join('')}</ul>` : '<p class="tr-note">Пока никто не в пути. Отправь питомца за Следами и находками.</p>'}<div class="tr-launch"><span class="tr-note">${free ? `Свободно слотов: ${free}` : 'Все слоты заняты. Дождись возвращения и забери награду.'}</span><button type="button" class="v3-pill${acts.some(a=>a.ready)?' v3-pill--ghost':''}" data-f="send" onclick="trailSend()"${free && sendable ? '' : ' disabled'}>Отправить в путь</button></div>${free && !sendable ? '<p class="tr-note">Нет свободного питомца с нужными силами. Покорми питомца или забери награду за его занятие.</p>' : ''}</section>`;
}
function _trLevelLine(p) {
  if (p.level >= (_tr.me.rules.max_level || 30)) return '<small class="tr-sub">Высший уровень</small>';
  if (p.level >= p.ceiling) return `<small class="tr-sub">Ждёт Связи: ${p.bond_days} из ${p.next_gate_days} дн.</small>`;
  return `${_trMeter(p.xp / Math.max(1,p.next_cost), { cls: 'tr-meter--xp' })}<small class="tr-sub">До ${p.level+1} ур. — ещё ${fmt(Math.max(0,Math.ceil(p.next_cost-p.xp)))} Следов</small>`;
}
function _trPetRow(p) {
  const s = _trState(p), min = _trMinCost(_tr.me), low = p.energy < min;
  const say = `${p.name}, уровень ${p.level}, ${s.label.toLowerCase()}, силы ${Math.round(p.energy)} из ${p.energy_max}`;
  return `<li><button type="button" class="tr-row tr-pet is-${s.k}${low ? ' is-low' : ''}" data-f="pet-${p.id}" onclick="trailPet(${p.id})" aria-label="${_trE(say)}"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span class="tr-nm"><b>${_trE(p.name)}</b><small>Ур.\u00a0${p.level} · <em class="tr-s">${s.label}</em></small>${_trLevelLine(p)}<small>Экипировка ${Object.keys(p.equipment?.equipped || {}).length}/5 · ${_TR_ROUTE[p.favorite_route]?.[1] || "Любой маршрут"}</small></span><span class="tr-en" aria-hidden="true"><b>${Math.round(p.energy)}</b><small>/${p.energy_max}</small>${_trMeter(p.energy / p.energy_max, { cls: 'tr-meter--sm' })}${low ? '<em>мало сил</em>' : ''}</span></button></li>`;
}
function _trPetMatches(p, filter) {
  const state = _trState(p).k;
  if (filter === 'free') return state === 'free';
  if (filter === 'ready') return state === 'ready';
  if (filter === 'busy') return state === 'busy' || state === 'outing';
  return true;
}
function trailCollectionFilter(filter) {
  _tr.filter = ['all','free','ready','busy'].includes(filter) ? filter : 'all';
  _trRender(); el('pg-pets')?.querySelector(`[data-f="filter-${_tr.filter}"]`)?.focus({preventScroll:true});
}
function _trPets(me, preview = false) {
  const rank = { ready: 0, free: 1, busy: 2, outing: 2 }, all = (me.pets || []).slice().sort((a,b)=>rank[_trState(a).k]-rank[_trState(b).k] || b.level-a.level || a.id-b.id);
  const filter = _tr.filter || 'all', filtered = all.filter(p=>_trPetMatches(p,filter));
  const filters = preview ? '' : `<div class="tr-filters" role="group" aria-label="Состояние питомцев">${[['all','Все'],['free','В лагере'],['ready','Вернулись'],['busy','В пути']].map(([key,label])=>`<button type="button" data-f="filter-${key}" aria-pressed="${filter===key}" onclick="trailCollectionFilter('${key}')">${label} <small>${all.filter(p=>_trPetMatches(p,key)).length}</small></button>`).join('')}</div>`;
  const pets = preview ? all.slice(0,2) : filtered;
  return `<section class="tr-sec" id="tr-pets">${_trSec(preview ? 'Мои питомцы' : `Коллекция · ${all.length}`, preview ? `<button type="button" class="v3-link" data-f="all-pets" onclick="trailTab('collection')">Все питомцы ›</button>` : '')}${filters}${pets.length ? `<ul class="tr-list">${pets.map(_trPetRow).join('')}</ul>` : '<p class="tr-note" role="status">В этой группе пока нет питомцев. Выбери другой фильтр.</p>'}</section>`;
}
function _trEmpty() {
  return `<section class="tr-sec"><div class="v3-empty tr-empty"><b>Питомцев пока нет, их можно получить в сундуках.</b>${_sysFlags.content_chests_v1 === true ? '<button type="button" class="v3-link" onclick="openChestsV1()">К сундукам ›</button>' : ''}</div></section>`;
}
function _trTags(t) { return [(_TR_ROUTE[t.route] || [])[1], `${t.tempo}\u00a0ч`, t.style === 'careful' ? 'осторожный путь' : 'рискованный путь'].filter(Boolean).join(' · '); }
function _trTabs() {
  const current = _tr.view === 'camp' ? 'camp' : (_tr.tab || 'overview');
  return `<nav class="tr-nav" aria-label="Разделы питомцев">${[['overview','Обзор'],['collection','Питомцы'],['camp','Лагерь']].map(([key,label])=>`<button type="button" data-f="tab-${key}"${current===key?' aria-current="page"':''} onclick="trailTab('${key}')">${label}</button>`).join('')}</nav>`;
}
function trailTab(tab) {
  if (!['overview','collection','camp'].includes(tab)) return;
  _tr.nav = (_tr.nav || 0) + 1;
  _tr.tab = tab; _tr.view = tab === 'camp' ? 'camp' : 'hub'; _tr.pet = 0; _tr.history = [];
  _trRender(); window.scrollTo(0,0); el('pg-pets')?.querySelector(`[data-f="tab-${tab}"]`)?.focus({preventScroll:true});
}
function _trModeCard(icon,title,tag,description,action,key) {
  return `<button type="button" class="tr-mode" data-f="mode-${key}" onclick="${action}"><span class="tr-mode-icon" aria-hidden="true">${_v3Icon(icon)}</span><span class="tr-mode-tag">${tag}</span><b>${title}</b><span>${description}</span><small>Открыть <i aria-hidden="true">↗</i></small></button>`;
}
function _trModes(me) {
  const g = me.equipment, track = me.track || {}, trial = me.trial || {}, r = me.rules;
  const cards = [];
  if (g) cards.push(_trModeCard('bag','Вылазка',g.open?'Продолжить':`${g.attempts_left}/${g.daily} попыток`,`${g.open?'Забег сохранён.':'7 решений без ожидания.'} Детали для экипировки${g.open?'':` · вход ${g.energy} сил`}.`,"trailGo('outing')",'outing'));
  cards.push(_trModeCard('scope','Выслеживание',track.open?'Продолжить':`${track.attempts_left || 0}/${r.track.daily} попыток`,'Находка на поле 3×3. Больше внимания — больше открытий.',"trailGo('track')",'track'));
  cards.push(_trModeCard('trophy','Испытание недели',trial.done?'Сдано':'Раз в неделю',trial.done?'Новое испытание в понедельник.':`${trial.xp || 0} Следов и Эссенция за подходящую сборку. Силы не тратятся.`,"trailGo('trial')",'trial'));
  return `<section class="tr-sec">${_trSec('Сыграть сейчас')}<div class="tr-modes">${cards.join('')}</div></section>`;
}
function _trResume(me) {
  const rows = [];
  if (me.equipment?.open) rows.push(_v3Row('bag','Вылазка ждёт решения',"trailGo('outing')",`Развилка ${me.equipment.open.step+1} из ${me.equipment.open.steps} · добыча ${me.equipment.open.cargo} дет.`));
  if (me.track?.open) rows.push(_v3Row('scope','Продолжить выслеживание',"trailGo('track')",`Внимание: ${me.track.open.points}. Поле сохранено.`));
  return rows.length ? `<section class="tr-resume" aria-label="Продолжить игру">${rows.join('')}</section>` : '';
}
_TR_VIEWS.hub = me => {
  const pets = (me.pets || []).length, collection = _tr.tab === 'collection';
  const daily = `<details class="tr-daily" data-detail="daily"><summary data-f="detail-daily"><span>Следы сегодня</span><b>${_trTraces(me,true).replace('Следы: ','')}</b></summary>${_trTraces(me)}</details>`;
  return `${_trHead()}${_trTabs()}${daily}${collection ? (pets ? _trPets(me) : _trEmpty()) : `${_trResume(me)}${pets ? `${_trSlots(me)}${_trModes(me)}${_trPets(me,true)}` : _trEmpty()}${me.camp?.job?.done ? `<button class="tr-camp-notice" type="button" onclick="trailTab('camp')">Постройка в лагере готова · посмотреть ›</button>` : ''}`}`;
};

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
  _tr.dialog = (_tr.dialog || 0) + 1;
  const keep = document.getElementById('tr-sheet') ? _tr.opener : document.activeElement;
  trailClose(true); _tr.opener = keep;
  const host = document.createElement('div'); host.id = 'tr-sheet'; host.className = 'lk-sheet-back';
  host.innerHTML = `<section class="lk-sheet tr-sheet" role="dialog" aria-modal="true" aria-labelledby="tr-sheet-t" tabindex="-1">${html}</section>`;
  host.addEventListener('click', e => { if (e.target === host) trailClose(); });
  _trKeys = e => {
    if (document.getElementById('cf-sheet')) return;   // сверху окно подтверждения: клавиши принадлежат ему
    if (e.key === 'Escape') { e.preventDefault(); trailClose(); return; }
    if (e.key !== 'Tab') return;
    const items = [...host.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], summary, [tabindex="0"]')].filter(node => node.getClientRects().length), first = items[0], last = items[items.length - 1];
    if (!first) return;
    if (!items.includes(document.activeElement) || (e.shiftKey && document.activeElement === first) || (!e.shiftKey && document.activeElement === last)) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
  };
  document.addEventListener('keydown', _trKeys, true);
  document.body.appendChild(host); host.firstElementChild.focus({ preventScroll: true });
}
// Выбор внутри окна перерисовывает его содержимое; прокрутка и фокус остаются на месте
function _trRepaint(html) {
  const sheet = document.querySelector('#tr-sheet .tr-sheet'); if (!sheet) return _trSheet(html);
  const body = sheet.querySelector('.tr-sbody'), top = body ? body.scrollTop : 0, key = document.activeElement?.dataset?.f;
  const opened = [...sheet.querySelectorAll('details[data-detail][open]')].map(n=>n.dataset.detail);
  sheet.innerHTML = html;
  opened.forEach(key=>sheet.querySelector(`details[data-detail="${key}"]`)?.setAttribute('open',''));
  const next = sheet.querySelector('.tr-sbody'); if (next) next.scrollTop = top;
  (key && sheet.querySelector(`[data-f="${key}"]`) || sheet).focus({ preventScroll: true });
}

// ── Действия: один номер операции на одно действие ───────────────────────────────────────────────
// Keep action identity through every failure: api() also represents uncertain HTTP 5xx as text. Confirmed writes require fresh state before another mutation.
function _trKey(...parts) {
  const k = parts.join(':');
  return _tr.keys[k] ||= { k, id: `tr-${String(parts[0]).slice(0, 12)}-${globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2, 10)}` };
}
function _trPost(path, body, ...parts) {
  const key = _trKey(...parts);
  return api(`/pets-v2/${path}`, { method: 'POST', body: JSON.stringify({ ...body, action_id: key.id }) }).then(
    data => { ++_tr.seq; _tr.needsRefresh = !((path === 'track/start' || path === 'track/open') && data.track?.status === 'open'); delete _tr.keys[key.k]; return data; });
}
async function _trRun(button, job) {
  if (_tr.busy) return;
  const focus = button?.dataset?.f, navigation = _tr.nav || 0;
  _tr.busy = true; if (button) button.disabled = true;
  try {
    if (_tr.needsRefresh) {
      toast('Предыдущее действие выполнено. Обновляем запасы.', true);
      await trailRecover(); return;
    }
    return await job();
  } finally {
    _tr.busy = false; if (button && button.isConnected) button.disabled = false;
    // Disabling a focused writer moves focus to body; reconnect it after the authoritative refresh.
    if (focus && navigation === (_tr.nav || 0) && _activePage === 'pets' && document.activeElement === document.body && !document.querySelector('[role="dialog"][aria-modal="true"]')) {
      el('pg-pets')?.querySelector(`[data-f="${focus}"]:not(:disabled)`)?.focus({preventScroll:true});
    }
  }
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
// ── Кого брать: подсказка «лучший выбор» ──────────────────────────────────────────────────────────────
// Сравниваем по тем же величинам, что показывает сама игра: экспедицию решает Выдержка (resilience —
// её считает сервер, от неё зависит исход броска), поход — сырые Следы (их поднимают звёзды вида и
// любимый маршрут), дозор — только запас сил (у него нет ни броска, ни надбавок). Занятый питомец или
// тот, кому не хватит сил на выбранные часы, в подсказке не участвует. Своих чисел не заводим.
function _trFitKey(p, kind, hours, route) {
  if (p.run_id || p.outing || p.energy < _trCost(kind, hours)) return null;
  const fav = route && (p.favorite_route === route || p.favorite_route === 'any') ? 1 : 0, fed = p.fed_favorite ? 1 : 0, stars = Number(p.stars) || 0;
  if (kind === 'watch') return [p.energy];
  return kind === 'expedition' ? [p.resilience, stars, fav, fed, p.energy] : [stars, fav, fed, p.energy];
}
const _trWins = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] > b[i]; return false; };
// Подсказка сервера (me.advice): ожидание с чертами, талисманами, Хранителем, мягкой защитой и повторами маршрута —
// по тем же правилам, что и начисление. Клиент только рисует звезду; без поля работает своя эвристика ниже.
function _trAdvice(kind, hours, route) {
  const map = _tr.me && _tr.me.advice ? _tr.me.advice.map : null;
  const id = map ? Number(map[`${kind}|${hours}|${route || ''}`]) : 0;
  const pet = id ? _trPet(id) : null;
  return pet && !pet.run_id && !pet.outing && pet.energy >= _trCost(kind, hours) ? pet : null;
}
function _trBestPet(list, kind, hours, route) {
  const advised = _trAdvice(kind, hours, route);
  if (advised) return advised;
  let best = null, key = null;
  (list || []).forEach(p => { const k = _trFitKey(p, kind, hours, route); if (k && (!key || _trWins(k, key))) { key = k; best = p; } });
  return best;
}
// Разметка метки «★» и невидимой подписи для читалки — визуально только значок, без слов
const _trBestMark = on => on ? '<i class="sr-only">Лучший выбор. </i>' : '';
// Почему звезда: только значки, слова — невидимой подписью. Факты о питомце берём из того же ответа сервера.
function _trWhyIcons(p, route) {
  const out = [], share = p.energy / Math.max(1, p.energy_max);
  if (route && (p.favorite_route === route || p.favorite_route === 'any')) out.push([(_TR_ROUTE[route] || [])[0] || '✦', 'любимый маршрут']);
  if (Number(p.stars) > 0) out.push(['⭐', `звёзд вида: ${p.stars}`]);
  if (p.fed_favorite) out.push(['🍖', 'сыт любимым']);
  if (p.calling === 'guardian') out.push(['🛡', 'Хранитель']);
  if (share >= .8) out.push(['⚡', 'много сил']);
  return out.slice(0, 4);
}
const _trWhyRow = (p, route) => {
  const why = p ? _trWhyIcons(p, route) : [];
  if (!why.length) return '';
  const label = _trE(`Почему лучший: ${why.map(w => w[1]).join(', ')}`);
  return `<p class="tr-bestwhy"><span class="sr-only">${label}</span><span aria-hidden="true">★</span>${why.map(w => `<span aria-hidden="true">${w[0]}</span>`).join('')}</p>`;
};
// Спутник: Лидер перенимает половину склонности Спутника к находкам, поэтому ценнее чужой вид находок, чем свой
function _trBestMate(list, lead) {
  const own = lead && lead.find_bias;
  return list.slice().sort((a, b) => (b.find_bias !== own) - (a.find_bias !== own) || b.energy - a.energy || a.id - b.id)[0] || null;
}
function trailSend(petId) {
  _tr.sendDraft = null;
  const me = _tr.me; if (!me) return;
  const free = (me.pets || []).filter(p => !p.run_id && !p.outing), first = (me.durations.run || [3])[0];
  const plan = petId ? null : (me.advice && me.advice.best ? me.advice.best.trek : null) || null;   // связка сервера: питомец, часы, маршрут
  const planPet = plan ? _trPet(plan.pet_id) : null;
  const pick = (petId ? _trPet(petId) : planPet && !planPet.run_id && !planPet.outing && planPet.energy >= _trCost('trek', plan.hours) ? planPet : null)
    || _trBestPet(free, 'trek', first, '') || free[0];
  const usePlan = !!plan && pick === planPet;
  _tr.send = { pet: pick ? pick.id : 0, kind: 'trek', hours: usePlan ? plan.hours : 3, route: usePlan ? plan.route : '',
               routeSet: usePlan, planRoute: usePlan, fitted: usePlan, comp: 0 };
  _trSendFit();
  _trSheet(_trSendHtml());
  _trForecastSchedule();
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
  if (key === 'pet') { s.pet = Number(value); s.comp = 0; s.fitted = false; if (s.planRoute) { s.routeSet = false; s.planRoute = false; } }
  else if (key === 'kind') { s.kind = value; s.fitted = false; if (value === 'watch') s.comp = 0; }
  else if (key === 'hours') { s.hours = Number(value); s.fitted = true; }
  else if (key === 'route') { s.route = value; s.routeSet = true; }
  else if (key === 'comp') s.comp = Number(value);
  _trSendFit(); _trRepaint(_trSendHtml()); _trForecastSchedule();
}
let _trForecastTimer = null, _trForecastSeq = 0;
function _trForecastSchedule() {
  clearTimeout(_trForecastTimer);
  const seq = ++_trForecastSeq, s = _tr.send;
  if (!s?.pet) return;
  _trForecastTimer = setTimeout(async () => {
    const body = { pet_id: s.pet, kind: s.kind, hours: s.hours, route: s.kind === 'watch' ? null : s.route,
      companion_id: s.kind !== 'watch' && s.comp ? s.comp : null };
    try {
      const q = await api('/pets-v2/preview', { method: 'POST', body: JSON.stringify(body) });
      const node = el('tr-send-forecast');
      if (seq !== _trForecastSeq || _tr.send !== s || !node) return;
      const range = (low, high) => low === high ? fmt(low) : `${fmt(low)}–${fmt(high)}`;
      const quote = el('tr-send-quote'); if (quote) quote.textContent = `Прогноз: ${range(q.min.credited,q.max.credited)} Следов`;
      const f = q.factors, paths = Object.entries(q.paths || {}).map(([path, row]) =>
        `<div><dt>${_TR_PATH[path]}</dt><dd>${range(row.min.credited, row.max.credited)}</dd></div>`).join('');
      node.innerHTML = `<details class="tr-forecast"><summary><span>Прогноз для питомца</span><b>${range(q.min.credited,q.max.credited)} Следов</b></summary><dl class="cf-rows"><div><dt>До дневной нормы</dt><dd>${range(q.min.raw,q.max.raw)}</dd></div>${body.companion_id ? `<div><dt>Спутнику</dt><dd>${range(q.min.companion,q.max.companion)}</dd></div>` : ''}${paths}</dl><p class="tr-note">Сборка ×${_trMult(f.build)}${f.favorite ? ' · любимый маршрут' : ''}${f.stars ? ` · звёзд привязанности: ${f.stars}` : ''}${f.repeats ? ` · повторов сегодня: ${f.repeats}, множитель ×${_trMult(f.repeat_multiplier)}` : ''}</p><p class="tr-note">${_trE(q.notice)}</p>${q.reasons.length ? `<p class="tr-note">${q.reasons.map(_trE).join(' ')}</p>` : ''}</details><p class="tr-note">Без случайных находок. Норма и сборка при возвращении могут измениться.</p>`;

    } catch (_) {
      const node = el('tr-send-forecast');
      if (seq === _trForecastSeq && _tr.send === s && node) { const quote = el('tr-send-quote'); if (quote) quote.textContent = 'Прогноз временно недоступен'; node.innerHTML = '<p class="tr-note">Прогноз недоступен. Награда будет рассчитана сервером при возвращении.</p><button type="button" class="v3-link" onclick="_trForecastSchedule()">Повторить расчёт</button>'; }
    }
  }, 220);
}
function _trSendHtml() {
  const me = _tr.me, s = _tr.send, rules = me.rules, pet = _trPet(s.pet), watch = s.kind === 'watch';
  const free = (me.pets || []).filter(p => !p.run_id && !p.outing), min = _trMinCost(me), cost = _trCost(s.kind, s.hours), pairCost = Number(rules.energy.pair) || 10;
  const slotsLeft = Math.max(0, (Number(me.slots) || 3) - (me.activities || []).length), mate = !watch && s.comp ? _trPet(s.comp) : null;
  const radio = (on, f, click, inner, cls = 'tr-chip') => `<button type="button" class="${cls}" role="radio" aria-checked="${on}" data-f="${f}" onclick="${click}">${inner}</button>`;
  const best = _trBestPet(free, s.kind, s.hours, s.route), whyRow = _trWhyRow(best, watch ? '' : s.route);
  const pets = free.map(p => { const top = best && p.id === best.id; return radio(p.id === s.pet, `pet-${p.id}`, `trailSendSet('pet',${p.id})`, `${_trBestMark(top)}<span aria-hidden="true">${_trE(p.icon)}</span><b>${_trE(p.name)}</b><small>${Math.round(p.energy)} из ${p.energy_max}</small>`, `tr-chip tr-chip--i${p.energy < min ? ' is-dim' : ''}${top ? ' is-best' : ''}`); }).join('');
  const kinds = ['trek', 'expedition', 'watch'].map(k => radio(s.kind === k, `kind-${k}`, `trailSendSet('kind','${k}')`, _TR_KIND[k], 'tr-seg-b')).join('');
  const note = { trek: 'Награда после возвращения. Развилок нет.', expedition: `На развилке вы выберете путь: награда больше, но есть риск. Следы ×${_trMult(rules.xp.expedition)}.`, watch: 'Долгий дозор без маршрута, для тех, кто заходит раз в день.' }[s.kind];
  const hours = (watch ? me.durations.watch : me.durations.run).map(h => radio(h === s.hours, `hours-${h}`, `trailSendSet('hours',${h})`, `<b>${h}\u00a0ч</b><small>${_trCost(s.kind, h)} сил</small>`, `tr-chip tr-chip--c${pet && _trCost(s.kind, h) > pet.energy ? ' is-dim' : ''}`)).join('');
  const fav = r => pet && (pet.favorite_route === r || pet.favorite_route === 'any');
  const routes = (me.routes || []).map(r => radio(r === s.route, `route-${r}`, `trailSendSet('route','${r}')`, `<span aria-hidden="true">${_TR_ROUTE[r][0]}</span><b>${_TR_ROUTE[r][1]}</b>${fav(r) ? '<small>любимый</small>' : ''}`, 'tr-chip tr-chip--i')).join('');
  const mates = free.filter(p => p.id !== s.pet && p.energy >= pairCost);
  const mateTop = pet ? _trBestMate(mates, pet) : null;
  const mateChips = mates.map(p => { const top = mateTop && p.id === mateTop.id; return radio(p.id === s.comp, `comp-${p.id}`, `trailSendSet('comp',${p.id})`, `${_trBestMark(top)}<span aria-hidden="true">${_trE(p.icon)}</span><b>${_trE(p.name)}</b><small>${Math.round(p.energy)} сил</small>`, `tr-chip tr-chip--i${top ? ' is-best' : ''}`); }).join('');
  let pair = '';
  if (!watch) {
    const need = me.pair?.need || 5;
    pair = me.pair?.unlocked
      ? `<details class="tr-grp tr-details" data-detail="send-comp"><summary data-f="detail-send-comp">Спутник · ${mate ? _trE(mate.name) : 'без спутника'}</summary><div class="tr-chips" role="radiogroup" aria-label="Спутник">${radio(!s.comp, 'comp-0', "trailSendSet('comp',0)", '<b>Без спутника</b>')}${mateChips}</div><p class="tr-note">Спутник тратит ${pairCost} сил и получает ${Math.round((rules.pair_share || .3) * 100)}\u00a0% Следов.</p></details>`
      : `<p class="tr-note tr-hint">Спутник открывается при ${need} разных видах питомцев, сейчас их ${me.pair?.species || 0}.</p>`;
  }
  const enough = pet && pet.energy >= cost, why = !pet ? 'Выберите питомца.' : !slotsLeft ? 'Все слоты заняты.' : !enough ? `Не хватает сил: нужно ${cost}, у питомца ${Math.floor(pet.energy)}.` : mate && mate.energy < pairCost ? `Спутнику нужно ${pairCost} сил.` : '';
  const who = pet ? `<div class="tr-send-pet"><span class="tr-ic" aria-hidden="true">${_trE(pet.icon)}</span><span><b>${_trE(pet.name)}</b><small>Ур. ${pet.level} · ${Math.round(pet.energy)}/${pet.energy_max} сил · экипировка ${Object.keys(pet.equipment?.equipped || {}).length}/5</small></span><button type="button" class="v3-link" data-f="send-prep" onclick="trailPrepareSend()">Подготовить ›</button></div>` : '';
  const body = `${who}<details class="tr-details" data-detail="send-pet"${pet?'':' open'}><summary data-f="detail-send-pet">Сменить питомца · доступно ${free.length}</summary>${free.length ? `<div class="tr-chips" role="radiogroup" aria-label="Кто идёт">${pets}</div>${whyRow}` : '<p class="tr-note">Свободных питомцев нет: все в пути или ждут награды.</p>'}</details>
    <div class="tr-grp"><span class="v3-eyebrow">Занятие</span><div class="tr-seg" role="radiogroup" aria-label="Что делать">${kinds}</div><p class="tr-note">${note}</p></div>
    <div class="tr-grp"><span class="v3-eyebrow">Время и стоимость</span><div class="tr-chips tr-chips--3" role="radiogroup" aria-label="Сколько часов">${hours}</div></div>
    ${watch ? '' : `<div class="tr-grp"><span class="v3-eyebrow">Маршрут</span><div class="tr-chips tr-chips--2" role="radiogroup" aria-label="Маршрут">${routes}</div></div>`}${pair}<section id="tr-send-forecast" class="tr-grp" aria-live="polite" aria-label="Прогноз Следов"><p class="tr-note">Считаем прогноз с учётом сборки и дневной нормы…</p></section>`;
  const selected = pet ? `<p class="tr-selected"><b>${_trE(pet.name)} · ${_TR_KIND[s.kind]} ${s.hours} ч</b><span>${watch ? '' : _TR_ROUTE[s.route][1]+' · '}силы ${Math.round(pet.energy)} → ${Math.max(0,Math.round(pet.energy-cost))}${mate ? ` · спутник −${pairCost}` : ''}</span></p>` : '';
  const foot = `${selected}<p class="tr-quote" id="tr-send-quote" role="status">Прогноз рассчитывается…</p>${why ? `<p class="tr-note tr-why" role="status">${_trE(why)}</p>` : ''}<p class="tr-err" role="alert" hidden></p><button type="button" class="v3-pill v3-pill--full" onclick="trailSendGo(this)"${why ? ' disabled' : ''}>Отправить в путь</button>`;
  return _trSheetHtml('Отправить в путь', body, foot);
}
function trailPrepareSend() {
  const s = _tr.send; if (!s?.pet) return;
  _tr.sendDraft = {...s}; ++_trForecastSeq; clearTimeout(_trForecastTimer);
  trailClose(true);
  if (_tr.view === 'pet' && _tr.pet === s.pet) _trRender(); else trailPet(s.pet);
}
async function trailResumeSend(button) {
  const navigation = _tr.nav || 0;
  if (_tr.busy || _tr.resumeRequest?.navigation === navigation) return;
  const request = {navigation}; _tr.resumeRequest = request;
  if (button) button.disabled = true;
  const draft = _tr.sendDraft, dialog = _tr.dialog || 0;
  let ok;
  try { ok = await _trLoad(); }
  finally { if (_tr.resumeRequest === request) _tr.resumeRequest = null; if (button?.isConnected) button.disabled = false; }
  if (!ok || _tr.busy || navigation !== (_tr.nav || 0) || dialog !== (_tr.dialog || 0) || document.querySelector('[role="dialog"][aria-modal="true"]') || !draft || _tr.sendDraft !== draft || _activePage !== 'pets' || _tr.view !== 'pet' || _tr.pet !== draft.pet) return;
  const pet = _trPet(draft.pet);
  if (!pet || pet.run_id || pet.outing) { _tr.sendDraft = null; _trRender(); toast('Питомец уже в пути. Выбери другое занятие после возвращения.',false); return; }
  const companion = draft.comp ? _trPet(draft.comp) : null;
  if (draft.comp && (!companion || companion.run_id || companion.outing || companion.energy < Number(_tr.me.rules.energy.pair))) {
    draft.comp = 0; toast('Спутник больше недоступен. Маршрут сохранён без спутника.',false);
  }
  _tr.sendDraft = null; _tr.send = {...draft}; _trSendFit();
  _trRender();
  const opener = el('pg-pets')?.querySelector('[data-f="pet-send"]:not(:disabled)');
  if (opener) opener.focus({preventScroll:true}); else _trFocusHead();
  _trSheet(_trSendHtml()); _trForecastSchedule();
}
function trailSendGo(button) {
  const s = _tr.send, pet = s && _trPet(s.pet); if (!pet) return;
  const watch = s.kind === 'watch', body = { pet_id: pet.id, kind: s.kind, hours: s.hours, route: watch ? null : s.route };
  if (!watch && s.comp) body.companion_id = s.comp;
  _trRun(button, () => _trPost('start', body, 'start', pet.id, s.kind, s.hours, body.route || '', body.companion_id || 0).then(r => {
    _haptic('success'); _tr.sendDraft = null; trailClose();
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
    const star = dec && dec.best === path ? '<i class="tr-best-i" aria-hidden="true">★</i><i class="sr-only">Лучший путь по ожиданию награды. </i>' : '';
    return `<button type="button" class="tr-opt${star ? ' is-best' : ''}" role="radio" aria-checked="${chosen === path}" data-f="path-${path}" onclick="trailPath('${path}')"><span class="tr-opt-t"><b>${star}${_TR_PATH[path]}</b><small>${sub}</small></span>${h.sign ? `<span class="tr-sign ${_TR_SIGN[h.sign] || ''}">${_trE(h.sign)}${odds ? `<small>${odds}</small>` : ''}</span>` : ''}</button>`;
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
  const c = r.companion;
  const companion = c ? `<section class="tr-grp" aria-label="Награда спутника"><b>Спутник: ${_trE(c.name)}</b><p class="tr-note">+${fmt(c.xp_credited)} Следов · силы ${Math.round(c.energy)}${c.level_after > c.level_before ? ` · уровень ${c.level_before} → ${c.level_after}` : ''}${c.stage_essence ? ` · +${fmt(c.stage_essence)} Эссенции за ступень` : ''}</p></section>` : '';
  const d = Object.assign({}, me.daily, { credited: Number(r.daily_credited) }), meter = _trTraces(Object.assign({}, me, { daily: d }));
  const body = `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(pet.icon)}</span><span><b>${title}</b><small>${_trE(sub)}</small></span></p>${calm}
    <ul class="tr-gain" aria-label="Что получено">${rows.join('') || '<li class="tr-none">На этот раз без находок.</li>'}</ul>${level}${energy}${companion}${meter}`;
  return _trSheetHtml('Награда', body, '<button type="button" class="v3-pill v3-pill--full" onclick="trailClose()">Готово</button>');
}
function _trResult(act, pet, r) {
  if (!pet) { trailClose(); return; }
  const had = document.getElementById('tr-sheet');
  if (had) _trRepaint(_trResultHtml(act, pet, r)); else _trSheet(_trResultHtml(act, pet, r));
  Object.entries(_TR_FIND).forEach(([key, f]) => { const n = Number((r.finds || {})[key]) > 0, row = n && f[2] && document.querySelector(`#tr-sheet .tr-gain li[data-k="${key}"] .tr-g`); if (row) v3Fly(row, f[2], f[0], 4); });   // награда летит из своей строки в чип валюты
}
