# «По коллекциям» + переключатель режимов (Стадия 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить переключатель режимов «По коллекциям» / «По слотам» во вкладку «Внешний вид» и реализовать сам режим «По коллекциям» — 7 карточек-линеек с авторскими анимированными SVG-медальонами, кольцом-прогрессом и полоской слот-иконок. Тап по карточке переключает в уже существующий (Стадия 1) режим «По слотам», отфильтрованный на эту линейку — без новой покупки/бэкенда в этой стадии.

**Architecture:** Чистый фронтенд-рефактор `FastAPI/static/app.10.js` (classic script) + `FastAPI/static/app.css`. Все данные уже приходят с бэка через `api('/cosmetics/')` (`_looksData.slots[slot][].lineup`/`.owned`, `_looksData.lineups[id]`) — статистика по коллекциям (сколько собрано, какие слоты) считается на клиенте, бэкенд не меняется. Детальный экран открытой коллекции (сегментный измеритель, кнопка «Купить всё недостающее» — реальная транзакция) **сознательно НЕ входит в эту стадию** — это Стадия 3, отдельный план: там появляется массовая покупка (риск для экономики), а эта стадия — чистая навигация/визуал.

**Tech Stack:** Vanilla JS (classic script), CSS (custom properties, `conic-gradient` для кольца-прогресса, inline SVG для медальонов-сигилей), Node.js + puppeteer против `predvestnik_v2/tools/preview_server.mjs` (в проекте нет unit-тестов для фронта — установленный паттерн проверки, см. Стадию 1).

## Global Constraints

- `FastAPI/static/app.js` (и все `app.0X.js` части) — classic script, НЕ ES-модуль. После каждого изменения — `node --check FastAPI/static/app.10.js`.
- `let/const` только вверху функции/скрипта (TDZ) — не объявлять переменные внутри условных блоков, если используются выше.
- Дублированные функции/классы недопустимы — `app.10.js` склеивается со всеми `app.0X.js` в один файл.
- **Новые CSS-классы карточки коллекции ОБЯЗАНЫ использовать префикс `.coll-`, НЕ `.lc-`.** Классы `.lc-name`, `.lc-sw`, `.lc-foot`, `.lc-rar`, `.lc-price-hint`, `.lc-vip`, `.lc-on`, `.lc-tag`, `.lc-dim`, `.lc-ava`, `.lc-nick`, `.lc-title`, `.lc-bg` уже заняты и активно используются компонентом карточки ОТДЕЛЬНОГО ПРЕДМЕТА (`_looksCard`/`_looksSwatch` в этом же файле, режим «По слотам», Стадия 1) — использование `.lc-*` для карточки КОЛЛЕКЦИИ создаст путаницу стилей между двумя разными компонентами карточек на одной странице.
- Иконки-сигили — правила оформления и уже готовый код всех 7 линеек взяты из `predvestnik_v2/COSMETICS_COLLECTION_DESIGN_RULES.md` и мокапа брейншторма (`(project root)/.superpowers/brainstorm/1020-1785343726/content/icon-set-v3.html` + `progress-restore.html` для кольца) — это транскрипция уже утверждённого дизайна. Полный код каждой иконки — в самих задачах ниже, ничего не изобретать заново.
- Правило текста статуса (см. DESIGN_RULES.md §5): **"✓ собрано"** (все предметы куплены) / **"N не куплено"** (частично) / **"не начато"** (0 куплено) — НИКОГДА "✓ надето" на уровне коллекции.
- Цена — всегда с единицей: `"N✨/предмет"`.
- Золото (`var(--gold)`/`#e8b54d`) — только на статусе "не куплено" (сигнал действия), НЕ как заливка цвета линейки. Собранная линейка — зелёный `#56c46a`, не начатая — серый `#7c84a0`.
- `body.no-fx` — уже существующий, повсеместно используемый в проекте класс для отключения анимаций (см. `app.css` многочисленные `body.no-fx .xxx { animation: none; }` правила). Новые keyframe-анимации иконок ОБЯЗАНЫ получить свой `body.no-fx` оверрайд — открытый пункт из DESIGN_RULES.md §8, закрывается в этой стадии.
- Персистентность выбранного режима — через `localStorage`, с префиксом ключей `pv_` (см. существующий `pv_no_fx`/`pv_last_level` в `app.01.js`) и обязательным `try/catch` вокруг обращений к `localStorage` (см. `app.01.js:11`) — Telegram WebView иногда блокирует localStorage, страница не должна падать.
- Работаем прямо в `master` (владелец подтвердил в Стадии 1 — `tab_cosmetics` отключён для игроков, риска для прода нет).

---

## Файловая карта

- **Modify:** `predvestnik_v2/FastAPI/static/app.10.js` — состояние режима, вычисление статистики коллекций, рендер карточек коллекций, переключатель.
- **Modify:** `predvestnik_v2/FastAPI/static/app.css` — стили переключателя, карточки коллекции, 7 иконок-сигилей, кольца-прогресса, `no-fx`.
- **Create:** `predvestnik_v2/tools/verify_collections_toggle.mjs` (Task 1)
- **Create:** `predvestnik_v2/tools/verify_collections_cards.mjs` (Task 2)
- **Create:** `predvestnik_v2/tools/verify_collections_navigation.mjs` (Task 3)
- **Create:** `predvestnik_v2/tools/verify_collections_nofx.mjs` (Task 4)

---

