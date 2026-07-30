# Косметика «Внешний вид» — Стадия 3: детальный экран коллекции Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить сегодняшний «мост» (тап по карточке коллекции → просто переключает в режим «По слотам» с фильтром) на полноценный детальный экран открытой коллекции: алтарная шапка с медальоном/атмосферой/сегментным измерителем + реальная кнопка «Купить всё недостающее» (массовая покупка всех недостающих предметов линейки одной транзакцией).

**Architecture:** Бэкенд — новая функция `buy_lineup()` в `services/cosmetics.py` (мирроит `buy_bundle()` из `FastAPI/routers/showcase.py`, но без скидки комплекта — у линейки уже единая фиксированная цена/предмет) + тонкий роутер-эндпоинт `POST /cosmetics/buy-lineup`. Фронтенд — чистый рефакторинг `FastAPI/static/app.10.js` (classic script) + `app.css`: новое состояние `_looksDetailLineup`, новая функция шапки, и **переиспользование БЕЗ ИЗМЕНЕНИЙ** уже существующих `_looksSectionHtml()`/`_looksGridHtml()`/`_looksCard()` (Стадия 1) для сетки 6 плиток по слотам — весь механизм «тап → инлайн примерка/покупка» уже реализован и проверен, здесь просто накрывается новой шапкой вместо перехода в режим «По слотам».

**Tech Stack:** FastAPI + asyncpg/PGAdapter (бэкенд), vanilla JS classic script + CSS (фронт), Puppeteer (`tools/verify_*.mjs`) для UI-тестов, `tools/preview_server.mjs` для локального стенда без БД.

## Global Constraints

- PostgreSQL плейсхолдеры: писать `?`, PGAdapter сам конвертирует в `$1,$2...` — НЕ писать `$1` вручную.
- `services/` не импортирует `bot.*`/`FastAPI.*` — вся бизнес-логика в `services/cosmetics.py`, роутер только тонкая обвязка (`HTTPException` + `db.commit()`).
- Новые CSS-классы детального экрана коллекции — префикс `.coll-` (НЕ `.lc-`, тот занят карточками отдельных предметов, см. `docs/superpowers/plans/2026-07-30-cosmetics-collections-mode.md`).
- Любая новая CSS-анимация ОБЯЗАНА гаситься и под `body.no-fx`, и под `@media (prefers-reduced-motion: reduce)` — парный паттерн, см. `app.css:3464-3492`.
- `animation: none` замораживает элемент на его СТАТИЧНОЙ (не-transform/не-keyframe) позиции/прозрачности, НЕ на визуально приятном кадре анимации — это уже ловилось в финальном ревью Стадии 2 (см. `.superpowers/sdd/progress.md`, находка I3: heat-glow превращался в сплошное пятно, снежинки обрезались `overflow:hidden`, т.к. их статичная позиция была ЗА пределами контейнера). Любой новый декоративный узел с `animation` обязан иметь осмысленную статичную позицию/прозрачность САМ ПО СЕБЕ, без учёта анимации.
- НЕ толстая цветная полоса сбоку карточки/экрана, НЕ бегущий диагональный блик по всей поверхности, НЕ `rotate()+translate()+rotate(-...)` для орбит — см. `COSMETICS_COLLECTION_DESIGN_RULES.md` §4.
- Цена — всегда с единицей (`"N✨/предмет"`), статус — честный текст, НИКОГДА `"✓ надето"` на уровне коллекции — см. `COSMETICS_COLLECTION_DESIGN_RULES.md` §5.
- `node --check FastAPI/static/app.10.js` после любой правки JS; `python -m py_compile services/cosmetics.py FastAPI/routers/cosmetics.py` после правки бэка.
- Локальный стенд: `node tools/preview_server.mjs` (порт 8402, дефолт) для puppeteer-тестов; параллельно может быть открыт ручной экземпляр на другом порту (`PORT=63768 node tools/preview_server.mjs`) для визуального просмотра — оба читают один и тот же `FastAPI/static/`.

---

### Task 1: Backend — `lineup_buy_quote()` + `buy_lineup()`

**Files:**
- Modify: `predvestnik_v2/services/cosmetics.py` (добавить импорт `lineup_items`, добавить 2 функции после `buy()`, т.е. после строки 363)
- Test: `predvestnik_v2/tools/test_buy_lineup.py` (новый)

**Interfaces:**
- Consumes: `LINEUPS`, `COSMETICS` (`core/cosmetics.py`, уже импортированы), `lineup_items(lineup_id) -> dict[str,dict]` (`core/cosmetics.py:107`, НЕ импортирован пока — добавить в импорт), `_owned(db, user_id) -> set[str]` (уже в файле, строка 131), `increment_metric(db, user_id, metric_name, delta) -> list` (`services/achievements.py`).
- Produces: `lineup_buy_quote(lineup_id: str, owned: set[str]) -> dict | None` (`{"missing": list[str], "unit_price": int, "total": int}` либо `None`), `buy_lineup(db, user_id: int, lineup_id: str) -> tuple[bool, str]` — используются в Task 2 (роутер) и Task 3 (фронт вызывает эндпоинт, не эту функцию напрямую).

- [ ] **Step 1: Написать падающий тест**

Создать `predvestnik_v2/tools/test_buy_lineup.py`:

```python
"""Стадия 3 косметики: «Купить всё недостающее» — массовая покупка недостающих
предметов линейки одной транзакцией, цена = кол-во недостающих × цена линейки
(core/cosmetics.py::LINEUPS — единая фиксированная цена за предмет в рамках
линейки). Мирроит buy_bundle() (routers/showcase.py) для витрины недели, но без
скидки комплекта — она там из-за поштучных цен, здесь цена и так одна на всех."""
import sys
import pathlib
import asyncio

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.cosmetics import lineup_items
from services.cosmetics import lineup_buy_quote, buy_lineup

# ── lineup_buy_quote(): чистая функция, реальный каталог, без БД ────────────
assert lineup_buy_quote("no_such_lineup", set()) is None, "неизвестная линейка → None"

forest_ids = set(lineup_items("forest"))
assert len(forest_ids) >= 2, "линейка 'forest' должна содержать несколько предметов"

q_none_owned = lineup_buy_quote("forest", set())
assert q_none_owned is not None
assert set(q_none_owned["missing"]) == forest_ids
assert q_none_owned["unit_price"] == 250
assert q_none_owned["total"] == 250 * len(forest_ids)

q_all_owned = lineup_buy_quote("forest", forest_ids)
assert q_all_owned is None, "вся линейка уже куплена → None (нечего докупать)"

one_owned = {next(iter(forest_ids))}
q_partial = lineup_buy_quote("forest", one_owned)
assert q_partial is not None
assert len(q_partial["missing"]) == len(forest_ids) - 1
assert q_partial["total"] == 250 * (len(forest_ids) - 1)

print("OK: lineup_buy_quote — None на неизвестной/полностью собранной линейке, "
      "верная раскладка missing×цена на частично собранной")


# ── buy_lineup(): транзакция, нехватка/достаток баланса ─────────────────────
class FakeCursor:
    def __init__(self, row=None):
        self._row = row

    async def fetchone(self):
        return self._row

    def __await__(self):
        async def _self():
            return self
        return _self().__await__()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _NoopTx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeConnection:
    def transaction(self):
        return _NoopTx()


class FakeDB:
    """execute() синхронный (не async def) — как реальный PGAdapter, курсор
    одновременно awaitable И async context manager (buy_lineup использует оба
    стиля: `await db.execute(...)` для UPDATE/INSERT, `async with db.execute(...)
    as c:` для SELECT ... FOR UPDATE — см. services/cosmetics.py::buy())."""

    def __init__(self, balance):
        self.connection = FakeConnection()
        self.executed = []
        self.balance = balance

    def execute(self, sql, args=()):
        self.executed.append((sql.strip(), tuple(args)))
        if "SELECT COALESCE(user_balance_zarniki" in sql:
            return FakeCursor((self.balance,))
        return FakeCursor(None)

    async def commit(self):
        pass


async def main():
    total_needed = 250 * len(forest_ids)

    # Недостаточно баланса — без единого UPDATE/INSERT (пока никаких списаний)
    db_poor = FakeDB(balance=total_needed - 1)
    ok, msg = await buy_lineup(db_poor, 555, "forest")
    assert ok is False, "должно отказать при нехватке баланса"
    assert "Нужно" in msg
    assert not any(sql.startswith("UPDATE users") for sql, _ in db_poor.executed), \
        "баланс не должен списываться при отказе"
    assert not any(sql.startswith("INSERT INTO user_cosmetics") for sql, _ in db_poor.executed), \
        "предметы не должны выдаваться при отказе"

    # Хватает баланса — ровно 1 UPDATE + по 1 INSERT на каждый недостающий предмет
    db_rich = FakeDB(balance=total_needed)
    ok, msg = await buy_lineup(db_rich, 777, "forest")
    assert ok is True, f"должно пройти при достаточном балансе: {msg}"
    updates = [a for sql, a in db_rich.executed if sql.startswith("UPDATE users")]
    inserts = [a for sql, a in db_rich.executed if sql.startswith("INSERT INTO user_cosmetics")]
    assert len(updates) == 1, f"ожидался 1 UPDATE баланса, получено {len(updates)}"
    assert updates[0][0] == total_needed, f"списано {updates[0][0]}, ожидалось {total_needed}"
    assert len(inserts) == len(forest_ids), \
        f"ожидалось {len(forest_ids)} INSERT (по одному на предмет), получено {len(inserts)}"
    assert str(len(forest_ids)) in msg and str(total_needed) in msg

    print("OK: buy_lineup — отказ без побочных эффектов при нехватке баланса; "
          "при достатке — 1 списание + по 1 выдаче на каждый недостающий предмет, "
          "сообщение содержит количество и сумму")


asyncio.run(main())
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python tools/test_buy_lineup.py`
Expected: `ImportError: cannot import name 'lineup_buy_quote' from 'services.cosmetics'`

- [ ] **Step 3: Реализовать `lineup_buy_quote()` и `buy_lineup()`**

В `predvestnik_v2/services/cosmetics.py` изменить импорт на строке 9-11:

```python
from core.cosmetics import (
    COSMETICS, COSMETIC_SLOTS, LINEUPS, WELCOME_ANIMATIONS, WELCOME_DEFAULT, is_vip_locked,
    lineup_items,
)
```

Добавить после конца функции `buy()` (после строки 363, `return True, msg`, перед `async def get_active_cosmetics`):

```python
def lineup_buy_quote(lineup_id: str, owned: set[str]) -> dict | None:
    """Раскладка покупки «всё недостающее» для линейки (Стадия 3 косметики):
    {"missing": [id,...], "unit_price": int, "total": int}. None если линейки
    нет, она не продаётся за зарники, либо уже полностью собрана — во всех
    трёх случаях покупать нечего/некорректно."""
    meta = LINEUPS.get(lineup_id)
    if not meta:
        return None
    price_opt = (meta.get("price") or [None])[0]
    if not price_opt or "zarniki" not in price_opt:
        return None
    missing = [cid for cid in lineup_items(lineup_id) if cid not in owned]
    if not missing:
        return None
    unit = int(price_opt["zarniki"])
    return {"missing": missing, "unit_price": unit, "total": unit * len(missing)}


async def buy_lineup(db, user_id: int, lineup_id: str) -> tuple[bool, str]:
    """Купить ВСЕ недостающие предметы линейки одной транзакцией («Купить всё
    недостающее», Стадия 3 редизайна «Внешний вид»). Мирроит buy_bundle()
    (FastAPI/routers/showcase.py, витрина недели) — тот же паттерн SELECT ...
    FOR UPDATE + одно списание + N выдач в одной транзакции — но без скидки
    комплекта: у линейки и так единая фиксированная цена за предмет."""
    owned = await _owned(db, user_id)
    quote = lineup_buy_quote(lineup_id, owned)
    if not quote:
        return False, "Эта линейка уже собрана полностью или недоступна для покупки."
    missing, total = quote["missing"], quote["total"]

    async with db.connection.transaction():
        async with db.execute(
            "SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id = ? FOR UPDATE",
            (user_id,)
        ) as c:
            row = await c.fetchone()
        bal = float(row[0]) if row else 0.0
        if bal < total:
            return False, f"Нужно {total}✨ за всю линейку (у тебя {int(bal)})."
        await db.execute(
            "UPDATE users SET user_balance_zarniki = user_balance_zarniki - ? WHERE user_tg_id = ?",
            (total, user_id))
        for cid in missing:
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING", (user_id, cid))

    # Ачивка «Модник» — считаем ВСЕ докупленные предметы, не только 1 (buy() делает
    # то же самое при одиночной покупке). Вне транзакции — increment_metric коммитит сам.
    try:
        from services.achievements import increment_metric
        await increment_metric(db, user_id, "cosmetics_bought", delta=float(len(missing)))
        await db.commit()
    except Exception:
        pass

    meta = LINEUPS[lineup_id]
    return True, f"🎨 «{meta['name']}» собрана полностью! Докуплено {len(missing)} шт. за {total}✨"
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python tools/test_buy_lineup.py`
Expected:
```
OK: lineup_buy_quote — None на неизвестной/полностью собранной линейке, верная раскладка missing×цена на частично собранной
OK: buy_lineup — отказ без побочных эффектов при нехватке баланса; при достатке — 1 списание + по 1 выдаче на каждый недостающий предмет, сообщение содержит количество и сумму
```

- [ ] **Step 5: `py_compile` + commit**

Run: `python -m py_compile predvestnik_v2/services/cosmetics.py`
Expected: без вывода (успех)

```bash
git add predvestnik_v2/services/cosmetics.py predvestnik_v2/tools/test_buy_lineup.py
git commit -m "feat(cosmetics): buy_lineup() — массовая покупка недостающих предметов линейки (Стадия 3, бэкенд)"
```

---

### Task 2: Backend — эндпоинт `POST /cosmetics/buy-lineup`

**Files:**
- Modify: `predvestnik_v2/FastAPI/routers/cosmetics.py`

**Interfaces:**
- Consumes: `buy_lineup(db, user_id, lineup_id) -> tuple[bool,str]` (Task 1).
- Produces: `POST /cosmetics/buy-lineup` принимает `{"lineup": str}`, возвращает `{"ok": true, "message": str}` либо HTTP 400 — используется фронтом в Task 3 (`_looksBuyLineup()`).

