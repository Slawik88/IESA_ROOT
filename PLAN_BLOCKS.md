# ПЛАН РЕАЛИЗАЦИИ — БЛОКИ ДЛЯ ПОЭТАПНОГО ВЫПОЛНЕНИЯ

> Каждый блок — отдельный промт. Выдавай по одному.
> API = единое для мини-апп (miniapp_views.py) и бота (handlers/).

---

## БЛОК 1 — База данных: новые колонки и таблицы

**Файл**: `PredvestnikBot/database/db.py`  
**Что делаем**: все миграции `ALTER TABLE … ADD COLUMN IF NOT EXISTS` и новые `CREATE TABLE IF NOT EXISTS`.

### 1.1 — Щит новичка в `user_stats`
```sql
ALTER TABLE user_stats ADD COLUMN IF NOT EXISTS newbie_shield_until TIMESTAMPTZ DEFAULT NULL;
```
Устанавливается при первом сообщении в `message_counter.py` → `+3 дня` от NOW().

### 1.2 — Настройки чистки в `chat_settings` (новые колонки)
```sql
-- уже есть: next_cleanup_at, cleanup_reminder_sent, cleanup_threshold
-- ДОБАВИТЬ:
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS cleanup_message_norm  INTEGER DEFAULT 70;
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS cleanup_warn_hours    INTEGER DEFAULT 48;
```
`cleanup_message_norm` — норма сообщений (сейчас хардкод 70, делаем настраиваемым).  
`cleanup_warn_hours` — за сколько часов присылать предупреждение в чат.

### 1.3 — Стакинг предметов в `gacha_inventory` (новая колонка)
```sql
ALTER TABLE gacha_inventory ADD COLUMN IF NOT EXISTS stack_count INTEGER DEFAULT 1;
```
Все существующие записи получают `stack_count = 1` (дефолт).  
Ключ уникального стека: `(user_id, chat_id, item_key)` — нужен UNIQUE constraint или merge-логика при добавлении.

> **Важно**: при добавлении предмета — если запись с таким `item_key` уже есть (`stack_count < 99`) — увеличиваем `stack_count + 1`. Иначе вставляем новую строку.  
> При удалении — если `stack_count > 1`, уменьшаем. Если `stack_count == 1` — удаляем строку.

### 1.4 — Донаты в казну: таблица `treasury_donations`
```sql
CREATE TABLE IF NOT EXISTS treasury_donations (
    id         SERIAL PRIMARY KEY,
    user_id    BIGINT      NOT NULL,
    chat_id    BIGINT      NOT NULL,
    amount     INTEGER     NOT NULL,
    donated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Используется для подсчёта "Покровителя недели" (сумма за текущую неделю по `donated_at`).

### 1.5 — Бейдж "Покровитель" в `user_badges` (уже есть таблица)
Таблица `user_badges` уже есть. Добавляем badge_key = `"patron_week"` при условии:
- единоразовый донат ≥ 500 🪙, ИЛИ суммарно ≥ 1000 🪙 за неделю.
- Срок: 7 дней от момента достижения порога.
- Сброс: планировщик раз в день проверяет просроченные бейджи и удаляет их.

### 1.6 — Глобальный баф чата: таблица `chat_global_buffs`
```sql
CREATE TABLE IF NOT EXISTS chat_global_buffs (
    id          SERIAL PRIMARY KEY,
    chat_id     BIGINT      NOT NULL,
    buff_type   TEXT        NOT NULL,   -- 'xp_plus10', 'feast' и т.д.
    activated_by BIGINT     NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    UNIQUE (chat_id, buff_type)         -- один тип бафа за раз
);
```

### 1.7 — Чат-пир: лог выдач `feast_log`
```sql
CREATE TABLE IF NOT EXISTS feast_log (
    id          SERIAL PRIMARY KEY,
    chat_id     BIGINT      NOT NULL,
    triggered_by BIGINT     NOT NULL,
    cost        INTEGER     NOT NULL,
    recipients  INTEGER     NOT NULL,
    total_given INTEGER     NOT NULL,
    triggered_at TIMESTAMPTZ NOT NULL
);
```
Нужен для анти-абуза: не более 1 пира в 12 часов на чат.

---

## БЛОК 2 — Щит новичка (автоматический, 3 дня)

**Файлы**:
- `PredvestnikBot/middlewares/message_counter.py` — установка щита
- `PredvestnikBot/database/db.py` — новая функция `set_newbie_shield()`
- `PredvestnikBot/api/admin.py` (или отдельный `api/user.py`) — get_user_shield_status
- `PredvestnikBot/handlers/user.py` — показ в профиле (текст)
- `PredvestnikBot/web/index.html` — показ в мини-апп профиле

### 2.1 — Установка щита при первом сообщении
В `message_counter.py`, в блоке upsert `user_stats`, после INSERT:
```python
# Если first_active только что был NULL (первое сообщение) — ставим щит
if first_message:
    await set_newbie_shield(user_id, chat_id, days=3)
