# CODEBASE AUDIT — Predvestnik V2
> Полный технический аудит проекта для передачи контекста в AI-ассистент.
> Актуален на: 2026-05-11

---

## 1. ЧТО ЭТО ЗА ПРОЕКТ

**Predvestnik V2** — гибридная игровая экосистема:
- **Telegram-бот** (Aiogram 3.x, Python 3.11+) — основной интерфейс игры
- **Веб-панель** (Django 6.x) — профиль игрока, статистика

Общая база данных — **SQLite** в режиме **WAL** (Write-Ahead Logging), файл `db.sqlite3` в корне.

Игра содержит:
- RPG-механику (уровни, опыт, ранги)
- Систему питомцев с гача-механикой
- Экономику с двумя валютами (Мора 🪙, Алмазы 💎)
- Систему браков и семейного банка
- Модерацию с варнами, банами, иммунитетом
- Систему экспедиций (отправить питомца в поход)
- Чистку чата (purge system)

---

## 2. ТЕХНОЛОГИЧЕСКИЙ СТЕК

| Компонент | Технология | Версия |
|---|---|---|
| Bot framework | Aiogram | 3.x |
| DB driver (async) | aiosqlite | latest |
| Web framework | Django | 6.x |
| Config | python-dotenv | 1.2.2 |
| Logging | loguru | latest |
| Python | CPython | 3.11+ |

**Виртуальное окружение:** `.venv/` в корне проекта.
**Запуск бота:** `python -m bot` из корня проекта.
**Запуск сайта:** `python manage.py runserver` из корня.

---

## 3. СТРУКТУРА ПАПОК (ПОЛНАЯ)

```
predvestnik_v2/                      ← КОРЕНЬ ПРОЕКТА
│
├── .env                             ← секреты (не в git)
├── db.sqlite3                       ← единая SQLite база
├── manage.py                        ← Django management
│
├── core/                            ← DOMAIN LAYER (нет внешних зависимостей)
│   ├── __init__.py
│   ├── constants.py                 ← ВСЕ игровые числа
│   └── registry.py                  ← реестр предметов, питомцев, гача, экспедиций
│
├── services/                        ← SERVICE LAYER (нет bot.* / django.*)
│   ├── __init__.py
│   ├── economy.py                   ← EconomyService (скидка черепахи)
│   ├── leveling.py                  ← LevelingService (XP, level-up, сова)
│   ├── roles.py                     ← иерархия рангов, проверка прав
│   ├── moderation.py                ← check_mod_rights, check_admin_rights
│   ├── marriage.py                  ← check_marriage_proposal
│   ├── expedition.py                ← calculate_reward (сокол, лиса)
│   └── formatting.py                ← format_currency, safe_html, ...
│
├── infrastructure/                  ← INFRASTRUCTURE LAYER (только SQL)
│   ├── __init__.py
│   ├── database.py                  ← WAL-mode aiosqlite factory
│   └── repositories/
│       ├── __init__.py
│       ├── economy.py               ← get_balance, add_reward, spend_mora, buy_item, ...
│       ├── users.py                 ← update_user, get_user_id_by_username, ...
│       ├── chat.py                  ← increment_stats_and_get_xp, update_level, ...
│       ├── zoo.py                   ← open_egg, get_user_pets, get_pet_by_id, ...
│       ├── marriages.py             ← get_user_marriage, family_bank_transaction, ...
│       ├── moderation.py            ← add_warn, remove_warn, get_chat_settings, ...
│       ├── stats.py                 ← get_top_messages, get_inactive_users
│       └── routing.py               ← create_bind_token, bind_admin_chat, ...
│
├── bot/                             ← BOT ADAPTER (только Telegram UI)
│   ├── __main__.py                  ← точка входа (python -m bot)
│   ├── config.py                    ← Config dataclass, загрузка .env
│   │
│   ├── core/
│   │   ├── database.py              ← init_db() — создание таблиц при старте
│   │   └── registry.py              ← re-export шим → core.registry
│   │
│   ├── database/                    ← re-export шимы → infrastructure/repositories/
│   │   ├── economy.py
│   │   ├── users.py
│   │   ├── chat.py
│   │   ├── zoo.py
│   │   ├── marriages.py
│   │   ├── moderation.py
│   │   ├── stats.py
│   │   └── routing.py
│   │
│   ├── services/                    ← инжектирующие шимы → services/
│   │   ├── leveling.py              ← вставляет config.timezone_offset
│   │   ├── roles.py                 ← вставляет config.developer_id
│   │   ├── moderation.py            ← вставляет config.developer_id
│   │   ├── utils.py                 ← re-export formatting + resolve_target
│   │   ├── marriage.py              ← re-export шим
│   │   └── scheduler.py             ← фоновая задача экспедиций
│   │
│   ├── handlers/                    ← обработчики команд (UI only)
│   │   ├── __init__.py              ← агрегирует все роутеры в main_router
│   │   ├── common.py                ← /help, /start
│   │   ├── economy.py               ← /balance, /inventory, /pay, /give
│   │   ├── shop.py                  ← /shop, покупка через EconomyService
│   │   ├── zoo.py                   ← /zoo, управление питомцами
│   │   ├── expeditions.py           ← /expedition, отправка в поход
│   │   ├── inventory.py             ← /inventory, открытие яиц
│   │   ├── marriage.py              ← /marry, /divorce, /family
│   │   ├── profile.py               ← /profile, /me
│   │   ├── admin.py                 ← /setrank
│   │   ├── moderation.py            ← /warn, /unwarn, /ban, /kick, /mute
│   │   ├── purge.py                 ← /purge, система чистки
│   │   ├── stats.py                 ← /top, /inactive
│   │   ├── routing.py               ← /bind_admin_chat
│   │   └── events.py                ← события вход/выход пользователя
│   │
│   ├── middlewares/
│   │   └── db.py                    ← открывает DB соединение, регает юзера, даёт XP
│   │
│   ├── filters/
│   │   └── text_commands.py         ← TextCmd фильтр для текстовых алиасов команд
│   │
│   ├── keyboards/
│   │   └── inline_kbs.py            ← инлайн-клавиатуры
│   │
│   └── lexicon/
│       └── strings.py               ← локализованные строки
│
├── dashboard/                       ← WEB ADAPTER (Django app)
│   ├── models.py                    ← Django ORM модели (managed=False, readonly)
│   ├── views.py                     ← user_profile view (использует core/ и services/)
│   ├── urls.py
│   ├── admin.py
│   └── templates/dashboard/
│       └── profile.html
│
└── webpanel/                        ← Django project settings
    ├── settings.py
    ├── urls.py
    ├── asgi.py
    └── wsgi.py
```