### Task 1: Переключатель режимов — инфраструктура

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js:31-40` (`openLooksModal`), `app.10.js:54-74` (`renderLooks`)
- Modify: `predvestnik_v2/FastAPI/static/app.css` (новый блок, добавить после строки 1888, `.smartrow` начало — см. Task 1 Step 5)
- Create: `predvestnik_v2/tools/verify_collections_toggle.mjs`

**Interfaces:**
- Consumes: ничего нового от других задач (это первая задача стадии).
- Produces: `_looksMode` (string, `'collections'|'slots'`, module-level `let`), `_looksSlotsViewHtml()` (function, returns HTML string — экстрагирована из текущего `renderLooks()`, поведение не меняется), `_looksCollectionsViewHtml()` (function, returns HTML string — в этой задаче временная заглушка с текстом-плейсхолдером САМ факт существования функции — реальное содержимое пишет Task 2, который эту функцию заменит), `_looksSetMode(mode)` (function, переключает режим+перерисовывает+сохраняет в localStorage), `_looksModeToggleHtml()` (function, returns HTML string для самого переключателя).

- [ ] **Step 1: Прочитать текущий `renderLooks()` перед изменением**

Открыть `predvestnik_v2/FastAPI/static/app.10.js`, найти `openLooksModal()` (строка 31) и `renderLooks()` (строка 54). Текущее содержимое `renderLooks()`:

```js
function renderLooks(){
  const b=el('pg-looks'); if(!b||!_looksData) return;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Купить можно любую косметику. Линейки дороже «Лесного Странника» <b>отображаются на профиле только с VIP</b>.</span>
    <button class="btn btn-sm btn-gold" onclick="goTo('market','vip')">Перейти к VIP</button></div>`;
  b.innerHTML=`
    <div class="looks-head">
      <button class="looks-back" onclick="_looksClose()" aria-label="Назад">‹</button>
      <div class="looks-htitle">🎨 Внешний вид</div>
    </div>
    <div class="looks-sticky"><div id="looks-top">${_looksPreviewHtml()}</div><div id="looks-filter-bar">${_looksFilterHtml()}</div></div>`
    +vipBar
    +'<button class="btn btn-ghost btn-full" style="margin:2px 0 10px" onclick="_openSurprisesModal()">🎁 Сюрпризы и 🔹 Крафт косметики</button>'
    +_looksPresetsHtml()
    +`<div class="looks-anchors">${_LOOKS_SECTIONS.map(s=>`<button class="looks-anchor-chip" onclick="_looksJump('${s}')">${_LOOKS_ANCHOR_LABEL[s]}</button>`).join('')}</div>`
    +`<div id="looks-sections">${_LOOKS_SLOTS.map(_looksSectionHtml).join('')}${_looksWelcomeSectionHtml()}${_looksThemesSectionHtml()}</div>`
    +`<div class="pay-terms">Покупая косметику, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`;
  _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
  _looksThemesEnsureLoaded();
  _looksSyncStickyH();
}
```

Ключевая мысль: часть `<div id="looks-filter-bar">...` + `<div class="looks-anchors">...` + `<div id="looks-sections">...` — это ТОЛЬКО режим «По слотам». VIP-бар, кнопка «Сюрпризы», пресеты, секции «Вход»/«Темы», пометка про соглашение — ОБЩИЕ для обоих режимов, не дублируются (по спеку). Переключатель режима вставляется МЕЖДУ sticky-превью и VIP-баром.

- [ ] **Step 2: Написать puppeteer-проверку (упадёт до реализации)**

Создать `predvestnik_v2/tools/verify_collections_toggle.mjs`:

```js
// Проверка переключателя режимов: виден, две кнопки, клик переключает контент
// и сохраняется в localStorage. Запуск: node tools/verify_collections_toggle.mjs
// (нужен запущенный preview_server.mjs на :8402)
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

const initial = await page.evaluate(() => ({
  hasToggle: !!document.getElementById('looks-mode-toggle'),
  hasCollectionsBtn: !!document.querySelector('[data-mode="collections"]'),
  hasSlotsBtn: !!document.querySelector('[data-mode="slots"]'),
  mode: typeof _looksMode !== 'undefined' ? _looksMode : null,
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
}));
check('переключатель существует', initial.hasToggle);
check('есть кнопка "По коллекциям"', initial.hasCollectionsBtn);
check('есть кнопка "По слотам"', initial.hasSlotsBtn);
check('режим по умолчанию — collections', initial.mode === 'collections');
check('в режиме collections НЕТ умного ряда "По слотам" на экране', !initial.hasFilterBar);

// Клик на "По слотам" переключает контент
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const afterSlotsClick = await page.evaluate(() => ({
  mode: _looksMode,
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
  savedMode: (() => { try { return localStorage.getItem('pv_looks_mode'); } catch(e){ return 'ERR'; } })(),
}));
check('клик "По слотам" переключает _looksMode', afterSlotsClick.mode === 'slots');
check('в режиме slots умный ряд появляется', afterSlotsClick.hasFilterBar);
check('режим сохранён в localStorage', afterSlotsClick.savedMode === 'slots');

// Закрыть и снова открыть — режим должен восстановиться из localStorage
await page.evaluate(() => { _looksData = null; });
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 500));
const afterReopen = await page.evaluate(() => _looksMode);
check('режим восстановлен из localStorage при повторном открытии', afterReopen === 'slots');

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

- [ ] **Step 3: Запустить проверку, убедиться что падает**

```bash
node predvestnik_v2/tools/verify_collections_toggle.mjs
```
Ожидается: `FAIL: [ 'переключатель существует', ... ]`.

- [ ] **Step 4: Реализовать в `app.10.js`**

Добавить состояние (рядом со строкой 13, `let _looksStatus='all';`):

```js
let _looksMode='collections';          // режим отображения: collections|slots — по умолчанию коллекции (Стадия 2)
```

Заменить `openLooksModal()` (строки 31-40) — добавить восстановление режима из localStorage при первом открытии:

```js
function openLooksModal(){
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksFocus=null;
  if(!_looksData){   // режим восстанавливаем только на «холодном» открытии — не сбрасывать выбор пользователя, если он уже листает вкладку
    try{ const saved=localStorage.getItem('pv_looks_mode'); if(saved==='collections'||saved==='slots') _looksMode=saved; }catch(e){}
  }
  switchPage('looks');
  if(_looksData){ renderLooks(); return; }        // из кэша — БЕЗ пере-запроса (убирает лаги навигации)
  _looksDirty=false;
  const b=el('pg-looks'); if(b) b.innerHTML='<div class="loader" style="margin-top:44px">Загрузка…</div>';
  Promise.all([api('/cosmetics/'),api('/cosmetics/presets')])
    .then(([d,pr])=>{_looksData=d;_looksSaved=_looksEquipped(d);_looksSel={..._looksSaved};_looksPresets=pr.presets||[];renderLooks();})
    .catch(e=>{const bb=el('pg-looks'); if(bb)bb.innerHTML=`<div class="err" style="margin:16px">${e}</div>`;});
}
```

Добавить переключатель + функцию режима переключения (новый код, разместить сразу ПОСЛЕ `openLooksModal`, перед `_looksClose`):

```js
const _LOOKS_MODE_LABEL={collections:'🗂 По коллекциям',slots:'📚 По слотам'};
function _looksModeToggleHtml(){
  return `<div class="mode-toggle" id="looks-mode-toggle">
    ${Object.keys(_LOOKS_MODE_LABEL).map(m=>`<button class="mode-toggle-btn${m===_looksMode?' on':''}" data-mode="${m}" type="button" onclick="_looksSetMode('${m}')">${_LOOKS_MODE_LABEL[m]}</button>`).join('')}
  </div>`;
}
function _looksSetMode(mode){
  if(mode===_looksMode) return;
  _looksMode=mode;
  try{ localStorage.setItem('pv_looks_mode', mode); }catch(e){}
  renderLooks();
}
```

Заменить `renderLooks()` (строки 54-74) целиком:

```js
function renderLooks(){
  const b=el('pg-looks'); if(!b||!_looksData) return;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Купить можно любую косметику. Линейки дороже «Лесного Странника» <b>отображаются на профиле только с VIP</b>.</span>
    <button class="btn btn-sm btn-gold" onclick="goTo('market','vip')">Перейти к VIP</button></div>`;
  const modeBody=_looksMode==='collections'?_looksCollectionsViewHtml():_looksSlotsViewHtml();
  // «Вход»/«Темы» — ОБЩИЕ для обоих режимов (по спеку), рендерятся здесь ОДИН раз,
  // а не внутри modeBody — иначе в режиме «По коллекциям» пропал бы доступ к смене
  // приветствия/темы.
  b.innerHTML=`
    <div class="looks-head">
      <button class="looks-back" onclick="_looksClose()" aria-label="Назад">‹</button>
      <div class="looks-htitle">🎨 Внешний вид</div>
    </div>
    <div class="looks-sticky"><div id="looks-top">${_looksPreviewHtml()}</div></div>
    ${_looksModeToggleHtml()}`
    +vipBar
    +'<button class="btn btn-ghost btn-full" style="margin:2px 0 10px" onclick="_openSurprisesModal()">🎁 Сюрпризы и 🔹 Крафт косметики</button>'
    +_looksPresetsHtml()
    +`<div id="looks-mode-body">${modeBody}</div>`
    +`<div id="looks-common-sections">${_looksWelcomeSectionHtml()}${_looksThemesSectionHtml()}</div>`
    +`<div class="pay-terms">Покупая косметику, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`;
  _playWelcomePreview(_looksData.welcome&&_looksData.welcome.current);
  _looksThemesEnsureLoaded();
  _looksSyncStickyH();
}
// Режим «По слотам» — извлечено из прежнего renderLooks() без изменений поведения
// (Стадия 1). Умный ряд, чипы-якоря, 6 секций-слотов. «Вход»/«Темы» сюда НЕ входят —
// они общие, рендерятся отдельно в renderLooks() (см. выше).
function _looksSlotsViewHtml(){
  return `<div id="looks-filter-bar">${_looksFilterHtml()}</div>`
    +`<div class="looks-anchors">${_LOOKS_SLOTS.map(s=>`<button class="looks-anchor-chip" onclick="_looksJump('${s}')">${_LOOKS_ANCHOR_LABEL[s]}</button>`).join('')}</div>`
    +`<div id="looks-sections">${_LOOKS_SLOTS.map(_looksSectionHtml).join('')}</div>`;
}
// Режим «По коллекциям» — заглушка, реальное содержимое (карточки линеек) пишет
// Task 2. Не убирать эту функцию при написании Task 2 — ЗАМЕНИТЬ её тело.
function _looksCollectionsViewHtml(){
  return `<div style="padding:20px;text-align:center;color:var(--muted);font-size:12px">Карточки коллекций — Task 2</div>`;
}
```

**Важное изменение относительно исходного кода Стадии 1:** якорь-чипы (`.looks-anchors`) теперь ведут ТОЛЬКО на 6 слотов (`_LOOKS_SLOTS`), не на `_LOOKS_SECTIONS` (которая включала `'welcome'`/`'themes'`) — потому что «Вход»/«Темы» больше не находятся физически внутри `#looks-sections`, идут отдельным блоком `#looks-common-sections` после него. Переход по старым якорям `_looksJump('welcome')`/`_looksJump('themes')` по-прежнему технически работает (ищет элемент по `id`, а не по позиции в DOM — `_looksSec-welcome`/`_looksSec-themes` существуют в `#looks-common-sections`), но кнопок-якорей на них теперь нет в ряду — это сознательное упрощение ряда якорей (он относился к структуре «По слотам», а не к общим секциям). Если нужно оставить быстрый переход к «Входу»/«Темам» и из режима «По слотам» — это отдельное решение для Стадии 3, не блокирует эту стадию.

- [ ] **Step 5: Добавить CSS переключателя**

Добавить в `app.css` СРАЗУ ПЕРЕД строкой 1888 (`.smartrow { display: flex; ... }`):

```css
/* Переключатель режимов (Стадия 2, 2026-07-30) — активная сторона светится
   золотом (награда за выбор, не плоская заливка — правило DESIGN.md), та же
   визуальная логика, что уже одобрена для режима «По слотам». */
.mode-toggle { display: flex; gap: 4px; background: var(--bg1); border: 1px solid var(--border2); border-radius: 14px; padding: 3px; margin: 10px 0; }
.mode-toggle-btn { flex: 1; text-align: center; padding: 8px 6px; border-radius: 11px; font-size: 10.5px; font-weight: 700; font-family: inherit; border: none; background: none; color: var(--muted); cursor: pointer; }
.mode-toggle-btn.on { background: linear-gradient(160deg, var(--gold2), var(--gold)); color: #1a1405; box-shadow: 0 3px 10px rgba(232,181,77,.35), inset 0 1px 0 rgba(255,255,255,.3); }
```

`--bg1: #0e1019;` уже объявлена в блоке `:root` (`app.css:12`) — использовать как есть, без дополнительных проверок.

- [ ] **Step 6: `node --check`**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
```

- [ ] **Step 7: Перезапустить preview_server.mjs и прогнать проверку**

```bash
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_collections_toggle.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 8: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_collections_toggle.mjs
git commit -m "feat(cosmetics): переключатель режимов «По коллекциям»/«По слотам»"
```

---

### Task 2: Карточка коллекции — статистика + гарнитура из 7 иконок

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js` (заменить `_looksCollectionsViewHtml()` из Task 1, добавить новые функции)
- Modify: `predvestnik_v2/FastAPI/static/app.css` (большой новый блок)
- Create: `predvestnik_v2/tools/verify_collections_cards.mjs`

**Interfaces:**
- Consumes: `_looksData.slots[slot][]` (массив предметов, поля `.lineup`, `.owned`), `_looksData.lineups[id]` (`{name, price, vip_required, blurb}`), `_LOOKS_SLOTS` (массив id слотов), `LINEUP_COLOR` (уже существует, строка 22-25), `lineupLabel(id)` (уже существует).
- Produces: `_looksLineupStats(lineupId)` → `{owned:number, total:number, slotOwned:{[slot]:boolean}}`, `_looksCollectionIconSvg(lineupId)` → HTML string (медальон+SVG), `_looksCollectionCard(lineupId)` → HTML string (полная карточка), `_looksCollectionsViewHtml()` (ЗАМЕНЯЕТ заглушку из Task 1).

- [ ] **Step 1: Написать puppeteer-проверку (упадёт до реализации)**

Создать `predvestnik_v2/tools/verify_collections_cards.mjs`:

```js
// Проверка карточек коллекций: 7 штук, у каждой медальон+SVG, кольцо-прогресс
// соответствует реальному owned/total, полоска слотов совпадает с фактическим
// владением, статус-текст честный (собрано/не куплено/не начато).
import puppeteer from 'puppeteer';

const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }

const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700);
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 800));

const info = await page.evaluate(() => {
  const cards = document.querySelectorAll('.coll-card');
  const lineupIds = Object.keys(_looksData.lineups || {});
  const results = [];
  cards.forEach(card => {
    const lin = card.getAttribute('data-lineup');
    const svg = card.querySelector('.sig-svg');
    const ring = card.querySelector('.ring');
    const slots = card.querySelectorAll('.coll-slot');
    const statusEl = card.querySelector('.coll-status');
    results.push({
      lin, hasSvg: !!svg, hasRing: !!ring,
      slotCount: slots.length,
      statusText: statusEl ? statusEl.textContent.trim() : null,
    });
  });
  return { cardCount: cards.length, lineupCount: lineupIds.length, results, lineupIds };
});

check('ровно 7 карточек коллекций (по числу линеек)', info.cardCount === info.lineupCount && info.cardCount === 7);
check('каждая карточка имеет data-lineup из реального набора линеек', info.results.every(r => info.lineupIds.includes(r.lin)));
check('у каждой карточки есть SVG-медальон', info.results.every(r => r.hasSvg));
check('у каждой карточки есть кольцо-прогресс', info.results.every(r => r.hasRing));
check('у каждой карточки ровно 6 слот-иконок (по числу слотов игры)', info.results.every(r => r.slotCount === 6));
check('у каждой карточки есть текст статуса', info.results.every(r => !!r.statusText));

// Честность статус-текста: сверяем с реальными данными по каждой линейке
const statsCheck = await page.evaluate(() => {
  const mismatches = [];
  Object.keys(_looksData.lineups).forEach(lin => {
    let owned = 0, total = 0;
    _LOOKS_SLOTS.forEach(slot => {
      (_looksData.slots[slot] || []).forEach(it => {
        if (it.lineup === lin) { total++; if (it.owned) owned++; }
      });
    });
    const card = document.querySelector(`.coll-card[data-lineup="${lin}"] .coll-status`);
    const text = card ? card.textContent.trim() : null;
    let expected;
    if (owned === total) expected = '✓ собрано';
    else if (owned === 0) expected = 'не начато';
    else expected = `${total - owned} не куплено`;
    if (text !== expected) mismatches.push({ lin, owned, total, text, expected });
  });
  return mismatches;
});
check('статус-текст на каждой карточке точно совпадает с реальным owned/total', statsCheck.length === 0);
if (statsCheck.length) console.log('mismatches:', JSON.stringify(statsCheck));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

- [ ] **Step 2: Запустить проверку, убедиться что падает**

```bash
node predvestnik_v2/tools/verify_collections_cards.mjs
```

- [ ] **Step 3: Реализовать `_looksLineupStats` и заменить `_looksCollectionsViewHtml()`**

В `app.10.js`, найти заглушку `_looksCollectionsViewHtml()` (добавленную в Task 1) и заменить её плюс добавить новые функции ПЕРЕД ней:

```js
// Статистика коллекции: считается на клиенте из уже загруженных _looksData.slots
// (никакого нового запроса к бэку не нужно — lineup/owned уже есть на каждом предмете).
function _looksLineupStats(lin){
  let owned=0, total=0; const slotOwned={};
  _LOOKS_SLOTS.forEach(slot=>{
    const items=(_looksData.slots[slot]||[]).filter(it=>it.lineup===lin);
    total+=items.length;
    const hasOwned=items.some(it=>it.owned);
    if(hasOwned) owned+=items.filter(it=>it.owned).length;
    slotOwned[slot]=hasOwned;
  });
  return {owned,total,slotOwned};
}
function _looksCollectionStatusHtml(stats){
  if(stats.total===0) return `<div class="coll-status" style="color:var(--muted);background:rgba(255,255,255,.05)">не начато</div>`;
  if(stats.owned===stats.total) return `<div class="coll-status" style="color:#56c46a;background:rgba(86,196,106,.13)">✓ собрано</div>`;
  if(stats.owned===0) return `<div class="coll-status" style="color:var(--muted);background:rgba(255,255,255,.05)">не начато</div>`;
  return `<div class="coll-status" style="color:var(--gold2);background:rgba(232,181,77,.13)">${stats.total-stats.owned} не куплено</div>`;
}
const _LOOKS_SLOT_ICON={name_glow:'✨',avatar_frame:'🖼',avatar_halo:'🌟',title:'🏷',profile_bg:'🖌',card_fx:'❄️'};
function _looksCollectionCard(lin){
  const meta=lineupMeta(lin); if(!meta) return '';
  const stats=_looksLineupStats(lin);
  const pct=stats.total?Math.round(stats.owned/stats.total*100):0;
  const c=LINEUP_COLOR[lin]||'#9aa7b8';
  const price=(meta.price&&meta.price[0]&&meta.price[0].zarniki)?`${meta.price[0].zarniki}✨/предмет`:'—';
  const slotsHtml=_LOOKS_SLOTS.map(slot=>`<span class="coll-slot${stats.slotOwned[slot]?' on':''}">${_LOOKS_SLOT_ICON[slot]}</span>`).join('');
  return `<div class="coll-card" style="--c:${c};--cb:${c}4d;--cg:${c}1f" data-lineup="${lin}" onclick="_looksOpenCollection('${lin}')">
    <div class="coll-inner"><div class="coll-frame"></div>
      <div class="coll-top">
        <div class="sig-med" style="--c:${c}">
          <div class="ring" style="background:conic-gradient(${c} calc(${pct}%),rgba(255,255,255,.08) 0)"><div class="ring-mask"></div></div>
          ${_looksCollectionIconSvg(lin)}
        </div>
        <div><div class="coll-name">${esc(meta.name)}</div>${_looksCollectionStatusHtml(stats)}<div class="coll-price">${price}</div></div>
      </div>
      <div class="coll-slots">${slotsHtml}</div>
    </div>
  </div>`;
}
function _looksCollectionsViewHtml(){
  const lineups=Object.keys(_looksData.lineups||{});
  return `<div class="coll-grid">${lineups.map(_looksCollectionCard).join('')}</div>`;
}
// Медальон-иконка каждой линейки — авторский анимированный SVG-сигиль (не эмодзи,
// см. COSMETICS_COLLECTION_DESIGN_RULES.md §1). Код транскрибирован из брейншторма
// (.superpowers/brainstorm/1020-1785343726/content/icon-set-v3.html) без изменений.
function _looksCollectionIconSvg(lin){
  switch(lin){
    case 'forest': return `<svg class="sig-svg" viewBox="0 0 24 24" style="animation:canopyBreathe 3.6s ease-in-out infinite;transform-origin:12px 20px">
        <defs><linearGradient id="pineGrad-${lin}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#a8e0a8"/><stop offset="100%" stop-color="#3f7d3f"/></linearGradient></defs>
        <polygon points="12,2 4,10 20,10" fill="url(#pineGrad-${lin})" stroke="#3f7d3f" stroke-width=".6"/>
        <polygon points="12,6 3,15 21,15" fill="url(#pineGrad-${lin})" stroke="#3f7d3f" stroke-width=".6" opacity=".95"/>
        <polygon points="12,10 2,20 22,20" fill="url(#pineGrad-${lin})" stroke="#3f7d3f" stroke-width=".6" opacity=".9"/>
        <rect x="10.5" y="20" width="3" height="2.5" fill="#5c4326"/>
        <circle cx="6" cy="9" r="1" fill="#e8ffb0" style="animation:fireflyDrift 3.4s ease-in-out infinite"/>
        <circle cx="18" cy="13" r="1" fill="#e8ffb0" style="animation:fireflyDrift 4.1s ease-in-out infinite 1.1s"/>
        <circle cx="9" cy="17" r=".7" fill="#e8ffb0" style="animation:fireflyDrift 3.8s ease-in-out infinite 2s"/>
      </svg>`;
    case 'threshold': return `<svg class="sig-svg" viewBox="0 0 24 24" fill="none">
        <defs>
          <clipPath id="gateClip-${lin}"><path d="M6.5 22V10a5.5 5.5 0 0 1 11 0v12z"/></clipPath>
          <linearGradient id="gateGlow-${lin}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#c084fc" stop-opacity="0"/><stop offset="50%" stop-color="#e6c9ff" stop-opacity=".9"/><stop offset="100%" stop-color="#c084fc" stop-opacity="0"/></linearGradient>
        </defs>
        <path d="M5 22V10a7 7 0 0 1 14 0v12" stroke="currentColor" stroke-width="1.3" style="color:#c084fc"/>
        <path d="M6.5 22V10a5.5 5.5 0 0 1 11 0v12" stroke="currentColor" stroke-width=".6" opacity=".5" style="color:#c084fc"/>
        <g clip-path="url(#gateClip-${lin})">
          <rect x="4" y="0" width="16" height="6" fill="url(#gateGlow-${lin})" style="animation:portalTravel 3.2s ease-in-out infinite"/>
          <g style="animation:portalSwirl 6s linear infinite;transform-origin:12px 15px">
            <circle cx="12" cy="11" r=".6" fill="#e6c9ff"/><circle cx="12" cy="19" r=".5" fill="#e6c9ff"/>
          </g>
        </g>
      </svg>`;
    case 'frost': return `<svg class="sig-svg" viewBox="0 0 24 24" fill="none" stroke="#7ad4ff" stroke-width="1.1" style="transform-origin:center;animation:frostSway 4.5s ease-in-out infinite">
        <line x1="12" y1="2" x2="12" y2="22"/><line x1="12" y1="2" x2="12" y2="22" transform="rotate(60 12 12)"/><line x1="12" y1="2" x2="12" y2="22" transform="rotate(120 12 12)"/>
        <path d="M12 6 9 8M12 6 15 8M12 18 9 16M12 18 15 16M12 4 10.5 5M12 4 13.5 5" style="animation:frostTwinkle 2s ease-in-out infinite"/>
        <circle cx="12" cy="12" r="1.4" fill="#7ad4ff" stroke="none" style="animation:frostTwinkle 2s ease-in-out infinite .3s"/>
      </svg>
      <svg class="sig-svg" viewBox="0 0 24 24" style="position:absolute;inset:0;margin:auto">
        <text x="4" y="2" font-size="3" fill="#cdeeff" style="--sx:3px;animation:snowFall 3s linear infinite">❋</text>
        <text x="17" y="0" font-size="2.4" fill="#cdeeff" style="--sx:-2px;animation:snowFall 3.6s linear infinite 1.2s">❋</text>
        <text x="10" y="-2" font-size="2" fill="#cdeeff" style="--sx:2px;animation:snowFall 2.6s linear infinite 2s">❋</text>
      </svg>`;
    case 'inferno': return `<div style="position:absolute;width:40px;height:40px;border-radius:50%;background:radial-gradient(circle,#ff7a3d,transparent 70%);animation:heatGlow 2.4s ease-in-out infinite"></div>
      <svg class="sig-svg" viewBox="0 0 24 24">
        <defs><linearGradient id="flameGrad-${lin}" x1="0" y1="1" x2="0" y2="0"><stop offset="0%" stop-color="#ff7a3d"/><stop offset="60%" stop-color="#ffb15e"/><stop offset="100%" stop-color="#fff1c2"/></linearGradient></defs>
        <path d="M12 2C9 6 6 9 6 13a6 6 0 0 0 12 0c0-2-1-3.5-2-5 .3 2-.5 3-1.5 3.5.5-3-1-6-2.5-9.5z" fill="url(#flameGrad-${lin})" style="transform-origin:12px 22px;animation:flameFlicker 1.6s ease-in-out infinite"/>
        <circle cx="9" cy="18" r="1" fill="#ffb15e" style="--ex:-4px;animation:emberRise 2.2s ease-in infinite"/>
        <circle cx="15" cy="19" r="1" fill="#ffb15e" style="--ex:5px;animation:emberRise 2.6s ease-in infinite .8s"/>
        <circle cx="12" cy="20" r=".8" fill="#ffb15e" style="--ex:1px;animation:emberRise 2s ease-in infinite 1.5s"/>
      </svg>`;
    case 'celestial': return `<svg class="sig-svg" viewBox="0 0 24 24" style="position:absolute;transform-origin:center">
        <g stroke="#e8c45a" stroke-width=".6">
          <line x1="12" y1="0" x2="12" y2="4" style="animation:rayPulse 2s ease-in-out infinite"/>
          <line x1="12" y1="20" x2="12" y2="24" style="animation:rayPulse 2s ease-in-out infinite .5s"/>
          <line x1="0" y1="12" x2="4" y2="12" style="animation:rayPulse 2s ease-in-out infinite 1s"/>
          <line x1="20" y1="12" x2="24" y2="12" style="animation:rayPulse 2s ease-in-out infinite 1.5s"/>
        </g>
      </svg>
      <svg class="sig-svg" viewBox="0 0 24 24" style="transform-origin:center;animation:starSpin 9s linear infinite">
        <defs><radialGradient id="starGrad-${lin}"><stop offset="0%" stop-color="#fff6d8"/><stop offset="100%" stop-color="#e8c45a"/></radialGradient></defs>
        <path d="M12 2 L14 10 L22 12 L14 14 L12 22 L10 14 L2 12 L10 10 Z" fill="url(#starGrad-${lin})"/>
        <circle cx="12" cy="12" r="2.2" fill="#fff6d8" style="animation:starPulse 2.4s ease-in-out infinite"/>
      </svg>`;
    case 'void': return `<svg class="sig-svg" viewBox="0 0 24 24" fill="none" style="position:absolute;animation:voidSwirl 12s linear infinite;transform-origin:12px 12px">
        <circle cx="12" cy="2.3" r=".6" fill="#ffd0e2" style="animation:voidSpark 2.4s ease-in-out infinite"/>
        <circle cx="21.7" cy="12" r=".5" fill="#ffd0e2" style="animation:voidSpark 3s ease-in-out infinite .8s"/>
        <circle cx="12" cy="21.7" r=".5" fill="#ffd0e2" style="animation:voidSpark 2.7s ease-in-out infinite 1.6s"/>
      </svg>
      <svg class="sig-svg" viewBox="0 0 24 24" fill="none">
        <defs><radialGradient id="voidGrad-${lin}" cx="50%" cy="50%" r="50%"><stop offset="55%" stop-color="#0e1019"/><stop offset="100%" stop-color="#ff4d8d" stop-opacity=".6"/></radialGradient></defs>
        <circle cx="12" cy="12" r="8.4" fill="url(#voidGrad-${lin})" stroke="#ff4d8d" stroke-width="1"/>
        <circle cx="12" cy="12" r="8.4" fill="#0e1019" style="animation:voidOrbit 6s ease-in-out infinite"/>
      </svg>`;
    case 'artifact': return `<svg class="sig-svg" viewBox="0 0 24 24" style="overflow:visible">
        <defs>
          <clipPath id="gemclip-${lin}"><path d="M12 2 L20 9 L16 21 L8 21 L4 9 Z"/></clipPath>
          <linearGradient id="gemGrad-${lin}" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#c8fbfb"/><stop offset="100%" stop-color="#1f9d9d"/></linearGradient>
        </defs>
        <path d="M12 2 L20 9 L16 21 L8 21 L4 9 Z" fill="url(#gemGrad-${lin})" opacity=".85" stroke="#3fe0e0" stroke-width=".8"/>
        <path d="M4 9 L20 9M8 21 L12 9 L16 21M12 2 L12 9" stroke="#0b3d3d" stroke-width=".6" opacity=".6" fill="none"/>
        <g clip-path="url(#gemclip-${lin})">
          <rect x="-4" y="-4" width="10" height="32" fill="#fff" opacity=".5" style="animation:gemShimmer 3.6s ease-in-out infinite alternate"/>
        </g>
        <circle cx="9" cy="12" r=".7" fill="#fff" style="animation:gemSparkle 2.6s ease-in-out infinite"/>
        <circle cx="15" cy="15" r=".6" fill="#fff" style="animation:gemSparkle 3.1s ease-in-out infinite 1.3s"/>
      </svg>`;
    default: return `<svg class="sig-svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="1.2"/></svg>`;
  }
}
```

**Важно про `id` внутри `<defs>`:** каждый `<linearGradient>`/`<radialGradient>`/`<clipPath> id` включает `-${lin}` (например `pineGrad-forest`) — SVG `id` глобальны для всего документа, и без этого суффикса все 7 карточек ссылались бы на ОДИН И ТОТ ЖЕ `id="pineGrad"`, последний отрендеренный элемент с этим id побеждал бы, ломая заливку остальных. В мокапе брейншторма (где на экране был только ОДИН экземпляр каждой иконки за раз) этой проблемы не было — она появляется именно тут, где все 7 рендерятся ОДНОВременно на одной странице. Не убирать суффикс при переносе кода.

- [ ] **Step 4: Добавить CSS**

Добавить в `app.css` НОВЫЙ блок (можно в конец файла или рядом с существующими `.looks-*` правилами — уточнить по вкусу, главное не внутри существующего правила):

```css
/* ═══ Стадия 2 (2026-07-30): режим «По коллекциям» — 7 карточек-линеек ═══ */
@keyframes fireflyDrift { 0%{opacity:.1;transform:translate(0,0)} 30%{opacity:.9;transform:translate(1px,-3px)} 55%{opacity:.4;transform:translate(-1px,-4px)} 80%{opacity:.8;transform:translate(0,-2px)} 100%{opacity:.1;transform:translate(0,0)} }
@keyframes canopyBreathe { 0%,100%{transform:scale(1)} 50%{transform:scale(1.025)} }
@keyframes portalTravel { 0%{transform:translateY(9px);opacity:0} 15%{opacity:.8} 85%{opacity:.8} 100%{transform:translateY(-9px);opacity:0} }
@keyframes portalSwirl { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
@keyframes frostSway { 0%,100%{transform:rotate(-6deg)} 50%{transform:rotate(6deg)} }
@keyframes frostTwinkle { 0%,100%{opacity:.35} 45%{opacity:1} 60%{opacity:.5} }
@keyframes snowFall { 0%{transform:translate(0,-2px);opacity:0} 20%{opacity:.9} 100%{transform:translate(var(--sx,2px),20px);opacity:0} }
@keyframes flameFlicker { 0%{transform:scaleY(1) scaleX(1) skewX(0deg)} 22%{transform:scaleY(1.07) scaleX(.97) skewX(-2deg)} 48%{transform:scaleY(.96) scaleX(1.03) skewX(1deg)} 74%{transform:scaleY(1.09) scaleX(.98) skewX(-1.5deg)} 100%{transform:scaleY(1) scaleX(1) skewX(0deg)} }
@keyframes emberRise { 0%{opacity:0;transform:translate(0,0) scale(.5)} 15%{opacity:1} 100%{opacity:0;transform:translate(var(--ex,3px),-18px) scale(.15)} }
@keyframes heatGlow { 0%,100%{opacity:.25} 50%{opacity:.55} }
@keyframes starSpin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
@keyframes starPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.75;transform:scale(1.1)} }
@keyframes rayPulse { 0%,100%{opacity:.2} 50%{opacity:.7} }
@keyframes voidOrbit { 0%{transform:translate(3px,0)} 25%{transform:translate(0,3px)} 50%{transform:translate(-3px,0)} 75%{transform:translate(0,-3px)} 100%{transform:translate(3px,0)} }
@keyframes voidSpark { 0%,100%{opacity:0} 50%{opacity:.9} }
@keyframes voidSwirl { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
@keyframes gemShimmer { 0%{transform:translateX(-30px) translateY(-30px) rotate(25deg)} 100%{transform:translateX(30px) translateY(30px) rotate(25deg)} }
@keyframes gemSparkle { 0%,100%{opacity:0;transform:scale(.4)} 50%{opacity:1;transform:scale(1)} }

.coll-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
.sig-med { width: 56px; height: 56px; border-radius: 50%; position: relative; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; overflow: hidden; }
.sig-med::before { content: ''; position: absolute; inset: 0; border-radius: 50%; background: radial-gradient(circle at 35% 30%, #232739, #0e1019 75%); box-shadow: inset 0 2px 6px rgba(0,0,0,.5); }
.sig-svg { position: relative; width: 27px; height: 27px; filter: drop-shadow(0 0 5px var(--c)); }
.ring { position: absolute; inset: 0; border-radius: 50%; padding: 2.5px; }
.ring-mask { width: 100%; height: 100%; border-radius: 50%; background: #0e1019; }

.coll-card { background: linear-gradient(135deg, var(--bg2), var(--bg3)); border-radius: 14px; padding: 1px; position: relative; cursor: pointer; }
.coll-card:active { transform: scale(.98); }
.coll-inner { background: linear-gradient(135deg, var(--bg2), var(--bg3)); border: 1px solid var(--cb); border-radius: 13px; padding: 10px; position: relative; overflow: hidden; }
.coll-frame { position: absolute; inset: 3px; border: 1px solid var(--cb); border-radius: 11px; opacity: .5; pointer-events: none; }
.coll-inner::before { content: ''; position: absolute; inset: 0; background: radial-gradient(circle at 8% 8%, var(--cg), transparent 55%); }
.coll-top { display: flex; align-items: center; gap: 8px; position: relative; }
.coll-name { color: var(--bright); font-weight: 700; font-size: 11px; line-height: 1.2; }
.coll-status { font-size: 8.5px; font-weight: 700; margin-top: 3px; display: inline-block; border-radius: 6px; padding: 1px 6px; }
.coll-price { color: var(--muted); font-size: 8px; margin-top: 2px; }
.coll-slots { display: flex; gap: 3px; margin-top: 8px; position: relative; padding-top: 7px; border-top: 1px solid rgba(255,255,255,.06); }
.coll-slot { flex: 1; text-align: center; font-size: 9px; opacity: .25; filter: grayscale(1); }
.coll-slot.on { opacity: 1; filter: none; text-shadow: 0 0 4px var(--c); }
```

- [ ] **Step 5: `node --check`, перезапустить preview_server, прогнать проверку**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_collections_cards.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 6: Визуальная проверка (скриншот)**

```bash
node -e "
const puppeteer = require('puppeteer');
(async () => {
  const b = await puppeteer.launch({ headless: 'new' });
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 900, deviceScaleFactor: 2 });
  await p.goto('http://localhost:8402/', { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 1500));
  await p.mouse.click(195, 700);
  await new Promise(r => setTimeout(r, 500));
  await p.evaluate(() => openLooksModal());
  await new Promise(r => setTimeout(r, 800));
  await p.screenshot({ path: 'predvestnik_v2/tools/_collections_screenshot.png', fullPage: true });
  await b.close();
})();
"
```
Открыть `predvestnik_v2/tools/_collections_screenshot.png` (Read tool) и визуально подтвердить: 7 разноцветных медальонов с узнаваемой геометрией (ёлка/арка/снежинка/пламя/звезда/затмение/кристалл), кольца-прогресса видны, полоски слотов видны. Удалить скриншот после проверки (`rm predvestnik_v2/tools/_collections_screenshot.png`) — это временный файл для ревью, не постоянный тестовый артефакт.

- [ ] **Step 7: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_collections_cards.mjs
git commit -m "feat(cosmetics): карточки коллекций — 7 SVG-сигилей, кольцо-прогресс, полоска слотов"
```

---

### Task 3: Навигация — тап по карточке коллекции

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js` (новая функция `_looksOpenCollection`)
- Create: `predvestnik_v2/tools/verify_collections_navigation.mjs`

**Interfaces:**
- Consumes: `_looksSetMode` (Task 1), `_looksFilter`/`_looksPickLineup`-style state (Стадия 1, уже существует), `onclick="_looksOpenCollection('${lin}')"` уже вызывается из карточки (Task 2, строка с `<div class="coll-card" ... onclick="_looksOpenCollection('${lin}')">`).
- Produces: `_looksOpenCollection(lin)` (function).

- [ ] **Step 1: Написать puppeteer-проверку**

Создать `predvestnik_v2/tools/verify_collections_navigation.mjs`:

```js
// Тап по карточке коллекции переключает в режим «По слотам», отфильтрованный
// на эту линейку, и режим сохраняется (можно вернуться назад к «По коллекциям»).
import puppeteer from 'puppeteer';
const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }
const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700);
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 800));

