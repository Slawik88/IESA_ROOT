// ── «Тропа» питомцев · карточка питомца, сборка, кормление, Лагерь, Выслеживание, Испытание недели ──────
// Подключает себя к app.40.js через _TR_VIEWS (pet, camp, track, trial) и пользуется его окнами, действиями и шкалами: _trSheet, _trPost, _trRun, _trFail, _trRefresh, _trMeter, _trTraces.
// Названия призваний, черт и талисманов живут здесь (лицо игры), а числа и тексты эффектов приходят с сервера (me.rules): клиент не хранит копию правил. Стили: trail-v3.css.
const _TR_CALL = { tracker: 'Следопыт', feeder: 'Кормилец', guardian: 'Хранитель', seeker: 'Искатель' };
const _TR_TRAIT = { night_walk: 'Ночной ход', sprinter: 'Скороход', reckless: 'Азартный', careful: 'Осторожный', picky: 'Привередливый', hoarder: 'Запасливый', piggybank: 'Копилка', meticulous: 'Скрупулёзный', hardy: 'Выносливый', nose: 'Нюх', lunatic: 'Лунатик', loner: 'Одиночка' };
const _TR_TAL = { forest_fang: ['🦷', 'Лесной клык'], pass_stone: ['🪨', 'Каменный перевал'], ruin_lens: ['🔍', 'Линза руин'], swamp_lamp: ['🏮', 'Болотный фонарь'] };
const _TR_TIER = ['', 'I', 'II', 'III'];
const _TR_BIAS = { mora: ['🪙', 'Мору'], diamond: ['💎', 'Алмазы'], essence: ['💧', 'Эссенцию'], treat: ['🍖', 'лакомства'], talisman: ['🧿', 'талисманы'], bonus_xp: ['🐾', 'дополнительные Следы'] };
const _TR_BLD = { lounge: 'Лежанка', markers: 'Указатели', workshop: 'Мастерская' };
const _TR_HEAT = { warm: 'тепло', cold: 'холодно', found: 'находка' };

const _trTxt = s => _trE(String(s ?? '').replace(/(\d)\.(\d)/g, '$1,$2').replace(/(\d) (%|ч)/g, '$1\u00a0$2'));   // тексты правил приходят с точкой и обычным пробелом
const _trPl = s => s ? `<span class="tr-pl"><i class="sr-only">Плюс: </i>${_trTxt(s)}</span>` : '';
const _trMi = s => s ? `<span class="tr-mi"><i class="sr-only">Минус: </i>${_trTxt(s)}</span>` : '';
const _trOut = p => (_tr.me.activities || []).some(a => a.pet_id === p.id);   // ведущий занятия; Спутник сборку менять может
const _trTal = t => _TR_TAL[t.kind] || ['🧿', t.kind];
const _trDays = n => `${n}\u00a0${_trWord(n, 'день', 'дня', 'дней')}`;
// Шапка подэкрана: общий v3Head с «‹» назад на главный экран питомцев, под заголовком — Следы дня
const _trSubHead = title => v3Head(title, { back: 'trailBack()', sub: _trTraces(_tr.me, true) });
// Баланс из того же места, что и панель сверху (её обновляет сервер через WebSocket); null — число пока неизвестно, тогда решает сервер
function _trHave(key) {
  const d = typeof _profileData === 'object' && _profileData || null; if (!d) return null;
  const v = key === 'essence' ? d.essence : _v3Wallet(d)[key];
  return v == null || !Number.isFinite(Number(v)) ? null : Number(v);
}
const _trCallFx = c => { const t = _tr.me.rules.calling_texts?.[c] || []; return `${_trPl(t[0])}${_trMi(t[1])}`; };
const _trTraitFx = id => { const t = _tr.me.rules.traits?.[id] || []; return `${_trPl(t[0])}${_trMi(t[1])}`; };
function _trTalFx(t) {   // «Лес +15 %, Болота −10 %»
  const k = _tr.me.rules.talisman || {}, ways = (k.kinds || {})[t.kind] || [], name = r => (_TR_ROUTE[r] || [])[1] || '';
  return `${name(ways[0])} +${(k.plus || {})[t.tier] ?? ''}\u00a0%, ${name(ways[1])} −${k.minus ?? ''}\u00a0%`;
}
// Найденное одним списком (общий вид наград: Выслеживание использует тот же)
function _trFindRows(finds) {
  const rows = [];
  Object.entries(_TR_FIND).forEach(([key, f]) => { const n = Number((finds || {})[key]) || 0; if (n > 0) rows.push(`<li data-k="${key}" style="--i:${rows.length}"><span class="tr-g" aria-hidden="true">${f[0]}</span><span class="tr-gl">${f[1]}</span><b class="tr-n">+${fmt(n)}</b></li>`); });
  return rows.join('');
}
function _trFlyRows(host) {
  Object.entries(_TR_FIND).forEach(([key, f]) => { const g = f[2] && host.querySelector(`.tr-gain li[data-k="${key}"] .tr-g`); if (g) v3Fly(g, f[2], f[0], 4); });
}
// Экраны со своим состоянием (Выслеживание, Испытание) начинают с чистого листа при каждом входе с главного экрана
_TR_ENTER.track = () => { _tr.track = { pet: 0, done: null }; };
_TR_ENTER.trial = () => { const best = (_tr.me.pets || []).slice().sort((a, b) => (b.trial?.matches || 0) - (a.trial?.matches || 0) || b.level - a.level)[0]; _tr.trial = { pet: best ? best.id : 0 }; };

