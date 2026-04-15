# 🔍 PREDVESTNIK — ПОЛНЫЙ АУДИТ КОДОВОЙ БАЗЫ v2

**Дата:** 2025  
**Охват:** Telegram-бот (`PredvestnikBot/`) + Django Mini App (`IESA_ROOT/`) + React Frontend (`frontend/`)  
**Цель:** Выявить все явные баги (которые встретит каждый пользователь) и все места рассинхронизации бота и сайта  
**Приоритеты:** 🔴 CRITICAL → 🔄 DESYNC → 🟠 HIGH → 🟡 MEDIUM

---

## ИТОГ ПО КАТЕГОРИЯМ

| Категория | Кол-во | Статус |
|-----------|--------|--------|
| 🔴 CRITICAL — крашащие баги | 5 | ❌ Не исправлены |
| 🔄 DESYNC — рассинхрон бот/сайт | 8 | ❌ Не исправлены |
| 🟠 HIGH — серьёзные баги | 5 | ❌ Не исправлены |
| 🟡 MEDIUM — заметные проблемы | 6 | ❌ Не исправлены |

---

## 🔴 CRITICAL BUGS — Крашащие баги (каждый пользователь столкнётся)

### CRIT-001 — `api/economy.py`: `_log` не определён → NameError при каждом сбое перевода

**Файл:** `PredvestnikBot/api/economy.py`  
**Тип:** Крашащий баг (NameError)  
**Частота:** Каждый перевод Моры с ошибкой

**Описание:**  
В файле полностью отсутствует `import logging` и определение `_log`. При этом в двух местах вызывается `_log.debug(...)`:

- Строка ~27: `except Exception as e: _log.debug(...)` — в блоке обработки ошибки перевода  
- Строка ~149: `except Exception as e: _log.debug(...)` — в блоке ledger-ошибки

Когда внутренний `try/except` срабатывает по любой причине (сеть, DB timeout, etc.), Python выбрасывает `NameError: name '_log' is not defined` — это поднимается выше и крашит всю операцию перевода вместо тихого логирования.

**Последствия:**  
- Любой перевод Моры между пользователями (`бот передать`) потенциально крашится при нестандартных условиях  
- Ошибка маскируется как загадочный краш без диагностики

**Исправление:**
```python
# Добавить в начало файла api/economy.py (после других imports):
import logging
_log = logging.getLogger(__name__)
```

---

### CRIT-002 — `api/auction.py`: `_log` не определён (16 мест) → NameError во всех error-хендлерах

**Файл:** `PredvestnikBot/api/auction.py`, строка 29  
**Тип:** Крашащий баг (NameError) во всей логике ошибок аукциона  
**Частота:** Любая ошибка в аукционной системе

**Описание:**  
Строка 29 определяет переменную с ДРУГИМ именем:
```python
logger = logging.getLogger(__name__)  # ← имя "logger"
```### CRIT-002 — `api/auction.py`: `_log` не определён (16 мест) → NameError во всех error-хендлерах
Но **во всём файле (16 мест)** используется `_log`:
```python
_log.debug(...)   # ← NameError! _log не определён
_log.warning(...) # ← то же
_log.exception(...)  # ← то же
```

**Последствия:**  
- Каждый `except`-блок в аукционной системе крашится с `NameError` вместо логирования  
- Это включает error-handling в `place_bid()`, `finalize_auction()`, `_dm_user()` и т.д.  
- Ошибки аукциона не логируются и вызывают cascade errors

**Исправление:**
```python
# Строка 29: изменить
logger = logging.getLogger(__name__)
# на:
_log = logging.getLogger(__name__)
```

---

### CRIT-003 — `api/auction.py`: Неправильное имя переменной окружения → все уведомления аукциона не работают

**Файл:** `PredvestnikBot/api/auction.py`  
**Строки:** ~45 (`_dm_user()`), ~65 (`_notify_all_chats_new_lot()`) — и ещё 6 мест  
**Тип:** Silent failure — уведомления никогда не отправляются  
**Частота:** Каждое событие аукциона (новый лот, ставка перебита, выигрыш)

