# «По слотам» — компактный редизайн (Стадия 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить текущие два ряда чипов-фильтров (линейка + статус) над сеткой косметики
во вкладке «Внешний вид» на компактный «умный ряд» (поиск + пилюля выбора линейки +
кнопка-переключатель статуса), добавить мини-измеритель прогресса на заголовок каждой
секции-слота, добавить статичный акцент цвета линейки на карточки предметов, улучшить
пустое состояние фильтра — без изменения бэкенда, без нового переключателя режимов
(«По коллекциям» — отдельная будущая стадия).

**Architecture:** Чистый фронтенд-рефактор `FastAPI/static/app.10.js` (classic script,
без сборки) + `FastAPI/static/app.css`. Все данные уже приходят с бэка через
`api('/cosmetics/')` (см. `services/cosmetics.py::get_catalog()`), новых полей не требуется.
Тестирование — через `node --check` (синтаксис) + puppeteer-скрипты против
`predvestnik_v2/tools/preview_server.mjs` (в проекте нет unit-тестов для фронта, это
установленный паттерн проверки за всю сессию).

**Tech Stack:** Vanilla JS (classic script, ES2017), CSS (custom properties, без
препроцессора), Node.js + puppeteer для верификации (`predvestnik_v2/tools/`).

## Global Constraints

- `FastAPI/static/app.js` (и все `app.0X.js` части) — classic script, НЕ ES-модуль.
  После каждого изменения обязательно `node --check FastAPI/static/app.10.js`.
- `let/const` только вверху функции/скрипта (TDZ!) — не объявлять переменные внутри
  условных блоков, если они используются выше по коду.
- Дублированные функции недопустимы — `app.10.js` склеивается в один файл со всеми
  `app.0X.js`, случайное совпадение имени функции сломает всё приложение молча.
- НЕ трогать `.looks-card.r-{rarity}` правила в `app.css` (строки 1907–1910,
  1935–1937) — используются модалкой сундуков/крафта (`_openSurprisesModal`,
  `_chestReveal`, `_craftCosmetic` в `app.10.js`), которая осознанно осталась на
  старой системе редкости (см. `COSMETICS_COLLECTION_DESIGN_RULES.md` — линейки
  заменили редкость только в основной сетке, не в сундуках).
- НЕ трогать `.lc-sw .lc-ava, .lc-sw .lc-nick, .lc-sw .card-fx, .lc-sw.lc-bg, .lc-sw .lc-title { animation: none !important; }`
  (строка 1925 `app.css`) — намеренная защита от лагов при рендере ~14×6 предметов
  одновременно. Новый акцент цвета линейки — только статичный (border/box-shadow),
  не анимация внутри свотча.
- Тап-зоны — НЕ `min-height`/явный крупный размер на самом видимом элементе
  (раздувает в «кирпичи», см. `COSMETICS_COLLECTION_DESIGN_RULES.md` §4) — увеличивать
  тап-зону невидимым padding на родительской обёртке.
- Цена всегда с явной единицей (`"N✨/предмет"` уже есть в `_looksLineupInfoHtml`),
  статус — честный текст, без намёка на «надето» на уровне множества предметов.
- Перед коммитом каждой задачи — `node --check FastAPI/static/app.10.js` должен
  пройти без ошибок, и puppeteer-скрипт задачи должен пройти.

---

## Файловая карта

- **Modify:** `predvestnik_v2/FastAPI/static/app.10.js` — вся логика фильтрации/рендера сетки «По слотам».
- **Modify:** `predvestnik_v2/FastAPI/static/app.css` — стили умного ряда, мини-измерителя, акцента карточек, пустого состояния.
- **Create:** `predvestnik_v2/tools/verify_slots_smartrow.mjs` — puppeteer-проверка умного ряда (Задача 1).
- **Create:** `predvestnik_v2/tools/verify_slots_meter.mjs` — puppeteer-проверка мини-измерителя (Задача 2).
- **Create:** `predvestnik_v2/tools/verify_slots_accent.mjs` — puppeteer-проверка акцента карточек (Задача 3).

---