// ── Карточка питомца ─────────────────────────────────────────────────────────────────────────────────
function _trCardState(p) {
  const me = _tr.me, s = _trState(p), min = _trMinCost(me), act = s.act, lead = act && _trPet(act.pet_id);
  const what = act ? [_TR_KIND[act.kind] || act.kind, `${act.hours}\u00a0ч`, act.route ? _TR_ROUTE[act.route][1] : ''].filter(Boolean).join(' · ') : '';
  let title = s.label, sub = what, end = '';
  if (s.k === 'free') {
    sub = p.energy >= min ? _trFem(p, 'Готов к пути', 'Готова к пути') : `Мало сил: для самого короткого занятия нужно ${min}`;
    end = `<button type="button" class="v3-pill v3-pill--sm" onclick="trailSend(${p.id})"${p.energy < min ? ' disabled' : ''}>Отправить</button>`;
  } else if (s.k === 'ready') {
    if (s.lead) end = `<button type="button" class="v3-pill v3-pill--sm" data-run="${_trE(act.id)}" onclick="trailRun(this)">${act.kind === 'expedition' ? 'Выбрать путь' : 'Забрать'}</button>`;
    else { sub = lead ? `Награду заберёт ${lead.name}` : ''; end = lead ? `<button type="button" class="v3-link tr-go" onclick="trailPet(${lead.id})">${_trE(lead.name)} ›</button>` : ''; }
  } else {
    if (!s.lead && lead) sub = `${lead.name} · ${what}`;
    end = `<span class="tr-left"><small>осталось</small><b data-end="${_trTime(act.ends_at)}" data-id="${_trE(act.id)}">${_trDur(_trLeft(act))}</b></span>`;
  }
  return `<section class="tr-sec tr-state is-${s.k}" aria-label="Состояние питомца"><div class="tr-state-t"><b>${_trE(title)}</b><small>${_trE(sub)}</small></div><div class="tr-end">${end}</div></section>`;
}
function _trCardLevel(p) {
  const max = _tr.me.rules.max_level || 30, atMax = p.level >= max, atCeil = !atMax && p.level >= p.ceiling;
  const left = p.next_gate_days == null ? 0 : Math.max(1, p.next_gate_days - p.bond_days), nextCeil = Math.min(max, p.ceiling + 5);
  const xp = atMax ? '' : `${_trMeter(p.xp / Math.max(1,p.next_cost), { cls: 'tr-meter--xp', label: `Следы до следующего уровня: ${Math.floor(p.xp)} из ${p.next_cost}` })}<p class="tr-note">Следы: ${fmt(Math.floor(p.xp))} из ${fmt(p.next_cost)} до уровня ${p.level + 1}.</p>`;
  const wait = atCeil ? `<p class="tr-note">Для уровня ${p.level + 1} нужна ещё Связь: ${p.bond_days} из ${p.next_gate_days} дней. День засчитывается при получении награды за занятие.</p>` : '';
  const rail = `${_trMeter(p.level / max, { cls: 'tr-meter--lad', notch: p.ceiling / max, label: `Уровень ${p.level} из ${max}, потолок ступени ${p.ceiling}` })}<p class="tr-rail"><span>Потолок ступени: ${p.ceiling}\u00a0ур.</span><span>${p.next_gate_days == null ? 'Высшая ступень' : `Дальше ${nextCeil}\u00a0ур.: ещё ${_trDays(left)} Связи`}</span></p>`;
  return `<section class="tr-sec">${_trSec('Развитие')}<p class="tr-big"><b>${p.level}</b><span>из ${max}</span></p><p class="tr-note">${atMax?'Максимальный уровень достигнут.':'Уровень повышается автоматически за Следы. Забирай награды за занятия; первое кормление за сутки тоже даёт Следы.'}</p>${xp}${wait}${rail}</section>`;
}
function _trCardEnergy(p) {
  const me = _tr.me, min = _trMinCost(me), lounge = (me.rules.camp?.lounge || [])[me.camp?.levels?.lounge || 0] || 0, full = p.energy >= p.energy_max - 0.5;
  const note = full ? 'Силы полные.' : `${p.energy < min ? `Для самого короткого занятия нужно ${min} сил. ` : ''}Питомец отдыхает сам${lounge ? `, Лежанка в Лагере добавляет ${lounge}\u00a0%` : ''}. Быстрее восстановит еда.`;
  const feed = `<button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" onclick="trailFeed(${p.id})">Покормить</button>`;
  return `<section class="tr-sec">${_trSec('Силы', feed)}<p class="tr-big"><b>${Math.round(p.energy)}</b><span>из ${p.energy_max}</span></p>${_trMeter(p.energy / p.energy_max, { label: `Силы: ${Math.round(p.energy)} из ${p.energy_max}` })}<p class="tr-note">${note}</p></section>`;
}
function _trCardFacts(p) {
  const seal = _tr.me.rules.seal || {}, stars = Math.max(0, Math.min(5, Number(p.stars) || 0));
  return `<section class="tr-sec"><dl class="tr-facts"><div><dt>Выдержка<small>Растёт с уровнем и силами. Чем выше, тем надёжнее путь экспедиции.</small></dt><dd>${Math.round(p.resilience)}</dd></div><div><dt>Привязанность вида<small>Растёт от дней Связи всех питомцев этого вида${seal.bonus ? `: +${seal.bonus}\u00a0% Следов за звезду` : ''}.</small></dt><dd class="tr-stars" role="img" aria-label="Звёзд: ${stars} из 5">${'★'.repeat(stars)}<i>${'☆'.repeat(5 - stars)}</i></dd></div></dl></section>`;
}
function _trCardLoves(p) {
  const me = _tr.me, r = me.rules, any = p.favorite_route === 'any', route = _TR_ROUTE[p.favorite_route] || _TR_ROUTE.any;
  const food = (me.foods || []).find(f => f.id === p.favorite_food), bias = _TR_BIAS[p.find_bias];
  const row = (glyph, title, sub) => `<li class="tr-fact"><span class="tr-g" aria-hidden="true">${glyph}</span><span class="tr-nm"><b>${title}</b><small>${sub}</small></span></li>`;
  const rows = [
    row(route[0], any ? 'Любой маршрут' : _trE(route[1]), `Любимый маршрут: +${Math.round((r.affinity_bonus || 0.2) * 100)}\u00a0% Следов и выше шанс на развилке`),
    row(food ? _trE(food.icon) : '🍖', food ? _trE(food.name) : 'Любимое лакомство', `${p.fed_favorite ? 'Сыт любимым: +2 к Выдержке до конца суток' : 'Любимое: +2 к Выдержке до конца суток'}${food ? ` · в запасе ${fmt(food.quantity)}` : ''}`),
  ];
  if (bias) rows.push(row(bias[0], `Чаще находит: ${bias[1]}`, 'Склонность вида в находках'));
  return `<section class="tr-sec">${_trSec('Любит')}<ul class="tr-list tr-facts-list">${rows.join('')}</ul></section>`;
}
function _trCardBuild(p) {
  const me = _tr.me, r = me.rules, minCall = r.calling_min_level || 10, slots = p.trait_slots, cap = r.talisman_slots || 2, out = _trOut(p);
  const nextSlot = (r.trait_slot_levels || []).find(l => l > p.level);
  const slot = (title, fx) => `<li class="tr-bs"><b>${title}</b>${fx || ''}</li>`, empty = text => `<li class="tr-bs is-empty"><b>${text}</b></li>`;
  const call = p.calling ? slot(_trE(_TR_CALL[p.calling] || p.calling), _trCallFx(p.calling)) : empty(p.level >= minCall ? 'Не выбрано' : `Откроется на ${minCall}\u00a0уровне`);
  const traits = p.traits.map(id => slot(_trE(_TR_TRAIT[id] || id), _trTraitFx(id)));
  for (let i = p.traits.length; i < slots; i++) traits.push(empty('Свободный слот'));
  if (nextSlot) traits.push(empty(`Следующий слот на ${nextSlot}\u00a0уровне`));
  const tals = p.talismans.map(id => (me.talismans || []).find(t => t.id === id)).filter(Boolean).map(t => slot(`${_trTal(t)[0]} ${_trE(_trTal(t)[1])} ${_TR_TIER[t.tier] || ''}`, _trPl(_trTalFx(t))));
  for (let i = tals.length; i < cap; i++) tals.push(empty('Свободный слот'));
  const edit = out ? '' : `<button type="button" class="v3-link tr-go" onclick="trailBuild(${p.id})">Изменить ›</button>`;
  const grp = (title, items) => `<div class="tr-bg"><span class="v3-eyebrow">${title}</span><ul class="tr-bl">${items.join('')}</ul></div>`;
  return `<section class="tr-sec">${_trSec('Сборка', edit)}${out ? '<p class="tr-note">Пока питомец в пути, сборку менять нельзя.</p>' : ''}${grp('Призвание', [call])}${grp(`Черты · ${p.traits.length} из ${slots}`, traits)}${grp(`Талисманы · ${p.talismans.length} из ${cap}`, tals)}</section>`;
}
_TR_VIEWS.pet = me => {
  const p = _trPet(_tr.pet);
  if (!p) { _tr.view = 'hub'; return _TR_VIEWS.hub(me); }
  const head = v3Head(p.name, { back: 'trailBack()', sub: `${rarLabel(p.rarity)} · ${_trTraces(me, true)}`, end: `<span class="tr-ic tr-ic--lg" aria-hidden="true">${_trE(p.icon)}</span>` });
  return `${head}${_trCardState(p)}${_trCardLevel(p)}${_trCardEnergy(p)}${_trCardFacts(p)}${_trCardLoves(p)}${_trCardBuild(p)}`;
};

