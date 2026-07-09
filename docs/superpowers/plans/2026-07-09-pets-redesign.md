# Питомцы 2.0 (редизайн под язык Казармы) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Свести вкладку «Питомцы» к единому экрану (слоты активный/пассивные + грид всех питомцев), убрав отдельную вкладку «Склад» — визуальный язык 1:1 с уже реализованной Казармой боевых юнитов (`app.11.js`/`.bk-*` CSS).

**Architecture:** Чистый фронтенд-рефакторинг одного файла (`app.03.js`) + точечные правки `index.html`/`app.css`. Бэкенд (`FastAPI/routers/zoo.py`, `services/zoo.py`, `infrastructure/repositories/zoo.py`) НЕ трогается — все нужные поля уже есть в ответе `GET /zoo/`. Максимально переиспользуются существующие CSS-классы Казармы (`.bk-slot`, `.bk-grid`, `.bk-card`, `.bk-insq`) вместо копипасты новых правил — см. `PETS_REDESIGN_CONCEPT.md` §3/§6 (спека, согласована с пользователем 2026-07-09).

**Tech Stack:** Vanilla JS (classic script, НЕ ES-модуль — `app.js` склеивается из `app.01.js…app.11.js` в `FastAPI/main.py`), чистый CSS (без препроцессоров), Jinja-шаблон `index.html`.

## Global Constraints

- Этот проект НЕ использует pytest/автотесты для фронтенда. Верификация — `node --check` на каждую тронутую часть + полную склейку всех 11 частей, плюс визуальная проверка через Playwright-стенд с мок-данными (см. `[[project-frontend-static-testing]]` в памяти пользователя, рецепт — в Task 7).
- `let/const` — только вверху `<script>` (TDZ!). Новые top-level переменные добавлять в начало файла, если требуются.
- Функциональность модалки деталей питомца (кормёжка/предметы/перемещение/все 10 уровней) сохраняется 1:1 — переверстка ТОЛЬКО визуальная (см. Task 6).
- Бестиарий (`renderZooGuide`, `#zoo-bestiary`) не трогать вообще.
- Особые виджеты вида (Хомяк/Волк/Единорог, `collectHamster`/`doWolfRestorePick`/`doUnicornImmunity`) и лаунчер похода (`expLauncherHtml`) — логика/API-вызовы не меняются, только их место в новой разметке (см. Task 5).
- Коммитить после каждой задачи (`git add` конкретные файлы, не `-A`).

---

### Task 1: index.html — убрать вкладку «Склад»

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/index.html:113-123`

**Interfaces:**
- Consumes: ничего нового.
- Produces: разметка `#pg-zoo` с 2 вкладками вместо 3 — на неё опирается Task 5 (`swZoo`/`renderZoo`).

- [ ] **Step 1: Заменить блок вкладок**

Текущий блок (строки 113-123):
```html
<!-- ═══ 2. ПИТОМЦЫ ═══ -->
<div id="pg-zoo" class="page">
  <div id="zoo-exp-wrap"></div>
  <div class="tabs">
    <button class="tb active" onclick="swZoo('nursery',this)">🐾 Мои питомцы</button>
    <button class="tb" onclick="swZoo('storage',this)">📦 Склад</button>
    <button class="tb" onclick="swZoo('bestiary',this)">📖 Бестиарий</button>
  </div>
  <div id="zoo-c"></div>
  <div id="zoo-bestiary" style="display:none"><div id="best-c"></div></div>
</div>
```

Заменить на:
```html
<!-- ═══ 2. ПИТОМЦЫ (Питомцы 2.0: единый экран — слоты + весь ростер гридом) ═══ -->
<div id="pg-zoo" class="page">
  <div id="zoo-exp-wrap"></div>
  <div class="tabs">
    <button class="tb active" onclick="swZoo('nursery',this)">🐾 Мои питомцы</button>
    <button class="tb" onclick="swZoo('bestiary',this)">📖 Бестиарий</button>
  </div>
  <div id="zoo-c"></div>
  <div id="zoo-bestiary" style="display:none"><div id="best-c"></div></div>
</div>
```

- [ ] **Step 2: Проверить, что вкладка «Склад» нигде больше не упоминается**

