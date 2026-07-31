# Примерочная — закреплённая dock-панель Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать доступ к примерочной постоянным и визуально цельным: компактная подписанная панель должна быть закреплена над нижней навигацией экрана «Внешний вид».

**Architecture:** Сохраняем существующую точку входа `_looksOpenFittingSheet()` и состояние `_looksTrial`. `_looksFabHtml()` становится семантически подписанным dock-action, а CSS связывает его с нижней навигацией через общие отступы, фон и безопасную зону; при наличии примерки показывается только компактный счётчик.

**Tech Stack:** vanilla JS classic script (`FastAPI/static/app.10.js`), CSS (`FastAPI/static/app.css`), Puppeteer и локальный preview-сервер.

## Global Constraints

- Не менять API примерочной, покупку или состояние `_looksTrial`.
- Панель видна только на экране «Внешний вид», закреплена выше `nav` и не перекрывает его.
- На 390 px остаётся один понятный CTA без горизонтального переполнения.
- Соблюдать `prefers-reduced-motion`; не добавлять новую обязательную анимацию.

---

### Task 1: Подписанная dock-панель примерочной

**Files:**
- Modify: `FastAPI/static/app.10.js`
- Modify: `FastAPI/static/app.css`
- Modify: `FastAPI/static/index.html`
- Modify: `FastAPI/static/app.01.js`
- Modify: `tools/verify_fitting_room.mjs`

**Interfaces:**
- Consumes: `_looksHeroSel()`, `_looksTrial`, `_looksOpenFittingSheet()`.
- Produces: `button.looks-fab` с доступным именем «Примерочная» и текстовой подписью, `span.looks-fab-badge` для количества примеряемых предметов.

- [ ] **Step 1: Дополнить failing UI-проверку dock-панели**

В `tools/verify_fitting_room.mjs` после проверки FAB добавить считывание геометрии:

```js
const dock = await page.evaluate(() => {
  const button = document.querySelector('.looks-fab');
  const nav = document.querySelector('nav');
  const label = button?.querySelector('.looks-fab-label');
  if (!button || !nav || !label) return null;
  const b = button.getBoundingClientRect();
  const n = nav.getBoundingClientRect();
  return { label: label.textContent.trim(), fixed: getComputedStyle(button).position === 'fixed', aboveNav: b.bottom <= n.top - 8 };
});
check('dock-панель существует', !!dock);
if (dock) {
  check('есть подпись «Примерочная»', dock.label === 'Примерочная');
  check('панель закреплена', dock.fixed);
  check('панель не перекрывает нижнюю навигацию', dock.aboveNav);
}
```

- [ ] **Step 2: Запустить проверку до реализации**

Run: `node tools/verify_fitting_room.mjs`

Expected: текущая среда может остановиться на запуске Chromium; на исправной машине новые проверки упадут из-за отсутствующего `.looks-fab-label`.

- [ ] **Step 3: Сделать разметку панели подписанной**

В `_looksFabHtml()` заменить содержимое кнопки на аватар, подпись и условный счётчик. Контейнер `#looks-dock` расположен в `index.html` рядом с `.nav`, вне `.page`: `.page.active` анимируется через `transform`, который создаёт для fixed-элементов неправильный containing block. В `switchPage()` очищать dock для любой страницы, кроме `looks`.

```js
return `<button class="looks-fab" onclick="_looksOpenFittingSheet()" aria-label="Примерочная">
  <span class="looks-fab-avatar"><div class="ava looks-fab-ava ${frame ? frame.css : ''} ${halo ? halo.css : ''}">${_looksData.vip ? '👑' : '🔮'}</div></span>
  <span class="looks-fab-label">Примерочная</span>
  ${hasTrial ? `<span class="looks-fab-badge">${Object.keys(_looksTrial).length}</span>` : ''}
</button>`;
```

- [ ] **Step 4: Стилизовать панель как продолжение нижней навигации**