**Описание:**  
Функции отправки уведомлений используют:
```python
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
```
Но в production переменная называется `PREDVESTNIK_BOT_TOKEN` (проверено в `config.py`). `BOT_TOKEN` не задана, поэтому `BOT_TOKEN = ""` → API-запросы к Telegram идут с пустым токеном → 401 Unauthorized → уведомления **никогда не отправляются**.

**Последствия:**  
- Продавец не получает ДМ о завершении аукциона  
- Покупатель не получает ДМ о победе / перебитой ставке  
- Все чаты не получают уведомление о новом лоте  
- Аукционная система работает «вслепую» — пользователи не знают о своих аукционах

**Исправление:**
```python
# Заменить во всех местах:
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# на:
BOT_TOKEN = os.environ.get("PREDVESTNIK_BOT_TOKEN") or os.environ.get("BOT_TOKEN", "")
```

---

### CRIT-004 — `handlers/boss.py`: HP мирового босса хранится в памяти → сбрасывается при каждом рестарте

**Файл:** `PredvestnikBot/handlers/boss.py`  
**Тип:** Дата-потеря при рестарте/деплое  
**Частота:** Каждый деплой уничтожает весь прогресс атак на мирового босса

**Описание:**  
```python
_boss_hp: dict[int, int] = {}  # ключ = chat_id, значение = текущий HP
```
Это обычный Python dict в памяти процесса. При любом рестарте бота (деплой, краш, обновление) весь накопленный урон теряется, HP восстанавливается до `500_000` у каждого чата.

**Последствия:**  
- Игроки часами наносят урон — бот перезапускается — босс снова на 500к HP  
- Доверие к игровой системе подрывается (~"Зачем атаковать если всё сбросится?")  
- Нет персистентного прогресса между сессиями

**Исправление:**  
Перенести хранение HP в базу данных. Создать таблицу `world_boss_state`:
```sql
CREATE TABLE IF NOT EXISTS world_boss_state (
    chat_id    BIGINT PRIMARY KEY,
    current_hp INTEGER NOT NULL DEFAULT 500000,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
Функции `get_boss_hp(chat_id)` и `apply_damage(chat_id, amount)` должны читать/писать в эту таблицу вместо `_boss_hp` dict.

---

### CRIT-005 — Бесплатная молитва на 20-й день стрика — обещана, но полностью не реализована

**Файлы:**  
- `PredvestnikBot/database/db.py`, строка 8449 (флаг ставится)  
- `PredvestnikBot/handlers/checkin.py` (объявляет но не даёт)  
- `PredvestnikBot/handlers/gacha.py` (не проверяет флаг)  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` (не проверяет флаг нигде)  
**Тип:** Функция объявлена пользователям, но не работает нигде  
**Частота:** Каждый пользователь с 20-дневным стриком чекина

**Описание:**  
В `db.py::perform_checkin()`:
```python
free_gacha = (day_idx == 20)  # строка 8449
```
Этот флаг возвращается вызывающему коду. При этом:

1. **Бот** (`handlers/checkin.py`): объявляет "🎰 Бесплатная молитва! Напиши бот молитва" — но `cmd_gacha` немедленно перенаправляет в Mini App, там бесплатного ролла нет
2. **Mini App** (`miniapp_views.py`): функция `miniapp_checkin` не проверяет `free_gacha` вообще
3. **Гача-хендлер** (`handlers/gacha.py`): нет кода для применения бесплатного ролла
4. **API гачи** (`api/gacha.py`): нет параметра `free_gacha` в `perform_gacha()`

Пользователь видит объявление, пытается получить награду — и ничего не происходит.

**Исправление (один из вариантов):**  
Добавить поле `free_gacha_available BOOLEAN DEFAULT FALSE` в таблицу `daily_checkin`. При получении 20-дневного чекина — ставить флаг. При гаче — проверять флаг и давать бесплатный ролл (без списания стоимости), затем сбрасывать флаг.

```python
# В api/gacha.py::perform_gacha() добавить параметр:
async def perform_gacha(user_id, chat_id, *, free: bool = False) -> dict:
    if not free:
        # стандартное списание стоимости
        ...
    # остальная логика гачи
```

---

## 🔄 DESYNC — Рассинхронизация бота и Mini App