---

## 4. ГЛАВНОЕ ПРАВИЛО АРХИТЕКТУРЫ

### Закон изоляции слоёв:
```
core/      ← НЕТ ИМПОРТОВ снаружи вообще
services/  ← ТОЛЬКО из core/ и infrastructure/
infrastructure/ ← ТОЛЬКО aiosqlite, стандартная библиотека
bot/       ← ТОЛЬКО из services/, infrastructure/, core/, aiogram
web/       ← ТОЛЬКО из services/, core/, django
```

**Нарушение:** `services/` импортирует что-то из `bot.` — это ЗАПРЕЩЕНО.

### Как правильно добавить новую механику:
1. Число/константу → `core/constants.py`
2. Новый предмет/питомца → `core/registry.py`
3. SQL-запрос → `infrastructure/repositories/<нужный>.py`
4. Бизнес-логику → `services/<нужный>.py`
5. Telegram-UI → `bot/handlers/<нужный>.py`
6. Веб-UI → `dashboard/views.py` + шаблон

---

## 5. ФАЙЛ КОНФИГУРАЦИИ

### `.env` (в корне, НЕ в git):
```
BOT_TOKEN=<токен бота>
DB_PATH=db.sqlite3
DEVELOPER_ID=<telegram_id разработчика>
TIMEZONE_OFFSET=+3 hours
```

### `bot/config.py`:
```python
@dataclass(frozen=True)
class Config:
    bot_token: str
    db_path: str          # абсолютный путь к db.sqlite3
    developer_id: int     # Telegram ID супер-админа
    timezone_offset: str  # для SQLite strftime: "+3 hours"

config = Config(...)  # синглтон, загружается из .env
```

---

## 6. СХЕМА БАЗЫ ДАННЫХ

### Таблица `users` — глобальные данные игрока
| Колонка | Тип | Описание |
|---|---|---|
| user_tg_id | INTEGER PK | Telegram ID |
| user_tg_username | TEXT | @username |
| user_balance_mora | REAL | Баланс Моры 🪙 |
| user_balance_diamonds | REAL | Баланс Алмазов 💎 |
| global_rank | INTEGER | 0=User, 1=Helper, 2=SrHelper |
| user_is_active | BOOLEAN | Активен ли |