```

Функция в `db.py`:
```python
async def set_newbie_shield(user_id, chat_id, days=3):
    until = datetime.now(timezone.utc) + timedelta(days=days)
    await db.execute(
        "UPDATE user_stats SET newbie_shield_until=? WHERE user_id=? AND chat_id=?",
        (until, user_id, chat_id)
    )
```

### 2.2 — Показ в профиле (бот)
В `handlers/user.py`, в блоке генерации текста профиля:
```python
shield = stats.get("newbie_shield_until")
if shield and shield > now:
    delta = shield - now
    days_left = delta.days
    hours_left = delta.seconds // 3600
    shield_str = f"🛡 Щит новичка: ещё {days_left}д {hours_left}ч"
else:
    shield_str = ""
```

### 2.3 — Показ в мини-апп
В `api/user.py` (или `get_leaderboard`), в данных профиля пользователя добавить поле `newbie_shield_until`.  
В `web/index.html`, в секции профиля добавить строку:
```js
if(p.newbie_shield_until){
    const d = new Date(p.newbie_shield_until);
    const diff = d - Date.now();
    if(diff > 0){
        // показать строку с днями и часами
    }
}
```

### 2.4 — Щит в логике чистки
В функции/хендлере запуска чистки — при переборе кандидатов:
```python
shield = stats.get("newbie_shield_until")
if shield and shield > now:
    continue  # пропустить, щит активен
```

---

## БЛОК 3 — Настройка даты/нормы чистки + умное предупреждение

**Файлы**:
- `PredvestnikBot/database/db.py` — `set_cleanup_config()`, `get_cleanup_config()`
- `PredvestnikBot/api/admin.py` — новая функция `set_cleanup_settings()`
- `PredvestnikBot/handlers/dev_panel.py` — команда в чате
- `PredvestnikBot/utils/scheduler.py` — улучшить `_task_cleanup_reminders()`
- `PredvestnikBot/web/index.html` — UI в dev-панели мини-апп
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — GET/POST `/api/cleanup_config`

### 3.1 — Команды в чате (owner + developer только)
```
бот чистка настройка [дата YYYY-MM-DD HH:MM] [норма N] [предупредить за Xч]
бот чистка настройка показать
```
Примеры:
```
бот чистка настройка 2026-04-05 20:00 норма 70 предупредить 48
```
Бот отвечает:
```
✅ Чистка настроена:
📅 Дата: 05.04.2026 20:00 (Zurich)
📊 Норма: 70 сообщений
🔔 Предупреждение: за 48 часов
```

### 3.2 — API endpoint `/api/cleanup_config`
**GET** `?chat_id=X` — возвращает текущие настройки:
```json
{
  "next_cleanup_at": "2026-04-05T18:00:00Z",
  "cleanup_message_norm": 70,
  "cleanup_warn_hours": 48,
  "cleanup_reminder_sent": 0
}
```
**POST** — body `{chat_id, next_cleanup_at, cleanup_message_norm, cleanup_warn_hours}` — обновляет настройки.  
Доступ: только owner и developer.

### 3.3 — UI в мини-апп (dev-панель)
В `index.html`, в dev-карточке (owner/developer видят), добавить секцию "🧹 Настройка чистки":
- Поле datetime (дата + время)
- Поле "Норма сообщений" (число)
- Поле "Предупреждение за N часов"
- Кнопка "Сохранить"
- Отображение текущих настроек

### 3.4 — Улучшенный scheduler
Текущий планировщик уже отправляет одно напоминание при 0-48ч. Расширить:
- Использовать `cleanup_warn_hours` вместо хардкода 48.
- Текст предупреждения включает:
  - Дату чистки
  - **Норму сообщений** (`cleanup_message_norm`)
  - Сколько часов/дней осталось
  - Упоминание щита новичка (если у кого-то активен)
- Сбрасывать `cleanup_reminder_sent = 0` после прохождения даты (уже есть, проверить).

---

## БЛОК 4 — Стакинг предметов в инвентаре

**Файлы**:
- `PredvestnikBot/database/db.py` — функции `add_gacha_item()`, `batch_sell_items()`
- `PredvestnikBot/shared_prices.py` — добавить флаг `"stackable": True/False` в `ITEM_METADATA`
- `PredvestnikBot/api/gacha.py` — `gacha_roll()` — стакинг при выдаче
- `PredvestnikBot/web/index.html` — UI инвентаря
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — `/api/inventory` (группировка)

### 4.1 — ITEM_METADATA: добавить флаги
```python
# Все предметы получают "stackable": True
# Кроме экипировки (weapon, armor, artifact) — НЕТ (у них могут быть разные статы)
# !!! По условию пользователя — стакать ВСЁ включая экипировку
# Значит stackable=True для всех кроме flair (косметика, уже нет дублей по ключу)
```
Проще: в ITEM_METADATA ничего не добавляем — стакаем всё по `item_key`.

### 4.2 — `add_gacha_item()` — логика стакинга
```python
async def add_gacha_item(user_id, chat_id, item_key, item_name, rarity, ...):
    # Проверяем есть ли предмет с таким item_key у юзера
    existing = SELECT id, stack_count FROM gacha_inventory
               WHERE user_id=? AND chat_id=? AND item_key=?
               LIMIT 1
    if existing and existing["stack_count"] < 99:
        # Увеличиваем стак
        UPDATE gacha_inventory SET stack_count = stack_count + 1 WHERE id=?
    else:
        # Новая строка
        INSERT INTO gacha_inventory (..., stack_count) VALUES (..., 1)
