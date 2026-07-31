# Примерочная — Стадия 4 (FAB + шторка + множественная примерка + покупка) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить сегодняшнюю примерочную (прилипающее сверху мини-превью + одна инлайн-плашка покупки, поддерживающая примерку только ОДНОГО некупленного предмета за раз) на плавающую кнопку (FAB) с живой мини-аватаркой игрока, открывающую полноэкранную шторку с настоящей карточкой профиля, где можно примерить НЕСКОЛЬКО ещё не купленных предметов одновременно (по одному на слот) и купить их по одному ИЛИ все разом одной золотой кнопкой.

**Architecture:** Реализует разделы A, B, C, D спеки `docs/superpowers/specs/2026-07-31-cosmetics-fitting-room-and-harmony-design.md` (Разделы E, F, G — системные фиксы композиции косметики, анимация открытия коллекции, гармонизация старых секций — ОТДЕЛЬНЫЕ будущие стадии, не в этом плане). Бэкенд — новая функция `buy_many()` в `services/cosmetics.py` (покупка произвольного набора `cosmetic_id` одной транзакцией, мирроит уже существующую `buy_lineup()` включая критичный урок «владение читается ПОСЛЕ блокировки баланса») + тонкий роутер-эндпоинт. Фронтенд — замена одиночного `_looksFocus` на пер-слотовую карту примерки `_looksTrial`, удаление старого прилипающего превью из общего потока страницы, новый FAB (переиспользует существующий `OM()`/`#modal` — тот же нативный `<dialog>`, что и все остальные модалки проекта) со шторкой внутри.

**Tech Stack:** FastAPI + asyncpg/PGAdapter (бэкенд), vanilla JS classic script + CSS (фронт, `FastAPI/static/app.10.js`+`app.css`), Puppeteer (`tools/verify_*.mjs`) для UI-тестов, `tools/preview_server.mjs` (порт 8402) для локального стенда без БД.

## Global Constraints

- PostgreSQL плейсхолдеры: писать `?`, PGAdapter сам конвертирует в `$1,$2...` — НЕ писать `$1` вручную.
- `services/` не импортирует `bot.*`/`FastAPI.*` — вся бизнес-логика в `services/cosmetics.py`, роутер только тонкая обвязка (`HTTPException` + `db.commit()`).
- **Владение при покупке ОБЯЗАНО читаться ПОСЛЕ `SELECT ... FOR UPDATE`, не до** — под реальным Postgres второй параллельный вызов (двойной тап) блокируется на этом SELECT; если владение прочитано раньше, оба вызова спишут цену за одни и те же предметы дважды (реальный Critical-баг, найденный и исправленный в финальном ревью Стадии 3 у `buy_lineup()` — `buy_many()` обязана повторить тот же паттерн, не регрессировать).
- Одна золотая кнопка на экран (DESIGN.md, «Правило золота-награды») — ни в одной комбинации состояний шторки не должно быть двух одновременно видимых `.btn-gold`.
- Правило тонированного чипа (DESIGN.md): фон ~13-14% альфы цвета, граница ~30%, текст полным цветом — НЕ сплошная заливка.
- Любая новая CSS-анимация — парный паттерн `body.no-fx` + `@media (prefers-reduced-motion: reduce)` (см. `app.css:1826-1841` — уже существующий общий блок для косметики, новые классы FAB/шторки должны попасть под тот же селектор, не заводить отдельный).
- `node --check FastAPI/static/app.10.js` после любой правки JS; `python -m py_compile services/cosmetics.py FastAPI/routers/cosmetics.py` после правки бэка.
- Мокапы примерочной в `predvestnik_v2/.superpowers/brainstorm/3239-1785485959/` использовали ВЕРБАТИМ-значения из `app.css` (не придуманные цвета) — то же правило действует при реализации: переиспользовать существующие классы/переменные, не изобретать новые цвета для того, что уже есть в дизайн-системе.

---

### Task 1: Backend — `buy_many()` (покупка произвольного набора предметов)

**Files:**
- Modify: `predvestnik_v2/services/cosmetics.py` (новая функция после `buy_lineup()`, т.е. после строки 440, перед `async def get_active_cosmetics` на строке 443)
- Modify: `predvestnik_v2/FastAPI/routers/cosmetics.py` (импорт + новый эндпоинт после `cosmetics_buy_lineup`, т.е. после строки 73, перед `class EquipRequest` на строке 76)
- Test: `predvestnik_v2/tools/test_buy_many.py` (новый)

**Interfaces:**
- Consumes: `COSMETICS` (`core/cosmetics.py`, уже импортирован в `services/cosmetics.py:10`), `_owned(db, user_id) -> set[str]` (уже в файле, строка 131).
- Produces: `buy_many(db, user_id: int, cosmetic_ids: list[str]) -> tuple[bool, str]` — используется в Task 2 (`_looksBuyAndApplyAll()` вызывает эндпоинт `POST /cosmetics/buy-many`, не эту функцию напрямую).

- [ ] **Step 1: Написать падающий тест**

Создать `predvestnik_v2/tools/test_buy_many.py`:

```python
"""Примерочная (Раздел C спеки 2026-07-31): «Купить и применить всё примеренное» —
покупка ПРОИЗВОЛЬНОГО набора конкретных cosmetic_id одной транзакцией. В отличие от
buy_lineup() (Стадия 3, покупает ВСЮ одну линейку по единой цене линейки), предметы
здесь могут быть из РАЗНЫХ линеек одновременно, каждый со своей ценой — игрок мог
примерить рамку из «Инферно» и фон из «Порог» разом."""
import sys
import pathlib
import asyncio
from unittest.mock import AsyncMock, patch

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.cosmetics import COSMETICS
from services.cosmetics import buy_many

# ── Реальные предметы из РАЗНЫХ линеек с РАЗНЫМИ ценами (не выдуманные) ─────
ID_A = "cos_name_glow_moon"        # forest, 250✨
ID_B = "cos_name_glow_frost"       # frost, 440✨
assert COSMETICS[ID_A]["price"][0]["zarniki"] == 250
assert COSMETICS[ID_B]["price"][0]["zarniki"] == 440
EXPECTED_TOTAL = 250 + 440


class FakeCursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self._rows

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
    одновременно awaitable И async context manager (см. services/cosmetics.py::
    buy()/buy_lineup() — тот же паттерн: `await db.execute(...)` для UPDATE/INSERT,
    `async with db.execute(...) as c:` для SELECT ... FOR UPDATE)."""

    def __init__(self, balance):
        self.connection = FakeConnection()
        self.executed = []
        self.balance = balance
        self.granted = set()   # имитирует строки user_cosmetics

    def execute(self, sql, args=()):
        self.executed.append((sql.strip(), tuple(args)))
        if "SELECT COALESCE(user_balance_zarniki" in sql:
            return FakeCursor((self.balance,))
        if "SELECT cosmetic_id FROM user_cosmetics" in sql:
            return FakeCursor(rows=[(cid,) for cid in self.granted])
        if sql.startswith("UPDATE users"):
            self.balance -= args[0]
            return FakeCursor(None)
        if sql.startswith("INSERT INTO user_cosmetics"):
            self.granted.add(args[1])
            return FakeCursor(None)
        return FakeCursor(None)

    async def commit(self):
        pass


async def main():
    with patch("services.achievements.increment_metric", new_callable=AsyncMock):
        # Пустой список
        ok, msg = await buy_many(FakeDB(balance=10000), 1, [])
        assert ok is False and "пуст" in msg.lower()

        # Неизвестный ID
        ok, msg = await buy_many(FakeDB(balance=10000), 1, ["cos_does_not_exist"])
        assert ok is False

        # Недостаточно баланса — без единого списания/выдачи
        db_poor = FakeDB(balance=EXPECTED_TOTAL - 1)
        ok, msg = await buy_many(db_poor, 555, [ID_A, ID_B])
        assert ok is False, "должно отказать при нехватке баланса"
        assert not any(sql.startswith("UPDATE users") for sql, _ in db_poor.executed), \
            "баланс не должен списываться при отказе"
        assert not any(sql.startswith("INSERT INTO user_cosmetics") for sql, _ in db_poor.executed), \
            "предметы не должны выдаваться при отказе"

        # Хватает баланса — ровно 1 UPDATE суммой РАЗНЫХ цен + по 1 INSERT на предмет
        db_rich = FakeDB(balance=EXPECTED_TOTAL)
        ok, msg = await buy_many(db_rich, 777, [ID_A, ID_B])
        assert ok is True, f"должно пройти при достаточном балансе: {msg}"
        updates = [a for sql, a in db_rich.executed if sql.startswith("UPDATE users")]
        inserts = [a for sql, a in db_rich.executed if sql.startswith("INSERT INTO user_cosmetics")]
        assert len(updates) == 1, f"ожидался 1 UPDATE, получено {len(updates)}"
        assert updates[0][0] == EXPECTED_TOTAL, f"списано {updates[0][0]}, ожидалось {EXPECTED_TOTAL}"
        assert len(inserts) == 2, f"ожидалось 2 INSERT, получено {len(inserts)}"
        assert str(EXPECTED_TOTAL) in msg

        print("OK: buy_many — пустой список/неизвестный ID отклоняются; отказ без "
              "побочных эффектов при нехватке баланса; при достатке — 1 списание "
              "суммы РАЗНЫХ цен + по 1 выдаче на предмет")

        # ── Регресс-тест: владение ОБЯЗАНО читаться ПОСЛЕ SELECT...FOR UPDATE —
        # тот же класс бага, что нашло финальное ревью Стадии 3 у buy_lineup()
        # (двойной тап/параллельный вызов спишет дважды, если порядок нарушить).
        # FakeDB не умеет симулировать реальную блокировку между ДВУМЯ вызовами,
        # но порядок SQL ВНУТРИ одного вызова — то, что делает фикс верным под
        # реальным Postgres — проверяется напрямую по журналу executed.
        db_order = FakeDB(balance=EXPECTED_TOTAL)
        await buy_many(db_order, 111, [ID_A, ID_B])
        sql_order = [sql for sql, _ in db_order.executed]
        idx_lock = next(i for i, s in enumerate(sql_order) if "FOR UPDATE" in s)
        idx_owned = next(i for i, s in enumerate(sql_order) if s.startswith("SELECT cosmetic_id FROM user_cosmetics"))
        assert idx_owned > idx_lock, (
            "владение прочитано ДО SELECT...FOR UPDATE — под реальным Postgres второй "
            "параллельный вызов (двойной тап по 'Купить всё примеренное') увидит "
            "СТАРОЕ владение и спишет total ещё раз за уже выданные предметы"
        )
        print("OK: buy_many — владение читается ПОСЛЕ захвата блокировки баланса, "
              "как и buy_lineup() — двойной тап не спишет дважды")


asyncio.run(main())
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `python tools/test_buy_many.py`
Expected: `ImportError: cannot import name 'buy_many' from 'services.cosmetics'`

- [ ] **Step 3: Реализовать `buy_many()`**

В `predvestnik_v2/services/cosmetics.py` добавить после строки 440 (`return True, f"🎨 «{meta['name']}» собрана полностью!..."`, конец `buy_lineup()`), перед `async def get_active_cosmetics`:

```python
async def buy_many(db, user_id: int, cosmetic_ids: list[str]) -> tuple[bool, str]:
    """Купить произвольный набор КОНКРЕТНЫХ предметов косметики одной транзакцией
    («Купить и применить всё примеренное» в примерочной — Раздел C спеки
    2026-07-31). В отличие от buy_lineup() (вся ОДНА линейка по её единой цене),
    здесь предметы могут быть из РАЗНЫХ линеек одновременно, каждый со своей ценой.

    Мирроит buy_lineup(): владение читается ПОСЛЕ SELECT...FOR UPDATE — иначе
    двойной тап/параллельный вызов спишет дважды за одни и те же предметы (см.
    docstring buy_lineup() и находку финального ревью Стадии 3)."""
    ids = list(dict.fromkeys(cosmetic_ids))   # de-dup, порядок не важен
    if not ids:
        return False, "Список предметов пуст."
    for cid in ids:
        cos = COSMETICS.get(cid)
        if not cos:
            return False, f"Нет такого предмета: {cid}."
        price = cos.get("price")
        if not price or "zarniki" not in price[0]:
            return False, f"«{cos['name']}» не продаётся за зарники."

    async with db.connection.transaction():
        async with db.execute(
            "SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id = ? FOR UPDATE",
            (user_id,)
        ) as c:
            row = await c.fetchone()
        bal = float(row[0]) if row else 0.0

        owned = await _owned(db, user_id)
        missing = [cid for cid in ids if cid not in owned]
        if not missing:
            return False, "Всё это у тебя уже есть."
        total = sum(COSMETICS[cid]["price"][0]["zarniki"] for cid in missing)

        if bal < total:
            return False, f"Нужно {total}✨ (у тебя {int(bal)})."
        await db.execute(
            "UPDATE users SET user_balance_zarniki = user_balance_zarniki - ? WHERE user_tg_id = ?",
            (total, user_id))
        for cid in missing:
            await db.execute(
                "INSERT INTO user_cosmetics (user_id, cosmetic_id) VALUES (?, ?) "
                "ON CONFLICT DO NOTHING", (user_id, cid))

    try:
        from services.achievements import increment_metric
        await increment_metric(db, user_id, "cosmetics_bought", delta=float(len(missing)))
        await db.commit()
    except Exception:
        pass

    return True, f"🎨 Куплено {len(missing)} шт. за {total}✨"
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python tools/test_buy_many.py`
Expected:
```
OK: buy_many — пустой список/неизвестный ID отклоняются; отказ без побочных эффектов при нехватке баланса; при достатке — 1 списание суммы РАЗНЫХ цен + по 1 выдаче на предмет
OK: buy_many — владение читается ПОСЛЕ захвата блокировки баланса, как и buy_lineup() — двойной тап не спишет дважды
```

- [ ] **Step 5: Роутер-эндпоинт**

В `predvestnik_v2/FastAPI/routers/cosmetics.py` изменить импорт (строки 13-19):

```python
from services.cosmetics import (
    buy, equip, get_catalog, set_welcome, unequip,
    chest_catalog, open_chest, craft_catalog, craft_cosmetic,
    giftable_cosmetics, gift_cosmetic, buy_chest,
    list_presets, save_preset, apply_preset, delete_preset,
    buy_lineup, buy_many,
)
```

Добавить после `cosmetics_buy_lineup` (после строки 73, `return {"ok": True, "message": msg}`, перед `class EquipRequest`):

```python
class BuyManyRequest(BaseModel):
    cosmetic_ids: list[str]