await page.click('.coll-card[data-lineup="inferno"]');
await new Promise(r => setTimeout(r, 400));

const state = await page.evaluate(() => ({
  mode: _looksMode,
  filter: _looksFilter,
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
  lineupPillText: (document.getElementById('looks-lineup-pill') || {}).textContent || null,
}));
check('тап по карточке "Инферно" переключает режим на slots', state.mode === 'slots');
check('фильтр линейки установлен на inferno', state.filter === 'inferno');
check('умный ряд "По слотам" виден', state.hasFilterBar);
check('пилюля линейки показывает название Инферно', /Инферно/i.test(state.lineupPillText || ''));

// Кнопка "По коллекциям" в переключателе возвращает назад (не теряя фильтр слотов)
await page.click('[data-mode="collections"]');
await new Promise(r => setTimeout(r, 300));
const back = await page.evaluate(() => ({ mode: _looksMode, cardCount: document.querySelectorAll('.coll-card').length }));
check('кнопка "По коллекциям" возвращает в режим collections', back.mode === 'collections');
check('карточки коллекций снова на экране', back.cardCount === 7);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

- [ ] **Step 2: Прогнать, убедиться что падает** (функции `_looksOpenCollection` ещё нет — клик по карточке ничего не сделает)

```bash
node predvestnik_v2/tools/verify_collections_navigation.mjs
```