// ── Сборка: призвание, черты, талисманы; цена видна до сохранения ───────────────────────────────────────
function trailBuild(petId) {
  const p = _trPet(petId); if (!p) return;
  if (_trOut(p)) { toast('Пока питомец в пути, сборку менять нельзя.', false); return; }
  _tr.build = { pet: p.id, calling: p.calling || null, traits: [...p.traits], tal: [...p.talismans] };
  _trSheet(_trBuildHtml());
}
function trailBuildSet(key, value) {
  const b = _tr.build, p = b && _trPet(b.pet); if (!p) return;
  _haptic('select');
  if (key === 'calling') b.calling = b.calling === value ? null : value;
  else {
    const list = key === 'trait' ? b.traits : b.tal, cap = key === 'trait' ? p.trait_slots : _tr.me.rules.talisman_slots || 2, at = list.indexOf(value);
    if (at >= 0) list.splice(at, 1); else if (list.length < cap) list.push(value);
  }
  _trRepaint(_trBuildHtml());
}
function trailPresetLoad(slot) {
  const b = _tr.build, p = b && _trPet(b.pet);
  const row = (_tr.me?.build_presets || []).find(x => x.pet_id === p?.id && x.slot === slot);
  if (!row) return;
  if (row.build.talismans.some(id => !(_tr.me.talismans || []).some(t => t.id === id))) {
    toast('В шаблоне есть недоступный талисман. Сохраните обновлённый вариант.', false); return;
  }
  Object.assign(b, { calling: row.build.calling, traits: [...row.build.traits], tal: [...row.build.talismans], presetName: row.name, presetSlot: slot });
  _trRepaint(_trBuildHtml());
  toast('Шаблон выбран. Проверьте цену и примените сборку.', true);
}
async function trailPresetSave(button) {
  const b = _tr.build; if (!b) return;
  const slot = Number(el('tr-preset-slot')?.value || b.presetSlot || 1), name = String(el('tr-preset-name')?.value || '').trim();
  if (!name) { toast('Дайте шаблону название.', false); return; }
  const prior = (_tr.me.build_presets || []).find(x => x.pet_id === b.pet && x.slot === slot);
  if (prior && !await v3Confirm({ title: 'Заменить шаблон?', name: prior.name, sub: 'Сборка питомца не изменится. Сохранение бесплатно.', cta: 'Заменить шаблон' })) return;
  const body = { pet_id: b.pet, slot, name, calling: b.calling || null, traits: [...b.traits], talismans: [...b.tal] };
  _trRun(button, () => _trPost('build-presets', body, 'preset', b.pet, slot, name, JSON.stringify(body)).then(async () => {
    b.presetName = name; b.presetSlot = slot;
    await _trLoad();
    if (_tr.build === b && el('tr-sheet')) _trRepaint(_trBuildHtml());
    toast('Шаблон сохранён. Сборка питомца не изменялась.', true);
  }).catch(_trFail));
}
const _trSame = (a, b) => a.length === b.length && a.every(x => b.includes(x));
// Цена считается так же, как на сервере: пустой слот бесплатно, замена бесплатна раз в неделю, дальше Эссенция
function _trBuildCost(p, b) {
  const sw = _tr.me.rules.swap || {}, free = p.swap_free || {}, parts = [];
  if (p.calling && b.calling !== p.calling && !free.calling) parts.push(['Замена призвания', Number(sw.calling) || 0]);
  const removed = p.traits.filter(t => !b.traits.includes(t));
  if (removed.length && !free.traits) parts.push([`Замена черт: ${removed.length}`, (Number(sw.trait) || 0) * removed.length]);
  return { parts, total: parts.reduce((sum, x) => sum + x[1], 0), removed };
}
function _trBuildHtml() {
  const me = _tr.me, b = _tr.build, p = _trPet(b.pet);
  if (!p) return _trSheetHtml('Сборка', '<p class="tr-note">Питомец не найден.</p>');
  const r = me.rules, minCall = r.calling_min_level || 10, slots = p.trait_slots, free = p.swap_free || {}, talCap = r.talisman_slots || 2, sw = r.swap || {};
  const opt = (role, on, f, attrs, inner, off) => `<button type="button" class="tr-opt" role="${role}" aria-checked="${on}" data-f="${f}" ${attrs}${off ? ' disabled' : ''}>${inner}</button>`;
  const callNote = !p.calling ? 'Первое призвание бесплатно.' : free.calling ? 'Заменить призвание на этой неделе можно бесплатно.' : `Заменить призвание снова стоит ${sw.calling} Эссенции: на этой неделе его уже меняли.`;
  const calling = p.level < minCall ? `<p class="tr-note">Призвание открывается с ${minCall}\u00a0уровня, сейчас ${p.level}.</p>`
    : `<div class="tr-opts" role="radiogroup" aria-label="Призвание">${(me.callings || []).map(c => opt('radio', b.calling === c, `call-${c}`, `onclick="trailBuildSet('calling','${c}')"`, `<span class="tr-opt-t"><b>${_trE(_TR_CALL[c] || c)}</b><small>${_trCallFx(c)}</small></span>`)).join('')}</div><p class="tr-note">${callNote}</p>`;
  const traitNote = !p.traits.length ? 'Пустой слот заполняется бесплатно.' : free.traits ? 'Заменить черту на этой неделе можно бесплатно.' : `Каждая убранная черта стоит ${sw.trait} Эссенции: на этой неделе черты уже меняли.`;
  const traits = !slots ? `<p class="tr-note">Слоты черт открываются на ${(r.trait_slot_levels || []).join(', ')}\u00a0уровнях, сейчас ${p.level}.</p>`
    : `${b.traits.length >= slots ? '<p class="tr-note">Слоты заняты. Чтобы выбрать другую черту, сначала уберите одну.</p>' : ''}<div class="tr-opts" role="group" aria-label="Черты">${(me.traits || []).map(id => { const on = b.traits.includes(id); return opt('checkbox', on, `trait-${id}`, `onclick="trailBuildSet('trait','${id}')"`, `<span class="tr-opt-t"><b>${_trE(_TR_TRAIT[id] || id)}</b><small>${_trTraitFx(id)}</small></span>`, !on && b.traits.length >= slots); }).join('')}</div><p class="tr-note">${traitNote}</p>`;
  const owned = me.talismans || [];
  const kinds = b.tal.map(id => (owned.find(t => t.id === id) || {}).kind).filter(Boolean), pair = kinds.length > 1 && kinds[0] === kinds[1];
  const tals = owned.length ? `<div class="tr-opts" role="group" aria-label="Талисманы">${owned.map((t, i) => {
    const on = b.tal.includes(t.id), [ic, nm] = _trTal(t), holder = t.pet_id && t.pet_id !== p.id ? _trPet(t.pet_id) : null;
    return opt('checkbox', on, `tal-${i}`, `data-id="${_trE(t.id)}" onclick="trailBuildSet('tal',this.dataset.id)"`, `<span class="tr-opt-t"><b>${ic} ${_trE(nm)} ${_TR_TIER[t.tier] || ''}</b><small>${_trPl(_trTalFx(t))}${holder ? `<span>Сейчас у ${_trE(holder.name)}, перейдёт сюда</span>` : ''}</small></span>`, !on && b.tal.length >= talCap);
  }).join('')}</div>${pair ? `<p class="tr-note">Два одинаковых талисмана: +${r.talisman?.set}\u00a0% Следов на их маршруте.</p>` : ''}`
    : '<p class="tr-note">Талисманов пока нет. Их находят питомцы в Походах и Экспедициях.</p>';
  const cost = _trBuildCost(p, b), have = _trHave('essence'), short = cost.total > 0 && have != null && have < cost.total;
  const changed = (b.calling || null) !== (p.calling || null) || !_trSame(b.traits, p.traits) || !_trSame(b.tal, p.talismans);
  const why = !changed ? 'Сборка не изменилась.' : short ? `Не хватает Эссенции: нужно ${cost.total}, у вас ${fmt(have)}.` : cost.total ? `Замена стоит ${cost.total} Эссенции${have != null ? `, у вас ${fmt(have)}` : ''}.` : 'Это бесплатно.';
  const presets = (_tr.me.build_presets || []).filter(x => x.pet_id === p.id);
  const saved = `<details class="tr-grp"><summary>Мои шаблоны · ${presets.length} из 3</summary><p class="tr-note">Шаблон хранит выбор. Загрузка ничего не меняет и не списывает; применение оплачивается по обычным правилам.</p><div class="tr-chips">${presets.map(x => `<button type="button" class="tr-chip" onclick="trailPresetLoad(${x.slot})">${_trE(x.name)}</button>`).join('')}</div><div class="tr-preset-form"><label class="tr-note" for="tr-preset-name">Название шаблона</label><input id="tr-preset-name" maxlength="40" value="${_trE(b.presetName || '')}" oninput="_tr.build.presetName=this.value" placeholder="Например, ночные походы"><label class="tr-note" for="tr-preset-slot">Место сохранения</label><select id="tr-preset-slot" onchange="_tr.build.presetSlot=Number(this.value)">${[1,2,3].map(n => `<option value="${n}"${n === (b.presetSlot || 1) ? ' selected' : ''}>${n}${presets.some(x => x.slot === n) ? ' · заменить' : ' · свободно'}</option>`).join('')}</select><button type="button" class="v3-link" onclick="trailPresetSave(this)">Сохранить шаблон бесплатно</button></div></details>`;
  const body = `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span><b>${_trE(p.name)}</b><small>Уровень ${p.level}</small></span></p>${saved}
    <div class="tr-grp"><span class="v3-eyebrow">Призвание</span>${calling}</div>
    <div class="tr-grp"><span class="v3-eyebrow">Черты · ${b.traits.length} из ${slots}</span>${traits}</div>
    <div class="tr-grp"><span class="v3-eyebrow">Талисманы · ${b.tal.length} из ${talCap}</span>${tals}</div>`;
  const foot = `<p class="tr-note tr-why" role="status">${_trE(why)}</p><p class="tr-err" role="alert" hidden></p><button type="button" class="v3-pill v3-pill--full" onclick="trailBuildGo(this)"${!changed || short ? ' disabled' : ''}>Применить сборку</button>`;
  return _trSheetHtml('Сборка', body, foot);
}
function trailBuildGo(button) {
  const b = _tr.build, p = b && _trPet(b.pet); if (!p) return;
  const cost = _trBuildCost(p, b), body = { pet_id: p.id, calling: b.calling || null, traits: [...b.traits], talismans: [...b.tal], expected_essence: _trBuildCost(p, b).total };
  const run = () => _trRun(button, () => _trPost('build', body, 'build', p.id, body.calling || '', [...body.traits].sort().join(','), [...body.talismans].sort().join(','), body.expected_essence).then(r => {
    _haptic('success'); trailClose();
    toast(r.essence_spent ? `Сборка сохранена · −${r.essence_spent} Эссенции` : 'Сборка сохранена', true, { icon: p.icon });
    return _trRefresh();
  }).catch(_trFail));
  if (!cost.total) { run(); return; }
  const have = _trHave('essence');
  v3Confirm({
    title: 'Заменить сборку', visual: p.icon, name: p.name, sub: `Уровень ${p.level}`, cta: `Заплатить ${cost.total} Эссенции`,
    rows: [...cost.parts.map(([k, v]) => [k, `${fmt(v)} 💧`]), ...(have != null ? [['На счёте', `${fmt(have)} 💧`], ['Останется', `${fmt(Math.max(0, have - cost.total))} 💧`, true]] : [['Итого', `${fmt(cost.total)} 💧`, true]])],
  }).then(ok => { if (ok) run(); });
}