Run: `grep -rn "swZoo('storage'" predvestnik_v2/FastAPI/static/`
Expected: no matches (пусто) — если что-то найдётся, будет починено в Task 5 (там переписывается `swZoo`).

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/FastAPI/static/index.html
git commit -m "feat(pets): убрать вкладку Склад из index.html (Питомцы 2.0, единый экран)"
```

---

### Task 2: app.css — новые классы слотов/грида/анимаций питомцев

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.css` (добавить в конец файла, после строки 2423)

**Interfaces:**
- Consumes: существующие `.bk-slot`, `.bk-grid`, `.bk-card`, `.bk-insq`, `.fat-bar`/`.fat-fill` (переиспользуются напрямую в разметке из Task 3-4, НЕ дублируются здесь).
- Produces: классы `.zc-slot-hero`, `.zc-slots-row`, `.zc-buy-hint`, `.zc-card-fat`, `.zc-card-in` (анимация появления), `.zc-slot-fill` (анимация назначения в слот) — используются в Task 3/4.

- [ ] **Step 1: Добавить CSS-блок в конец `app.css`**

```css

/* ═══ Питомцы 2.0: слоты/ростер — максимально переиспользует .bk-*
   из Казармы (BATTLE_REWORK), новое — только то, чего там не было ═══ */
.zc-slot-hero { grid-column: span 3; padding: 14px 8px; }
.zc-slot-hero .bk-slot-e { font-size: 34px; }
.zc-slots-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-bottom: 6px; }
.zc-slots-passive { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
.zc-buy-hint { font-size: 10px; color: var(--muted); text-align: center; margin: 4px 0 10px; line-height: 1.5; }

/* Тонкая полоска усталости внизу карточки ростера (пользователь явно попросил
   видеть её прямо в гриде, не только в деталях) */
.zc-card-fat { height: 3px; border-radius: 2px; background: var(--bg1); margin-top: 5px; overflow: hidden; }
.zc-card-fat-fill { height: 100%; transition: width .3s; }

/* Появление карточки в гриде при первом рендере — мягче chestPop */
@keyframes zcCardIn { from { opacity: 0; transform: scale(.92); } to { opacity: 1; transform: scale(1); } }
.zc-card-in { animation: zcCardIn .35s ease both; }

/* Питомец «влетает» в слот при перемещении */
@keyframes zcSlotFill { 0% { transform: scale(.85); opacity: .4; } 60% { transform: scale(1.04); } 100% { transform: scale(1); opacity: 1; } }
.zc-slot-fill { animation: zcSlotFill .3s ease both; }

/* Уважаем no-fx/prefers-reduced-motion — анимации лёгкие, упрощённого
   промежуточного режима не нужно, просто гасим (см. PETS_REDESIGN_CONCEPT §5) */
@media (prefers-reduced-motion: reduce) { .zc-card-in, .zc-slot-fill { animation: none; } }
body.no-fx .zc-card-in, body.no-fx .zc-slot-fill { animation: none; }
```

- [ ] **Step 2: Проверить, что CSS не сломал существующие правила**

Run: `node -e "require('fs').readFileSync('predvestnik_v2/FastAPI/static/app.css','utf8')" && echo CSS_READABLE`
Expected: `CSS_READABLE` (CSS не парсится Node, это просто smoke-check что файл не битый/не обрезан — визуальная проверка синтаксиса CSS будет в Task 7 через реальный рендер).

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.css
git commit -m "feat(pets): CSS слотов/грида/анимаций для Питомцы 2.0 (переиспользует .bk-*)"
```

---

### Task 3: app.03.js — рендер слотов (активный + пассивные) и пикер назначения

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.03.js` (новые функции добавить перед `function petCard(p) {` — текущая строка 361)