```

### 4.3 — `batch_sell_items()` — продажа стаками
Параметры расширить: `{item_id: int, sell_qty: int}`.  
При продаже:
- Если `sell_qty >= stack_count` — удаляем строку.
- Иначе — `stack_count -= sell_qty`.

### 4.4 — `/api/inventory` — группировка для фронта
Отдавать данные уже сгруппированными (по item_key). Каждый объект:
```json
{
  "id": 123,
  "item_key": "str_potion",
  "item_name": "Зелье Силы",
  "rarity": "common",
  "stack_count": 4,
  "sell_price": 50,
  "is_cosmetic": false
}
```

### 4.5 — UI инвентаря в `index.html`
- Значок количества в углу карточки предмета: `×4`.
- При нажатии "Продать" — слайдер / input "Сколько продать? (1..4)".
- Кнопка "Продать мусор" продаёт все `junk_*` (весь стак).
- Косметика (`slot == "flair"` или `sell == 0`) — кнопка "Продать" скрыта.

### 4.6 — Защита от продажи косметики (сервер)
В `batch_sell_items()` и `/api/inventory/sell`:
```python
meta = ITEM_METADATA.get(item_key, {})
if meta.get("slot") == "flair" or meta.get("sell", 0) == 0:
    raise ValueError("Косметику нельзя продать")
```

---

## БЛОК 5 — Новые предметы гачи + экспедиционные ускорения

**Файлы**:
- `PredvestnikBot/shared_prices.py` — добавить новые item_key в `ITEM_METADATA`
- `PredvestnikBot/api/gacha.py` — добавить в пулы
- `PredvestnikBot/api/expeditions.py` — использование купона ускорения
- `PredvestnikBot/web/index.html` — показ ускорений на странице экспедиций + инвентарь
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — endpoint `/api/expeditions/boost`

### 5.1 — Новые item_key в ITEM_METADATA
```python
# Купоны ускорения экспедиции
"exp_boost_sm":  {"slot": "coupon", "sell": 15,  "desc": "Ускорение экспедиции −30 мин",       "boost_minutes": 30,  "rarity": "common"},
"exp_boost_md":  {"slot": "coupon", "sell": 60,  "desc": "Ускорение экспедиции −2 часа",       "boost_minutes": 120, "rarity": "rare"},
"exp_boost_lg":  {"slot": "coupon", "sell": 200, "desc": "Ускорение экспедиции −50% времени",  "boost_pct": 0.5,     "rarity": "legendary"},