### Таблица `user_chat_stats` — статистика в конкретном чате
| Колонка | Тип | Описание |
|---|---|---|
| user_tg_id, chat_tg_id | PK | Составной ключ |
| user_level | INTEGER | Текущий уровень |
| user_xp | INTEGER | Накопленный XP |
| local_rank | INTEGER | 0-6 (Пользователь → Владелец) |
| user_messages_count_per_day/week/month/all_time | INTEGER | Счётчики |
| last_message_at | TIMESTAMP | Последнее сообщение |
| is_left | BOOLEAN | Покинул чат |
| joined_at | TIMESTAMP | Дата вступления |
| immune_until | TIMESTAMP | До когда иммунитет |
| is_immune | BOOLEAN | Постоянный иммунитет |
| warnings | INTEGER | Количество варнов |

### Таблица `inventory` — инвентарь
| Колонка | Тип | Описание |
|---|---|---|
| user_id, item_id | PK | Составной ключ |
| quantity | INTEGER | Количество |

### Таблица `pets` — питомцы
| Колонка | Тип | Описание |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| owner_id | INTEGER | Telegram ID владельца |
| marriage_id | INTEGER NULL | ID брака (семейный питомец) |
| name | TEXT | Имя питомца |
| species_id | TEXT | Вид: 'hamster', 'owl', 'turtle', ... |
| rarity | TEXT | 'common', 'rare', 'epic', 'legendary' |
| placement | TEXT | 'active', 'passive', 'storage' |
| fatigue | INTEGER | Усталость 0–100 |
| is_summoned | BOOLEAN | Из Яйца Призыва |
| buff_active_until | TIMESTAMP | Активный бафф от еды |

### Таблица `active_expeditions` — текущие походы
| Колонка | Тип | Описание |
|---|---|---|
| pet_id | INTEGER PK | |
| chat_id | INTEGER | Откуда отправили |
| duration_hours | INTEGER | 2/4/6/8 |
| cost_mora | REAL | Стоимость |
| ends_at | TIMESTAMP | Время завершения |

### Таблица `marriages` — браки
| Колонка | Тип | Описание |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| chat_id | INTEGER | Чат где заключён брак |
| user1_id, user2_id | INTEGER | Партнёры |
| user1_name, user2_name | TEXT | Имена |
| marriage_date | TIMESTAMP | |
| family_balance | REAL | Семейный банк |

### Таблица `chat_settings` — настройки чата
| Колонка | Тип | Описание |
|---|---|---|
| chat_id | INTEGER PK | |
| shield_duration_days | INTEGER | Дней иммунитета новичку |
| max_warnings | INTEGER | Лимит варнов |
| is_purging | BOOLEAN | Режим чистки активен |
| purge_min_rank | INTEGER | Минимальный ранг для bypass purge |

### Таблица `user_zoo_stats`
| Колонка | Тип | Описание |
|---|---|---|
| user_id | INTEGER PK | |
| max_slots | INTEGER | Максимум слотов (default 3) |
| wolf_cooldown_until | TIMESTAMP | Когда волк снова заблокирует варн |
| last_income_collection | TIMESTAMP | Последний сбор дохода хомяка |

### Остальные таблицы
- `user_warnings` — история варнов (id, chat_id, user_id, admin_id, reason, created_at)
- `moderation_logs` — лог банов/киков/мутов (id, chat_id, user_id, admin_id, action, created_at)
- `chat_links` — привязка admin-чата (main_chat_id → admin_chat_id)
- `chat_bind_tokens` — одноразовые токены привязки
- `daily_user_stats` — сообщения по дням (user_id, chat_id, date, message_count)

---

## 7. ИГРОВЫЕ КОНСТАНТЫ (core/constants.py)