**Interfaces:**
- Consumes: `_zooData` (глобал, уже существует, заполняется в `loadZoo()`) — поля `pets[]` (каждый: `id,name,species_id,rarity,pet_level,fatigue,placement`), `max_slots`, `bought_slots`, `vip_extra_slot`, `at_slot_cap`, `slot_next_price`, `base_slots`. `doMove(pid, placement, btn)` (существующая функция, строка 646, НЕ меняется) — вызывается пикером.
- Produces: `_zcEmoji(speciesId) → string` (переиспользуется в Task 4's `_zcCard`), `_zcRenderSlots(active, passive, totalSlots) → string` (HTML), `_zcOpenSlotPicker(targetPlacement)` (глобальная, вызывается из `onclick`), `_zcAssignPick(petId, targetPlacement)` (глобальная).

- [ ] **Step 1: Добавить функции слотов перед `petCard`**

Вставить непосредственно перед строкой `function petCard(p) {` (361):

```js
// ── Питомцы 2.0: слоты (Казарма-стиль) ─────────────────────────────────────────
function _zcEmoji(speciesId) {
  // PET_SPECIES_EMOJI определён в app.04.js (позже в склейке) — но это function
  // declaration вызывается только по клику, после того как весь скрипт уже
  // выполнился, так что const уже проинициализирован. Defensive-check — тот же
  // паттерн, что уже используется в app.06.js/app.11.js для этого же глобала.
  const map = (typeof PET_SPECIES_EMOJI !== 'undefined') ? PET_SPECIES_EMOJI : {};
  return map[speciesId] || '🐾';
}
function _zcSlotInner(p) {
  if (!p) return `<div class="bk-slot-e bk-slot-empty">➕</div><div class="bk-slot-n cx-dim">пусто</div>`;
  const fatPct = p.fatigue || 0;
  return `<div class="bk-slot-e">${_zcEmoji(p.species_id)}</div>
    <div class="bk-slot-n">${esc(p.name || p.species_id)}</div>
    <div class="bk-slot-s">Ур.${p.pet_level || 1}/10</div>
    <div class="zc-card-fat"><div class="zc-card-fat-fill" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>`;
}
function _zcRenderSlots(active, passive, totalSlots) {
  const heroPet = active[0] || null;
  const hero = `<div class="bk-slot zc-slot-hero" onclick="${heroPet ? `openPetModal(${heroPet.id})` : `_zcOpenSlotPicker('active')`}">
    <div class="bk-slot-t">⚔️ Активный</div>${_zcSlotInner(heroPet)}
  </div>`;
  const passiveSlotsCount = Math.max(0, totalSlots - 1);
  const passiveCells = [];
  for (let i = 0; i < passiveSlotsCount; i++) {
    const p = passive[i] || null;
    passiveCells.push(`<div class="bk-slot" onclick="${p ? `openPetModal(${p.id})` : `_zcOpenSlotPicker('passive')`}">
      <div class="bk-slot-t">🛡 Пассивный</div>${_zcSlotInner(p)}
    </div>`);
  }
  return `<div class="zc-slots-row">${hero}</div>
    <div class="zc-slots-passive">${passiveCells.join('')}</div>`;
}
function _zcOpenSlotPicker(targetPlacement) {
  if (!_zooData) return;
  const storagePets = (_zooData.pets || []).filter(p => p.placement === 'storage');
  if (!storagePets.length) {
    toast('На складе нет питомцев — крутни Гачу.', false);
    return;
  }
  const label = targetPlacement === 'active' ? 'В активный слот' : 'В пассивный слот';
  const rows = storagePets.map(p => `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border2)">
      <div>
        <span style="font-weight:600">${esc(p.name || p.species_id)}</span> ${rc(p.rarity)}
        <span style="font-size:11px;color:var(--muted);margin-left:6px">Ур.${p.pet_level || 1}</span>
      </div>
      <button class="btn btn-sm btn-gold" onclick="_zcAssignPick(${p.id},'${targetPlacement}',this)">Выбрать</button>
    </div>`).join('');
  OM(label, `<div>${rows}</div>`, [{ l: 'Отмена', c: 'btn-ghost', f: 'CM()' }]);
}
function _zcAssignPick(petId, targetPlacement, btn) {
  if (btn) btn.disabled = true;
  api('/zoo/move', { method: 'POST', body: JSON.stringify({ pet_id: petId, placement: targetPlacement }) })
    .then(() => { CM(); toast('✅ Перемещено!'); _zooData = null; loadZoo(); })
    .catch(e => { toast(e, false); if (btn) btn.disabled = false; });
}
```