@router.post("/buy-many")
async def cosmetics_buy_many(body: BuyManyRequest, db=Depends(get_db), user=Depends(require_tg_user)):
    ok, msg = await buy_many(db, user["id"], body.cosmetic_ids)
    if not ok:
        raise HTTPException(400, msg)
    await db.commit()
    return {"ok": True, "message": msg}
```

- [ ] **Step 6: `py_compile` + smoke-импорт**

Run: `python -m py_compile predvestnik_v2/services/cosmetics.py predvestnik_v2/FastAPI/routers/cosmetics.py`
Expected: без вывода

Run: `python -c "import sys; sys.path.insert(0,'predvestnik_v2'); from FastAPI.routers.cosmetics import router; print([r.path for r in router.routes if 'buy-many' in r.path])"`
Expected: `['/cosmetics/buy-many']`

- [ ] **Step 7: Commit**

```bash
git add predvestnik_v2/services/cosmetics.py predvestnik_v2/FastAPI/routers/cosmetics.py predvestnik_v2/tools/test_buy_many.py
git commit -m "feat(cosmetics): buy_many() — покупка произвольного набора предметов одной транзакцией (примерочная, бэкенд)"
```

---

### Task 2: Frontend — множественная примерка + FAB + шторка

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.10.js`
- Modify: `predvestnik_v2/FastAPI/static/app.css`
- Modify: `predvestnik_v2/tools/preview_server.mjs` (мок `POST /cosmetics/buy-many`)
- Test: `predvestnik_v2/tools/verify_fitting_room.mjs` (новый)

Это один большой связанный таск (не дробится дальше), т.к. состояние примерки (`_looksTrial`), FAB и шторка меняются одновременно и по отдельности не дают проверяемого результата — реальная проверяемая цель таска: «примерить 2 некупленных предмета из разных слотов, увидеть оба разом в шторке, купить по одному и/или всё разом».

**Interfaces:**
- Consumes: `_looksSel`/`_looksSaved`/`_looksData` (существуют), `_looksCos(id)`, `_looksApply()`, `_looksReloadCatalog()`, `_looksMarkSel(slot)`, `OM(title,body,btns)`/`CM()` (глобальный shared `<dialog>`, `app.01.js:412-420`), `_LOOKS_SLOTS`, `_LOOKS_SLOT_ICON`, `lineupLabel(id)`, `_looksCos`, `_looksRenderCard(sel)` (существует, будет изменена).
- Produces: `_looksTrial` (module-level `{slot: cosmetic_id}`, заменяет `_looksFocus`), `_looksRenderFab()`, `_looksOpenFittingSheet()`, `_looksFittingSheetBodyHtml()`, `_looksTrialTotal()`, `_looksBuyAndApplyAll(btn)`, `_looksResetTrialAndRerenderSheet()` — используются только внутри Task 2, других потребителей нет.

- [ ] **Step 1: Заменить `_looksFocus` на `_looksTrial` в объявлении состояния**

В `app.10.js` заменить строку 9:
```js
let _looksData=null, _looksSel={}, _looksSaved={}, _looksDirty=false, _looksFocus=null;
```
на:
```js
let _looksData=null, _looksSel={}, _looksSaved={}, _looksDirty=false;
let _looksTrial={};   // Примерочная (Стадия 4): {slot: cosmetic_id} НЕкупленных предметов, ПО ОДНОМУ НА СЛОТ — в отличие от старого _looksFocus (один слот на весь экран), можно примерять несколько слотов сразу
```

- [ ] **Step 2: Убрать сброс `_looksFocus` в `openLooksModal()`**

Заменить строку 33:
```js
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksFocus=null; _looksDetailLineup=null;
```
на:
```js
  _looksFilter='all'; _looksStatus='all'; _looksSearch=''; _looksTrial={}; _looksDetailLineup=null;
```

- [ ] **Step 3: Переписать состояние показа/hero/действий (замена `_looksFocus` на `_looksTrial` везде)**

Заменить блок строк 469 (`_looksChanged`) — оставить БЕЗ изменений (не трогать), это про `_looksSel` vs `_looksSaved`, к примерке некупленного не относится.

Заменить блок строк 585-596 целиком:
```js
// Что показано в слоте прямо сейчас: примеряемый (focus) перекрывает выбранное.
function _looksShownId(slot){ return (_looksFocus&&_looksFocus.slot===slot)?_looksFocus.id:(_looksSel[slot]||null); }
// Набор для hero: применимый выбор + наложенная примерка focus (в т.ч. непокупленного).
function _looksHeroSel(){ if(!_looksFocus) return _looksSel; const s={..._looksSel}; s[_looksFocus.slot]=_looksFocus.id; return s; }
// Отличается ли hero от применённого визуально (для стрелки/подписи «Станет»).
function _looksHeroDiffers(){ const hs=_looksHeroSel(); return _LOOKS_SLOTS.some(s=>(hs[s]||null)!==(_looksSaved[s]||null)); }
function _looksEquip(slot,id){ _looksSel[slot]=id; _looksFocus={slot,id}; _looksRenderTop(); _looksMarkSel(slot); }
function _looksUnequip(slot){ _looksSel[slot]=null; _looksFocus=null; _looksRenderTop(); _looksMarkSel(slot); }
function _looksReset(){ _looksSel={..._looksSaved}; _looksFocus=null; _looksRenderTop(); _LOOKS_SLOTS.forEach(_looksMarkSel); }
// Непокупленный: только примерка (focus), в _looksSel НЕ кладём → «Применить» его не тронет
// (нельзя надеть то, чем не владеешь); для покупки — инлайн-плашка под hero.
function _looksTapUnowned(slot,id){ _looksFocus={slot,id}; _looksRenderTop(); _looksMarkSel(slot); }
```
на:
```js
// Что показано в слоте прямо сейчас: примерка (_looksTrial[slot], если есть)
// перекрывает сохранённый выбор.
function _looksShownId(slot){ return _looksTrial[slot] || _looksSel[slot] || null; }
// Набор для hero: применимый выбор + ВСЕ активные примерки некупленного разом
// (Стадия 4: раньше был один общий _looksFocus — примерка нового некупленного
// предмета в другом слоте стирала предыдущую; теперь _looksTrial хранит по
// одному некупленному предмету НА КАЖДЫЙ слот одновременно).
function _looksHeroSel(){
  const s={..._looksSel};
  Object.keys(_looksTrial).forEach(slot=>{ s[slot]=_looksTrial[slot]; });
  return s;
}
// Отличается ли hero от применённого (для статуса примерочной).
function _looksHeroDiffers(){ const hs=_looksHeroSel(); return _LOOKS_SLOTS.some(s=>(hs[s]||null)!==(_looksSaved[s]||null)); }
function _looksEquip(slot,id){ _looksSel[slot]=id; delete _looksTrial[slot]; _looksRenderFab(); _looksMarkSel(slot); }
function _looksUnequip(slot){ _looksSel[slot]=null; delete _looksTrial[slot]; _looksRenderFab(); _looksMarkSel(slot); }
function _looksReset(){ _looksSel={..._looksSaved}; _looksTrial={}; _looksRenderFab(); _LOOKS_SLOTS.forEach(_looksMarkSel); }
// Непокупленный: только примерка (_looksTrial[slot]), в _looksSel НЕ кладём →
// «Применить» его не тронет (нельзя надеть то, чем не владеешь). Другие слоты
// в _looksTrial НЕ трогаем — можно примерять некупленное в НЕСКОЛЬКИХ слотах разом,
// это и есть фикс "нельзя примерить сразу несколько".
function _looksTapUnowned(slot,id){ _looksTrial[slot]=id; _looksRenderFab(); _looksMarkSel(slot); }
```