```python
# Левелинг
XP_PER_MESSAGE = 10          # базовый XP за сообщение
XP_PER_LEVEL = 3000          # XP для следующего уровня
MORA_PER_LEVEL = 200.0       # награда за уровень (Мора)
DIAMONDS_PER_LEVEL = 0.5     # награда за уровень (Алмазы)

# Баффы питомцев
TURTLE_DISCOUNT = 0.95       # множитель цены в магазине (-5%)
OWL_BONUS_XP = 1             # доп. XP за сообщение
DOG_EXPEDITION_SPEED = 0.9   # множитель времени похода (-10%)
FALCON_LOOT_BONUS = 1.15     # множитель награды в походе (+15%)
FOX_DIAMOND_CHANCE = 0.05    # шанс найти Алмаз в походе (5%)
HAMSTER_DAILY_INCOME = 20.0  # Мора/день от хомяка

DRAGON_BANK_BONUS = 50_000.0         # доп. лимит семейного банка
DRAGON_FREE_FOOD_CHANCE = 0.10       # шанс не потратить корм (10%)
UNICORN_FAMILY_FATIGUE_CAP = 10      # макс. прирост усталости семьи/день

# Экономика
FAMILY_BANK_DEFAULT_CAP = 50_000.0

# Питомцы
PET_FATIGUE_WARN_THRESHOLD = 80      # усталость для предупреждения
PET_PLACEMENT_FATIGUE_RESTORE = 30   # усталость снимается при размещении
SOUL_SHARDS_FOR_SUMMON_EGG = 5       # осколков для Яйца Призыва

# Модерация
WOLF_WARN_BLOCK_COOLDOWN_DAYS = 7    # дней между блокировками варна волком
DEFAULT_MAX_WARNINGS = 3
DEFAULT_SHIELD_DURATION_DAYS = 7

# Purge
DEFAULT_PURGE_NORM = 50              # минимум сообщений за период
DEFAULT_PURGE_PERIOD_DAYS = 7
```

---

## 8. РЕЕСТР ИГРОВЫХ ДАННЫХ (core/registry.py)

### ITEMS_REGISTRY — предметы
```python
ITEMS_REGISTRY = {
    "soul_shard": { "name": "💠 Осколок Души", "category": "material", ... },
    # ЯЙЦА:
    "egg_basic":  { "name": "🥚 Базовое Яйцо",    "category": "egg", "price_mora": 500, ... },
    "egg_silver": { "name": "🥈 Серебряное Яйцо", "category": "egg", ... },
    "egg_gold":   { "name": "🪙 Золотое Яйцо",    "category": "egg", "price_diamonds": 50, ... },
    "egg_mythic": { "name": "💎 Мифическое Яйцо", "category": "egg", "price_diamonds": 150, ... },
    "egg_unity":  { "name": "💖 Яйцо Единства",   "category": "egg", ... },  # только для семей
    "egg_summon": { "name": "🔮 Яйцо Призыва",    "category": "egg", ... },  # крафт из 5 осколков
    # ЕДА:
    "food_basic":   { "price_mora": 50,  "fatigue_restore": 15, ... },
    "food_elite":   { "price_mora": 150, "fatigue_restore": 50, ... },
    "food_energy":  { "price_mora": 100, "fatigue_restore": 20, "buff": "expedition_cd_reset", ... },
    "food_diamond": { "price_diamonds": 5, "fatigue_restore": 100, "buff": "efficiency_20", "duration_hours": 24, ... },
}
```

### PET_SPECIES — виды питомцев
```python
PET_SPECIES = {
    # common
    "hamster": { "name": "🐹 Хомяк-банкир",       "rarity": "common",    "desc": "+20 Моры/день" },
    "owl":     { "name": "🦉 Сова-студент",         "rarity": "common",    "desc": "+1 XP/сообщение" },
    "dog":     { "name": "🐕 Дворовая Собака",      "rarity": "common",    "desc": "-10% время похода" },
    # rare
    "turtle":  { "name": "🐢 Черепаха-торговец",   "rarity": "rare",      "desc": "-5% цены в магазине" },
    "falcon":  { "name": "🦅 Охотничий Сокол",     "rarity": "rare",      "desc": "+15% лута в походе" },
    # epic
    "wolf":    { "name": "🐺 Снежный Волк",         "rarity": "epic",      "desc": "блокирует 1 варн/7 дней" },
    "fox":     { "name": "🦊 Огненная Лиса",        "rarity": "epic",      "desc": "5% шанс Алмаза в походе" },
    # legendary
    "dragon":  { "name": "🐉 Дракон Хранитель",    "rarity": "legendary", "desc": "+50к банк, 10% бесплатная еда" },
    "unicorn": { "name": "🦄 Астральный Единорог", "rarity": "legendary", "desc": "усталость семьи +10/день" },
}
```