### Task 1: Умный ряд (поиск + пилюля линейки + переключатель статуса)

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js:12-13` (состояние), `app.10.js:90-121` (`_looksFilterHtml`/`_looksSetFilter`/`_looksStatusFilterHtml`/`_looksSetStatus`), `app.10.js:201-204` (`_looksGridHtml` фильтр-предикат)
- Modify: `predvestnik_v2/FastAPI/static/app.css:1880-1902` (стили `.looks-filter`/`.looks-chip`/`.looks-filter--status`)
- Create: `predvestnik_v2/tools/verify_slots_smartrow.mjs`

**Interfaces:**
- Consumes: `_looksData.lineups` (объект `{id: {name, ...}}`, уже приходит с бэка), `_looksFilter`/`_looksStatus` (существующие state-переменные, значения не меняются: `'all'|lineupId` и `'all'|'owned'|'missing'`)
- Produces: новая state-переменная `_looksSearch` (string, по умолчанию `''`); функции
  `_looksSetSearch(v)`, `_looksOpenLineupPicker()`, `_looksPickLineup(id)`, `_looksCycleStatus()`
  — последующие задачи их не используют напрямую, но `_looksGridHtml()` (уже
  существующая) теперь фильтрует ещё и по `_looksSearch`.

- [ ] **Step 1: Прочитать текущую реализацию, чтобы не разойтись построчно**

Открыть `predvestnik_v2/FastAPI/static/app.10.js`, найти строки 90–121
(`_looksFilterHtml`, `_looksSetFilter`, `_LOOKS_STATUS_LABEL`,
`_looksStatusFilterHtml`, `_looksSetStatus`) и строки 201–209 (`_looksGridHtml`).
Это заменяемый блок.

- [ ] **Step 2: Написать puppeteer-проверку (будет падать до реализации)**

Создать `predvestnik_v2/tools/verify_slots_smartrow.mjs`:

```js
// Проверка умного ряда «По слотам»: один <input> поиска, одна пилюля выбора
// линейки (не 8 чипов), одна кнопка статуса (не отдельный ряд чипов).
// Запуск: node tools/verify_slots_smartrow.mjs (нужен запущенный preview_server.mjs на :8402)
import puppeteer from 'puppeteer';

const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }

const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700); // skip welcome splash
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 500));

const state = await page.evaluate(() => {
  const searchInput = document.querySelector('#looks-filter-bar input[type="text"]');
  const oldChipRows = document.querySelectorAll('.looks-filter .looks-chip').length;
  const lineupPill = document.getElementById('looks-lineup-pill');
  const statusBtn = document.getElementById('looks-status-btn');
  return {
    hasSearchInput: !!searchInput,
    oldChipCount: oldChipRows,
    hasLineupPill: !!lineupPill,
    hasStatusBtn: !!statusBtn,
  };
});
check('есть текстовое поле поиска', state.hasSearchInput);
check('старых чипов-линеек/статуса больше нет (было 8+3)', state.oldChipCount === 0);
check('есть пилюля выбора линейки', state.hasLineupPill);
check('есть кнопка-переключатель статуса', state.hasStatusBtn);

// Ввод в поиск фильтрует сетку
if (state.hasSearchInput) {
  await page.type('#looks-filter-bar input[type="text"]', 'Лунный');
  await new Promise(r => setTimeout(r, 300));
  const visibleCards = await page.evaluate(() =>
    document.querySelectorAll('#looks-grid-name_glow .looks-card[data-cos]:not([data-cos="__none__"])').length);
  check('поиск "Лунный" сужает сетку ореолов до 1 предмета', visibleCards === 1);
}

// Клик по кнопке статуса циклит all → owned → missing
if (state.hasStatusBtn) {
  const seq = [];
  for (let i = 0; i < 3; i++) {
    await page.click('#looks-status-btn');
    await new Promise(r => setTimeout(r, 150));
    seq.push(await page.evaluate(() => window._looksStatus));
  }
  check('кнопка статуса циклит all→owned→missing→all', JSON.stringify(seq) === JSON.stringify(['owned','missing','all']));
}

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

- [ ] **Step 3: Запустить проверку, убедиться что падает**

```bash
node predvestnik_v2/tools/verify_slots_smartrow.mjs
```