- [ ] **Step 4: Удалить старое прилипающее превью из `renderLooks()`, убрать `#looks-top`/старый `.looks-sticky`-с-превью, добавить FAB**

Заменить блок строк 70-106 (всю функцию `renderLooks()`) целиком:
```js
function renderLooks(){
  const b=el('pg-looks'); if(!b||!_looksData) return;
  const vipBar=_looksData.vip?'':`<div class="looks-vipbar">
    <span>👑 Купить можно любую косметику. Линейки дороже «Лесного Странника» <b>отображаются на профиле только с VIP</b>.</span>
    <button class="btn btn-sm btn-gold" onclick="goTo('market','vip')">Перейти к VIP</button></div>`;
  const modeBody=_looksMode==='collections'?_looksCollectionsViewHtml():_looksSlotsViewHtml();
  // «Вход»/«Темы» — ОБЩИЕ для обоих режимов (по спеку), рендерятся здесь ОДИН раз,
  // а не внутри modeBody — иначе в режиме «По коллекциям» пропал бы доступ к смене
  // приветствия/темы. Умный ряд фильтров («По слотам» режим) тоже ОБЩИЙ.
  //
  // Стадия 4: прилипающее превью «Сейчас→Станет» (было здесь, #looks-top) убрано
  // из общего потока страницы целиком — примерочная переехала в FAB+шторку (см.
  // _looksFabHtml()/_looksOpenFittingSheet() ниже). .looks-sticky теперь несёт
  // ТОЛЬКО умный ряд фильтра (режим «По слотам») — при скролле он всё ещё не
  // должен уезжать под шапку, поэтому остаётся sticky, просто короче, чем раньше.
  const stickyFilterBar = _looksMode==='slots' ? `<div class="looks-sticky"><div id="looks-filter-bar">${_looksFilterHtml()}</div></div>` : '';
  b.innerHTML=`
    <div class="looks-head">
      <button class="looks-back" onclick="_looksClose()" aria-label="Назад">‹</button>
      <div class="looks-htitle">🎨 Внешний вид</div>
    </div>
    ${_looksDetailLineup?'':_looksModeToggleHtml()}
    ${stickyFilterBar}`
    +vipBar
    +'<button class="btn btn-ghost btn-full" style="margin:2px 0 10px" onclick="_openSurprisesModal()">🎁 Сюрпризы и 🔹 Крафт косметики</button>'
    +_looksPresetsHtml()
    +`<div id="looks-mode-body">${modeBody}</div>`
    +`<div id="looks-common-sections">${_looksWelcomeSectionHtml()}${_looksThemesSectionHtml()}</div>`
    +`<div class="pay-terms">Покупая косметику, вы соглашаетесь с <a href="${BASE}/legal/tos" target="_blank" rel="noopener">Соглашением</a>. Цифровые товары возврату не подлежат.</div>`
    +`<div class="looks-fab-wrap">${_looksFabHtml()}</div>`;
  _looksThemesEnsureLoaded();
  _looksSyncStickyH();
}
```

Удалить (не переносить никуда — заменяется шторкой) следующие функции целиком: `_looksRenderTop()` (строки 451-454), `_looksRenderCard(sel)` НЕ удалять — переиспользуется, но изменить (см. Step 6), `_looksPreviewHtml()` (строки 470-486), `_looksBuyBarHtml()` (строки 488-502), `_looksBuyFocus()` (строки 503-506).

- [ ] **Step 5: Обновить оставшихся вызывателей удалённого `_looksRenderTop()`**

Заменить `_looksRenderTop()` на `_looksRenderFab()` в двух оставшихся местах:

В `_looksBuyLineup` (строка ~367) заменить:
```js
      _looksFocus=null; _looksDirty=true;
      const body=el('looks-mode-body'); if(body) body.innerHTML=_looksCollectionsViewHtml();
      _looksRenderTop(); _looksSyncStickyH();})
```
на:
```js
      _looksDirty=true;
      const body=el('looks-mode-body'); if(body) body.innerHTML=_looksCollectionsViewHtml();
      _looksRenderFab(); _looksSyncStickyH();})
```

(Остальные вызовы `_looksRenderTop()` уже переписаны в Step 3 как часть `_looksEquip`/`_looksUnequip`/`_looksReset`/`_looksTapUnowned`.)

- [ ] **Step 6: Упростить `_looksRenderCard` — убрать `--mini`, это теперь герой экрана шторки, не мелкая деталь прилипшего превью**

Заменить (строки 456-468):
```js
// Мини-карточка профиля из набора слотов sel для сравнения «Сейчас → Станет».
function _looksRenderCard(sel){
  const d=_looksData;
  const glow=_looksCos(sel.name_glow), frame=_looksCos(sel.avatar_frame), title=_looksCos(sel.title);
  const halo=_looksCos(sel.avatar_halo), bg=_looksCos(sel.profile_bg), fx=_looksCos(sel.card_fx);
  const sizeCls=' looks-preview--mini';
  return `<div class="looks-preview${sizeCls} ${bg?bg.css:''}">
    ${fx?`<div class="card-fx ${fx.css}"></div>`:''}
    <div class="ava ${frame?frame.css:''} ${halo?halo.css:''}">${d.vip?'👑':'🔮'}</div>
    <div class="pname ${glow?glow.css:''}">@${esc((_profileData&&_profileData.username)||'Игрок')}</div>
    ${title?`<div class="ptitle${title.css?' '+title.css:''}">${esc(title.text||title.name)}</div>`:''}
  </div>`;
}
```
на:
```js
// Карточка профиля из набора слотов sel — настоящий компонент .looks-preview
// (Раздел A спеки 2026-07-31: примерочная — это НЕ абстрактное мини-превью, а
// та же карточка, что в «Профиль»/публичном профиле). Используется В ШТОРКЕ,
// поэтому БЕЗ модификатора --mini (был нужен только для старого прилипающего
// сверху превью, которое занимало мало места — здесь карточка герой экрана).
function _looksRenderCard(sel){
  const d=_looksData;
  const glow=_looksCos(sel.name_glow), frame=_looksCos(sel.avatar_frame), title=_looksCos(sel.title);
  const halo=_looksCos(sel.avatar_halo), bg=_looksCos(sel.profile_bg), fx=_looksCos(sel.card_fx);
  return `<div class="looks-preview ${bg?bg.css:''}">
    ${fx?`<div class="card-fx ${fx.css}"></div>`:''}
    <div class="ava ${frame?frame.css:''} ${halo?halo.css:''}">${d.vip?'👑':'🔮'}</div>
    <div class="pname ${glow?glow.css:''}">@${esc((_profileData&&_profileData.username)||'Игрок')}</div>
    ${title?`<div class="ptitle${title.css?' '+title.css:''}">${esc(title.text||title.name)}</div>`:''}
  </div>`;
}
```