// ── Кормление: еда из запасов сундуков; окно остаётся открытым, можно покормить ещё ──────────────────
function trailFeed(petId) {
  const p = _trPet(petId); if (!p) return;
  _tr.feed = { pet: p.id, note: '' };
  _trSheet(_trFeedHtml());
}
function _trFeedHtml() {
  const me = _tr.me, f = _tr.feed, p = _trPet(f.pet);
  if (!p) return _trSheetHtml('Кормление', '<p class="tr-note">Питомец не найден.</p>');
  const foods = me.foods || [], any = foods.some(x => x.quantity > 0), xp = me.rules.feed_xp || 10;
  const rows = foods.map(x => {
    const fav = x.id === p.favorite_food, gain = Math.max(0, Math.min(p.energy_max, p.energy + x.restore) - p.energy);
    const sub = `+${x.restore} сил${gain < x.restore ? ` (поместится ${Math.round(gain)})` : ''} · в запасе ${fmt(x.quantity)}`;
    return `<li class="tr-food${fav ? ' is-fav' : ''}"><span class="tr-ic" aria-hidden="true">${_trE(x.icon)}</span><span class="tr-nm"><b>${_trE(x.name)}</b><small>${sub}</small>${fav ? `<small class="tr-fav">${p.fed_favorite ? 'Сыт любимым до конца суток' : 'Любимое: +2 к Выдержке до конца суток'}</small>` : ''}</span><button type="button" class="v3-pill v3-pill--sm${x.quantity ? '' : ' v3-pill--ghost'}" data-id="${_trE(x.id)}" onclick="trailFeedGo(this)"${x.quantity ? '' : ' disabled'}>${x.quantity ? 'Дать' : 'Нет'}</button></li>`;
  }).join('');
  const body = `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span><b>${_trE(p.name)}</b><small>Силы ${Math.round(p.energy)} из ${p.energy_max}</small></span></p>
    ${f.note ? `<p class="tr-ok" role="status">${_trE(f.note)}</p>` : ''}
    ${any ? '' : '<p class="tr-note">Еды в запасе нет. Её находят питомцы на Тропе и получают из сундуков.</p>'}
    <ul class="tr-list tr-foods">${rows}</ul>
    <p class="tr-note">${p.fed_today ? 'Следы за кормление сегодня уже получены.' : `Первое кормление за сутки даёт ещё +${xp} Следов.`}</p>`;
  return _trSheetHtml('Покормить', body, `<p class="tr-err" role="alert" hidden></p><button type="button" class="v3-pill v3-pill--full v3-pill--ghost" onclick="trailClose()">Готово</button>`);
}
function trailFeedGo(button) {
  const f = _tr.feed, p = f && _trPet(f.pet), id = button.dataset.id; if (!p || !id) return;
  const food = (_tr.me.foods || []).find(x => x.id === id);
  _trRun(button, () => _trPost('feed', { pet_id: p.id, food_id: id }, 'feed', p.id, id).then(async r => {
    _haptic('success');
    const bits = [`${food ? food.name : 'Еда'}: силы ${Math.round(r.energy)} из ${p.energy_max}`];
    if (Number(r.xp_credited) > 0) bits.push(`+${fmt(Math.round(r.xp_credited))} Следов`);
    if (r.favorite) bits.push('сыт любимым до конца суток');
    f.note = bits.join(' · ');
    await _trRefresh();
    if (document.getElementById('tr-sheet') && _tr.feed === f) _trRepaint(_trFeedHtml());
  }).catch(_trFail));
}