### SYNC-001 — Цены и ассортимент еды отличаются в боте и на сайте

**Файлы:**  
- `PredvestnikBot/handlers/food.py` — FOOD_CATALOG (только для бота)  
- `PredvestnikBot/shared_prices.py` — FOOD_ITEMS (только для Mini App)  
**Тип:** Прямая рассинхронизация данных

| Блюдо | Бот (`handlers/food.py`) | Mini App (`shared_prices.py`) |
|-------|--------------------------|-------------------------------|
| Краб  | 50 🪙 | 40 🪙 |
| Лапша | 25 🪙 | 20 🪙 |
| Деликатес | ❌ не существует | 80 🪙 |
| Гриб  | ❌ не существует | 35 🪙 |

**Дополнительная проблема:**  
После перехода на Phase 3 (redirect-to-Mini-App), `cmd_food_shop` сразу делает `return` и отправляет ссылку на Mini App. Но callback-хендлер `cb_buy_food` по-прежнему зарегистрирован. Если у пользователя сохранилось старое сообщение с кнопками — срабатывает стара логика со старыми ценами (50/25 вместо 40/20), и `Деликатес`/`Гриб` недоступны.

**Последствия:**  
- Пользователь видит в боте меню `Лапша 25🪙`, покупает через Mini App за `20🪙` — путается в ценах  
- 2 из 4 блюд полностью недоступны через бота  
- Старые кнопки могут списать неправильную сумму

**Исправление:**
```python
# handlers/food.py — удалить FOOD_CATALOG и импортировать из shared_prices:
from shared_prices import FOOD_ITEMS as FOOD_CATALOG

# Удалить регистрацию обработчика cb_buy_food или заменить на:
async def cb_buy_food(callback: CallbackQuery):
    await callback.answer("Устарело, используй Mini App 👆", show_alert=True)
```

---

### SYNC-002 — Задание дня: бот показывает только XP, Mini App показывает XP + Мора

**Файлы:**  
- `PredvestnikBot/handlers/quests.py` — `cmd_quest()`  
- `frontend/src/pages/Quests.tsx` — компонент с полными данными  
**Тип:** Неполное отображение информации в боте

**Описание:**  
Бот показывает награду за задание так:
```
Награда: +{xp_reward} XP
```
Mini App показывает обе награды: XP и Мора.

В базе данных (`DAILY_QUESTS` в `db.py`) каждый квест имеет ОБА поля — `xp` и `mora`:
```python
{"type": "messages", "goal": 10, "xp": 30, "mora": 3, "desc": "..."}
```

Пользователь в чате не знает о денежной составляющей награды — теряет мотивацию или не понимает зачем выполнять задание.

**Исправление:**
```python
# handlers/quests.py, в тексте ответа добавить:
reward_text = f"Награда: +{quest['xp']} XP  +{quest['mora']} 🪙"
```

---

### SYNC-003 — Мировой босс в чате vs Одиночный босс в Mini App — две независимые системы без общего прогресса

**Файлы:**  
- `PredvestnikBot/handlers/boss.py` — мировой босс (in-memory HP, атаки в чате)  
- `frontend/src/pages/BossFight.tsx` — Solo Boss / Couple Boss (личные сессии)  
- `database/db.py` — `boss_damage_log` (только атаки из чата), `solo_boss_sessions` (только из Mini App)  
**Тип:** Архитектурная рассинхронизация

**Описание:**  
Существуют ДВЕ полностью независимые системы:

**Система 1 — Мировой bosс в чате:**
- HP хранится в `_boss_hp` dict в памяти
- Атаки: `бот атаковать` в Telegram
- Записи повреждений: `boss_damage_log`
- Лидерборд: `get_boss_leaderboard()` → читает из `boss_damage_log`

**Система 2 — Solo/Couple Boss в Mini App:**
- Личные сессии в таблицах `solo_boss_sessions`, `couple_boss_sessions`
- Атаки: кнопки ATB в BossFight.tsx
- RPG-механика: уровни 1-5, HP/ATK/DEF статы, крит-удары
- Таблица `solo_boss_progress` — отдельная от мирового босса