### GACHA_RATES — шансы выпадения (в процентах, сумма = 100)
```python
GACHA_RATES = {
    "egg_basic":  {"common": 80, "rare": 19, "epic": 1,  "legendary": 0},
    "egg_silver": {"common": 50, "rare": 40, "epic": 10, "legendary": 0},
    "egg_gold":   {"common": 0,  "rare": 75, "epic": 25, "legendary": 0},
    "egg_mythic": {"common": 0,  "rare": 40, "epic": 60, "legendary": 0},
    "egg_unity":  {"common": 0,  "rare": 0,  "epic": 0,  "legendary": 100},
}
```

### EXPEDITIONS_DATA — данные экспедиций
```python
EXPEDITIONS_DATA = {
    2: {"cost": 0,  "min_m": 10, "max_m": 15,  "min_xp": 10, "max_xp": 10,  "fatigue": 10},
    4: {"cost": 15, "min_m": 40, "max_m": 45,  "min_xp": 20, "max_xp": 40,  "fatigue": 20},
    6: {"cost": 25, "min_m": 80, "max_m": 90,  "min_xp": 50, "max_xp": 70,  "fatigue": 30},
    8: {"cost": 35, "min_m": 90, "max_m": 120, "min_xp": 80, "max_xp": 100, "fatigue": 40},
}
```

---

## 9. РАНГИ

### Глобальные ранги (поле `global_rank` в таблице `users`):
| ID | Название | Кто может выдать |
|---|---|---|
| 0 | 👤 Пользователь | — |
| 1 | 🛡 Хелпер | Разработчик |
| 2 | ⚔️ Старший хелпер | Разработчик |

Разработчик (developer_id из .env) имеет специальное отображение: "🌌 Главный разработчик".

### Локальные ранги (поле `local_rank` в таблице `user_chat_stats`):
| ID | Название | Минимальный ранг для выдачи |
|---|---|---|
| 0 | 👤 Пользователь | — |
| 1 | 👁 Модератор | rank ≥ 2 (у выдающего) |
| 2 | 👮‍♂️ Младший админ | rank ≥ 3 |
| 3 | 👮‍♂️ Админ | rank ≥ 4 |
| 4 | 🕵️‍♂️ Старший админ | rank ≥ 5 |
| 5 | 👑 Совладелец | rank = 6 или developer |
| 6 | 👑 Владелец | только developer |

**Правило:** нельзя выдать ранг ≥ своего. Нельзя изменить ранг того, у кого он ≥ твоего.

---

## 10. КАК РАБОТАЕТ БОТ (поток данных)

### При каждом сообщении (Middleware):
```
Сообщение → db_middleware →
  1. Открывает aiosqlite соединение
  2. update_user(db, user.id, user.username)     ← регистрирует/обновляет юзера
  3. Проверяет purge mode (если активен — удаляет сообщение у низкоранговых)
  4. leveling.process_message_xp(db, ...)        ← +10 XP, +1 если есть Сова, level-up
  5. Записывает в daily_user_stats
  6. Передаёт db в data["db"] для хэндлера
  7. Вызывает хэндлер
```

### При покупке в магазине:
```
/shop → cmd_shop handler →
  EconomyService(db).has_turtle_discount(user_id) →
  Рисует список товаров с ценами
  [Нажатие кнопки] → cb_buy_item handler →
  EconomyService(db).purchase_item(user_id, item_id) →
    has_turtle_discount() →
    apply_discount(price, has_discount) →
    infrastructure.repositories.economy.buy_item(db, ...) →
    BEGIN TRANSACTION → списать валюту + добавить предмет → COMMIT
```

### При экспедиции:
```
/expedition 4 → cmd_expedition handler →
  Ищет активного питомца (placement='active')
  spend_mora(db, user_id, cost)
  Записывает в active_expeditions
  [каждые 60 сек] expedition_background_task →
    services.expedition.calculate_reward(hours, species_id) →
    Начисляет Мору + XP + возможный Алмаз
    Отправляет уведомление в чат
```

---

## 11. ПАТТЕРНЫ КОДА

### Хэндлер (только UI, никакой бизнес-логики):
```python
from aiogram import Router, types
from aiogram.filters import Command
from services.economy import EconomyService
from core.registry import ITEMS_REGISTRY

router = Router(name="shop_router")

@router.message(Command("shop"))
async def cmd_shop(message: types.Message, db):
    if message.chat.type == "private":
        return
    economy = EconomyService(db)
    has_discount = await economy.has_turtle_discount(message.from_user.id)
    # ... только форматирование и отправка
    await message.answer(text, parse_mode="HTML")
```