- [ ] **Step 3: Реализовать `_looksOpenCollection`**

Добавить в `app.10.js` рядом с `_looksSetMode` (Task 1):

```js
// Тап по карточке коллекции: переключает в «По слотам», фильтрует на эту линейку.
// Полноценный компактный «детальный экран одной линейки» — Стадия 3 (там же
// появляется кнопка «Купить всё недостающее», массовая покупка). Сейчас —
// осознанно простой мост на уже проверенный фильтр Стадии 1.
function _looksOpenCollection(lin){
  _looksFilter=lin;
  _looksSetMode('slots');
}
```

**Обратить внимание:** `_looksSetMode` уже вызывает `renderLooks()` внутри себя — отдельный вызов рендера здесь не нужен. Порядок важен: `_looksFilter` выставляется ДО `_looksSetMode`, чтобы к моменту рендера умного ряда (Стадия 1, `_looksFilterHtml()`) фильтр уже был установлен.

- [ ] **Step 4: `node --check`, перезапустить preview_server, прогнать проверку**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_collections_navigation.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/tools/verify_collections_navigation.mjs
git commit -m "feat(cosmetics): тап по карточке коллекции открывает «По слотам» с фильтром"
```

---

### Task 4: `prefers-reduced-motion`/`no-fx` для новых анимаций

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.css` (новое правило, конец блока Стадии 2)
- Create: `predvestnik_v2/tools/verify_collections_nofx.mjs`