- [ ] **Step 7: FAB — плавающая кнопка с живой мини-аватаркой**

Добавить сразу после `_looksRenderCard` (после Step 6):

```js
// ── FAB примерочной (Стадия 4, Раздел A спеки) ──────────────────────────────
// Живая композиция аватара игрока (та же frame/halo, что и на полной карточке),
// не абстрактная иконка — кнопка сама по себе уже отвечает "что это". Золотая
// точка-бейдж — только когда есть неоплаченная примерка (золото = ожидающее
// действие, не декор, DESIGN.md). Позиция — над нижней навигацией (см. app.css
// #nav-back: bottom:78px — тот же проверенный отступ, левый нижний угол там,
// FAB — правый).
function _looksFabHtml(){
  if(!_looksData) return '';
  const sel=_looksHeroSel();
  const frame=_looksCos(sel.avatar_frame), halo=_looksCos(sel.avatar_halo);
  const hasTrial=Object.keys(_looksTrial).length>0;
  return `<button class="looks-fab" onclick="_looksOpenFittingSheet()" aria-label="Примерочная">
    <div class="ava looks-fab-ava ${frame?frame.css:''} ${halo?halo.css:''}">${_looksData.vip?'👑':'🔮'}</div>
    ${hasTrial?'<span class="looks-fab-badge"></span>':''}
  </button>`;
}
// Точечно обновляет ТОЛЬКО FAB (не всю страницу) — вызывается из _looksEquip/
// _looksUnequip/_looksTapUnowned/_looksReset/_looksBuyLineup, т.е. на каждый тап
// по предмету где угодно в конструкторе, пока шторка ЗАКРЫТА (нативный <dialog>
// с showModal() блокирует фон — тапы по сетке предметов физически невозможны,
// пока шторка открыта, поэтому саму шторку она не трогает).
function _looksRenderFab(){
  const wrap=document.querySelector('.looks-fab-wrap'); if(!wrap) return;
  wrap.innerHTML=_looksFabHtml();
}
```

- [ ] **Step 8: Шторка — открытие, тело, ряд слот-чипов, покупка**

Добавить сразу после Step 7:

```js
// ── Шторка примерочной (Стадия 4, Разделы A-C спеки) ────────────────────────
// Переиспользует общий OM()/#modal — тот же нативный <dialog>, что и все
// остальные модалки проекта (DESIGN.md: «Bottom Sheet — сигнатурный компонент»,
// не изобретается новый механизм). Живой контент (карточка+ряд+кнопки) целиком
// в теле — footer только для закрытия, чтобы не плодить лишний golden-button
// рядом с телом (см. Global Constraints, «одна золотая кнопка на экран»).
function _looksOpenFittingSheet(){
  OM('🎨 Примерочная', _looksFittingSheetBodyHtml(), [{l:'Закрыть',c:'btn-ghost',f:'CM()'}]);
}
function _looksTrialTotal(){
  return Object.values(_looksTrial).reduce((sum,id)=>{
    const it=_looksCos(id);
    const price=(it&&it.price&&it.price[0]&&it.price[0].zarniki)||0;
    return sum+price;
  },0);
}
// Ряд из 6 слот-чипов: серый потушенный = пусто, яркий = своё надето,
// золотисто-тонированный (правило тонированного чипа, НЕ сплошная заливка) =
// примерено-не-куплено, с ценой — тап покупает именно этот один предмет.
function _looksFittingSlotChipsHtml(){
  return `<div class="fit-slotrow">${_LOOKS_SLOTS.map(slot=>{
    const trialId=_looksTrial[slot];
    if(trialId){
      const it=_looksCos(trialId);
      const price=(it&&it.price&&it.price[0]&&it.price[0].zarniki)||0;
      return `<button class="fit-slotchip trial" onclick="_looksBuyFromPreview('${trialId}',0,'${slot}')">
        <span class="ic">${_LOOKS_SLOT_ICON[slot]}</span>${esc(lineupLabel(it.lineup))}<span class="price">${price}✨</span></button>`;
    }
    const ownedId=_looksSel[slot];
    if(ownedId) return `<div class="fit-slotchip owned"><span class="ic">${_LOOKS_SLOT_ICON[slot]}</span>своё</div>`;
    return `<div class="fit-slotchip"><span class="ic">${_LOOKS_SLOT_ICON[slot]}</span>—</div>`;
  }).join('')}</div>`;
}
// Единственная золотая кнопка шторки: показывает АКТУАЛЬНОЕ действие — просто
// "Применить" (бесплатно, если платных примерок нет — сегодняшнее поведение не
// меняется) или "Купить и применить всё — N✨" (если есть хоть один платный слот
// — одно действие сразу коммитит бесплатные перестановки И платит за примеренное,
// см. Раздел C спеки — так на экране никогда нет двух золотых кнопок одновременно).
function _looksFittingSheetBodyHtml(){
  const hasTrial=Object.keys(_looksTrial).length>0;
  const hasFree=_looksChanged();
  let actionHtml;
  if(!hasFree && !hasTrial){
    actionHtml=`<div class="looks-ba-hint">👇 Жми предмет в списке — примерка сразу здесь. Понравилось — «Применить».</div>`;
  } else {
    const total=_looksTrialTotal();
    const bal=(_looksData.balances||{}).zarniki||0;
    const can=!hasTrial || bal>=total;
    const label = hasTrial
      ? (can?`✨ Купить и применить всё — ${total}✨`:`🚫 Нужно ${total}✨ (есть ${Math.floor(bal)}✨)`)
      : '✓ Применить';
    actionHtml=`<div class="looks-ba-act">
      <button class="btn btn-sm btn-ghost" onclick="_looksResetTrialAndRerenderSheet()">Сбросить примерку</button>
      <button class="btn btn-sm ${can?'btn-gold':'btn-ghost'}" ${can?'':'disabled'} onclick="_looksBuyAndApplyAll(this)">${label}</button>
    </div>`;
  }
  return `<div id="looks-fit-top">${_looksRenderCard(_looksHeroSel())}</div>
    ${_looksFittingSlotChipsHtml()}
    ${actionHtml}`;
}
function _looksRerenderFittingSheetIfOpen(){
  const dlg=el('modal'); if(dlg && dlg.open){ const b=el('mb'); if(b) b.innerHTML=_looksFittingSheetBodyHtml(); }
}
function _looksResetTrialAndRerenderSheet(){
  _looksReset();   // уже чистит и _looksSel (откат к _looksSaved), и _looksTrial, и обновляет FAB
  _looksRerenderFittingSheetIfOpen();
}
// «Купить и применить всё»: buy_many() за все примеренные-некупленные (если есть),
// затем переносит их в _looksSel и переиспользует существующий _looksApply()
// (равняет _looksSaved под _looksSel через /cosmetics/equip для изменённых
// слотов — включая и платные, теперь уже купленные, и бесплатные перестановки
// СВОИХ предметов, если они тоже были в примерке). После — перезагрузка каталога
// (актуализирует owned-флаги купленных предметов в сетке) и закрытие шторки.
function _looksBuyAndApplyAll(btn){
  if(btn) btn.disabled=true;
  const trialIds=Object.values(_looksTrial);
  const doBuy = trialIds.length
    ? api('/cosmetics/buy-many',{method:'POST',body:JSON.stringify({cosmetic_ids:trialIds})})
    : Promise.resolve(null);
  doBuy.then(r=>{
      if(r){ toast(r.message); refreshCurrBar(); }
      Object.entries(_looksTrial).forEach(([slot,id])=>{ _looksSel[slot]=id; });
      _looksTrial={};
      return _looksApply();
    })
    .then(()=>_looksReloadCatalog())
    .then(()=>CM())
    .catch(e=>{toast(e,false); if(btn) btn.disabled=false;});
}
```