Примечание: `_zcAssignPick` дублирует тело `doMove` (строка 646) намеренно — `doMove` принимает `btn` из контекста модалки деталей с другим набором аргументов (`pid,pl,btn` без CM() после); ре-использовать напрямую нельзя без разъезда поведения. Дублирование двух похожих 6-строчных функций — приемлемо (DRY не ценой лишней косвенности), см. `[[feedback-code-principles]]`.

- [ ] **Step 2: Проверить синтаксис**

Run: `node --check predvestnik_v2/FastAPI/static/app.03.js`
Expected: без вывода (exit code 0).

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.03.js
git commit -m "feat(pets): рендер слотов активный/пассивные + пикер назначения (Питомцы 2.0)"
```

---

### Task 4: app.03.js — карточка ростера (грид) вместо `petCard`

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.03.js:361-382` (заменить `petCard`)

**Interfaces:**
- Consumes: объект питомца `p` (те же поля, что и раньше в `petCard`), `_zcEmoji(speciesId)` (из Task 3, уже вставлена выше по файлу к этому моменту).
- Produces: `_zcCard(p) → string` (HTML одной карточки грида) — используется в Task 5's `renderZoo()`.

- [ ] **Step 1: Заменить `petCard`**

Текущий код (строки 361-382):
```js
function petCard(p) {
  const fatPct = p.fatigue || 0;
  const fatWarn = fatPct >= 100 ? '⛔ ' : fatPct >= 80 ? '⚠️ ' : '';
  const placeBadge = p.placement === 'active'
    ? '<span style="color:var(--teal);font-size:10px;font-weight:600">⚔️ Активный</span>'
    : p.placement === 'passive'
    ? '<span style="color:var(--blue);font-size:10px;font-weight:600">🛡 Пассивный</span>'
    : '<span style="color:var(--dim);font-size:10px">📦 Склад</span>';
  const lvl = p.pet_level || 1;
  const dups = p.duplicates_collected || 0;
  return `<div class="pcard" style="cursor:pointer;${fatPct>=80?'border-color:'+fatC(fatPct)+';':''}" onclick="openPetModal(${p.id})">
    <div class="pcol">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:2px">
        <div class="pn">${p.name||p.species_id} ${rc(p.rarity)}</div>
        ${placeBadge}
      </div>
      <div class="ps">Lv${lvl}/10 · 📦 ${dups} дубл.</div>
      <div class="fat-bar"><div class="fat-fill${fatPct>=80?' critical':''}" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
      <div style="font-size:10px;color:${fatC(fatPct)}">${fatWarn}${fatPct}% усталости</div>
    </div>
  </div>`;
}
```

Заменить на:
```js
// Питомцы 2.0: компактная карточка грида (Казарма-стиль) — заменяет старую
// list-style petCard. Имя функции сохранено под старым именем НЕ будет —
// все места вызова обновлены на _zcCard в Task 5.
function _zcCard(p) {
  const fatPct = p.fatigue || 0;
  const lvl = p.pet_level || 1;
  const emoji = _zcEmoji(p.species_id);   // хелпер из Task 3 (_zcSlotInner блок)
  const badge = p.placement === 'active' ? '⚔️ Активный'
    : p.placement === 'passive' ? '🛡 Пассивный' : '';
  return `<div class="bk-card zc-card zc-card-in r-${p.rarity}" onclick="openPetModal(${p.id})">
    <div class="bk-card-e">${emoji}</div>
    <div class="bk-card-n">${esc(p.name || p.species_id)}</div>
    <div class="bk-card-s">${rc(p.rarity)} · Ур.${lvl}/10</div>
    <div class="zc-card-fat"><div class="zc-card-fat-fill" style="width:${fatPct}%;background:${fatC(fatPct)}"></div></div>
    ${badge ? `<div class="bk-card-f"><span class="bk-insq">${badge}</span></div>` : ''}
  </div>`;
}
```

- [ ] **Step 2: Проверить, что старое имя `petCard` больше нигде не используется до Task 5 (временно ожидаемо — Task 5 обновит вызовы)**