Ожидается: `FAIL: [ 'есть текстовое поле поиска', ... ]` (элементов ещё нет).

- [ ] **Step 4: Заменить блок `_looksFilterHtml`/`_looksSetFilter`/статус в `app.10.js`**

Заменить строки 90–121 (от `function _looksFilterHtml(){` до конца `_looksSetStatus`) на:

```js
let _looksSearch='';   // поиск по названию — общий для всех секций разом, как и остальные фильтры
function _looksFilterHtml(){
  const lin=lineupMeta(_looksFilter);
  const lineupTxt=_looksFilter==='all'?'Все линейки':esc(lin?lin.name:'—');
  const dotHtml=_looksFilter==='all'
    ?`<span class="sr-dot-all"><span style="background:#ff7a3d"></span><span style="background:#7ad4ff"></span><span style="background:#c084fc"></span></span>`
    :`<span class="sr-dot" style="color:${lineupColor(_looksFilter)}"></span>`;
  const statusIcon={all:'∅',owned:'✓',missing:'🔒'}[_looksStatus];
  return `<div class="smartrow">
    <div class="sr-tap sr-tap--flex"><div class="sr-box sr-search">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
      <input type="text" id="looks-search-inp" placeholder="Поиск…" value="${esc(_looksSearch)}" oninput="_looksSetSearch(this.value)">
    </div></div>
    <div class="sr-tap"><div class="sr-box sr-lineup" id="looks-lineup-pill" onclick="_looksOpenLineupPicker()">${dotHtml}${lineupTxt}</div></div>
    <div class="sr-tap"><div class="sr-box sr-status sr-status--${_looksStatus}" id="looks-status-btn" onclick="_looksCycleStatus()">${statusIcon}</div></div>
  </div><div id="looks-lineup-info">${_looksLineupInfoHtml()}</div>`;
}
function _looksSetSearch(v){
  _looksSearch=v;
  _LOOKS_SLOTS.forEach(_looksRenderSectionGrid);
  _looksSyncStickyH();
}
function _looksOpenLineupPicker(){
  const lineups=Object.keys(_looksData.lineups||{});
  const rows=[{id:'all',label:'Все линейки'}, ...lineups.map(id=>({id,label:lineupLabel(id)}))]
    .map(o=>`<div class="picker-opt${o.id===_looksFilter?' on':''}" onclick="_looksPickLineup('${o.id}')">${esc(o.label)}</div>`).join('');
  OM('Линейка', `<div class="picker">${rows}</div>`, [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}
function _looksPickLineup(lin){
  CM();
  _looksFilter=lin;
  // Полная перерисовка умного ряда (пилюля/точка меняются) — дешёвая операция, не вся страница
  const host=el('looks-filter-bar');
  if(host) host.outerHTML=`<div id="looks-filter-bar">${_looksFilterHtml()}</div>`;
  _LOOKS_SLOTS.forEach(_looksRenderSectionGrid);
  _looksSyncStickyH();
}
const _LOOKS_STATUS_CYCLE=['all','owned','missing'];
function _looksCycleStatus(){
  const i=_LOOKS_STATUS_CYCLE.indexOf(_looksStatus);
  _looksStatus=_LOOKS_STATUS_CYCLE[(i+1)%_LOOKS_STATUS_CYCLE.length];
  const btn=el('looks-status-btn');
  if(btn){
    btn.textContent={all:'∅',owned:'✓',missing:'🔒'}[_looksStatus];
    btn.className=`sr-box sr-status sr-status--${_looksStatus}`;
  }
  _LOOKS_SLOTS.forEach(_looksRenderSectionGrid);
  _looksSyncStickyH();
}
```

Обернуть весь блок из `_looksFilterHtml()` в `renderLooks()` (строка 64) идентификатором
`id="looks-filter-bar"` вместо прежнего `.looks-filter` (там сейчас
`<div class="looks-sticky"><div id="looks-top">...</div>${_looksFilterHtml()}</div>` —
заменить на
`<div class="looks-sticky"><div id="looks-top">...</div><div id="looks-filter-bar">${_looksFilterHtml()}</div></div>`).

Обновить фильтр-предикат `_looksGridHtml` (строка 202-204) — добавить поиск:

```js
function _looksGridHtml(slot){
  const q=_looksSearch.trim().toLowerCase();
  const items=(_looksData.slots[slot]||[]).filter(it=>
    (_looksFilter==='all'||it.lineup===_looksFilter) &&
    (_looksStatus==='all'||(_looksStatus==='owned'?it.owned:!it.owned)) &&
    (!q||it.name.toLowerCase().includes(q)));
  const none=`<div class="looks-card ${_looksShownId(slot)==null?'sel':''}" data-cos="__none__" onclick="_looksUnequip('${slot}')">
    <div class="lc-sw lc-sw--none">✖</div><div class="lc-name">Без</div></div>`;
  const empty=items.length?'':`<div class="looks-empty"><div class="looks-empty-ico">🔍</div>Ничего не найдено по этому фильтру</div>`;
  return `<div class="looks-cards">${none}${items.map(it=>_looksCard(slot,it)).join('')}${empty}</div>`;
}
```

Инициализировать `_looksSearch=''` в `openLooksModal()` (строка 32, рядом с
`_looksFilter='all'; _looksStatus='all';`).

- [ ] **Step 5: Добавить CSS умного ряда, заменить старые правила чипов**

В `predvestnik_v2/FastAPI/static/app.css` заменить блок строк 1880–1902
(от комментария `/* Фильтр по линейке ... */` до конца `.looks-filter--status .looks-chip.active`) на:

```css
/* Умный ряд (Стадия 1, 2026-07-29): поиск + пилюля линейки + переключатель
   статуса вместо двух рядов чипов. Тап-зона ≥44px — НЕВИДИМЫМ padding на
   .sr-tap (обёртке), сама пилюля остаётся тонкой ~30px (см. правило в
   COSMETICS_COLLECTION_DESIGN_RULES.md §4 — раздувать саму пилюлю нельзя). */
.smartrow { display: flex; gap: 6px; margin-bottom: 6px; }
.sr-tap { padding: 5px 0; display: flex; flex: none; }
.sr-tap--flex { flex: 1; min-width: 0; }
.sr-box {
  width: 100%; background: linear-gradient(160deg, var(--bg3), var(--bg2));
  border: 1px solid var(--border2); border-radius: 10px;
  box-shadow: inset 0 1px 2px rgba(0,0,0,.35);
  display: flex; align-items: center; gap: 6px; padding: 6px 10px;
  font-family: inherit; cursor: pointer;
}
.sr-search { min-width: 0; cursor: text; }
.sr-search:focus-within { border-color: rgba(139,108,240,.5); box-shadow: inset 0 1px 2px rgba(0,0,0,.35), 0 0 0 2px rgba(139,108,240,.13); }
.sr-search svg { width: 12px; height: 12px; opacity: .65; flex: none; color: var(--muted); }
.sr-search input { background: none; border: none; outline: none; color: var(--bright); font-size: 10px; width: 100%; font-family: inherit; }
.sr-search input::placeholder { color: var(--muted); }
.sr-lineup { white-space: nowrap; max-width: 100px; overflow: hidden; text-overflow: ellipsis; color: var(--bright); font-size: 10px; font-weight: 600; }
.sr-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 4px; box-shadow: 0 0 5px currentColor; flex: none; }
.sr-dot-all { display: inline-flex; flex: none; margin-right: 5px; }
.sr-dot-all span { width: 5.5px; height: 5.5px; border-radius: 50%; margin-left: -2px; border: 1px solid var(--bg2); }
.sr-dot-all span:first-child { margin-left: 0; }
.sr-status { width: 30px; justify-content: center; padding: 6px 0; font-size: 12px; }
.sr-status--owned { background: linear-gradient(160deg, rgba(86,196,106,.16), rgba(86,196,106,.04)); border-color: rgba(86,196,106,.3); }
.sr-status--missing { background: linear-gradient(160deg, rgba(232,181,77,.16), rgba(232,181,77,.04)); border-color: rgba(232,181,77,.3); }
/* Лист выбора линейки (открывается тапом по .sr-lineup через OM()) */
.picker { display: flex; flex-direction: column; gap: 2px; }
.picker-opt { padding: 8px 10px; font-size: 12px; color: var(--text); border-radius: 8px; cursor: pointer; }
.picker-opt:active { background: var(--bg3); }
.picker-opt.on { background: rgba(232,181,77,.1); color: var(--gold2); font-weight: 700; }
```

