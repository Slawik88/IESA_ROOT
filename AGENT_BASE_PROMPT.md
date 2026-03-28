# БАЗОВЫЙ ПРОМТ ДЛЯ AI-АГЕНТА — ПРОЕКТ IESA ROOT / PredvestnikBot

> **Вставляй этот промт В НАЧАЛО каждого нового запроса к агенту.**  
> Он вводит агента в полный технический контекст проекта и задаёт стандарты написания кода.

---

## 1. ОПИСАНИЕ ПРОЕКТА

Проект состоит из **двух взаимосвязанных систем**:

### A. `PredvestnikBot/` — Telegram-бот (Python, aiogram 3.x, asyncpg)
- Telegram-бот для управления сообществом в групповых чатах
- Экономика (Мора), браки, питомцы, гача, боссы, экспедиции, облигации
- Асинхронный, работает на своём event loop
- БД: PostgreSQL (async через `asyncpg` + хелпер `postgres_connect()`)

### B. `IESA_ROOT/` — Django-приложение + Mini App API (Python, Django, psycopg2)
- Публичный сайт IESA (блог, галерея, продукты, пользователи)
- Mini App (WebApp через Telegram) — REST API для фронтенда
- Синхронный Django, отдельный event loop от бота
- БД: та же PostgreSQL, но через `psycopg2` (sync), одна и та же база данных

**Обе системы читают/пишут в ОДНУ базу PostgreSQL.** Таблицы бота доступны из Mini App через psycopg2.

---

## 2. ТЕХНОЛОГИЧЕСКИЙ СТЕК

| Компонент | Технология |
|-----------|-----------|
| Telegram-бот | aiogram 3.x, Python 3.11+ |
| Async DB (бот) | asyncpg + `postgres_connect()` context manager |
| Sync DB (Django) | psycopg2, ph = `%s` placeholder |
| Web-фреймворк | Django 4.x + Daphne (ASGI) |
| Кеш | In-memory LRU (`services/smart_cache.py`), 60s TTL |
| Планировщик | asyncio-based hourly loop (`utils/scheduler.py`) |
| Хостинг | DigitalOcean App Platform |
| Git | master branch → `https://github.com/Slawik88/IESA_ROOT.git` |
| Валюта | **Мора** 🪙 (внутриигровая, не реальная) |

---

## 3. СТРУКТУРА ПРОЕКТА

```
IESA_ROOT/
├── PredvestnikBot/          ← Telegram-бот
│   ├── main.py              ← Точка входа: init_db, регистрация роутеров, запуск планировщика
│   ├── config.py            ← Все константы, env vars, каталоги цен
│   ├── shared_prices.py     ← ЕДИНСТВЕННЫЙ источник всех цен (импортировать отсюда!)
│   ├── database/
│   │   ├── postgres.py      ← postgres_connect(), пул соединений, _maybe_datetime()
│   │   └── db.py            ← 200+ async DB-функций (init_db, get_*, add_*, upsert_*)
│   ├── api/                 ← Бизнес-логика (shared между ботом и Mini App)
│   │   ├── economy.py       ← transfer_mora() — атомарная транзакция (deduct+credit+tax)
│   │   ├── gacha.py         ← gacha_roll(), item pools (_JUNK_ITEMS, _COMMON_ITEMS, …)
│   │   ├── boss.py          ← record_miniapp_damage(), BOSS_DAILY_DAMAGE_LIMIT=50_000
│   │   ├── marriage.py      ← family_withdraw(), deduct_family_pool() с FOR UPDATE
│   │   ├── expeditions.py   ← start_expedition(), get_expedition_status()
│   │   ├── shop.py, bank.py, bonds.py, pets.py, casino.py, loans.py, quests.py, …
│   ├── handlers/            ← aiogram Router-ы (30+ файлов)
│   ├── services/            ← Вспомогательные сервисы
│   │   ├── boss_service.py  ← BOSS_DAILY_DAMAGE_LIMIT=50_000 (канонично, не менять!)
│   │   ├── message_buffer.py← Буфер сообщений, лимит 50_000 записей
│   │   └── smart_cache.py   ← LRU-кеш с TTL
│   ├── filters/             ← BotCommand(), RankFilter()
│   ├── middlewares/         ← AutoModMiddleware (XP, антифлуд)
│   └── utils/
│       ├── scheduler.py     ← Фоновые задачи (лотерея, дилижанс, дивиденды…)
│       ├── helpers.py       ← user_mention(), resolve_target(), bot_today()
│       └── ranks.py         ← has_permission(), иерархия рангов
│
└── IESA_ROOT/
    ├── IESA_ROOT/
    │   ├── settings.py      ← Django settings
    │   ├── urls.py          ← URL routing
    │   └── miniapp_views.py ← 50+ Mini App API-эндпоинтов
    ├── blog/, core/, users/, gallery/, products/, notifications/
    └── templates/, static/, media/
```

