# PET_AUDIT_FOR_AI — Технический план (только незавершённые блоки)

> **Все B1–B22 выполнены.** Ниже — только pending задачи из AUDIT_V3.md.  
> Перед каждым блоком перечитать BASE_PROMPT.md.

---

## ✅ ВЫПОЛНЕНО (B1–B22 + AUDIT_V3 часть 1)

Всё реализовано. Подробная архитектура → `memory/project_architecture.md`.

**Последние фиксы:**
- BUG-1: db.py commit после dev rank UPDATE → chest transaction ошибка исправлена
- events.py: авто-ранг 6 для владельца чата при входе бота
- events.py: приветственные сообщения (5 вариантов) бота и новых юзеров
- streak_mw: защита от callback_query событий

---

# PENDING БЛОКИ (AUDIT_V3)

---

## 🟡 БЛОК C1-A — Чёрный список чата (per-chat)

**Цель.** Пользователь в ЧС → при входе бот его сразу кикает.

### БД
```sql
chat_blacklist(
  chat_id INTEGER,
  user_id INTEGER,
  reason TEXT,
  added_by INTEGER,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (chat_id, user_id)
)
```

### Команды
```
бот чс                           → список ЧС чата
бот чс добавить, @юзер [причина] → добавить
бот чс убрать, @юзер             → убрать
```

### Права
Требует ранг ≥ `rank_ban` из chat_settings (по умолчанию 5).

### Логика
- `on_user_status_changed` в events.py: при входе юзера → проверить `chat_blacklist`
- Если есть → `bot.ban_chat_member(chat_id, user_id)` → через секунду `bot.unban_chat_member` (kick без бана)
- Уведомить в чат о кике из ЧС

### Файлы
- `bot/core/database.py` — таблица
- `infrastructure/repositories/blacklist.py` (новый)
- `bot/handlers/blacklist.py` (новый)
- `bot/handlers/events.py` — проверка при входе

### Зависимости
Нет

---

## 🟡 БЛОК C1-B — Уведомление при выходе + кнопка [Добавить в ЧС]

**Цель.** Когда юзер уходит или его кикают — бот пишет сообщение с кнопками.

### Формат
```
👋 Buy_me_Acoffee покинул(а) чат

[🚫 Добавить в ЧС]  [✖️ Закрыть]
```

### Логика
- Только администраторы могут нажать `[🚫 Добавить в ЧС]` (проверка ранга)
- Сообщение активно 10 минут — потом становится неактивным
- `[✖️ Закрыть]` — удаляет сообщение (любой может)

### Файлы
- `bot/handlers/events.py` — `on_user_status_changed` → при left/kicked отправить кнопочное сообщение

### Зависимости
C1-A (для функции добавления в ЧС)

---

## 🟡 БЛОК C1-C — Глобальный ЧС бота (dev-only)

**Цель.** Developer может заблокировать конкретного юзера или чат для всего бота.