// ── Лагерь: три постройки, одна стройка за раз; перековка талисманов в Мастерской ────────────────────
function _trBldFx(b, level) {   // что постройка даёт на этом уровне
  const c = _tr.me.rules.camp || {};
  if (b === 'lounge') return level ? `Отдых сил +${(c.lounge || [])[level]}\u00a0%` : 'Отдых сил без бонуса';
  if (b === 'markers') return `Повтор маршрута за день: Следы ×${_trMult((c.markers || [])[level])}`;
  return level === 0 ? 'Без улучшения мастерской · талисманы до тира I' : `Талисманы до тира ${_TR_TIER[(c.workshop || [])[level]] || ''}${level === 1 ? ' · первый уровень постройки' : ''}`;
}
function _trBldRow(b, me, job) {
  const camp = me.camp, lv = camp.levels[b] || 0, cost = camp.next_costs?.[b], name = _TR_BLD[b];
  const pips = Array.from({ length: 5 }, (_, i) => `<i${i < lv ? ' class="on"' : ''}></i>`).join('');
  let next = '';
  if (job && job.building === b) next = `<p class="tr-note tr-busy">Строится: уровень ${job.to_level}</p>`;
  else if (cost) {
    const mora = _trHave('mora'), ess = _trHave('essence'), lack = [];
    if (mora != null && mora < cost.mora) lack.push(`Моры ${fmt(cost.mora - mora)}`);
    if (ess != null && ess < cost.essence) lack.push(`Эссенции ${fmt(cost.essence - ess)}`);
    const why = !job && lack.length ? `Не хватает: ${lack.join(', ')}.` : '';
    next = `<div class="tr-bld-n"><span class="tr-nm"><b>Уровень ${lv + 1}: ${_trE(_trBldFx(b, lv + 1))}</b><small>${fmt(cost.mora)}\u00a0🪙 · ${fmt(cost.essence)}\u00a0💧 · ${cost.hours}\u00a0ч</small></span><button type="button" class="v3-pill v3-pill--sm" onclick="trailUpgrade('${b}')"${job ? ' aria-describedby="tr-job" disabled' : why ? ' disabled' : ''}>Улучшить</button></div>${why ? `<p class="tr-note tr-why">${_trE(why)}</p>` : ''}`;
  } else next = '<p class="tr-note">Высший уровень.</p>';
  return `<li class="tr-bld"><div class="tr-bld-h"><span class="tr-nm"><b>${name}</b><small>${_trE(_trBldFx(b, lv))}</small></span><span class="tr-bld-l" role="img" aria-label="Уровень ${lv} из 5"><b>${lv}</b><small>из 5</small></span></div><div class="tr-pips" aria-hidden="true">${pips}</div>${next}</li>`;
}
function _trNeedWorkshop(tier) { const w = _tr.me.rules.camp?.workshop || []; const lv = w.findIndex(x => x > tier); return lv < 0 ? 5 : lv; }
function _trReforgeRows(me) {
  const tals = (me.talismans || []).slice().sort((a, b) => String(a.kind).localeCompare(String(b.kind)) || b.tier - a.tier), top = (me.rules.camp?.workshop || [])[me.camp?.levels?.workshop || 0] || 1;
  if (!tals.length) return '<div class="v3-empty tr-empty"><b>Талисманов пока нет.</b><span>Их находят питомцы в Походах и Экспедициях.</span></div>';
  return `<ul class="tr-list">${tals.map(t => {
    const [ic, nm] = _trTal(t), holder = t.pet_id ? _trPet(t.pet_id) : null, cost = (me.rules.reforge || {})[t.tier];
    let end = '', note = holder ? `носит ${holder.name}` : '';
    if (t.tier >= 3 || cost == null) note = [note, 'высший тир'].filter(Boolean).join(' · ');
    else if (t.tier >= top) note = [note, `нужна Мастерская ${_trNeedWorkshop(t.tier)}\u00a0ур.`].filter(Boolean).join(' · ');
    else end = `<span class="tr-act"><button type="button" class="v3-pill v3-pill--sm v3-pill--ghost" data-id="${_trE(t.id)}" onclick="trailReforge(this.dataset.id)">Перековать</button><small>${fmt(cost)}\u00a0💧</small></span>`;
    return `<li class="tr-row tr-tal"><span class="tr-ic" aria-hidden="true">${ic}</span><span class="tr-nm"><b>${_trE(nm)} ${_TR_TIER[t.tier] || ''}</b><small>${_trE(_trTalFx(t))}</small>${note ? `<small>${_trE(note)}</small>` : ''}</span><span class="tr-end">${end}</span></li>`;
  }).join('')}</ul>`;
}
_TR_VIEWS.camp = me => {
  const camp = me.camp || { levels: {}, job: null }, job = camp.job && !camp.job.done ? camp.job : null;
  const rows = ['lounge', 'markers', 'workshop'].map(b => _trBldRow(b, me, job)).join('');
  const busy = job ? `<div class="tr-state is-busy" id="tr-job" role="status"><div class="tr-state-t"><b>Идёт стройка</b><small>${_trE(_TR_BLD[job.building] || job.building)}, уровень ${job.to_level}. Другую можно начать после неё.</small></div><div class="tr-end"><span class="tr-left"><small>осталось</small><b data-end="${_trTime(job.ends_at)}" data-id="camp-${_trTime(job.ends_at)}">${_trDur(_trTime(job.ends_at) - _trNow())}</b></span></div></div>` : '';
  return `${_trSubHead('Лагерь')}${busy}<section class="tr-sec">${_trSec('Постройки')}<p class="tr-note">Каждую можно улучшить до 5 уровня. Стройка идёт сама, пока вас нет: одна за раз.</p><ul class="tr-list tr-blds">${rows}</ul></section>
    <section class="tr-sec">${_trSec('Перековка талисманов', `<span class="tr-count">${(me.talismans || []).length}</span>`)}<p class="tr-note">Перековка поднимает тир талисмана за Эссенцию. Высший тир открывает Мастерская.</p>${_trReforgeRows(me)}</section>`;
};
function trailUpgrade(building) {
  const camp = _tr.me.camp, lv = camp.levels[building] || 0, cost = camp.next_costs?.[building]; if (!cost || !_TR_BLD[building]) return;
  const mora = _trHave('mora'), ess = _trHave('essence');
  const rows = [['Постройка', `${_TR_BLD[building]}, ${lv} → ${lv + 1}`], ['Что даст', _trBldFx(building, lv + 1)], ['Мора', `${fmt(cost.mora)} 🪙`], ['Эссенция', `${fmt(cost.essence)} 💧`], ['Стройка займёт', `${cost.hours}\u00a0ч`]];
  if (mora != null) rows.push(['Моры останется', `${fmt(Math.max(0, mora - cost.mora))} 🪙`]);
  if (ess != null) rows.push(['Эссенции останется', `${fmt(Math.max(0, ess - cost.essence))} 💧`, true]);
  v3Confirm({ title: 'Улучшить постройку', visual: '⛺', name: `${_TR_BLD[building]} → ${lv + 1}\u00a0ур.`, sub: 'Плата списывается сразу', cta: 'Начать стройку', rows }).then(ok => {
    if (!ok) return;
    _trRun(null, () => _trPost('camp/upgrade', { building }, 'camp', building, lv + 1).then(r => {
      _haptic('success'); toast(`${_TR_BLD[building]}: стройка до ${r.to_level}\u00a0ур. началась · ${r.cost.hours}\u00a0ч`, true);
      return _trRefresh();
    }).catch(_trFail));
  });
}
function trailReforge(talismanId) {
  const t = (_tr.me.talismans || []).find(x => x.id === talismanId); if (!t) return;
  const cost = (_tr.me.rules.reforge || {})[t.tier]; if (cost == null) return;
  const [ic, nm] = _trTal(t), ess = _trHave('essence');
  const rows = [['Тир', `${_TR_TIER[t.tier]} → ${_TR_TIER[t.tier + 1]}`], ['Эссенция', `${fmt(cost)} 💧`]];
  if (ess != null) rows.push(['Эссенции останется', `${fmt(Math.max(0, ess - cost))} 💧`, true]);
  v3Confirm({ title: 'Перековать талисман', visual: ic, name: `${nm} ${_TR_TIER[t.tier]}`, sub: _trTalFx(t), cta: 'Перековать', rows }).then(ok => {
    if (!ok) return;
    _trRun(null, () => _trPost('talisman/reforge', { talisman_id: t.id }, 'reforge', t.id, t.tier).then(r => {
      _haptic('success'); toast(`${nm}: тир ${_TR_TIER[r.tier]}`, true, { icon: ic });
      return _trRefresh();
    }).catch(_trFail));
  });
}