- [ ] **Step 1: Добавить импорт и эндпоинт**

В `predvestnik_v2/FastAPI/routers/cosmetics.py` изменить импорт на строках 13-18:

```python
from services.cosmetics import (
    buy, equip, get_catalog, set_welcome, unequip,
    chest_catalog, open_chest, craft_catalog, craft_cosmetic,
    giftable_cosmetics, gift_cosmetic, buy_chest,
    list_presets, save_preset, apply_preset, delete_preset,
    buy_lineup,
)
```

Добавить сразу после `cosmetics_buy` (после строки 59, `return {"ok": True, "message": msg}`, перед `class EquipRequest`):

```python
class BuyLineupRequest(BaseModel):
    lineup: str


@router.post("/buy-lineup")
async def cosmetics_buy_lineup(body: BuyLineupRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await buy_lineup(db, user["id"], body.lineup)
    if not ok:
        raise HTTPException(400, msg)
    await db.commit()
    return {"ok": True, "message": msg}
```

- [ ] **Step 2: `py_compile` + smoke-импорт**

Run: `python -m py_compile predvestnik_v2/FastAPI/routers/cosmetics.py`
Expected: без вывода

Run: `python -c "import sys; sys.path.insert(0,'predvestnik_v2'); from FastAPI.routers.cosmetics import router; print([r.path for r in router.routes if 'buy-lineup' in r.path])"`
Expected: `['/cosmetics/buy-lineup']`

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/FastAPI/routers/cosmetics.py
git commit -m "feat(cosmetics): POST /cosmetics/buy-lineup — эндпоинт массовой покупки линейки"
```

---

### Task 3: Frontend — детальный экран (навигация + шапка + сегментный измеритель + кнопка покупки)

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js`
- Modify: `predvestnik_v2/FastAPI/static/app.css`
- Modify: `predvestnik_v2/tools/preview_server.mjs` (мок нового эндпоинта — иначе кнопка «Купить всё» будет падать в `unknown-api.log` при ручном клике в превью)
- Test: `predvestnik_v2/tools/verify_collection_detail_header.mjs` (новый)

**Interfaces:**
- Consumes: `_looksLineupStats(lin)` (уже существует, `app.10.js:107`, даёт `{owned,total,slotOwned}`), `lineupMeta(lin)`, `LINEUP_COLOR`, `_looksCollectionIconSvg(lin)` (уже существует), `esc()`/`el()`/`api()`/`toast()`/`refreshCurrBar()` (глобальные хелперы проекта), `_looksSectionHtml(slot)`/`_looksGridHtml(slot)` (уже существуют, Стадия 1 — переиспользуются БЕЗ ИЗМЕНЕНИЙ).
- Produces: `_looksDetailLineup` (module-level, `string|null`), `_looksOpenCollection(lin)` (переписана), `_looksCloseCollection()` (новая), `_looksCollectionDetailHeaderHtml(lin)`, `_looksCollectionDetailBodyHtml()`, `_looksBuyLineup(lin)` — используются в Task 4 (`_looksCollectionAtmosphereHtml` встраивается в шапку) и Task 5 (обновлённый тест навигации).

- [ ] **Step 1: Состояние + навигация — заменить `_looksOpenCollection`, добавить `_looksCloseCollection`**

В `app.10.js` добавить новую переменную сразу после строки 13 (`let _looksMode='collections';`):

```js
let _looksDetailLineup=null;   // id открытой коллекции в детальном экране (Стадия 3); null = список карточек
```

В `openLooksModal()` (строка 32) добавить сброс — заменить:
```js
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksFocus=null;
```
на:
```js
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksFocus=null; _looksDetailLineup=null;
```

Заменить весь блок строк 289-298 (комментарий + `function _looksOpenCollection`) на:

```js
// Тап по карточке коллекции: открывает детальный экран (Стадия 3) — алтарная
// шапка (медальон крупнее/блёрб/сегментный измеритель/атмосфера линейки) +
// кнопка «Купить всё недостающее» + все 6 секций слотов (переиспользованы БЕЗ
// изменений из Стадии 1 — они уже фильтруются по _looksFilter=lin).
function _looksOpenCollection(lin){
  _looksSearch=''; _looksStatus='all'; _looksFilter=lin; _looksDetailLineup=lin;
  renderLooks();
}
function _looksCloseCollection(){
  _looksDetailLineup=null; _looksFilter='all';
  renderLooks();
}
```

- [ ] **Step 2: Ветвление в `_looksCollectionsViewHtml()` + скрыть переключатель режимов внутри детального экрана**

Заменить блок строк 145-148:
```js
function _looksCollectionsViewHtml(){
  const lineups=Object.keys(_looksData.lineups||{});
  return `<div class="coll-grid">${lineups.map(_looksCollectionCard).join('')}</div>`;
}
```
на:
```js
function _looksCollectionsViewHtml(){
  if(_looksDetailLineup) return _looksCollectionDetailHeaderHtml(_looksDetailLineup)+_looksCollectionDetailBodyHtml();
  const lineups=Object.keys(_looksData.lineups||{});
  return `<div class="coll-grid">${lineups.map(_looksCollectionCard).join('')}</div>`;
}
// Детальный экран: все 6 секций слотов, переиспользованы БЕЗ ИЗМЕНЕНИЙ из режима
// «По слотам» (Стадия 1) — уже читают _looksFilter (=lin, выставлен в
// _looksOpenCollection) и рендерят реальные карточки предметов с тем же
// инлайн-примеркой+покупкой, что и everywhere else в конструкторе. Якорь-чипы
// (.looks-anchors) намеренно не рендерим — 6 секций одной линейки короткие,
// прыгать некуда.
function _looksCollectionDetailBodyHtml(){
  return `<div id="looks-sections">${_LOOKS_SLOTS.map(_looksSectionHtml).join('')}</div>`;
}
```

В `renderLooks()` (строки 69-97) заменить:
```js
  const modeBody=_looksMode==='collections'?_looksCollectionsViewHtml():_looksSlotsViewHtml();
```
оставить как есть (не трогать — уже правильно вызывает `_looksCollectionsViewHtml`), но заменить строку с `${_looksModeToggleHtml()}`:
```js
    <div class="looks-sticky"><div id="looks-top">${_looksPreviewHtml()}</div>${stickyFilterBar}</div>
    ${_looksModeToggleHtml()}`
```
на:
```js
    <div class="looks-sticky"><div id="looks-top">${_looksPreviewHtml()}</div>${stickyFilterBar}</div>
    ${_looksDetailLineup?'':_looksModeToggleHtml()}`
```

- [ ] **Step 3: Компонент шапки + кнопка «Купить всё недостающее»**

Добавить после `_looksCloseCollection()` (конец блока из Step 1):