- [ ] **Step 6: `node --check`**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
```
Ожидается: без вывода (успех).

- [ ] **Step 7: Перезапустить preview_server.mjs и прогнать puppeteer-проверку**

```bash
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_slots_smartrow.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 8: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_slots_smartrow.mjs
git commit -m "redesign(cosmetics): умный ряд фильтра вместо двух рядов чипов (По слотам)"
```

---

### Task 2: Мини-измеритель прогресса на заголовке секции

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js:135-141` (`_looksSectionHtml`)
- Modify: `predvestnik_v2/FastAPI/static/app.css:3360` (`.looks-sec-t`, добавить соседние правила)
- Create: `predvestnik_v2/tools/verify_slots_meter.mjs`

**Interfaces:**
- Consumes: `_looksData.slots[slot]` (массив предметов с полем `owned: bool`)
- Produces: ничего нового наружу — чисто визуальная надстройка `_looksSectionHtml()`

- [ ] **Step 1: Написать puppeteer-проверку**

Создать `predvestnik_v2/tools/verify_slots_meter.mjs`:

```js
// Проверка мини-измерителя на заголовке секции: есть N делений = N предметов слота,
// заполненные (owned) делений столько же, сколько owned=true в данных.
import puppeteer from 'puppeteer';
const FAIL=[];
function check(name,cond){ if(!cond) FAIL.push(name); else console.log('OK:',name); }
const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(r=>setTimeout(r,1500));
await page.mouse.click(195,700);
await new Promise(r=>setTimeout(r,500));
await page.evaluate(()=>openLooksModal());
await new Promise(r=>setTimeout(r,500));
const info=await page.evaluate(()=>{
  const total=(_looksData.slots.name_glow||[]).length;
  const owned=(_looksData.slots.name_glow||[]).filter(it=>it.owned).length;
  const sec=document.getElementById('looks-sec-name_glow');
  const notches=sec?sec.querySelectorAll('.mini-notch').length:0;
  const onNotches=sec?sec.querySelectorAll('.mini-notch.on').length:0;
  const numTxt=sec?(sec.querySelector('.sec-num')||{}).textContent:null;
  return {total,owned,notches,onNotches,numTxt};
});
check('число делений совпадает с числом предметов слота', info.notches===info.total);
check('число горящих делений совпадает с owned', info.onNotches===info.owned);
check('текстовая подпись показывает X/Y', info.numTxt===`${info.owned}/${info.total}`);
await browser.close();
if(FAIL.length){console.error('FAIL:',FAIL);process.exit(1);}
console.log('ALL OK');
```

- [ ] **Step 2: Прогнать, убедиться что падает** (элементов `.mini-notch`/`.sec-num` ещё нет)

```bash
node predvestnik_v2/tools/verify_slots_meter.mjs
```

- [ ] **Step 3: Реализовать в `app.10.js`**

Заменить `_looksSectionHtml` (строки 135–141):

```js
function _looksSectionHtml(slot){
  const items=_looksData.slots[slot]||[];
  const owned=items.filter(it=>it.owned).length, total=items.length;
  // Порядок делений НЕ важен — деления обезличены (просто N одинаковых чёрточек,
  // не привязаны к конкретному предмету), горят ПЕРВЫЕ owned штук слева направо.
  // Это осознанно проще per-item подсветки (которая бы выглядела рандомно
  // раскиданной, т.к. массив не гарантированно owned-first).
  const notches=items.map((_,i)=>`<div class="mini-notch${i<owned?' on':''}"></div>`).join('');
  return `<section class="looks-section" id="looks-sec-${slot}">
    <div class="sec-head">
      <div class="looks-sec-t">${_LOOKS_SLOT_LABEL[slot]}</div>
      <div class="mini-meter">${notches}</div>
      <div class="sec-num">${owned}/${total}</div>
    </div>
    <div class="looks-sec-grid" id="looks-grid-${slot}">${_looksGridHtml(slot)}</div>
  </section>`;
}
```