**Последствия:**  
- Урон в Mini App не отображается в лидерборде чата
- Урон в чате не влияет на Solo Boss сессии
- Пользователь, убивший 5 боссов в Mini App, на лидерборде чата — последний
- Нет единого «уровня угрозы» или совместного прогресса для сообщества

**Исправление (предпочтительное):**  
Урон из Solo Boss сессий (`miniapp_solo_boss_attack`) должен вызывать `add_boss_damage(user_id, chat_id, total_damage)` — тот же лидерборд. Или явно отобразить оба лидерборда раздельно с объяснением.

---

### SYNC-004 — Зелья: получать можно везде, применять — только в Mini App

**Файлы:**  
- `PredvestnikBot/handlers/gacha.py` — выдаёт зелья из гачи  
- `PredvestnikBot/api/roulette.py` — выдаёт зелья как призы  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — `miniapp_consume_item` — единственное место применения  
**Тип:** Функция доступна только на сайте, хотя предметы получают везде

**Описание:**  
Зелья (`potion_atk`, `potion_def`, `potion_hp`) и баффы появляются в инвентаре из гачи и рулетки — обоих системах (бот + Mini App). Применить зелье можно только в Mini App → Inventory → кнопка "Использовать".

В боте нет ни одной команды типа `бот зелья` / `бот инвентарь` / `бот использовать зелье`.

**Последствия:**  
- Пользователь бота видит в гаче "Кристальное зелье атаки!" — не понимает как использовать  
- Лёгкая потеря пользователей: получил предмет, не видит эффекта, думает что это баг  
- Часть аудитории использует только чат-бота и никогда не зайдёт в Mini App

**Исправление:**  
Добавить в бота команду `бот инвентарь` которая:
1. Показывает список предметов в `gacha_inventory` для данного пользователя  
2. Предлагает кнопки "Использовать" для расходников (зелий и баффов)  
3. Ссылается на Mini App для косметических предметов

---

### SYNC-005 — Темы профиля: купить/получить везде, активировать только в Mini App

**Файлы:**  
- `PredvestnikBot/api/gacha.py` — выдаёт темы из гачи  
- `database/db.py` — `user_themes` таблица  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — `miniapp_set_theme` — единственное место активации  
**Тип:** Аналогично SYNC-004

**Описание:**  
Темы профиля (`rare_theme_ocean`, `epic_theme_fire` и т.д.) выпадают из гачи и могут быть куплены в Mini App. Активировать тему нельзя через бота — только Mini App → Profile → Themes.

В боте у пользователя есть тема в инвентаре, но он не может её применить и не видит эффекта.

**Исправление:**  
Добавить команду `бот тема` в чат которая показывает доступные темы и позволяет активировать, или как минимум сообщает "Для активации темы открой Mini App 👆" с прямой ссылкой.

---

### SYNC-006 — Устаревшие callback-кнопки Phase 2 живут рядом с Phase 3 redirect

**Файлы:**  
- `PredvestnikBot/handlers/food.py` — `cb_buy_food` зарегистрирован  
- `PredvestnikBot/handlers/bank.py` — `bank_open` callback зарегистрирован  
- `PredvestnikBot/handlers/expeditions.py` — `exped:` callback зарегистрирован  
**Тип:** Dead code + опасное состояние

**Описание:**  
После перехода на Phase 3 многие команды теперь выглядят так:
```python
async def cmd_food_shop(message):
    await message.reply("Магазин Еды ➡️ [Mini App](...)", ...)
    return  # ← ранний выход
    # ... весь старый код остался ниже return
```
НО: старые callback-хендлеры для inline-кнопок Phase 2 остаются **зарегистрированными**. Если у пользователя в чате сохранились старые сообщения с кнопками (бот не редактировал их), нажатие кнопки запустит старый Phase 2 код:
- Со старыми ценами (еда: 50/25 вместо 40/20)
- С устаревшей логикой (возможно без актуальных проверок)
- Без Phase 3 safety-check'ов

**Исправление:**  
Заменить все устаревшие callbacks на:
```python
@router.callback_query(F.data.startswith("buy_food:"))
async def cb_buy_food_legacy(callback: CallbackQuery):
    await callback.answer("Кнопка устарела. Используй Mini App 👆", show_alert=True)
```