```js
// Алтарная шапка открытой коллекции (Стадия 3) — см. COSMETICS_COLLECTION_DESIGN_RULES.md §6:
// медальон крупнее (74px+), сегментный измеритель (N делений = N предметов
// линейки, не гладкий %), явная кнопка «Купить всё недостающее» — реальная
// транзакция, НЕ побочный эффект тапа по карточке/плитке.
function _looksCollectionDetailHeaderHtml(lin){
  const meta=lineupMeta(lin); if(!meta) return '';
  const stats=_looksLineupStats(lin);
  const c=LINEUP_COLOR[lin]||'#9aa7b8';
  const missing=stats.total-stats.owned;
  const unit=(meta.price&&meta.price[0]&&meta.price[0].zarniki)||0;
  const total=missing*unit;
  const bal=(_looksData.balances||{}).zarniki||0;
  const can=missing>0&&bal>=total;
  const notches=Array.from({length:stats.total},(_,i)=>`<div class="coll-meter-notch${i<stats.owned?' on':''}"></div>`).join('');
  const action = missing===0
    ? `<div class="coll-detail-done">✓ Коллекция собрана полностью</div>`
    : `<button class="btn btn-sm ${can?'btn-gold':'btn-ghost'} btn-full" ${can?'':'disabled'} onclick="_looksBuyLineup('${lin}')">${can?`✨ Купить всё недостающее — ${total}✨ (${missing}×${unit}✨)`:`🚫 Нужно ${total}✨ (есть ${Math.floor(bal)})`}</button>`;
  return `<div class="coll-detail-head" style="--c:${c};--cb:${c}4d;--cg:${c}1f">
    <button class="coll-detail-back" onclick="_looksCloseCollection()" aria-label="Назад к коллекциям">‹</button>
    <div class="coll-detail-atmo">${_looksCollectionAtmosphereHtml(lin)}</div>
    <div class="coll-detail-sig" style="--c:${c}">${_looksCollectionIconSvg(lin)}</div>
    <div class="coll-detail-name">${esc(meta.name)}</div>
    <div class="coll-detail-blurb">${esc(meta.blurb||'')}</div>
    <div class="coll-meter">${notches}</div>
    <div class="coll-meter-caption"><span>${stats.owned} из ${stats.total} собрано</span><span>${missing>0?`${missing} не куплено · ${unit}✨/предмет`:''}</span></div>
    ${action}
  </div>`;
}
function _looksBuyLineup(lin){
  api('/cosmetics/buy-lineup',{method:'POST',body:JSON.stringify({lineup:lin})})
    .then(r=>{toast(r.message); refreshCurrBar(); return api('/cosmetics/');})
    .then(d=>{_looksData=d; _looksSaved=_looksEquipped(d); _looksSel={..._looksSaved};
      const body=el('looks-mode-body'); if(body) body.innerHTML=_looksCollectionsViewHtml();})
    .catch(e=>toast(e,false));
}
```

`_looksCollectionAtmosphereHtml(lin)` ещё не существует — добавляется в Task 4. На этом шаге временно добавить прямо здесь заглушку-однострочник, которую Task 4 заменит полностью (не оставлять как есть после Task 4 — тест Task 4 обязан проверить, что заглушка исчезла):

```js
function _looksCollectionAtmosphereHtml(lin){ return ''; }   // Task 4 заменит на реальную атмосферу
```

- [ ] **Step 4: CSS — шапка, медальон, измеритель**

В `app.css` добавить сразу после строки 3342 (`.coll-slot.on { ... }`):

```css

/* Стадия 3 (2026-07-30): алтарная шапка открытой коллекции — медальон крупнее,
   сегментный измеритель, кнопка «Купить всё недостающее». См.
   COSMETICS_COLLECTION_DESIGN_RULES.md §6. */
.coll-detail-head { position: relative; overflow: hidden; border-radius: 16px;
  padding: 22px 14px 16px; margin-bottom: 14px; text-align: center;
  background: linear-gradient(180deg, var(--bg2), var(--bg3));
  border: 1px solid var(--cb); }
.coll-detail-head::before { content: ''; position: absolute; inset: 0;
  background: radial-gradient(circle at 50% 0%, var(--cg), transparent 60%); }
.coll-detail-head::after { content: ''; position: absolute; inset: 0; border-radius: 16px;
  box-shadow: inset 0 0 26px rgba(0,0,0,.55); pointer-events: none; }
.coll-detail-back { position: absolute; top: 8px; left: 8px; z-index: 3; width: 30px; height: 30px;
  border-radius: 50%; border: none; background: rgba(0,0,0,.35); color: var(--bright);
  font-size: 18px; line-height: 1; cursor: pointer; }
.coll-detail-atmo { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 0; }
.coll-detail-sig { position: relative; z-index: 1; width: 76px; height: 76px; margin: 4px auto 10px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.coll-detail-sig::before { content: ''; position: absolute; inset: 0; border-radius: 50%;
  background: radial-gradient(circle at 35% 30%, #232739, #0e1019 75%);
  box-shadow: inset 0 3px 10px rgba(0,0,0,.55); }
.coll-detail-sig::after { content: ''; position: absolute; inset: 0; border-radius: 50%;
  border: 1px solid var(--c); opacity: .5; }
.coll-detail-sig .coll-sig-svg { position: relative; width: 38px; height: 38px;
  filter: drop-shadow(0 0 8px var(--c)); }
.coll-detail-name { position: relative; z-index: 1; color: var(--bright); font-weight: 700; font-size: 16px; }
.coll-detail-blurb { position: relative; z-index: 1; color: var(--muted); font-size: 11px;
  margin: 4px auto 14px; max-width: 280px; line-height: 1.4; }
.coll-meter { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 3px;
  justify-content: center; max-width: 280px; margin: 0 auto; }
.coll-meter-notch { width: 14px; height: 6px; border-radius: 2px; background: var(--dim); }
.coll-meter-notch.on { background: linear-gradient(180deg, var(--gold2), var(--gold));
  box-shadow: 0 0 5px var(--gold2); animation: collMeterPulse 2.6s ease-in-out infinite; }
.coll-meter-caption { position: relative; z-index: 1; display: flex; justify-content: space-between;
  font-size: 10px; color: var(--muted); margin: 8px auto 12px; max-width: 280px; }
.coll-detail-done { position: relative; z-index: 1; color: #56c46a; font-weight: 700; font-size: 12px;
  background: rgba(86,196,106,.13); border-radius: 8px; padding: 8px; }
@keyframes collMeterPulse { 0%,100%{box-shadow:0 0 5px var(--gold2)} 50%{box-shadow:0 0 10px var(--gold)} }
```

Добавить в конец файла (после строки 3492, существующего блока `.coll-card` no-fx):

```css

/* Стадия 3 (2026-07-30): та же пара no-fx/prefers-reduced-motion для шапки
   детального экрана (см. правило в комментарии над блоком .coll-card выше). */
body.no-fx .coll-meter-notch.on { animation: none !important; box-shadow: 0 0 5px var(--gold2); }
@media (prefers-reduced-motion: reduce) {
  .coll-meter-notch.on { animation: none !important; box-shadow: 0 0 5px var(--gold2); }
}
```

- [ ] **Step 5: Мок нового эндпоинта в preview_server.mjs**

В `predvestnik_v2/tools/preview_server.mjs` добавить сразу после строки `'POST /cosmetics/craft': { message: '✅ Скрафчено!' },`:

```js
  'POST /cosmetics/buy-lineup': { ok: true, message: '🎨 Линейка собрана полностью! Докуплено — за ✨' },
```

- [ ] **Step 6: `node --check` + запустить preview + написать и прогнать puppeteer-тест шапки**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