### БД
```sql
global_blacklist(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT,   -- 'user' | 'chat'
  entity_id INTEGER,
  reason TEXT,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Команды (только developer)
```
бот dev глобал чс                        → показать список
бот dev глобал чс добавить, @юзер [причина]
бот dev глобал чс добавить, [chat_id]
бот dev глобал чс убрать, @юзер
```

### Логика
В `db_middleware` — ПЕРВАЯ проверка перед всем остальным:
```python
# Проверить global_blacklist
# Если entity_id в ЧС → return (не обрабатывать)
```

### Файлы
- `bot/core/database.py` — таблица
- `infrastructure/repositories/blacklist.py` — добавить global функции
- `bot/middlewares/db.py` — проверка в начале
- `bot/handlers/dev.py` — команды управления

---

## 🟢 БЛОК C2 — Система модулей (вкл/выкл через кнопки)

**Цель.** Администратор через кнопки может выключить/включить модули бота.

### Модули
| Ключ | Модуль |
|---|---|
| `module_shop` | Магазин |
| `module_gacha` | Гача |
| `module_expeditions` | Экспедиции |
| `module_auction` | Аукцион |
| `module_games` | Мини-игры |
| `module_exchange` | Конвертер |
| `module_quests` | Квесты |
| `module_zoo` | Зоопарк |
| `module_warps` | Варп-команды |

### БД
```python
# new_schema_columns в database.py:
("chat_settings", "module_shop",        "INT DEFAULT 1"),
("chat_settings", "module_gacha",       "INT DEFAULT 1"),
("chat_settings", "module_expeditions", "INT DEFAULT 1"),
("chat_settings", "module_auction",     "INT DEFAULT 1"),
("chat_settings", "module_games",       "INT DEFAULT 1"),
("chat_settings", "module_exchange",    "INT DEFAULT 1"),
("chat_settings", "module_quests",      "INT DEFAULT 1"),
("chat_settings", "module_zoo",         "INT DEFAULT 1"),
("chat_settings", "module_warps",       "INT DEFAULT 1"),
```

```sql
-- Глобальный toggle (только dev)
global_module_toggles(
  module_key TEXT PRIMARY KEY,
  enabled INTEGER DEFAULT 1,
  disabled_reason TEXT,
  updated_at TIMESTAMP
)
```

### UI
В `бот настройки чата` добавить секцию "🧩 Модули" с переключателями.
`бот dev модули` — глобальное управление.

### Middleware
`bot/middlewares/module_check_mw.py` — перед обработкой команды проверить включён ли модуль.
При выключенном модуле: `"🔧 Этот раздел временно недоступен."`

### Файлы
- `bot/core/database.py` — колонки + таблица
- `bot/middlewares/module_check_mw.py` (новый)
- `bot/handlers/chat_settings.py` — секция модулей
- `bot/handlers/dev.py` — команда модули

---

## 🟡 БЛОК C4-E — Квесты не считают callback-клики

**Цель.** Метрики квестов (`messages_in_chat_today` и другие) должны инкрементироваться только от реальных сообщений.

**Проблема.** `quest_increment` вызывается в обработчиках, но некоторые из них (auction_bid, gacha_spins) вызываются из callback-обработчиков — это OK. Но `messages_in_chat_today` зависит от `daily_user_stats.message_count`, которая может включать клики если db_middleware обрабатывает callbacks (проверить после Bug-2 фикса).

**Фикс:** Убедиться что `daily_user_stats` инкрементируется только в блоке `event.message` в db_middleware (уже выполнено). Квест msg_15/msg_30 читает `user_messages_count_per_day` из `user_chat_stats` — проверить что это значение корректное.

**Файлы:** `bot/handlers/quests.py`, `services/quests.py`

---

## 🟡 БЛОК C5-A — `бот ранг ,` с пробелом не работает

**Проблема.** `бот ранг , @юзер 5` (пробел перед запятой) → бот отвечает "команда не найдена".

**Фикс.** В `TextCmd.__call__` нормализовать пробелы вокруг запятой:
```python
import re
clean_text = re.sub(r'\s*,\s*', ', ', clean_text)
```

**Файлы:** `bot/filters/text_commands.py`

---

## 🟡 БЛОК C5-C — `бот шоп` / `бот магазин` UX

**Проблема.** Из лога: `Бот шоп` → сразу показывает форму покупки конкретного предмета вместо каталога.

**Исследовать:** В `bot/handlers/shop.py` проверить почему `бот шоп` вместо `render_shop` попадает в `cb_shop_qty` напрямую. Возможно конфликт алиасов.

**Файлы:** `bot/handlers/shop.py`

---

## 🟢 БЛОК C6 — Web API расширение

**Цель.** `/profile/{user_id}` должен возвращать больше данных.

**Добавить в ответ:**
- `global_rank_name` — строка ("🌌 Главный разработчик")
- `balance_diamonds` — как float (сейчас int 0 вместо 0.0)
- `streak` — текущий стрик
- `achievements_count` — количество разблокированных достижений

**Файлы:** `FastAPI/main.py` или аналог (проверить)

---

# КАК НАЧИНАТЬ БЛОК

1. Перечитать BASE_PROMPT.md
2. Перечитать блок в этом файле
3. `TodoWrite` подзадачи
4. Реализовать
5. `ast.parse()` всех изменённых файлов
6. Поставить ✅