---

### SYNC-007 — VIP-статус: бот не проверяет дату истечения

**Файл:** `PredvestnikBot/database/db.py` — функция `get_vip()`  
**Тип:** Неверный статус в боте после истечения VIP

**Описание:**  
Функция `get_vip()` в db.py **корректно** проверяет expiry:
```python
async def get_vip(user_id: int, chat_id: int) -> int:
    ...
    exp = row["vip_expires_at"]
    if exp is not None and exp < datetime.now(timezone.utc):
        return 0  # expired
    return 1
```

Однако ряд хендлеров бота делает прямые запросы к `user_mora.vip` минуя эту функцию. Нужно проверить все места где используется `vip` из `user_mora` напрямую — они могут не учитывать `vip_expires_at`.

Mini App (`miniapp_user_data`) всегда считает VIP с учётом expiry через Django-запрос. Если бот читает `vip=1` без проверки expiry — пользователь после истечения подписки по-прежнему видит VIP-приветствие в чате.

**Исправление:**  
Все обращения к VIP-статусу в боте должны идти через `get_vip(user_id, chat_id)`, а не напрямую читать поле `vip` из сырой строки БД.

---

### SYNC-008 — Аукцион: нет команд в чат-боте + уведомления молчат из-за CRIT-003

**Файлы:**  
- `PredvestnikBot/` — нет ни одного файла c командами аукциона  
- `PredvestnikBot/api/auction.py` — уведомления `_notify_all_chats_new_lot()`  
**Тип:** Функция только в Mini App + Silent failure уведомлений

**Описание:**  
Аукцион доступен исключительно через Mini App. В боте нет команды проверить лоты, участвовать в торгах или получить уведомление. При этом `_notify_all_chats_new_lot()` должна отправлять в чаты сообщение о новом лоте — но из-за CRIT-003 (неправильный env var токена) это никогда не происходит.

**Последствия:**  
- Большинство пользователей не знают о существовании аукциона  
- Продавцы ждут ставок, которые не приходят потому что никто не в курсе об аукционе  
- Нет способа узнать о лоте через чат

**Исправление:**  
1. Исправить CRIT-003 — уведомления заработают автоматически  
2. Добавить команду `бот аукцион` в чат — показывает последние активные лоты со ссылкой на Mini App

---

## 🟠 HIGH — Серьёзные баги

### HIGH-001 — Экспедиции: рефанд при ошибке идёт на личный кошелёк независимо от способа оплаты

**Файл:** `PredvestnikBot/api/expeditions.py`  
**Тип:** Финансовый баг — неверный возврат средств

**Описание:**  
При ошибке старта экспедиции (`_db_start_expedition()` фейлится):
```python
# В коде рефанда:
await add_mora(uid, chat_id, cost)  # ← ВСЕГДА возвращает на личный кошелёк
```
Но пользователь мог оплатить экспедицию из СЕМЕЙНОГО кошелька (`wallet_type="family"`). В таком случае деньги списались из семейного кошелька, а возвратились на личный — это финансовая потеря для пары.

**Исправление:**
```python
if wallet_type == "family":
    await add_to_family_wallet(chat_id, uid, cost)
else:
    await add_mora(uid, chat_id, cost)
```

---

### HIGH-002 — Экспедиции: TOCTOU race condition при проверке партнёра

**Файл:** `PredvestnikBot/api/expeditions.py`  
**Тип:** Race condition (параллельные запросы)

**Описание:**  
Логика запуска экспедиции:
1. `get_any_active_expedition(partner_id)` — проверяем, нет ли у партнёра активной экспедиции
2. Если нет — вызываем `_db_start_expedition()` для обоих

Между шагом 1 и шагом 2 существует временное окно. Если оба партнёра одновременно нажали "Отправить питомца" (например, через Mini App и бот одновременно):
- Оба проходят проверку на шаге 1: "партнёр свободен"
- Оба запускают `_db_start_expedition()` — дважды стартуют, дважды списываются деньги, возможны дублированные награды