Run: `grep -n "petCard(" predvestnik_v2/FastAPI/static/app.03.js`
Expected: одно вхождение — только определение `_zcCard` только что добавленное; строка `el('zoo-c').innerHTML=pets.map(petCard).join('');` внутри `renderZoo` (текущая строка ~488) всё ещё ссылается на старое имя — это ОЖИДАЕМО и будет исправлено в Task 5. Не коммитить, если `node --check` упадёт из-за этого — не упадёт (JS не проверяет существование функции на этапе парсинга, только при вызове), но зафиксировать в уме, что Task 5 обязателен сразу следом.

- [ ] **Step 3: Проверить синтаксис**

Run: `node --check predvestnik_v2/FastAPI/static/app.03.js`
Expected: без вывода (exit code 0).

- [ ] **Step 4: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.03.js
git commit -m "feat(pets): карточка ростера _zcCard в стиле Казармы (замена petCard)"
```

---

### Task 5: app.03.js — единый `renderZoo()` + упрощение `swZoo()`

Это ключевая интеграционная задача: слоты (Task 3) + виджеты видов (без изменений) + грид всех питомцев (Task 4) на одном экране, без вкладки «Склад».

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.03.js:384-491` (заменить `swZoo` целиком и `renderZoo` целиком)

**Interfaces:**
- Consumes: `_zcRenderSlots` (Task 3), `_zcCard` (Task 4), `_zooData` (существующий global), `expLauncherHtml()`, `collectHamster`, `doWolfRestorePick`, `doUnicornImmunity`, `doBuySlot` (все существующие, без изменений).
- Produces: обновлённые `swZoo(tab, btn)` и `renderZoo()` (без параметра — раньше принимала `tab`, теперь всегда рендерит единый экран).

- [ ] **Step 1: Заменить `swZoo`**

Текущий код (строки 384-395):
```js
function swZoo(tab,btn) {
  _zooTab=tab;
  document.querySelectorAll('#pg-zoo > .tabs > .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const zooC = el('zoo-c'), zooBest = el('zoo-bestiary');
  if(zooC) zooC.style.display = tab==='bestiary' ? 'none' : '';
  if(zooBest) zooBest.style.display = tab==='bestiary' ? '' : 'none';
  _trackSubtab('zoo/'+tab);
  if(tab==='bestiary') { renderZooGuide(); return; }
  if(!_zooData){loadZoo();return;}
  renderZoo(tab);
}
```

Заменить на:
```js
// Питомцы 2.0: 2 вкладки (nursery = единый экран, bestiary — без изменений).
function swZoo(tab,btn) {
  _zooTab=tab;
  document.querySelectorAll('#pg-zoo > .tabs > .tb').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  const zooC = el('zoo-c'), zooBest = el('zoo-bestiary');
  if(zooC) zooC.style.display = tab==='bestiary' ? 'none' : '';
  if(zooBest) zooBest.style.display = tab==='bestiary' ? '' : 'none';
  _trackSubtab('zoo/'+tab);
  if(tab==='bestiary') { renderZooGuide(); return; }
  if(!_zooData){loadZoo();return;}
  renderZoo();
}
```

- [ ] **Step 2: Заменить `renderZoo`**

Текущий код — строки 397-491 (весь блок от `function renderZoo(tab) {` до закрывающей `}` перед `function openPetModal`). Прочитать точный текущий диапазон перед заменой:

Run: `sed -n '397,491p' predvestnik_v2/FastAPI/static/app.03.js`

Заменить весь этот диапазон (от `function renderZoo(tab) {` до его закрывающей `}`) на:

```js
function renderZoo() {
  if(!_zooData)return;
  const allPets = _zooData.pets || [];
  if(!allPets.length){
    el('zoo-c').innerHTML=`<div style="text-align:center;padding:32px 16px;color:var(--muted)">
        <div style="font-size:32px;margin-bottom:8px">🐾</div>
        <div style="font-size:13px;font-weight:600;margin-bottom:4px">Питомцев пока нет</div>
        <div style="font-size:11px">Крутни Гачу, чтобы получить первого питомца</div>
        <button class="btn btn-gold btn-sm" style="margin-top:10px" onclick="goTo('market','gacha')">🎲 Открыть Гачу</button>
      </div>`;
    return;
  }

  const active=allPets.filter(p=>p.placement==='active');
  const passive=allPets.filter(p=>p.placement==='passive');
  const maxSlots=_zooData.max_slots||3;
  const baseSlots=_zooData.base_slots||3;
  const boughtSlots=_zooData.bought_slots||0;
  const vipExtra=_zooData.vip_extra_slot||0;
  const atCap=!!_zooData.at_slot_cap;
  const nextPrice=_zooData.slot_next_price;
  const totalSlots=maxSlots+vipExtra;
  const pendingMora=_zooData.pending_hamster_mora||0;
  const hasHamsters=allPets.some(p=>p.species_id==='hamster');

  let html = _zcRenderSlots(active, passive, totalSlots);
  html += `<div class="zc-buy-hint">
      📦 Базовых: <b style="color:var(--bright)">${baseSlots}</b>
      ${boughtSlots>0?` · 💎 Докуплено: <b style="color:var(--bright)">+${boughtSlots}</b>`:''}
      ${vipExtra>0?` · 👑 VIP: <b style="color:var(--gold)">+${vipExtra}</b>`:''}
    </div>`;
  html += atCap
    ? `<button class="btn btn-full btn-sm" disabled style="opacity:.45;cursor:not-allowed;margin-bottom:10px">🔒 Слоты за алмазы куплены (${boughtSlots}/${_zooData.max_purchasable||4})</button>`
    : `<button class="btn btn-full btn-sm btn-gold" style="margin-bottom:10px" onclick="doBuySlot()">🛒 Купить слот за ${nextPrice} 💎</button>`;

  if(hasHamsters){
    html += `<div style="background:var(--gold-dim);border:1px solid var(--border);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🐹 Хомяк-банкир накопил</div>
        <div style="font-size:16px;font-weight:700;color:var(--gold)">${pendingMora>0?fmt(pendingMora)+' 🪙':'Копит...'}</div>
      </div>
      <button class="btn btn-gold btn-sm" onclick="collectHamster(this)" ${pendingMora<1?'disabled':''}>Собрать</button>
    </div>`;
  }
  const wr=_zooData.wolf_restore;
  if(wr && wr.uses_left>0){
    html += `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
      <div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🐺 Волк — восстановление усталости</div>
        <div style="font-size:13px;font-weight:600">Осталось: ${wr.uses_left}/${wr.max_uses} · −${wr.restore_amount}% усталости</div>
      </div>
      <button class="btn btn-sm" style="background:var(--purple,#7c3aed);color:#fff" onclick="doWolfRestorePick()">Использовать</button>
    </div>`;
  }
  const ua=_zooData.unicorn_ability;
  if(ua){
    if(ua.active){
      html += `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px">
        <div style="font-size:11px;color:var(--muted)">🦄 Иммунитет усталости: <b style="color:var(--green)">АКТИВЕН</b></div>
        <div style="font-size:10px;color:var(--muted);margin-top:2px">Истекает: ${ua.expires_at?ua.expires_at.slice(0,16).replace('T',' '):''}</div>
      </div>`;
    } else if(ua.available){
      html += `<div style="background:var(--s);border:1px solid var(--border2);border-radius:var(--r);padding:10px 12px;margin-bottom:10px;display:flex;align-items:center;justify-content:space-between">
        <div>
          <div style="font-size:11px;color:var(--muted);margin-bottom:2px">🦄 Единорог — иммунитет усталости</div>
          <div style="font-size:13px;font-weight:600">Защита на ${ua.immunity_hours} ч. для всех питомцев</div>
        </div>
        <button class="btn btn-sm" style="background:linear-gradient(135deg,#a855f7,#ec4899);color:#fff" onclick="doUnicornImmunity(this)">Активировать</button>
      </div>`;
    }
  }
  html += expLauncherHtml();

  // Ростер: ВСЕ питомцы (вкл. занятых слотом — с бейджем), сортировка:
  // сначала занятые слотом (активный → пассивные), потом склад; внутри —
  // по убыванию редкости и уровня.
  const rarityRank = {mythic:5, legendary:4, epic:3, rare:2, uncommon:1, common:0};
  const placeRank = p => p.placement==='active' ? 2 : p.placement==='passive' ? 1 : 0;
  const roster = [...allPets].sort((a,b) =>
    (placeRank(b)-placeRank(a)) ||
    ((rarityRank[b.rarity]||0)-(rarityRank[a.rarity]||0)) ||
    ((b.pet_level||1)-(a.pet_level||1)));

  html += `<div class="looks-slot-t" style="margin-top:14px">📖 Все питомцы (${roster.length})</div>
    <div class="bk-grid">${roster.map(_zcCard).join('')}</div>`;

  el('zoo-c').innerHTML = html;
}
```