- [ ] **Step 4: Добавить CSS**

Добавить в `app.css` рядом со строкой 3360 (`.looks-sec-t`):

```css
.sec-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; gap: 10px; }
.sec-head .looks-sec-t { margin-bottom: 0; white-space: nowrap; }
.mini-meter { display: flex; gap: 2px; flex: 1; max-width: 90px; }
.mini-notch { flex: 1; height: 5px; border-radius: 2px; background: var(--dim); }
.mini-notch.on { background: linear-gradient(180deg, var(--gold2), var(--gold)); }
.sec-num { font-size: 8.5px; color: var(--muted); white-space: nowrap; }
```

- [ ] **Step 5: `node --check`, перезапустить preview_server, прогнать проверку**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_slots_meter.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 6: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_slots_meter.mjs
git commit -m "feat(cosmetics): мини-измеритель прогресса на заголовке секции слота"
```

---

### Task 3: Статичный акцент цвета линейки на карточке предмета

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js:224-243` (`_looksCard`)
- Modify: `predvestnik_v2/FastAPI/static/app.css` (новый блок, НЕ трогать 1907-1910/1935-1937)
- Create: `predvestnik_v2/tools/verify_slots_accent.mjs`

**Interfaces:**
- Consumes: `it.lineup` (строка, уже есть на каждом предмете), `lineupColor(id)` (уже существует, строка 28)
- Produces: класс `.lc-lineup-accent` на `.looks-card`, инлайн `style="--lc:...;--lcg:...;"`

- [ ] **Step 1: Написать puppeteer-проверку**

Создать `predvestnik_v2/tools/verify_slots_accent.mjs`:

```js
// Карточка предмета в сетке «По слотам» должна иметь класс lc-lineup-accent
// и инлайн-переменную --lc, совпадающую с цветом её линейки, БЕЗ удаления
// r-{rarity} класса (нужен модалке сундуков/крафта).
import puppeteer from 'puppeteer';
const FAIL=[];
function check(name,cond){ if(!cond) FAIL.push(name); else console.log('OK:',name); }
const browser=await puppeteer.launch({headless:'new'});
const page=await browser.newPage();
await page.setViewport({width:390,height:844,deviceScaleFactor:2});
await page.goto('http://localhost:8402/',{waitUntil:'load'});
await new Promise(r=>setTimeout(r,1500));
await page.mouse.click(195,700);
await new Promise(r=>setTimeout(r,500));
await page.evaluate(()=>openLooksModal());
await new Promise(r=>setTimeout(r,500));
const info=await page.evaluate(()=>{
  const card=document.querySelector('#looks-grid-name_glow .looks-card[data-cos]:not([data-cos="__none__"])');
  if(!card) return null;
  const cosId=card.getAttribute('data-cos');
  const it=_looksData.slots.name_glow.find(x=>x.id===cosId);
  return {
    hasAccentClass: card.classList.contains('lc-lineup-accent'),
    hasRarityClass: [...card.classList].some(c=>c.startsWith('r-')),
    styleAttr: card.getAttribute('style')||'',
    expectedColor: lineupColor(it.lineup),
  };
});
check('карточка нашлась', !!info);
if(info){
  check('есть класс lc-lineup-accent', info.hasAccentClass);
  check('класс r-{rarity} НЕ удалён (нужен сундукам/крафту)', info.hasRarityClass);
  check('инлайн-стиль содержит цвет линейки', info.styleAttr.includes(info.expectedColor));
}
await browser.close();
if(FAIL.length){console.error('FAIL:',FAIL);process.exit(1);}
console.log('ALL OK');
```

- [ ] **Step 2: Прогнать, убедиться что падает**

```bash
node predvestnik_v2/tools/verify_slots_accent.mjs
```

- [ ] **Step 3: Реализовать в `_looksCard` (`app.10.js:224-243`)**

Заменить целиком:

```js
function _looksCard(slot,it){
  const sel=_looksShownId(slot)===it.id;
  const sw=_looksSwatch(slot,it);
  const rar=`<span class="lc-rar" style="color:${lineupColor(it.lineup)}">${esc(lineupLabel(it.lineup))}</span>`;
  // Статичный акцент цвета линейки (не анимация — .lc-sw уже намеренно без
  // анимации из-за перф, см. app.css:1925). r-{rarity} класс НЕ убираю —
  // им пользуется модалка сундуков/крафта (осталась на старой системе).
  const accentStyle=`style="--lc:${lineupColor(it.lineup)};--lcg:${lineupColor(it.lineup)}22"`;
  if(it.owned){
    const offBadge=it.vip_locked_inactive?'<span class="lc-vip-off">⏸ нужна VIP</span>':'';
    return `<div class="looks-card lc-lineup-accent r-${it.rarity} ${sel?'sel':''} ${it.vip_locked_inactive?'lc-dim':''}" ${accentStyle} data-cos="${it.id}" onclick="_looksEquip('${slot}','${it.id}')">
      ${sw}<div class="lc-name">${esc(it.name)}</div>
      <div class="lc-foot">${rar}${offBadge}${(!it.vip_locked_inactive&&_looksSaved[slot]===it.id)?'<span class="lc-on">✓ надето</span>':''}</div></div>`;
  }
  const vip=it.vip_required?'<span class="lc-vip">VIP</span>':'';
  const priceTxt=it.price&&it.price.length?`<span class="lc-price-hint">${_looksPriceTxt(it.price[0])} ✨</span>`:'';
  return `<div class="looks-card lc-lineup-accent r-${it.rarity} locked lc-buyable ${sel?'sel':''}" ${accentStyle} data-cos="${it.id}" onclick="_looksTapUnowned('${slot}','${it.id}')">
    ${sw}<div class="lc-name">🔒 ${esc(it.name)} ${vip}</div>
    <div class="lc-foot">${rar}${priceTxt}<span class="lc-prev-hint">👁</span></div></div>`;
}
```

- [ ] **Step 4: Добавить CSS акцента**

Добавить в `app.css` сразу ПОСЛЕ строки 1911 (`.looks-card.lc-dim { opacity: .42; }`),
не заменяя ничего из существующего r-{rarity} блока:

```css
/* Статичный акцент цвета линейки (Стадия 1, 2026-07-29) — override поверх
   r-{rarity} рамки ТОЛЬКО когда есть класс lc-lineup-accent (сундуки/крафт
   этот класс не получают, у них остаётся старая r-{rarity} окраска нетронутой). */
.looks-card.lc-lineup-accent { border-color: var(--lc, var(--border2)); position: relative; overflow: hidden; }
.looks-card.lc-lineup-accent::before { content: ''; position: absolute; inset: 0; background: radial-gradient(circle at 90% 0%, var(--lcg, transparent), transparent 60%); pointer-events: none; }
.looks-card.lc-lineup-accent.sel { border-color: var(--gold); }
```

- [ ] **Step 5: `node --check`, перезапустить preview_server, прогнать проверку**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_slots_accent.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 6: Ручная проверка, что сундуки/крафт НЕ затронуты**

```bash
node -e "
const puppeteer=require('puppeteer');
(async()=>{
  const b=await puppeteer.launch({headless:'new'});
  const p=await b.newPage();
  await p.setViewport({width:390,height:844});
  await p.goto('http://localhost:8402/',{waitUntil:'load'});
  await new Promise(r=>setTimeout(r,1500));
  await p.mouse.click(195,700);
  await new Promise(r=>setTimeout(r,500));
  await p.evaluate(()=>openLooksModal());
  await new Promise(r=>setTimeout(r,500));
  await p.evaluate(()=>_openSurprisesModal());
  await new Promise(r=>setTimeout(r,800));
  const hasAccent=await p.evaluate(()=>!!document.querySelector('#mb .looks-card.lc-lineup-accent'));
  console.log('сундуки/крафт содержат lc-lineup-accent (должно быть false):', hasAccent);
  await b.close();
})();
"
```
Ожидается: `false`.

- [ ] **Step 7: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_slots_accent.mjs
git commit -m "feat(cosmetics): статичный акцент цвета линейки на карточках предметов (По слотам)"
```

---

### Task 4: Пустое состояние фильтра — визуальное обновление

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.css:1877` (`.looks-empty`)

