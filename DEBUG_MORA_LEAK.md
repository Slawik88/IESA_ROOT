# Отладка: утечка Моры и предметов между чатами

---

## 1. Хранение состояния

### 1a. Мора — глобальный баланс

```sql
-- ЕДИНЫЙ БАЛАНС на пользователя (не привязан к чату)
TABLE users (
    user_id    BIGINT PRIMARY KEY,
    balance    BIGINT DEFAULT 0,      -- ← вся Мора здесь, общая для всех чатов
    total_earned BIGINT DEFAULT 0
)

-- МЕТА-ДАННЫЕ на пару (user_id, chat_id) — НЕ баланс
TABLE user_mora (
    user_id   BIGINT,
    chat_id   BIGINT,
    vip       INT DEFAULT 0,
    streak_days INT DEFAULT 0,
    last_daily TEXT,
    top_frame TEXT,
    xp_boost_until TIMESTAMPTZ,
    PRIMARY KEY (user_id, chat_id)
)
```

**Вывод**: Мора — глобальна. Заработал 100 в чате A → баланс вырос в чате B тоже.
Это НЕ баг, это архитектурное решение. Но для пользователей выглядит как «утечка».

### 1b. Инвентарь — должен быть per-chat

```sql
TABLE gacha_inventory (
    id       BIGINT PRIMARY KEY,
    user_id  BIGINT NOT NULL,
    chat_id  BIGINT NOT NULL,   -- ← предметы чат-специфичны в БД
    item_key TEXT,
    rarity   TEXT,
    equipped INT DEFAULT 0,
    slot     TEXT
)
```

**БАГ (исправлен в коммите c6b91af7)**: GET `/api/inventory` запрашивал
`WHERE user_id=? ORDER BY id DESC` — без фильтра по `chat_id`.
Пользователь видел предметы из ВСЕХ чатов одновременно.
Сейчас: `WHERE user_id=? AND chat_id=?` — фильтрует правильно.

---

## 2. Обработчики начисления Моры

### 2a. Автоматическое начисление — middleware

Файл: `PredvestnikBot/middlewares/message_counter.py`

```python
# _process_economy вызывается из AutoModMiddleware на каждое сообщение.
# ТОЛЬКО для не-изолированных чатов (см. раздел 3).

async def _process_economy(user_id: int, chat_id: int, event: Message) -> None:
    # 1. Ежедневный бонус
    is_daily, _streak, streak_bonus = await check_daily_mora(user_id, chat_id)
    if is_daily:
        await add_mora(user_id, chat_id, MORA_DAILY_BONUS)      # +x Моры глобально
        if streak_bonus:
            await add_mora(user_id, chat_id, MORA_STREAK_BONUS)

    # 2. Случайный дроп по таймеру
    if now - _mora_cooldown.get((user_id, chat_id), 0) >= MORA_MSG_COOLDOWN:
        if random.random() < MORA_MSG_CHANCE:
            _mora_cooldown[(user_id, chat_id)] = now
            await add_mora(user_id, chat_id, drop)

    # 3. Квестовая награда
    if quest["type"] == "messages":
        if just_done:
            await add_mora(user_id, chat_id, mora_reward)
```

**Ключевое**: `user_id` = `message.from_user.id`, `chat_id` = `message.chat.id`.
Кулдаун хранится в dict с ключом `(user_id, chat_id)` — чаты не перемешиваются.

### 2b. Ручное начисление — команды Owner

Файл: `PredvestnikBot/handlers/owner.py`

```python
@router.message(BotCommand("выдать"), RankFilter("owner"))
async def cmd_emit_mora(message: Message, cmd_args: str):
    # ...
    # БЫЛО (до фикса): add_mora(uid, message.chat.id, amount)
    #   → если команда запущена из admin-чата → is_isolated_chat = True → NO-OP
    #   → бот показывал "+500 🪙" но реально 0 добавлялось

    # СЕЙЧАС (после коммита c6b91af7):
    new_bal = await add_mora(uid, 0, amount)  # chat_id=0 → без проверки изоляции
```