- [ ] **Step 3: Проверить, что старая функция `renderZoo(tab)` полностью заменена (нет двух определений)**

Run: `grep -n "^function renderZoo" predvestnik_v2/FastAPI/static/app.03.js`
Expected: ровно одна строка `function renderZoo() {`.

- [ ] **Step 4: Проверить, что `petCard` больше нигде не вызывается (Task 4 переименовала в `_zcCard`)**

Run: `grep -n "petCard" predvestnik_v2/FastAPI/static/app.03.js`
Expected: пусто (0 вхождений) — если что-то осталось, значит старый вызов `pets.map(petCard)` не был заменён, поправить вручную.

- [ ] **Step 5: Проверить синтаксис**

Run: `node --check predvestnik_v2/FastAPI/static/app.03.js`
Expected: без вывода (exit code 0).

- [ ] **Step 6: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.03.js
git commit -m "feat(pets): единый renderZoo() — слоты + виджеты + грид всех питомцев, Склад убран"
```

---

### Task 6: app.03.js/app.css — визуальная переверстка шапки модалки деталей

Функциональность (статы/бонусы/все уровни/кормёжка/предметы/перемещение) НЕ меняется — только шапка визуально приводится к чип-стилю Казармы (`.bk-info-head`).

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.03.js:564-571` (внутри `openPetModal`, только header-часть тела модалки)

**Interfaces:**
- Consumes: `p.rarity`, `p.name`, `p.species_desc`, `placePill`-эквивалент (переменные `isActive`/`isPassive`, уже вычислены выше по коду функции — строки 541-547, не трогаются).

- [ ] **Step 1: Заменить шапку тела модалки**

Текущий код (строки 564-571):
```js
    const body = `
      <!-- Header -->
      <div style="text-align:center;padding:10px 0 10px">
        <div style="font-size:28px;margin-bottom:6px">${p.name}</div>
        <div style="margin-bottom:6px">${rc(p.rarity)}</div>
        <div style="margin-bottom:8px">${placePill}</div>
        <div style="font-size:11px;color:var(--muted);line-height:1.5;max-width:280px;margin:0 auto">${p.species_desc||''}</div>
      </div>
      <div class="divider"></div>
```

Заменить на:
```js
    const body = `
      <!-- Header: чип-стиль Казармы (bk-info-head), рамка модалки по редкости
           навешивается через класс r-${p.rarity} на корневой div ниже -->
      <div class="r-${p.rarity}" style="text-align:center;padding:10px 0 10px;border-radius:var(--r)">
        <div style="font-size:28px;margin-bottom:6px">${p.name}</div>
        <div class="bk-info-head">
          <span>${rc(p.rarity)}</span>
          <span>${placePill}</span>
        </div>
        <div style="font-size:11px;color:var(--muted);line-height:1.5;max-width:280px;margin:8px auto 0">${p.species_desc||''}</div>
      </div>
      <div class="divider"></div>
```

- [ ] **Step 2: Проверить синтаксис**