---

## 4. КАНОНИЧЕСКИЕ ИСТОЧНИКИ ЦЕН (НИКОГДА не дублировать!)

Все цены берутся **только из `shared_prices.py`**. Никаких локальных констант в хендлерах!

```python
# shared_prices.py (фрагмент)
GACHA_SINGLE_PRICE    = 120   # Стандартная молитва (одиночная)
GACHA_MULTI_PRICE     = 1000  # Стандартная молитва (×10)
GACHA_SINGLES_SINGLE  = 110   # Одиночная молитва (singles)
GACHA_SINGLES_MULTI   = 950   # Х10 молитва (singles)
GACHA_PITY_MAX        = 40    # Гарантированный 5★ каждые N роллов
PRICE_VIP             = 300
# Каталоги: FRAMES_CATALOG, COSMETICS_CATALOG, PET_COLOR_CATALOG,
#           FOOD_ITEMS, POTIONS_CATALOG, BOND_DEFAULTS, BANK_PLANS
```

```python
# Правильный импорт в любом файле:
from shared_prices import GACHA_SINGLES_SINGLE, GACHA_SINGLES_MULTI
# Неправильно — НЕ ДЕЛАТЬ:
SINGLES_GACHA_SINGLE = 150  # дубль, устаревшие значения
```

---

## 5. ПАТТЕРН ASYNC DB (бот)

**Единственно правильный способ работы с БД в боте:**

```python
from database.postgres import postgres_connect

async def my_db_function(user_id: int, chat_id: int, amount: int) -> dict | None:
    async with postgres_connect() as db:
        # Одиночный запрос:
        row = await db.fetchrow(
            "SELECT balance FROM user_mora WHERE user_id=$1 AND chat_id=$2",
            user_id, chat_id
        )
        # Несколько операций в одной транзакции:
        async with db.transaction():
            await db.execute(
                "UPDATE user_mora SET balance=balance-$1 WHERE user_id=$2 AND chat_id=$3",
                amount, user_id, chat_id
            )
            await db.execute(
                "INSERT INTO wallet_ledger(user_id, chat_id, direction, amount, source)"
                " VALUES($1,$2,'out',$3,'transfer')",
                user_id, chat_id, amount
            )
    return {"ok": True}
```

**Ключевые правила:**
- Placeholder: `$1, $2, $3, ...` (asyncpg-стиль, НЕ `?` и НЕ `%s`)
- `db.fetchrow()` → одна строка или `None`
- `db.fetch()` → список строк
- `db.fetchval()` → одно скалярное значение
- `db.execute()` → DML без результата
- **Транзакции**: `async with db.transaction():` для атомарных операций
- **Блокировки**: `SELECT ... FOR UPDATE` при TOCTOU-зависимых операциях (кошелёк, перевод)
- Строки возвращаются как `asyncpg.Record` — доступ: `row["column"]` или `row[0]`

---

## 6. ПАТТЕРН SYNC DB (Mini App / miniapp_views.py)

```python
# Подключение к боту:
conn, db_type = _get_bot_db_connection()
ph = "%s"   # psycopg2 placeholder
cur = conn.cursor()

# Запрос:
cur.execute(f"SELECT balance FROM user_mora WHERE user_id={ph} AND chat_id={ph}", (uid, cid))
row = cur.fetchone()
balance = row[0] if row else 0

# Batch IN-запрос (вместо N отдельных запросов!):
ids = [1, 2, 3]
placeholders = ",".join([ph] * len(ids))
cur.execute(f"SELECT id, item_name FROM gacha_inventory WHERE id IN ({placeholders})", tuple(ids))
rows = cur.fetchall()

# Всегда закрывать:
conn.close()
```