- [ ] **Step 9: Обновить `_looksBuyFromPreview` — очищать примерку слота и обновлять открытую шторку**

Заменить (текущие строки ~577-583):
```js
function _looksBuyFromPreview(id,opt,slot){
  api('/cosmetics/buy',{method:'POST',body:JSON.stringify({cosmetic_id:id,option_index:opt})})
    .then(r=>{toast(r.message); refreshCurrBar(); _looksDirty=true;
      return api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})});})
    .then(()=>{toast('✅ Надето!'); return _looksReloadCatalog();})   // владение изменилось → перезагрузить кэш
    .catch(e=>toast(e,false));
}
```
на:
```js
// Покупка ОДНОГО конкретного предмета + надевание — вызывается и из сетки
// предметов (карточка "🔒 предмет"), и из слот-чипа шторки примерочной ("тап
// покупает именно этот один", Раздел C спеки). После успеха убирает примерку
// ИМЕННО этого слота (не всю _looksTrial целиком — другие примерянные слоты
// остаются нетронутыми) и обновляет открытую шторку, если она сейчас видна.
function _looksBuyFromPreview(id,opt,slot){
  api('/cosmetics/buy',{method:'POST',body:JSON.stringify({cosmetic_id:id,option_index:opt})})
    .then(r=>{toast(r.message); refreshCurrBar(); _looksDirty=true;
      return api('/cosmetics/equip',{method:'POST',body:JSON.stringify({cosmetic_id:id})});})
    .then(()=>{toast('✅ Надето!'); delete _looksTrial[slot]; return _looksReloadCatalog();})
    .then(()=>_looksRerenderFittingSheetIfOpen())
    .catch(e=>toast(e,false));
}
```

- [ ] **Step 10: CSS — FAB и шторка**

В `app.css` добавить в конец файла:

```css

/* ═══ Примерочная — Стадия 4 (2026-07-31): FAB + шторка ══════════════════════ */
.looks-fab-wrap { position: fixed; right: 16px; bottom: 78px; z-index: 60; }
.looks-fab {
  width: 52px; height: 52px; border-radius: 50%; position: relative;
  border: 1px solid var(--border2); background: var(--bg2);
  box-shadow: 0 6px 18px rgba(0,0,0,.45); cursor: pointer; padding: 0;
}
.looks-fab:active { transform: scale(.94); }
.looks-fab-ava { width: 100%; height: 100%; margin: 0; border-radius: 50%; font-size: 24px; }
.looks-fab-badge {
  position: absolute; top: -2px; right: -2px; width: 14px; height: 14px; border-radius: 50%;
  background: var(--gold); box-shadow: 0 0 6px rgba(232,181,77,.6); border: 2px solid var(--bg1);
}

/* Ряд слот-чипов внутри шторки — правило тонированного чипа (DESIGN.md): фон
   ~13% альфы, граница ~30%, текст полным цветом, НЕ сплошная заливка. */
.fit-slotrow { display: flex; gap: 5px; margin: 10px 0 8px; }
.fit-slotchip {
  flex: 1; border-radius: 10px; padding: 7px 3px; text-align: center; font-size: 8.5px;
  background: var(--bg1); border: 1px solid var(--border2); color: var(--muted);
}
.fit-slotchip .ic { font-size: 13px; display: block; margin-bottom: 2px; opacity: .5; filter: grayscale(1); }
.fit-slotchip.owned { color: var(--bright); }
.fit-slotchip.owned .ic { opacity: 1; filter: none; }
.fit-slotchip.trial {
  background: var(--gold-dim); border-color: var(--border); color: var(--gold2);
  cursor: pointer; font-family: inherit;
}
.fit-slotchip.trial .ic { opacity: 1; filter: none; }
.fit-slotchip.trial .price { display: block; margin-top: 2px; font-weight: 700; }
.fit-slotchip.trial:active { transform: scale(.96); }
```

- [ ] **Step 11: Мок `POST /cosmetics/buy-many` в preview_server.mjs**

В `predvestnik_v2/tools/preview_server.mjs` добавить рядом с существующим `'POST /cosmetics/buy-lineup'`:

```js
  'POST /cosmetics/buy-many': { ok: true, message: '🎨 Куплено 2 шт. за 690✨' },
```

- [ ] **Step 12: `node --check` + puppeteer-тест множественной примерки**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

Preview-сервер на 8402 должен быть запущен (`node tools/preview_server.mjs` в фоне). Создать `predvestnik_v2/tools/verify_fitting_room.mjs`:

```js
// Примерочная (Стадия 4): FAB + шторка + множественная примерка НЕСКОЛЬКИХ
// некупленных предметов из РАЗНЫХ слотов одновременно + покупка по одному/всё разом.
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

// FAB виден сразу, без примерки — без бейджа
const fab0 = await page.evaluate(() => ({
  exists: !!document.querySelector('.looks-fab'),
  hasBadge: !!document.querySelector('.looks-fab-badge'),
}));
check('FAB отрендерен на странице', fab0.exists);
check('FAB БЕЗ бейджа, пока нет примерки', !fab0.hasBadge);

// Переключиться в "По слотам", примерить НЕКУПЛЕННЫЙ предмет в слоте name_glow
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 300));
await page.evaluate(() => {
  const card = document.querySelector('#looks-grid-name_glow .looks-card.lc-buyable[data-cos]');
  if (card) card.click();
});
await new Promise(r => setTimeout(r, 300));

// Примерить ЕЩЁ ОДИН некупленный предмет в ДРУГОМ слоте (avatar_frame)
await page.evaluate(() => {
  const card = document.querySelector('#looks-grid-avatar_frame .looks-card.lc-buyable[data-cos]');
  if (card) card.click();
});
await new Promise(r => setTimeout(r, 300));

const trialState = await page.evaluate(() => ({
  trialSlots: Object.keys(_looksTrial),
  fabHasBadge: !!document.querySelector('.looks-fab-badge'),
}));
check('оба слота (name_glow И avatar_frame) одновременно в _looksTrial — не стирают друг друга',
  trialState.trialSlots.includes('name_glow') && trialState.trialSlots.includes('avatar_frame'));
check('FAB показывает бейдж, пока есть неоплаченная примерка', trialState.fabHasBadge);

// Открыть шторку — обе примерки видны разом на карточке и в ряду чипов
await page.click('.looks-fab');
await new Promise(r => setTimeout(r, 400));
const sheetState = await page.evaluate(() => {
  const chips = Array.from(document.querySelectorAll('.fit-slotchip.trial'));
  return {
    modalOpen: document.getElementById('modal').open,
    hasHeroCard: !!document.querySelector('#looks-fit-top .looks-preview'),
    trialChipCount: chips.length,
    hasGoldBtn: document.querySelectorAll('.looks-ba-act .btn-gold').length,
    btnText: (document.querySelector('.looks-ba-act .btn-gold, .looks-ba-act .btn-ghost:last-child') || {}).textContent || '',
  };
});
check('шторка (модалка) открыта', sheetState.modalOpen);
check('в шторке настоящая карточка профиля (.looks-preview)', sheetState.hasHeroCard);
check('в ряду чипов ровно 2 примеренных (не 1, не 0) — обе примерки сохранились одновременно',
  sheetState.trialChipCount === 2);
check('ровно ОДНА золотая кнопка на экране шторки (правило DESIGN.md)', sheetState.hasGoldBtn === 1);
check('текст золотой кнопки — "Купить и применить всё" (не просто "Применить", т.к. есть платное)',
  /Купить и применить/.test(sheetState.btnText));

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

Run: `node predvestnik_v2/tools/verify_fitting_room.mjs`
Expected: `ALL OK`

- [ ] **Step 13: Ручная скриншот-проверка**

Через puppeteer сделать скриншот открытой шторки (390px) в состоянии из Step 12 (2 примерянных предмета) — посмотреть глазами (Read поддерживает изображения): карточка профиля не обрезана, ряд из 6 чипов не переполняет ширину экрана, золотая кнопка одна и не наезжает на текст. Если что-то не помещается — уменьшить `.fit-slotchip` паддинги/шрифт, не увеличивать высоту шторки сверх экрана.

- [ ] **Step 14: Regression — прогнать существующие puppeteer-тесты косметики**

Run:
```bash
for f in predvestnik_v2/tools/verify_slots_*.mjs predvestnik_v2/tools/verify_collections_*.mjs predvestnik_v2/tools/verify_collection_detail_*.mjs predvestnik_v2/tools/verify_looks_no_jump.mjs; do
  echo "=== $f ==="; node "$f" || exit 1
done
```
Expected: все `ALL OK` — ни один из существующих тестов Стадий 1-3 не должен сломаться (особенно `verify_slots_meter.mjs`/`verify_slots_smartrow.mjs`, которые проверяют функции, потерявшие `_looksFocus` в этом таске, и `verify_collection_detail_header.mjs`, который открывает детальный экран через тот же `renderLooks()`).

- [ ] **Step 15: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/preview_server.mjs predvestnik_v2/tools/verify_fitting_room.mjs
git commit -m "feat(cosmetics): примерочная — FAB+шторка, множественная примерка нескольких некупленных предметов разом (Стадия 4)"
```

---

### Task 3: Живой свотч карточек предметов (Раздел D спеки)

**Контекст находки при планировании (не было видно на брейншторме):** свотчи сегодня СТАТИЧНЫ НАМЕРЕННО — `app.css:1973` (`.lc-sw .lc-ava, .lc-sw .lc-nick, .lc-sw .card-fx, .lc-sw.lc-bg, .lc-sw .lc-title { animation: none !important; }`) с комментарием «Перф (ШАГ 5): в свотчах вкладки НЕ гоняем анимации — их там десятки одновременно → лаг/нагрев». Владелец подтвердил (см. диалог): живой свотч, но ТОЛЬКО у карточек, реально видимых на экране прямо сейчас (не у всех разом) — через `IntersectionObserver`, отключается при скролле за пределы видимости.

**Files:**
- Modify: `predvestnik_v2/FastAPI/static/app.css`
- Modify: `predvestnik_v2/FastAPI/static/app.10.js`
- Test: `predvestnik_v2/tools/verify_live_swatch.mjs` (новый)

**Interfaces:**
- Consumes: `.looks-card[data-cos]` (существующий селектор карточек предметов), `_looksRenderSectionGrid(slot)` (существует, `app.10.js`).
- Produces: `_looksObserveSwatches(container)` — вызывается из `_looksRenderSectionGrid`/`renderLooks`, других потребителей нет.

- [ ] **Step 1: Инвертировать правило отключения анимации — статично ПО УМОЛЧАНИЮ, живо только с классом `.lc-sw-live`**

В `app.css` заменить (текущая строка, найти по точному тексту):
```css
/* Перф (ШАГ 5): в свотчах вкладки НЕ гоняем анимации — их там десятки одновременно
   (box-shadow/частицы) → лаг/нагрев. Показываем статичный кадр эффекта; движение
   видно в большом живом превью сверху и на самом профиле (там по 1 экземпляру). */
.lc-sw .lc-ava, .lc-sw .lc-nick, .lc-sw .card-fx, .lc-sw.lc-bg, .lc-sw .lc-title { animation: none !important; }
```
на:
```css
/* Стадия 4 (2026-07-31): раньше свотчи ВСЕГДА статичны (перф — десятки карточек
   разом), но большое "живое" превью сверху, на которое ссылался этот комментарий,
   переехало за FAB+шторку (Task 2) — стало на тап дальше, а не всегда на экране.
   Теперь статично ТОЛЬКО когда карточка НЕ помечена видимой на экране прямо
   сейчас (.lc-sw-live, IntersectionObserver — см. app.10.js::_looksObserveSwatches).
   :not() — если JS-обозреватель по какой-то причине не сработал, класс никогда
   не появится и карточка останется статичной (безопасно по умолчанию, не наоборот). */
.looks-card:not(.lc-sw-live) .lc-sw .lc-ava,
.looks-card:not(.lc-sw-live) .lc-sw .lc-nick,
.looks-card:not(.lc-sw-live) .lc-sw .card-fx,
.looks-card:not(.lc-sw-live) .lc-sw.lc-bg,
.looks-card:not(.lc-sw-live) .lc-sw .lc-title { animation: none !important; }
```

- [ ] **Step 2: `IntersectionObserver` — включает анимацию только видимым карточкам**