### Сервис (бизнес-логика, без Telegram):
```python
import aiosqlite
from core.constants import TURTLE_DISCOUNT
from infrastructure.repositories.economy import buy_item

class EconomyService:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def purchase_item(self, user_id: int, item_id: str) -> tuple[bool, str]:
        # ... логика, возвращает (успех, сообщение)
        return await buy_item(self._db, user_id, item_id, mora, diamonds, 1)
```

### Репозиторий (только SQL):
```python
import aiosqlite

async def get_balance(db: aiosqlite.Connection, user_id: int) -> dict:
    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds FROM users WHERE user_tg_id = ?",
        (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else {"user_balance_mora": 0.0, "user_balance_diamonds": 0.0}
```

### Транзакция (для операций, которые нельзя потерять):
```python
try:
    await db.execute("BEGIN TRANSACTION")
    await db.execute("UPDATE users SET user_balance_mora = user_balance_mora - ? ...", ...)
    await db.execute("INSERT INTO inventory ...", ...)
    await db.commit()
    return True, "OK"
except Exception as e:
    await db.rollback()
    return False, str(e)
```

### Текстовые алиасы команд (TextCmd фильтр):
```python
@router.message(Command("shop"))
@router.message(TextCmd(["магазин", "лавка"]))
async def cmd_shop(...):
    ...
```

### Inline CallbackData:
```python
class ShopCB(CallbackData, prefix="shop"):
    action: str
    item_id: str

# Создание кнопки:
builder.button(text="🛒 Купить", callback_data=ShopCB(action="buy", item_id="egg_basic"))

# Обработчик:
@router.callback_query(ShopCB.filter(F.action == "buy"))
async def cb_buy(query: types.CallbackQuery, callback_data: ShopCB, db):
    ...
```

---

## 12. PLACEMENT ПИТОМЦЕВ

Питомец может находиться в трёх состояниях:
- **`storage`** — склад, питомец не даёт баффов
- **`active`** — активный слот (участвует в экспедициях, даёт бафф)
- **`passive`** — пассивный слот (постоянный бафф: сова, черепаха, хомяк, волк)

Максимум слотов по умолчанию: 3 (из `user_zoo_stats.max_slots`).

---

## 13. КАК РАБОТАЮТ БАФФЫ ПИТОМЦЕВ

| Питомец | Placement | Где проверяется |
|---|---|---|
| 🐢 Черепаха | active/passive | `services/economy.py::has_turtle_discount()` |
| 🦉 Сова | active/passive | `services/leveling.py::_has_owl_buff()` |
| 🐕 Собака | active | `bot/handlers/expeditions.py` — умножает время на `DOG_EXPEDITION_SPEED` |
| 🦅 Сокол | active | `services/expedition.py::calculate_reward()` |
| 🦊 Лиса | active | `services/expedition.py::calculate_reward()` |
| 🐺 Волк | active/passive | `bot/handlers/moderation.py::cmd_warn()` — проверяет `wolf_cooldown_until` |
| 🐉 Дракон | active/passive | НЕ РЕАЛИЗОВАН (константа есть в `core/constants.py`) |
| 🦄 Единорог | active/passive | НЕ РЕАЛИЗОВАН (константа есть в `core/constants.py`) |

**Проверка наличия питомца** (унифицированный SQL):
```sql
SELECT 1 FROM pets
WHERE owner_id = ? AND placement IN ('active', 'passive') AND species_id = 'wolf'
```

---

## 14. ШАБЛОН ДОБАВЛЕНИЯ НОВОЙ КОМАНДЫ

**Пример:** добавить команду `/daily` — ежедневная награда.

### Шаг 1 — Константы в `core/constants.py`:
```python
DAILY_MORA_REWARD = 100.0
DAILY_COOLDOWN_HOURS = 24
```

### Шаг 2 — SQL в `infrastructure/repositories/economy.py` (или нужный репо):
```python
async def get_last_daily(db, user_id: int) -> str | None:
    async with db.execute(
        "SELECT last_daily FROM users WHERE user_tg_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
        return row[0] if row else None
```
*(предварительно добавить колонку через ALTER TABLE в `bot/core/database.py`)*