**Ключевые правила для miniapp_views.py:**
- Ловить `Exception` → `logger.exception("context"); return JsonResponse({"error": "Внутренняя ошибка сервера"}, status=500)`
- **Никогда** `str(exc)` в `status=500` ответах — утечка внутренних данных!
- `ValueError` / `LookupError` можно возвращать в `status=400` — это intentional user-facing messages
- Аутентификация: `uid = _validate_init_data(request.headers.get("X-Telegram-Init-Data",""))` → `if not uid: return JsonResponse({"error":"Unauthorized"}, status=401)`

---

## 7. ПАТТЕРН ХЕНДЛЕРА (бот)

```python
# handlers/my_feature.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from filters.bot_command import BotCommand
from database.db import get_mora, deduct_mora
from shared_prices import MY_PRICE

router = Router()

@router.message(BotCommand("моякоманда", "mycmd"))
async def handle_my_command(msg: Message):
    uid = msg.from_user.id
    cid = msg.chat.id
    
    mora = await get_mora(uid, cid)
    balance = mora["balance"] if mora else 0
    
    if balance < MY_PRICE:
        await msg.answer(f"❌ Недостаточно Моры. Нужно: {MY_PRICE} 🪙, у тебя: {balance} 🪙")
        return
    
    # Бизнес-логика через api/ модуль:
    from api.my_feature import execute_feature
    result = await execute_feature(uid, cid)
    
    kbd = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{uid}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])
    await msg.answer(f"<b>Результат:</b> {result['data']}", reply_markup=kbd)

@router.callback_query(F.data.startswith("confirm_"))
async def handle_confirm(cb: CallbackQuery):
    uid = int(cb.data.split("_")[1])
    await cb.message.edit_text("✅ Выполнено!")
    await cb.answer()
```

**Регистрация роутера в main.py** (перед `extras`):
```python
from handlers import my_feature
dp.include_router(my_feature.router)
```

---

## 8. ПАТТЕРН API-МОДУЛЯ (shared logic)

```python
# api/my_feature.py
# Бизнес-логика, используемая и ботом, и Mini App

from database.postgres import postgres_connect
from database.db import get_mora, add_mora

async def execute_feature(user_id: int, chat_id: int, amount: int) -> dict:
    """
    Описание функции.
    
    Returns:
        {"ok": True, "data": {...}}  или  {"ok": False, "error": "..."}
    Raises:
        ValueError: если входные данные некорректны
    """
    async with postgres_connect() as db:
        async with db.transaction():
            row = await db.fetchrow(
                "SELECT balance FROM user_mora WHERE user_id=$1 AND chat_id=$2 FOR UPDATE",
                user_id, chat_id
            )
            if not row or row["balance"] < amount:
                raise ValueError("Недостаточно Моры")
            await db.execute(
                "UPDATE user_mora SET balance=balance-$1 WHERE user_id=$2 AND chat_id=$3",
                amount, user_id, chat_id
            )
    return {"ok": True, "data": {"spent": amount}}
```

---

## 9. ПАТТЕРН ПЛАНИРОВЩИКА (`utils/scheduler.py`)

```python
# Гарды задач сохраняются в БД, а не в памяти!
from database.db import get_scheduler_state, set_scheduler_state

async def _task_my_event(bot: Bot) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    last = await get_scheduler_state("my_event_last_date")
    if last == today:
        return  # Уже выполнялось сегодня
    
    # ... логика задачи ...
    
    await set_scheduler_state("my_event_last_date", today)
```

**Доступные task_key для `scheduler_state`:**
- `"chest_next_hour"` — следующий час сундука
- `"diligence_last_date"` — дата последнего дилижанса
- `"dividend_last_date"` — дата последних дивидендов
- `"bond_price_last_update"` — дата обновления цен облигаций

---

## 10. ТАБЛИЦЫ БАЗЫ ДАННЫХ

### Основные (60+ таблиц):