# Купон реролла дейлика
"quest_reroll":  {"slot": "coupon", "sell": 25,  "desc": "Сбросить и получить новый квест",    "rarity": "common"},

# Купон переименования питомца (только гача, косметика — не продаётся)
"pet_rename":    {"slot": "flair",  "sell": 0,   "desc": "Переименовать питомца бесплатно 1 раз","rarity": "rare"},
```

### 5.2 — Добавить в пулы гачи (`api/gacha.py`)
```python
# В _COMMON_ITEMS добавить:
("exp_boost_sm",  "🗺️ Ускорение экспедиции S",  "−30 мин от времени текущей или следующей экспедиции"),
("quest_reroll",  "🔄 Купон реролла задания",    "Сбросить текущий квест дня на новый"),

# В _RARE_ITEMS добавить:
("exp_boost_md",  "🗺️✨ Ускорение экспедиции M", "−2 часа от времени текущей или следующей экспедиции"),
("pet_rename",    "✏️ Купон переименования питомца", "Переименовать питомца бесплатно 1 раз"),

# В _LEGENDARY_ITEMS добавить:
("exp_boost_lg",  "🗺️⚡ Ускорение экспедиции L", "−50% оставшегося времени экспедиции"),
```

### 5.3 — API: `/api/expeditions/boost` (POST)
```json
Request: { "chat_id": X, "item_id": Y }
Logic:
  - Получить активную экспедицию
  - Получить предмет из инвентаря (item_key = "exp_boost_*")
  - Рассчитать новое время окончания
  - Обновить expedition.started_at (сдвинуть назад) или expires_at
  - Удалить (уменьшить стак) купона
Response: { "ok": true, "new_end_at": "...", "saved_minutes": 30 }
```

### 5.4 — Показ на странице экспедиции в `index.html`
На странице экспедиции (где отображается питомец в пути):
- Если в инвентаре есть `exp_boost_*` — показать блок "⚡ Ускорить экспедицию"
- Список доступных купонов с кнопкой "Применить"
- После применения — таймер обновляется

### 5.5 — Купон реролла квеста (использование)
В `api/quests.py` (если отдельный файл) или `miniapp_views.py`:
- Эндпоинт уже есть: `/api/quests/reroll`. 
- Логика изменится: если у юзера есть `quest_reroll` в инвентаре — разрешить бесплатный реролл сверх лимита, списать купон.

### 5.6 — Купон переименования питомца (использование)
Через `/api/pets/rename` — существующий или новый эндпоинт:
- Если тип запроса "coupon" — проверить инвентарь на `pet_rename`, списать, переименовать бесплатно.
- Иначе — стандартное платное переименование (если оно было).

---

## БЛОК 6 — Цветной тег питомца (только магазин)

**Файлы**:
- `PredvestnikBot/shared_prices.py` — каталог цветов
- `PredvestnikBot/api/shop.py` — добавить в get_catalog / buy_item
- `PredvestnikBot/database/db.py` — уже есть `pets.color_name`
- `PredvestnikBot/web/index.html` — UI в магазине + отображение в профиле питомца
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — уже есть `/api/shop/buy`

### 6.1 — Каталог цветов в shared_prices.py
```python
PET_COLOR_CATALOG = [
    ("pet_color_red",    "❤️ Алый",       800),
    ("pet_color_blue",   "💙 Синий",      800),
    ("pet_color_gold",   "💛 Золотой",    1000),
    ("pet_color_green",  "💚 Зелёный",    800),
    ("pet_color_purple", "💜 Фиолетовый", 1000),
    ("pet_color_white",  "🤍 Белый",      600),
]
```

### 6.2 — В shop.py: buy_item для pet_color_*
При покупке:
- Списать мору
- Обновить `pets.color_name = 'red'` (например)
- Добавить в `shop_items` как подтверждение (или в `gacha_inventory` с slot="flair")
- **Нельзя купить повторно тот же цвет** (проверка)

### 6.3 — Отображение цвета в мини-апп
В профиле питомца и на странице экспедиций: название питомца окрашивать CSS-классом.
Маппинг цвет → CSS:
```js
const petColorMap = {
    'red': '#ef4444', 'blue': '#3b82f6', 'gold': '#f59e0b',
    'green': '#22c55e', 'purple': '#a855f7', 'white': '#f0f0f0'
};
```

---

## БЛОК 7 — Донат в казну + Покровитель недели + Чат-пир

**Файлы**:
- `PredvestnikBot/api/economy.py` — `donate_to_treasury()`, `trigger_feast()`
- `PredvestnikBot/database/db.py` — `add_treasury_donation()`, `get_weekly_top_donor()`, `trigger_feast_payout()`
- `PredvestnikBot/handlers/wallet.py` — команда `бот пожертвовать N`
- `PredvestnikBot/web/index.html` — UI доната и пира в transfers-таб
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — `/api/treasury/donate`, `/api/feast`
- `PredvestnikBot/utils/scheduler.py` — еженедельный сброс "Покровителя"

### 7.1 — API `donate_to_treasury(uid, chat_id, amount)`
```python
async def donate_to_treasury(uid, chat_id, amount):
    DONATE_MIN = 50   # min сумма доната
    # 1. Списать мору у юзера (deduct_mora)
    # 2. add_to_treasury(chat_id, amount, "donation", uid)
    # 3. Записать в treasury_donations
    # 4. Проверить порог для бейджа:
    #    - single >= 500 ИЛИ weekly_total >= 1000
    #    → award badge "patron_week" на 7 дней
    # 5. Публичный анонс через бот (возвращаем флаг needs_announce=True)
    # 6. Вернуть {ok, amount, new_treasury, badge_awarded, weekly_total}