Run (в отдельном терминале, оставить работать): `node predvestnik_v2/tools/preview_server.mjs`
Expected: `preview on http://localhost:8402/`

Создать `predvestnik_v2/tools/verify_collection_detail_header.mjs`:

```js
// Детальный экран коллекции (Стадия 3): шапка, сегментный измеритель, кнопка
// «Купить всё недостающее» — 3 сценария на реальных данных мока preview_server.mjs:
// forest (1 предмет, уже владеет → «собрано»), threshold (2 предмета, 0 owned,
// цена 440 → 880 ≤ баланс 1250 → кнопка активна), artifact (1 предмет, 0 owned,
// цена 1500 > баланс 1250 → кнопка заблокирована).
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

async function openAndRead(lin) {
  await page.evaluate((l) => _looksOpenCollection(l), lin);
  await new Promise(r => setTimeout(r, 300));
  return page.evaluate(() => ({
    hasHead: !!document.querySelector('.coll-detail-head'),
    hasToggle: !!document.getElementById('looks-mode-toggle'),
    notches: document.querySelectorAll('.coll-meter-notch').length,
    onNotches: document.querySelectorAll('.coll-meter-notch.on').length,
    doneText: (document.querySelector('.coll-detail-done') || {}).textContent || null,
    btn: document.querySelector('.coll-detail-head button.btn-gold, .coll-detail-head button.btn-ghost'),
    btnText: (document.querySelector('.coll-detail-head button.btn-gold, .coll-detail-head button.btn-ghost') || {}).textContent || null,
    btnDisabled: (document.querySelector('.coll-detail-head button.btn-gold, .coll-detail-head button.btn-ghost') || {}).disabled,
    sectionsCount: document.querySelectorAll('#looks-sections .looks-section').length,
  }));
}

const forest = await openAndRead('forest');
check('шапка детального экрана отрендерена (forest)', forest.hasHead);
check('переключатель режимов скрыт внутри детального экрана', !forest.hasToggle);
check('forest: 1 деление, 1 горит (мок владеет единственным предметом)', forest.notches === 1 && forest.onNotches === 1);
check('forest: показан статус "собрано", кнопки покупки нет', /собрана полностью/.test(forest.doneText || '') && !forest.btn);
check('6 секций слотов отрендерены под шапкой', forest.sectionsCount === 6);

const threshold = await openAndRead('threshold');
check('threshold: 2 деления, 0 горит', threshold.notches === 2 && threshold.onNotches === 0);
check('threshold: кнопка активна (880✨ ≤ баланс 1250✨)', threshold.btn && !threshold.btnDisabled);
check('threshold: текст кнопки содержит раскладку 2×440', /880.*2.*440|2.*440.*880/.test((threshold.btnText||'').replace(/✨/g,'')));

const artifact = await openAndRead('artifact');
check('artifact: кнопка заблокирована (1500✨ > баланс 1250✨)', artifact.btn && artifact.btnDisabled);
check('artifact: текст кнопки — "Нужно"', /Нужно/.test(artifact.btnText || ''));

// Назад — детальный экран закрывается, переключатель режимов возвращается
await page.click('.coll-detail-back');
await new Promise(r => setTimeout(r, 300));
const back = await page.evaluate(() => ({
  detailGone: !document.querySelector('.coll-detail-head'),
  toggleBack: !!document.getElementById('looks-mode-toggle'),
  cardCount: document.querySelectorAll('.coll-card').length,
}));
check('кнопка "‹ Назад" закрывает детальный экран', back.detailGone);
check('переключатель режимов снова виден', back.toggleBack);
check('карточки коллекций снова на экране', back.cardCount === 7);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

Run: `node predvestnik_v2/tools/verify_collection_detail_header.mjs`
Expected: `ALL OK`

- [ ] **Step 7: Ручная визуальная проверка на реальном стенде**

В браузере (или через уже поднятый на 63768 стенд из предыдущего шага сессии) открыть «Внешний вид» → «По коллекциям» → тап по любой карточке. Проверить глазами: шапка не наезжает на секции ниже, кнопка «‹» кликабельна и не перекрыта, кнопка покупки не разъезжается на 390px (мобильная ширина). Если шапка «плавает» по высоте и уезжает под sticky-превью — тот же класс бага, что был у фильтр-бара (Стадия 1/2, см. `_looksSyncStickyH()`); при необходимости вызвать `_looksSyncStickyH()` из `_looksOpenCollection()`/`_looksCloseCollection()`.

- [ ] **Step 8: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/preview_server.mjs predvestnik_v2/tools/verify_collection_detail_header.mjs
git commit -m "feat(cosmetics): детальный экран коллекции — алтарная шапка+сегментный измеритель+«Купить всё недостающее» (Стадия 3, фронт)"
```

---