**Interfaces:**
- Consumes: разметку `<div class="looks-empty"><div class="looks-empty-ico">🔍</div>Ничего не найдено по этому фильтру</div>`, уже добавленную в Task 1 Step 4 (`_looksGridHtml`)
- Produces: ничего наружу, чисто CSS

- [ ] **Step 1: Заменить `.looks-empty` в `app.css:1877`**

```css
.looks-empty { grid-column: 1 / -1; text-align: center; color: var(--muted); font-size: 10px; padding: 18px 12px; border: 1px dashed var(--border2); border-radius: 12px; background: rgba(255,255,255,.015); }
.looks-empty-ico { font-size: 20px; opacity: .4; margin-bottom: 6px; }
```

- [ ] **Step 2: Визуальная проверка puppeteer (используя уже написанный поиск из Task 1)**

```bash
node -e "
const puppeteer=require('puppeteer');
(async()=>{
  const b=await puppeteer.launch({headless:'new'});
  const p=await b.newPage();
  await p.setViewport({width:390,height:844});
  await p.goto('http://localhost:8402/',{waitUntil:'load'});
  await new Promise(r=>setTimeout(r,1500));
  await p.mouse.click(195,700);
  await new Promise(r=>setTimeout(r,500));
  await p.evaluate(()=>openLooksModal());
  await new Promise(r=>setTimeout(r,500));
  await p.type('#looks-search-inp','этогонесуществует12345');
  await new Promise(r=>setTimeout(r,300));
  const empty=await p.evaluate(()=>{
    const e=document.querySelector('#looks-grid-name_glow .looks-empty');
    return e?{text:e.textContent.trim(),hasIco:!!e.querySelector('.looks-empty-ico')}:null;
  });
  console.log(JSON.stringify(empty));
  await b.close();
})();
"
```
Ожидается: `{"text":"🔍Ничего не найдено по этому фильтру","hasIco":true}`.

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.css
git commit -m "style(cosmetics): пустое состояние фильтра — пунктирная рамка вместо голого текста"
```

---

## Финальная проверка стадии (перед деплоем)

- [ ] **Прогнать все 3 puppeteer-скрипта подряд**

```bash
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_slots_smartrow.mjs
node predvestnik_v2/tools/verify_slots_meter.mjs
node predvestnik_v2/tools/verify_slots_accent.mjs
```
Все три — `ALL OK`.

- [ ] **`node --check` на весь файл ещё раз**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
```

- [ ] **Убедиться, что старые функции `_looksSetFilter`/`_looksStatusFilterHtml` больше нигде не вызываются (были заменены, не должны остаться мёртвым кодом)**

```bash
grep -n "_looksSetFilter\|_looksStatusFilterHtml\|_LOOKS_STATUS_LABEL" predvestnik_v2/FastAPI/static/app.10.js
```
Ожидается: пусто (все три имени удалены вместе с заменённым блоком в Task 1).

- [ ] **Ручной смоук на реальном телефоне через ngrok/тестовый бот** (не автоматизируется —
  тач-скролл ряда фильтров, реальная клавиатура при вводе в поиск, реальные тап-зоны
  пальцем, не курсором мыши).

- [ ] **Деплой на DigitalOcean** (git push уже сделан по коммитам выше — нужен рестарт
  процесса, статика читается в память при старте, см. проектную память
  `project_prod_stale_static`).

## Что НЕ входит в эту стадию (следующие планы)

- Переключатель режимов «По коллекциям»/«По слотам» и сам режим «По коллекциям»
  (карточки-линейки, SVG-сигили, детальный экран) — отдельный план, добавляется
  ВМЕСТЕ со вторым режимом (иначе тап по несуществующему режиму сломает UX).
- «Сейчас→Станет» с публичной карточкой, «Образы» (пресеты+сеты), 6 QoL-фич,
  экран-праздник, «Вход»/«Темы» — каждое отдельным планом при переходе к нему.
- `prefers-reduced-motion` для новых анимаций — из этой стадии анимаций не
  добавляется вовсе (только статичные акценты), актуально начиная со стадии
  «По коллекциям» (SVG-сигили).