**Исправление:**  
Использовать атомарную INSERT с UNIQUE constraint:
```sql
ALTER TABLE pet_expeditions ADD CONSTRAINT uniq_pet_per_user UNIQUE(user_id);
```
Тогда вторая попытка вставки просто упадёт с IntegrityError, которую нужно поймать и сообщить "Питомец уже в экспедиции".

---

### HIGH-003 — Казино: глобальные sets `_active_coins` / `_resolved_coins` никогда не очищаются → утечка памяти

**Файл:** `PredvestnikBot/handlers/casino.py`  
**Тип:** Утечка памяти

**Описание:**  
```python
_active_coins: set[tuple]   = set()  # накапливается вечно
_resolved_coins: set[tuple] = set()  # накапливается вечно
```
Каждая игра в казино добавляет туплы в эти sets. Ни одна строка кода их не очищает. На активном сервере с тысячами игр за день/неделю — sets растут до десятков тысяч записей, занимая значительную память.

**Исправление:**  
Ограничить размер или использовать TTL-очистку:
```python
import time
_active_coins: dict[tuple, float] = {}  # tuple → timestamp
_resolved_coins: dict[tuple, float] = {}

# Периодически:
now = time.time()
_resolved_coins = {k: v for k, v in _resolved_coins.items() if now - v < 3600}
```

---

### HIGH-004 — Перевод Моры: получатель не проверяется на существование

**Файл:** `PredvestnikBot/database/db.py` — `transfer_mora()`  
**Тип:** Финансовый баг — деньги пропадают

**Описание:**  
В функции `transfer_mora()` деньги сначала снимаются с отправителя, затем начисляются получателю. Если получатель не существует в таблице `users`, `UPDATE ... WHERE user_id=to_uid` выполнится с `rowcount=0` — деньги пропали у отправителя и не появились у получателя.

**Примечание:** Функция в `db.py` теперь обрабатывает это: при `rcv_cur.rowcount == 0` поднимает `ValueError("receiver_not_found")`, что откатывает транзакцию. Но нужно убедиться что вызывающий код обрабатывает этот случай и показывает пользователю понятное сообщение "Получатель не найден в системе".

**Исправление:**  
Проверить обработчики `cmd_transfer` в `handlers/wallet.py` — убедиться что случай `receiver_not_found` обрабатывается с понятным сообщением пользователю.

---

### HIGH-005 — Рулетка: два параллельных DB-запроса — баланс и пити-счётчик

**Файл:** `PredvestnikBot/api/roulette.py`  
**Тип:** Race condition (параллельные запросы)

**Описание:**  
Логика рулетки:
1. `SELECT balance, roulette_losses FROM user_mora WHERE ...` — первый запрос
2. Проверка пити-системы на основе считанных данных
3. `UPDATE users SET balance = balance - ? WHERE ...` — второй запрос

Между шагом 1 и шагом 3 другой параллельный процесс может изменить `roulette_losses` (например пользователь сыграл в рулетку дважды одновременно из двух вкладок Mini App). Пити-счётчик будет прочитан как N, но к моменту ставки уже может быть N+1 — гарантированная победа может сработать дважды или не сработать вообще.

**Исправление:**  
Объединить первый SELECT и UPDATE в одну атомарную операцию через `FOR UPDATE` или переписать как одну SQL-транзакцию.

---

## 🟡 MEDIUM — Заметные проблемы

### MED-001 — Season XP при чекине и квесте молча заглатывается при ошибке

**Файлы:** `PredvestnikBot/handlers/checkin.py`, `PredvestnikBot/database/db.py::mark_quest_rewarded()`  
**Тип:** Silent failure, пользователи теряют сезонный XP без уведомления

**Описание:**
```python
try:
    await add_season_xp(user_id, xp_amount)
except Exception:
    pass  # ← ошибка проглочена без уведомления
```
Если сезонная система сломана — пользователи не получают XP за чекин/квесты и не знают об этом.

**Исправление:**  
Заменить `pass` на `_log.exception("add_season_xp failed uid=%s", user_id)` — хотя бы логировать.

---

### MED-002 — Реролл задания в боте не проверяет купоны из инвентаря

**Файл:** `PredvestnikBot/handlers/quests.py` — `cmd_reroll_quest()`  
**Тип:** Рассинхронизация (купон работает только в Mini App)