### Task 4: Frontend — атмосфера линейки в шапке (7 вариантов)

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js` (заменить заглушку `_looksCollectionAtmosphereHtml` из Task 3)
- Modify: `predvestnik_v2/FastAPI/static/app.css` (no-fx/reduced-motion для новых узлов)
- Test: `predvestnik_v2/tools/verify_collection_detail_atmo.mjs` (новый)

**Interfaces:**
- Consumes: существующие keyframes `fireflyDrift`, `portalTravel`, `snowFall`, `heatGlow`, `emberRise`, `starSpin`, `voidSpark`, `gemShimmer` (все уже определены в `app.css:3305-3322`, см. правило §6 design rules: «тот же тип, что у иконки, но крупнее и медленнее» — НЕ новые keyframes).
- Produces: `_looksCollectionAtmosphereHtml(lin)` (полная реализация, заменяет заглушку из Task 3) — используется только из `_looksCollectionDetailHeaderHtml` (Task 3), других потребителей нет.

- [ ] **Step 1: Заменить заглушку на реальную атмосферу по 7 линейкам**

В `app.10.js` заменить:
```js
function _looksCollectionAtmosphereHtml(lin){ return ''; }   // Task 4 заменит на реальную атмосферу
```
на:
```js
// Фоновая атмосфера шапки детального экрана (Стадия 3) — 2-3 крупные МЕДЛЕННЫЕ
// малозаметные частицы в духе линейки, см. COSMETICS_COLLECTION_DESIGN_RULES.md
// §6: «тот же тип, что у иконки (_looksCollectionIconSvg), но крупнее и
// медленнее — это фон всего экрана, не деталь 56px иконки». Переиспользует
// СУЩЕСТВУЮЩИЕ keyframes иконок (app.css) с более долгой длительностью —
// не изобретает новые анимации.
function _looksCollectionAtmosphereHtml(lin){
  switch(lin){
    case 'forest': return `
      <div style="position:absolute;width:5px;height:5px;border-radius:50%;background:#e8ffb0;left:20%;top:65%;animation:fireflyDrift 7s ease-in-out infinite"></div>
      <div style="position:absolute;width:4px;height:4px;border-radius:50%;background:#e8ffb0;left:75%;top:30%;animation:fireflyDrift 8.5s ease-in-out infinite 2s"></div>`;
    case 'threshold': return `
      <div style="position:absolute;left:30%;top:0;width:40%;height:60%;background:linear-gradient(180deg, rgba(224,201,255,.35), transparent);animation:portalTravel 6.5s ease-in-out infinite"></div>`;
    case 'frost': return `
      <div style="position:absolute;font-size:20px;color:#cdeeff;left:15%;top:8%;animation:snowFall 7s linear infinite">❋</div>
      <div style="position:absolute;font-size:14px;color:#cdeeff;left:70%;top:14%;animation:snowFall 9s linear infinite 2.5s">❋</div>`;
    case 'inferno': return `
      <div style="position:absolute;width:90px;height:90px;border-radius:50%;left:50%;top:60%;transform:translate(-50%,0);background:radial-gradient(circle,#ff7a3d,transparent 70%);animation:heatGlow 4.5s ease-in-out infinite"></div>
      <div style="position:absolute;width:4px;height:4px;border-radius:50%;background:#ffb15e;left:35%;top:70%;animation:emberRise 4s ease-in infinite"></div>
      <div style="position:absolute;width:3px;height:3px;border-radius:50%;background:#ffb15e;left:60%;top:75%;animation:emberRise 4.6s ease-in infinite 1.5s"></div>`;
    case 'celestial': return `
      <div style="position:absolute;width:100%;height:100%;background:conic-gradient(from 0deg, transparent, rgba(232,196,90,.12), transparent 30%);animation:starSpin 20s linear infinite"></div>`;
    case 'void': return `
      <div style="position:absolute;width:3px;height:3px;border-radius:50%;background:#ffd0e2;left:25%;top:40%;animation:voidSpark 4.4s ease-in-out infinite"></div>
      <div style="position:absolute;width:2px;height:2px;border-radius:50%;background:#ffd0e2;left:70%;top:55%;animation:voidSpark 5.2s ease-in-out infinite 1.6s"></div>`;
    case 'artifact': return `
      <div style="position:absolute;width:60%;height:200%;left:-30%;top:-50%;background:linear-gradient(100deg, transparent, rgba(255,255,255,.10), transparent);animation:gemShimmer 6s ease-in-out infinite alternate"></div>`;
    default: return '';
  }
}
```

- [ ] **Step 2: CSS no-fx/reduced-motion для узлов атмосферы**

В `app.css` расширить блок, добавленный в Task 3 Step 4 (в конце файла), — заменить:
```css
body.no-fx .coll-meter-notch.on { animation: none !important; box-shadow: 0 0 5px var(--gold2); }
@media (prefers-reduced-motion: reduce) {
  .coll-meter-notch.on { animation: none !important; box-shadow: 0 0 5px var(--gold2); }
}
```
на:
```css
body.no-fx .coll-meter-notch.on { animation: none !important; box-shadow: 0 0 5px var(--gold2); }
body.no-fx .coll-detail-atmo * { animation: none !important; opacity: .3; }
@media (prefers-reduced-motion: reduce) {
  .coll-meter-notch.on { animation: none !important; box-shadow: 0 0 5px var(--gold2); }
  .coll-detail-atmo * { animation: none !important; opacity: .3; }
}
```

- [ ] **Step 3: `node --check` + puppeteer-тест атмосферы+no-fx**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

Создать `predvestnik_v2/tools/verify_collection_detail_atmo.mjs`:

```js
// Атмосфера шапки детального экрана (Стадия 3): каждая из 7 линеек рендерит
// хотя бы 1 анимированный узел внутри .coll-detail-atmo, и все они гасятся
// под body.no-fx (тот же парный паттерн, что и .coll-card, Стадия 2).
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

const lineups = ['forest','threshold','frost','inferno','celestial','void','artifact'];
for (const lin of lineups) {
  await page.evaluate((l) => _looksOpenCollection(l), lin);
  await new Promise(r => setTimeout(r, 200));
  const n = await page.evaluate(() => document.querySelectorAll('.coll-detail-atmo *').length);
  check(`${lin}: атмосфера рендерит ≥1 декоративный узел`, n >= 1);
}

// no-fx гасит анимацию атмосферы (проверяем на inferno — 3 узла, ico-heatglow-стиль)
await page.evaluate(() => _looksOpenCollection('inferno'));
await new Promise(r => setTimeout(r, 200));
await page.evaluate(() => document.body.classList.add('no-fx'));
await new Promise(r => setTimeout(r, 200));
const styles = await page.evaluate(() =>
  Array.from(document.querySelectorAll('.coll-detail-atmo *')).map(e => getComputedStyle(e).animationName));
check('body.no-fx гасит все анимации атмосферы (animationName === "none")', styles.every(s => s === 'none'));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

Run: `node predvestnik_v2/tools/verify_collection_detail_atmo.mjs`
Expected: `ALL OK`

- [ ] **Step 4: Скриншот-проверка (обязательно, не доверять описанию кода)**

Урок из card_fx Артефакта (память `project_artifact_cosmetics_full_set_brief`): визуальные эффекты проверяются скриншотом, не на глаз по коду. Сделать 2 скриншота через puppeteer (например добавить временный `await page.screenshot(...)` в конце цикла выше или отдельным скриптом) для лидера с самой плотной атмосферой (`inferno`, 3 узла) и для `celestial` (широкий conic-gradient) — визуально проверить, что атмосфера не перекрывает текст шапки (медальон/имя/блёрб/измеритель/кнопку) и не выглядит «грязно» поверх `.coll-detail-head`. При необходимости скорректировать `opacity`/позиционирование в Step 1.

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_collection_detail_atmo.mjs
git commit -m "feat(cosmetics): атмосфера 7 линеек в шапке детального экрана (Стадия 3)"
```

---

### Task 5: Обновить существующий тест навигации (старое поведение-«мост» больше не существует)

**Files:**
- Modify: `predvestnik_v2/tools/verify_collections_navigation.mjs`

**Interfaces:**
- Consumes: `_looksOpenCollection`, `_looksCloseCollection`, `.coll-detail-head`, `.coll-detail-back` (Task 3).

- [ ] **Step 1: Переписать устаревшие ассерты**

`verify_collections_navigation.mjs` сейчас проверяет, что тап по карточке переключает `_looksMode` в `'slots'` и показывает умный ряд — это поведение Task 3 заменило детальным экраном. Заменить содержимое файла (после шапки-комментария и общей puppeteer-обвязки, строки 1-18 без изменений) — заменить строки 16-35:

```js
await page.click('.coll-card[data-lineup="inferno"]');
await new Promise(r => setTimeout(r, 400));

const state = await page.evaluate(() => ({
  mode: _looksMode,
  detailLineup: _looksDetailLineup,
  hasDetailHead: !!document.querySelector('.coll-detail-head'),
  hasFilterBar: !!document.getElementById('looks-filter-bar'),
}));
check('тап по карточке "Инферно" открывает детальный экран (mode остаётся collections)', state.mode === 'collections');
check('_looksDetailLineup выставлен на inferno', state.detailLineup === 'inferno');
check('шапка детального экрана отрендерена', state.hasDetailHead);
check('умный ряд "По слотам" НЕ показывается внутри детального экрана', !state.hasFilterBar);