| Таблица | PK / UNIQUE | Назначение |
|---------|------------|------------|
| `users` | `user_id BIGINT PK` | Глобальный профиль, ранг, бан, warns |
| `user_stats` | `(user_id, chat_id)` | XP, уровень, репутация, bio, кастом-тайтл |
| `user_mora` | `(user_id, chat_id)` | Баланс Моры, VIP, бусты, стрик |
| `chats` | `chat_id BIGINT PK` | Зарегистрированные группы |
| `chat_settings` | `chat_id BIGINT PK` | Настройки чата (антифлуд, приветствие, ...) |
| `marriages` | `(user_id, chat_id)` | Брак (симметрично: 2 строки на пару) |
| `family_wallet` | `(chat_id, user_id)` | Семейный кошелёк |
| `pets` | `(user_id, chat_id)` | Питомец: тип, имя, усталость, цвет |
| `pet_expeditions` | `(user_id, chat_id)` | Текущая экспедиция питомца |
| `gacha_inventory` | `id SERIAL PK` | Гача-инвентарь: предмет, редкость, статы |
| `user_rpg_stats` | `(user_id, chat_id)` | RPG: HP/ATK/DEF/CRIT, equipped IDs |
| `boss_damage_log` | `id SERIAL PK` | Урон боссу (session_date TEXT) |
| `bank_deposits` | `id SERIAL PK` | Вклады (3/7/14 дней, rate REAL) |
| `user_bonds` | `(user_id, chat_id, bond_key)` | Облигации пользователя |
| `bond_prices` | `(bond_key, chat_id)` | Текущая цена облигации |
| `chat_treasury` | `chat_id BIGINT PK` | Казна чата |
| `casino_lottery` | `(chat_id, user_id, week_key)` | Лотерейные билеты |
| `daily_checkin` | `(user_id, chat_id)` | Стрик ежедневного чеккина |
| `user_quests` | `(user_id, chat_id, quest_date)` | Ежедневные задания |
| `wallet_ledger` | `id SERIAL PK` | Лог транзакций (60-дн. TTL) |
| `scheduler_state` | `task_key TEXT PK` | Персистентные гарды планировщика |
| `solo_boss_sessions` | `(user_id, chat_id, session_date)` | Соло-сессия против босса |
| `couple_boss_sessions` | `id SERIAL PK` | Парная сессия против босса |
| `espionage_log` | `id SERIAL PK` | Лог шпионажа |
| `mora_loans` | `id SERIAL PK` | Займы Моры |
| `active_buffs` | `id SERIAL PK` | Активные баффы пользователя |
| `notes` | `(chat_id, name)` | Заметки чата |
| `blacklist` | `(chat_id, word)` | Чёрный список слов |
| `rep_log` | `id SERIAL PK` | Лог репутации (кто, кому, сколько) |

---

## 11. ИЕРАРХИЯ РАНГОВ

```
developer > owner > admin > moderator > helper > vip > user
```
- Хендлеры ограничивают доступ через `RankFilter(min_rank="admin")`
- `DEVELOPER_ID = 1460945748` — обходит все ограничения
- Не менять порядок роутеров в main.py (важен приоритет)

---

## 12. КЛЮЧЕВЫЕ ПРАВИЛА НАПИСАНИЯ КОДА

### ✅ ОБЯЗАТЕЛЬНО:
1. **Цены** — только из `shared_prices.py`, никаких локальных дублей
2. **datetime** — всегда `datetime.now(timezone.utc)`, НИКОГДА `datetime.utcnow()`
3. **Транзакции** — атомарность для операций вида "снять + зачислить + лог"
4. **FOR UPDATE** — при TOCTOU (проверка баланса → списание — всегда в одной транзакции)
5. **Batch-запросы** — `WHERE id IN (...)` вместо цикла с отдельными `SELECT`
6. **N+1** — не допускать: если в цикле нужны данные из БД — batching или JOIN
7. **Ошибки (status=500)** — `logger.exception("ctx"); return JsonResponse({"error":"Внутренняя ошибка сервера"}, status=500)`
8. **Буфер сообщений** — не превышать `_MAX_BUFFER_SIZE = 50_000`
9. **Гарды планировщика** — только через `scheduler_state` (не in-memory переменные)
10. **Placeholder asyncpg** — `$1, $2, ...` (не `?`, не `%s`)
11. **Placeholder psycopg2** — `%s` (не `?`, не `$1`)