**Описание:**  
`cmd_reroll_quest` всегда списывает `QUEST_REROLL_PRICE` монет. В Mini App (`Quests.tsx`) можно использовать купон `quest_reroll` из гачи для бесплатного реролла. В боте купон из инвентаря игнорируется — `бот пересдать` всегда платный.

**Исправление:**  
Перед списанием денег проверять `gacha_inventory` на наличие `item_key='quest_reroll'` у пользователя и использовать его вместо оплаты.

---

### MED-003 — Займы: уведомления через Telegram не отправляются

**Файлы:**  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — `miniapp_loans_create`  
- `PredvestnikBot/handlers/wallet.py` — `cmd_give_loan`  
**Тип:** UX-проблема

**Описание:**  
При создании займа (как через Mini App, так и через бота) заёмщик не получает никакого Telegram-уведомления. Он узнаёт о предложении займа только если:
- Зайдёт в Mini App → Loans  
- Увидит сообщение в чате (если кредитор упомянул его)

**Исправление:**  
После `create_loan()` отправить ДМ заёмщику через Bot API:
```python
await bot.send_message(borrower_id, f"💰 {lender_name} предлагает тебе займ {amount}🪙. Открой Mini App для подтверждения.")
```

---

### MED-004 — Solo Boss прогресс не отображается в лидерборде чата

**Файлы:**  
- `PredvestnikBot/database/db.py` — `get_boss_leaderboard()` — читает только `boss_damage_log`  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — `miniapp_solo_boss_attack` — пишет в `solo_boss_sessions`  
**Тип:** Рассинхронизация прогресса (связано с SYNC-003)

**Описание:**  
Команда `бот топ босс` показывает топ по суммарному урону из `boss_damage_log`. Урон от Solo Boss сессий идёт только в `solo_boss_sessions` / `user_damage` — в `boss_damage_log` не попадает. Активные Solo Boss игроки на лидерборде чата выглядят хуже чем они есть.

---

### MED-005 — Косметические эффекты профиля (flair) невидимы в боте

**Файлы:**  
- Легендарные предметы типа `lego_flair_star`, `lego_flair_void` в каталоге гачи  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — применяются через `miniapp_profile`  
**Тип:** Рассинхронизация отображения

**Описание:**  
Пользователь выигрывает редкий легендарный `flair` (косметический эффект профиля) из гачи. В боте этот предмет никак не отображается и не работает. Эффект виден только в Mini App в разделе профиля. Для пользователей, редко открывающих Mini App — ценный предмет выглядит как баг или мусор.

---

### MED-006 — Бейджи и приветствия: нет команды просмотра в боте

**Файлы:**  
- `database/db.py` — таблицы `user_badges`, `user_greetings`  
- `IESA_ROOT/IESA_ROOT/miniapp_views.py` — только через Mini App  
**Тип:** Функция полностью невидима в боте

**Описание:**  
Пользователь зарабатывает бейджи (ачивки за достижения) и персонализированные приветствия (из гачи). В боте нет ни одной команды чтобы посмотреть свои бейджи. Через `бот профиль` они тоже не отображаются. Пользователь накапливает предметы, которые он никогда не увидит если не заходит в Mini App.

---

## 🛠 ПЛАН УНИФИКАЦИИ И ИСПРАВЛЕНИЙ

### Приоритет 1 — Исправить немедленно (блокирующие баги)

1. **CRIT-001**: Добавить `import logging; _log = logging.getLogger(__name__)` в `api/economy.py`
2. **CRIT-002**: Переименовать `logger` → `_log` в строке 29 `api/auction.py`
3. **CRIT-003**: Исправить `os.environ.get("BOT_TOKEN")` → `os.environ.get("PREDVESTNIK_BOT_TOKEN")` в `api/auction.py`

### Приоритет 2 — Исправить в ближайшем спринте (критическое UX)

4. **CRIT-004**: Перенести `_boss_hp` в PostgreSQL таблицу `world_boss_state`
5. **SYNC-001**: Синхронизировать цены еды через `shared_prices.FOOD_ITEMS`; убить `cb_buy_food` legacy callback
6. **CRIT-005**: Реализовать бесплатную молитву через поле в БД ИЛИ убрать анонс из `handlers/checkin.py`