**Тот же фикс** в `cmd_setuser` для полей `мора`/`+200`/`-100`.

### 2c. Ядро начисления — `add_mora`

Файл: `PredvestnikBot/database/db.py` ~строка 3313

```python
async def add_mora(user_id: int, chat_id: int, amount: int) -> int:
    if chat_id and is_isolated_chat(chat_id):
        # ИЗОЛИРОВАННЫЙ ЧАТ → NO-OP, возвращает ТЕКУЩИЙ баланс (не новый!)
        # До фикса: caller не знал, что ничего не добавилось
        return current_balance  # ← ИСТОЧНИК ЛОЖНОГО УСПЕХА

    # Happy path
    await db.execute(
        "UPDATE users SET balance = GREATEST(0, COALESCE(balance, 0) + ?) WHERE user_id = ?",
        (amount, user_id),
    )
    return new_balance
```

---

## 3. Контекст чата — изоляция admin/test чатов

### 3a. Двухуровневая защита

**Уровень 1 — Middleware (`AutoModMiddleware`)**

```python
# middlewares/message_counter.py строка ~230

is_isolated = in_group and (
    event.chat.id in get_admin_group_ids() or is_test_chat(event.chat.id)
)
data["is_isolated_chat"] = is_isolated  # инжектируется в data для фильтров

if is_isolated:
    # Экономика полностью пропускается — только регистрация юзера/чата
    return await handler(event, data)  # ← ранний выход, _process_economy не вызывается
```

**Уровень 2 — Фильтр роутера (`MainChatOnly`)**

```python
# filters/chat_mode.py

class MainChatOnly(BaseFilter):
    async def __call__(self, message: Message, is_isolated_chat: bool = False) -> bool:
        if message.chat.type not in ("group", "supergroup"):
            return True   # личные сообщения всегда проходят
        return not is_isolated_chat  # изолированный чат → команда не выполняется
```

Роутеры `economy.py` и `wallet.py` подключают этот фильтр:
```python
router = Router()
router.message.filter(MainChatOnly())  # все команды в роутере защищены
```

**Уровень 3 — DB safety net (`add_mora`)**

```python
def is_isolated_chat(chat_id: int) -> bool:
    return chat_id in _admin_groups or chat_id in _test_chats
```

Это резервный слой на случай если какой-то код обходит middleware.

### 3b. Разделение типов чатов

| Тип чата | Middleware | `MainChatOnly` | `add_mora` |
|---|---|---|---|
| Личные сообщения (DM) | проходит | проходит | `chat_id=0` → работает |
| Обычная группа | полный pipeline | проходит | работает |
| Admin-группа | early return (регистрация юзера, без экономики) | блокирует команды | NO-OP при добавлении |
| Тест-чат | early return | блокирует команды | NO-OP при добавлении |

### 3c. `get_admin_group_ids()` vs `_admin_groups`

```python
# db.py
_admin_groups: set[int] = set()  # только в боте — в Django всегда пуст!

def get_admin_group_ids() -> set[int]:
    return _admin_groups  # middleware читает отсюда

async def load_admin_groups():
    # Вызывается при старте бота — читает таблицу admin_groups из БД
    # НЕ вызывается в Django процессе
```

**Риск**: В Django ASGI `_admin_groups` всегда пустой → `is_isolated_chat()` всегда `False`
→ Django-сторона никогда не блокирует начисление. Это нормально для `/api/dev/add_mora`
(явная выдача), но если бы Django вызывал автоматическое начисление — был бы баг.

---

## 4. Глобальный стейт — полный список