// Кнопка "‹ Назад" в шапке детального экрана возвращает к списку карточек коллекций
await page.click('.coll-detail-back');
await new Promise(r => setTimeout(r, 300));
const back = await page.evaluate(() => ({
  mode: _looksMode,
  detailLineup: _looksDetailLineup,
  cardCount: document.querySelectorAll('.coll-card').length,
}));
check('кнопка "‹ Назад" возвращает detailLineup в null', back.detailLineup === null);
check('режим остаётся collections', back.mode === 'collections');
check('карточки коллекций снова на экране', back.cardCount === 7);
```

Обновить комментарий-шапку файла (строки 1-2) на:
```js
// Тап по карточке коллекции открывает детальный экран (Стадия 3) с шапкой и
// сегментным измерителем; кнопка "‹ Назад" возвращает к списку карточек.
```

- [ ] **Step 2: Запустить**

Run: `node predvestnik_v2/tools/verify_collections_navigation.mjs`
Expected: `ALL OK`

- [ ] **Step 3: Commit**

```bash
git add predvestnik_v2/tools/verify_collections_navigation.mjs
git commit -m "fix(cosmetics): verify_collections_navigation — обновлён под детальный экран Стадии 3"
```

---

### Task 6: Убрать «прыжки» вёрстки при переключении режима и примерке предмета

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js`
- Modify: `predvestnik_v2/FastAPI/static/app.css`
- Test: `predvestnik_v2/tools/verify_looks_no_jump.mjs` (новый)

**Контекст (не из письменной спеки, а из живого ручного теста владельцем на локальном стенде):** переключение «🗂 По коллекциям / 📚 По слотам» физически сдвигает сам переключатель то вниз, то вверх — раздражает, «портит всё впечатление». Корень: `.looks-sticky` (прилипающий блок превью, `app.css:3465`) не имеет фиксированной высоты — она целиком зависит от того, что внутри рендерится в конкретный момент. Переключатель режимов и все секции ниже стоят СРАЗУ ПОСЛЕ `.looks-sticky` в обычном потоке (не sticky сами) — как только высота `.looks-sticky` меняется, всё это физически сдвигается.

Два конкретных источника такой переменной высоты внутри `.looks-sticky`, которые чинит эта задача:
1. **Умный ряд фильтра** (`#looks-filter-bar`) — сегодня рендерится ТОЛЬКО в режиме «По слотам» (`_looksMode==='slots'`), в «По коллекциям» это пустая строка → блок короче на высоту умного ряда → при каждом клике переключателя высота `.looks-sticky` меняется → всё ниже прыгает. Это ровно тот баг, который заметил владелец.
2. **Ряд действий под превью «Сейчас→Станет»** (`.looks-ba-act` / `.looks-ba-hint`, три разных состояния: «✓ Применить + Сбросить» (2 кнопки) / «↩ Сбросить примерку» (1 кнопка на всю ширину) / текст-подсказка) — меняется на КАЖДЫЙ тап по предмету косметики (самое частое действие на этом экране).

**Осознанно НЕ входит в эту задачу** (совсем другая, более рискованная категория фикса — см. ниже): плашка покупки `.looks-buybar` (появляется/исчезает при тапе по некупленному предмету) и плашка описания линейки `#looks-lineup-info` (появляется при выборе конкретной линейки в «По слотам»). Обе, в отличие от двух источников выше, НЕ бинарный переключатель «есть/нет одного и того же по размеру блока» — их реальный контент существенно крупнее и разной длины по контенту (описание предмета/линейки, предупреждение VIP), поэтому резервировать под них место означало бы держать заметный пустой блок ПОСТОЯННО, когда ничего не выбрано — это самостоятельная, более тонкая UX-проблема (нужна плавная анимация высоты, а не резервирование места), не блокирующая эту задачу и не в объёме одной сессии вперемешку с остальным.

**Interfaces:**
- Consumes: `_looksFilterHtml()`, `_looksMode` (уже существуют, не меняются).
- Produces: CSS-класс `.sr-hidden` (переиспользуемый паттерн «скрыто, но место зарезервировано»); `.looks-ba-act`/`.looks-ba-hint` получают одинаковый `min-height`.

- [ ] **Step 1: Умный ряд фильтра — всегда рендерить, скрывать классом вместо удаления из DOM**

В `app.10.js` заменить (строка 81):
```js
const stickyFilterBar = _looksMode==='slots' ? `<div id="looks-filter-bar">${_looksFilterHtml()}</div>` : '';
```
на:
```js
// Всегда рендерим (не убираем из DOM условно) — иначе высота .looks-sticky
// меняется между режимами и всё ниже (переключатель режимов, секции) прыгает
// при каждом клике «По коллекциям»/«По слотам». sr-hidden прячет визуально,
// но оставляет место — резервирование места, не анимация (см. комментарий
// в app.css рядом с .sr-hidden).
const stickyFilterBar = `<div id="looks-filter-bar" class="${_looksMode==='slots'?'':'sr-hidden'}">${_looksFilterHtml()}</div>`;
```

(Ничего больше в `renderLooks()` менять не нужно — `_looksFilterHtml()` уже безопасно рендерится независимо от режима, она просто раньше не вызывалась в режиме «По коллекциям». `_looksPickLineup()` (существующая функция, точечно обновляет `#looks-filter-bar` через `outerHTML`) трогать не нужно — она вызывается только тапом по пилюле линейки, а эта пилюля недоступна для тапа, когда скрыта классом `sr-hidden` (`pointer-events:none`), то есть достижима только когда режим и так `'slots'` — переключатель там всегда корректно виден.)

- [ ] **Step 2: CSS для `.sr-hidden`**

В `app.css` добавить рядом с `.smartrow`/`.sr-*` правилами (после блока `.sr-box`, найти по имени класса, не по номеру строки — файл менялся другими задачами):

```css
/* Задача 6 (2026-07-30): «скрыто, но место зарезервировано» — не даёт
   .looks-sticky менять высоту при переключении режима (visibility, не
   display:none — DOM/тап-зона теряется, layout-место остаётся). */
.sr-hidden { visibility: hidden; pointer-events: none; }
```

- [ ] **Step 3: Ряд действий под превью — одинаковый `min-height` на все 3 состояния**

В `app.css` найти правила `.looks-ba-act`/`.looks-ba-hint` (сейчас: `.looks-ba-act { display: flex; gap: 8px; margin: 2px 0 12px; }` и `.looks-ba-hint { font-size: 10px; color: var(--muted); text-align: center; margin: 2px 0 12px; line-height: 1.4; }`). Заменить оба правила на:

```css
.looks-ba-act { display: flex; align-items: center; gap: 8px; margin: 2px 0 12px; min-height: 34px; box-sizing: border-box; }
.looks-ba-act .btn { flex: 1; }
.looks-ba-hint { font-size: 10px; color: var(--muted); text-align: center; margin: 2px 0 12px; line-height: 1.4; min-height: 34px; box-sizing: border-box; display: flex; align-items: center; justify-content: center; }
```

(`min-height:34px` — примерно высота ряда с кнопками `.btn.btn-sm`; строка-подсказка теперь центрируется по вертикали внутри той же высоты, а не занимает меньше места. Если после скриншот-проверки в Step 5 окажется, что кнопки реально выше/ниже 34px — подобрать точное число по факту, но оба правила ОБЯЗАНЫ иметь ОДИНАКОВОЕ значение `min-height`, иначе фикс не работает.)

- [ ] **Step 4: `node --check` + puppeteer-тест «нет прыжка»**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