Заменить круглый размер `.looks-fab` на компактную плашку с `position: fixed; right: 12px; bottom: calc(78px + var(--safe-b)); min-height: 44px;` и внутренним `display:flex`. Это оставляет 12 px до фактической верхней границы `.nav` на 390×844. Использовать `var(--bg2)`, `var(--border2)`, `var(--gold2)` и существующий радиус системы; счётчик оставить абсолютным на аватаре. Не вводить CSS-анимаций.

- [ ] **Step 5: Проверить реализацию**

Run: `node --check FastAPI/static/app.10.js && node --check tools/verify_fitting_room.mjs && git diff --check`

Expected: без вывода и без ошибок.

### Task 2: Живые свотчи только в области видимости

**Files:**
- Modify: `FastAPI/static/app.10.js`
- Modify: `FastAPI/static/app.css`
- Create: `tools/verify_live_swatch.mjs`

**Interfaces:**
- Consumes: `.looks-card[data-cos]` и `_looksRenderSectionGrid(slot)`.
- Produces: `_looksObserveSwatches(container)` и класс `.lc-sw-live` только на пересекающихся с viewport карточках.

- [ ] **Step 1: Добавить test-first сценарий**

`tools/verify_live_swatch.mjs` открывает локальный экран, переключает «По слотам» и проверяет: хотя бы одна видимая карточка имеет `.lc-sw-live`; её `animationName` не `none`.

- [ ] **Step 2: Включить `IntersectionObserver`**

Добавить `_looksObserveSwatches(container)` перед `_looksRenderSectionGrid`: наблюдатель с `rootMargin:'50px'`, `threshold:0.1` переключает `.lc-sw-live` по `entry.isIntersecting`. Вызвать после полной отрисовки `renderLooks()` и после точечной перерисовки секции.

- [ ] **Step 3: Сохранить безопасный статичный fallback в CSS**

Отключать анимации селектором `.looks-card:not(.lc-sw-live) …`, а не для всех `.lc-sw`; без JavaScript свотчи должны остаться статичными.

- [ ] **Step 4: Проверить**

Run: `node --check FastAPI/static/app.10.js && node --check tools/verify_live_swatch.mjs && node tools/verify_live_swatch.mjs`

Expected: синтаксические проверки проходят; Puppeteer заканчивается `ALL OK` на машине, где Chromium запускается.

### Task 3: Локальная визуальная и регрессионная проверка

**Files:**
- Verify: `tools/verify_fitting_room.mjs`, `tools/verify_live_swatch.mjs`, `tools/verify_slots_*.mjs`, `tools/verify_collections_*.mjs`, `tools/verify_collection_detail_*.mjs`, `tools/verify_looks_no_jump.mjs`

- [ ] **Step 1: Прогнать backend-проверки**

Run: `python tools/test_buy_many.py && python tools/test_buy_lineup.py && python -m py_compile services/cosmetics.py FastAPI/routers/cosmetics.py`

Expected: все сценарии `OK`, без ошибок компиляции.

- [ ] **Step 2: Проверить flow на локальном интерфейсе 390 px**

Открыть `http://localhost:8402/`, выбрать два незакупленных предмета из разных слотов, убедиться: dock всегда виден над навигацией, счётчик равен двум, шторка содержит два trial-чипа и одну золотую кнопку «Купить и применить всё».

- [ ] **Step 3: Запустить полный набор браузерных тестов**

Run: `Get-ChildItem tools/verify_slots_*.mjs,tools/verify_collections_*.mjs,tools/verify_collection_detail_*.mjs,tools/verify_looks_no_jump.mjs,tools/verify_fitting_room.mjs,tools/verify_live_swatch.mjs | ForEach-Object { node $_.FullName }`

Expected: каждый завершается `ALL OK` на машине с запускающимся Chromium; отдельно зафиксировать внешнюю проблему запуска, если она воспроизводится до загрузки страницы.