### Шаг 3 — Логика в `services/economy.py` (или отдельный сервис):
```python
async def claim_daily(self, user_id: int) -> tuple[bool, str, float]:
    last = await get_last_daily(self._db, user_id)
    if last and (datetime.now() - datetime.fromisoformat(last)).total_seconds() < DAILY_COOLDOWN_HOURS * 3600:
        return False, "Уже получили сегодня!", 0
    await add_reward(self._db, user_id, DAILY_MORA_REWARD, 0)
    await set_last_daily(self._db, user_id)
    return True, "Получено!", DAILY_MORA_REWARD
```

### Шаг 4 — Хэндлер в `bot/handlers/economy.py`:
```python
@router.message(Command("daily"))
@router.message(TextCmd(["ежедневка", "дейли"]))
async def cmd_daily(message: types.Message, db):
    from services.economy import EconomyService
    ok, msg, amount = await EconomyService(db).claim_daily(message.from_user.id)
    await message.answer(f"{'✅' if ok else '❌'} {msg}", parse_mode="HTML")
```

### Шаг 5 — Зарегистрировать роутер в `bot/handlers/__init__.py` (уже добавлен для economy).

---

## 15. НЕЗАВЕРШЁННЫЕ МЕХАНИКИ (TODO)

| Механика | Статус | Где добавить |
|---|---|---|
| 🐉 Дракон: +50к к банку | Нет реализации | `infrastructure/repositories/marriages.py` — увеличить лимит при family_bank_transaction |
| 🐉 Дракон: 10% бесплатная еда | Нет реализации | В хэндлере кормления питомца |
| 🦄 Единорог: -10 усталости/день семье | Нет реализации | `bot/services/scheduler.py` или отдельная задача |
| 🐹 Хомяк: сбор дохода | Есть в zoo handler | `user_zoo_stats.last_income_collection` уже есть |
| Яйцо Призыва (крафт) | Нет интерфейса | Нужен `/craft` хэндлер: 5 `soul_shard` → `egg_summon` |
| Продажа питомца на осколки | Частичная реализация | В `bot/handlers/zoo.py` |
| `/profile` через web | Базовый шаблон | `dashboard/templates/dashboard/profile.html` |

---

## 16. ПРАВИЛА СТИЛЯ КОДА

1. **Комментарии** — только если WHY неочевиден. Не писать что делает код.
2. **Типы** — аннотации везде: `async def foo(db: aiosqlite.Connection, user_id: int) -> dict:`
3. **Возврат ошибок** — `tuple[bool, str]`: `(True, "")` или `(False, "Текст ошибки")`
4. **HTML в сообщениях** — всегда `parse_mode="HTML"`, экранировать через `safe_html()`
5. **Транзакции** — всегда для операций с балансом/инвентарём
6. **Приватные чаты** — в начале хэндлера: `if message.chat.type == "private": return`
7. **Тип `db`** — всегда `aiosqlite.Connection`, получается из `data["db"]` через middleware
8. **Хэндлеры** — не содержат бизнес-логики, только форматирование и вызов сервисов
9. **Inline кнопки** — `CallbackData` с prefix для пространства имён
10. **Row factory** — всегда установлен `db.row_factory = aiosqlite.Row`, доступ по имени колонки

---

## 17. КОНФИГУРАЦИЯ AIOGRAM

**Middleware** подключается в `bot/__main__.py`:
```python
dp.update.middleware(db_middleware)
```

**Роутеры** агрегируются в `bot/handlers/__init__.py`:
```python
main_router = Router()
main_router.include_routers(
    common.router, economy.router, shop.router, zoo.router, ...
)
```

**Фоновая задача** запускается в `main()`:
```python
asyncio.create_task(expedition_background_task(bot))
```

---

## 18. КЛЮЧЕВЫЕ ФУНКЦИИ ПО СЛОЯМ

### infrastructure/repositories/economy.py
- `get_balance(db, user_id)` → `dict` с mora/diamonds
- `add_balance(db, user_id, mora, diamonds)` → None (выдать из воздуха)
- `add_reward(db, user_id, mora, diamonds)` → alias для add_balance
- `spend_mora(db, user_id, amount)` → `tuple[bool, str]` (списать без получателя)
- `transfer_mora(db, sender_id, receiver_id, amount)` → `tuple[bool, str]`
- `buy_item(db, user_id, item_id, mora, diamonds, qty)` → `tuple[bool, str]`
- `get_inventory(db, user_id)` → `list[dict]`
- `add_item(db, user_id, item_id, qty)` → None
- `remove_item(db, user_id, item_id, qty, commit)` → `bool`