В `app.10.js` добавить перед `_looksRenderSectionGrid` (найти по тексту `function _looksRenderSectionGrid(slot){`):

```js
// Живой свотч ТОЛЬКО у карточек, реально видимых на экране прямо сейчас (Раздел D
// спеки 2026-07-31) — не у всех разом (см. правило в app.css рядом с .lc-sw-live).
let _lcSwObserver=null;
function _looksObserveSwatches(container){
  if(!('IntersectionObserver' in window)) return;   // старый браузер → свотчи остаются статичными, safe default
  if(!_lcSwObserver){
    _lcSwObserver=new IntersectionObserver(entries=>{
      entries.forEach(e=>e.target.classList.toggle('lc-sw-live', e.isIntersecting));
    }, {root:null, rootMargin:'50px', threshold:0.1});
  }
  (container||document).querySelectorAll('.looks-card[data-cos]').forEach(el=>_lcSwObserver.observe(el));
}
```

Изменить `_looksRenderSectionGrid`:
```js
function _looksRenderSectionGrid(slot){
  const g=el('looks-grid-'+slot); if(g) g.innerHTML=_looksGridHtml(slot);
}
```
на:
```js
function _looksRenderSectionGrid(slot){
  const g=el('looks-grid-'+slot); if(g){ g.innerHTML=_looksGridHtml(slot); _looksObserveSwatches(g); }
}
```

В `renderLooks()` (изменена в Task 2, Step 4) добавить вызов в самом конце, перед закрывающей `}` функции — заменить последнюю строку тела:
```js
  _looksThemesEnsureLoaded();
  _looksSyncStickyH();
}
```
на:
```js
  _looksThemesEnsureLoaded();
  _looksSyncStickyH();
  _looksObserveSwatches();
}
```

- [ ] **Step 3: `node --check` + puppeteer-тест: видимая карточка анимирована, невидимая — нет**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

Создать `predvestnik_v2/tools/verify_live_swatch.mjs`:
```js
// Живой свотч (Стадия 4, Раздел D): анимация свотча включена ТОЛЬКО у карточек,
// реально видимых на экране прямо сейчас (IntersectionObserver), не у всех разом.
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
await new Promise(r => setTimeout(r, 400));
await page.click('[data-mode="slots"]');
await new Promise(r => setTimeout(r, 500));   // время сработать IntersectionObserver

const state = await page.evaluate(() => {
  const cards = Array.from(document.querySelectorAll('#looks-sec-name_glow .looks-card[data-cos]'));
  const visible = cards.find(c => c.classList.contains('lc-sw-live'));
  const sw = visible ? visible.querySelector('.lc-sw .lc-nick, .lc-sw .lc-ava') : null;
  return {
    hasVisibleLive: !!visible,
    animationName: sw ? getComputedStyle(sw).animationName : null,
  };
});
check('хотя бы одна видимая на экране карточка помечена .lc-sw-live', state.hasVisibleLive);
check('у видимой карточки animationName реального эффекта, не "none"', state.animationName && state.animationName !== 'none');

await browser.close();
if (FAIL.length) { console.error('FAIL:', FAIL); process.exit(1); }
console.log('ALL OK');
```

Run: `node predvestnik_v2/tools/verify_live_swatch.mjs`
Expected: `ALL OK`

- [ ] **Step 4: Regression — существующие тесты «По слотам»**

Run: `node predvestnik_v2/tools/verify_slots_accent.mjs && node predvestnik_v2/tools/verify_slots_empty.mjs && node predvestnik_v2/tools/verify_slots_meter.mjs && node predvestnik_v2/tools/verify_slots_smartrow.mjs`
Expected: все `ALL OK`

- [ ] **Step 5: Commit**

```bash
git add predvestnik_v2/FastAPI/static/app.css predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/tools/verify_live_swatch.mjs
git commit -m "feat(cosmetics): живой свотч карточек предметов только в видимой области экрана (Стадия 4, Раздел D)"
```

---

### Task 4: Финальный прогон — все puppeteer-тесты подряд + компиляция

**Files:** нет новых — только запуск существующего набора.

- [ ] **Step 1: Backend**

Run:
```bash
python -m py_compile predvestnik_v2/services/cosmetics.py predvestnik_v2/FastAPI/routers/cosmetics.py
python predvestnik_v2/tools/test_buy_lineup.py
python predvestnik_v2/tools/test_buy_many.py
```
Expected: все `OK:`, без ошибок компиляции.

- [ ] **Step 2: Все puppeteer-тесты косметики**

Run (preview-сервер на 8402 должен быть запущен):
```bash
for f in predvestnik_v2/tools/verify_slots_*.mjs predvestnik_v2/tools/verify_collections_*.mjs predvestnik_v2/tools/verify_collection_detail_*.mjs predvestnik_v2/tools/verify_looks_no_jump.mjs predvestnik_v2/tools/verify_fitting_room.mjs predvestnik_v2/tools/verify_live_swatch.mjs; do
  echo "=== $f ==="; node "$f" || { echo "FAILED: $f"; }
done
```
Expected: каждый файл заканчивается `ALL OK` (или `✓ Spacing restored correctly` для `verify_slots_spacing.mjs`, у него свой формат). Любой `FAIL:` — вернуться к соответствующему Task и исправить, не считать план завершённым.

Если какой-то файл падает НЕИЗОЛИРОВАННО (проходит в одиночном запуске, но не в общем прогоне подряд) — известная гибкость puppeteer-тестов этого проекта под нагрузкой (см. `.superpowers/sdd/progress.md`, финальное ревью Стадии 3) — перепроверить именно этот файл в одиночном запуске перед тем как считать находкой.

- [ ] **Step 3: `node --check` на весь app.10.js**

Run: `node --check predvestnik_v2/FastAPI/static/app.10.js`
Expected: без вывода

- [ ] **Step 4: Итоговый commit (если Step 2 потребовал правок)**

Если были найдены и исправлены проблемы:
```bash
git add -u predvestnik_v2/FastAPI/static/app.10.js predvestnik_v2/FastAPI/static/app.css predvestnik_v2/tools/
git commit -m "fix(cosmetics): финальный ревью Стадии 4 «примерочная»"
```
Если правок не потребовалось — коммит не нужен, всё уже закоммичено по ходу Tasks 1-3.

---

## Что НЕ входит в эту стадию (отдельные будущие планы)

- **Раздел E спеки** (тонирование аватара под цвет линейки, разведение рамка/гало, тёмный скрим за текстом) — системные фиксы композиции косметики, затрагивают ВСЮ игру (профиль, публичный профиль), не только примерочную. Большой, самостоятельный технический таск (~14 halo-вариантов across 7 линеек) — отдельная стадия.
- **Раздел F спеки** (shared-element анимация открытия коллекции) — независимая, самостоятельная стадия.
- **Раздел G спеки** (гармонизация «Вход»/«Темы»/«Образы»/«Сюрпризы и Крафт» под новый визуальный язык) — визуальный рефакторинг, независимая стадия.
- **Второй сет «Артефакт», аппаратная кнопка «Назад» детального экрана** — уже отложены раньше (см. спеку 2026-07-31 и план Стадии 3).