Run: `node --check predvestnik_v2/FastAPI/static/app.03.js`
Expected: без вывода (exit code 0).

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.03.js
git commit -m "style(pets): шапка модалки деталей питомца в чип-стиле Казармы (функциональность без изменений)"
```

---

### Task 7: Финальная верификация — синтаксис всех частей + визуальная проверка

**Files:** нет новых, только проверка ранее изменённых.

**Interfaces:** нет.

- [ ] **Step 1: `node --check` на все 11 частей по отдельности**

Run (Bash):
```bash
cd predvestnik_v2 && for f in FastAPI/static/app.0*.js FastAPI/static/app.10.js FastAPI/static/app.11.js; do node --check "$f" || echo "FAIL: $f"; done
```
Expected: никаких строк `FAIL:` в выводе.

- [ ] **Step 2: `node --check` на полную склейку (как реально отдаётся `main.py`)**

Run (Bash):
```bash
cd predvestnik_v2 && cat FastAPI/static/app.01.js FastAPI/static/app.02.js FastAPI/static/app.03.js FastAPI/static/app.04.js FastAPI/static/app.05.js FastAPI/static/app.06.js FastAPI/static/app.07.js FastAPI/static/app.08.js FastAPI/static/app.09.js FastAPI/static/app.10.js FastAPI/static/app.11.js > /tmp/pets_concat.js && node --check /tmp/pets_concat.js && echo ALL_JS_OK
```
Expected: `ALL_JS_OK`.

- [ ] **Step 3: Визуальная проверка через Playwright-стенд**

Пересобрать статик-стенд (см. память `[[project-frontend-static-testing]]` — использовать существующий `uiroot/` из прошлых сессий, если сохранился в scratchpad, либо пересоздать по тому же рецепту: `sed` замена `{{BASE}}`/`{{ASSET_VER}}`/`{{BOT_USERNAME}}` в `index.html`, склейка `app.01.js…app.11.js` в `uiroot/static/app.js`, `http.server` из `uiroot/`).

Мок-данные `_zooData` для проверки ЧЕТЫРЁХ состояний (генерировать через `page.evaluate` с `_zooData=...; renderZoo();` — не требует живого бэкенда):
1. Пустой питомник (`pets: []`) — проверить empty-state с кнопкой в Гачу.
2. Частично занятые слоты (1 активный, 1 из 3 пассивных, остальное на складе) — проверить, что пустые слоты кликабельны и открывают пикер, полоски усталости на слотах и карточках читаемы на 390px.
3. Все слоты заняты + докупленные (VIP+куплено) — проверить, что кнопка «Купить слот» корректно показывает `🔒` при `at_slot_cap:true`.
4. Длинный ростер (10+ питомцев вперемешку redkостей/уровней) — проверить, что грид не ломается, сортировка (занятые слотом сначала) видна, скролл работает.

Для каждого состояния — скриншот 390×844, проверить консоль на ошибки (`page.on('console', ...)` — не должно быть `[error]` кроме ожидаемого WebSocket-шума).

Дополнительно: открыть модалку деталей питомца (`openPetModal(id)`) в состоянии 2 — проверить, что шапка в чип-стиле не сломала остальной контент (статы/бонусы/уровни/кормёжка/перемещение всё ещё рендерятся).

- [ ] **Step 4: Ручная сверка функциональности (чек-лист)**

Пройтись по списку и подтвердить (по коду или по скриншотам из Step 3), что ничего не потеряно относительно старой версии:
- [ ] Кормёжка (`doFeed`) — кнопки видны в модалке, вызывают тот же API.
- [ ] Применение предметов (`renderPetItems`) — не тронуто, рендерится.
- [ ] Перемещение между слотами кнопками в модалке (`doMove`) — 3 кнопки (актив/пассив/склад) всё ещё есть.
- [ ] Тап по пустому слоту открывает пикер, тап по занятому — модалку деталей.
- [ ] Покупка слота (`doBuySlot`) работает из нового расположения кнопки.
- [ ] Хомяк/Волк/Единорог/лаунчер похода — визуально на месте, клики не сломаны.
- [ ] Бестиарий (`swZoo('bestiary')`) открывается как раньше, полностью нетронут.

- [ ] **Step 5: Итоговый коммит (если Step 3-4 потребовали мелких правок)**

```bash
git add predvestnik_v2/FastAPI/static/
git commit -m "fix(pets): правки по итогам визуальной проверки Питомцы 2.0"
```

Если правок не потребовалось — пропустить (не создавать пустой коммит).

---

*Конец плана. Спека: `predvestnik_v2/PETS_REDESIGN_CONCEPT.md`. После выполнения — обновить `NOT_IMPLEMENTED.md` (перенести пункт «Питомцы 2.0» из «ОТКРЫТЫЕ ПУНКТЫ» в «ЗАКРЫТЫЕ БЛОКИ» с датой и коротким описанием) и добавить запись в `PLAYER_CHANGELOG.md`, если фича видна игроку (видна — это UI-редизайн вкладки).*