**Interfaces:**
- Consumes: класс `body.no-fx` (уже существует в проекте, переключается настройками пользователя — см. `app.02.js::openSettingsModal`).
- Produces: ничего наружу, чисто CSS.

- [ ] **Step 1: Написать puppeteer-проверку**

Создать `predvestnik_v2/tools/verify_collections_nofx.mjs`:

```js
// При body.no-fx все новые keyframe-анимации иконок должны быть отключены
// (DESIGN_RULES.md §8 — открытый пункт, закрывается здесь).
import puppeteer from 'puppeteer';
const FAIL = [];
function check(name, cond) { if (!cond) FAIL.push(name); else console.log('OK:', name); }
const browser = await puppeteer.launch({ headless: 'new' });
const page = await browser.newPage();
await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 2 });
await page.goto('http://localhost:8402/', { waitUntil: 'load' });
await new Promise(r => setTimeout(r, 1500));
await page.mouse.click(195, 700);
await new Promise(r => setTimeout(r, 500));
await page.evaluate(() => document.body.classList.add('no-fx'));
await page.evaluate(() => openLooksModal());
await new Promise(r => setTimeout(r, 800));

const anims = await page.evaluate(() => {
  const results = [];
  document.querySelectorAll('.coll-card .sig-svg, .coll-card .sig-svg *, .coll-card [style*="animation"]').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.animationName && cs.animationName !== 'none') results.push({ tag: el.tagName, cls: el.className, anim: cs.animationName });
  });
  return results;
});
check('под body.no-fx ни один элемент иконок не анимируется', anims.length === 0);
if (anims.length) console.log('still animating:', JSON.stringify(anims));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

- [ ] **Step 2: Прогнать, убедиться что падает** (анимации ещё не отключены под `no-fx`)

```bash
node predvestnik_v2/tools/verify_collections_nofx.mjs
```

- [ ] **Step 3: Добавить CSS-оверрайд**

Добавить в `app.css`, в САМЫЙ КОНЕЦ блока Стадии 2 (после `.coll-slot.on` из Task 2):

```css
/* Отключение анимаций под настройкой «уменьшить анимации» — тот же паттерн,
   что уже используется по всему проекту (body.no-fx .xxx { animation: none }). */