### Приоритет 3 — Улучшения синхронизации (Sprint +1)

7. **SYNC-002**: Добавить `+{quest['mora']} 🪙` в текст квеста в боте
8. **SYNC-006**: Заменить все legacy Phase 2 callbacks на "alert + return"
9. **HIGH-001**: Исправить рефанд экспедиции с учётом `wallet_type`
10. **HIGH-003**: Добавить TTL-очистку для `_active_coins` и `_resolved_coins`

### Приоритет 4 — Стратегические улучшения

11. **SYNC-003**: Унифицировать Boss лидерборды (или добавить отдельный Solo Boss топ)
12. **SYNC-004 + SYNC-005**: Добавить `бот инвентарь` / `бот зелья` / `бот тема` команды в чат
13. **SYNC-008**: Добавить `бот аукцион` — просмотр активных лотов из чата
14. **MED-003**: Telegram ДМ-уведомления при создании/принятии займа
15. **MED-002**: Поддержка купонов реролла в боте

---

## 📁 СПИСОК ИССЛЕДОВАННЫХ ФАЙЛОВ

| Файл | Статус | Найденные проблемы |
|------|--------|--------------------|
| `PredvestnikBot/api/economy.py` | ❌ CRIT | `_log` undefined (CRIT-001) |
| `PredvestnikBot/api/auction.py` | ❌ CRIT | `_log` undefined × 16 (CRIT-002), wrong BOT_TOKEN (CRIT-003) |
| `PredvestnikBot/handlers/boss.py` | ❌ CRIT | In-memory HP (CRIT-004) |
| `PredvestnikBot/handlers/checkin.py` | ❌ CRIT | free_gacha объявлена но не работает (CRIT-005) |
| `PredvestnikBot/handlers/food.py` | ❌ CRIT+SYNC | Неверные цены (SYNC-001), legacy callbacks (SYNC-006) |
| `PredvestnikBot/handlers/quests.py` | ❌ SYNC | Нет mora в тексте награды (SYNC-002), купон реролла игнорируется (MED-002) |
| `PredvestnikBot/handlers/expeditions.py` | ❌ SYNC | Legacy callbacks (SYNC-006) |
| `PredvestnikBot/handlers/bank.py` | ❌ SYNC | Legacy callbacks (SYNC-006) |
| `PredvestnikBot/handlers/gacha.py` | ⚠️ | free_gacha не используется |
| `PredvestnikBot/handlers/casino.py` | ❌ HIGH | Memory leak в sets (HIGH-003) |
| `PredvestnikBot/handlers/wallet.py` | ⚠️ | Нет уведомления займополучателю (MED-003) |
| `PredvestnikBot/api/expeditions.py` | ❌ HIGH | Неверный рефанд (HIGH-001), TOCTOU (HIGH-002) |
| `PredvestnikBot/api/roulette.py` | ❌ HIGH | Race condition (HIGH-005) |
| `PredvestnikBot/api/gacha.py` | ⚠️ | free_gacha не используется |
| `PredvestnikBot/api/pets.py` | ✅ | Проблем не найдено |
| `PredvestnikBot/api/bank.py` | ✅ | Проблем не найдено |
| `PredvestnikBot/api/achievements.py` | ✅ | Проблем не найдено |
| `PredvestnikBot/shared_prices.py` | ✅ | Корректный источник истины для цен |
| `PredvestnikBot/config.py` | ✅ | `PREDVESTNIK_BOT_TOKEN` — правильное имя переменной |
| `PredvestnikBot/database/db.py` | ⚠️ | `perform_checkin` возвращает `free_gacha` который никто не использует |
| `IESA_ROOT/IESA_ROOT/miniapp_views.py` | ⚠️ | free_gacha не обрабатывается; нет уведомлений займов |
| `frontend/src/pages/BossFight.tsx` | ⚠️ | Отдельная система от чат-босса (SYNC-003) |
| `frontend/src/pages/Quests.tsx` | ✅ | Показывает ОБОИ награды (XP + Мора) — бот отстаёт |

---