// ── Выслеживание: поле 3×3, три подсказки даром, каждое открытие стоит очко внимания ───────────────────
function _trBoard(track, o = {}) {
  const by = new Map((track.opened || []).map(c => [c.cell, c]));
  const cells = Array.from({ length: 9 }, (_, i) => {
    const c = by.get(i), pos = `ряд ${Math.floor(i / 3) + 1}, столбец ${i % 3 + 1}`;
    if (c) return `<div class="tr-cell is-${c.heat}" role="img" aria-label="${pos}: ${_TR_HEAT[c.heat] || ''}"><b>${c.heat === 'found' ? '✦' : ''}${_TR_HEAT[c.heat] || ''}</b></div>`;
    if (o.hidden === i) return `<div class="tr-cell is-lost" role="img" aria-label="${pos}: здесь была находка"><b>здесь</b></div>`;
    if (o.live) return `<button type="button" class="tr-cell is-shut" data-f="cell-${i}" onclick="trailTrackOpen(${i})" aria-label="${pos}: закрыта. Открыть за одно очко внимания"></button>`;
    return `<div class="tr-cell is-shut" role="img" aria-label="${pos}: закрыта"></div>`;
  });
  return `<div class="tr-board" role="group" aria-label="Поле три на три" tabindex="-1">${cells.join('')}</div>`;
}
const _trPips = (left, total) => `<span class="tr-pips tr-pips--pt" role="img" aria-label="Очков внимания: ${left} из ${total}">${Array.from({ length: Math.max(total, left) }, (_, i) => `<i${i < left ? ' class="on"' : ''}></i>`).join('')}</span>`;
const _trLegend = '<p class="tr-note">Тепло: находка рядом, считая по диагонали. Холодно: дальше. Находка отмечена знаком ✦.</p>';
function _trTrackOpenGame(track) {
  const p = _trPet(track.pet_id), total = p ? p.track_points : track.points;
  return `<section class="tr-sec">${_trSec('Идёт выслеживание', _trPips(track.points, total))}${p ? `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span><b>${_trE(p.name)}</b><small>Очков внимания: ${track.points}. Каждое открытие стоит одно.</small></span></p>` : ''}${_trBoard(track, { live: true })}${_trLegend}</section>`;
}
function _trTrackDone(done) {
  const won = done.status === 'won', p = _trPet(done.pet_id), rows = _trFindRows(done.result?.finds);
  const left = _tr.me.track?.attempts_left || 0;
  return `<section class="tr-sec">${_trSec(won ? 'Находка найдена' : 'Не нашли')}${p ? `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span><b>${_trE(p.name)}</b><small>${won ? 'Нашёл, что было спрятано' : 'Очки внимания закончились'}</small></span></p>` : ''}${_trBoard(done, { hidden: won ? -1 : done.hidden })}
    ${won ? (rows ? `<ul class="tr-gain" aria-label="Что получено">${rows}</ul>` : '<p class="tr-note">На этот раз без наград.</p>') : '<p class="tr-note">Ничего не потеряно. Находка была в клетке с пометкой «здесь».</p>'}
    <div class="tr-two">${left ? '<button type="button" class="v3-pill" onclick="trailTrackAgain()">Ещё раз</button>' : `<p class="tr-note">Попытки на сегодня закончились.</p>`}<button type="button" class="v3-pill v3-pill--ghost" onclick="trailBack()">К Тропе</button></div></section>`;
}
function _trTrackPicker(me) {
  const t = _tr.track, left = me.track?.attempts_left || 0, daily = me.rules.track?.daily || 2, free = me.rules.track?.free_clues || 3;
  const pets = (me.pets || []).slice().sort((a, b) => b.track_points - a.track_points || b.level - a.level || a.id - b.id);
  if (!t.pet || !_trPet(t.pet)) t.pet = pets[0] ? pets[0].id : 0;
  const best = pets[0] && (!pets[1] || pets[0].track_points > pets[1].track_points) ? pets[0].id : null;
  const chips = pets.map(p => `<button type="button" class="tr-chip tr-chip--i${p.id === best ? ' is-best' : ''}" role="radio" aria-checked="${p.id === t.pet}" data-f="tpet-${p.id}" onclick="trailTrackPet(${p.id})">${_trBestMark(p.id === best)}<span aria-hidden="true">${_trE(p.icon)}</span><b>${_trE(p.name)}</b><small>очков внимания: ${p.track_points}</small></button>`).join('');
  return `<section class="tr-sec">${_trSec('Выслеживание', `<span class="tr-count">Попыток: ${left} из ${daily}</span>`)}<p class="tr-note">Находка спрятана в одной из девяти клеток. Сначала открыты ${free} подсказки: «тепло» значит, что она рядом, «холодно» значит, что дальше. Остальные клетки открываются за очки внимания: чем выше уровень питомца, тем их больше.</p>
    ${pets.length ? `<div class="tr-grp"><span class="v3-eyebrow">Кто ищет</span><div class="tr-chips tr-chips--2" role="radiogroup" aria-label="Кто ищет">${chips}</div></div>` : ''}
    ${left ? '' : '<p class="tr-note tr-why">Попытки на сегодня закончились. Завтра будут новые.</p>'}
    <button type="button" class="v3-pill v3-pill--full tr-cta" onclick="trailTrackStart(this)"${left && t.pet ? '' : ' disabled'}>Начать выслеживание</button></section>`;
}
_TR_VIEWS.track = me => {
  const t = _tr.track ||= { pet: 0, done: null }, open = me.track?.open;
  const body = open ? _trTrackOpenGame(open) : t.done ? _trTrackDone(t.done) : _trTrackPicker(me);
  return `${_trSubHead('Выслеживание')}${body}`;
};
function trailTrackPet(id) { _haptic('select'); _tr.track.pet = Number(id); _trRender(); document.querySelector(`#pg-pets [data-f="tpet-${id}"]`)?.focus({ preventScroll: true }); }
function trailTrackAgain() { _haptic('select'); _tr.track.done = null; _trRender(); }
function trailTrackStart(button) {
  const t = _tr.track, p = t && _trPet(t.pet); if (!p) return;
  _trRun(button, () => _trPost('track/start', { pet_id: p.id }, 'tstart', p.id).then(r => {
    _haptic('success'); t.done = null;
    _tr.me.track = { attempts_left: r.attempts_left, open: r.track };
    _trRender(); document.querySelector('#pg-pets .tr-board')?.focus({ preventScroll: true });
  }).catch(_trFail));
}
function trailTrackOpen(cell) {
  const t = _tr.track, open = _tr.me.track?.open; if (!t || !open) return;
  _trRun(null, () => _trPost('track/open', { track_id: open.id, cell }, 'topen', open.id, cell).then(r => {
    const next = r.track;
    if (next.status === 'open') { _tr.me.track.open = next; _haptic((next.opened.find(c => c.cell === cell) || {}).heat === 'warm' ? 'medium' : 'select'); _trRender(); }
    else {
      _tr.me.track = { attempts_left: _tr.me.track.attempts_left, open: null }; t.done = next;
      _haptic(next.status === 'won' ? 'success' : 'warning'); _trRender();
      if (next.status === 'won') _trFlyRows(el('pg-pets'));
      _trLoad();   // находки уже на счёте: тихо обновляем данные (талисманы, еда)
    }
    document.querySelector('#pg-pets .tr-board')?.focus({ preventScroll: true });
  }).catch(_trFail));
}