body.no-fx .coll-card .sig-svg,
body.no-fx .coll-card .sig-svg *,
body.no-fx .coll-card [style*="animation"] {
  animation: none !important;
}
```

- [ ] **Step 4: `node --check`, перезапустить preview_server, прогнать проверку**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_collections_nofx.mjs
```
Ожидается: `ALL OK`.

- [ ] **Step 5: Убедиться, что без `no-fx` анимации по-прежнему работают** (регрессия наоборот — оверрайд не должен случайно вырубить анимации всегда)

```bash
node -e "
const puppeteer = require('puppeteer');
(async () => {
  const b = await puppeteer.launch({ headless: 'new' });
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 844 });
  await p.goto('http://localhost:8402/', { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 1500));
  await p.mouse.click(195, 700);
  await new Promise(r => setTimeout(r, 500));
  await p.evaluate(() => openLooksModal());
  await new Promise(r => setTimeout(r, 800));
  const anims = await p.evaluate(() => {
    const svg = document.querySelector('.coll-card .sig-svg');
    return svg ? getComputedStyle(svg).animationName : null;
  });
  console.log('animationName БЕЗ no-fx (должно быть НЕ none):', anims);
  await b.close();
})();
"
```
Ожидается: значение отличное от `none` (например `canopyBreathe` для первой линейки в списке).