### ❌ ЗАПРЕЩЕНО:
- `datetime.utcnow()` — deprecated, не даёт timezone-aware объект
- `str(exc)` в `status=500` ответах Mini App — утечка внутренних данных
- Дублировать константы из `shared_prices.py`
- Дублировать логику из `api/` в хендлерах
- Дублировать пулы товаров из `api/gacha.py` в `handlers/gacha.py`
- In-memory гарды в scheduler (сбрасываются при перезапуске)
- `try/except: FALLBACK_DICT = {...}` для config-импортов — падать с ошибкой, не маскировать
- Запросы в цикле (`for item in items: cur.execute(...)`) — только batch

---

## 13. АРХИТЕКТУРНЫЙ ПРИНЦИП: "КОД КАК ЕДИНЫЙ ОРГАНИЗМ ЧЕРЕЗ API"

```
handlers/*  →  api/*  →  database/db.py  →  PostgreSQL
     ↑              ↑
miniapp_views.py ───┘  (тоже использует api/ через async_to_sync или напрямую)
```

- **handlers** — только UI-логика (разбор аргументов, форматирование ответа, клавиатуры)
- **api** — вся бизнес-логика, валидация, транзакции; shared между ботом и Mini App
- **database/db.py** — только CRUD-функции, никакой бизнес-логики
- **miniapp_views.py** — только HTTP-слой (аутентификация, JSON-ответы), логика в api/

---

## 14. ЭКОНОМИКА: ПРОГРЕССИВНЫЙ НАЛОГ НА ПЕРЕВОДЫ

```
Перевод Моры через transfer_mora() (api/economy.py):
  ≤ 1000  →  налог 3%
  ≤ 5000  →  налог 7%
  > 5000  →  налог 8%
Налог идёт в казну чата (chat_treasury)
Источник: source='transfer' в treasury_log
```

---

## 15. ГАЧА-СИСТЕМА

```python
# Пулы — только из api/gacha.py:
from api.gacha import _JUNK_ITEMS, _COMMON_ITEMS, _RARE_ITEMS, _LEGENDARY_ITEMS

# Роллы — только через gacha_roll():
from api.gacha import gacha_roll
result = await gacha_roll(uid, cid, count=1, wallet_type="mora")
# result["items"] → список предметов с полями: item_key, item_name, rarity, ...

# Pity: гарантированный legendary каждые GACHA_PITY_MAX=40 роллов
# Редкости: "junk" ⚪, "common" 🟢, "rare" 🟣, "legendary" 🟡
```

---

## 16. БОСС-СИСТЕМА

```
BOSS_DAILY_DAMAGE_LIMIT = 50_000  (канонично в api/boss.py И services/boss_service.py)
Урон буферизуется 60 секунд, потом сбрасывается в БД (_boss_flush_loop)
Таблица: boss_damage_log (user_id, chat_id, damage, session_date TEXT)
```

---

## 17. ПРИМЕР ДОБАВЛЕНИЯ ПОЛНОЙ ФИЧИ (конец-в-конец)

**Задача: добавить команду `бот дуэль @user`**

1. `api/duel.py` — бизнес-логика (атомарная транзакция, валидация)
2. `handlers/duel.py` — Router, BotCommand("дуэль"), keyboard, FSM если нужен
3. `main.py` — `dp.include_router(duel.router)` перед `extras`
4. `database/db.py` — новые CRUD-функции если нужна новая таблица
5. `database/db.py:init_db()` — CREATE TABLE IF NOT EXISTS новой таблицы
6. `miniapp_views.py` — если нужен API-эндпоинт для Mini App
7. `shared_prices.py` — если есть стоимость дуэли

---

## 18. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ

| Переменная | Использование |
|-----------|--------------|
| `PREDVESTNIK_BOT_TOKEN` / `BOT_TOKEN` | Токен Telegram-бота |
| `PREDVESTNIK_DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY_DJANGO` | Django SECRET_KEY |
| `DEBUG` | `'true'/'false'` |
| `MINI_APP_URL` | URL Mini App (DO App Platform) |

---

*Этот промт сгенерирован автоматически на основе полного анализа кодовой базы проекта по состоянию на 28 марта 2026 г.*