### infrastructure/repositories/chat.py
- `increment_stats_and_get_xp(db, user_id, chat_id, timezone_offset)` → `dict` (xp, level)
- `update_level(db, user_id, chat_id, new_level)` → None
- `get_chat_stats(db, user_id, chat_id)` → `dict`
- `set_local_rank(db, user_id, chat_id, rank_id)` → None
- `get_local_rank(db, user_id, chat_id)` → `int`

### infrastructure/repositories/zoo.py
- `open_egg(db, user_id, egg_item_id, is_summoned)` → `tuple[bool, dict|str]`
- `get_user_pets(db, user_id, placement)` → `list[dict]`
- `get_pet_by_id(db, pet_id)` → `dict | None`
- `get_zoo_stats(db, user_id)` → `dict`

### services/economy.py — EconomyService
- `has_turtle_discount(user_id)` → `bool`
- `apply_discount(price, has_discount)` → `int`
- `get_item_prices(item_id, user_id, has_discount=None)` → `dict`
- `purchase_item(user_id, item_id, qty=1)` → `tuple[bool, str]`

### services/leveling.py — LevelingService
- `calculate_level(xp)` → `int` (чистая функция)
- `process_message(user_id, chat_id, username)` → None

### services/expedition.py
- `calculate_reward(hours, species_id)` → `dict` {mora, xp, diamond_found, buff_message}

### services/roles.py
- `get_global_rank_name(user_id, rank_id, developer_id=0)` → `str`
- `get_local_rank_name(user_id, rank_id, developer_id=0)` → `str`
- `can_assign_local_rank(admin_id, admin_rank, target_rank, new_rank, developer_id=0)` → `tuple[bool, str]`

### services/moderation.py
- `check_mod_rights(db, chat_id, admin_id, target_id, min_rank, developer_id=0)` → `tuple[bool, str]`
- `check_admin_rights(db, chat_id, user_id, min_rank, developer_id=0)` → `tuple[bool, str]`

### services/formatting.py
- `format_currency(amount)` → `str` (1500.5 → "1 500.50")
- `safe_html(text)` → `str` (экранирование HTML)
- `format_progress_bar(current, max, length=10)` → `str` (████░░░)
- `format_seconds_to_time(seconds)` → `str` (3661 → "1ч 1м 1с")

---

## 19. ЧТО НЕЛЬЗЯ ДЕЛАТЬ (антипаттерны)

❌ Добавлять бизнес-логику в хэндлеры (handlers/)
❌ Импортировать `from bot.*` в `services/` или `infrastructure/`
❌ Хардкодить цены/шансы/числа — только через `core/constants.py`
❌ Добавлять новый предмет/питомца не в `core/registry.py`
❌ Использовать `transfer_mora(db, user_id, 0, cost)` — используй `spend_mora`
❌ `int(x * (1.15 - 1.0))` — floating point баг, используй `int(x * 1.15) - x`
❌ Писать `DROP TABLE` в production коде
❌ Делать БД-запросы без транзакций для связанных операций (баланс+инвентарь)

---

## 20. БЫСТРЫЙ СПРАВОЧНИК ФАЙЛОВ

| Что нужно изменить | Какой файл редактировать |
|---|---|
| Цена предмета | `core/registry.py` |
| Шанс выпадения гачи | `core/registry.py` (GACHA_RATES) |
| Награда за уровень | `core/constants.py` |
| Бафф питомца (число) | `core/constants.py` |
| Логика покупки/скидки | `services/economy.py` |
| Логика экспедиционных наград | `services/expedition.py` |
| XP за сообщение | `core/constants.py` (XP_PER_MESSAGE) — и SQL в `infrastructure/repositories/chat.py` |
| SQL-запрос к таблице | `infrastructure/repositories/<нужный>.py` |
| Структура таблицы | `bot/core/database.py` (init_db) |
| Текст Telegram-ответа | `bot/handlers/<нужный>.py` |
| Проверка прав модератора | `services/moderation.py` → вызов из `bot/services/moderation.py` |
| Ранги (названия) | `services/roles.py` |
| Уведомление после экспедиции | `bot/services/scheduler.py` |
| Веб-профиль игрока | `dashboard/views.py` + `dashboard/templates/dashboard/profile.html` |