```

### 7.2 — Покровитель недели
Функция `get_weekly_top_donor(chat_id)` — суммирует `treasury_donations` за текущую неделю,  
возвращает топ-1 донатора.

Отображение на главном экране мини-апп: "🏆 Покровитель недели: [имя] — X 🪙"  
(виджет обновляется каждый раз при загрузке профиля).

Еженедельный сброс в планировщике (воскресенье в 23:59):  
- Удалить все `badge_key = "patron_week"` из `user_badges` где `expired_at < NOW()`.

### 7.3 — Команда в чате `бот пожертвовать N`
В `handlers/wallet.py` или новый хендлер:
```
бот пожертвовать 200
→ ✅ Ты пожертвовал 200 🪙 в казну!
   Казна чата: X 🪙
   🏆 Покровитель недели: ты (если достиг порога)
   Публичное сообщение в чат.
```

### 7.4 — Чат-пир `бот пир` / кнопка в мини-апп
```python
async def trigger_feast(uid, chat_id):
    FEAST_COST = 3000
    MIN_RECIPIENTS = 3
    PAYOUT_PER_USER = 40  # fixed или random 25-50
    COOLDOWN_HOURS = 12
    
    # 1. Проверить cooldown (feast_log за 12ч)
    # 2. Списать FEAST_COST у uid
    # 3. Найти всех активных за последние 24ч (last_active >= NOW()-24h)
    # 4. Если recipients < MIN_RECIPIENTS → refund, ошибка
    # 5. Выдать PAYOUT_PER_USER каждому (add_mora)
    # 6. Записать в feast_log
    # 7. Анонс в чат: "🎉 [имя] устроил ПИР! X участников получили по 40 🪙!"
```

### 7.5 — UI в мини-апп (transfers-таб или отдельная секция)
- Кнопка "💰 Донат в казну" — поле суммы + кнопка.
- Показать текущий баланс казны.
- Показать покровителя недели.
- Кнопка "🎉 Устроить пир (3000 🪙)" — с предупреждением о стоимости.

---

💬 Управление чатами

## ПОРЯДОК ВЫПОЛНЕНИЯ (ЗАВИСИМОСТИ)

```
БЛОК 1 (DB миграции)
    ↓
БЛОК 2 (Щит) ← зависит от 1.1
БЛОК 4 (Стакинг) ← зависит от 1.3
БЛОК 7 (Донат/Пир) ← зависит от 1.4, 1.5
БЛОК 8 (Глоб.баф) ← зависит от 1.6
    ↓
БЛОК 3 (Настройка чистки) ← зависит от 1.2
БЛОК 5 (Гача/Ускорения) ← зависит от БЛОКА 4 (стакинг)
БЛОК 6 (Цвет питомца) ← независим, можно в любой момент
```

**Рекомендуемый порядок промтов:**
1. БЛОК 1
2. БЛОК 2 + БЛОК 4 (параллельно, независимы)
3. БЛОК 3
4. БЛОК 5
5. БЛОК 6
6. БЛОК 7
7. БЛОК 8