Preview-сервер на 8402 должен быть уже запущен. Создать `predvestnik_v2/tools/verify_looks_no_jump.mjs`:

```js
// Задача 6: переключатель режимов и ряд действий под превью не должны физически
// сдвигаться при переключении «По коллекциям»/«По слотам» и при примерке предмета.
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

// Сценарий 1: переключатель режимов не должен менять свой Y при клике по нему самому
const toggleYBefore = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const toggleYAfterSlots = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
await page.click('[data-mode="collections"]');
await new Promise(r => setTimeout(r, 300));
const toggleYAfterBack = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
check('переключатель режимов НЕ сдвигается при переходе в "По слотам"', toggleYBefore === toggleYAfterSlots);
check('переключатель режимов НЕ сдвигается при возврате в "По коллекциям"', toggleYBefore === toggleYAfterBack);

// Сценарий 2: умный ряд всегда в DOM (скрыт визуально, не удалён)
const barPresence = await page.evaluate(() => ({
  existsInCollections: !!document.getElementById('looks-filter-bar'),
  hiddenInCollections: document.getElementById('looks-filter-bar').classList.contains('sr-hidden'),
}));
check('умный ряд фильтра существует в DOM в режиме "По коллекциям" (просто скрыт)', barPresence.existsInCollections);
check('умный ряд фильтра скрыт классом sr-hidden в режиме "По коллекциям"', barPresence.hiddenInCollections);

// Сценарий 3: ряд действий под превью не сдвигает переключатель режимов при примерке предмета
// (переключаемся в slots, тапаем по некупленному предмету — фокус ставится, actions меняется)
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
const toggleYBeforeTap = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
await page.evaluate(() => {
  const card = document.querySelector('.looks-card.lc-buyable[data-cos]');
  if (card) card.click();
});
await new Promise(r => setTimeout(r, 300));
const toggleYAfterTap = await page.evaluate(() => document.getElementById('looks-mode-toggle').getBoundingClientRect().y);
check('переключатель режимов НЕ сдвигается при примерке некупленного предмета (ряд действий меняется на "Сбросить примерку")', toggleYBeforeTap === toggleYAfterTap);

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

Run: `node predvestnik_v2/tools/verify_looks_no_jump.mjs`
Expected: `ALL OK`

- [ ] **Step 5: Скриншот-проверка обоих режимов при 390px**

Через puppeteer сделать 2 скриншота (390px ширина): режим «По коллекциям» и режим «По слотам», сразу после `openLooksModal()`. Посмотреть на оба глазами (изображение можно открыть через Read) — убедиться, что в режиме «По коллекциям» под превью нет заметной пустой полосы там, где раньше был умный ряд (он невидим, но резервирует место — если это выглядит как «дыра», а не просто чуть больше отступа перед переключателем — сообщить как concern, не решать самостоятельно).

- [ ] **Step 6: Regression — прогнать все существующие puppeteer-тесты косметики**

Run:
```bash
for f in predvestnik_v2/tools/verify_slots_*.mjs predvestnik_v2/tools/verify_collections_*.mjs predvestnik_v2/tools/verify_collection_detail_*.mjs; do
  echo "=== $f ==="; node "$f" || exit 1
done
```
Expected: ВСЕ заканчиваются `ALL OK` (эта задача не должна сломать ничего из Стадий 1/2/3 — особенно `verify_slots_smartrow.mjs`, который проверяет именно умный ряд, и `verify_collection_detail_header.mjs`, который открывает детальный экран через тот же `renderLooks()`).

- [ ] **Step 7: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/verify_looks_no_jump.mjs
git commit -m "fix(cosmetics): убраны прыжки вёрстки — переключатель режимов и ряд действий под превью не сдвигаются (найдено ручным тестом владельца)"
```

---

### Task 7: Финальный прогон — все puppeteer-тесты подряд + компиляция

**Files:** нет новых — только запуск существующего набора.

- [ ] **Step 1: Прогнать backend-тесты**

Run:
```bash
python -m py_compile predvestnik_v2/services/cosmetics.py predvestnik_v2/FastAPI/routers/cosmetics.py
python predvestnik_v2/tools/test_buy_lineup.py
```
Expected: оба `OK:` из Task 1 Step 4, без ошибок компиляции.

- [ ] **Step 2: Прогнать ВСЕ puppeteer-тесты косметики подряд**

Run (preview-сервер из Task 3 Step 6 должен быть запущен на 8402):
```bash
for f in predvestnik_v2/tools/verify_slots_*.mjs predvestnik_v2/tools/verify_collections_*.mjs predvestnik_v2/tools/verify_collection_detail_*.mjs predvestnik_v2/tools/verify_looks_no_jump.mjs; do
  echo "=== $f ==="; node "$f" || exit 1
done
```
Expected: каждый файл заканчивается `ALL OK` (10 существующих Стадии 1/2 + `verify_collection_detail_header.mjs` + `verify_collection_detail_atmo.mjs` + обновлённый `verify_collections_navigation.mjs` + `verify_looks_no_jump.mjs` (Task 6) = 13 всего). Любой `FAIL:` — вернуться и исправить соответствующий Task, не идти дальше.

- [ ] **Step 3: `node --check` на весь app.10.js ещё раз (после всех правок трёх задач)**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

- [ ] **Step 4: Итоговый commit (если Step 2 потребовал правок)**

Если в Step 2 были найдены и исправлены проблемы:
```bash
git add -u predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/
git commit -m "fix(cosmetics): финальный ревью Стадии 3 «детальный экран коллекции»"
```
Если правок не потребовалось — коммит не нужен, все изменения уже закоммичены по ходу Tasks 1-6.

---

## Что НЕ входит в эту стадию (сознательно отложено)

- **Плашка покупки (`.looks-buybar`) и плашка описания линейки (`#looks-lineup-info`) всё ещё «прыгают»** при появлении/исчезновении (см. Task 6) — это НЕ такой же баг, как переключатель режимов/ряд действий: их реальный контент существенно крупнее и разной длины, резервировать место означало бы держать заметный пустой блок постоянно, когда ничего не выбрано. Нужна плавная анимация высоты (CSS grid `0fr↔1fr` приём или JS FLIP), а не резервирование — отдельная, более тонкая задача, не в объёме этой сессии.
- **Аппаратная кнопка «Назад» Telegram / `_navStack`** — детальный экран коллекции не встроен в общую систему навигации вкладок (закрывается только явным тапом «‹»). Согласуется с текущим уровнем интеграции: сама Стадия 2 тоже не трогала `_navStack` для переключения режимов.
- **6 QoL-фичи** (сортировка/избранное/рандомайзер/бейдж «новое»/экран-праздник/уведомление на навигации) и **«Образы»** (объединение пресетов+кураторских сетов) — отдельные будущие стадии, см. `docs/superpowers/specs/2026-07-29-cosmetics-tab-redesign-design.md`, разделы «QoL-функции» и «Образы».
- **Деплой на прод** — эта стадия собирается и проверяется ТОЛЬКО в `tools/preview_server.mjs` (порт 8402/63768). Перенос на прод — отдельный шаг после ручного смоука (см. открытый пункт 1 в `docs/superpowers/specs/2026-07-23-remaining-work-and-cosmetics-redesign.md`, который уже включает Стадии 1-2 и теперь должен включить эту).