// ── Испытание недели: сколько тегов закрывает сборка каждого питомца, видно до сдачи ─────────────────────
function _trTrialTags(trial) {
  const k = _tr.me.rules.talisman?.kinds || {}, route = _TR_ROUTE[trial.route] || _TR_ROUTE.any, kind = Object.keys(k).find(x => k[x][0] === trial.route);
  const tempo = trial.tempo === 9 ? 'night_walk' : 'sprinter', style = trial.style === 'careful' ? 'careful' : 'reckless';
  return [
    { key: 'route', label: 'Маршрут', value: `${route[0]} ${route[1]}`, how: `любимый маршрут питомца или талисман «${kind ? _TR_TAL[kind][1] : route[1]}»`, need: `нужен любимый маршрут «${route[1]}» или талисман «${kind ? _TR_TAL[kind][1] : ''}»` },
    { key: 'tempo', label: 'Темп', value: `${trial.tempo}\u00a0ч`, how: `черта «${_TR_TRAIT[tempo]}»`, need: `нужна черта «${_TR_TRAIT[tempo]}»` },
    { key: 'style', label: 'Стиль', value: style === 'careful' ? 'Осторожный путь' : 'Рискованный путь', how: `черта «${_TR_TRAIT[style]}»`, need: `нужна черта «${_TR_TRAIT[style]}»` },
  ];
}
function _trTrialPets(me, tags) {
  const t = _tr.trial ||= { pet: 0 };
  const pets = (me.pets || []).slice().sort((a, b) => (b.trial?.matches || 0) - (a.trial?.matches || 0) || b.level - a.level || a.id - b.id);
  if (!t.pet || !_trPet(t.pet)) t.pet = pets[0] ? pets[0].id : 0;
  const best = pets[0]?.trial?.matches > 0 && (!pets[1] || pets[0].trial.matches > (pets[1].trial?.matches || 0)) ? pets[0].id : null;
  return pets.map(p => {
    const hits = p.trial?.hits || {}, n = p.trial?.matches || 0;
    const marks = tags.map(g => `<span class="tr-tag${hits[g.key] ? ' is-hit' : ''}"><i class="sr-only">${hits[g.key] ? 'Закрыто: ' : 'Не закрыто: '}</i>${g.label}</span>`).join('');
    return `<li><button type="button" class="tr-row tr-pet${p.id === t.pet ? ' is-picked' : ''}${p.id === best ? ' is-best' : ''}" role="radio" aria-checked="${p.id === t.pet}" data-f="trial-${p.id}" onclick="trailTrialPick(${p.id})">${_trBestMark(p.id === best)}<span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span class="tr-nm"><b>${_trE(p.name)}</b><span class="tr-tags">${marks}</span></span><span class="tr-hits" aria-label="Закрыто тегов: ${n} из 3"><b>${n}</b><small>из 3</small></span></button></li>`;
  }).join('');
}
_TR_VIEWS.trial = me => {
  const trial = me.trial || {}, tags = trial.tags ? _trTrialTags(trial.tags) : [], t = _tr.trial ||= { pet: 0 }, ess = trial.essence || {};
  const head = _trSubHead('Испытание недели');
  if (!tags.length) return `${head}<section class="tr-sec"><div class="v3-empty tr-empty"><b>Испытание пока не объявлено.</b></div></section>`;
  const rows = tags.map(g => `<li class="tr-tagrow"><span class="tr-nm"><small>${g.label}</small><b>${_trE(g.value)}</b><small>Закрывает: ${_trE(g.how)}</small></span></li>`).join('');
  const reward = `<p class="tr-note">Награда: ${fmt(trial.xp || 0)} Следов и Эссенция по числу закрытых тегов: ${[1, 2, 3].map(n => `${ess[n]}\u00a0за ${n}`).join(', ')}. Сдать можно один раз в неделю.</p>`;
  if (trial.done) return `${head}<section class="tr-sec">${_trSec('Теги недели')}<ul class="tr-list tr-tagl">${rows}</ul>${reward}<div class="v3-empty tr-empty"><b>На этой неделе испытание сдано.</b><span>Новое появится в понедельник.</span></div></section>`;
  const p = _trPet(t.pet), hits = p?.trial?.hits || {}, n = p?.trial?.matches || 0, miss = tags.filter(g => !hits[g.key]);
  const need = n < 3 && p ? `<p class="tr-note">Не закрыто: ${miss.map(g => `${_trE(g.label.toLowerCase())} (${_trE(g.need)})`).join('; ')}.</p>` : '';
  const why = !p ? 'Питомцев пока нет.' : n < 1 ? 'Сборка этого питомца не закрывает ни одного тега.' : '';
  const cta = n ? `Сдать на ${n} из 3` : 'Сдать испытание';
  return `${head}<section class="tr-sec">${_trSec('Теги недели')}<ul class="tr-list tr-tagl">${rows}</ul>${reward}</section>
    <section class="tr-sec">${_trSec('Питомец для испытания')}<p class="tr-note">Проверка мгновенная: питомец остаётся с вами, силы сохраняются.</p><ul class="tr-list" role="radiogroup" aria-label="Питомец для испытания">${_trTrialPets(me, tags)}</ul>${need}${why ? `<p class="tr-note tr-why">${why}</p>` : ''}
    <button type="button" class="v3-pill v3-pill--full tr-cta" onclick="trailTrialGo(this)"${why ? ' disabled' : ''}>${cta}${n ? ` · Эссенция ${ess[n]}` : ''}</button></section>`;
};
function trailTrialPick(id) { _haptic('select'); _tr.trial.pet = Number(id); _trRender(); document.querySelector(`#pg-pets [data-f="trial-${id}"]`)?.focus({ preventScroll: true }); }
function trailTrialGo(button) {
  const p = _trPet(_tr.trial?.pet), n = p?.trial?.matches || 0; if (!p || n < 1) return;
  const ess = (_tr.me.trial?.essence || {})[n], xp = _tr.me.trial?.xp || 0;
  v3Confirm({
    title: 'Сдать испытание', visual: p.icon, name: p.name, sub: `Закрыто тегов: ${n} из 3`, cta: 'Сдать',
    rows: [['Эссенция', `${fmt(ess)} 💧`, true], ['Следы', `до ${fmt(xp)}`]], note: 'Испытание сдаётся один раз в неделю. Теги и сборку после сдачи менять можно.',
  }).then(ok => {
    if (!ok) return;
    _trRun(button, () => _trPost('trial', { pet_id: p.id, difficulty: n }, 'trial', p.id, n).then(r => {
      _haptic('success'); _trTrialResult(p, r);
      return _trRefresh();
    }).catch(_trFail));
  });
}
function _trTrialResult(p, r) {
  const rows = [];
  const add = (glyph, n, label, kind = '') => rows.push(`<li data-k="${kind}" style="--i:${rows.length}"><span class="tr-g" aria-hidden="true">${glyph}</span><span class="tr-gl">${label}</span><b class="tr-n">+${fmt(n)}</b></li>`);
  if (Number(r.essence) > 0) add('💧', r.essence, 'Эссенция', 'essence');
  if (Number(r.xp_credited) >= 0.5) add('🐾', Math.round(r.xp_credited), 'Следы');
  if (Number(r.stage_essence) > 0) add('💧', r.stage_essence, 'Эссенция за ступень');
  const up = Number(r.level_after) > Number(r.level_before);
  const level = up ? `<p class="tr-lv is-up"><span>Новый уровень</span><b>${r.level_before} → ${r.level_after}</b></p>` : '';
  const body = `<p class="tr-who"><span class="tr-ic" aria-hidden="true">${_trE(p.icon)}</span><span><b>Испытание сдано</b><small>${_trE(p.name)} · закрыто тегов: ${r.matches} из 3</small></span></p><ul class="tr-gain" aria-label="Что получено">${rows.join('')}</ul>${level}`;
  _trSheet(_trSheetHtml('Награда', body, '<button type="button" class="v3-pill v3-pill--full" onclick="trailClose()">Готово</button>'));
  _trFlyRows(document.getElementById('tr-sheet'));
}