| Переменная | Файл | Тип | Ключ | Риск утечки? |
|---|---|---|---|---|
| `_mora_cooldown` | middleware | `dict[(uid,cid), float]` | `(user_id, chat_id)` | ❌ нет — ключ включает оба ID |
| `_mora_daily_checked` | middleware | `dict[(uid,cid), str]` | `(user_id, chat_id)` | ❌ нет |
| `_xp_cooldown` | middleware | `dict[(uid,cid), float]` | `(user_id, chat_id)` | ❌ нет |
| `_pending_resolved` | middleware | `set[(uid,cid)]` | `(user_id, chat_id)` | ❌ нет |
| `_shield_checked` | middleware | `set[(uid,cid)]` | `(user_id, chat_id)` | ❌ нет |
| `_admin_groups` | db.py | `set[int]` | `chat_id` | ✅ источник утечки — пустой в Django |
| `_test_chats` | db.py | `set[int]` | `chat_id` | ✅ источник утечки — пустой в Django |
| `_boss_hp` | boss.py | `dict[int, int]` | `chat_id` | ❌ нет — per-chat |
| `_attack_cooldown` | boss.py | `dict[(uid,cid), float]` | `(user_id, chat_id)` | ❌ нет |
| `_DILIGENCE_ACTIVE` | diligence.py | `dict[int, bool]` | `chat_id` | ❌ нет — per-chat |
| `_DILIGENCE_CLICKS` | diligence.py | `dict[int, dict[uid,int]]` | `chat_id` | ❌ нет — per-chat |
| `_active_events` | tax_event.py | `dict[int, int]` | `chat_id` | ❌ нет — per-chat |
| `_active_coins` | casino.py | `set[(uid,msg_id)]` | `(uid, msg_id)` | ❌ нет — per-user |
| `_awaiting_marriages` | admin.py | `dict[int, ...]` | `chat_id` | ❌ нет — per-chat |
| `_proposals` | fun.py | `dict[(uid,uid,cid), float]` | `(u1, u2, chat_id)` | ❌ нет |

**Вывод**: Глобальный стейт для регулярной экономики НЕ является источником утечки.
Все кулдауны/флаги используют составной ключ `(user_id, chat_id)`.

---

## 5. Итоговая диагностика

### Реальные источники «утечки»

**1. Мора — по дизайну глобальна**

Это не баг. `users.balance` — один на пользователя. Если пользователь хочет видеть
«разные кошельки» в разных чатах — нужно менять архитектуру на `user_mora.balance`.

**2. Инвентарь — баг исправлен** (`c6b91af7`)

GET `/api/inventory` теперь фильтрует по `chat_id`. До фикса показывал все предметы.

**3. Ложный успех команд Owner** — баг исправлен (`c6b91af7`)

`бот выдать 500 @user` в admin-чате → теперь всегда применяется (chat_id=0).

**4. `_admin_groups` пустой в Django ASGI**

Не вызывает реальной утечки, но означает что Django не блокирует начисление.
Это приемлемо: Django вызывает только явные admin-операции, не автоматику.

### Что проверить если «Мора передаётся куда не нужно»

```
1. Какой чат является источником? Он в admin_groups или test_chats?
2. Команда или автоматическое начисление?
   - Команда owner → проверить что запускается из правильного чата (или chat_id=0 уже фиксит)
   - Автоматика → проверить что _admin_groups корректно загружен (load_admin_groups() вызвался)
3. Инвентарь → пересобрать Mini App с обновлённым бэкендом (c6b91af7)
4. Проверить PREDVESTNIK_DATABASE_URL в Django окружении — если пустой, все данные идут в SQLite-призрак
```

---

## 6. Перекрёстная проверка чат-контекста в handlers

Все обработчики экономики извлекают контекст единообразно:

```python
uid     = message.from_user.id   # кто выполняет команду
chat_id = message.chat.id        # в каком чате выполняется

# Пример из handlers/wallet.py (cmd_transfer):
res = await _api_transfer(uid, target_id, chat_id, amount)
#                                          ↑
#                                 transfer записывает tax в chat_treasury[chat_id]
#                                 баланс меняется глобально (users.balance)
```

**Личные сообщения (DM)**: `message.chat.type == "private"`, `chat_id == user_id`.
Команды wallet/economy делают ранний выход: `if message.chat.type not in ("group", "supergroup"): return`.
В DM экономика работает только через Mini App API.

**Нет ни одного обработчика** который бы перепутал `from_user.id` с `chat.id` или
использовал константный/глобальный `chat_id` вместо `message.chat.id`.