- [ ] **Step 6: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_collections_nofx.mjs
git commit -m "fix(cosmetics): анимации иконок коллекций отключаются под body.no-fx"
```

---

## Финальная проверка стадии (перед деплоем)

- [ ] **Прогнать все 4 новых + все 6 скриптов Стадии 1 подряд** (Стадия 2 не должна ломать Стадию 1)

```bash
node predvestnik_v2/tools/preview_server.mjs &
sleep 1
node predvestnik_v2/tools/verify_collections_toggle.mjs
node predvestnik_v2/tools/verify_collections_cards.mjs
node predvestnik_v2/tools/verify_collections_navigation.mjs
node predvestnik_v2/tools/verify_collections_nofx.mjs
node predvestnik_v2/tools/verify_slots_smartrow.mjs
node predvestnik_v2/tools/verify_slots_meter.mjs
node predvestnik_v2/tools/verify_slots_accent.mjs
node predvestnik_v2/tools/verify_slots_empty.mjs
node predvestnik_v2/tools/verify_slots_spacing.mjs
node predvestnik_v2/tools/verify_chest_craft_isolation.mjs
```
Все десять — `ALL OK`.

- [ ] **`node --check` на весь файл ещё раз**

```bash
node --check predvestnik_v2/FastAPI/static/app.10.js
```

- [ ] **Проверить отсутствие дублей SVG id при одновременном рендере всех 7 карточек** (см. предупреждение в Task 2 Step 3)

```bash
node -e "
const puppeteer = require('puppeteer');
(async () => {
  const b = await puppeteer.launch({ headless: 'new' });
  const p = await b.newPage();
  await p.setViewport({ width: 390, height: 900 });
  await p.goto('http://localhost:8402/', { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 1500));
  await p.mouse.click(195, 700);
  await new Promise(r => setTimeout(r, 500));
  await p.evaluate(() => openLooksModal());
  await new Promise(r => setTimeout(r, 800));
  const ids = await p.evaluate(() => {
    const all = [...document.querySelectorAll('.coll-card [id]')].map(e => e.id);
    const dupes = all.filter((id, i) => all.indexOf(id) !== i);
    return { total: all.length, dupes };
  });
  console.log(JSON.stringify(ids));
  await b.close();
})();
"
```
Ожидается: `dupes: []`.

- [ ] **Ручной смоук на реальном телефоне** (не автоматизируется) — реальная плавность анимаций 7 одновременных SVG на живом устройстве (владелец явно попросил не блокировать разработку на этом, но перед деплоем стоит один раз увидеть вживую), переключение режимов пальцем, тап по карточке.

- [ ] **Деплой на DigitalOcean** — рестарт процесса (см. проектную память `project_prod_stale_static`), затем смоук.

## Что НЕ входит в эту стадию (следующий план — Стадия 3)

- Полноценный детальный экран открытой коллекции («алтарная» шапка, сегментный измеритель N=предметов, фоновые частицы) — сейчас тап просто фильтрует «По слотам».
- Кнопка «Купить всё недостающее» (массовая покупка, реальная транзакция зарниками).
- «Сейчас→Станет» с публичной картой, объединённые «Образы» (пресеты+сеты), 6 QoL-фич, экран-праздник — по спеку, каждое отдельным планом при переходе к нему.
