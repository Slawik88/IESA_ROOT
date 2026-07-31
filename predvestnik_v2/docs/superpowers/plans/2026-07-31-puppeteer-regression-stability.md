# Стабильность Puppeteer-регрессии Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать ложные падения `verify_looks_no_jump.mjs` в длинной последовательности UI-тестов, не ослабляя проверку геометрии переключателя.

**Architecture:** Тест сейчас сравнивает `getBoundingClientRect().y` строгим `===` после фиксированной задержки 300 ms. На 2026-07-31 он трижды прошёл в изоляции, но дважды падал после длинной серии, что указывает на гонку кадра/шрифтов, а не на реальное смещение. Нужна синхронизация по двум animation frame и сравнение с допуском менее одного CSS-пикселя.

**Tech Stack:** Puppeteer, `tools/verify_looks_no_jump.mjs`, локальный preview-сервер на 8402.

## Global Constraints

- Не менять реализацию вкладки «Внешний вид» ради тестовой нестабильности без подтверждённого визуального дефекта.
- Сохранить проверку реального клика по карточке второй строки и отсутствие фильтра в режиме коллекций.
- Новый тест должен проходить пять запусков подряд после полного набора косметических UI-тестов.

---

### Task 1: Зафиксировать готовую геометрию перед измерением

**Files:**
- Modify: `tools/verify_looks_no_jump.mjs`

- [x] **Step 1: Заменить таймауты после переключения режима на ожидание кадров**

Добавить helper и вызывать его после каждого `page.click('[data-mode=…]')`:

```js
async function settledFrame(page) {
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}
```

- [x] **Step 2: Проверять координату с субпиксельным допуском**

Заменить строгие сравнения на:

```js
const sameY = (a, b) => Math.abs(a - b) < 0.5;
check('переключатель не сдвигается при переходе в «По слотам»', sameY(toggleYBefore, toggleYAfterSlots));
check('переключатель не сдвигается при возврате в «По коллекциям»', sameY(toggleYBefore, toggleYAfterBack));
```

- [x] **Step 3: Подтвердить устойчивость**

Run: `1..5 | ForEach-Object { node tools/verify_looks_no_jump.mjs }`

Expected: все пять запусков завершаются `ALL OK`, а изменение CSS, которое действительно сдвигает переключатель более чем на 0.5 px, по-прежнему делает тест красным.
